import asyncio
import functools
import os
from datetime import datetime
from functools import wraps
from itertools import chain
from pathlib import Path
from subprocess import PIPE
from typing import List, Optional, Tuple

import aiofiles
import click
import httpx
import ujson as json
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.interfaces import (
    BuildkiteArtifact,
    BuildkiteStatus,
    BuildResult,
    GHAJobStat,
    GHCommit,
    TestResult,
    _parse_duration,
)


def retry(func):
    @wraps(func)
    async def wrapper(*args, **kwargs):
        exception = None
        for _ in range(3):
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                exception = e
        else:
            raise exception

    return wrapper


def run_as_sync(async_func):
    @wraps(async_func)
    def wrapper(*args, **kwargs):
        asyncio.run(async_func(*args, **kwargs))

    return wrapper


async def get_or_fetch(
    cache_path: Path, *, use_cached: bool, result_cls, many: bool, async_func
):
    if not use_cached or not cache_path.exists():
        result = await async_func()
        if result is None:
            return
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(cache_path, "w") as f:
            if result_cls and many:
                content = json.dumps([r.to_dict() for r in result])
            elif result_cls and not many:
                content = json.dumps(result.to_dict())
            else:
                content = json.dumps(result)
            await f.write(content)
        return result
    else:
        async with aiofiles.open(cache_path) as f:
            content = await f.read()
            if result_cls and many:
                loaded = json.loads(content)
                return [result_cls.from_dict(r) for r in loaded]
            elif result_cls and not many:
                return result_cls.from_json(content)
            else:
                return json.loads(content)


def _yield_test_result(bazel_log_path):
    # Gather the known flaky set and test owners
    flaky_tests = set()
    test_owners = dict()
    with open(bazel_log_path) as f:
        for line in f:
            loaded = json.loads(line)
            if "targetConfigured" in loaded["id"] and "tag" in loaded["configured"]:
                test_name = loaded["id"]["targetConfigured"]["label"]
                for tag in loaded["configured"]["tag"]:
                    if tag == "flaky":
                        flaky_tests.add(test_name)
                    if tag.startswith("team:"):
                        test_owners[test_name] = tag.replace("team:", "")

    with open(bazel_log_path) as f:
        for line in f:
            loaded = json.loads(line)
            if "testSummary" in loaded:
                test_summary = loaded["testSummary"]

                name = loaded["id"]["testSummary"]["label"]
                status = test_summary["overallStatus"]
                if status in {"FAILED", "TIMEOUT", "NO_STATUS"}:
                    status = "FAILED"
                duration_s = float(test_summary["totalRunDurationMillis"]) / 1e3
                yield TestResult(
                    name,
                    status,
                    duration_s,
                    name in flaky_tests,
                    test_owners.get(name, "unknown"),
                )


def _process_single_build(dir_name) -> Optional[BuildResult]:
    metadata_path = dir_name / "metadata.json"
    if not os.path.exists(dir_name / "metadata.json"):
        return None

    with open(metadata_path) as f:
        metadata = json.load(f)

    return BuildResult(
        sha=metadata["build_env"]["TRAVIS_COMMIT"],
        job_url=metadata["build_env"]["TRAVIS_JOB_WEB_URL"],
        os=metadata["build_env"]["TRAVIS_OS_NAME"],
        build_env=metadata["build_config"]["config"]["env"],
        job_id=os.path.split(dir_name)[-1],
        results=list(
            chain.from_iterable(
                _yield_test_result(log) for log in dir_name.glob("bazel_log.*")
            )
        ),
    )

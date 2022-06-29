import asyncio
import functools
import os
from itertools import chain
from pathlib import Path
from subprocess import PIPE
from typing import List

from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import _process_single_build, get_or_fetch
from ray_ci_tracker.interfaces import BuildResult, GHCommit


class S3DataSource:
    @staticmethod
    async def fetch_all(cache_path: Path, cached_s3: bool, commits: List[GHCommit]):
        concurrency_limiter = asyncio.Semaphore(value=20)

        bazel_events = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path / f"bazel_cached/{commit.sha}/cached_result.json",
                    use_cached=cached_s3,
                    result_cls=BuildResult,
                    many=True,
                    async_func=functools.partial(
                        S3DataSource._get_bazel_events_s3,
                        s3_path=f"s3://ray-travis-logs/bazel_events/master/{commit.sha}",
                        download_dir=cache_path / f"bazel_events/master/{commit.sha}",
                        concurrency_limiter=concurrency_limiter,
                    ),
                )
                for commit in commits
            ]
        )
        return list(chain.from_iterable(bazel_events))

    @staticmethod
    async def _get_bazel_events_s3(
        s3_path, download_dir, concurrency_limiter: asyncio.Semaphore
    ) -> List[BuildResult]:

        async with concurrency_limiter:
            proc = await asyncio.subprocess.create_subprocess_shell(
                f"aws s3 sync {s3_path} {download_dir}",
                shell=True,
                stdout=PIPE,
                stderr=PIPE,
            )
            try:
                status = await asyncio.wait_for(proc.wait(), timeout=60)
            except asyncio.TimeoutError as e:
                print(f"`aws s3 sync {s3_path} {download_dir}` timedout")
                return []
            assert status == 0, await proc.communicate()

        lst = [
            _process_single_build(Path(download_dir) / build)
            for build in os.listdir(download_dir)
        ]
        return [item for item in lst if item is not None]

import asyncio
import functools
import os
from itertools import chain
from pathlib import Path
from subprocess import PIPE
import sys
from typing import List

from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import _process_single_build, get_or_fetch
from ray_ci_tracker.interfaces import BuildResult, GHCommit

# Commits that are known to be bad, often has bazel build logs that are too
# large to sync down.
_COMMIT_BLACKLIST = []


class S3DataSource:
    @staticmethod
    async def fetch_all(cache_path: Path, cached_s3: bool, commits: List[GHCommit]):
        concurrency_limiter = asyncio.Semaphore(10)

        bazel_events = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path / f"bazel_cached/{commit.sha}/cached_result.json",
                    use_cached=cached_s3,
                    result_cls=BuildResult,
                    many=True,
                    async_func=functools.partial(
                        S3DataSource._get_bazel_events_s3,
                        commit=commit.sha,
                        bucket="ray-travis-logs",
                        s3_path=f"bazel_events/master/{commit.sha}",
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
        commit, bucket, s3_path, download_dir, concurrency_limiter: asyncio.Semaphore
    ) -> List[BuildResult]:
        if commit in _COMMIT_BLACKLIST:
            return []
        
        os.makedirs(download_dir, exist_ok=True)

        async with concurrency_limiter:
            ls_proc = await asyncio.subprocess.create_subprocess_shell(
                f"aws s3 ls --recursive s3://{bucket}/{s3_path}",
                shell=True,
                stdout=PIPE,
                stderr=PIPE,
            )

            objects, stderr = await ls_proc.communicate()
            if stderr:
                print(stderr.decode("utf-8"))
            assert ls_proc.returncode == 0

            lines = objects.decode("utf-8").splitlines()

            exclude = []
            for line in lines:
                # Trim the leading date-time
                line = line[len("2020-01-01 00:00:00 "):].strip()
                fields = line.split()
                if len(fields) != 2:
                    print(f"Unexpected line: {line}")
                    continue
                size = int(fields[0])
                object_key = fields[1]
                if object_key.endswith("/"):
                    continue
                if size > 100000000:
                    print(f"Skipping {object_key} because it's too large: {size}")
                    continue
                exclude.append(object_key)

            cmd = f"aws s3 sync s3://{bucket}/{s3_path} {download_dir}"
            for obj in exclude:
                cmd += f" --exclude {obj}"
            proc = await asyncio.subprocess.create_subprocess_shell(
                cmd,
                shell=True,
                stdout=PIPE,
                stderr=PIPE,
            )
            _, stderr = await proc.communicate()
            if stderr:
                print(stderr.decode("utf-8"))
            assert proc.returncode == 0

        lst = [
            _process_single_build(Path(download_dir) / build)
            for build in os.listdir(download_dir)
        ]
        return [item for item in lst if item is not None]

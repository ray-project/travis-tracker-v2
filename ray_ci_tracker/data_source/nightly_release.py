import os
import re
from pathlib import Path
from typing import List, Optional

import httpx
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import get_or_fetch, retry
from ray_ci_tracker.interfaces import SiteNightlyRun

BUILDKITE_API = "https://api.buildkite.com/v2"
ORG, PIPELINE = "ray-project", "release"
WHEEL_BASE = "https://s3-us-west-2.amazonaws.com/ray-wheels/master"

# Scheduled nightlies are the only master builds carrying AUTOMATIC=1. Builds
# triggered from the API or the Buildkite UI are ad-hoc maintainer runs and are
# deliberately excluded.
NIGHTLY_FREQUENCIES = {"nightly", "nightly-3x"}

# Release-test jobs are labelled like "foo_test.aws (None) (0)". The image work
# in the same build (wanda:, :tapioca:, :crane:) and "init" carry no such
# suffix, and counting them roughly doubles the apparent test total.
TEST_JOB_NAME = re.compile(r"\(.*\) \(\d+\)\s*$")

FAILED_STATES = {"failed", "broken", "timed_out"}


def _job_name(job: dict) -> str:
    return (job.get("name") or job.get("label") or "").strip()


def _is_test_job(job: dict) -> bool:
    return job.get("type") == "script" and bool(TEST_JOB_NAME.search(_job_name(job)))


def parse_build(build: dict) -> Optional[SiteNightlyRun]:
    """Turn one Buildkite build into a nightly row, or None if it is not one."""
    env = build.get("env") or {}
    if env.get("AUTOMATIC") != "1":
        return None
    frequency = env.get("RELEASE_FREQUENCY")
    if frequency not in NIGHTLY_FREQUENCIES:
        return None

    tests = [j for j in build.get("jobs", []) if _is_test_job(j)]
    failed = [j for j in tests if j.get("state") in FAILED_STATES]
    sha = build.get("commit") or ""

    return SiteNightlyRun(
        build_number=build["number"],
        frequency=frequency,
        # A run that never got past init has no tests to speak of; the frontend
        # renders these as "incomplete" rather than as a pass.
        state=build.get("state") or "unknown",
        commit=sha,
        commit_short=sha[:8],
        created_at=build.get("created_at") or "",
        wheel_base=f"{WHEEL_BASE}/{sha}/" if sha else "",
        tests_total=len(tests),
        tests_failed=len(failed),
        failed_tests=sorted(_job_name(j) for j in failed),
    )


class NightlyReleaseSource:
    @staticmethod
    @retry
    async def fetch_page(page: int) -> List[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUILDKITE_API}/organizations/{ORG}/pipelines/{PIPELINE}/builds",
                params={"branch": "master", "per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {os.environ['BUILDKITE_TOKEN']}"
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()

    @staticmethod
    async def fetch_all(cache_path: Path, cached: bool, pages: int = 2):
        print("💤 Downloading nightly release builds")
        raw_pages = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path / f"nightly_release/page_{page}.json",
                    use_cached=cached,
                    result_cls=None,
                    many=False,
                    async_func=lambda page=page: NightlyReleaseSource.fetch_page(page),
                )
                for page in range(1, pages + 1)
            ]
        )

        runs, seen = [], set()
        for builds in raw_pages:
            for build in builds or []:
                run = parse_build(build)
                if run is not None and run.build_number not in seen:
                    seen.add(run.build_number)
                    runs.append(run)

        runs.sort(key=lambda r: r.build_number, reverse=True)
        return runs

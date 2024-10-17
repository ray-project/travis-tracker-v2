import asyncio
import functools
import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import httpx
from dotenv import load_dotenv
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import get_or_fetch
from ray_ci_tracker.interfaces import GHAJobStat, GHCommit, _parse_duration

load_dotenv()

GH_HEADERS = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}


class GithubDataSource:
    @staticmethod
    async def _get_latest_commit() -> List[GHCommit]:
        resp = httpx.get(
            "https://api.github.com/repos/ray-project/ray/commits?per_page=80",
            headers=GH_HEADERS,
        )
        assert resp.status_code == 200, "Pinging github API /commits failed"
        json_data = resp.json()

        return [
            GHCommit(
                sha=data["sha"],
                unix_time_s=int(
                    datetime.fromisoformat(
                        data["commit"]["author"]["date"].replace("Z", "")
                    ).timestamp()
                ),
                message=data["commit"]["message"].split("\n")[0],
                html_url=data["html_url"],
                author_login=(data["author"] or {}).get("login", "unknown"),
                author_avatar_url=(data["author"] or {}).get("avatar_url", ""),
            )
            for data in json_data
        ]

    @staticmethod
    async def fetch_commits(cache_path: Path, cached_github: bool) -> List[GHCommit]:
        commits: List[GHCommit] = await get_or_fetch(
            cache_path / "github_commits.json",
            use_cached=cached_github,
            result_cls=GHCommit,
            many=True,
            async_func=GithubDataSource._get_latest_commit,
        )
        return commits

    @staticmethod
    async def fetch_all(cache_path: Path, cached_gha: bool, commits: List[GHCommit]):
        concurrency_limiter = asyncio.Semaphore(5)
        gha_status_raw: List[Optional[GHAJobStat]] = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path / f"gha_cached/{commit.sha}/job.json",
                    use_cached=cached_gha,
                    result_cls=GHAJobStat,
                    many=False,
                    async_func=functools.partial(
                        GithubDataSource.get_gha_status,
                        sha=commit.sha,
                        concurrency_limiter=concurrency_limiter,
                    ),
                )
                for commit in commits
            ]
        )
        gha_status: List[GHAJobStat] = [s for s in gha_status_raw if s is not None]
        return gha_status

    @staticmethod
    async def get_gha_status(
        sha: str, concurrency_limiter: asyncio.Semaphore
    ) -> Optional[GHAJobStat]:
        GITHUB_TO_BAZEL_STATUS_MAP = {
            "action_required": None,
            "cancelled": "FAILED",
            "failure": "FAILED",
            "neutral": None,
            "success": "PASSED",
            "skipped": "FAILED",
            "stale": "FAILED",
            "timed_out": "FAILED",
        }

        async with concurrency_limiter:
            async with httpx.AsyncClient() as client:
                data = (
                    await client.get(
                        f"https://api.github.com/repos/ray-project/ray/commits/{sha}/check-suites",
                        headers=GH_HEADERS,
                    )
                ).json()

                if "check_suites" not in data:
                    return None

                for check in data["check_suites"]:
                    slug = check["app"]["slug"]
                    if slug == "github-actions" and check["status"] == "completed":
                        data = (
                            await client.get(check["check_runs_url"], headers=GH_HEADERS)
                        ).json()
                        if len(data.get("check_runs", [])) == 0:
                            return None
                        run = data["check_runs"][0]
                        return GHAJobStat(
                            job_id=run["id"],
                            os="windows",
                            commit=sha,
                            env="github action main job",
                            state=GITHUB_TO_BAZEL_STATUS_MAP[check["conclusion"]],
                            url=run["html_url"],
                            duration_s=_parse_duration(
                                run.get("started_at"), run.get("completed_at")
                            ),
                        )
        return None

import asyncio
import functools
import os
from itertools import chain
from pathlib import Path
from typing import Callable, List, Optional

import aiofiles
import httpx
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import _process_single_build, get_or_fetch, retry
from ray_ci_tracker.interfaces import (
    BuildkiteArtifact,
    BuildkitePRBuildTime,
    BuildkiteStatus,
    BuildResult,
)

GRAPHQL_QUERY = """
query AllPipelinesQuery {
  pipeline(slug: "ray-project/oss-ci-build-branch") {
    builds(branch: "master", commit: "COMMIT_PLACEHODLER") {
      count
      edges {
        node {
          createdAt
          startedAt
          finishedAt
          number
          jobs(first: 500) {
            edges {
              node {
                ... on JobTypeCommand {
                  uuid
                  label
                  passed
                  state
                  url
                  build {
                    commit
                  }
                  createdAt
                  runnableAt
                  startedAt
                  finishedAt
                  events(last: 50) {
                    edges {
                      node {
                        ... on JobEventRetried {
                          retriedInJob {
                            uuid
                          }
                        }
                      }
                    }
                  }
                  artifacts(first: 100) {
                    edges {
                      node {
                        downloadURL
                        path
                      }
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
"""

PR_TIME_QUERY = """
query PRTimeQuery {
  pipeline(slug: "ray-project/ray-builders-pr") {
    builds(first: 500) {
      edges {
        node {
          commit
          createdAt
          createdBy {
            ... on User {
              userName: name
            }
            ... on UnregisteredUser {
              unregisteredUserName: name
            }
          }
          canceledAt
          canceledBy {
            ... on User {
              userName: name
            }
          }
          finishedAt
          message
          pullRequest {
            id
          }
          startedAt
          state
          url
        }
      }
    }
  }
}
"""


class BuildkiteSource:
    @staticmethod
    async def fetch_all(cache_path: Path, cached_buildkite, commits):
        async def try_get_or_fetch(func: Callable):
            try:
                return await func()
            except Exception as e:
                print(f"Failed to run {getattr(func, '__name__', 'Unknown')}:")
                print(str(e))
                return []

        concurrency_limiter = asyncio.Semaphore(20)

        async def get_buildkite_status():
            print("Downloading Buildkite Status (Jobs)")
            buildkite_jsons = await tqdm_asyncio.gather(
                *[
                    get_or_fetch(
                        cache_path / f"bk_jobs/{commit.sha}/http_resp.json",
                        use_cached=cached_buildkite,
                        result_cls=None,
                        many=False,
                        async_func=functools.partial(
                            BuildkiteSource.get_buildkite_job_status,
                            commit_sha=commit.sha,
                            concurrency_limiter=concurrency_limiter,
                        ),
                    )
                    for commit in commits
                ]
            )

            buildkite_parsed: List[BuildkiteStatus] = await asyncio.gather(
                *[
                    get_or_fetch(
                        cache_path / f"bk_jobs/{commit.sha}/parsed.json",
                        use_cached=cached_buildkite,
                        result_cls=BuildkiteStatus,
                        many=True,
                        async_func=functools.partial(
                            BuildkiteSource.parse_buildkite_build_json,
                            resp_json,
                        ),
                    )
                    for commit, resp_json in zip(commits, buildkite_jsons)
                ]
            )
            return buildkite_parsed

        async def get_buildkite_artifacts():
            print("Downloading Buildkite Artifacts")

            def contains_bad_commit(status: BuildkiteStatus):
                return status.commit in {
                    "5985c1902dc24236e15757f42d899b0c0bc5b5d4",
                    "893f57591df7cb7b1fb4fed9978604964123eead",
                }

            macos_bazel_events = await tqdm_asyncio.gather(
                *[
                    get_or_fetch(
                        cache_path
                        / f"bazel_cached/{status.commit}/mac_result_{status.job_id}.json",
                        use_cached=cached_buildkite,
                        result_cls=BuildResult,
                        many=False,
                        async_func=functools.partial(
                            BuildkiteSource.get_buildkite_artifact,
                            dir_prefix=cache_path,
                            artifacts=status.artifacts,
                            concurrency_limiter=asyncio.Semaphore(50),
                        ),
                    )
                    for status in chain.from_iterable(buildkite_parsed)
                    if len(status.artifacts) > 0 and not contains_bad_commit(status)
                ]
            )

            return macos_bazel_events

        async def get_buildkite_pr_time():
            print("Fetching Buildkite PR Time")
            pr_build_times = await get_or_fetch(
                cache_path / f"bk_pr_time/result.json",
                use_cached=cached_buildkite,
                result_cls=BuildkitePRBuildTime,
                many=True,
                async_func=BuildkiteSource.get_buildkite_pr_buildtime,
            )

            return pr_build_times

        buildkite_parsed = await try_get_or_fetch(get_buildkite_status)
        macos_bazel_events = await try_get_or_fetch(get_buildkite_artifacts)
        pr_build_times = await try_get_or_fetch(get_buildkite_pr_time)

        return (
            list(chain.from_iterable(buildkite_parsed)),
            macos_bazel_events,
            pr_build_times,
        )

    @staticmethod
    @retry
    async def get_buildkite_job_status(
        commit_sha, concurrency_limiter: asyncio.Semaphore
    ):
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(60))
        async with concurrency_limiter, http_client:
            resp = await http_client.post(
                "https://graphql.buildkite.com/v1",
                headers={"Authorization": f"Bearer {os.environ['BUILDKITE_TOKEN']}"},
                json={"query": GRAPHQL_QUERY.replace("COMMIT_PLACEHODLER", commit_sha)},
            )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    async def parse_buildkite_build_json(
        resp_json: dict,
    ) -> List[BuildkiteStatus]:
        builds = resp_json["data"]["pipeline"]["builds"]["edges"]

        statuses = []
        for build in builds:
            jobs = build["node"]["jobs"]["edges"]
            for job in jobs:
                actual_job = job["node"]
                if not actual_job:  # sometimes this can be empty
                    continue
                job_id = actual_job["uuid"]
                sha = actual_job["build"]["commit"]

                # We will not persist steps that are retried.
                is_retried = False
                for event in actual_job["events"]["edges"]:
                    if "retriedInJob" in event["node"]:
                        is_retried = True
                        break
                if is_retried:
                    continue

                artifacts = []
                for artifact in actual_job["artifacts"]["edges"]:
                    url = artifact["node"]["downloadURL"]
                    path = artifact["node"]["path"]
                    if "bazel_event_logs" in path:
                        filename = os.path.split(path)[1]
                        on_disk_path = f"bazel_events/master/{sha}/{job_id}/{filename}"
                        artifacts.append(
                            BuildkiteArtifact(
                                url=url,
                                bazel_events_path=on_disk_path,
                                job_id=job_id,
                                sha=sha,
                            )
                        )

                status = BuildkiteStatus(
                    job_id=job_id,
                    label=actual_job["label"],
                    passed=actual_job["passed"],
                    state=actual_job["state"],
                    url=actual_job["url"],
                    commit=sha,
                    startedAt=actual_job["startedAt"],
                    finished_at=actual_job["finishedAt"],
                    artifacts=artifacts,
                )
                statuses.append(status)
        return statuses

    @staticmethod
    @retry
    async def get_buildkite_artifact(
        dir_prefix: Path,
        artifacts: List[BuildkiteArtifact],
        concurrency_limiter: asyncio.Semaphore,
    ) -> Optional[BuildResult]:
        assert len(artifacts)

        bazel_events_dir = None
        async with concurrency_limiter, httpx.AsyncClient() as client:
            for artifact in artifacts:
                path = dir_prefix / artifact.bazel_events_path

                path.parent.mkdir(exist_ok=True, parents=True)
                bazel_events_dir = path.parent
                async with client.stream("GET", artifact.url) as response:
                    if response.status_code == 404:
                        print(dir_prefix, artifact, 404)
                        continue
                    response.raise_for_status()
                    async with aiofiles.open(path, "wb") as f:
                        async for chunk in response.aiter_bytes():
                            await f.write(chunk)

        assert bazel_events_dir is not None
        return _process_single_build(bazel_events_dir)

    @staticmethod
    @retry
    async def get_buildkite_pr_buildtime() -> List[BuildkitePRBuildTime]:
        http_client = httpx.AsyncClient(timeout=httpx.Timeout(60))
        async with http_client:
            resp = await http_client.post(
                "https://graphql.buildkite.com/v1",
                headers={"Authorization": f"Bearer {os.environ['BUILDKITE_TOKEN']}"},
                json={"query": PR_TIME_QUERY},
            )
        resp.raise_for_status()
        builds = resp.json()["data"]["pipeline"]["builds"]["edges"]
        return [
            BuildkitePRBuildTime(
                commit=build["node"]["commit"],
                created_by=list(
                    build["node"].get("createdBy", {"_": "unknown"}).values()
                )[0],
                state=build["node"]["state"],
                url=build["node"]["url"],
                created_at=build["node"].get("createdAt"),
                started_at=build["node"].get("startedAt"),
                finished_at=build["node"].get("finishedAt"),
                pull_id=build["node"].get("pullRequest", {"id": None}).get("id"),
            )
            for build in builds
            if build["node"] is not None
            and build["node"].get("pullRequest") is not None
        ]

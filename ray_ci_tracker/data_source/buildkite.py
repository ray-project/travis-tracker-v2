import asyncio
import functools
import os
from itertools import chain
import json
from pathlib import Path
from typing import List, Optional

import aiofiles
import httpx
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import _process_single_build, get_or_fetch, retry
from ray_ci_tracker.interfaces import (
    BuildkiteArtifact,
    BuildkiteStatus,
    BuildResult,
)

GRAPHQL_QUERY = """
query AllPipelinesQuery {
  pipeline(slug: "ray-project/postmerge") {
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


class BuildkiteSource:
    @staticmethod
    async def fetch_all(cache_path: Path, cached_buildkite, commits):
        print("Downloading Buildkite Status (Jobs)")
        concurrency_limiter = asyncio.Semaphore(5)
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
        print("Downloading Buildkite Artifacts (CI)")

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
                        concurrency_limiter=asyncio.Semaphore(5),
                    ),
                )
                for status in chain.from_iterable(buildkite_parsed)
                if len(status.artifacts) > 0 and not contains_bad_commit(status)
            ]
        )
        return (
            list(chain.from_iterable(buildkite_parsed)),
            macos_bazel_events,
        )

    @staticmethod
    @retry
    async def get_buildkite_job_status(
        commit_sha, concurrency_limiter: asyncio.Semaphore
    ):
        async with concurrency_limiter:
            http_client = httpx.AsyncClient(timeout=httpx.Timeout(60))
            async with http_client:
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
        if "data" not in resp_json:
            raise Exception("invalid data: " + json.dumps(resp_json, indent=2))

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
        async with concurrency_limiter:
            async with httpx.AsyncClient() as client:
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

import asyncio
import functools
import json
import os
from itertools import chain
from pathlib import Path
import re
from typing import Dict, List, Optional

import aiofiles
import httpx
from tqdm.asyncio import tqdm_asyncio

from ray_ci_tracker.common import _process_single_build, get_or_fetch, retry
from ray_ci_tracker.interfaces import (
    BuildkiteArtifact,
    BuildkiteStatus,
    BuildResult,
    TestResult,
)

GRAPHQL_QUERY = """
query ReleaseTestQuery {
  pipeline(slug: "ray-project/release-tests-branch") {
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
                    uuid
                    number
                    commit
                  }
                  createdAt
                  runnableAt
                  startedAt
                  finishedAt
                  artifacts(first: 200) {
                    edges {
                      node {
                        uuid
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


def _map_status(status: str) -> str:
    if status in {"finished", "success"}:
        return "PASSED"
    return "FAILED"


class BuildkiteReleaseSource:
    @staticmethod
    async def fetch_all(cache_path: Path, cached_buildkite, commits):
        print("Downloading Buildkite Status (Jobs)")
        concurrency_limiter = asyncio.Semaphore(5)
        buildkite_jsons = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path / f"bk_release_jobs/{commit.sha}/http_resp.json",
                    use_cached=cached_buildkite,
                    result_cls=None,
                    many=False,
                    async_func=functools.partial(
                        BuildkiteReleaseSource.get_buildkite_job_status,
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
                    cache_path / f"bk_release_jobs/{commit.sha}/parsed.json",
                    use_cached=cached_buildkite,
                    result_cls=BuildkiteStatus,
                    many=True,
                    async_func=functools.partial(
                        BuildkiteReleaseSource.parse_buildkite_build_json,
                        resp_json,
                    ),
                )
                for commit, resp_json in zip(commits, buildkite_jsons)
            ]
        )
        print("Downloading Buildkite Artifacts (Release)")

        artifact_data = await tqdm_asyncio.gather(
            *[
                get_or_fetch(
                    cache_path
                    / f"bk_release_jobs/{status.commit}/release_result_{status.job_id}.json",
                    use_cached=cached_buildkite,
                    result_cls=BuildResult,
                    many=False,
                    async_func=functools.partial(
                        BuildkiteReleaseSource.get_buildkite_artifact,
                        dir_prefix=cache_path,
                        artifacts=status.artifacts,
                        concurrency_limiter=asyncio.Semaphore(5),
                    ),
                )
                for status in chain.from_iterable(buildkite_parsed)
                if len(status.artifacts) > 0
            ]
        )

        return artifact_data

    @staticmethod
    @retry
    async def get_buildkite_job_status(
        commit_sha, concurrency_limiter: asyncio.Semaphore
    ) -> Dict:
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
        builds = resp_json["data"]["pipeline"]["builds"]["edges"]

        statuses = []
        for build in builds:
            jobs = build["node"]["jobs"]["edges"]
            for job in jobs:
                actual_job = job["node"]
                if actual_job == {}:
                    continue
                job_id = actual_job["uuid"]
                sha = actual_job["build"]["commit"]
                build_id = str(actual_job["build"]["number"])

                artifacts = []
                for artifact in actual_job["artifacts"]["edges"]:
                    url = artifact["node"]["downloadURL"]
                    path = artifact["node"]["path"]
                    if ".json" in path:
                        filename = os.path.split(path)[1]
                        on_disk_path = (
                            f"release_test_json/master/{sha}/{job_id}/{filename}"
                        )
                        artifacts.append(
                            BuildkiteArtifact(
                                url=url,
                                bazel_events_path=on_disk_path,
                                id=artifact["node"]["uuid"],
                                job_id=job_id,
                                build_id=build_id,
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
            async with httpx.AsyncClient(timeout=60) as client:
                for artifact in artifacts:
                    path = dir_prefix / artifact.bazel_events_path

                    path.parent.mkdir(exist_ok=True, parents=True)
                    bazel_events_dir = path.parent

                    artifact_url = (
                        "https://api.buildkite.com/v2/organizations/ray-project" +
                        "/pipelines/release-tests-branch" +
                        "/builds/" + artifact.build_id +
                        "/jobs/" + artifact.job_id +
                        "/artifacts/" + artifact.id + "/download"
                    )

                    async with client.stream(
                        "GET", artifact_url, follow_redirects=True,
                        headers={"Authorization": f"Bearer {os.environ['BUILDKITE_TOKEN']}"},
                    ) as response:
                        if response.status_code == 404:
                            print(dir_prefix, artifact, 404)
                            continue
                        response.raise_for_status()
                        async with aiofiles.open(path, "wb") as f:
                            async for chunk in response.aiter_bytes():
                                await f.write(chunk)

        assert bazel_events_dir is not None
        if not os.path.exists(os.path.join(bazel_events_dir, "result.json")):
            return None

        with open(os.path.join(bazel_events_dir, "result.json")) as f:
            result_json = json.load(f)
        with open(os.path.join(bazel_events_dir, "test_config.json")) as f:
            config_json = json.load(f)

        return BuildResult(
            sha=artifacts[0].sha,
            job_url=result_json["buildkite_url"],
            os="",
            build_env="",
            job_id=artifacts[0].job_id,
            results=[
                TestResult(
                    test_name="release://" + config_json["name"],
                    status=_map_status(result_json["status"]),
                    total_duration_s=result_json["runtime"],
                    is_labeled_flaky=False,
                    owner=config_json["team"],
                    is_labeled_staging=result_json["stable"],
                )
            ],
        )

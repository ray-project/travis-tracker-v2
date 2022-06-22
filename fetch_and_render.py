import argparse
from concurrent.futures import ThreadPoolExecutor, wait
import sys
import traceback
from collections import defaultdict
import json
import glob
import os
from itertools import chain
from pathlib import Path
from sqlite3 import connect
from typing import List, Tuple
from subprocess import Popen, PIPE
from datetime import datetime
from dataclasses_json.api import dataclass_json

import requests
from dotenv import load_dotenv
from tqdm import tqdm
import numpy as np
import pandas as pd

from interfaces import *

load_dotenv()

GH_HEADERS = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}


def _parse_duration(started_at, finished_at) -> int:
    started = pd.to_datetime(started_at)
    finished = pd.to_datetime(finished_at)
    if started is None or finished is None:
        duration_s = 0
    else:
        duration_s = (finished - started).total_seconds()
    return duration_s


def get_latest_commit() -> List[GHCommit]:
    resp = requests.get(
        "https://api.github.com/repos/ray-project/ray/commits?per_page=100",
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


@dataclass_json
@dataclass
class TravisJobStat:
    job_id: str
    os: str
    commit: str
    env: str
    state: str
    url: str
    duration_s: str


GITHUB_TO_TRAVIS_STATUS_MAP = {
    "action_required": "created",
    "cancelled": "failed",
    "failure": "failed",
    "neutral": "created",
    "success": "passed",
    "skipped": "failed",
    "stale": "failed",
    "timed_out": "failed",
}


def get_travis_status(commit_sha, cache_dir="travis_events") -> List[TravisJobStat]:
    def get_gha_status(sha):
        data = requests.get(
            f"https://api.github.com/repos/ray-project/ray/commits/{sha}/check-suites",
            headers=GH_HEADERS,
        ).json()

        if "check_suites" not in data:
            return None

        for check in data["check_suites"]:
            slug = check["app"]["slug"]
            if slug == "github-actions" and check["status"] == "completed":
                data = requests.get(check["check_runs_url"], headers=GH_HEADERS).json()
                if len(data["check_runs"]) == 0:
                    return None
                run = data["check_runs"][0]
                return TravisJobStat(
                    job_id=run["id"],
                    os="windows",
                    commit=sha,
                    env="github action main job",
                    state=GITHUB_TO_TRAVIS_STATUS_MAP[check["conclusion"]],
                    url=run["html_url"],
                    duration_s=_parse_duration(
                        check.get("started_at"), check.get("completed_at")
                    ),
                )

    def find_travis_build_id(sha):
        data = requests.get(
            f"https://api.github.com/repos/ray-project/ray/commits/{sha}/check-suites",
            headers=GH_HEADERS,
        ).json()

        if "check_suites" not in data:
            return

        for check in data["check_suites"]:
            slug = check["app"]["slug"]
            if slug == "travis-ci":
                data = requests.get(check["check_runs_url"], headers=GH_HEADERS).json()
                if (
                    len(data["check_runs"]) == 0
                ):  # Travis added the check but not runs yet.
                    return None
                return data["check_runs"][0]["external_id"]

    def list_travis_job_status(build_id):
        resp = requests.get(
            f"https://api.travis-ci.com/build/{build_id}?include=job.config,job.state,job.started_at,job.finished_at",
            headers={"Travis-API-Version": "3"},
        ).json()
        data = []
        for job in resp["jobs"]:
            duration_s = _parse_duration(job["started_at"], job["finished_at"])

            data.append(
                TravisJobStat(
                    job_id=job["id"],
                    os=job["config"]["os"],
                    commit=resp["commit"]["sha"],
                    env=job["config"]["env"],
                    state=job["state"],
                    url=f"https://travis-ci.com/github/ray-project/ray/jobs/{job['id']}",
                    duration_s=duration_s,
                )
            )
        return data

    dir_name = Path(cache_dir) / commit_sha
    os.makedirs(dir_name, exist_ok=True)

    status_file = dir_name / "status_complete"
    data_file = dir_name / "status.json"
    if not status_file.exists():
        statuses = []
        gha_status = get_gha_status(commit_sha)
        if gha_status:
            statuses.append(gha_status)

        build_id = find_travis_build_id(commit_sha)
        if build_id is not None:
            job_status = list_travis_job_status(build_id)
            statuses.extend(job_status)

        if len(statuses) == 0:
            return []

        with open(data_file, "w") as f:
            f.write(TravisJobStat.schema().dumps(statuses, many=True))

        job_states = {job.state for job in statuses}
        if len(job_states.intersection({"created", "started"})) == 0:
            status_file.touch()

    if data_file.exists():
        with open(data_file) as f:
            return TravisJobStat.schema().loads(f.read(), many=True)
    return []


@dataclass
class BuildkiteStatus:
    job_id: str
    label: str
    passed: bool  # if it's running, passed=false
    state: str
    url: str
    commit: str
    startedAt: Optional[str]
    finished_at: Optional[str]

    def get_duration_s(self) -> int:
        return _parse_duration(self.startedAt, self.finished_at)


def get_buildkite_status() -> Tuple[List, List[BuildkiteStatus]]:
    builds = []
    result = []
    page_token = None
    for offset in [0, 20, 40, 60, 80, 100]:
        if offset == 0:
            builds_chunk, result_chunks, page_token = get_buildkite_status_paginated(
                f"first: 20"
            )
        else:
            builds_chunk, result_chunks, page_token = get_buildkite_status_paginated(
                f'first: 20, after: "{page_token}"'
            )
        builds.extend(builds_chunk)
        result.extend(result_chunks)
    return builds, result


def get_buildkite_status_paginated(page_command):
    BUILDKITE_TOKEN = os.environ["BUILDKITE_TOKEN"]
    tries = 5
    for attempt in range(tries):
        resp = requests.post(
            "https://graphql.buildkite.com/v1",
            headers={"Authorization": f"Bearer {BUILDKITE_TOKEN}"},
            json={
                "query": """
    query AllPipelinesQuery {
      pipeline(slug: "ray-project/ray-builders-branch") {
        builds(branch: "master", PAGE_COMMAND_PLACEHOLDER) {
          pageInfo {
            endCursor
          }
          edges {
            node {
              createdAt
              startedAt
              finishedAt
              number
              jobs(first: 100) {
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
    """.replace(
                    "PAGE_COMMAND_PLACEHOLDER", page_command
                )
            },
        )
        try:
            assert resp.status_code == 200, resp.text
        except AssertionError as e:
            if attempt < tries - 1:
                continue
            else:
                raise
        break
    page_cursor = resp.json()["data"]["pipeline"]["builds"]["pageInfo"]["endCursor"]
    builds = resp.json()["data"]["pipeline"]["builds"]["edges"]
    results = []

    thread_pool = ThreadPoolExecutor(100)
    futures = []

    for build in tqdm(builds):
        jobs = build["node"]["jobs"]["edges"]
        for job in jobs:
            actual_job = job["node"]
            job_id = actual_job["uuid"]
            sha = actual_job["build"]["commit"]
            status = BuildkiteStatus(
                job_id=job_id,
                label=actual_job["label"],
                passed=actual_job["passed"],
                state=actual_job["state"],
                url=actual_job["url"],
                commit=sha,
                startedAt=actual_job["startedAt"],
                finished_at=actual_job["finishedAt"],
            )
            results.append(status)

            artifacts = actual_job["artifacts"]["edges"]
            for artifact in artifacts:
                url = artifact["node"]["downloadURL"]
                path = artifact["node"]["path"]
                filename = os.path.split(path)[1]
                on_disk_path = f"bazel_events/master/{sha}/{job_id}/{filename}"
                if not os.path.exists(on_disk_path):
                    # Use the artifact link to download the logs. This might not work well
                    # on slower internet because the link is presigned S3 url and only last 10min.
                    def task(url, on_disk_path, actual_job):
                        resp = requests.get(url, timeout=5)
                        assert (
                            resp.status_code == 200
                        ), f"failed to download {url} for {actual_job}: {resp.text}"
                        if len(resp.content):
                            # Make the directory, just to be safe.
                            os.makedirs(os.path.split(on_disk_path)[0], exist_ok=True)
                            with open(on_disk_path, "wb") as f:
                                f.write(resp.content)

                    futures.append(
                        thread_pool.submit(task, url, on_disk_path, actual_job)
                    )
    wait(futures)
    exception_set = [fut for fut in futures if fut.exception()]

    if len(exception_set) > 100:
        print("More than 100 exception as occured when downloading Buldkite status.")
        raise exception_set[0]
    return builds, results, page_cursor


def download_files_given_prefix(prefix: str):
    proc = Popen(
        f"aws s3 sync s3://ray-travis-logs/{prefix} {prefix}",
        shell=True,
        stdout=PIPE,
        stderr=PIPE,
    )
    status = proc.wait()
    assert status == 0, proc.communicate()


def yield_test_result(bazel_log_path):
    # Gather the known flaky set
    flaky_tests = set()
    with open(bazel_log_path) as f:
        for line in f:
            loaded = json.loads(line)
            if "targetConfigured" in loaded["id"] and "tag" in loaded["configured"]:
                test_name = loaded["id"]["targetConfigured"]["label"]
                if "flaky" in loaded["configured"]["tag"]:
                    flaky_tests.add(test_name)

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
                yield TestResult(name, status, duration_s, name in flaky_tests)


TRAVIS_TO_BAZEL_STATUS_MAP = {
    "created": None,
    "queued": None,
    "errored": "FAILED",
    "failed": "FAILED",
    "passed": "PASSED",
    "started": None,
    "received": None,
}


def process_single_build(dir_name) -> BuildResult:
    with open(dir_name / "metadata.json") as f:
        metadata = json.load(f)

    return BuildResult(
        sha=metadata["build_env"]["TRAVIS_COMMIT"],
        job_url=metadata["build_env"]["TRAVIS_JOB_WEB_URL"],
        os=metadata["build_env"]["TRAVIS_OS_NAME"],
        build_env=metadata["build_config"]["config"]["env"],
        results=list(
            chain.from_iterable(
                yield_test_result(log) for log in dir_name.glob("bazel_log.*")
            )
        ),
    )


class ResultsDB:
    def __init__(self, location=":memory:", wipe=True) -> None:
        self.table = connect(location)
        if not wipe:
            return
        self.table.executescript(
            """
        DROP TABLE IF EXISTS test_result;
        CREATE TABLE test_result (
            test_name TEXT,
            status TEXT,
            build_env TEXT,
            os TEXT,
            job_url TEXT,
            job_id TEXT,
            sha TEXT,
            test_duration_s REAL,
            is_labeled_flaky BOOLEAN
        );

        DROP TABLE IF EXISTS commits;
        CREATE TABLE commits (
            sha TEXT,
            unix_time INT,
            idx INT,
            message TEXT,
            url TEXT,
            avatar_url TEXT
        )
        """
        )

    def write_commits(self, commits: List[GHCommit]):
        self.table.executemany(
            "INSERT INTO commits VALUES (?,?,?,?,?,?)",
            [
                (
                    commit.sha,
                    commit.unix_time_s,
                    i,
                    commit.message,
                    commit.html_url,
                    commit.author_avatar_url,
                )
                for i, commit in enumerate(commits)
            ],
        )
        self.table.commit()

    def write_build_results(self, dir_prefixes: List[str]):
        records_to_insert = []
        for prefix in tqdm(dir_prefixes):
            if not os.path.exists(prefix):
                # The direcotry dones't exists. It's fine
                continue
            for build in os.listdir(prefix):
                dir_name = Path(prefix) / build
                build_result = process_single_build(dir_name)
                travis_job_id = build
                for test in build_result.results:
                    records_to_insert.append(
                        (
                            f"{build_result.os}:{test.test_name}",
                            test.status,
                            build_result.build_env,
                            build_result.os,
                            build_result.job_url,
                            travis_job_id,
                            build_result.sha,
                            test.total_duration_s,
                            test.is_labeled_flaky,
                        )
                    )

        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def write_buildkite_data(self, buildkite_data: List[BuildkiteStatus]):
        records_to_insert = []
        for job in buildkite_data:
            num_result = len(
                self.table.execute(
                    f"SELECT * FROM test_result WHERE job_id == (?)",
                    (job.job_id,),
                ).fetchall()
            )
            status = "PASSED" if job.passed else "FAILED"
            if job.state == "FINISHED":
                records_to_insert.append(
                    (
                        f"bk://{job.label}",
                        # Mark the entire build passed when individual tests result uploaded
                        status if num_result == 0 else "PASSED",
                        job.label,
                        "linux",
                        job.url,
                        job.job_id,
                        job.commit,
                        job.get_duration_s(),
                        False,  # is_labeled_flaky
                    )
                )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def write_travis_data(self, travis_data: List[List[TravisJobStat]]):
        records_to_insert = []
        for data in tqdm(travis_data):
            for travis_commit in data:
                travis_job_id = travis_commit.job_id
                num_result = len(
                    self.table.execute(
                        f"SELECT * FROM test_result WHERE job_id == (?)",
                        (travis_job_id,),
                    ).fetchall()
                )
                status = TRAVIS_TO_BAZEL_STATUS_MAP.get(travis_commit.state)
                if status is not None:
                    records_to_insert.append(
                        (
                            f"{travis_commit.os}://travis/{travis_commit.env}".replace(
                                "PYTHONWARNINGS=ignore", ""
                            ),
                            # Mark the entire build passed when individual tests result uploaded
                            status if num_result == 0 else "PASSED",
                            travis_commit.env,
                            travis_commit.os,
                            travis_commit.url,
                            travis_commit.job_id,
                            travis_commit.commit,
                            travis_commit.duration_s,
                            False,  # is_labeled_flaky
                        )
                    )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def list_tests_ordered(self):
        query = f"""
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == (?)
            GROUP BY test_name
        """
        failed_tests = self.table.execute(query, ("FAILED",)).fetchall()
        flaky_tests = self.table.execute(query, ("FLAKY",)).fetchall()
        top_failed_tests = self.table.execute(
            """
            SELECT test_name, SUM(10 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            AND commits.idx < 10
            GROUP BY test_name
        """
        ).fetchall()
        green_flaky_tests = self.table.execute(
            """
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
              AND status == 'PASSED'
              AND is_labeled_flaky = 1
            GROUP BY test_name
        """
        ).fetchall()

        prioritization = defaultdict(int)
        for test_name, score in top_failed_tests:
            prioritization[test_name] += score * 1_000_000  # Prioritize recent failure.

        for test_name, score in failed_tests:
            prioritization[test_name] += score

        # for test_name, score in green_flaky_tests:
        #     prioritization[test_name] += 0.5 * score

        for test_name, score in flaky_tests:
            prioritization[test_name] += 0.1 * score

        results = sorted(list(prioritization.items()), key=lambda kv: -kv[1])
        return results

    def get_travis_link(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Travis Link
            SELECT commits.sha, commits.unix_time, commits.message, build_env, job_url, os, status
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status in ('FAILED', 'FLAKY')
            AND test_name == (?)
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteTravisLink(
                sha_short=sha[:6],
                commit_time=unix_time,
                commit_message=msg,
                build_env=env,
                job_url=url,
                os=os,
                status=status
            )
            for sha, unix_time, msg, env, url, os, status in cursor.fetchall()
        ]

    def get_recent_build_time_stats(self, test_name: str) -> Optional[List[float]]:
        cursor = self.table.execute(
            """
            -- Build Time Stats
            SELECT test_duration_s
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND commits.idx <= 20
            AND test_name == (?)
            """,
            (test_name,),
        )
        arr = np.array(list(cursor)).flatten()
        if len(arr) == 0:
            return None
        runtime_stat = np.percentile(arr, [0, 50, 90]).tolist()
        return runtime_stat

    def get_marked_flaky_status(self, test_name: str) -> bool:
        cursor = self.table.execute(
            "SELECT SUM(is_labeled_flaky) FROM test_result WHERE test_name == (?)",
            (test_name,),
        )
        return bool(list(cursor)[0][0])

    def get_commit_tooltips(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Commit Tooltip
            WITH filtered(sha, num_failed, num_flaky) AS (
                SELECT sha, SUM(status == 'FAILED'), SUM(status == 'FLAKY') as num_failed
                FROM test_result
                WHERE test_name == (?)
                GROUP BY sha
            )
            SELECT commits.sha, commits.message, commits.url, commits.avatar_url,
                filtered.num_failed, filtered.num_flaky
            FROM commits LEFT JOIN filtered
            ON commits.sha == filtered.sha
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteCommitTooltip(
                num_failed=num_failed,
                num_flaky=num_flaky,
                message=msg,
                author_avatar=avatar,
                commit_url=url,
            )
            for _, msg, url, avatar, num_failed, num_flaky in cursor.fetchall()
        ]

    def get_stats(self):
        master_green_query = """
            -- Master Green Rate (past 100 commits)
            SELECT SUM(green)*1.0/COUNT(green)
            FROM (
                SELECT SUM(status == 'FAILED') == 0 as green
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                GROUP BY test_result.sha
                ORDER BY commits.idx
            )
        """

        master_green_without_flaky_query = """
            -- Master Green Rate (past 100 commits) (without flaky tests)
            SELECT SUM(green)*1.0/COUNT(green)
            FROM (
                SELECT SUM(status == 'FAILED') == 0 as green
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                  AND test_result.is_labeled_flaky == 0
                GROUP BY commits.sha
                ORDER BY commits.idx
            )
        """

        pass_rate_query = """
            -- Number of tests with <95% pass rate
            SELECT COUNT(*)
            FROM (
                SELECT test_name, 1 - (SUM(status == 'FAILED') *1.0 / COUNT(*)) AS success_rate
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                GROUP BY test_name
                ORDER BY success_rate
            )
            WHERE success_rate < 0.95
        """

        return [
            SiteStatItem(
                key="Master Green (past 100 commits)",
                value=self.table.execute(master_green_query).fetchone()[0] * 100,
                desired_value=100,
                unit="%",
            ),
            SiteStatItem(
                key="Master Green (without flaky tests)",
                value=self.table.execute(master_green_without_flaky_query).fetchone()[0]
                * 100,
                desired_value=100,
                unit="%",
            ),
            SiteStatItem(
                key="Number of Tests <95% Pass",
                value=self.table.execute(pass_rate_query).fetchone()[0],
                desired_value=0,
                unit="",
            ),
        ]


def get_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--bazel-cached", action="store_true")
    return p.parse_args()


def main():
    print("🐙 Fetching Commits from Github")
    commits = get_latest_commit()

    args = get_args()
    if args.bazel_cached:
        print("💻 Using local file cache for bazel events!")
        prefixes = glob.glob("bazel_events/master/*")
    else:
        print("💻 Downloading Files from S3")
        prefixes = [f"bazel_events/master/{commit.sha}" for commit in commits]

        for prefix in tqdm(prefixes):
            download_files_given_prefix(prefix)
            pass

    print("Downloading Travis Status")
    travis_data = [get_travis_status(commit.sha) for commit in tqdm(commits)]
    print("Downloading Buildkite Status")
    raw_builds_result, buildkite_status = get_buildkite_status()
    with open("cached_buildkite.json", "w") as f:
        json.dump(raw_builds_result, f)

    print("✍️ Writing Data")
    db = ResultsDB("./results.db")
    db.write_commits(commits)
    db.write_build_results(prefixes)
    db.write_travis_data(travis_data)
    # TODO(simon): Cache this?
    db.write_buildkite_data(buildkite_status)

    print("🔮 Analyzing Data")
    display = dict()
    failed_tests = db.list_tests_ordered()
    data_to_display = [
        SiteFailedTest(
            name=test_name,
            status_segment_bar=db.get_commit_tooltips(test_name),
            travis_links=db.get_travis_link(test_name),
            build_time_stats=db.get_recent_build_time_stats(test_name),
            is_labeled_flaky=db.get_marked_flaky_status(test_name),
        )
        for test_name, _ in failed_tests
    ]
    root_display = SiteDisplayRoot(
        failed_tests=data_to_display,
        stats=db.get_stats(),
    )

    print("⌛️ Writing Out to Frontend")
    with open("js/src/data.json", "w") as f:
        json.dump(root_display.to_dict(), f)


if __name__ == "__main__":
    if os.environ.get("CI"):
        total_retries = 3
        for i in range(1, total_retries + 1):
            print(f"In CI environment, try {i} of {total_retries}")
            try:
                main()
                break
            except Exception as e:
                traceback.print_exc()
        else:
            print("All failed")
            sys.exit(1)
    else:
        main()

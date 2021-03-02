from collections import defaultdict
import json
import os
from itertools import chain
from pathlib import Path
from sqlite3 import connect
from typing import List
from subprocess import Popen, PIPE
from datetime import datetime
from dataclasses_json.api import dataclass_json

import requests
from dotenv import load_dotenv
from tqdm import tqdm

from interfaces import *

load_dotenv()

GH_HEADERS = {"Authorization": f"token {os.environ['GITHUB_TOKEN']}"}


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
            author_login=data["author"]["login"],
            author_avatar_url=data["author"]["avatar_url"],
        )
        for data in json_data
    ]


@dataclass_json
@dataclass
class TravisJobStat:
    job_id: int
    os: str
    commit: str
    env: str
    state: str
    url: str


def get_travis_status(commit_sha, cache_dir="travis_events") -> List[TravisJobStat]:
    def find_travis_build_id(sha):
        data = requests.get(
            f"https://api.github.com/repos/ray-project/ray/commits/{sha}/check-suites",
            headers=GH_HEADERS,
        ).json()
        for check in data["check_suites"]:
            slug = check["app"]["slug"]
            if slug == "travis-ci":
                data = requests.get(check["check_runs_url"], headers=GH_HEADERS).json()
                return data["check_runs"][0]["external_id"]

    def list_travis_job_status(build_id):
        resp = requests.get(
            f"https://api.travis-ci.com/build/{build_id}?include=job.config,job.state",
            headers={"Travis-API-Version": "3"},
        ).json()
        data = []
        for job in resp["jobs"]:
            data.append(
                TravisJobStat(
                    job_id=job["id"],
                    os=job["config"]["os"],
                    commit=resp["commit"]["sha"],
                    env=job["config"]["env"],
                    state=job["state"],
                    url=f"https://travis-ci.com/github/ray-project/ray/jobs/{job['id']}",
                )
            )
        return data

    dir_name = Path(cache_dir) / commit_sha
    os.makedirs(dir_name, exist_ok=True)

    status_file = dir_name / "status_complete"
    data_file = dir_name / "status.json"
    if not status_file.exists():
        build_id = find_travis_build_id(commit_sha)
        if build_id is None:
            return []
        job_status = list_travis_job_status(build_id)

        with open(data_file, "w") as f:
            f.write(TravisJobStat.schema().dumps(job_status, many=True))

        job_states = {job.state for job in job_status}
        if len(job_states.intersection({"created", "started"})) == 0:
            status_file.touch()

    if data_file.exists():
        with open(data_file) as f:
            return TravisJobStat.schema().loads(f.read(), many=True)
    return []


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
    with open(bazel_log_path) as f:
        for line in f:
            try:
                loaded = json.loads(line)
                if "testSummary" in loaded:
                    test_summary = loaded["testSummary"]

                    name = loaded["id"]["testSummary"]["label"]
                    status = test_summary["overallStatus"]
                    if status in {"FAILED", "TIMEOUT", "NO_STATUS"}:
                        status = "FAILED"
                    yield TestResult(name, status)
            except:
                pass


TRAVIS_TO_BAZEL_STATUS_MAP = {
    "created": None,
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
            job_id INT,
            sha TEXT
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
                travis_job_id = int(build)
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
                        )
                    )

        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?)",
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
                        f"SELECT * FROM test_result WHERE job_id == {travis_job_id}"
                    ).fetchall()
                )
                status = TRAVIS_TO_BAZEL_STATUS_MAP[travis_commit.state]
                if num_result == 0 and status is not None:
                    records_to_insert.append(
                        (
                            f"{travis_commit.os}://travis/{travis_commit.env}".replace(
                                "PYTHONWARNINGS=ignore", ""
                            ),
                            status,
                            travis_commit.env,
                            travis_commit.os,
                            travis_commit.url,
                            travis_commit.job_id,
                            travis_commit.commit,
                        )
                    )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?)",
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
        top_failed_tests = self.table.execute("""
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            AND commits.idx < 5
            GROUP BY test_name
        """).fetchall()

        prioritization = defaultdict(int)
        for test_name, score in top_failed_tests:
            prioritization[test_name] += score * 2

        for test_name, score in failed_tests:
            prioritization[test_name] += score

        for test_name, score in flaky_tests:
            prioritization[test_name] += 0.1 * score
        results = sorted(list(prioritization.items()), key=lambda kv: -kv[1])
        return results

    def get_travis_link(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Travis Link
            SELECT commits.sha, commits.unix_time, commits.message, build_env, job_url, os
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            AND test_name == (?)
            ORDER BY commits.idx
            """,
            (
                test_name,
            ),
        )
        return [
            SiteTravisLink(
                sha_short=sha[:6],
                commit_time=unix_time,
                commit_message=msg,
                build_env=env,
                job_url=url,
                os=os,
            )
            for sha, unix_time, msg, env, url, os in cursor.fetchall()
        ]

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
            (
                test_name,
            ),
        )
        return [
            SiteCommitTooltip(
                num_failed=num_failed,
                num_flaky=num_flaky, message=msg, author_avatar=avatar, commit_url=url
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
                key="Number of Tests <95% Pass",
                value=self.table.execute(pass_rate_query).fetchone()[0],
                desired_value=0,
                unit="",
            ),
        ]


import argparse

def get_args():
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("--bazel-cached", action="store_true")
    return p.parse_args()

if __name__ == "__main__":

    print("🐙 Fetching Commits from Github")
    commits = get_latest_commit()

    args = get_args()
    if args.bazel_cached:
        import glob
        print("💻 Using file cache from S3!")
        prefixes = glob.glob("bazel_events/master/*")
    else:
        print("💻 Downloading Files from S3")
        prefixes = [f"bazel_events/master/{commit.sha}" for commit in commits]

        for prefix in tqdm(prefixes):
            download_files_given_prefix(prefix)
            pass

    print("Downloading Travis Status")
    travis_data = [get_travis_status(commit.sha) for commit in tqdm(commits)]

    print("✍️ Writing Data")
    db = ResultsDB("./results.db")
    db.write_commits(commits)
    db.write_build_results(prefixes)
    db.write_travis_data(travis_data)

    print("🔮 Analyzing Data")
    display = dict()
    failed_tests = db.list_tests_ordered()
    data_to_display = [
        SiteFailedTest(
            name=test_name,
            status_segment_bar=db.get_commit_tooltips(test_name),
            travis_links=db.get_travis_link(test_name),
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

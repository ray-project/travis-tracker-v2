import json
import os
import time
from dataclasses import dataclass
from itertools import chain
from pathlib import Path
from pprint import pprint
from sqlite3 import connect
from typing import List, Optional, Union

import boto3
import requests
from dotenv import load_dotenv
from jinja2 import Template
from tqdm import tqdm
from typing_extensions import Literal

from interfaces import *


def get_latest_commit() -> List[GHCommit]:
    resp = requests.get(
        "https://api.github.com/repos/ray-project/ray/commits?per_page=100"
    )
    assert resp.status_code == 200, "Pinging github API /commits failed"
    json_data = resp.json()

    return [
        GHCommit(
            sha=data["sha"],
            message=data["commit"]["message"].split("\n")[0],
            html_url=data["html_url"],
            author_login=data["author"]["login"],
            author_avatar_url=data["author"]["avatar_url"],
        )
        for data in json_data
    ]


def download_files_given_prefix(s3_client, prefix: str):
    resp = s3_client.list_objects_v2(Bucket="ray-travis-logs", Prefix=prefix)
    for content in resp.get("Contents", []):
        key = content["Key"]

        if os.path.exists(key):
            continue

        os.makedirs(os.path.dirname(key), exist_ok=True)
        s3_client.download_file(Bucket="ray-travis-logs", Key=key, Filename=key)


def yield_test_result(bazel_log_path):
    with open(bazel_log_path) as f:
        for line in f:
            try:
                loaded = json.loads(line)
                if "testSummary" in loaded:
                    test_summary = loaded["testSummary"]

                    name = loaded["id"]["testSummary"]["label"]
                    status = test_summary["overallStatus"]
                    yield TestResult(name, status)
            except:
                pass


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
    def __init__(self, location=":memory:") -> None:
        self.table = connect(location)
        self.table.executescript(
            """
        DROP TABLE IF EXISTS test_result;
        CREATE TABLE test_result (
            test_name TEXT,
            status TEXT,
            build_env TEXT,
            os TEXT,
            job_url TEXT,
            sha TEXT
        );

        DROP TABLE IF EXISTS commits;
        CREATE TABLE commits (
            sha TEXT,
            idx INT,
            message TEXT,
            url TEXT,
            avatar_url TEXT
        )
        """
        )

    def write_commits(self, commits: List[GHCommit]):
        self.table.executemany(
            "INSERT INTO commits VALUES (?,?,?,?,?)",
            [
                (
                    commit.sha,
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
                for test in build_result.results:
                    records_to_insert.append(
                        (
                            test.test_name,
                            test.status,
                            build_result.build_env,
                            build_result.os,
                            build_result.job_url,
                            build_result.sha,
                        )
                    )

        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def list_failed_tests_ordered(self):
        cursor = self.table.execute(
            """
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            GROUP BY test_name
            ORDER BY weight DESC;
        """,
        )
        return cursor.fetchall()

    def get_travis_link(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Travis Link
            SELECT commits.sha, commits.message, build_env, job_url, os
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            AND test_name == (?)
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteTravisLink(
                sha_short=sha[:6], commit_message=msg, build_env=env, job_url=url, os=os
            )
            for sha, msg, env, url, os in cursor.fetchall()
        ]

    def get_commit_tooltips(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Commit Tooltip
            SELECT commits.sha, commits.message, commits.url,
                   commits.avatar_url, SUM(status == 'FAILED') as num_failed
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND test_name == (?)
            GROUP BY test_result.sha
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteCommitTooltip(
                failed=num_failed > 0, message=msg, author_avatar=avatar, commit_url=url
            )
            for _, msg, url, avatar, num_failed in cursor.fetchall()
        ]


if __name__ == "__main__":
    load_dotenv()
    client = boto3.client("s3")

    print("🐙 Fetching Commits from Github")
    commits = get_latest_commit()

    print("💻 Downloading Files from S3")
    prefixes = [f"bazel_events/master/{commit.sha}" for commit in commits]

    for prefix in tqdm(prefixes):
        download_files_given_prefix(client, prefix)

    print("✍️ Writing Data")
    db = ResultsDB("./results.db")
    db.write_commits(commits)
    db.write_build_results(prefixes)

    print("🔮 Analyzing Data")
    failed_tests = db.list_failed_tests_ordered()
    data_to_display = [
        SiteFailedTest(
            name=test_name,
            status_segment_bar=db.get_commit_tooltips(test_name),
            travis_links=db.get_travis_link(test_name),
        ).to_dict()
        for test_name, _ in failed_tests
    ]

    print("⌛️ Writing Out to Frontend")
    with open("js/src/data.json", "w") as f:
        json.dump(data_to_display, f)
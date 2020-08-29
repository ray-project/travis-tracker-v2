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

TestResultType = Union[
    Literal["PASSED"], Literal["FAILED"], Literal["FLAKY"], Literal["TIMEOUT"]
]


@dataclass
class GHCommit:
    sha: str

    message: str
    html_url: str

    author_login: str
    author_avatar_url: str


@dataclass
class TestResult:
    test_name: str
    status: TestResultType


@dataclass
class BuildResult:
    sha: str
    job_url: str
    build_env: str
    results: List[TestResult]

    sha_index: Optional[int] = None


@dataclass
class SiteTravisLink:
    sha_short: str
    build_env: str
    job_url: str


@dataclass
class SiteCommitTooltip:
    failed: bool
    message: str
    author_avatar: str


@dataclass
class SiteFailedTest:
    name: str
    status_segment_bar: List[SiteCommitTooltip]
    travis_links: List[SiteTravisLink]


def get_latest_commit() -> List[GHCommit]:
    resp = requests.get("https://api.github.com/repos/ray-project/ray/commits")
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
        build_env=metadata["build_config"]["config"]["env"],
        results=list(
            chain.from_iterable(
                yield_test_result(log) for log in dir_name.glob("bazel_log.*")
            )
        ),
    )


class ResultsDB:
    def __init__(self) -> None:
        # self.table = connect(":memory:")
        self.table = connect("results.db")
        self.table.executescript(
            """
        DROP TABLE IF EXISTS test_result;
        CREATE TABLE test_result (
            test_name TEXT,
            status TEXT,
            build_env TEXT,
            job_url TEXT,
            sha TEXT,
            sha_idx INTEGER
        );
        """
        )

    def write_build_result(self, build: BuildResult):
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?)",
            [
                (
                    result.test_name,
                    result.status,
                    build.build_env,
                    build.job_url,
                    build.sha,
                    build.sha_index,
                )
                for result in build.results
            ],
        )
        self.table.commit()

    def get_failed_tests(self, first_k=10):
        cursor = self.table.execute(
            """
        SELECT test_name, status, COUNT(*) as count
        FROM test_result
        WHERE sha_idx < ?
        GROUP BY test_name, status
        HAVING status == 'FAILED'
        ORDER BY count DESC;
        """,
            (first_k,),
        )
        return cursor.fetchall()

    def get_failed_test(self, test_name: str, test_status: str):
        cursor = self.table.execute(
            """
        SELECT build_env, job_url, sha, sha_idx
        FROM test_result
        WHERE test_name == (?)
          AND status == (?)
        ORDER BY sha_idx
            """,
            (test_name, test_status),
        )
        return cursor.fetchall()

    def _debug_list_all(self):
        pprint(list(self.table.execute("SELECT * FROM test_result").fetchall()))


if __name__ == "__main__":
    load_dotenv()

    commits = get_latest_commit()

    prefixes = [f"bazel_events/master/{commit.sha}" for commit in commits]

    client = boto3.client("s3")

    NUM_COMMITS = 10

    print("💻 Downloading Files from S3")
    for prefix in tqdm(prefixes[:NUM_COMMITS]):
        download_files_given_prefix(client, prefix)
        pass

    print("🔮 Analyzing Data")
    db = ResultsDB()
    for i, prefix in tqdm(enumerate(prefixes[:NUM_COMMITS])):
        if not os.path.exists(prefix):
            # The direcotry dones't exists. It's fine
            continue
        for build in os.listdir(prefix):
            dir_name = Path(prefix) / build
            build_result = process_single_build(dir_name)
            build_result.sha_index = i
            db.write_build_result(build_result)

    failed_tests = db.get_failed_tests()
    failed_tests_displays: List[SiteFailedTest] = []
    for failed in failed_tests:
        name, status, count = failed
        display = SiteFailedTest(
            name,
            status_segment_bar=[
                SiteCommitTooltip(
                    False, commits[i].message, commits[i].author_avatar_url
                )
                for i in range(NUM_COMMITS)
            ],
            travis_links=[],
        )

        for build_env, job_url, sha, sha_idx in db.get_failed_test(name, status):
            display.status_segment_bar[sha_idx].failed = True
            display.travis_links.append(SiteTravisLink(sha[:6], build_env, job_url))

        failed_tests_displays.append(display)

    print("⌛️ Generating Sites")
    with open("site/template.html.j2") as f:
        template = Template(f.read())
    rendered = template.render(
        display=failed_tests_displays, unix_timestamp=str(time.time())
    )
    with open("site/index.html", "w") as f:
        f.write(rendered)

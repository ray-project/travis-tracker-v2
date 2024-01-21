from datetime import datetime
from typing import List

import boto3
import json

from ray_ci_tracker.interfaces import GHCommit, BuildResult, TestResult

BUCKET = "ray-ci-results"
TEST_KEY = "ray_tests"
RESULT_KEY = "ray_test_results"
TWO_WEEKS = 2 * 60 * 60 * 24 * 7

def fetch_all_release_test_results(commits: List[GHCommit]) -> List[BuildResult]:
    tests = fetch_all_tests()
    build_results = []
    for test in tests:
        build_results.extend(fetch_result_for_test(test, commits))

    return build_results

def fetch_result_for_test(test: dict, commits: List[GHCommit]) -> List[BuildResult]:
    """
    Obtain build results for a single test
    """
    print(f"fetching test: {test['name']}")
    s3 = boto3.client("s3")
    files = sorted(
        s3.list_objects_v2(
            Bucket=BUCKET,
            Prefix=f"{RESULT_KEY}/{test['name']}-",
        ).get("Contents", []),
        key=lambda file: int(file["LastModified"].strftime("%s")),
        reverse=True,
    )[:100]
    if not files:
        return []
    results = [
        json.loads(
            s3.get_object(Bucket=BUCKET, Key=file["Key"])
            .get("Body")
            .read()
            .decode("utf-8")
        ) for file in files
    ]
    current_result = results.pop(0)
    build_results = []
    for commit in commits:
        build_results.append(BuildResult(
            sha = commit.sha,
            job_url = current_result["url"],
            job_id = "",
            os = "release",
            build_env = "",
            results = [TestResult(
                test_name = test["name"],
                owner = test["team"],
                status = "PASSED" if current_result["status"] == "success" else "FAILED",
                total_duration_s = 0,
                is_labeled_flaky = test.get("state") == "jailed" or test.get("stable", "True") != "True",
                is_labeled_staging = False,
            )],
        ))
        if commit.sha == current_result["commit"]:
            current_result = results.pop(0)
    return build_results

def fetch_all_tests() -> List[dict]:
    """
    Obtain release tests
    """
    s3 = boto3.client("s3")
    paginator = s3.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=BUCKET, Prefix=f"{TEST_KEY}/")
    test_objs = []
    for page in pages:
        for obj in page['Contents']:
            if not is_release_test(obj):
                continue
            test_objs.append(obj)

    return [
        json.loads(
            s3.get_object(Bucket=BUCKET, Key=obj["Key"])
            .get("Body")
            .read()
            .decode("utf-8")
        ) for obj in test_objs
    ]

def is_release_test(file) -> bool:
    """
    Check if s3 file is a release test
    """
    if int(file["LastModified"].strftime("%s")) < int(datetime.now().timestamp()) - TWO_WEEKS:
        return False

    test_name = file["Key"].lstrip(f"{TEST_KEY}/")
    return (
        not test_name.startswith("linux:__") and 
        not test_name.startswith("windows:__") and 
        not test_name.startswith("darwin:__") and 
        not test_name.endswith(".linux.json") and
        not test_name.endswith(".windows.json") and
        not test_name.endswith(".darwin.json")
    )
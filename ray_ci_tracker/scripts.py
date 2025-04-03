from pathlib import Path

import boto3
import click
import ujson as json

from ray_ci_tracker.common import run_as_sync
from ray_ci_tracker.data_source.buildkite_release import BuildkiteReleaseSource
from ray_ci_tracker.data_source.github import GithubDataSource
from ray_ci_tracker.data_source.s3 import S3DataSource
from ray_ci_tracker.database import ResultsDBReader, ResultsDBWriter
from ray_ci_tracker.interfaces import SiteDisplayRoot, SiteFailedTest, SiteWeeklyGreenMetric


AWS_ROLE = "arn:aws:iam::029272617770:role/go-flaky-dashboard"
AWS_BUCKET = "ray-ci-results"
AWS_WEEKLY_GREEN_METRIC_PREFIX = "ray_weekly_green_metric/blocker_"


@click.group()
@click.option("--cached-github/--no-cached-github", default=True)
@click.option("--cached-s3/--no-cached-s3", default=True)
@click.option("--cached-buildkite/--no-cached-buildkite", default=True)
@click.option("--cached-buildkite-release/--no-cached-buildkite-release", default=True)
@click.option("--cached-gha/--no-cached-gha", default=True)
@click.pass_context
def cli(
    ctx,
    cached_github: bool,
    cached_s3: bool,
    cached_buildkite: bool,
    cached_buildkite_release: bool,
    cached_gha: bool,
):
    ctx.ensure_object(dict)
    ctx.obj["cached_github"] = cached_github
    ctx.obj["cached_s3"] = cached_s3
    ctx.obj["cached_buildkite"] = cached_buildkite
    ctx.obj["cached_buildkite_release"] = cached_buildkite
    ctx.obj["cached_gha"] = cached_gha


@cli.command("download")
@click.argument("cache-dir")
@click.pass_context
@run_as_sync
async def download(ctx, cache_dir):
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)

    print("🐙 Fetching Commits from Github")
    commits = await GithubDataSource.fetch_commits(cache_path, ctx.obj["cached_github"])

    print("💻 Downloading Files from S3")
    await S3DataSource.fetch_all(
        cache_path, ctx.obj["cached_s3"], commits
    )

    print("💻 Downloading Files from Buildkite Release Tests")
    await BuildkiteReleaseSource.fetch_all(
        cache_path, ctx.obj["cached_buildkite_release"], commits
    )


@cli.command("etl")
@click.argument("cache_dir")
@click.argument("db_path")
@click.pass_context
@run_as_sync
async def etl_process(ctx, cache_dir, db_path):
    print("✍️ Writing Data")
    db = ResultsDBWriter(db_path, wipe=True)
    cache_path = Path(cache_dir)

    print("[1/n] Writing commits")
    commits = await GithubDataSource.fetch_commits(cache_path, ctx.obj["cached_github"])
    db.write_commits(commits)

    print("[1/n] Writing S3 data")
    build_events = await S3DataSource.fetch_all(
        cache_path, ctx.obj["cached_s3"], commits
    )
    db.write_build_results(build_events)
    del build_events
    
    print("[1/n] Writing Release Test data")
    buildkite_release_result = await BuildkiteReleaseSource.fetch_all(
        cache_path, ctx.obj["cached_buildkite_release"], commits
    )
    buildkite_release_result = list(
        filter(lambda r: r is not None, buildkite_release_result)
    )
    db.write_build_results(buildkite_release_result)
    del buildkite_release_result


def get_weekly_green_metric():
    role = boto3.client('sts').assume_role(
        RoleArn=AWS_ROLE,
        RoleSessionName="SessionOne",
    )
    credentials = role['Credentials']
    session = boto3.Session(
        aws_access_key_id=credentials['AccessKeyId'],
        aws_secret_access_key=credentials['SecretAccessKey'],
        aws_session_token=credentials['SessionToken']
    )
    s3_client = session.client("s3")
    files = sorted(
        s3_client.list_objects_v2(
            Bucket=AWS_BUCKET,
            Prefix=AWS_WEEKLY_GREEN_METRIC_PREFIX,
        ).get("Contents", []),
        key=lambda file: int(file["LastModified"].strftime("%s")),
        reverse=True,
    )[:100]

    metrics = []
    for file in files:
        blockers = json.loads(
            s3_client.get_object(
                Bucket=AWS_BUCKET,
                Key=file["Key"],
            )
            .get("Body")
            .read()
            .decode("utf-8")
        )
        metrics.append(SiteWeeklyGreenMetric(
            date=file["LastModified"].strftime("%Y-%m-%d"),
            num_of_blockers=sum(blockers.values())
        ))

    return metrics
    

@cli.command("analysis")
@click.argument("db_path")
@click.argument("frontend_json_path")
def perform_analysis(db_path, frontend_json_path):
    print("🔮 Analyzing Data")
    db = ResultsDBReader(db_path)

    failed_tests = db.list_tests_ordered()
    data_to_display = [
        SiteFailedTest(
            name=test_name,
            status_segment_bar=db.get_commit_tooltips(test_name),
            travis_links=db.get_travis_link(test_name),
            build_time_stats=db.get_recent_build_time_stats(test_name),
            is_labeled_flaky=db.get_marked_flaky_status(test_name),
            owner=db.get_test_owner(test_name),
        )
        for test_name, _ in failed_tests
    ]
    root_display = SiteDisplayRoot(
        failed_tests=data_to_display,
        stats=db.get_stats(),
        weekly_green_metric=get_weekly_green_metric(),
        test_owners=db.get_all_owners(),
        table_stat=db.get_table_stat(),
    )

    print("⌛️ Writing Out to Frontend", frontend_json_path)
    with open(frontend_json_path, "w") as f:
        json.dump(root_display.to_dict(), f)

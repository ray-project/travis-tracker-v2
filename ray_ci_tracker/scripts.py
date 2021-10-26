from pathlib import Path

import click
import ujson as json

from ray_ci_tracker.common import run_as_sync
from ray_ci_tracker.data_source.buildkite import BuildkiteSource
from ray_ci_tracker.data_source.github import GithubDataSource
from ray_ci_tracker.data_source.s3 import S3DataSource
from ray_ci_tracker.database import ResultsDBReader, ResultsDBWriter
from ray_ci_tracker.interfaces import SiteDisplayRoot, SiteFailedTest


@click.group()
@click.option("--cached-github/--no-cached-github", default=True)
@click.option("--cached-s3/--no-cached-s3", default=True)
@click.option("--cached-buildkite/--no-cached-buildkite", default=True)
@click.option("--cached-gha/--no-cached-gha", default=True)
@click.pass_context
def cli(
    ctx,
    cached_github: bool,
    cached_s3: bool,
    cached_buildkite: bool,
    cached_gha: bool,
):
    ctx.ensure_object(dict)
    ctx.obj["cached_github"] = cached_github
    ctx.obj["cached_s3"] = cached_s3
    ctx.obj["cached_buildkite"] = cached_buildkite
    ctx.obj["cached_gha"] = cached_gha


async def _downloader(
    ctx,
    cache_dir: str,
):
    cache_path = Path(cache_dir)
    cache_path.mkdir(exist_ok=True)

    print("🐙 Fetching Commits from Github")
    commits = await GithubDataSource.fetch_commits(cache_path, ctx.obj["cached_github"])

    print("💻 Downloading Files from S3")
    build_events = await S3DataSource.fetch_all(
        cache_path, ctx.obj["cached_s3"], commits
    )

    print("💻 Downloading Files from Buildkite")
    (
        buildkite_parsed,
        macos_bazel_events,
        pr_build_time,
    ) = await BuildkiteSource.fetch_all(
        cache_path, ctx.obj["cached_buildkite"], commits
    )

    print("💻 Downloading Github Action Status")
    gha_status = await GithubDataSource.fetch_all(
        cache_path, ctx.obj["cached_gha"], commits
    )
    return {
        "commits": commits,
        "bazel_events": macos_bazel_events + build_events,
        "buildkite_status": buildkite_parsed,
        "gha_status": gha_status,
        "pr_build_time": pr_build_time,
    }


@cli.command("download")
@click.argument("cache-dir")
@click.pass_context
@run_as_sync
async def download(ctx, cache_dir):
    await _downloader(ctx, cache_dir)


@cli.command("etl")
@click.argument("cache_dir")
@click.argument("db_path")
@click.pass_context
@run_as_sync
async def etl_process(ctx, cache_dir, db_path):
    loaded = await _downloader(ctx, cache_dir)

    print("✍️ Writing Data")
    db = ResultsDBWriter(db_path, wipe=True)

    print("[1/n] Writing commits")
    db.write_commits(loaded["commits"])
    print("[2/n] Writing build results")
    db.write_build_results(loaded["bazel_events"])
    print("[3/n] Writing buildkite")
    db.write_buildkite_data(loaded["buildkite_status"])
    db.write_buildkite_pr_time(loaded["pr_build_time"])
    print("[4/n] Writing github action")
    db.write_gha_data(loaded["gha_status"])
    print("[5/n] fixing data with backfill")
    db.backfill_test_owners()


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
        test_owners=db.get_all_owners(),
        table_stat=db.get_table_stat(),
    )

    print("⌛️ Writing Out to Frontend", frontend_json_path)
    with open(frontend_json_path, "w") as f:
        json.dump(root_display.to_dict(), f)

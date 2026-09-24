import asyncio
import os
import re
from pathlib import Path
from typing import List, Optional

import httpx
from ray_ci_tracker.common import get_or_fetch, retry
from ray_ci_tracker.interfaces import SiteNightlyRun

BUILDKITE_API = "https://api.buildkite.com/v2"
ORG, PIPELINE = "ray-project", "release"
# The wheels for a commit live under this prefix, but the bucket has no static
# website hosting: fetching the prefix as a path returns NoSuchKey, not a file
# listing, so a bare ".../master/<sha>/" link is dead for every row. The S3
# ListObjectsV2 query form is readable anonymously and returns the whole set
# (a commit carries ~24 objects, well inside the 1000-key page, so the result
# is never truncated). An unknown commit returns an empty listing rather than
# an error, which is the right behaviour for a sha whose wheels have aged out.
WHEEL_BUCKET_URL = "https://ray-wheels.s3.us-west-2.amazonaws.com"
WHEEL_PREFIX = "master"

# One listing request per run, so cap the fan-out rather than opening 200 at once.
_WHEEL_LIST_CONCURRENCY = 16

# Nightly images are tagged nightly.{YYMMDD}.{sha[:6]} with ~300 python/CUDA
# variants per commit. The date comes from when the image was built rather than
# when the release tests ran, so composing a tag risks an off-by-one-day 404.
# Filtering DockerHub by the six-character sha alone is date-independent and
# lands on every variant for that commit.
IMAGE_TAGS_URL = "https://hub.docker.com/r/rayproject/ray/tags?name="
DOCKERHUB_TAGS_API = (
    "https://hub.docker.com/v2/repositories/rayproject/ray/tags?page_size=1&name="
)

# Scheduled nightlies are the only master builds carrying AUTOMATIC=1. Builds
# triggered from the API or the Buildkite UI are ad-hoc maintainer runs and are
# deliberately excluded.
#
# Only the plain nightly is shown. "nightly-3x" is a separate 8-test suite rather
# than a rerun of the full set, so its pass rate is not comparable and mixing the
# two in one table is misleading. "weekly" is excluded for the same reason.
NIGHTLY_FREQUENCY = "nightly"

# Release-test jobs are labelled like "foo_test.aws (None) (0)". The image work
# in the same build (wanda:, :tapioca:, :crane:) and "init" carry no such
# suffix, and counting them roughly doubles the apparent test total.
TEST_JOB_NAME = re.compile(r"\(.*\) \(\d+\)\s*$")



def _job_name(job: dict) -> str:
    return (job.get("name") or job.get("label") or "").strip()


def _is_test_job(job: dict) -> bool:
    return job.get("type") == "script" and bool(TEST_JOB_NAME.search(_job_name(job)))


def parse_build(build: dict) -> Optional[SiteNightlyRun]:
    """Turn one Buildkite build into a nightly row, or None if it is not one."""
    env = build.get("env") or {}
    if env.get("AUTOMATIC") != "1":
        return None
    frequency = env.get("RELEASE_FREQUENCY")
    if frequency != NIGHTLY_FREQUENCY:
        return None

    # Counted, not published: only the number of test jobs leaves this function,
    # to tell a run that produced none from one that did. Individual test names
    # are deliberately withheld -- this feed is compiled into a public bundle, so
    # anything kept here is readable by anyone, and the failures are frequently
    # infrastructure rather than Ray.
    tests = [j for j in build.get("jobs", []) if _is_test_job(j)]
    sha = build.get("commit") or ""

    return SiteNightlyRun(
        build_number=build["number"],
        frequency=frequency,
        # The page's verdict comes from this: Buildkite already aggregates every
        # job in the build into one result. A non-terminal state renders as
        # "in progress", and a run with no test jobs as "incomplete".
        state=build.get("state") or "unknown",
        commit=sha,
        commit_short=sha[:8],
        created_at=build.get("created_at") or "",
        # Filled in later by attach_wheel_names; one listing request per run.
        wheels=[],
        image_tags_url=f"{IMAGE_TAGS_URL}{sha[:6]}" if sha else "",
        tests_total=len(tests),
    )


# The REST list endpoint returns every build's full job array — ~459MB to publish a
# 66KB feed, because we want six scalars per build and it ships ~530 job objects.
# GraphQL lets us select fields, so we ask only for what the page renders.
#
# Job labels are still needed to tell release tests from the image-build steps that
# share the build, so we cannot use a bare `jobs { count }`; but label+state+passed
# is a small fraction of a REST job object.
class NightlyReleaseSource:
    @staticmethod
    @retry
    async def fetch_page(page: int) -> List[dict]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{BUILDKITE_API}/organizations/{ORG}/pipelines/{PIPELINE}/builds",
                params={"branch": "master", "per_page": 100, "page": page},
                headers={
                    "Authorization": f"Bearer {os.environ['BUILDKITE_TOKEN']}"
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json()

    # Why REST and not GraphQL, which would return far less data:
    #
    # Buildkite prices GraphQL by node count against a hard budget
    # (ratelimit-limit: 20000 per ~5min window), and the label is the only
    # reliable way to tell a release test from the image-build steps sharing the
    # build, so every job has to be fetched. Measured cost is ~600 complexity per
    # build, i.e. ~33 builds per window. The ~530 master builds behind 200
    # nightlies would take ~16 windows, about 80 minutes, against a 30-minute
    # cron. REST does the same work in under three minutes; its cost is ~459MB of
    # bandwidth, which is not a constrained resource on a CI runner.
    #
    # GraphQL is only cheap here if the per-test denominator is given up:
    # jobs(type: [COMMAND]) { count } is ~540 (image builds included) and the
    # agentQueryRules queue filter is ~372, because the :tapioca: custom-image
    # builds share the release queues. Neither is the ~265 the page reports.
    @staticmethod
    async def fetch_all(
        cache_path: Path,
        cached: bool,
        target_runs: int = 200,
        max_pages: int = 8,
    ):
        """Page back through master builds until `target_runs` nightlies are found.

        Pages are fetched and parsed one at a time rather than gathered. Each raw
        page is ~85MB because the list endpoint returns every build's full job
        array, so holding several at once is what would actually hurt; the parsed
        rows are a few hundred bytes each. Stopping as soon as the target is met
        also keeps this resilient to the nightly share of master builds drifting
        (it is ~40% today, but that depends on how often maintainers kick off
        ad-hoc runs, which has nothing to do with us).
        """
        print(f"💤 Downloading nightly release builds (target {target_runs})")

        runs, seen = [], set()
        for page in range(1, max_pages + 1):
            # get_or_fetch always writes what it fetched, so a later --cached
            # run can replay it. That is worth paying for locally, where it
            # turns a multi-minute fetch into an instant one; it is pure
            # overhead in CI, where the cache directory does not outlive the
            # run. A raw page is tens of megabytes and json.dumps materialises
            # a second full copy before the write, so skip the helper entirely
            # when caching is off.
            if cached:
                builds = await get_or_fetch(
                    cache_path / f"nightly_release/page_{page}.json",
                    use_cached=True,
                    result_cls=None,
                    many=False,
                    async_func=lambda page=page: NightlyReleaseSource.fetch_page(
                        page
                    ),
                )
            else:
                builds = await NightlyReleaseSource.fetch_page(page)
            if not builds:
                print(f"   page {page}: empty, reached the end of available history")
                break

            for build in builds:
                run = parse_build(build)
                if run is not None and run.build_number not in seen:
                    seen.add(run.build_number)
                    runs.append(run)
            del builds  # release the raw page before fetching the next

            print(f"   page {page}: {len(runs)} nightly runs so far")
            if len(runs) >= target_runs:
                break

        runs.sort(key=lambda r: r.build_number, reverse=True)
        return runs[:target_runs]

    @staticmethod
    async def _has_images(run) -> bool:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                DOCKERHUB_TAGS_API + run.commit[:6], timeout=20.0
            )
            resp.raise_for_status()
            return (resp.json().get("count") or 0) > 0

    @staticmethod
    @staticmethod
    @retry
    async def _fetch_wheel_names(sha: str) -> List[str]:
        """Return the wheel filenames the bucket holds for one commit.

        The bucket is readable anonymously and sends no CORS headers, so the
        page cannot do this itself: the listing has to be resolved here and
        shipped in the feed. A commit carries a couple of dozen objects, well
        inside the 1000-key page, so there is no continuation to follow.
        """
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                WHEEL_BUCKET_URL,
                params={"list-type": "2", "prefix": f"{WHEEL_PREFIX}/{sha}/"},
                timeout=30.0,
            )
            resp.raise_for_status()
            return [
                key.rsplit("/", 1)[-1]
                for key in re.findall(r"<Key>([^<]+)</Key>", resp.text)
                if key.endswith(".whl")
            ]

    @staticmethod
    async def attach_wheel_names(runs) -> None:
        """Fill in each run's wheel list, concurrently and best effort.

        Runs inside `make data`; a raised exception here would stop the whole
        site deploying over a link list, so a commit whose listing cannot be
        read keeps an empty list and renders as "no wheels" rather than
        failing the build.
        """
        if not runs:
            return
        sem = asyncio.Semaphore(_WHEEL_LIST_CONCURRENCY)

        async def one(run):
            if not run.commit:
                return
            async with sem:
                try:
                    run.wheels = await NightlyReleaseSource._fetch_wheel_names(
                        run.commit
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"   wheel listing failed for {run.commit_short}: {e}")

        await asyncio.gather(*(one(r) for r in runs))
        listed = sum(1 for r in runs if r.wheels)
        print(f"   wheel listings: {listed}/{len(runs)} runs have wheels")

    @staticmethod
    async def drop_expired_image_links(runs) -> None:
        """Blank image links for commits whose nightly images have aged out.

        DockerHub retains nightly tags for roughly five months while this feed
        spans seven or more, so a third of rows would otherwise point at an empty
        tag filter, which reads as a broken link. Retention is a clean cutoff by
        date, so a bisect finds it in ~8 requests rather than one per run.

        Best effort: if DockerHub is unreachable the links are left intact rather
        than failing the build, since this runs inside `make data` and a raised
        exception here would stop the whole site from deploying.
        """
        if not runs:
            return
        try:
            if await NightlyReleaseSource._has_images(runs[-1]):
                return  # even the oldest run still has images
            lo, hi = 0, len(runs) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if await NightlyReleaseSource._has_images(runs[mid]):
                    lo = mid
                else:
                    hi = mid - 1
            expired = 0
            for run in runs[lo + 1 :]:
                run.image_tags_url = ""
                expired += 1
            print(
                f"   {expired} run(s) older than {runs[lo].created_at[:10]} have no "
                f"nightly images left on DockerHub; image links omitted"
            )
        except Exception as e:
            print(f"   warning: could not check DockerHub image retention ({e})")

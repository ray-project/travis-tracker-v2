from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd
from dataclasses_json import DataClassJsonMixin
from py_ts_interfaces import Interface


def _parse_duration(started_at, finished_at) -> int:
    started = pd.to_datetime(started_at)
    finished = pd.to_datetime(finished_at)
    if started is None or finished is None:
        duration_s = 0
    else:
        duration_s = (finished - started).total_seconds()
    return duration_s


class Mixin(Interface, DataClassJsonMixin):
    pass


@dataclass
class GHCommit(Mixin):
    sha: str
    unix_time_s: int

    message: str
    html_url: str

    author_login: str
    author_avatar_url: str


@dataclass
class TestResult(Mixin):
    test_name: str
    status: str
    total_duration_s: float
    is_labeled_flaky: bool
    owner: str
    is_labeled_staging: bool


@dataclass
class BuildResult(Mixin):
    sha: str
    job_url: str
    os: str
    build_env: str
    job_id: str
    results: List[TestResult]


@dataclass
class SiteTravisLink(Mixin):
    sha_short: str
    sha: str
    commit_time: int
    commit_message: str
    build_env: str
    job_url: str
    os: str
    status: str


@dataclass
class SiteCommitTooltip(Mixin):
    num_failed: Optional[int]
    num_flaky: Optional[int]
    message: str
    author_avatar: str
    commit_url: str


@dataclass
class SiteStatItem(Mixin):
    key: str
    unit: str
    value: float
    desired_value: float


@dataclass
class SiteFailedTest(Mixin):
    name: str
    status_segment_bar: List[SiteCommitTooltip]
    travis_links: List[SiteTravisLink]
    build_time_stats: Optional[List[float]]
    is_labeled_flaky: bool
    owner: str


@dataclass
class SiteDisplayRoot(Mixin):
    failed_tests: List[SiteFailedTest]
    stats: List[SiteStatItem]
    test_owners: List[str]
    table_stat: str


@dataclass
class BuildkiteArtifact(Mixin):
    url: str
    bazel_events_path: str
    job_id: str
    sha: str


@dataclass
class BuildkiteStatus(Mixin):
    job_id: str
    label: str
    passed: bool  # if it's running, passed=false
    state: str
    url: str
    commit: str
    startedAt: Optional[str]
    finished_at: Optional[str]

    artifacts: List[BuildkiteArtifact]

    def get_duration_s(self) -> int:
        return _parse_duration(self.startedAt, self.finished_at)


@dataclass
class GHAJobStat(Mixin):
    job_id: str
    os: str
    commit: str
    env: str
    state: str
    url: str
    duration_s: int


@dataclass
class BuildkitePRBuildTime(Mixin):
    commit: str
    created_by: str
    state: str
    url: str
    created_at: str
    started_at: Optional[str]
    finished_at: Optional[str]
    pull_id: str

    def get_duration_s(self) -> int:
        return _parse_duration(self.started_at, self.finished_at)

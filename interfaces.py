from typing import List, Dict, Optional
from dataclasses import dataclass

from py_ts_interfaces import Interface
from dataclasses_json import DataClassJsonMixin


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


@dataclass
class BuildResult(Mixin):
    sha: str
    job_url: str
    os: str
    build_env: str
    results: List[TestResult]


@dataclass
class SiteTravisLink(Mixin):
    sha_short: str
    commit_time: int
    commit_message: str
    build_env: str
    job_url: str
    os: str


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


@dataclass
class SiteDisplayRoot(Mixin):
    failed_tests: List[SiteFailedTest]
    stats: List[SiteStatItem]

from typing import List, Optional, Union
from dataclasses import dataclass

from py_ts_interfaces import Interface
from dataclasses_json import DataClassJsonMixin


class Mixin(Interface, DataClassJsonMixin):
    pass


@dataclass
class GHCommit(Mixin):
    sha: str

    message: str
    html_url: str

    author_login: str
    author_avatar_url: str


@dataclass
class TestResult(Mixin):
    test_name: str
    status: str


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
    commit_message: str
    build_env: str
    job_url: str
    os: str


@dataclass
class SiteCommitTooltip(Mixin):
    failed: bool
    message: str
    author_avatar: str
    commit_url: str


@dataclass
class SiteFailedTest(Mixin):
    name: str
    status_segment_bar: List[SiteCommitTooltip]
    travis_links: List[SiteTravisLink]

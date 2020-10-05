// Generated using py-ts-interfaces.
// See https://github.com/cs-cordero/py-ts-interfaces

export interface GHCommit {
    sha: string;
    unix_time_s: number;
    message: string;
    html_url: string;
    author_login: string;
    author_avatar_url: string;
}

export interface TestResult {
    test_name: string;
    status: string;
}

export interface BuildResult {
    sha: string;
    job_url: string;
    os: string;
    build_env: string;
    results: Array<TestResult>;
}

export interface SiteTravisLink {
    sha_short: string;
    commit_time: number;
    commit_message: string;
    build_env: string;
    job_url: string;
    os: string;
}

export interface SiteCommitTooltip {
    num_failed: number | null;
    message: string;
    author_avatar: string;
    commit_url: string;
}

export interface SiteStatItem {
    key: string;
    unit: string;
    value: number;
    desired_value: number;
}

export interface SiteFailedTest {
    name: string;
    status_segment_bar: Array<SiteCommitTooltip>;
    travis_links: Array<SiteTravisLink>;
}

export interface SiteDisplayRoot {
    failed_tests: Array<SiteFailedTest>;
    stats: Array<SiteStatItem>;
}

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
    total_duration_s: number;
    is_labeled_flaky: boolean;
    owner: string;
}

export interface BuildResult {
    sha: string;
    job_url: string;
    os: string;
    build_env: string;
    job_id: string;
    results: Array<TestResult>;
}

export interface SiteTravisLink {
    sha_short: string;
    commit_time: number;
    commit_message: string;
    build_env: string;
    job_url: string;
    os: string;
    status: string;
}

export interface SiteCommitTooltip {
    num_failed: number | null;
    num_flaky: number | null;
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
    build_time_stats: Array<number> | null;
    is_labeled_flaky: boolean;
    owner: string;
}

export interface SiteDisplayRoot {
    failed_tests: Array<SiteFailedTest>;
    stats: Array<SiteStatItem>;
    test_owners: Array<string>;
    table_stat: string;
}

export interface BuildkiteArtifact {
    url: string;
    bazel_events_path: string;
}

export interface BuildkiteStatus {
    job_id: string;
    label: string;
    passed: boolean;
    state: string;
    url: string;
    commit: string;
    startedAt: string | null;
    finished_at: string | null;
    artifacts: Array<BuildkiteArtifact>;
}

export interface GHAJobStat {
    job_id: string;
    os: string;
    commit: string;
    env: string;
    state: string;
    url: string;
    duration_s: number;
}

export interface BuildkitePRBuildTime {
    commit: string;
    created_by: string;
    state: string;
    url: string;
    created_at: string;
    started_at: string | null;
    finished_at: string | null;
    pull_id: string;
}
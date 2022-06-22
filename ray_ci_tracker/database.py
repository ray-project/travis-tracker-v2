from collections import defaultdict
import dataclasses
from itertools import chain
from sqlite3 import connect
from typing import List, Optional

import numpy as np
import ujson as json

from ray_ci_tracker.interfaces import (
    BuildkitePRBuildTime,
    BuildkiteStatus,
    BuildResult,
    GHAJobStat,
    GHCommit,
    SiteCommitTooltip,
    SiteStatItem,
    SiteTravisLink,
)


class ResultsDBWriter:
    def __init__(self, location=":memory:", wipe=True) -> None:
        self.table = connect(location)
        self.table.executescript(
            """
        PRAGMA synchronous=OFF;
        PRAGMA journal_mode=MEMORY;
        """
        )
        if not wipe:
            return
        self.table.executescript(
            """
        DROP TABLE IF EXISTS test_result;
        CREATE TABLE test_result (
            test_name TEXT,
            status TEXT,
            build_env TEXT,
            os TEXT,
            job_url TEXT,
            job_id TEXT,
            sha TEXT,
            test_duration_s REAL,
            is_labeled_flaky BOOLEAN,
            owner TEXT,
            is_staging_test BOOLEAN
        );

        DROP TABLE IF EXISTS commits;
        CREATE TABLE commits (
            sha TEXT,
            unix_time INT,
            idx INT,
            message TEXT,
            url TEXT,
            avatar_url TEXT
        );

        DROP TABLE IF EXISTS pr_time;
        CREATE TABLE pr_time (
            sha TEXT,
            created_by TEXT,
            state TEXT,
            url TEXT,
            created_at TEXT,
            started_at TEXT,
            finished_at TEXT,
            pull_id TEXT,
            duration_min REAL
        );

        CREATE INDEX test_result_hot_path_job_id
        ON test_result (job_id);

        CREATE INDEX test_result_hot_path_test_name
        ON test_result (test_name);
        """
        )

    def write_commits(self, commits: List[GHCommit]):
        self.table.executemany(
            "INSERT INTO commits VALUES (?,?,?,?,?,?)",
            [
                (
                    commit.sha,
                    commit.unix_time_s,
                    i,
                    commit.message,
                    commit.html_url,
                    commit.author_avatar_url,
                )
                for i, commit in enumerate(commits)
            ],
        )
        self.table.commit()

    def write_build_results(self, results: List[BuildResult]):
        records_to_insert = []
        for build_result in results:
            for test in build_result.results:
                records_to_insert.append(
                    (
                        f"{build_result.os}:{test.test_name}",
                        test.status,
                        build_result.build_env,
                        build_result.os,
                        build_result.job_url,
                        build_result.job_id,
                        build_result.sha,
                        test.total_duration_s,
                        test.is_labeled_flaky,
                        test.owner,
                        test.is_labeled_staging,
                    )
                )

        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?,?, ?)",
            records_to_insert,
        )
        self.table.commit()

    def write_buildkite_pr_time(self, pr_time_data: List[BuildkitePRBuildTime]):
        records_to_insert = []
        for build in pr_time_data:
            records_to_insert.append(
                (
                    *dataclasses.astuple(build),
                    build.get_duration_s() / 60,
                )
            )
        self.table.executemany(
            f"INSERT INTO pr_time VALUES ({','.join(['?']*9)})",
            records_to_insert,
        )
        self.table.commit()

    def write_buildkite_data(self, buildkite_data: List[BuildkiteStatus]):
        records_to_insert = []
        for job in buildkite_data:
            num_result = self.table.execute(
                f"SELECT COUNT(*) FROM test_result WHERE job_id == (?)",
                (job.job_id,),
            ).fetchone()[0]
            status = "PASSED" if job.passed else "FAILED"
            if job.state == "FINISHED":
                records_to_insert.append(
                    (
                        f"bk://{job.label}",
                        # Mark the entire build passed when individual tests result uploaded
                        status if num_result == 0 else "PASSED",
                        job.label,
                        "linux",
                        job.url,
                        job.job_id,
                        job.commit,
                        job.get_duration_s(),
                        False,  # is_labeled_flaky
                        "infra",  # owner
                        False,  # is_labeled_staging
                    )
                )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?,?, ?)",
            records_to_insert,
        )
        self.table.commit()

    def write_gha_data(self, gha_data: List[GHAJobStat]):
        records_to_insert = []
        for gha_run in gha_data:
            num_result = len(
                self.table.execute(
                    f"SELECT * FROM test_result WHERE sha == (?) AND os == (?)",
                    (gha_run.commit, "windows"),
                ).fetchall()
            )
            if gha_run.state is not None:
                records_to_insert.append(
                    (
                        f"{gha_run.os}://github-action/{gha_run.env}",
                        # Mark the entire build passed when individual tests result uploaded
                        gha_run.state if num_result == 0 else "PASSED",
                        gha_run.env,
                        gha_run.os,
                        gha_run.url,
                        gha_run.job_id,
                        gha_run.commit,
                        gha_run.duration_s,
                        False,  # is_labeled_flaky
                        "infra",  # owner
                        False,  # is_labeled_staging
                    )
                )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def backfill_test_owners(self):
        results = self.table.execute(
            """
        WITH need_backfill as (
            SELECT test_name
            FROM test_result
            GROUP BY test_name
            HAVING COUNT(DISTINCT owner) > 1
        )
        SELECT need_backfill.test_name, owner
        FROM need_backfill, test_result
        WHERE need_backfill.test_name = test_result.test_name
        AND test_result.owner NOT LIKE 'unknown'
        GROUP BY need_backfill.test_name
        """
        ).fetchall()
        self.table.executemany(
            """
            UPDATE test_result
            SET owner = (?)
            WHERE test_name = (?)
            """,
            [(owner, test_name) for test_name, owner in results],
        )
        self.table.commit()


class ResultsDBReader:
    def __init__(self, path) -> None:
        self.table = connect(path)

    def list_tests_ordered(self):
        query = f"""
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == (?)
            GROUP BY test_name
        """
        failed_tests = self.table.execute(query, ("FAILED",)).fetchall()
        flaky_tests = self.table.execute(query, ("FLAKY",)).fetchall()
        passed_tests = self.table.execute(
            f"""
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == (?)
            AND test_result.test_duration_s > 600
            GROUP BY test_name
        """,
            ("PASSED",),
        ).fetchall()
        top_failed_tests = self.table.execute(
            """
            SELECT test_name, SUM(10 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
            AND commits.idx < 10
            GROUP BY test_name
        """
        ).fetchall()
        green_flaky_tests = self.table.execute(
            """
            SELECT test_name, SUM(100 - commits.idx) as weight
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
              AND status == 'PASSED'
              AND is_labeled_flaky = 1
            GROUP BY test_name
        """
        ).fetchall()

        prioritization = defaultdict(int)
        for test_name, score in top_failed_tests:
            prioritization[test_name] += score * 1_000_000  # Prioritize recent failure.

        for test_name, score in failed_tests:
            prioritization[test_name] += score

        # for test_name, score in green_flaky_tests:
        #     prioritization[test_name] += 0.5 * score

        for test_name, score in flaky_tests:
            prioritization[test_name] += 0.1 * score

        for test_name, score in passed_tests:
            prioritization[test_name] += 0.001 * score

        results = sorted(list(prioritization.items()), key=lambda kv: -kv[1])
        return results

    def get_travis_link(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Travis Link
            SELECT commits.sha, commits.unix_time, commits.message, build_env, job_url, os, status
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status in ('FAILED', 'FLAKY')
            AND test_name == (?)
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteTravisLink(
                sha_short=sha[:6],
                commit_time=unix_time,
                commit_message=msg,
                build_env=env,
                job_url=url,
                os=os,
                status=status,
            )
            for sha, unix_time, msg, env, url, os, status in cursor.fetchall()
        ]

    def get_recent_build_time_stats(self, test_name: str) -> Optional[List[float]]:
        cursor = self.table.execute(
            """
            -- Build Time Stats
            SELECT test_duration_s
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND commits.idx <= 50
            AND test_name == (?)
            """,
            (test_name,),
        )
        arr = np.array(list(cursor)).flatten()
        if len(arr) == 0:
            return [0, 0, 0]
        runtime_stat = np.percentile(arr, [0, 50, 90]).tolist()
        return runtime_stat

    def get_marked_flaky_status(self, test_name: str) -> bool:
        cursor = self.table.execute(
            "SELECT SUM(is_labeled_flaky) FROM test_result WHERE test_name == (?)",
            (test_name,),
        )
        return bool(list(cursor)[0][0])

    def get_test_owner(self, test_name: str) -> str:
        cursor = self.table.execute(
            "SELECT owner FROM test_result WHERE test_name == (?) GROUP BY owner",
            (test_name,),
        )
        owners = cursor.fetchall()
        return owners[0][0]

    def get_all_owners(self) -> List[str]:
        return list(
            chain.from_iterable(
                self.table.execute("SELECT owner FROM test_result GROUP BY owner")
            )
        )

    def get_commit_tooltips(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Commit Tooltip
            WITH filtered(sha, num_failed, num_flaky) AS (
                SELECT sha, SUM(status == 'FAILED'), SUM(status == 'FLAKY') as num_failed
                FROM test_result
                WHERE test_name == (?)
                GROUP BY sha
            )
            SELECT commits.sha, commits.message, commits.url, commits.avatar_url,
                filtered.num_failed, filtered.num_flaky
            FROM commits LEFT JOIN filtered
            ON commits.sha == filtered.sha
            ORDER BY commits.idx
            """,
            (test_name,),
        )
        return [
            SiteCommitTooltip(
                num_failed=num_failed,
                num_flaky=num_flaky,
                message=msg,
                author_avatar=avatar,
                commit_url=url,
            )
            for _, msg, url, avatar, num_failed, num_flaky in cursor.fetchall()
        ]

    def get_stats(self):
        master_green_query = """
            -- Master Green Rate (past 100 commits)
            SELECT SUM(green)*1.0/COUNT(green)
            FROM (
                SELECT SUM(status == 'FAILED') == 0 as green
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                  AND test_result.is_staging_test == FALSE
                GROUP BY test_result.sha
                ORDER BY commits.idx
            )
        """

        master_green_without_flaky_query = """
            -- Master Green Rate (past 100 commits) (without flaky tests)
            SELECT SUM(green)*1.0/COUNT(green)
            FROM (
                SELECT SUM(status == 'FAILED') == 0 as green
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                  AND test_result.is_labeled_flaky == 0
                  AND test_result.os NOT LIKE 'windows'
                  AND test_result.is_staging_test == FALSE
                GROUP BY commits.sha
                ORDER BY commits.idx
            )
        """

        master_green_without_windows_query = """
            -- Master Green Rate (past 100 commits)
            SELECT SUM(green)*1.0/COUNT(green)
            FROM (
                SELECT SUM(status == 'FAILED') == 0 as green
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                  AND test_result.os NOT LIKE 'windows'
                  AND test_result.is_staging_test == FALSE
                GROUP BY test_result.sha
                ORDER BY commits.idx
            )
        """

        pr_build_p50_query = """
            WITH finished_job_time AS (
                SELECT duration_min
                FROM pr_time
                WHERE duration_min > 0
                AND state NOT LIKE "%CANCELED%"
                ORDER BY duration_min
            )
            SELECT duration_min
            FROM finished_job_time
            ORDER BY duration_min
            LIMIT 1
            OFFSET (SELECT COUNT(*)
                    FROM finished_job_time) / 2
        """

        return [
            SiteStatItem(
                key="Master Green (past 100 commits)",
                value=self.table.execute(master_green_query).fetchone()[0] * 100,
                desired_value=100,
                unit="%",
            ),
            SiteStatItem(
                key="Master Green (without windows)",
                value=self.table.execute(master_green_without_windows_query).fetchone()[
                    0
                ]
                * 100,
                desired_value=100,
                unit="%",
            ),
            # SiteStatItem(
            #     key="Master Green (without window + flaky tests)",
            #     value=self.table.execute(master_green_without_flaky_query).fetchone()[0]
            #     * 100,
            #     desired_value=100,
            #     unit="%",
            # ),
            SiteStatItem(
                key="P50 Buildkite PR Build Time (last 500 builds)",
                value=self.table.execute(pr_build_p50_query).fetchone()[0],
                desired_value=45,
                unit="min",
            ),
        ]

    def get_table_stat(self):
        query_template = """
        SELECT owner, SUM(green)*1.0/COUNT(green) as pass_rate
        FROM (
            SELECT test_result.owner, SUM(status == 'FAILED') == 0 as green
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND commits.idx <= 100
            {condition}
            GROUP BY test_result.owner, test_result.sha
            ORDER BY commits.idx
        )
        GROUP BY owner
        ORDER BY owner
        """

        per_team_pass_rate_all = self.table.execute(
            query_template.format(condition="")
        ).fetchall()
        per_team_pass_rate_no_windows = self.table.execute(
            query_template.format(condition="AND test_result.os NOT LIKE 'windows'")
        ).fetchall()
        per_team_pass_rate_no_windows_no_flaky = self.table.execute(
            query_template.format(
                condition="AND test_result.os NOT LIKE 'windows' AND test_result.is_labeled_flaky == 0"
            )
        ).fetchall()

        owners = dict(per_team_pass_rate_all).keys()

        data_source = [
            {
                "key": "Pass Rate",
                **{k: f"{int(v*100)}%" for k, v in per_team_pass_rate_all},
            },
            {
                "key": "Pass Rate (No Windows)",
                **{k: f"{int(v*100)}%" for k, v in per_team_pass_rate_no_windows},
            },
            # {
            #     "key": "Pass Rate (No Windows, Flaky)",
            #     **{
            #         k: f"{int(v*100)}%"
            #         for k, v in per_team_pass_rate_no_windows_no_flaky
            #     },
            # },
        ]
        columns = [{"title": "", "dataIndex": "key", "key": "key"}] + [
            {"title": name, "dataIndex": name, "key": name} for name in owners
        ]
        return json.dumps({"dataSource": data_source, "columns": columns})

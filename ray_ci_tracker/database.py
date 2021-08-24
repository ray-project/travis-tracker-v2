from collections import defaultdict
from sqlite3 import connect
from typing import List, Optional

import numpy as np

from ray_ci_tracker.interfaces import (
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
            is_labeled_flaky BOOLEAN
        );

        DROP TABLE IF EXISTS commits;
        CREATE TABLE commits (
            sha TEXT,
            unix_time INT,
            idx INT,
            message TEXT,
            url TEXT,
            avatar_url TEXT
        )
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
                    )
                )

        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
            records_to_insert,
        )
        self.table.commit()

    def write_buildkite_data(self, buildkite_data: List[BuildkiteStatus]):
        records_to_insert = []
        for job in buildkite_data:
            num_result = len(
                self.table.execute(
                    f"SELECT * FROM test_result WHERE job_id == (?)",
                    (job.job_id,),
                ).fetchall()
            )
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
                    )
                )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
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
                    )
                )
        self.table.executemany(
            "INSERT INTO test_result VALUES (?,?,?,?,?,?,?,?,?)",
            records_to_insert,
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

        results = sorted(list(prioritization.items()), key=lambda kv: -kv[1])
        return results

    def get_travis_link(self, test_name: str):
        cursor = self.table.execute(
            """
            -- Travis Link
            SELECT commits.sha, commits.unix_time, commits.message, build_env, job_url, os
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND status == 'FAILED'
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
            )
            for sha, unix_time, msg, env, url, os in cursor.fetchall()
        ]

    def get_recent_build_time_stats(self, test_name: str) -> Optional[List[float]]:
        cursor = self.table.execute(
            """
            -- Build Time Stats
            SELECT test_duration_s
            FROM test_result, commits
            WHERE test_result.sha == commits.sha
            AND commits.idx <= 20
            AND test_name == (?)
            """,
            (test_name,),
        )
        arr = np.array(list(cursor)).flatten()
        if len(arr) == 0:
            return None
        runtime_stat = np.percentile(arr, [0, 50, 90]).tolist()
        return runtime_stat

    def get_marked_flaky_status(self, test_name: str) -> bool:
        cursor = self.table.execute(
            "SELECT SUM(is_labeled_flaky) FROM test_result WHERE test_name == (?)",
            (test_name,),
        )
        return bool(list(cursor)[0][0])

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
                GROUP BY commits.sha
                ORDER BY commits.idx
            )
        """

        pass_rate_query = """
            -- Number of tests with <95% pass rate
            SELECT COUNT(*)
            FROM (
                SELECT test_name, 1 - (SUM(status == 'FAILED') *1.0 / COUNT(*)) AS success_rate
                FROM test_result, commits
                WHERE test_result.sha == commits.sha
                GROUP BY test_name
                ORDER BY success_rate
            )
            WHERE success_rate < 0.95
        """

        return [
            SiteStatItem(
                key="Master Green (past 100 commits)",
                value=self.table.execute(master_green_query).fetchone()[0] * 100,
                desired_value=100,
                unit="%",
            ),
            SiteStatItem(
                key="Master Green (without flaky tests)",
                value=self.table.execute(master_green_without_flaky_query).fetchone()[0]
                * 100,
                desired_value=100,
                unit="%",
            ),
            SiteStatItem(
                key="Number of Tests <95% Pass",
                value=self.table.execute(pass_rate_query).fetchone()[0],
                desired_value=0,
                unit="",
            ),
        ]

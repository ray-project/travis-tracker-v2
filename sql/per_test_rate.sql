-- Master Green Rate (past 100 commits)
-- SELECT test_name, SUM(green)*1.0/COUNT(green) as pass_rate
-- FROM (
--     SELECT test_result.test_name, SUM(status == 'FAILED') == 0 as green
--     FROM test_result, commits
--     WHERE test_result.sha == commits.sha
--       AND commits.idx <= 100
--     GROUP BY test_result.test_name, test_result.sha
--     ORDER BY commits.idx
-- )
-- GROUP BY test_name
-- ORDER BY pass_rate

SELECT ownder, SUM(green)*1.0/COUNT(green) as pass_rate
FROM (
    SELECT owners.ownder, SUM(status == 'FAILED') == 0 as green
    FROM test_result, commits, owners
    WHERE test_result.sha == commits.sha
      AND commits.idx <= 100
      AND test_result.test_name == owners.test_name
    GROUP BY owners.ownder, test_result.sha
    ORDER BY commits.idx
)
GROUP BY ownder
ORDER BY pass_rate
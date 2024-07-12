-- Master Green Rate (past 200 commits)
-- SELECT test_name, SUM(green)*1.0/COUNT(green) as pass_rate
-- FROM (
--     SELECT test_result.test_name, SUM(status == 'FAILED') == 0 as green
--     FROM test_result, commits
--     WHERE test_result.sha == commits.sha
--       AND commits.idx <= 200
--     GROUP BY test_result.test_name, test_result.sha
--     ORDER BY commits.idx
-- )
-- GROUP BY test_name
-- ORDER BY pass_rate

SELECT owner, SUM(green)*1.0/COUNT(green) as pass_rate
FROM (
    SELECT test_result.owner, SUM(status == 'FAILED') == 0 as green
    FROM test_result, commits
    WHERE test_result.sha == commits.sha
      AND commits.idx <= 200
      AND os NOT LIKE 'windows'
    GROUP BY test_result.owner, test_result.sha
    ORDER BY commits.idx
)
GROUP BY owner
ORDER BY pass_rate

SELECT test_name
FROM test_result
WHERE owner LIKE 'unknown'
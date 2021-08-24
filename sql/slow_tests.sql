-- SQLite
SELECT test_name, (SUM(test_duration_s)/COUNT(*)) as mean_duration_s
FROM test_result,commits
WHERE test_name NOT LIKE "%travis%"
  AND test_name NOT LIKE "bk:%"
AND test_result.sha == commits.sha
AND commits.idx <= 20
GROUP BY test_name
ORDER BY mean_duration_s DESC
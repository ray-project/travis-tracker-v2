-- SQLite
.mode table

SELECT test_name, owner, (SUM(test_duration_s)/COUNT(*)) as mean_duration_s
FROM test_result,commits
WHERE owner NOT LIKE "%infra%"
AND test_result.sha == commits.sha
AND commits.idx <= 20
GROUP BY test_name
ORDER BY mean_duration_s DESC
LIMIT 10
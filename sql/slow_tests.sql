-- SQLite
.mode column
.headers on

SELECT SUBSTR(test_name, 0, 50) as name, owner, PRINTF("%.2f", mean_duration_s) as duration_s
FROM (
  SELECT test_name, owner, (SUM(test_duration_s)/COUNT(*)) as mean_duration_s
  FROM test_result,commits
  WHERE owner NOT LIKE "%infra%"
  AND test_result.sha == commits.sha
  AND commits.idx <= 20
  GROUP BY test_name
  ORDER BY mean_duration_s DESC
  LIMIT 10
)
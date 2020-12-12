import os
import sqlite3
import requests
from dotenv import load_dotenv

load_dotenv()

db = sqlite3.connect("./results.db")
top_failed_tests = list(
    db.execute(
        """
SELECT test_name, COUNT(*) as failed_count
FROM test_result, commits
WHERE test_result.sha == commits.sha
  AND status == 'FAILED'
  AND commits.idx < 20
GROUP BY test_name
  HAVING COUNT(*) >= 5
ORDER BY failed_count DESC;
"""
    )
)
markdown_lines = ["🚓 Your Flaky Test Report of the Day (posted 9AM each weekday)"]
for name, count in top_failed_tests:
    markdown_lines.append(f"- `{name}` failed *{count}* times over latest 20 tests.")
markdown_lines.append("Go to https://flakey-tests.ray.io/ to view Travis links")
slack_url = os.environ["SLACK_WEBHOOK"]
slack_channnel = os.environ.get("SLACK_CHANNEL_OVERRIDE", "#open-source")

resp = requests.post(
    slack_url,
    json={
        "text": "\n".join(markdown_lines),
        "channel": slack_channnel,
        "username": "Flaky Bot",
        "icon_emoji": ":snowflake:",
    },
)
print(resp.status_code)
print(resp.text)
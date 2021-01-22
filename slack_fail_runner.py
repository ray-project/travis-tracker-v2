import os
import sqlite3
import requests
from dotenv import load_dotenv
import sys

load_dotenv()

db = sqlite3.connect("./results.db")
failed_tests = list(
    db.execute(
        """
SELECT test_name, COUNT(*) as failed_count
FROM test_result, commits
WHERE test_result.sha == commits.sha
  AND status == 'FAILED'
  AND commits.idx < 5
GROUP BY test_name
  HAVING COUNT(*) >= 3
"""
    )
)
if len(failed_tests) == 0:
    print("No failed cases, skipping.")
    sys.exit(0)

markdown_lines = ["🚧 Your Failing Test Report"]
for name, count in failed_tests:
    markdown_lines.append(f"- `{name}` failed *{count}* times over latest 5 "
                          f"tests.")
markdown_lines.append("Go to https://flakey-tests.ray.io/ to view Travis links")
slack_url = os.environ["SLACK_WEBHOOK"]
slack_channnel = os.environ.get("SLACK_CHANNEL_OVERRIDE", "#open-source")

resp = requests.post(
    slack_url,
    json={
        "text": "\n".join(markdown_lines),
        "channel": slack_channnel,
        "username": "Fail Bot",
        "icon_emoji": ":red_circle:",
    },
)
print(resp.status_code)
print(resp.text)

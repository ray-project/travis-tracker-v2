import os
import sqlite3
import requests
from dotenv import load_dotenv
import sys
from datetime import datetime
import pytz

from docker_checker import check_recent_commits_have_docker_build

current_time_pacific = (
    datetime.utcnow()
    .replace(tzinfo=pytz.utc)
    .astimezone(pytz.timezone("America/Los_Angeles"))
)

if not ((9 <= current_time_pacific.hour < 17) and (current_time_pacific.weekday() < 5)):
    print("Not in US pacific working hours, skipping...")
    sys.exit(0)


load_dotenv()

db = sqlite3.connect("./results.db")
failed_tests = list(
    db.execute(
        """
SELECT test_name, COUNT(*) as failed_count
FROM test_result, commits
WHERE test_result.sha == commits.sha
  AND status == 'FAILED'
  AND commits.idx <= 5
GROUP BY test_name
  HAVING COUNT(*) >= 3
"""
    )
)
failed_docker_builds = check_recent_commits_have_docker_build()
if len(failed_tests) == 0 and len(failed_docker_builds) == 0:
    print("No failed cases, skipping.")
    sys.exit(0)

markdown_lines = []
if len(failed_tests) != 0:
    markdown_lines.append("🚧 Your Failing Test Report")
    for name, count in failed_tests:
        markdown_lines.append(f"- `{name}` failed *{count}* times over latest 5 commits")
    markdown_lines.append("Go to https://flakey-tests.ray.io/ to view Travis links")

markdown_lines.extend(failed_docker_builds)
slack_url = os.environ["SLACK_WEBHOOK"]
slack_channnel = os.environ.get("SLACK_CHANNEL_OVERRIDE", "#oss-test-cop")

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

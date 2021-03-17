import os
import requests

slack_url = os.environ["SLACK_WEBHOOK"]
slack_channnel = os.environ.get("SLACK_CHANNEL_OVERRIDE", "#oss-test-cop")

resp = requests.post(
    slack_url,
    json={
        "text": "Job Failure!! Please check: https://github.com/ray-project/travis-tracker-v2/actions",
        "channel": slack_channnel,
        "username": "Fail Bot",
        "icon_emoji": ":red_circle:",
    },
)
print(resp.status_code)
print(resp.text)
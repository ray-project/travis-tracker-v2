import requests
import os

token = os.environ["DB_TOKEN"]
job_id = "632878248547820"
list_job_url = "https://dbc-073b287d-29d2.cloud.databricks.com/api/2.0/jobs/runs/list"
export_url = "https://dbc-073b287d-29d2.cloud.databricks.com/api/2.0/jobs/runs/export"

resp = requests.get(
    list_job_url,
    headers={"Authorization": f"Bearer {token}"},
    params={"job_id": job_id, "completed_only": True, "limit": 1},
)
run_id = resp.json()["runs"][0]["run_id"]

resp = requests.get(
    export_url,
    headers={"Authorization": f"Bearer {token}"},
    params={"run_id": run_id, "views_to_export": "DASHBOARDS"},
)
data = resp.json()

with open("serve.html", "w") as f:
    f.write(data["views"][0]["content"])

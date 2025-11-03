import requests
import os
import json


_OUTPUT_FILE = "serve.html"


def _write_empty_output():
    print("No dashboard views found")
    with open(_OUTPUT_FILE, "w") as f:
        f.write("<html><body><p>No dashboard views found.</p></body></html>")


def _main():
    token = os.environ["DB_TOKEN"]
    job_id = "632878248547820"
    list_job_url = "https://dbc-073b287d-29d2.cloud.databricks.com/api/2.0/jobs/runs/list"
    export_url = "https://dbc-073b287d-29d2.cloud.databricks.com/api/2.0/jobs/runs/export"

    resp = requests.get(
        list_job_url,
        headers={"Authorization": f"Bearer {token}"},
        params={"job_id": job_id, "completed_only": True, "limit": 1},
    )
    resp.raise_for_status()

    resp_json = resp.json()
    if "runs" not in resp_json:
        _write_empty_output()
        return

    run_id = resp_json["runs"][0]["run_id"]

    resp = requests.get(
        export_url,
        headers={"Authorization": f"Bearer {token}"},
        params={"run_id": run_id, "views_to_export": "DASHBOARDS"},
    )
    resp.raise_for_status()

    data = resp.json()

    if "views" not in data:
        _write_empty_output()
    else:
        with open(_OUTPUT_FILE, "w") as f:
            f.write(data["views"][0]["content"])


if __name__ == "__main__":
    _main()

import concurrent.futures
from dateutil.parser import parse as date_parser
from datetime import datetime, timedelta
import json
import pytz
import requests
from typing import Any, Dict, List, Optional, Tuple

from fetch_and_render import get_latest_commit

ARCH_VERSIONS = ["-cpu", "-gpu", ""]
IMAGES_TO_CHECK = ["ray", "ray-ml"]
MAX_TIME_FOR_DOCKER_BUILD = timedelta(hours=3)
PYTHON_VERSIONS = ["py36", "py37", "py38"]


def get_most_recent_layer(tag_resp: Dict[str, Any]) -> datetime:
    """
    Find the time of the most recently created layer of a given image.
    """
    dates = []
    for layer in tag_resp["history"]:
        layer_json = json.loads(layer["v1Compatibility"])
        dates.append(date_parser(layer_json["created"]).replace(tzinfo=pytz.utc))
    return max(dates)

def fetch_manifest_time(image_name: str, tag: str, token: str) -> datetime:
    """
    Fetches the manifest of the provided `image_name`:`tag` and returns the time
    it was created.
    """
    manifest_url = f"https://registry.hub.docker.com/v2/rayproject/{image_name}/manifests/{tag}"
    manifest_resp = requests.get(manifest_url,headers={"Authorization": f"Bearer {token}"})
    assert manifest_resp.ok
    return get_most_recent_layer(manifest_resp.json())
    


def check_last_updated_for_repo(image_name: str, tag_prefix="nightly") -> Dict[str, datetime]:
    """
    Returns a mapping from `image_name`:`tag` to time of creation. This looks through
    ARCH_VERSIONS and PYTHON_VERSIONS to generate all possible tags.
    """
    token_url = f"https://auth.docker.io/token?service=registry.docker.io&scope=repository:rayproject/{image_name}:pull"
    token_resp = requests.get(token_url)
    assert token_resp.ok
    token = token_resp.json()["token"]

    results = {}
    with concurrent.futures.ThreadPoolExecutor() as executor:
        for py_version in PYTHON_VERSIONS:
            for arch in ARCH_VERSIONS:
                tag = f"{tag_prefix}-{py_version}{arch}"
                results[f"{image_name}/{tag}"] = executor.submit(fetch_manifest_time, image_name, tag, token)
    
    for tag, fut in results.items():
        results[tag] = fut.result()
    return results

def find_commit_of_age(age=timedelta(hours=4)) -> Tuple[str, datetime]:
    """
    Finds the first commit that was made at least `age` time before now.
    """
    recent_commits = get_latest_commit()
    now = datetime.now(tz=pytz.utc)
    for commit in recent_commits:
        # GitHub commits use UTC time
        created_at = datetime.fromtimestamp(commit.unix_time_s, tz=pytz.utc)
        if (now - age) > created_at:
            return (commit.sha, created_at)



def check_recent_commits_have_docker_build() -> List[str]:
    # We want to choose a commit that is old enough to have a completed
    # Docker build. We need to tie this to a commit because Docker images
    # are only built per commit (e.g. there may be no images built for 
    # 48 hours over a weekend if there are no commits).
    sha, commit_time = find_commit_of_age(MAX_TIME_FOR_DOCKER_BUILD)
    all_images =  check_last_updated_for_repo("ray")
    all_images.update(check_last_updated_for_repo("ray-ml"))
    failed = []
    for tag, date in all_images.items():
        if date < commit_time:
            failed.append(f"- `{tag}` did not build for SHA: `{sha}`")
    if len(failed) == 0:
        return []
    lines = [
        "🐳 Your Docker Build Failure Report", 
    ]
    lines.extend(failed)
    return lines
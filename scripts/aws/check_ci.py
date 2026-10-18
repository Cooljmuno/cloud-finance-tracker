"""Require successful main-branch CI before obtaining AWS credentials."""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from common import DeploymentError

REQUIRED_JOBS = {"backend", "frontend", "containers", "infrastructure"}


def github_request(path):
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "cloud-finance-tracker-deployment",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request("https://api.github.com" + path, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as error:
        raise DeploymentError("Cannot verify GitHub CI; deployment is blocked.") from error


def check_ci(repository, sha, request_json=github_request):
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise DeploymentError("Repository must be OWNER/REPOSITORY.")
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise DeploymentError("Deployment SHA must be a full lowercase 40-character commit SHA.")
    query = urllib.parse.urlencode(
        {"branch": "main", "event": "push", "head_sha": sha, "per_page": 100}
    )
    result = request_json(f"/repos/{repository}/actions/workflows/ci.yml/runs?{query}")
    if not isinstance(result, dict) or not isinstance(result.get("workflow_runs"), list):
        raise DeploymentError("GitHub returned an invalid CI run list.")
    candidates = [
        run
        for run in result["workflow_runs"]
        if isinstance(run, dict)
        and run.get("head_sha") == sha
        and run.get("head_branch") == "main"
        and run.get("event") == "push"
        and run.get("path") == ".github/workflows/ci.yml"
        and run.get("head_repository", {}).get("full_name", "").casefold() == repository.casefold()
        and type(run.get("id")) is int
    ]
    if not candidates:
        raise DeploymentError(
            "No CI push run from this repository's main branch matches this commit."
        )
    run = max(candidates, key=lambda item: item["id"])
    if run.get("status") != "completed" or run.get("conclusion") != "success":
        raise DeploymentError("The latest matching CI run has not completed successfully.")
    result = request_json(
        f"/repos/{repository}/actions/runs/{run['id']}/jobs?filter=latest&per_page=100"
    )
    if (
        not isinstance(result, dict)
        or not isinstance(result.get("jobs"), list)
        or result.get("total_count", 0) > 100
    ):
        raise DeploymentError("Cannot verify the required CI jobs.")
    jobs = {item.get("name"): item for item in result["jobs"] if isinstance(item, dict)}
    if any(
        name not in jobs
        or jobs[name].get("status") != "completed"
        or jobs[name].get("conclusion") != "success"
        for name in REQUIRED_JOBS
    ):
        raise DeploymentError(
            "Backend, frontend, containers, and infrastructure CI jobs must all pass."
        )
    return run["id"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args()
    try:
        run_id = check_ci(args.repository, args.sha)
    except DeploymentError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Verified successful main-branch CI run {run_id} for {args.sha}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

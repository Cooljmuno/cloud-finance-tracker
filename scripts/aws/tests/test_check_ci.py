import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from check_ci import REQUIRED_JOBS, check_ci
from common import DeploymentError

SHA = "a" * 40
REPOSITORY = "Cooljmuno/cloud-finance-tracker"


def ci_run():
    return {
        "id": 123,
        "head_sha": SHA,
        "head_branch": "main",
        "event": "push",
        "path": ".github/workflows/ci.yml",
        "head_repository": {"full_name": REPOSITORY},
        "status": "completed",
        "conclusion": "success",
    }


def ci_jobs():
    return {
        "jobs": [
            {"name": name, "status": "completed", "conclusion": "success"}
            for name in sorted(REQUIRED_JOBS)
        ]
    }


class CiGateTests(unittest.TestCase):
    def request(self, runs=None, jobs=None):
        responses = [
            {"workflow_runs": runs if runs is not None else [ci_run()]},
            jobs if jobs is not None else ci_jobs(),
        ]
        calls = []

        def get(path):
            calls.append(path)
            return copy.deepcopy(responses.pop(0))

        return get, calls

    def test_success_requires_exact_main_push_commit_and_all_jobs(self):
        get, calls = self.request()
        self.assertEqual(check_ci(REPOSITORY, SHA, get), 123)
        self.assertIn("head_sha=" + SHA, calls[0])
        self.assertIn("branch=main", calls[0])
        self.assertIn("event=push", calls[0])
        self.assertIn("/actions/runs/123/jobs?filter=latest", calls[1])

    def test_other_branch_fork_event_workflow_or_commit_cannot_authorize(self):
        for key, value in {
            "head_sha": "b" * 40,
            "head_branch": "feature",
            "event": "pull_request",
            "path": ".github/workflows/other.yml",
            "head_repository": {"full_name": "attacker/cloud-finance-tracker"},
        }.items():
            get, calls = self.request(runs=[{**ci_run(), key: value}])
            with self.subTest(key=key), self.assertRaises(DeploymentError):
                check_ci(REPOSITORY, SHA, get)
            self.assertEqual(len(calls), 1)

    def test_failed_or_pending_latest_run_blocks_older_success(self):
        for status, conclusion in (
            ("completed", "failure"),
            ("in_progress", None),
            ("completed", "cancelled"),
        ):
            run = {**ci_run(), "id": 124, "status": status, "conclusion": conclusion}
            get, _ = self.request(runs=[ci_run(), run])
            with (
                self.subTest(status=status, conclusion=conclusion),
                self.assertRaises(DeploymentError),
            ):
                check_ci(REPOSITORY, SHA, get)

    def test_skipped_missing_or_failed_required_job_blocks_deployment(self):
        for conclusion in ("skipped", "failure", "cancelled", None):
            jobs = ci_jobs()
            jobs["jobs"][0]["conclusion"] = conclusion
            get, _ = self.request(jobs=jobs)
            with self.subTest(conclusion=conclusion), self.assertRaises(DeploymentError):
                check_ci(REPOSITORY, SHA, get)
        jobs = ci_jobs()
        jobs["jobs"].pop()
        get, _ = self.request(jobs=jobs)
        with self.assertRaises(DeploymentError):
            check_ci(REPOSITORY, SHA, get)

    def test_no_matching_run_or_invalid_api_response_is_not_a_pass(self):
        for response in ({"workflow_runs": []}, {}, {"workflow_runs": "invalid"}):
            with self.subTest(response=response), self.assertRaises(DeploymentError):
                check_ci(REPOSITORY, SHA, lambda path, response=response: response)

    def test_short_sha_and_untrusted_repository_path_are_rejected_before_http(self):
        for repository, sha in (
            (REPOSITORY, "abcdef"),
            ("owner/repo/../../other", SHA),
            (REPOSITORY, "A" * 40),
        ):

            def forbidden(path):
                self.fail("Invalid request must not contact GitHub")

            with self.subTest(repository=repository, sha=sha), self.assertRaises(DeploymentError):
                check_ci(repository, sha, forbidden)


if __name__ == "__main__":
    unittest.main()

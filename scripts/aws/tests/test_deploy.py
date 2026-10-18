import copy
import json
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import deploy
from common import (
    AwsCli,
    AwsCommandError,
    DeploymentError,
    register_task,
    run_task,
    validate_config,
)

SHA = "a" * 40
DIGEST = "sha256:" + "b" * 64


def deployment_config():
    account = "123456789012"
    region = "us-east-2"
    return {
        "schema_version": 1,
        "aws_account_id": account,
        "aws_region": region,
        "ecr_repository_url": f"{account}.dkr.ecr.{region}.amazonaws.com/finance-api",
        "ecs_cluster_name": "finance",
        "ecs_service_name": "finance-api",
        "ecs_task_family": "finance-api",
        "ecs_container_name": "backend",
        "task_definition_template_arn": (
            f"arn:aws:ecs:{region}:{account}:task-definition/finance-api:1"
        ),
        "task_execution_role_arn": f"arn:aws:iam::{account}:role/finance-execution",
        "task_role_arn": f"arn:aws:iam::{account}:role/finance-task",
        "github_deploy_role_arn": f"arn:aws:iam::{account}:role/finance-github",
        "db_bootstrap_execution_role_arn": f"arn:aws:iam::{account}:role/finance-bootstrap",
        "app_secret_arn": f"arn:aws:secretsmanager:{region}:{account}:secret:finance-app-abcdef",
        "db_master_secret_arn": f"arn:aws:secretsmanager:{region}:{account}:secret:rds!db-master",
        "task_subnet_ids": ["subnet-12345678", "subnet-87654321"],
        "task_security_group_ids": ["sg-12345678"],
        "assign_public_ip": True,
        "frontend_bucket_name": "finance-frontend-123456789012",
        "cloudfront_distribution_id": "E1234567890ABC",
        "frontend_url": "https://d123example.cloudfront.net",
        "api_url": "https://d123example.cloudfront.net/api/v1",
        "cognito_region": region,
        "cognito_user_pool_id": "us-east-2_ABC123",
        "cognito_app_client_id": "abc123456789",
        "cognito_domain": "https://finance-123.auth.us-east-2.amazoncognito.com",
        "db_host": "finance.abc123.us-east-2.rds.amazonaws.com",
        "db_name": "finance_tracker",
        "db_master_username": "finance_admin",
        "db_app_username": "finance_app",
    }


def task_template(config):
    return {
        "family": config["ecs_task_family"],
        "taskDefinitionArn": config["task_definition_template_arn"],
        "revision": 1,
        "status": "ACTIVE",
        "registeredAt": "2026-10-18T00:00:00Z",
        "networkMode": "awsvpc",
        "requiresCompatibilities": ["FARGATE"],
        "taskRoleArn": config["task_role_arn"],
        "executionRoleArn": config["task_execution_role_arn"],
        "cpu": "256",
        "memory": "512",
        "containerDefinitions": [
            {
                "name": config["ecs_container_name"],
                "image": config["ecr_repository_url"] + ":bootstrap",
                "environment": [{"name": "POSTGRES_USER", "value": "finance_app"}],
                "secrets": [
                    {
                        "name": "POSTGRES_PASSWORD",
                        "valueFrom": config["app_secret_arn"] + ":POSTGRES_PASSWORD::",
                    }
                ],
            }
        ],
    }


class StubAws:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, *args, payload=None):
        self.calls.append((args, payload))
        if not self.responses:
            raise AssertionError(f"Unexpected AWS call: {args}")
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return copy.deepcopy(response)


class DeploymentTests(unittest.TestCase):
    def setUp(self):
        self.config = deployment_config()
        self.revision = self.config["task_definition_template_arn"].rsplit(":", 1)[0] + ":2"
        self.task = f"arn:aws:ecs:us-east-2:123456789012:task/finance/{'c' * 32}"

    def test_configuration_rejects_cross_account_and_malformed_metadata(self):
        self.assertEqual(validate_config(self.config), self.config)
        for key, value in {
            "schema_version": True,
            "task_execution_role_arn": "arn:aws:iam::999999999999:role/other",
            "task_definition_template_arn": self.revision.replace("finance-api", "other"),
            "ecr_repository_url": "999999999999.dkr.ecr.us-east-2.amazonaws.com/finance-api",
            "api_url": "https://attacker.invalid/api/v1",
            "assign_public_ip": "true",
            "task_subnet_ids": [{}],
            "db_app_username": "postgres",
        }.items():
            with self.subTest(key=key), self.assertRaises(DeploymentError):
                validate_config({**self.config, key: value})

    def assert_private_request(self, command, kwargs, payload):
        uri = command[command.index("--cli-input-json") + 1]
        self.assertTrue(uri.startswith("file:///"))
        self.assertNotEqual(uri, "file:///dev/stdin")
        request = Path(uri.removeprefix("file://"))
        self.assertEqual(stat.S_IMODE(request.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(request.parent.stat().st_mode), 0o700)
        self.assertEqual(json.loads(request.read_text()), payload)
        self.assertNotIn("input", kwargs)
        self.assertNotIn(payload["SecretString"], " ".join(command))
        return request

    def test_aws_payload_uses_closed_private_file_and_deletes_it_after_success(self):
        secret = "synthetic-private-secret"
        payload = {"SecretString": secret}
        paths = []
        writers = []
        temporary_file = tempfile.NamedTemporaryFile

        def track_writer(*args, **kwargs):
            writer = temporary_file(*args, **kwargs)
            writers.append(writer)
            return writer

        def run(command, **kwargs):
            paths.append(self.assert_private_request(command, kwargs, payload))
            self.assertTrue(all(writer.closed for writer in writers))
            return subprocess.CompletedProcess(command, 0, '{"ok":true}', "")

        with (
            patch("common.tempfile.NamedTemporaryFile", side_effect=track_writer),
            patch("common.subprocess.run", side_effect=run),
        ):
            self.assertEqual(
                AwsCli("us-east-2").run("secretsmanager", "put-secret-value", payload=payload),
                {"ok": True},
            )
        self.assertEqual(len(paths), 1)
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())

    def test_aws_error_deletes_private_payload_and_hides_secret_values(self):
        secret = "synthetic-private-secret"
        payload = {"SecretString": secret}
        paths = []

        def run(command, **kwargs):
            paths.append(self.assert_private_request(command, kwargs, payload))
            return subprocess.CompletedProcess(
                command, 1, "", f"An error occurred (AccessDeniedException) secret={secret}"
            )

        with patch("common.subprocess.run", side_effect=run):
            with self.assertRaises(AwsCommandError) as raised:
                AwsCli("us-east-2").run("secretsmanager", "put-secret-value", payload=payload)
        self.assertNotIn(secret, str(raised.exception))
        self.assertEqual(raised.exception.error_code, "AccessDeniedException")
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())

    def test_spawn_error_deletes_private_payload_and_hides_secret_values(self):
        secret = "synthetic-private-secret"
        payload = {"SecretString": secret}
        paths = []

        def run(command, **kwargs):
            paths.append(self.assert_private_request(command, kwargs, payload))
            raise OSError(f"Cannot start process: {secret}")

        with patch("common.subprocess.run", side_effect=run):
            with self.assertRaises(DeploymentError) as raised:
                AwsCli("us-east-2").run("secretsmanager", "put-secret-value", payload=payload)
        self.assertNotIn(secret, str(raised.exception))
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())

    def test_invalid_json_response_leaves_no_private_payload(self):
        payload = {"SecretString": "synthetic-private-secret"}
        paths = []

        def run(command, **kwargs):
            paths.append(self.assert_private_request(command, kwargs, payload))
            return subprocess.CompletedProcess(command, 0, "invalid JSON", "")

        with patch("common.subprocess.run", side_effect=run):
            with self.assertRaises(DeploymentError):
                AwsCli("us-east-2").run("secretsmanager", "put-secret-value", payload=payload)
        self.assertFalse(paths[0].exists())
        self.assertFalse(paths[0].parent.exists())

    def test_high_level_s3_output_is_not_parsed_as_json(self):
        with patch(
            "common.subprocess.run",
            return_value=subprocess.CompletedProcess(
                [], 0, "upload: index.html to s3://example/index.html", ""
            ),
        ):
            self.assertIsNone(
                AwsCli("us-east-2").run("s3", "cp", "index.html", "s3://example/index.html")
            )

    def test_existing_commit_image_is_reused_without_docker(self):
        aws = StubAws([{"imageDetails": [{"imageDigest": DIGEST, "imageTags": [SHA]}]}])
        runner = Mock()
        self.assertEqual(
            deploy.release_image(aws, self.config, SHA, runner),
            self.config["ecr_repository_url"] + "@" + DIGEST,
        )
        runner.assert_not_called()

    def test_missing_commit_image_is_built_for_fargate_then_resolved(self):
        aws = StubAws(
            [
                AwsCommandError("ecr describe-images", error_code="ImageNotFoundException"),
                {"imageDetails": [{"imageDigest": DIGEST, "imageTags": [SHA]}]},
            ]
        )
        runner = Mock()
        deploy.release_image(aws, self.config, SHA, runner)
        build = runner.call_args_list[0].args[0]
        self.assertIn("linux/amd64", build)
        self.assertIn("production", build)
        self.assertEqual(runner.call_args_list[1].args[0][:2], ["docker", "push"])
        self.assertEqual(len(aws.calls), 2)

    def test_image_permission_errors_and_invalid_digests_abort(self):
        for response in (
            AwsCommandError("ecr describe-images", error_code="AccessDeniedException"),
            {"imageDetails": [{"imageDigest": "sha256:wrong", "imageTags": [SHA]}]},
            {"imageDetails": [{"imageDigest": DIGEST, "imageTags": ["other"]}]},
        ):
            with self.subTest(response=response), self.assertRaises(DeploymentError):
                deploy.release_image(StubAws([response]), self.config, SHA, Mock())

    def test_candidate_uses_digest_and_strips_read_only_template_fields(self):
        aws = StubAws(
            [
                {"taskDefinition": task_template(self.config)},
                {"taskDefinition": {"taskDefinitionArn": self.revision}},
            ]
        )
        image = self.config["ecr_repository_url"] + "@" + DIGEST
        self.assertEqual(register_task(aws, self.config, image=image), self.revision)
        payload = aws.calls[1][1]
        self.assertEqual(payload["containerDefinitions"][0]["image"], image)
        self.assertNotIn("registeredAt", payload)
        self.assertNotIn("taskDefinitionArn", payload)
        self.assertNotIn("revision", payload)

    def test_bootstrap_role_and_secret_overrides_do_not_keep_plaintext_password(self):
        aws = StubAws(
            [
                {"taskDefinition": task_template(self.config)},
                {"taskDefinition": {"taskDefinitionArn": self.revision}},
            ]
        )
        register_task(
            aws,
            self.config,
            execution_role=self.config["db_bootstrap_execution_role_arn"],
            environment={"POSTGRES_USER": "finance_admin"},
            secrets={"POSTGRES_PASSWORD": self.config["db_master_secret_arn"] + ":password::"},
        )
        payload = aws.calls[1][1]
        self.assertEqual(
            payload["executionRoleArn"], self.config["db_bootstrap_execution_role_arn"]
        )
        container = payload["containerDefinitions"][0]
        self.assertNotIn("POSTGRES_PASSWORD", {item["name"] for item in container["environment"]})
        self.assertEqual(
            container["secrets"][0]["valueFrom"],
            self.config["db_master_secret_arn"] + ":password::",
        )

    def test_wrong_template_role_or_revision_aborts_registration(self):
        template = task_template(self.config)
        template["taskRoleArn"] = "arn:aws:iam::123456789012:role/unexpected"
        aws = StubAws([{"taskDefinition": template}])
        with self.assertRaises(DeploymentError):
            register_task(aws, self.config)
        self.assertEqual(len(aws.calls), 1)
        aws = StubAws(
            [
                {"taskDefinition": task_template(self.config)},
                {
                    "taskDefinition": {
                        "taskDefinitionArn": self.revision.replace("123456789012", "999999999999")
                    }
                },
            ]
        )
        with self.assertRaises(DeploymentError):
            register_task(aws, self.config)

    def test_one_off_task_requires_exit_zero_on_expected_container(self):
        for exit_code in (None, 1, False):
            result = {
                "tasks": [
                    {
                        "lastStatus": "STOPPED",
                        "containers": [{"name": "backend", "exitCode": exit_code}],
                    }
                ]
            }
            aws = StubAws([{"tasks": [{"taskArn": self.task}]}, None, result])
            with self.subTest(exit_code=exit_code), self.assertRaises(DeploymentError):
                run_task(
                    aws, self.config, self.revision, ["python", "manage.py", "migrate", "--noinput"]
                )
        aws = StubAws(
            [
                {"tasks": [{"taskArn": self.task}]},
                None,
                {
                    "tasks": [
                        {
                            "lastStatus": "STOPPED",
                            "containers": [{"name": "backend", "exitCode": 0}],
                        }
                    ]
                },
            ]
        )
        self.assertEqual(
            run_task(
                aws, self.config, self.revision, ["python", "manage.py", "migrate", "--noinput"]
            ),
            self.task,
        )
        self.assertEqual(
            aws.calls[0][1]["networkConfiguration"]["awsvpcConfiguration"]["assignPublicIp"],
            "ENABLED",
        )

    def test_one_off_launch_failures_or_missing_task_abort(self):
        for response in (
            {"failures": [{"reason": "RESOURCE"}], "tasks": []},
            {"tasks": []},
            {"tasks": [{"taskArn": self.task}], "failures": [{"reason": "partial"}]},
        ):
            aws = StubAws([response])
            with self.subTest(response=response), self.assertRaises(DeploymentError):
                run_task(
                    aws, self.config, self.revision, ["python", "manage.py", "migrate", "--noinput"]
                )
            self.assertEqual(len(aws.calls), 1)

    def test_one_off_timeout_attempts_stop_and_never_assumes_success(self):
        aws = StubAws([{"tasks": [{"taskArn": self.task}]}, AwsCommandError("ecs wait", 255), {}])
        with self.assertRaises(DeploymentError):
            run_task(
                aws, self.config, self.revision, ["python", "manage.py", "migrate", "--noinput"]
            )
        self.assertEqual(aws.calls[-1][0][:2], ("ecs", "stop-task"))

    def test_one_off_cross_account_revision_is_rejected_before_aws(self):
        aws = StubAws([])
        with self.assertRaises(DeploymentError):
            run_task(
                aws,
                self.config,
                self.revision.replace("123456789012", "999999999999"),
                ["python", "manage.py", "migrate"],
            )
        self.assertEqual(aws.calls, [])

    def test_circuit_breaker_rollback_is_detected_after_waiter_succeeds(self):
        previous = self.config["task_definition_template_arn"]
        aws = StubAws(
            [
                {},
                None,
                {
                    "services": [
                        {
                            "taskDefinition": previous,
                            "desiredCount": 1,
                            "runningCount": 1,
                            "deployments": [
                                {
                                    "status": "PRIMARY",
                                    "taskDefinition": previous,
                                    "rolloutState": "COMPLETED",
                                }
                            ],
                        }
                    ]
                },
            ]
        )
        with self.assertRaisesRegex(DeploymentError, "rolled back"):
            deploy.update_service(aws, self.config, self.revision)

    def test_candidate_service_must_be_completed_and_running(self):
        service = {
            "taskDefinition": self.revision,
            "desiredCount": 1,
            "runningCount": 1,
            "deployments": [
                {"status": "PRIMARY", "taskDefinition": self.revision, "rolloutState": "COMPLETED"}
            ],
        }
        deploy.update_service(
            StubAws([{}, None, {"services": [service]}]), self.config, self.revision
        )
        for key, value in (("desiredCount", 0), ("runningCount", 0), ("deployments", [])):
            with self.subTest(key=key), self.assertRaises(DeploymentError):
                deploy.update_service(
                    StubAws([{}, None, {"services": [{**service, key: value}]}]),
                    self.config,
                    self.revision,
                )

    def test_wrong_account_blocks_all_mutations(self):
        aws = StubAws([{"Account": "999999999999"}])
        with self.assertRaises(DeploymentError):
            deploy.deploy(self.config, SHA, aws, Mock())
        self.assertEqual(aws.calls[0][0], ("sts", "get-caller-identity"))
        self.assertEqual(len(aws.calls), 1)

    def test_uninitialized_secret_blocks_release(self):
        aws = StubAws([{"Account": self.config["aws_account_id"]}, {"VersionIdsToStages": {}}])
        with self.assertRaisesRegex(DeploymentError, "bootstrap"):
            deploy.deploy(self.config, SHA, aws, Mock())
        self.assertEqual(len(aws.calls), 2)

    def test_failed_migration_never_updates_service_or_builds_frontend(self):
        aws = StubAws(
            [
                {"Account": self.config["aws_account_id"]},
                {"VersionIdsToStages": {"version": ["AWSCURRENT"]}},
            ]
        )
        with (
            patch(
                "deploy.release_image",
                return_value=self.config["ecr_repository_url"] + "@" + DIGEST,
            ),
            patch("deploy.register_task", return_value=self.revision),
            patch("deploy.run_task", side_effect=DeploymentError("Migration failed")),
            patch("deploy.update_service") as update,
            patch("deploy.build_frontend") as frontend,
        ):
            with self.assertRaises(DeploymentError):
                deploy.deploy(self.config, SHA, aws)
        update.assert_not_called()
        frontend.assert_not_called()

    def test_frontend_receives_same_origin_api_and_pkce_configuration(self):
        runner = Mock()
        deploy.build_frontend(self.config, runner)
        environment = runner.call_args_list[1].kwargs["env"]
        self.assertEqual(environment["VITE_API_BASE_URL"], self.config["api_url"])
        self.assertEqual(environment["VITE_AUTH_MODE"], "cognito")
        self.assertEqual(
            environment["VITE_COGNITO_REDIRECT_URI"], self.config["frontend_url"] + "/"
        )

    def test_frontend_publishes_assets_before_index_without_deleting_previous_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text("<html></html>")
            aws = StubAws([None, None, None, {"Invalidation": {"Id": "I123ABC"}}, None])
            deploy.publish_frontend(aws, self.config, dist)
        commands = [args for args, _ in aws.calls]
        self.assertEqual(commands[0][:2], ("s3", "sync"))
        self.assertIn("public,max-age=31536000,immutable", commands[0])
        self.assertIn("index.html", commands[1])
        self.assertEqual(commands[2][:2], ("s3", "cp"))
        self.assertIn("no-store", commands[2])
        self.assertTrue(all("--delete" not in command for command in commands))
        self.assertEqual(commands[3][:2], ("cloudfront", "create-invalidation"))
        self.assertEqual(commands[4][:3], ("cloudfront", "wait", "invalidation-completed"))

    def test_asset_upload_failure_does_not_replace_index(self):
        with tempfile.TemporaryDirectory() as directory:
            dist = Path(directory)
            (dist / "assets").mkdir()
            (dist / "index.html").write_text("<html></html>")
            aws = StubAws([AwsCommandError("s3 sync")])
            with self.assertRaises(DeploymentError):
                deploy.publish_frontend(aws, self.config, dist)
        self.assertEqual(len(aws.calls), 1)


if __name__ == "__main__":
    unittest.main()

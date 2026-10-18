import copy
import io
import json
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import bootstrap_environment as bootstrap_script  # noqa: E402
from common import AwsCommandError, DeploymentError  # noqa: E402


def configuration():
    account = "123456789012"
    region = "us-east-2"
    role_prefix = f"arn:aws:iam::{account}:role/"
    secret_prefix = f"arn:aws:secretsmanager:{region}:{account}:secret:"
    return {
        "schema_version": 1,
        "aws_region": region,
        "aws_account_id": account,
        "ecr_repository_url": f"{account}.dkr.ecr.{region}.amazonaws.com/finance-api",
        "ecs_cluster_name": "finance",
        "ecs_service_name": "finance-api",
        "ecs_task_family": "finance-api",
        "ecs_container_name": "backend",
        "task_definition_template_arn": (
            f"arn:aws:ecs:{region}:{account}:task-definition/finance-api:1"
        ),
        "task_execution_role_arn": role_prefix + "finance-execution",
        "task_role_arn": role_prefix + "finance-task",
        "task_subnet_ids": ["subnet-12345678"],
        "task_security_group_ids": ["sg-12345678"],
        "assign_public_ip": True,
        "frontend_bucket_name": "finance-web-123456789012",
        "cloudfront_distribution_id": "E1234567890123",
        "frontend_url": "https://d123example.cloudfront.net",
        "api_url": "https://d123example.cloudfront.net/api/v1",
        "cognito_region": region,
        "cognito_user_pool_id": "us-east-2_example",
        "cognito_app_client_id": "exampleclient123",
        "cognito_domain": "https://finance-123.auth.us-east-2.amazoncognito.com",
        "github_deploy_role_arn": role_prefix + "finance-deploy",
        "app_secret_arn": secret_prefix + "finance-app-abcdef",
        "db_master_secret_arn": secret_prefix + "rds-master-abcdef",
        "db_bootstrap_execution_role_arn": role_prefix + "finance-bootstrap-execution",
        "db_host": "finance.example.us-east-2.rds.amazonaws.com",
        "db_name": "finance",
        "db_master_username": "finance_admin",
        "db_app_username": "finance_app",
    }


def existing_secret():
    return {
        "SecretString": json.dumps(
            {
                "POSTGRES_PASSWORD": "existing-password-retained-with-0123456789",
                "DJANGO_SECRET_KEY": (
                    "existing-django-key-retained-with-0123456789-abcdefghijklmnopqrstuvwxyz"
                ),
            }
        )
    }


class FakeAws:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def run(self, *args, payload=None):
        self.calls.append((args, copy.deepcopy(payload)))
        if not self.responses:
            raise AssertionError(f"Unexpected AWS operation {args[:2]}")
        operation, result = self.responses.pop(0)
        if args[: len(operation)] != operation:
            raise AssertionError(f"Expected {operation}, received {args[:2]}")
        if isinstance(result, Exception):
            raise result
        return copy.deepcopy(result)


def current_responses():
    return [
        (
            ("secretsmanager", "describe-secret"),
            {"VersionIdsToStages": {"current": ["AWSCURRENT"]}},
        ),
        (("secretsmanager", "get-secret-value"), existing_secret()),
    ]


def template(config):
    return {
        "taskDefinition": {
            "taskDefinitionArn": config["task_definition_template_arn"],
            "revision": 1,
            "status": "ACTIVE",
            "family": config["ecs_task_family"],
            "taskRoleArn": config["task_role_arn"],
            "executionRoleArn": config["task_execution_role_arn"],
            "networkMode": "awsvpc",
            "requiresCompatibilities": ["FARGATE"],
            "cpu": "256",
            "memory": "512",
            "containerDefinitions": [
                {
                    "name": config["ecs_container_name"],
                    "image": config["ecr_repository_url"] + ":bootstrap",
                    "environment": [
                        {"name": "DJANGO_SETTINGS_MODULE", "value": "config.settings.production"},
                        {"name": "POSTGRES_USER", "value": "finance_app"},
                    ],
                    "secrets": [
                        {
                            "name": "POSTGRES_PASSWORD",
                            "valueFrom": config["app_secret_arn"] + ":POSTGRES_PASSWORD::",
                        }
                    ],
                }
            ],
        }
    }


class BootstrapSecretTests(unittest.TestCase):
    def setUp(self):
        self.config = configuration()

    def test_existing_secret_is_validated_and_never_rotated(self):
        aws = FakeAws(current_responses())
        bootstrap_script.ensure_app_secret(aws, self.config)
        self.assertEqual(len(aws.calls), 2)
        self.assertFalse(aws.responses)

    def test_empty_secret_is_generated_only_in_cli_input(self):
        aws = FakeAws(
            [
                (("secretsmanager", "describe-secret"), {}),
                (("secretsmanager", "put-secret-value"), {"VersionId": "initial"}),
                (("secretsmanager", "get-secret-value"), existing_secret()),
            ]
        )
        bootstrap_script.ensure_app_secret(aws, self.config)
        args, payload = aws.calls[1]
        self.assertEqual(args, ("secretsmanager", "put-secret-value"))
        self.assertEqual(payload["SecretId"], self.config["app_secret_arn"])
        self.assertEqual(payload["VersionStages"], ["AWSCURRENT"])
        self.assertEqual(len(payload["ClientRequestToken"]), 64)
        bootstrap_script.validate_app_secret(payload["SecretString"])
        self.assertNotIn(payload["SecretString"], repr(args))

    def test_concurrent_initializers_cannot_replace_first_generated_version(self):
        tokens = []
        for result in (
            {},
            AwsCommandError(
                "secretsmanager put-secret-value", error_code="ResourceExistsException"
            ),
        ):
            aws = FakeAws(
                [
                    (("secretsmanager", "describe-secret"), {}),
                    (("secretsmanager", "put-secret-value"), result),
                    (("secretsmanager", "get-secret-value"), existing_secret()),
                ]
            )
            bootstrap_script.ensure_app_secret(aws, self.config)
            tokens.append(aws.calls[1][1]["ClientRequestToken"])
        self.assertEqual(tokens[0], tokens[1])

    def test_put_permissions_error_is_not_treated_as_concurrent_creation(self):
        aws = FakeAws(
            [
                (("secretsmanager", "describe-secret"), {}),
                (
                    ("secretsmanager", "put-secret-value"),
                    AwsCommandError(
                        "secretsmanager put-secret-value", error_code="AccessDeniedException"
                    ),
                ),
            ]
        )
        with self.assertRaises(AwsCommandError):
            bootstrap_script.ensure_app_secret(aws, self.config)
        self.assertEqual(len(aws.calls), 2)

    def test_versions_without_current_stage_are_not_replaced(self):
        aws = FakeAws(
            [
                (
                    ("secretsmanager", "describe-secret"),
                    {"VersionIdsToStages": {"old": ["AWSPREVIOUS"]}},
                ),
            ]
        )
        with self.assertRaisesRegex(DeploymentError, "restore it manually"):
            bootstrap_script.ensure_app_secret(aws, self.config)
        self.assertEqual(len(aws.calls), 1)

    def test_secret_scheduled_for_deletion_is_not_written(self):
        aws = FakeAws([(("secretsmanager", "describe-secret"), {"DeletedDate": "2026-10-18"})])
        with self.assertRaisesRegex(DeploymentError, "deletion"):
            bootstrap_script.ensure_app_secret(aws, self.config)

    def test_invalid_existing_values_fail_without_disclosing_or_rotating(self):
        for secret_value in (
            "not-json-confidential-value",
            "[]",
            "{}",
            json.dumps(
                {
                    "POSTGRES_PASSWORD": "weak-confidential-value",
                    "DJANGO_SECRET_KEY": "x" * 60,
                }
            ),
        ):
            with self.subTest(secret=secret_value):
                aws = FakeAws(
                    [
                        (
                            ("secretsmanager", "describe-secret"),
                            {"VersionIdsToStages": {"v": ["AWSCURRENT"]}},
                        ),
                        (("secretsmanager", "get-secret-value"), {"SecretString": secret_value}),
                    ]
                )
                with self.assertRaises(DeploymentError) as error:
                    bootstrap_script.ensure_app_secret(aws, self.config)
                self.assertNotIn("confidential-value", str(error.exception))
                self.assertEqual(len(aws.calls), 2)


class BootstrapTaskTests(unittest.TestCase):
    def setUp(self):
        self.config = configuration()
        self.image = self.config["ecr_repository_url"] + "@sha256:" + "a" * 64
        self.task_definition = self.config["task_definition_template_arn"].rsplit(":", 1)[0] + ":2"
        self.task_arn = "arn:aws:ecs:us-east-2:123456789012:task/finance/abc123"

    def responses(self, exit_code=0):
        return [
            (("sts", "get-caller-identity"), {"Account": self.config["aws_account_id"]}),
            (("ecr", "describe-images"), {"imageDetails": [{"imageDigest": "sha256:" + "a" * 64}]}),
            *current_responses(),
            (("ecs", "describe-task-definition"), template(self.config)),
            (
                ("ecs", "register-task-definition"),
                {"taskDefinition": {"taskDefinitionArn": self.task_definition}},
            ),
            (("ecs", "run-task"), {"tasks": [{"taskArn": self.task_arn}]}),
            (("ecs", "wait", "tasks-stopped"), None),
            (
                ("ecs", "describe-tasks"),
                {
                    "tasks": [
                        {
                            "lastStatus": "STOPPED",
                            "containers": [
                                {"name": "backend", "exitCode": exit_code},
                            ],
                        }
                    ]
                },
            ),
        ]

    def test_bootstrap_uses_master_only_in_temporary_execution_role(self):
        aws = FakeAws(self.responses())
        self.assertEqual(bootstrap_script.bootstrap(aws, self.config, self.image), self.task_arn)
        registration = next(
            payload
            for args, payload in aws.calls
            if args[:2] == ("ecs", "register-task-definition")
        )
        self.assertEqual(
            registration["executionRoleArn"], self.config["db_bootstrap_execution_role_arn"]
        )
        self.assertEqual(registration["taskRoleArn"], self.config["task_role_arn"])
        self.assertNotIn("revision", registration)
        container = registration["containerDefinitions"][0]
        self.assertEqual(container["image"], self.image)
        environment = {item["name"]: item["value"] for item in container["environment"]}
        self.assertEqual(environment["POSTGRES_USER"], "finance_admin")
        self.assertEqual(environment["ENABLE_DATABASE_BOOTSTRAP"], "true")
        secret_refs = {item["name"]: item["valueFrom"] for item in container["secrets"]}
        self.assertEqual(
            secret_refs["POSTGRES_PASSWORD"], self.config["db_master_secret_arn"] + ":password::"
        )
        self.assertEqual(
            secret_refs["APP_DATABASE_PASSWORD"],
            self.config["app_secret_arn"] + ":POSTGRES_PASSWORD::",
        )
        self.assertNotIn("existing-password", repr(registration))
        run_payload = next(
            payload for args, payload in aws.calls if args[:2] == ("ecs", "run-task")
        )
        self.assertEqual(
            run_payload["overrides"]["containerOverrides"][0]["command"],
            ["python", "manage.py", "bootstrap_database"],
        )
        self.assertFalse(any(args[:2] == ("ecs", "update-service") for args, _ in aws.calls))
        self.assertFalse(aws.responses)

    def test_failed_bootstrap_never_updates_service(self):
        aws = FakeAws(self.responses(exit_code=1))
        with self.assertRaisesRegex(DeploymentError, "failed"):
            bootstrap_script.bootstrap(aws, self.config, self.image)
        self.assertFalse(any(args[:2] == ("ecs", "update-service") for args, _ in aws.calls))

    def test_wrong_aws_account_is_rejected_before_secret_write(self):
        aws = FakeAws([(("sts", "get-caller-identity"), {"Account": "999999999999"})])
        with self.assertRaisesRegex(DeploymentError, "account"):
            bootstrap_script.bootstrap(aws, self.config, self.image)
        self.assertEqual(len(aws.calls), 1)

    def test_missing_bootstrap_image_is_rejected_before_secret_write(self):
        aws = FakeAws(
            [
                (("sts", "get-caller-identity"), {"Account": self.config["aws_account_id"]}),
                (("ecr", "describe-images"), {"imageDetails": []}),
            ]
        )
        with self.assertRaisesRegex(DeploymentError, "unavailable"):
            bootstrap_script.bootstrap(aws, self.config, self.image)
        self.assertEqual(len(aws.calls), 2)

    def test_mutable_or_foreign_image_is_rejected_before_any_aws_calls(self):
        for image in (
            self.config["ecr_repository_url"] + ":latest",
            "other.example/api@sha256:" + "a" * 64,
        ):
            aws = FakeAws([])
            with self.assertRaisesRegex(DeploymentError, "immutable image"):
                bootstrap_script.bootstrap(aws, self.config, image)
            self.assertFalse(aws.calls)

    def test_shared_master_identity_or_secret_is_rejected_before_any_aws_calls(self):
        pairs = [
            ("db_master_username", "db_app_username"),
            ("db_bootstrap_execution_role_arn", "task_execution_role_arn"),
            ("app_secret_arn", "db_master_secret_arn"),
        ]
        for changed, source in pairs:
            with self.subTest(key=changed):
                config = {**self.config, changed: self.config[source]}
                aws = FakeAws([])
                with self.assertRaises(DeploymentError):
                    bootstrap_script.bootstrap(aws, config, self.image)
                self.assertFalse(aws.calls)

    def test_cli_success_and_failure_output_does_not_show_secret_values(self):
        with (
            patch.object(bootstrap_script, "load_config", return_value=self.config),
            patch.object(bootstrap_script, "AwsCli"),
            patch.object(bootstrap_script, "bootstrap"),
        ):
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    bootstrap_script.main(["--config", "deployment.json", "--image", self.image]), 0
                )
            self.assertIn("service is unchanged", output.getvalue())
        with patch.object(
            bootstrap_script, "load_config", side_effect=DeploymentError("Invalid configuration.")
        ):
            error_output = io.StringIO()
            with redirect_stderr(error_output):
                self.assertEqual(
                    bootstrap_script.main(["--config", "deployment.json", "--image", self.image]), 1
                )
            self.assertIn("Bootstrap failed", error_output.getvalue())


if __name__ == "__main__":
    unittest.main()

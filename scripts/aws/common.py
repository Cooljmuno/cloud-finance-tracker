"""Shared AWS deployment operations; requires Python 3.11+ and AWS CLI v2."""

import copy
import json
import os
import re
import subprocess
import tempfile
from contextlib import ExitStack
from pathlib import Path


class DeploymentError(RuntimeError):
    pass


class AwsCommandError(DeploymentError):
    def __init__(self, operation, returncode=1, error_code=None):
        self.error_code = error_code
        super().__init__(f"AWS {operation} failed (exit {returncode}).")


class AwsCli:
    def __init__(self, region):
        self.region = region

    def run(self, *args, payload=None):
        command = ["aws", "--region", self.region, "--output", "json", "--no-cli-pager", *args]
        try:
            with ExitStack() as cleanup:
                if payload is not None:
                    directory = cleanup.enter_context(
                        tempfile.TemporaryDirectory(prefix="finance-aws-")
                    )
                    os.chmod(directory, 0o700)
                    with tempfile.NamedTemporaryFile(
                        mode="w", encoding="utf-8", dir=directory, delete=False
                    ) as request:
                        os.fchmod(request.fileno(), 0o600)
                        json.dump(payload, request)
                    command.extend(["--cli-input-json", f"file://{request.name}"])
                result = subprocess.run(
                    command,
                    text=True,
                    capture_output=True,
                    check=False,
                )
        except OSError as error:
            raise DeploymentError("AWS CLI v2 is required and must be on PATH.") from error
        if result.returncode:
            match = re.search(r"An error occurred \(([^)]+)\)", result.stderr)
            raise AwsCommandError(
                " ".join(args[:2]), result.returncode, match[1] if match else None
            )
        if args[0] == "s3" or not result.stdout.strip():
            return None
        try:
            return json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise DeploymentError(f"AWS {' '.join(args[:2])} returned invalid JSON.") from error


def _matches(value, pattern, name):
    if not isinstance(value, str) or re.fullmatch(pattern, value) is None:
        raise DeploymentError(f"Invalid deployment configuration: {name}.")
    return value


def validate_config(config):
    if not isinstance(config, dict) or type(config.get("schema_version")) is not int:
        raise DeploymentError("Deployment configuration must be a schema_version 1 JSON object.")
    if config["schema_version"] != 1:
        raise DeploymentError("Unsupported deployment configuration schema_version.")
    account = _matches(config.get("aws_account_id"), r"[0-9]{12}", "aws_account_id")
    region = _matches(config.get("aws_region"), r"[a-z]{2}-[a-z]+-[1-9]", "aws_region")
    family = _matches(config.get("ecs_task_family"), r"[A-Za-z0-9_-]{1,255}", "ecs_task_family")
    for key in ("ecs_cluster_name", "ecs_service_name", "ecs_container_name"):
        _matches(config.get(key), r"[A-Za-z0-9_-]{1,255}", key)
    _matches(
        config.get("ecr_repository_url"),
        rf"{account}\.dkr\.ecr\.{re.escape(region)}\.amazonaws\.com/[a-z0-9][a-z0-9._/-]*",
        "ecr_repository_url",
    )
    for key in (
        "task_execution_role_arn",
        "task_role_arn",
        "github_deploy_role_arn",
        "db_bootstrap_execution_role_arn",
    ):
        _matches(config.get(key), rf"arn:aws:iam::{account}:role/[A-Za-z0-9+=,.@_/-]+", key)
    _matches(
        config.get("task_definition_template_arn"),
        rf"arn:aws:ecs:{re.escape(region)}:{account}:task-definition/{re.escape(family)}:[1-9][0-9]*",
        "task_definition_template_arn",
    )
    for key in ("app_secret_arn", "db_master_secret_arn"):
        _matches(
            config.get(key),
            rf"arn:aws:secretsmanager:{re.escape(region)}:{account}:secret:[A-Za-z0-9/_+=.!@-]+",
            key,
        )
    for key, prefix in (("task_subnet_ids", "subnet"), ("task_security_group_ids", "sg")):
        values = config.get(key)
        if (
            not isinstance(values, list)
            or not values
            or not all(isinstance(value, str) for value in values)
            or len(values) != len(set(values))
        ):
            raise DeploymentError(f"Invalid deployment configuration: {key}.")
        for value in values:
            _matches(value, rf"{prefix}-(?:[0-9a-f]{{8}}|[0-9a-f]{{17}})", key)
    if config.get("assign_public_ip") is not True:
        raise DeploymentError(
            "This network requires assign_public_ip=true for task outbound access."
        )
    _matches(
        config.get("frontend_bucket_name"),
        r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]",
        "frontend_bucket_name",
    )
    _matches(
        config.get("cloudfront_distribution_id"), r"[A-Z0-9]{8,32}", "cloudfront_distribution_id"
    )
    frontend = _matches(
        config.get("frontend_url"), r"https://[a-z0-9]+\.cloudfront\.net", "frontend_url"
    )
    if config.get("api_url") != frontend + "/api/v1":
        raise DeploymentError("api_url must be the frontend URL followed by /api/v1.")
    if config.get("cognito_region") != region:
        raise DeploymentError("cognito_region must match aws_region.")
    _matches(
        config.get("cognito_user_pool_id"),
        rf"{re.escape(region)}_[A-Za-z0-9]+",
        "cognito_user_pool_id",
    )
    _matches(config.get("cognito_app_client_id"), r"[a-z0-9]{1,128}", "cognito_app_client_id")
    _matches(
        config.get("cognito_domain"),
        rf"https://[a-z0-9-]+\.auth\.{re.escape(region)}\.amazoncognito\.com",
        "cognito_domain",
    )
    _matches(
        config.get("db_host"), rf"[a-z0-9.-]+\.{re.escape(region)}\.rds\.amazonaws\.com", "db_host"
    )
    for key in ("db_name", "db_master_username"):
        _matches(config.get(key), r"[A-Za-z][A-Za-z0-9_]{0,62}", key)
    if config.get("db_app_username") != "finance_app":
        raise DeploymentError("db_app_username must be finance_app.")
    if config["db_master_username"] == config["db_app_username"]:
        raise DeploymentError("Application and administrator database users must differ.")
    if config["task_execution_role_arn"] == config["db_bootstrap_execution_role_arn"]:
        raise DeploymentError("Application and database bootstrap execution roles must differ.")
    if config["app_secret_arn"] == config["db_master_secret_arn"]:
        raise DeploymentError("Application and administrator secrets must differ.")
    return config


def load_config(path):
    try:
        config = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise DeploymentError("Cannot read deployment configuration JSON.") from error
    return validate_config(config)


def verify_account(aws, config):
    identity = aws.run("sts", "get-caller-identity")
    if not isinstance(identity, dict) or identity.get("Account") != config["aws_account_id"]:
        raise DeploymentError(
            "AWS identity does not match the configured account; no deployment performed."
        )


def register_task(aws, config, *, image=None, execution_role=None, environment=None, secrets=None):
    result = aws.run(
        "ecs",
        "describe-task-definition",
        "--task-definition",
        config["task_definition_template_arn"],
    )
    template = result.get("taskDefinition", {}) if isinstance(result, dict) else {}
    if (
        template.get("family") != config["ecs_task_family"]
        or template.get("taskRoleArn") != config["task_role_arn"]
        or template.get("executionRoleArn") != config["task_execution_role_arn"]
        or template.get("networkMode") != "awsvpc"
        or "FARGATE" not in template.get("requiresCompatibilities", [])
    ):
        raise DeploymentError(
            "Task template does not match the configured family, roles, or Fargate network."
        )
    allowed = {
        "family",
        "taskRoleArn",
        "executionRoleArn",
        "networkMode",
        "containerDefinitions",
        "volumes",
        "placementConstraints",
        "requiresCompatibilities",
        "cpu",
        "memory",
        "pidMode",
        "ipcMode",
        "proxyConfiguration",
        "inferenceAccelerators",
        "ephemeralStorage",
        "runtimePlatform",
        "enableFaultInjection",
    }
    candidate = copy.deepcopy({key: value for key, value in template.items() if key in allowed})
    containers = candidate.get("containerDefinitions", [])
    if len(containers) != 1 or containers[0].get("name") != config["ecs_container_name"]:
        raise DeploymentError(
            "Task template must contain exactly the configured application container."
        )
    container = containers[0]
    if image is not None:
        _matches(
            image, re.escape(config["ecr_repository_url"]) + r"@sha256:[0-9a-f]{64}", "image digest"
        )
        container["image"] = image
    if execution_role is not None:
        if execution_role not in (
            config["task_execution_role_arn"],
            config["db_bootstrap_execution_role_arn"],
        ):
            raise DeploymentError("Unrecognized task execution role.")
        candidate["executionRoleArn"] = execution_role
    merged_env = {item["name"]: item["value"] for item in container.get("environment", [])}
    merged_secrets = {item["name"]: item["valueFrom"] for item in container.get("secrets", [])}
    for key, value in (environment or {}).items():
        merged_env[key] = value
        merged_secrets.pop(key, None)
    for key, value in (secrets or {}).items():
        merged_secrets[key] = value
        merged_env.pop(key, None)
    container["environment"] = [
        {"name": key, "value": value} for key, value in sorted(merged_env.items())
    ]
    container["secrets"] = [
        {"name": key, "valueFrom": value} for key, value in sorted(merged_secrets.items())
    ]
    result = aws.run("ecs", "register-task-definition", payload=candidate)
    arn = (
        result.get("taskDefinition", {}).get("taskDefinitionArn")
        if isinstance(result, dict)
        else None
    )
    return _matches(
        arn,
        rf"arn:aws:ecs:{re.escape(config['aws_region'])}:{config['aws_account_id']}:task-definition/{re.escape(config['ecs_task_family'])}:[1-9][0-9]*",
        "registered task revision",
    )


def run_task(aws, config, task_definition, command):
    _matches(
        task_definition,
        rf"arn:aws:ecs:{re.escape(config['aws_region'])}:{config['aws_account_id']}:task-definition/{re.escape(config['ecs_task_family'])}:[1-9][0-9]*",
        "one-off task revision",
    )
    payload = {
        "cluster": config["ecs_cluster_name"],
        "taskDefinition": task_definition,
        "launchType": "FARGATE",
        "platformVersion": "1.4.0",
        "count": 1,
        "networkConfiguration": {
            "awsvpcConfiguration": {
                "subnets": config["task_subnet_ids"],
                "securityGroups": config["task_security_group_ids"],
                "assignPublicIp": "ENABLED" if config["assign_public_ip"] else "DISABLED",
            }
        },
        "overrides": {
            "containerOverrides": [{"name": config["ecs_container_name"], "command": command}]
        },
    }
    result = aws.run("ecs", "run-task", payload=payload)
    tasks = result.get("tasks", []) if isinstance(result, dict) else []
    if not isinstance(result, dict) or result.get("failures") or len(tasks) != 1:
        raise DeploymentError("One-off task could not be launched; service was not updated.")
    task_arn = _matches(
        tasks[0].get("taskArn"),
        rf"arn:aws:ecs:{re.escape(config['aws_region'])}:{config['aws_account_id']}:task/{re.escape(config['ecs_cluster_name'])}/[0-9a-f]+",
        "one-off task ARN",
    )
    try:
        aws.run(
            "ecs",
            "wait",
            "tasks-stopped",
            "--cluster",
            config["ecs_cluster_name"],
            "--tasks",
            task_arn,
        )
    except DeploymentError:
        try:
            aws.run(
                "ecs",
                "stop-task",
                "--cluster",
                config["ecs_cluster_name"],
                "--task",
                task_arn,
                "--reason",
                "One-off deployment task wait failed",
            )
        except DeploymentError:
            pass
        raise DeploymentError(
            "One-off task did not stop successfully; inspect its ECS logs before retrying."
        ) from None
    result = aws.run(
        "ecs", "describe-tasks", "--cluster", config["ecs_cluster_name"], "--tasks", task_arn
    )
    tasks = result.get("tasks", []) if isinstance(result, dict) else []
    if (
        not isinstance(result, dict)
        or result.get("failures")
        or len(tasks) != 1
        or tasks[0].get("lastStatus") != "STOPPED"
    ):
        raise DeploymentError(
            "One-off task completion could not be verified; service was not updated."
        )
    containers = [
        item
        for item in tasks[0].get("containers", [])
        if item.get("name") == config["ecs_container_name"]
    ]
    if (
        len(containers) != 1
        or type(containers[0].get("exitCode")) is not int
        or containers[0]["exitCode"] != 0
    ):
        raise DeploymentError(
            "One-off task failed or has no successful exit code; service was not updated."
        )
    return task_arn

"""Administrator-only initialization; never changes the running ECS service."""

import argparse
import hashlib
import json
import re
import secrets
import sys

from common import (
    AwsCli,
    AwsCommandError,
    DeploymentError,
    load_config,
    register_task,
    run_task,
    verify_account,
)


def validate_app_secret(value):
    try:
        data = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        raise DeploymentError("The existing application secret must contain valid JSON.") from None
    if not isinstance(data, dict):
        raise DeploymentError("The existing application secret must contain a JSON object.")
    for key, minimum in (("POSTGRES_PASSWORD", 32), ("DJANGO_SECRET_KEY", 50)):
        item = data.get(key)
        if (
            not isinstance(item, str)
            or len(item) < minimum
            or len(set(item)) < 5
            or "\x00" in item
            or (key == "DJANGO_SECRET_KEY" and item.startswith("django-insecure-"))
        ):
            raise DeploymentError(f"The application secret has a missing or weak {key} value.")


def read_app_secret(aws, secret_arn):
    result = aws.run(
        "secretsmanager",
        "get-secret-value",
        "--secret-id",
        secret_arn,
        "--version-stage",
        "AWSCURRENT",
    )
    if not isinstance(result, dict):
        raise DeploymentError("Cannot validate the current application secret.")
    validate_app_secret(result.get("SecretString"))


def ensure_app_secret(aws, config):
    secret_arn = config["app_secret_arn"]
    metadata = aws.run("secretsmanager", "describe-secret", "--secret-id", secret_arn)
    if not isinstance(metadata, dict) or metadata.get("DeletedDate"):
        raise DeploymentError(
            "Application secret metadata is unavailable or scheduled for deletion."
        )
    versions = metadata.get("VersionIdsToStages", {})
    if not isinstance(versions, dict) or any(
        not isinstance(stages, list) for stages in versions.values()
    ):
        raise DeploymentError("Application secret version metadata is invalid.")
    if any("AWSCURRENT" in stages for stages in versions.values()):
        read_app_secret(aws, secret_arn)
        return
    if versions:
        raise DeploymentError(
            "Application secret versions exist without AWSCURRENT; restore it manually."
        )

    initial_values = {
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "POSTGRES_PASSWORD": secrets.token_urlsafe(48),
    }
    request_token = hashlib.sha256(f"finance-bootstrap-v1:{secret_arn}".encode()).hexdigest()
    try:
        aws.run(
            "secretsmanager",
            "put-secret-value",
            payload={
                "SecretId": secret_arn,
                "SecretString": json.dumps(initial_values),
                "ClientRequestToken": request_token,
                "VersionStages": ["AWSCURRENT"],
            },
        )
    except AwsCommandError as error:
        if error.error_code != "ResourceExistsException":
            raise
    read_app_secret(aws, secret_arn)


def bootstrap(aws, config, image):
    if (
        not isinstance(image, str)
        or re.fullmatch(re.escape(config["ecr_repository_url"]) + r"@sha256:[0-9a-f]{64}", image)
        is None
    ):
        raise DeploymentError(
            "Bootstrap requires an immutable image digest from the configured ECR repository."
        )
    if config["db_master_username"] == config["db_app_username"]:
        raise DeploymentError("The administrator and application database users must be different.")
    if config["db_bootstrap_execution_role_arn"] == config["task_execution_role_arn"]:
        raise DeploymentError("Bootstrap requires a separate task execution role.")
    if config["app_secret_arn"] == config["db_master_secret_arn"]:
        raise DeploymentError("The application and administrator secrets must be different.")

    verify_account(aws, config)
    digest = image.split("@", 1)[1]
    image_result = aws.run(
        "ecr",
        "describe-images",
        "--repository-name",
        config["ecr_repository_url"].split("/", 1)[1],
        "--image-ids",
        f"imageDigest={digest}",
    )
    details = image_result.get("imageDetails", []) if isinstance(image_result, dict) else []
    if len(details) != 1 or details[0].get("imageDigest") != digest:
        raise DeploymentError(
            "The bootstrap image digest is unavailable in the configured ECR repository."
        )
    ensure_app_secret(aws, config)
    task_definition = register_task(
        aws,
        config,
        image=image,
        execution_role=config["db_bootstrap_execution_role_arn"],
        environment={
            "ENABLE_DATABASE_BOOTSTRAP": "true",
            "POSTGRES_HOST": config["db_host"],
            "POSTGRES_DB": config["db_name"],
            "POSTGRES_USER": config["db_master_username"],
        },
        secrets={
            "POSTGRES_PASSWORD": config["db_master_secret_arn"] + ":password::",
            "APP_DATABASE_PASSWORD": config["app_secret_arn"] + ":POSTGRES_PASSWORD::",
            "DJANGO_SECRET_KEY": config["app_secret_arn"] + ":DJANGO_SECRET_KEY::",
        },
    )
    return run_task(aws, config, task_definition, ["python", "manage.py", "bootstrap_database"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Terraform deployment_config JSON file.")
    parser.add_argument(
        "--image", required=True, help="Existing configured ECR repository@sha256:digest."
    )
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        bootstrap(AwsCli(config["aws_region"]), config, args.image)
    except DeploymentError as error:
        print(f"Bootstrap failed: {error}", file=sys.stderr)
        return 1
    print(
        "Application secrets and the restricted database role are ready. ECS service is unchanged."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())

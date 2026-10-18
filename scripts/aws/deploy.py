"""Deploy a CI-verified release; invoked by the protected GitHub production workflow."""

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from common import (
    AwsCli,
    AwsCommandError,
    DeploymentError,
    load_config,
    register_task,
    run_task,
    verify_account,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def run_command(command, *, cwd=REPOSITORY_ROOT, env=None):
    try:
        subprocess.run(command, cwd=cwd, env=env, check=True)
    except (OSError, subprocess.CalledProcessError) as error:
        raise DeploymentError(f"Release command failed: {command[0]}.") from error


def require_initialized_secret(aws, config):
    result = aws.run("secretsmanager", "describe-secret", "--secret-id", config["app_secret_arn"])
    versions = result.get("VersionIdsToStages", {}) if isinstance(result, dict) else {}
    if (
        not isinstance(result, dict)
        or result.get("DeletedDate")
        or not isinstance(versions, dict)
        or any(not isinstance(stages, list) for stages in versions.values())
    ):
        raise DeploymentError("Application secret metadata is invalid or scheduled for deletion.")
    if not any("AWSCURRENT" in stages for stages in versions.values()):
        raise DeploymentError(
            "Application secret is not initialized; complete the administrator bootstrap first."
        )


def release_image(aws, config, sha, runner=run_command):
    repository_url = config["ecr_repository_url"]
    repository_name = repository_url.split("/", 1)[1]
    try:
        result = aws.run(
            "ecr",
            "describe-images",
            "--repository-name",
            repository_name,
            "--image-ids",
            f"imageTag={sha}",
        )
    except AwsCommandError as error:
        if error.error_code != "ImageNotFoundException":
            raise
        result = None
    if result is None:
        runner(
            [
                "docker",
                "build",
                "--platform",
                "linux/amd64",
                "--target",
                "production",
                "--tag",
                f"{repository_url}:{sha}",
                "backend",
            ]
        )
        runner(["docker", "push", f"{repository_url}:{sha}"])
        result = aws.run(
            "ecr",
            "describe-images",
            "--repository-name",
            repository_name,
            "--image-ids",
            f"imageTag={sha}",
        )
    images = result.get("imageDetails", []) if isinstance(result, dict) else []
    if (
        len(images) != 1
        or re.fullmatch(r"sha256:[0-9a-f]{64}", images[0].get("imageDigest", "")) is None
    ):
        raise DeploymentError("ECR did not return one valid immutable release image digest.")
    if sha not in images[0].get("imageTags", []):
        raise DeploymentError("ECR image does not carry the requested commit tag.")
    return f"{repository_url}@{images[0]['imageDigest']}"


def update_service(aws, config, revision):
    aws.run(
        "ecs",
        "update-service",
        payload={
            "cluster": config["ecs_cluster_name"],
            "service": config["ecs_service_name"],
            "taskDefinition": revision,
            "desiredCount": 1,
        },
    )
    aws.run(
        "ecs",
        "wait",
        "services-stable",
        "--cluster",
        config["ecs_cluster_name"],
        "--services",
        config["ecs_service_name"],
    )
    result = aws.run(
        "ecs",
        "describe-services",
        "--cluster",
        config["ecs_cluster_name"],
        "--services",
        config["ecs_service_name"],
    )
    services = result.get("services", []) if isinstance(result, dict) else []
    if not isinstance(result, dict) or result.get("failures") or len(services) != 1:
        raise DeploymentError(
            "ECS service status could not be verified; frontend was not published."
        )
    service = services[0]
    primary = [item for item in service.get("deployments", []) if item.get("status") == "PRIMARY"]
    if (
        service.get("taskDefinition") != revision
        or len(primary) != 1
        or primary[0].get("taskDefinition") != revision
        or primary[0].get("rolloutState") != "COMPLETED"
        or service.get("desiredCount", 0) < 1
        or service.get("runningCount", 0) < service["desiredCount"]
    ):
        raise DeploymentError(
            "ECS did not complete the candidate release (it may have rolled back); "
            "frontend was not published."
        )


def build_frontend(config, runner=run_command):
    environment = {
        **os.environ,
        "VITE_AUTH_MODE": "cognito",
        "VITE_API_BASE_URL": config["api_url"],
        "VITE_COGNITO_ISSUER": f"https://cognito-idp.{config['cognito_region']}.amazonaws.com/{config['cognito_user_pool_id']}",
        "VITE_COGNITO_CLIENT_ID": config["cognito_app_client_id"],
        "VITE_COGNITO_DOMAIN": config["cognito_domain"],
        "VITE_COGNITO_REDIRECT_URI": config["frontend_url"] + "/",
        "VITE_COGNITO_LOGOUT_URI": config["frontend_url"] + "/",
    }
    runner(["npm", "ci"], cwd=REPOSITORY_ROOT / "frontend", env=environment)
    runner(["npm", "run", "build"], cwd=REPOSITORY_ROOT / "frontend", env=environment)
    return REPOSITORY_ROOT / "frontend" / "dist"


def publish_frontend(aws, config, dist):
    if not (dist / "index.html").is_file() or not (dist / "assets").is_dir():
        raise DeploymentError("Frontend build is missing index.html or its assets directory.")
    bucket = "s3://" + config["frontend_bucket_name"]
    aws.run(
        "s3",
        "sync",
        str(dist / "assets"),
        bucket + "/assets/",
        "--cache-control",
        "public,max-age=31536000,immutable",
        "--no-progress",
    )
    aws.run(
        "s3",
        "sync",
        str(dist),
        bucket + "/",
        "--exclude",
        "assets/*",
        "--exclude",
        "index.html",
        "--cache-control",
        "no-cache",
        "--no-progress",
    )
    aws.run(
        "s3",
        "cp",
        str(dist / "index.html"),
        bucket + "/index.html",
        "--content-type",
        "text/html",
        "--cache-control",
        "no-store",
        "--no-progress",
    )
    result = aws.run(
        "cloudfront",
        "create-invalidation",
        "--distribution-id",
        config["cloudfront_distribution_id"],
        "--paths",
        "/*",
    )
    invalidation = result.get("Invalidation", {}).get("Id") if isinstance(result, dict) else None
    if not isinstance(invalidation, str) or re.fullmatch(r"[A-Z0-9]+", invalidation) is None:
        raise DeploymentError("CloudFront did not return an invalidation ID.")
    aws.run(
        "cloudfront",
        "wait",
        "invalidation-completed",
        "--distribution-id",
        config["cloudfront_distribution_id"],
        "--id",
        invalidation,
    )


def deploy(config, sha, aws, runner=run_command):
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None:
        raise DeploymentError("Release SHA must be a full lowercase 40-character commit SHA.")
    verify_account(aws, config)
    require_initialized_secret(aws, config)
    image = release_image(aws, config, sha, runner)
    revision = register_task(aws, config, image=image)
    print("Running database migrations with the candidate image.")
    run_task(aws, config, revision, ["python", "manage.py", "migrate", "--noinput"])
    print("Waiting for the candidate API release to become healthy.")
    update_service(aws, config, revision)
    print("Building and publishing the frontend.")
    publish_frontend(aws, config, build_frontend(config, runner))
    return revision


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        config = load_config(args.config)
        if re.fullmatch(r"[0-9a-f]{40}", args.sha) is None:
            raise DeploymentError("Release SHA must be a full lowercase 40-character commit SHA.")
        if args.validate_only:
            print(
                json.dumps(
                    {
                        "aws_region": config["aws_region"],
                        "aws_account_id": config["aws_account_id"],
                        "github_deploy_role_arn": config["github_deploy_role_arn"],
                    }
                )
            )
            return 0
        revision = deploy(config, args.sha, AwsCli(config["aws_region"]))
    except DeploymentError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f"Deployed {args.sha} as {revision}. Open {config['frontend_url']}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

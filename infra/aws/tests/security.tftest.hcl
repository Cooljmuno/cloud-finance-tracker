mock_provider "aws" {

  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012", arn = "arn:aws:iam::123456789012:user/terraform-test", user_id = "terraform-test" }
  }
  mock_data "aws_availability_zones" {
    defaults = { names = ["us-east-2a", "us-east-2b"], zone_ids = ["use2-az1", "use2-az2"] }
  }
  mock_data "aws_security_group" {
    defaults = { id = "sg-0cf00000000000001", vpc_id = "vpc-0123456789abcdef0" }
  }
  mock_resource "aws_vpc" {
    defaults = { id = "vpc-0123456789abcdef0", arn = "arn:aws:ec2:us-east-2:123456789012:vpc/vpc-0123456789abcdef0" }
  }
  mock_resource "aws_subnet" {
    defaults = { id = "subnet-0123456789abcdef0" }
  }
  mock_resource "aws_security_group" {
    defaults = { id = "sg-0123456789abcdef0", arn = "arn:aws:ec2:us-east-2:123456789012:security-group/sg-0123456789abcdef0" }
  }
  mock_resource "aws_ecr_repository" {
    defaults = { arn = "arn:aws:ecr:us-east-2:123456789012:repository/cloud-finance-tracker-production-api", repository_url = "123456789012.dkr.ecr.us-east-2.amazonaws.com/cloud-finance-tracker-production-api" }
  }
  mock_resource "aws_cloudwatch_log_group" {
    defaults = { arn = "arn:aws:logs:us-east-2:123456789012:log-group:/ecs/cloud-finance-tracker-production/api" }
  }
  mock_resource "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::123456789012:role/mock-task-role" }
  }
  mock_resource "aws_iam_openid_connect_provider" {
    defaults = { arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
  }
  mock_resource "aws_secretsmanager_secret" {
    defaults = { arn = "arn:aws:secretsmanager:us-east-2:123456789012:secret:application-AbCdEf" }
  }
  mock_resource "aws_db_instance" {
    defaults = {
      address            = "finance.test.us-east-2.rds.amazonaws.com"
      master_user_secret = [{ secret_arn = "arn:aws:secretsmanager:us-east-2:123456789012:secret:rds-master-AbCdEf", secret_status = "active", kms_key_id = "mock-kms-key" }]
    }
  }
  mock_resource "aws_lb" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:loadbalancer/app/finance/1234567890123456", dns_name = "internal-finance.us-east-2.elb.amazonaws.com", arn_suffix = "app/finance/1234567890123456" }
  }
  mock_resource "aws_lb_target_group" {
    defaults = { arn = "arn:aws:elasticloadbalancing:us-east-2:123456789012:targetgroup/finance/1234567890123456", arn_suffix = "targetgroup/finance/1234567890123456" }
  }
  mock_resource "aws_s3_bucket" {
    defaults = { id = "cloud-finance-tracker-production-123456789012-us-east-2", arn = "arn:aws:s3:::cloud-finance-tracker-production-123456789012-us-east-2", bucket_regional_domain_name = "cloud-finance-tracker-production-123456789012-us-east-2.s3.us-east-2.amazonaws.com" }
  }
  mock_resource "aws_cloudfront_distribution" {
    defaults = { id = "E1234567890ABC", arn = "arn:aws:cloudfront::123456789012:distribution/E1234567890ABC", domain_name = "d123example.cloudfront.net" }
  }
  mock_resource "aws_cloudfront_function" {
    defaults = { arn = "arn:aws:cloudfront::123456789012:function/finance-spa" }
  }
  mock_resource "aws_ecs_cluster" {
    defaults = { id = "arn:aws:ecs:us-east-2:123456789012:cluster/cloud-finance-tracker-production", arn = "arn:aws:ecs:us-east-2:123456789012:cluster/cloud-finance-tracker-production" }
  }
  mock_resource "aws_ecs_task_definition" {
    defaults = { arn = "arn:aws:ecs:us-east-2:123456789012:task-definition/cloud-finance-tracker-production-api:1" }
  }
  mock_resource "aws_cognito_user_pool" {
    defaults = { id = "us-east-2_MockPool" }
  }
  mock_resource "aws_cognito_user_pool_client" {
    defaults = { id = "mockappclient123456789" }
  }
  override_data {
    target = data.aws_security_group.cloudfront_origin

    values = { id = "sg-0cf00000000000001", vpc_id = "vpc-0123456789abcdef0" }
  }
  override_resource {
    target = aws_iam_role.execution

    values = { arn = "arn:aws:iam::123456789012:role/mock-normal-execution" }
  }
  override_resource {
    target = aws_iam_role.task

    values = { arn = "arn:aws:iam::123456789012:role/mock-application" }
  }
  override_resource {
    target = aws_iam_role.database_bootstrap_execution

    values = { arn = "arn:aws:iam::123456789012:role/mock-database-bootstrap" }
  }
  override_resource {
    target = aws_security_group.alb

    values = { id = "sg-00000000000000001" }
  }
  override_resource {
    target = aws_security_group.tasks

    values = { id = "sg-00000000000000002" }
  }
  override_resource {
    target = aws_security_group.database

    values = { id = "sg-00000000000000003" }
  }
  override_resource {
    target = aws_subnet.tasks[0]

    values = { id = "subnet-00000000000000001" }
  }
  override_resource {
    target = aws_subnet.tasks[1]

    values = { id = "subnet-00000000000000002" }
  }
  override_resource {
    target = aws_subnet.private[0]

    values = { id = "subnet-00000000000000003" }
  }
  override_resource {
    target = aws_subnet.private[1]

    values = { id = "subnet-00000000000000004" }
  }
}

variables {
  github_oidc_subject       = "repo:Cooljmuno@92428715/cloud-finance-tracker@1351595936:environment:production"
  final_snapshot_identifier = "finance-production-final-test-20261018"
}

run "private_network_and_public_https_edge" {
  # Every AWS operation is simulated by mock_provider. Apply resolves the
  # service-managed SG lookup that intentionally occurs after VPC-origin creation.
  command = apply

  assert {
    condition     = aws_lb.api.internal && !aws_db_instance.app.publicly_accessible && length(aws_subnet.private) == 2 && length(aws_subnet.tasks) == 2
    error_message = "Origin ALB and RDS must remain private across two AZs."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.tasks_from_alb.from_port == 8000 && aws_vpc_security_group_ingress_rule.tasks_from_alb.referenced_security_group_id == aws_security_group.alb.id && aws_vpc_security_group_ingress_rule.database_from_tasks.from_port == 5432 && aws_vpc_security_group_ingress_rule.database_from_tasks.referenced_security_group_id == aws_security_group.tasks.id
    error_message = "Only ALB-to-API and API-to-database ingress is allowed."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.tasks_from_alb.security_group_id == aws_security_group.tasks.id && aws_vpc_security_group_ingress_rule.database_from_tasks.security_group_id == aws_security_group.database.id && aws_vpc_security_group_ingress_rule.alb_from_cloudfront.security_group_id == aws_security_group.alb.id
    error_message = "Ingress rules must attach to the intended distinct security groups."
  }
  assert {
    condition     = aws_vpc_security_group_ingress_rule.alb_from_cloudfront.from_port == 80 && aws_vpc_security_group_ingress_rule.alb_from_cloudfront.referenced_security_group_id == data.aws_security_group.cloudfront_origin.id
    error_message = "The private ALB must accept only the CloudFront service-managed origin security group."
  }
  assert {
    condition     = length(regexall("resource\\s+\"aws_nat_gateway\"", join("\n", [for name in fileset(path.module, "*.tf") : file(join("/", [path.module, name]))]))) == 0 && length(aws_route_table.private.route) == 0
    error_message = "This topology must have no NAT gateway and no Internet route for private origin/database subnets."
  }
  assert {
    condition     = aws_ecs_service.api.desired_count == 0 && aws_ecs_service.api.network_configuration[0].assign_public_ip && aws_ecs_service.api.deployment_circuit_breaker[0].rollback
    error_message = "Infrastructure must not run the placeholder image; deployment starts the first task with rollback protection."
  }
  assert {
    condition     = aws_ecs_task_definition.api.cpu == "256" && aws_ecs_task_definition.api.memory == "512" && jsondecode(aws_ecs_task_definition.api.container_definitions)[0].readonlyRootFilesystem
    error_message = "Use the bounded small Fargate task with a read-only root filesystem."
  }
  assert {
    condition     = aws_cloudfront_distribution.app.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https" && aws_cloudfront_distribution.app.ordered_cache_behavior[0].viewer_protocol_policy == "https-only" && aws_cloudfront_distribution.app.ordered_cache_behavior[0].cache_policy_id == "4135ea2d-6df8-44a3-9df3-4b5a84be39ad"
    error_message = "Viewers require HTTPS and authenticated API responses must not be cached."
  }
  assert {
    condition     = aws_cloudfront_origin_request_policy.api.headers_config[0].header_behavior == "allViewerAndWhitelistCloudFront" && contains(aws_cloudfront_origin_request_policy.api.headers_config[0].headers[0].items, "CloudFront-Forwarded-Proto") && aws_cloudfront_origin_request_policy.api.query_strings_config[0].query_string_behavior == "all" && aws_cloudfront_origin_request_policy.api.cookies_config[0].cookie_behavior == "none"
    error_message = "Forward bearer auth, viewer Host, generated HTTPS protocol, and filters; do not forward session cookies."
  }
  assert {
    condition     = alltrue([for response in aws_cloudfront_distribution.app.custom_error_response : response.error_caching_min_ttl == 0 && (response.response_page_path == null || response.response_page_path == "")])
    error_message = "Errors must retain their original status and never become a cached SPA page."
  }
  assert {
    condition     = aws_cloudfront_cache_policy.static.min_ttl == 0 && aws_cloudfront_cache_policy.static.max_ttl == 31536000 && aws_cloudfront_origin_access_control.frontend.signing_behavior == "always" && aws_s3_bucket_public_access_block.frontend.block_public_policy
    error_message = "Private signed S3 origin must respect no-store index and immutable hashed-asset cache headers."
  }
  assert {
    condition     = !aws_cognito_user_pool_client.app.generate_secret && aws_cognito_user_pool_client.app.allowed_oauth_flows == toset(["code"]) && aws_cognito_user_pool_client.app.callback_urls == toset(["https://d123example.cloudfront.net/"])
    error_message = "The SPA must use the public authorization-code client and exact HTTPS callback."
  }
  assert {
    condition     = jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:sub"] == var.github_oidc_subject && jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Condition.StringEquals["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    error_message = "GitHub trust must bind the exact production subject and STS audience."
  }
  assert {
    condition     = aws_db_instance.app.manage_master_user_password && aws_db_instance.app.storage_encrypted && aws_db_instance.app.deletion_protection && !aws_db_instance.app.skip_final_snapshot && aws_db_instance.app.backup_retention_period == 7 && aws_lb.api.enable_deletion_protection && aws_cognito_user_pool.app.deletion_protection == "ACTIVE"
    error_message = "Data protection, managed master credentials, and reviewed deletion guards are required."
  }
  assert {
    condition     = aws_cloudwatch_log_group.api.retention_in_days == 14 && toset(keys(aws_cloudwatch_log_group.database)) == toset(aws_db_instance.app.enabled_cloudwatch_logs_exports) && alltrue([for group in aws_cloudwatch_log_group.database : group.retention_in_days == 14])
    error_message = "API logs and every enabled RDS log export must expire after fourteen days."
  }
  assert {
    condition     = !strcontains(aws_iam_role_policy.execution.policy, "rds-master") && strcontains(aws_iam_role_policy.database_bootstrap_execution.policy, "rds-master") && !strcontains(aws_iam_role_policy.github_deploy.policy, "secretsmanager:GetSecretValue") && !strcontains(aws_iam_role_policy.github_deploy.policy, "database-bootstrap")
    error_message = "Master credentials and bootstrap PassRole must remain unavailable to normal runtime/deployment."
  }
  assert {
    condition     = toset(one([for statement in jsondecode(aws_iam_role_policy.github_deploy.policy).Statement : statement if statement.Sid == "PassOnlyNormalTaskRoles"]).Resource) == toset([aws_iam_role.execution.arn, aws_iam_role.task.arn])
    error_message = "The deployment role must pass exactly the two ordinary task roles."
  }
  assert {
    condition     = length(regexall("aws_secretsmanager_secret_version|random_password", join("\n", [for name in fileset(path.module, "*.tf") : file(join("/", [path.module, name]))]))) == 0
    error_message = "Terraform must store app secret metadata only, without generated passwords or secret values."
  }
  assert {
    condition     = { for entry in jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment : entry.name => entry.value }.POSTGRES_USER == "finance_app" && { for entry in jsondecode(aws_ecs_task_definition.api.container_definitions)[0].environment : entry.name => entry.value }.POSTGRES_SSLROOTCERT == "/app/certs/global-bundle.pem"
    error_message = "Normal API uses a separate least-privileged DB login and verified RDS CA bundle."
  }
  assert {
    condition = toset(keys(output.deployment_config)) == toset([
      "schema_version", "aws_region", "aws_account_id", "ecr_repository_url",
      "ecs_cluster_name", "ecs_service_name", "ecs_task_family", "ecs_container_name",
      "task_definition_template_arn", "task_execution_role_arn", "task_role_arn",
      "task_subnet_ids", "task_security_group_ids", "assign_public_ip", "frontend_bucket_name",
      "cloudfront_distribution_id", "frontend_url", "api_url", "cognito_region", "cognito_user_pool_id",
      "cognito_app_client_id", "cognito_domain", "github_deploy_role_arn", "app_secret_arn",
      "db_master_secret_arn", "db_bootstrap_execution_role_arn", "db_host", "db_name", "db_master_username", "db_app_username"
    ]) && output.deployment_config.schema_version == 1 && output.deployment_config.db_app_username == "finance_app" && output.deployment_config.api_url == "https://d123example.cloudfront.net/api/v1"
    error_message = "Deployment metadata must keep the exact documented public schema and same-origin API URL."
  }
  assert {
    condition     = toset(output.deployment_config.task_subnet_ids) == toset(aws_subnet.tasks[*].id) && length(setintersection(toset(output.deployment_config.task_subnet_ids), toset(aws_subnet.private[*].id))) == 0 && output.deployment_config.task_security_group_ids == [aws_security_group.tasks.id]
    error_message = "Deployment must use the outbound-capable task subnets and the restrictive task security group."
  }
}

run "reuse_existing_account_oidc_provider" {
  command = plan
  variables {
    github_oidc_provider_arn = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com"
  }
  assert {
    condition     = length(aws_iam_openid_connect_provider.github) == 0 && jsondecode(aws_iam_role.github_deploy.assume_role_policy).Statement[0].Principal.Federated == var.github_oidc_provider_arn
    error_message = "An existing account-wide GitHub provider must be reused."
  }
}

run "reject_wildcard_github_trust" {
  command = plan
  variables {
    github_oidc_subject = "repo:Cooljmuno/*:environment:production"
  }
  expect_failures = [var.github_oidc_subject]
}

run "reject_foreign_account_oidc_provider" {
  command = plan
  variables {
    github_oidc_provider_arn = "arn:aws:iam::999999999999:oidc-provider/token.actions.githubusercontent.com"
  }
  expect_failures = [aws_iam_role.github_deploy]
}

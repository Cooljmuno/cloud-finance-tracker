output "deployment_config" {
  description = "Public deployment metadata consumed by the admin bootstrap and GitHub deployment scripts; contains no secret values."
  value = {
    schema_version                  = 1
    aws_region                      = var.aws_region
    aws_account_id                  = local.account_id
    ecr_repository_url              = aws_ecr_repository.api.repository_url
    ecs_cluster_name                = aws_ecs_cluster.app.name
    ecs_service_name                = aws_ecs_service.api.name
    ecs_task_family                 = local.task_family
    ecs_container_name              = "api"
    task_definition_template_arn    = aws_ecs_task_definition.api.arn
    task_execution_role_arn         = aws_iam_role.execution.arn
    task_role_arn                   = aws_iam_role.task.arn
    task_subnet_ids                 = aws_subnet.tasks[*].id
    task_security_group_ids         = [aws_security_group.tasks.id]
    assign_public_ip                = true
    frontend_bucket_name            = aws_s3_bucket.frontend.id
    cloudfront_distribution_id      = aws_cloudfront_distribution.app.id
    frontend_url                    = local.frontend_url
    api_url                         = "${local.frontend_url}/api/v1"
    cognito_region                  = var.aws_region
    cognito_user_pool_id            = aws_cognito_user_pool.app.id
    cognito_app_client_id           = aws_cognito_user_pool_client.app.id
    cognito_domain                  = "https://${aws_cognito_user_pool_domain.app.domain}.auth.${var.aws_region}.amazoncognito.com"
    github_deploy_role_arn          = aws_iam_role.github_deploy.arn
    app_secret_arn                  = aws_secretsmanager_secret.app.arn
    db_master_secret_arn            = aws_db_instance.app.master_user_secret[0].secret_arn
    db_bootstrap_execution_role_arn = aws_iam_role.database_bootstrap_execution.arn
    db_host                         = aws_db_instance.app.address
    db_name                         = aws_db_instance.app.db_name
    db_master_username              = aws_db_instance.app.username
    db_app_username                 = "finance_app"
  }
}

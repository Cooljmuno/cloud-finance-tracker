locals {
  task_trust = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ecs-tasks.amazonaws.com" }
      Action    = "sts:AssumeRole"
      Condition = {
        StringEquals = { "aws:SourceAccount" = local.account_id }
        ArnLike      = { "aws:SourceArn" = "arn:aws:ecs:${var.aws_region}:${local.account_id}:*" }
      }
    }]
  })
  execution_statements = [
    {
      Effect   = "Allow"
      Action   = ["ecr:GetAuthorizationToken"]
      Resource = ["*"]
    },
    {
      Effect   = "Allow"
      Action   = ["ecr:BatchCheckLayerAvailability", "ecr:GetDownloadUrlForLayer", "ecr:BatchGetImage"]
      Resource = [aws_ecr_repository.api.arn]
    },
    {
      Effect   = "Allow"
      Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
      Resource = ["${aws_cloudwatch_log_group.api.arn}:*"]
    }
  ]
  github_provider_arn         = var.github_oidc_provider_arn != null ? var.github_oidc_provider_arn : aws_iam_openid_connect_provider.github[0].arn
  task_definition_arn_pattern = "arn:aws:ecs:${var.aws_region}:${local.account_id}:task-definition/${local.task_family}:*"
  cluster_tasks_arn_pattern   = "arn:aws:ecs:${var.aws_region}:${local.account_id}:task/${aws_ecs_cluster.app.name}/*"
  service_arn                 = "arn:aws:ecs:${var.aws_region}:${local.account_id}:service/${aws_ecs_cluster.app.name}/api"
}

resource "aws_iam_role" "execution" {
  name               = "${local.name}-task-execution"
  assume_role_policy = local.task_trust
}

resource "aws_iam_role_policy" "execution" {
  name = "pull-log-and-read-app-secret"
  role = aws_iam_role.execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(local.execution_statements, [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.app.arn]
    }])
  })
}

resource "aws_iam_role" "task" {
  name               = "${local.name}-application"
  assume_role_policy = local.task_trust
}

resource "aws_iam_role" "database_bootstrap_execution" {
  name               = "${local.name}-database-bootstrap"
  assume_role_policy = local.task_trust
}

resource "aws_iam_role_policy" "database_bootstrap_execution" {
  name = "admin-only-database-bootstrap"
  role = aws_iam_role.database_bootstrap_execution.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(local.execution_statements, [{
      Effect   = "Allow"
      Action   = ["secretsmanager:GetSecretValue"]
      Resource = [aws_secretsmanager_secret.app.arn, aws_db_instance.app.master_user_secret[0].secret_arn]
    }])
  })
}

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.github_oidc_provider_arn == null ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

resource "aws_iam_role" "github_deploy" {
  name                 = "${local.name}-github-deploy"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = local.github_provider_arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = var.github_oidc_subject
        }
      }
    }]
  })
  lifecycle {
    precondition {
      condition     = var.github_oidc_provider_arn == null ? true : startswith(var.github_oidc_provider_arn, "arn:aws:iam::${local.account_id}:")
      error_message = "The existing GitHub OIDC provider must belong to this AWS account."
    }
  }
}

resource "aws_iam_role_policy" "github_deploy" {
  name = "deploy-one-application"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "RegistryLogin"
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Sid    = "PushAndReuseImmutableImage"
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload", "ecr:PutImage", "ecr:DescribeImages", "ecr:BatchGetImage"
        ]
        Resource = aws_ecr_repository.api.arn
      },
      {
        Sid      = "ReadTaskTemplate"
        Effect   = "Allow"
        Action   = ["ecs:DescribeTaskDefinition"]
        Resource = "*"
      },
      {
        Sid      = "RegisterApplicationRevision"
        Effect   = "Allow"
        Action   = ["ecs:RegisterTaskDefinition", "ecs:TagResource"]
        Resource = local.task_definition_arn_pattern
      },
      {
        Sid       = "RunApplicationMigrations"
        Effect    = "Allow"
        Action    = ["ecs:RunTask"]
        Resource  = local.task_definition_arn_pattern
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.app.arn } }
      },
      {
        Sid       = "InspectAndStopMigrationTasks"
        Effect    = "Allow"
        Action    = ["ecs:DescribeTasks", "ecs:StopTask"]
        Resource  = local.cluster_tasks_arn_pattern
        Condition = { ArnEquals = { "ecs:cluster" = aws_ecs_cluster.app.arn } }
      },
      {
        Sid      = "RollOutApplicationService"
        Effect   = "Allow"
        Action   = ["ecs:UpdateService", "ecs:DescribeServices"]
        Resource = local.service_arn
      },
      {
        Sid       = "PassOnlyNormalTaskRoles"
        Effect    = "Allow"
        Action    = ["iam:PassRole"]
        Resource  = [aws_iam_role.execution.arn, aws_iam_role.task.arn]
        Condition = { StringEquals = { "iam:PassedToService" = "ecs-tasks.amazonaws.com" } }
      },
      {
        Sid      = "CheckAppSecretMetadata"
        Effect   = "Allow"
        Action   = ["secretsmanager:DescribeSecret"]
        Resource = aws_secretsmanager_secret.app.arn
      },
      {
        Sid      = "InspectFrontendBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket", "s3:GetBucketLocation"]
        Resource = aws_s3_bucket.frontend.arn
      },
      {
        Sid      = "PublishFrontendObjects"
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.frontend.arn}/*"
      },
      {
        Sid      = "InvalidateFrontendCache"
        Effect   = "Allow"
        Action   = ["cloudfront:CreateInvalidation", "cloudfront:GetInvalidation"]
        Resource = aws_cloudfront_distribution.app.arn
      }
    ]
  })
}

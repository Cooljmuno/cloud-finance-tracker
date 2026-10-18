resource "aws_ecr_repository" "api" {
  name                 = "${local.name}-api"
  image_tag_mutability = "IMMUTABLE"
  force_delete         = false
  image_scanning_configuration {
    scan_on_push = true
  }
  encryption_configuration {
    encryption_type = "AES256"
  }
}

resource "aws_ecr_lifecycle_policy" "api" {
  repository = aws_ecr_repository.api.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Remove untagged build layers after seven days; retain immutable tagged releases"
      selection = {
        tagStatus   = "untagged"
        countType   = "sinceImagePushed"
        countUnit   = "days"
        countNumber = 7
      }
      action = { type = "expire" }
    }]
  })
}

resource "aws_cloudwatch_log_group" "api" {
  name              = "/ecs/${local.name}/api"
  retention_in_days = 14
}

resource "aws_ecs_cluster" "app" {
  name = local.name
  setting {
    name  = "containerInsights"
    value = "disabled"
  }
}

resource "aws_ecs_task_definition" "api" {
  family                   = local.task_family
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = "256"
  memory                   = "512"
  execution_role_arn       = aws_iam_role.execution.arn
  task_role_arn            = aws_iam_role.task.arn

  runtime_platform {
    cpu_architecture        = "X86_64"
    operating_system_family = "LINUX"
  }

  volume {
    name                = "tmp"
    configure_at_launch = false
  }

  container_definitions = jsonencode([{
    name                   = "api"
    image                  = "${aws_ecr_repository.api.repository_url}:bootstrap"
    essential              = true
    readonlyRootFilesystem = true
    portMappings           = [{ containerPort = 8000, hostPort = 8000, protocol = "tcp" }]
    mountPoints            = [{ sourceVolume = "tmp", containerPath = "/tmp", readOnly = false }]
    linuxParameters        = { capabilities = { add = [], drop = ["ALL"] } }
    systemControls         = []
    volumesFrom            = []
    environment = [
      { name = "DJANGO_SETTINGS_MODULE", value = "config.settings.production" },
      { name = "DJANGO_ALLOWED_HOSTS", value = aws_cloudfront_distribution.app.domain_name },
      { name = "POSTGRES_HOST", value = aws_db_instance.app.address },
      { name = "POSTGRES_PORT", value = "5432" },
      { name = "POSTGRES_DB", value = aws_db_instance.app.db_name },
      { name = "POSTGRES_USER", value = "finance_app" },
      { name = "POSTGRES_SSLROOTCERT", value = "/app/certs/global-bundle.pem" },
      { name = "COGNITO_REGION", value = var.aws_region },
      { name = "COGNITO_USER_POOL_ID", value = aws_cognito_user_pool.app.id },
      { name = "COGNITO_APP_CLIENT_ID", value = aws_cognito_user_pool_client.app.id },
      { name = "ENABLE_LOCAL_AUTH", value = "false" },
      { name = "ENABLE_DEMO_DATA", value = "false" },
      { name = "ENABLE_DJANGO_ADMIN", value = "false" }
    ]
    secrets = [
      { name = "DJANGO_SECRET_KEY", valueFrom = "${aws_secretsmanager_secret.app.arn}:DJANGO_SECRET_KEY::" },
      { name = "POSTGRES_PASSWORD", valueFrom = "${aws_secretsmanager_secret.app.arn}:POSTGRES_PASSWORD::" }
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.api.name
        awslogs-region        = var.aws_region
        awslogs-stream-prefix = "api"
      }
    }
    healthCheck = {
      command     = ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health/', timeout=3).read()"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 30
    }
  }])
}

resource "aws_lb" "api" {
  name                       = "${local.short_name}-api"
  internal                   = true
  load_balancer_type         = "application"
  security_groups            = [aws_security_group.alb.id]
  subnets                    = aws_subnet.private[*].id
  drop_invalid_header_fields = true
  enable_deletion_protection = var.deletion_protection
}

resource "aws_lb_target_group" "api" {
  name                 = "${local.short_name}-api"
  port                 = 8000
  protocol             = "HTTP"
  target_type          = "ip"
  vpc_id               = aws_vpc.app.id
  deregistration_delay = 30
  health_check {
    enabled             = true
    path                = "/api/v1/health/"
    protocol            = "HTTP"
    matcher             = "200"
    interval            = 30
    timeout             = 5
    healthy_threshold   = 2
    unhealthy_threshold = 3
  }
}

resource "aws_lb_listener" "api" {
  load_balancer_arn = aws_lb.api.arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.api.arn
  }
}

resource "aws_ecs_service" "api" {
  name                               = "api"
  cluster                            = aws_ecs_cluster.app.id
  task_definition                    = aws_ecs_task_definition.api.arn
  desired_count                      = 0
  launch_type                        = "FARGATE"
  platform_version                   = "1.4.0"
  health_check_grace_period_seconds  = 60
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200
  enable_execute_command             = false

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  network_configuration {
    subnets          = aws_subnet.tasks[*].id
    security_groups  = [aws_security_group.tasks.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.api.arn
    container_name   = "api"
    container_port   = 8000
  }

  lifecycle {
    ignore_changes = [task_definition, desired_count]
  }

  depends_on = [aws_lb_listener.api, aws_iam_role_policy.execution, aws_route.internet]
}

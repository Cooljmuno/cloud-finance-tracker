resource "aws_cloudwatch_metric_alarm" "api_cpu" {
  alarm_name          = "${local.name}-api-high-cpu"
  alarm_description   = "API CPU above 80 percent for ten minutes; no notification unless alarm actions are supplied"
  namespace           = "AWS/ECS"
  metric_name         = "CPUUtilization"
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 2
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { ClusterName = aws_ecs_cluster.app.name, ServiceName = aws_ecs_service.api.name }
  alarm_actions       = var.alarm_action_arns
  ok_actions          = var.alarm_action_arns
}

resource "aws_cloudwatch_metric_alarm" "api_errors" {
  alarm_name          = "${local.name}-api-server-errors"
  namespace           = "AWS/ApplicationELB"
  metric_name         = "HTTPCode_Target_5XX_Count"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { LoadBalancer = aws_lb.api.arn_suffix, TargetGroup = aws_lb_target_group.api.arn_suffix }
  alarm_actions       = var.alarm_action_arns
  ok_actions          = var.alarm_action_arns
}

resource "aws_cloudwatch_metric_alarm" "database_storage" {
  alarm_name          = "${local.name}-database-low-free-storage"
  namespace           = "AWS/RDS"
  metric_name         = "FreeStorageSpace"
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 5 * 1024 * 1024 * 1024
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "notBreaching"
  dimensions          = { DBInstanceIdentifier = aws_db_instance.app.identifier }
  alarm_actions       = var.alarm_action_arns
  ok_actions          = var.alarm_action_arns
}

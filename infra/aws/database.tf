resource "aws_db_subnet_group" "app" {
  name       = local.name
  subnet_ids = aws_subnet.private[*].id
}

resource "aws_db_parameter_group" "app" {
  name_prefix = "${local.name}-"
  family      = "postgres18"
  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_cloudwatch_log_group" "database" {
  for_each          = toset(["postgresql", "upgrade"])
  name              = format("/aws/rds/instance/%s/%s", local.name, each.value)
  retention_in_days = 14
}

resource "aws_db_instance" "app" {
  identifier                      = local.name
  engine                          = "postgres"
  engine_version                  = "18"
  instance_class                  = "db.t4g.micro"
  allocated_storage               = 20
  max_allocated_storage           = 40
  storage_type                    = "gp3"
  storage_encrypted               = true
  db_name                         = "finance_tracker"
  username                        = "finance_admin"
  manage_master_user_password     = true
  db_subnet_group_name            = aws_db_subnet_group.app.name
  vpc_security_group_ids          = [aws_security_group.database.id]
  parameter_group_name            = aws_db_parameter_group.app.name
  publicly_accessible             = false
  multi_az                        = false
  backup_retention_period         = 7
  backup_window                   = "06:00-07:00"
  maintenance_window              = "sun:08:00-sun:09:00"
  auto_minor_version_upgrade      = true
  allow_major_version_upgrade     = false
  deletion_protection             = var.deletion_protection
  skip_final_snapshot             = false
  final_snapshot_identifier       = var.final_snapshot_identifier
  copy_tags_to_snapshot           = true
  enabled_cloudwatch_logs_exports = ["postgresql", "upgrade"]

  depends_on = [aws_cloudwatch_log_group.database]
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/application"
  description             = "Application credentials initialized out of band by the admin bootstrap script"
  recovery_window_in_days = 30
}

resource "aws_vpc" "app" {
  cidr_block           = "10.42.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags                 = { Name = local.name }
}

resource "aws_internet_gateway" "app" {
  vpc_id = aws_vpc.app.id
}

resource "aws_subnet" "tasks" {
  count                   = 2
  vpc_id                  = aws_vpc.app.id
  availability_zone       = local.zones[count.index]
  cidr_block              = cidrsubnet(aws_vpc.app.cidr_block, 8, count.index)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-tasks-${count.index + 1}" }
}

resource "aws_subnet" "private" {
  count                   = 2
  vpc_id                  = aws_vpc.app.id
  availability_zone       = local.zones[count.index]
  cidr_block              = cidrsubnet(aws_vpc.app.cidr_block, 8, count.index + 10)
  map_public_ip_on_launch = false
  tags                    = { Name = "${local.name}-private-${count.index + 1}" }
}

resource "aws_route_table" "tasks" {
  vpc_id = aws_vpc.app.id
}

resource "aws_route" "internet" {
  route_table_id         = aws_route_table.tasks.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.app.id
}

resource "aws_route_table_association" "tasks" {
  count          = 2
  subnet_id      = aws_subnet.tasks[count.index].id
  route_table_id = aws_route_table.tasks.id
}

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.app.id
  route  = []
}

resource "aws_route_table_association" "private" {
  count          = 2
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private.id
}

resource "aws_security_group" "alb" {
  name_prefix = "${local.short_name}-alb-"
  description = "Private origin: ingress only from the CloudFront managed VPC-origin security group"
  vpc_id      = aws_vpc.app.id
}

resource "aws_security_group" "tasks" {
  name_prefix = "${local.short_name}-tasks-"
  description = "API tasks: only ALB ingress; HTTPS outbound and PostgreSQL to the database"
  vpc_id      = aws_vpc.app.id
}

resource "aws_security_group" "database" {
  name_prefix = "${local.short_name}-db-"
  description = "Database: PostgreSQL only from API tasks"
  vpc_id      = aws_vpc.app.id
}

resource "aws_vpc_security_group_ingress_rule" "tasks_from_alb" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.alb.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "alb_to_tasks" {
  security_group_id            = aws_security_group.alb.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 8000
  to_port                      = 8000
}

resource "aws_vpc_security_group_egress_rule" "tasks_https" {
  security_group_id = aws_security_group.tasks.id
  cidr_ipv4         = "0.0.0.0/0"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
}

resource "aws_vpc_security_group_egress_rule" "tasks_to_database" {
  security_group_id            = aws_security_group.tasks.id
  referenced_security_group_id = aws_security_group.database.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

resource "aws_vpc_security_group_ingress_rule" "database_from_tasks" {
  security_group_id            = aws_security_group.database.id
  referenced_security_group_id = aws_security_group.tasks.id
  ip_protocol                  = "tcp"
  from_port                    = 5432
  to_port                      = 5432
}

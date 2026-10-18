terraform {
  required_version = "= 1.16.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
  }

  backend "s3" {}
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "Terraform"
    }
  }
}

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"

  filter {
    name   = "opt-in-status"
    values = ["opt-in-not-required"]
  }
}

locals {
  name         = "${var.project_name}-${var.environment}"
  short_name   = substr(local.name, 0, 24)
  account_id   = data.aws_caller_identity.current.account_id
  zones        = slice(data.aws_availability_zones.available.names, 0, 2)
  task_family  = "${local.name}-api"
  frontend_url = "https://${aws_cloudfront_distribution.app.domain_name}"
}

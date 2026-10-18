terraform {
  required_version = "= 1.16.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.69"
    }
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project   = "cloud-finance-tracker"
      Purpose   = "terraform-state"
      ManagedBy = "Terraform"
    }
  }
}

variable "aws_region" {
  description = "A supported CloudFront VPC-origin region without excluded availability zones."
  type        = string
  default     = "us-east-2"
  validation {
    condition     = contains(["us-east-2", "us-west-2", "eu-west-1"], var.aws_region)
    error_message = "Use us-east-2, us-west-2, or eu-west-1; validate VPC-origin AZ support before adding regions."
  }
}

variable "project_name" {
  type    = string
  default = "cloud-finance-tracker"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.project_name)) && !strcontains(var.project_name, "--")
    error_message = "project_name must be 3 to 24 lowercase letters, digits, or hyphens, starting with a letter, with no consecutive or trailing hyphens."
  }
}

variable "environment" {
  type    = string
  default = "production"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{0,10}[a-z0-9]$", var.environment)) && !strcontains(var.environment, "--")
    error_message = "environment must be 2 to 12 lowercase letters, digits, or hyphens, with no consecutive or trailing hyphens."
  }
}

variable "github_oidc_subject" {
  description = "Exact production-environment GitHub OIDC sub claim, including immutable IDs if your repository uses them. Never a wildcard."
  type        = string
  validation {
    condition     = startswith(var.github_oidc_subject, "repo:") && can(regex(":environment:production(:|$)", var.github_oidc_subject)) && !strcontains(var.github_oidc_subject, "*") && !strcontains(var.github_oidc_subject, "?")
    error_message = "Supply the exact repo OIDC subject for the production environment, with no wildcard."
  }
}

variable "github_oidc_provider_arn" {
  description = "Existing account-wide GitHub OIDC provider ARN; null creates it once for this account."
  type        = string
  default     = null
  validation {
    condition     = var.github_oidc_provider_arn == null ? true : can(regex("^arn:aws:iam::[0-9]{12}:oidc-provider/token.actions.githubusercontent.com$", var.github_oidc_provider_arn))
    error_message = "Expected the ARN of the GitHub Actions OIDC provider in this AWS account."
  }
}

variable "final_snapshot_identifier" {
  description = "Unique final RDS snapshot identifier, chosen before provisioning; retained when the database is intentionally removed."
  type        = string
  validation {
    condition     = can(regex("^[a-zA-Z][a-zA-Z0-9-]{0,253}[a-zA-Z0-9]$", var.final_snapshot_identifier)) && !strcontains(var.final_snapshot_identifier, "--")
    error_message = "Use a unique 2 to 255 character snapshot identifier starting with a letter, with no consecutive or trailing hyphens."
  }
}

variable "alarm_action_arns" {
  description = "Optional existing SNS or other supported CloudWatch alarm action ARNs. Empty means alarms have no notification destination."
  type        = list(string)
  default     = []
}

variable "deletion_protection" {
  description = "Protect RDS, ALB, and Cognito from deletion. Disable only in a reviewed cleanup plan after backing up data."
  type        = bool
  default     = true
}

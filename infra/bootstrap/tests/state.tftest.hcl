mock_provider "aws" {
  override_during = plan
  mock_resource "aws_s3_bucket" {
    defaults = { id = "finance-test-private-state", arn = "arn:aws:s3:::finance-test-private-state" }
  }
}

variables {
  state_bucket_name = "finance-test-private-state"
}

run "private_encrypted_versioned_state" {
  command = plan
  assert {
    condition     = aws_s3_bucket_public_access_block.state.block_public_acls && aws_s3_bucket_public_access_block.state.block_public_policy && aws_s3_bucket_public_access_block.state.ignore_public_acls && aws_s3_bucket_public_access_block.state.restrict_public_buckets && !aws_s3_bucket.state.force_destroy
    error_message = "Terraform state must remain private and protected from force deletion."
  }
  assert {
    condition     = aws_s3_bucket_versioning.state.versioning_configuration[0].status == "Enabled" && one(aws_s3_bucket_server_side_encryption_configuration.state.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "State requires encryption and version history."
  }
  assert {
    condition     = jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Effect == "Deny" && jsondecode(aws_s3_bucket_policy.state.policy).Statement[0].Condition.Bool["aws:SecureTransport"] == "false"
    error_message = "Unencrypted transport must be denied."
  }
}

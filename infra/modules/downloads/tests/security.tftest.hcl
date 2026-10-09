mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-south-1" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
}

variables {
  name = "lung-test"
}

run "only_apks_are_public" {
  command = plan
  assert {
    condition = alltrue([
      for s in data.aws_iam_policy_document.public_read.statement :
      s.effect == "Deny" || (s.actions == toset(["s3:GetObject"]) && alltrue([for r in s.resources : endswith(r, "/*.apk")]))
    ])
    error_message = "the only public permission must be reading .apk objects"
  }
  assert {
    condition = alltrue([
      aws_s3_bucket_public_access_block.this.block_public_acls,
      aws_s3_bucket_public_access_block.this.ignore_public_acls,
    ])
    error_message = "public ACLs must stay blocked; access is the bucket policy only"
  }
  assert {
    condition     = one(aws_s3_bucket_ownership_controls.this.rule).object_ownership == "BucketOwnerEnforced"
    error_message = "ACLs must be disabled"
  }
}

run "https_only_and_encrypted" {
  command = plan
  assert {
    condition = anytrue([
      for s in data.aws_iam_policy_document.public_read.statement :
      s.effect == "Deny" && anytrue([for c in s.condition : c.variable == "aws:SecureTransport" && contains(c.values, "false")])
    ])
    error_message = "plain-HTTP requests must be denied"
  }
  assert {
    condition     = one(aws_s3_bucket_server_side_encryption_configuration.this.rule).apply_server_side_encryption_by_default[0].sse_algorithm == "AES256"
    error_message = "the bucket must be encrypted"
  }
}

# Run once per AWS account, with local state, to create the bucket that holds every other
# OpenTofu state file. Native S3 locking (use_lockfile) means no DynamoDB table is needed.
#
#   cd infra/bootstrap && tofu init && tofu apply
#   -> prints state_bucket; use it as -backend-config="bucket=..." in envs/*

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
}

variable "region" {
  type    = string
  default = "ap-south-1"
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "lung-exposure", managed_by = "opentofu" }
  }
}

data "aws_caller_identity" "this" {}

resource "aws_s3_bucket" "state" {
  bucket = "lung-tfstate-${data.aws_caller_identity.this.account_id}-${var.region}"
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "state" {
  bucket = aws_s3_bucket.state.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "state" {
  bucket = aws_s3_bucket.state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "state" {
  bucket                  = aws_s3_bucket.state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

output "state_bucket" { value = aws_s3_bucket.state.bucket }

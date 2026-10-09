# Public download bucket for the Android APK, in the same region as the server.
# GitHub's release CDN is slow from India (~0.6 Mbit/s measured, vs ~30 Mbit/s from S3 Mumbai),
# so the app is served from here. Anyone may read *.apk objects; nothing else is public, and
# nothing else should be put here. Uploads: deploy/scripts/publish-apk.sh.

variable "name" { type = string }

data "aws_caller_identity" "this" {}
data "aws_region" "this" {}

resource "aws_s3_bucket" "this" {
  bucket = "${var.name}-downloads-${data.aws_caller_identity.this.account_id}-${data.aws_region.this.region}"
}

resource "aws_s3_bucket_ownership_controls" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    object_ownership = "BucketOwnerEnforced" # no ACLs; access is the policy below only
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "this" {
  bucket = aws_s3_bucket.this.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Public bucket policies are allowed (that's the point); public ACLs stay blocked.
resource "aws_s3_bucket_public_access_block" "this" {
  bucket                  = aws_s3_bucket.this.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

data "aws_iam_policy_document" "public_read" {
  statement {
    sid       = "PublicReadApkOnly"
    actions   = ["s3:GetObject"]
    resources = ["${aws_s3_bucket.this.arn}/*.apk"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
  }
  statement {
    sid       = "HttpsOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.this.arn, "${aws_s3_bucket.this.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
}

resource "aws_s3_bucket_policy" "this" {
  bucket = aws_s3_bucket.this.id
  policy = data.aws_iam_policy_document.public_read.json
  # the public access block must allow public policies first
  depends_on = [aws_s3_bucket_public_access_block.this]
}

output "bucket_name" { value = aws_s3_bucket.this.bucket }

output "apk_url" {
  value = "https://${aws_s3_bucket.this.bucket}.s3.${data.aws_region.this.region}.amazonaws.com/lung-score.apk"
}

# Two roles, both least-privilege:
#  - the EC2 instance role: its own queues, its own bucket prefixes, its own SSM path and
#    log group, plus SSM Session Manager / Run Command;
#  - the GitHub Actions deploy role (OIDC, no stored AWS keys): upload a release bundle and
#    run the deploy script on this one instance, from one repo's "demo" environment only.

variable "name" { type = string }
variable "env" { type = string }
variable "queue_arns" { type = list(string) }
variable "bucket_arn" { type = string }
variable "log_group_arn" { type = string }
variable "github_repo" {
  type        = string
  description = <<-EOT
    Repo allowed to deploy, exactly as GitHub writes it in the OIDC subject: owner/repo, or
    owner@owner_id/repo@repo_id for repos that use immutable subjects
    (gh api repos/OWNER/REPO/actions/oidc/customization/sub shows the prefix).
  EOT
}
variable "create_github_oidc_provider" {
  type        = bool
  default     = true
  description = "false if the account already has the token.actions.githubusercontent.com provider"
}

data "aws_caller_identity" "this" {}
data "aws_region" "this" {}

locals {
  account    = data.aws_caller_identity.this.account_id
  region     = data.aws_region.this.region
  ssm_prefix = "/lung/${var.env}"
}

# ---------------------------------------------------------------- instance role

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "instance" {
  name               = "${var.name}-instance"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.instance.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_iam_policy_document" "instance" {
  statement {
    sid = "Queues"
    actions = [
      "sqs:SendMessage", "sqs:ReceiveMessage", "sqs:DeleteMessage",
      "sqs:ChangeMessageVisibility", "sqs:GetQueueAttributes", "sqs:GetQueueUrl",
    ]
    resources = var.queue_arns
  }
  statement {
    sid       = "BackupsAndReleases"
    actions   = ["s3:PutObject", "s3:GetObject"]
    resources = ["${var.bucket_arn}/postgres/*", "${var.bucket_arn}/releases/*"]
  }
  statement {
    sid       = "ListBucket"
    actions   = ["s3:ListBucket"]
    resources = [var.bucket_arn]
  }
  statement {
    sid     = "ConfigAndSecrets"
    actions = ["ssm:GetParametersByPath", "ssm:GetParameters", "ssm:GetParameter"]
    resources = ["arn:aws:ssm:${local.region}:${local.account}:parameter${local.ssm_prefix}/*",
    "arn:aws:ssm:${local.region}:${local.account}:parameter${local.ssm_prefix}"]
  }
  statement {
    sid       = "DecryptSecureStrings"
    actions   = ["kms:Decrypt"]
    resources = ["*"]
    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["ssm.${local.region}.amazonaws.com"]
    }
  }
  statement {
    sid       = "Logs"
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents", "logs:DescribeLogStreams"]
    resources = [var.log_group_arn, "${var.log_group_arn}:*"]
  }
}

resource "aws_iam_role_policy" "instance" {
  role   = aws_iam_role.instance.id
  policy = data.aws_iam_policy_document.instance.json
}

resource "aws_iam_instance_profile" "instance" {
  name = "${var.name}-instance"
  role = aws_iam_role.instance.name
}

# ---------------------------------------------------------------- GitHub deploy role

resource "aws_iam_openid_connect_provider" "github" {
  count          = var.create_github_oidc_provider ? 1 : 0
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
}

locals {
  oidc_arn = var.create_github_oidc_provider ? aws_iam_openid_connect_provider.github[0].arn : "arn:aws:iam::${local.account}:oidc-provider/token.actions.githubusercontent.com"
}

data "aws_iam_policy_document" "github_assume" {
  statement {
    actions = ["sts:AssumeRoleWithWebIdentity"]
    principals {
      type        = "Federated"
      identifiers = [local.oidc_arn]
    }
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }
    condition {
      # Only jobs running in this repo's GitHub environment named after the env ("demo").
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repo}:environment:${var.env}"]
    }
  }
}

resource "aws_iam_role" "deploy" {
  name                 = "${var.name}-github-deploy"
  assume_role_policy   = data.aws_iam_policy_document.github_assume.json
  max_session_duration = 3600
}

data "aws_iam_policy_document" "deploy" {
  statement {
    sid       = "UploadRelease"
    actions   = ["s3:PutObject"]
    resources = ["${var.bucket_arn}/releases/*"]
  }
  statement {
    # Only instances tagged lung-env = <env> (set by the compute module), only with the
    # stock shell-script document.
    sid       = "RunDeployOnTheInstance"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ec2:${local.region}:${local.account}:instance/*"]
    condition {
      test     = "StringEquals"
      variable = "ssm:resourceTag/lung-env"
      values   = [var.env]
    }
  }
  statement {
    sid       = "TheShellScriptDocument"
    actions   = ["ssm:SendCommand"]
    resources = ["arn:aws:ssm:${local.region}::document/AWS-RunShellScript"]
  }
  statement {
    sid       = "ReadCommandResults"
    actions   = ["ssm:GetCommandInvocation", "ssm:ListCommandInvocations"]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "deploy" {
  role   = aws_iam_role.deploy.id
  policy = data.aws_iam_policy_document.deploy.json
}

output "instance_profile_name" { value = aws_iam_instance_profile.instance.name }
output "instance_role_name" { value = aws_iam_role.instance.name }
output "deploy_role_arn" { value = aws_iam_role.deploy.arn }
output "deploy_role_name" { value = aws_iam_role.deploy.name }

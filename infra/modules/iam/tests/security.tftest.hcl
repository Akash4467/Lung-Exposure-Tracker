mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "123456789012" }
  }
  mock_data "aws_iam_policy_document" {
    defaults = { json = "{}" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-south-1" }
  }
}

variables {
  name          = "lung-test"
  env           = "demo"
  queue_arns    = ["arn:aws:sqs:ap-south-1:123456789012:q"]
  bucket_arn    = "arn:aws:s3:::bucket"
  log_group_arn = "arn:aws:logs:ap-south-1:123456789012:log-group:/lung/demo"
  github_repo   = "owner/repo"
}

run "deploy_role_trusts_only_this_repo_environment" {
  command = plan
  assert {
    condition = contains(flatten([
      for s in data.aws_iam_policy_document.github_assume.statement : [
        for c in s.condition : c.values if c.variable == "token.actions.githubusercontent.com:sub"
      ]
    ]), "repo:owner/repo:environment:demo")
    error_message = "the deploy role must only trust owner/repo's demo environment"
  }
}

run "instance_secrets_are_scoped_to_its_env" {
  command = plan
  assert {
    condition = alltrue([
      for arn in one([for s in data.aws_iam_policy_document.instance.statement : s.resources if s.sid == "ConfigAndSecrets"]) :
      strcontains(arn, ":parameter/lung/demo")
    ])
    error_message = "the instance may only read its own /lung/<env> parameters"
  }
}

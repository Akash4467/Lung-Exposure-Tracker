# The deployed environment: one EC2 server behind Caddy, DuckDNS, everything else managed.
#
#   tofu init -backend-config="bucket=<state_bucket from infra/bootstrap>"
#   tofu apply -var-file=demo.tfvars

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
    key          = "lung/demo.tfstate"
    region       = "ap-south-1"
    encrypt      = true
    use_lockfile = true
  }
}

variable "region" {
  type    = string
  default = "ap-south-1"
}
variable "github_repo" { type = string }
variable "domain" { type = string }
variable "alarm_email" {
  type    = string
  default = ""
}
variable "create_github_oidc_provider" {
  type    = bool
  default = true
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "lung-exposure", env = "demo", managed_by = "opentofu" }
  }
}

module "stack" {
  source                      = "../../modules/stack"
  env                         = "demo"
  github_repo                 = var.github_repo
  domain                      = var.domain
  alarm_email                 = var.alarm_email
  instance_type               = "t4g.small"
  create_github_oidc_provider = var.create_github_oidc_provider
}

output "public_ip" {
  value       = module.stack.public_ip
  description = "Point your DuckDNS name at this"
}
output "instance_id" { value = module.stack.instance_id }
output "bucket" { value = module.stack.bucket }
output "deploy_role_arn" { value = module.stack.deploy_role_arn }
output "log_group" { value = module.stack.log_group }
output "downloads_bucket" { value = module.stack.downloads_bucket }
output "apk_url" { value = module.stack.apk_url }

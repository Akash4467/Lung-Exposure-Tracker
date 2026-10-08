# WRITTEN, NOT DEPLOYED. The same stack with the ALB (needs a real domain in Route 53) and
# RDS switched on. Costs roughly $45-60/month on top of the demo; see docs/deployment.md.

terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  backend "s3" {
    key          = "lung/scale.tfstate"
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
variable "route53_zone_id" { type = string }
variable "alarm_email" {
  type    = string
  default = ""
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { project = "lung-exposure", env = "scale", managed_by = "opentofu" }
  }
}

module "stack" {
  source                      = "../../modules/stack"
  env                         = "scale"
  github_repo                 = var.github_repo
  domain                      = var.domain
  alarm_email                 = var.alarm_email
  instance_type               = "t4g.medium"
  create_github_oidc_provider = false # created by the demo env in the same account
  enable_alb                  = true
  route53_zone_id             = var.route53_zone_id
  enable_rds                  = true
}

output "alb_dns_name" { value = module.stack.alb_dns_name }
output "rds_endpoint" { value = module.stack.rds_endpoint }
output "deploy_role_arn" { value = module.stack.deploy_role_arn }

# The whole environment. envs/demo and envs/scale call this with different switches.

variable "env" { type = string }
variable "github_repo" { type = string }
variable "domain" {
  type        = string
  description = "e.g. lung-demo.duckdns.org"
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "instance_type" {
  type    = string
  default = "t4g.small"
}
variable "create_github_oidc_provider" {
  type    = bool
  default = true
}
variable "protect_instance" {
  type    = bool
  default = true
}
variable "enable_alb" {
  type    = bool
  default = false
}
variable "route53_zone_id" {
  type    = string
  default = ""
}
variable "enable_rds" {
  type    = bool
  default = false
}

locals {
  name = "lung-${var.env}"
}

module "network" {
  source = "../network"
  name   = local.name
}

module "storage" {
  source = "../storage"
  name   = local.name
}

module "queue" {
  source = "../queue"
  name   = local.name
}

module "monitoring" {
  source      = "../monitoring"
  name        = local.name
  env         = var.env
  alarm_email = var.alarm_email
  dlq_names   = module.queue.dlq_names
  queue_names = module.queue.queue_names
  instance_id = module.compute.instance_id
}

module "iam" {
  source                      = "../iam"
  name                        = local.name
  env                         = var.env
  queue_arns                  = module.queue.queue_arns
  bucket_arn                  = module.storage.bucket_arn
  log_group_arn               = module.monitoring.log_group_arn
  github_repo                 = var.github_repo
  create_github_oidc_provider = var.create_github_oidc_provider
}

module "compute" {
  source                = "../compute"
  name                  = local.name
  env                   = var.env
  instance_type         = var.instance_type
  subnet_id             = module.network.public_subnet_ids[0]
  security_group_ids    = [module.network.web_sg_id]
  instance_profile_name = module.iam.instance_profile_name
  release_bucket        = module.storage.bucket_name
  protect               = var.protect_instance
}

module "edge" {
  source            = "../edge"
  enabled           = var.enable_alb
  name              = local.name
  vpc_id            = module.network.vpc_id
  public_subnet_ids = module.network.public_subnet_ids
  instance_ids      = [module.compute.instance_id]
  instance_sg_id    = module.network.web_sg_id
  domain            = var.domain
  route53_zone_id   = var.route53_zone_id
}

module "rds" {
  source             = "../rds"
  enabled            = var.enable_rds
  name               = local.name
  vpc_id             = module.network.vpc_id
  private_subnet_ids = module.network.private_subnet_ids
  app_sg_id          = module.network.web_sg_id
}

# Non-secret configuration the deploy script reads from SSM. Secrets are NOT created here
# (they would sit in plain text in the state file); deploy/scripts/put-secrets.sh adds
# them as SecureStrings.
locals {
  config = {
    ENV            = var.env
    AWS_REGION     = module.compute.region
    SQS_INGEST_URL = module.queue.ingest_url
    SQS_USER_URL   = module.queue.user_url
    DOMAIN         = var.domain
    BACKUP_BUCKET  = module.storage.bucket_name
    LOG_GROUP      = module.monitoring.log_group_name
    TLS_MODE       = var.enable_alb ? "alb" : "caddy"
  }
}

resource "aws_ssm_parameter" "config" {
  for_each = local.config
  name     = "/lung/${var.env}/${each.key}"
  type     = "String"
  value    = each.value
}

output "public_ip" { value = module.compute.public_ip }
output "instance_id" { value = module.compute.instance_id }
output "bucket" { value = module.storage.bucket_name }
output "deploy_role_arn" { value = module.iam.deploy_role_arn }
output "ingest_queue_url" { value = module.queue.ingest_url }
output "user_queue_url" { value = module.queue.user_url }
output "log_group" { value = module.monitoring.log_group_name }
output "alb_dns_name" { value = module.edge.alb_dns_name }
output "rds_endpoint" { value = module.rds.endpoint }

# OFF by default. Managed Postgres (with PostGIS, which RDS supports) for when there are
# enough users to justify ~$15+/month: automated backups, patching, and a Multi-AZ option.
# Switching on means: enable here, restore the latest S3 dump into it, then point
# DATABASE_URL at its endpoint and drop the postgres container.

variable "enabled" {
  type    = bool
  default = false
}
variable "name" { type = string }
variable "vpc_id" { type = string }
variable "private_subnet_ids" { type = list(string) }
variable "app_sg_id" { type = string }
variable "instance_class" {
  type    = string
  default = "db.t4g.micro"
}
variable "multi_az" {
  type    = bool
  default = false
}

locals {
  n = var.enabled ? 1 : 0
}

resource "aws_db_subnet_group" "this" {
  count      = local.n
  name       = "${var.name}-db"
  subnet_ids = var.private_subnet_ids
}

resource "aws_security_group" "db" {
  count  = local.n
  name   = "${var.name}-db"
  vpc_id = var.vpc_id
  ingress {
    description     = "Postgres from the app server only"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [var.app_sg_id]
  }
}

resource "aws_db_instance" "this" {
  count                       = local.n
  identifier                  = "${var.name}-db"
  engine                      = "postgres"
  engine_version              = "17"
  instance_class              = var.instance_class
  allocated_storage           = 20
  max_allocated_storage       = 100
  storage_type                = "gp3"
  storage_encrypted           = true
  db_name                     = "lung"
  username                    = "lung"
  manage_master_user_password = true # password lives in Secrets Manager, never in state
  db_subnet_group_name        = aws_db_subnet_group.this[0].name
  vpc_security_group_ids      = [aws_security_group.db[0].id]
  multi_az                    = var.multi_az
  publicly_accessible         = false
  backup_retention_period     = 7
  deletion_protection         = true
  skip_final_snapshot         = false
  final_snapshot_identifier   = "${var.name}-db-final"
  auto_minor_version_upgrade  = true
}

output "endpoint" { value = var.enabled ? aws_db_instance.this[0].endpoint : null }

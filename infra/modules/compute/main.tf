# The one EC2 server: Amazon Linux 2023 on ARM (Graviton), an Elastic IP for DuckDNS, an
# encrypted root disk, and a separate encrypted data disk for Postgres that survives the
# instance being replaced.

variable "name" { type = string }
variable "env" { type = string }
variable "instance_type" {
  type    = string
  default = "t4g.small"
}
variable "subnet_id" { type = string }
variable "security_group_ids" { type = list(string) }
variable "instance_profile_name" { type = string }
variable "root_gb" {
  type    = number
  default = 20
}
variable "data_gb" {
  type    = number
  default = 10
}
variable "release_bucket" { type = string }
variable "protect" {
  type        = bool
  default     = true
  description = "Stop the instance being terminated by accident (turn off before destroy)"
}

data "aws_ssm_parameter" "al2023_arm" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

data "aws_subnet" "this" {
  id = var.subnet_id
}

data "aws_region" "this" {}

resource "aws_ebs_volume" "data" {
  availability_zone = data.aws_subnet.this.availability_zone
  size              = var.data_gb
  type              = "gp3"
  encrypted         = true
  tags              = { Name = "${var.name}-data" }
  lifecycle {
    prevent_destroy = true # the database lives here; remove this line on purpose to delete
  }
}

resource "aws_instance" "this" {
  ami                     = data.aws_ssm_parameter.al2023_arm.value
  instance_type           = var.instance_type
  subnet_id               = var.subnet_id
  vpc_security_group_ids  = var.security_group_ids
  iam_instance_profile    = var.instance_profile_name
  disable_api_termination = var.protect
  monitoring              = false # basic 5-minute metrics are free

  metadata_options {
    http_tokens                 = "required" # IMDSv2 only
    http_put_response_hop_limit = 2          # containers need the instance role (SQS, S3)
  }

  root_block_device {
    volume_type = "gp3"
    volume_size = var.root_gb
    encrypted   = true
  }

  user_data = templatefile("${path.module}/user_data.sh.tftpl", {
    env            = var.env
    region         = data.aws_region.this.region
    release_bucket = var.release_bucket
    data_volume_id = replace(aws_ebs_volume.data.id, "-", "")
  })

  tags = { Name = var.name, "lung-env" = var.env }

  lifecycle {
    # A newer AMI or edited boot script must not silently replace the server.
    ignore_changes = [ami, user_data]
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf"
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.this.id
}

resource "aws_eip" "this" {
  domain = "vpc"
  tags   = { Name = var.name }
}

resource "aws_eip_association" "this" {
  instance_id   = aws_instance.this.id
  allocation_id = aws_eip.this.id
}

output "instance_id" { value = aws_instance.this.id }
output "instance_arn" { value = aws_instance.this.arn }
output "public_ip" { value = aws_eip.this.public_ip }
output "region" { value = data.aws_region.this.region }

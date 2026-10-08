mock_provider "aws" {
  mock_data "aws_ssm_parameter" {
    defaults = { value = "ami-0123456789abcdef0" }
  }
  mock_data "aws_subnet" {
    defaults = { availability_zone = "ap-south-1a" }
  }
  mock_data "aws_region" {
    defaults = { region = "ap-south-1" }
  }
}

variables {
  name                  = "lung-test"
  env                   = "test"
  subnet_id             = "subnet-123"
  security_group_ids    = ["sg-123"]
  instance_profile_name = "profile"
  release_bucket        = "bucket"
}

run "hardened_instance" {
  command = plan
  assert {
    condition     = aws_instance.this.metadata_options[0].http_tokens == "required"
    error_message = "IMDSv2 must be required"
  }
  assert {
    condition     = aws_instance.this.root_block_device[0].encrypted
    error_message = "the root disk must be encrypted"
  }
  assert {
    condition     = aws_ebs_volume.data.encrypted
    error_message = "the data disk must be encrypted"
  }
  assert {
    condition     = aws_instance.this.tags["lung-env"] == "test"
    error_message = "the deploy role finds the instance by its lung-env tag"
  }
  assert {
    condition     = startswith(aws_instance.this.instance_type, "t4g.")
    error_message = "the images are built for ARM (Graviton)"
  }
}

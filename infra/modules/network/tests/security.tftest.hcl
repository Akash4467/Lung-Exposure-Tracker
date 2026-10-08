mock_provider "aws" {
  mock_data "aws_availability_zones" {
    defaults = { names = ["ap-south-1a", "ap-south-1b", "ap-south-1c"] }
  }
}

variables {
  name = "lung-test"
}

run "only_http_and_https_are_open" {
  command = plan
  assert {
    condition     = length(aws_security_group.web.ingress) == 2
    error_message = "the web security group must have exactly two ingress rules"
  }
  assert {
    condition     = alltrue([for r in aws_security_group.web.ingress : contains([80, 443], r.from_port) && r.from_port == r.to_port])
    error_message = "only ports 80 and 443 may be open (no SSH: use SSM)"
  }
}

run "no_nat_gateway_and_two_azs" {
  command = plan
  assert {
    condition     = length(aws_subnet.public) == 2 && length(aws_subnet.private) == 2
    error_message = "expected public and private subnets in two AZs"
  }
}

# OFF by default. For when the project has a real domain in Route 53 (DuckDNS can't point
# at an ALB or validate an ACM certificate). Then: ALB with an ACM certificate terminates
# TLS and forwards plain HTTP to Caddy on the instance(s), and Route 53 points the domain
# at the ALB. Cost: about $16-20/month.

variable "enabled" {
  type    = bool
  default = false
}
variable "name" { type = string }
variable "vpc_id" { type = string }
variable "public_subnet_ids" { type = list(string) }
variable "instance_ids" { type = list(string) }
variable "instance_sg_id" { type = string }
variable "domain" {
  type    = string
  default = ""
}
variable "route53_zone_id" {
  type    = string
  default = ""
}

locals {
  n = var.enabled ? 1 : 0
}

resource "aws_security_group" "alb" {
  count  = local.n
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "this" {
  count                      = local.n
  name                       = substr("${var.name}-alb", 0, 32)
  load_balancer_type         = "application"
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb[0].id]
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "caddy" {
  count    = local.n
  name     = substr("${var.name}-caddy", 0, 32)
  port     = 80
  protocol = "HTTP"
  vpc_id   = var.vpc_id
  health_check {
    path    = "/health"
    matcher = "200"
  }
}

resource "aws_lb_target_group_attachment" "caddy" {
  for_each         = var.enabled ? toset(var.instance_ids) : toset([])
  target_group_arn = aws_lb_target_group.caddy[0].arn
  target_id        = each.value
  port             = 80
}

resource "aws_acm_certificate" "this" {
  count             = local.n
  domain_name       = var.domain
  validation_method = "DNS"
  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_route53_record" "validation" {
  for_each = var.enabled ? {
    for o in aws_acm_certificate.this[0].domain_validation_options : o.domain_name => o
  } : {}
  zone_id = var.route53_zone_id
  name    = each.value.resource_record_name
  type    = each.value.resource_record_type
  records = [each.value.resource_record_value]
  ttl     = 300
}

resource "aws_acm_certificate_validation" "this" {
  count                   = local.n
  certificate_arn         = aws_acm_certificate.this[0].arn
  validation_record_fqdns = [for r in aws_route53_record.validation : r.fqdn]
}

resource "aws_lb_listener" "https" {
  count             = local.n
  load_balancer_arn = aws_lb.this[0].arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = aws_acm_certificate_validation.this[0].certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.caddy[0].arn
  }
}

resource "aws_lb_listener" "http" {
  count             = local.n
  load_balancer_arn = aws_lb.this[0].arn
  port              = 80
  protocol          = "HTTP"
  default_action {
    type = "redirect"
    redirect {
      port        = "443"
      protocol    = "HTTPS"
      status_code = "HTTP_301"
    }
  }
}

resource "aws_route53_record" "app" {
  count   = local.n
  zone_id = var.route53_zone_id
  name    = var.domain
  type    = "A"
  alias {
    name                   = aws_lb.this[0].dns_name
    zone_id                = aws_lb.this[0].zone_id
    evaluate_target_health = true
  }
}

output "alb_dns_name" { value = var.enabled ? aws_lb.this[0].dns_name : null }
output "alb_sg_id" { value = var.enabled ? aws_security_group.alb[0].id : null }

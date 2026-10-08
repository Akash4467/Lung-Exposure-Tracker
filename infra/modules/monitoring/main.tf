# Logs and the alarms that matter. All within the CloudWatch free tier (10 alarms; app-level
# metrics, alarms and the dashboard are in app.tf).

variable "name" { type = string }
variable "env" { type = string }
variable "log_retention_days" {
  type    = number
  default = 14
}
variable "alarm_email" {
  type    = string
  default = ""
}
variable "dlq_names" { type = list(string) }
variable "queue_names" {
  type    = list(string)
  default = []
}
variable "instance_id" { type = string }

data "aws_region" "this" {}

resource "aws_cloudwatch_log_group" "app" {
  name              = "/lung/${var.env}"
  retention_in_days = var.log_retention_days
}

resource "aws_sns_topic" "alarms" {
  name = "${var.name}-alarms"
}

resource "aws_sns_topic_subscription" "email" {
  count     = var.alarm_email == "" ? 0 : 1
  topic_arn = aws_sns_topic.alarms.arn
  protocol  = "email" # AWS emails a confirmation link first
  endpoint  = var.alarm_email
}

# A message in a dead-letter queue means a job failed 5 times.
resource "aws_cloudwatch_metric_alarm" "dlq" {
  for_each            = toset(var.dlq_names)
  alarm_name          = "${each.key}-not-empty"
  namespace           = "AWS/SQS"
  metric_name         = "ApproximateNumberOfMessagesVisible"
  dimensions          = { QueueName = each.key }
  statistic           = "Maximum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
}

# AWS hardware problem: move the instance to healthy hardware (same IP, same disks).
resource "aws_cloudwatch_metric_alarm" "system_check" {
  alarm_name          = "${var.name}-system-check-failed"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_System"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 2
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [
    "arn:aws:automate:${data.aws_region.this.region}:ec2:recover",
    aws_sns_topic.alarms.arn,
  ]
}

# The OS is stuck: reboot it.
resource "aws_cloudwatch_metric_alarm" "instance_check" {
  alarm_name          = "${var.name}-instance-check-failed"
  namespace           = "AWS/EC2"
  metric_name         = "StatusCheckFailed_Instance"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Maximum"
  period              = 60
  evaluation_periods  = 3
  threshold           = 0
  comparison_operator = "GreaterThanThreshold"
  alarm_actions = [
    "arn:aws:automate:${data.aws_region.this.region}:ec2:reboot",
    aws_sns_topic.alarms.arn,
  ]
}

resource "aws_cloudwatch_metric_alarm" "cpu" {
  alarm_name          = "${var.name}-cpu-high"
  namespace           = "AWS/EC2"
  metric_name         = "CPUUtilization"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Average"
  period              = 300
  evaluation_periods  = 3
  threshold           = 80
  comparison_operator = "GreaterThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

# t4g instances run on CPU credits; running out throttles the whole server.
resource "aws_cloudwatch_metric_alarm" "cpu_credits" {
  alarm_name          = "${var.name}-cpu-credits-low"
  namespace           = "AWS/EC2"
  metric_name         = "CPUCreditBalance"
  dimensions          = { InstanceId = var.instance_id }
  statistic           = "Minimum"
  period              = 300
  evaluation_periods  = 2
  threshold           = 20
  comparison_operator = "LessThanThreshold"
  alarm_actions       = [aws_sns_topic.alarms.arn]
}

output "log_group_name" { value = aws_cloudwatch_log_group.app.name }
output "log_group_arn" { value = aws_cloudwatch_log_group.app.arn }
output "alarm_topic_arn" { value = aws_sns_topic.alarms.arn }

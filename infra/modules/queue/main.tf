# Two SQS queues, each with a dead-letter queue, and the hourly tick from EventBridge
# Scheduler. Same shape as deploy/elasticmq/elasticmq.conf, which mirrors this locally.

variable "name" { type = string }
variable "tick_schedule" {
  type    = string
  default = "rate(1 hour)"
}

locals {
  queues = toset(["ingest-jobs", "user-jobs"])
}

resource "aws_sqs_queue" "dlq" {
  for_each                  = local.queues
  name                      = "${var.name}-${each.key}-dlq"
  message_retention_seconds = 14 * 24 * 3600
  sqs_managed_sse_enabled   = true
}

resource "aws_sqs_queue" "main" {
  for_each                   = local.queues
  name                       = "${var.name}-${each.key}"
  visibility_timeout_seconds = 60
  receive_wait_time_seconds  = 20
  message_retention_seconds  = 4 * 24 * 3600
  sqs_managed_sse_enabled    = true
  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.dlq[each.key].arn
    maxReceiveCount     = 5
  })
}

resource "aws_sqs_queue_redrive_allow_policy" "dlq" {
  for_each  = local.queues
  queue_url = aws_sqs_queue.dlq[each.key].id
  redrive_allow_policy = jsonencode({
    redrivePermission = "byQueue"
    sourceQueueArns   = [aws_sqs_queue.main[each.key].arn]
  })
}

# ---------------------------------------------------------------- hourly tick

data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "${var.name}-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler" {
  role = aws_iam_role.scheduler.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "sqs:SendMessage"
      Resource = aws_sqs_queue.main["ingest-jobs"].arn
    }]
  })
}

resource "aws_scheduler_schedule" "tick" {
  name                = "${var.name}-tick"
  schedule_expression = var.tick_schedule
  flexible_time_window {
    mode = "OFF"
  }
  target {
    arn      = aws_sqs_queue.main["ingest-jobs"].arn
    role_arn = aws_iam_role.scheduler.arn
    input    = jsonencode({ type = "tick" })
    retry_policy {
      maximum_retry_attempts       = 3
      maximum_event_age_in_seconds = 3600
    }
  }
}

output "ingest_url" { value = aws_sqs_queue.main["ingest-jobs"].url }
output "user_url" { value = aws_sqs_queue.main["user-jobs"].url }
output "queue_arns" { value = [for q in aws_sqs_queue.main : q.arn] }
output "dlq_names" { value = [for q in aws_sqs_queue.dlq : q.name] }
output "queue_names" { value = [for q in aws_sqs_queue.main : q.name] }

mock_provider "aws" {
  mock_data "aws_region" {
    defaults = { region = "ap-south-1" }
  }
  mock_resource "aws_sns_topic" {
    defaults = { arn = "arn:aws:sns:ap-south-1:123456789012:lung-test-alarms" }
  }
}

variables {
  name        = "lung-test"
  env         = "test"
  dlq_names   = ["lung-test-ingest-jobs-dlq", "lung-test-user-jobs-dlq"]
  queue_names = ["lung-test-ingest-jobs", "lung-test-user-jobs"]
  instance_id = "i-0123456789abcdef0"
}

run "stays_in_free_tier" {
  command = plan
  assert {
    condition     = (length(aws_cloudwatch_metric_alarm.dlq) + 4 + 3) <= 10
    error_message = "the CloudWatch free tier has 10 alarms"
  }
  assert {
    condition     = length(aws_cloudwatch_log_metric_filter.app) <= 10
    error_message = "the CloudWatch free tier has 10 custom metrics"
  }
}

run "silence_means_stale_air" {
  command = plan
  assert {
    condition     = aws_cloudwatch_metric_alarm.air_stale.treat_missing_data == "breaching"
    error_message = "no fetch log lines at all must raise the stale-air alarm"
  }
  assert {
    condition     = aws_cloudwatch_metric_alarm.air_stale.period * aws_cloudwatch_metric_alarm.air_stale.evaluation_periods >= 7200
    error_message = "the hourly tick needs at least 2 hours before data counts as stale"
  }
}

run "filters_match_the_app_log_fields" {
  command = plan
  assert {
    condition     = strcontains(aws_cloudwatch_log_metric_filter.app["Api5xx"].pattern, "$.status >= 500")
    error_message = "5xx comes from the request log line's status field"
  }
  assert {
    condition     = strcontains(aws_cloudwatch_log_metric_filter.app["UpstreamFailed"].pattern, "$.event = \"openaq_failed\"")
    error_message = "upstream failures are matched by event name"
  }
}

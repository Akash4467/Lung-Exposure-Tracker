# App-level health, read from the app's own JSON logs (structlog: `event`, `level`, ...).
#
# Metric filters turn log lines into metrics, so the app needs no CloudWatch SDK or agent.
# Free tier: 10 custom metrics (7 here), 10 alarms (6 in main.tf + 3 here), 3 dashboards (1).

locals {
  ns = "Lung/${var.env}"

  # Calls to outside services that failed (the app carries on degraded: fallback route,
  # uncorrected air, cached search...). Breakdown by service on the dashboard's log widget.
  upstream_events = [
    "openaq_failed",
    "cpcb_failed",
    "geocode_nominatim_failed",
    "geocode_photon_failed",
    "reverse_nominatim_failed",
    "fcm_send_failed",
    "email_send_failed",
    "route_fallback",
    "route_planner_fallback",
  ]

  metrics = {
    ApiRequests    = { pattern = "{ $.event = \"request\" }", value = "1" }
    Api5xx         = { pattern = "{ $.event = \"request\" && $.status >= 500 }", value = "1" }
    ApiLatencyMs   = { pattern = "{ $.event = \"request\" }", value = "$.ms" }
    AirFetched     = { pattern = "{ $.event = \"fetched\" }", value = "1" }
    JobFailed      = { pattern = "{ $.event = \"job_failed\" }", value = "1" }
    UpstreamFailed = { pattern = "{ ${join(" || ", [for e in local.upstream_events : "$.event = \"${e}\""])} }", value = "1" }
    AlertsSent     = { pattern = "{ $.event = \"alert_sent\" }", value = "1" }
  }
}

resource "aws_cloudwatch_log_metric_filter" "app" {
  for_each       = local.metrics
  name           = "${var.name}-${each.key}"
  log_group_name = aws_cloudwatch_log_group.app.name
  pattern        = each.value.pattern

  metric_transformation {
    name      = each.key
    namespace = local.ns
    value     = each.value.value
    unit      = each.key == "ApiLatencyMs" ? "Milliseconds" : "Count"
  }
}

# The API is answering with server errors.
resource "aws_cloudwatch_metric_alarm" "api_5xx" {
  alarm_name          = "${var.name}-api-5xx"
  alarm_description   = "5 or more 5xx responses in 5 minutes. Logs: filter level = error."
  namespace           = local.ns
  metric_name         = "Api5xx"
  statistic           = "Sum"
  period              = 300
  evaluation_periods  = 1
  threshold           = 5
  comparison_operator = "GreaterThanOrEqualToThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.app]
}

# No air data fetched for 2 hours. The hourly tick always fetches the warm areas (Delhi NCR
# etc.), so silence means the tick, the worker or Open-Meteo is broken and scores are going
# stale. Missing data counts as breaching: that silence is exactly what this is for.
resource "aws_cloudwatch_metric_alarm" "air_stale" {
  alarm_name          = "${var.name}-air-data-stale"
  alarm_description   = "No air fetched for 2 hours: check the worker, the hourly tick and Open-Meteo."
  namespace           = local.ns
  metric_name         = "AirFetched"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 2
  threshold           = 1
  comparison_operator = "LessThanThreshold"
  treat_missing_data  = "breaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  ok_actions          = [aws_sns_topic.alarms.arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.app]
}

# Jobs failing faster than retries can absorb (the DLQ alarm only fires after 5 failures).
resource "aws_cloudwatch_metric_alarm" "jobs_failing" {
  alarm_name          = "${var.name}-jobs-failing"
  alarm_description   = "More than 10 worker jobs failed in an hour. Logs: event = job_failed."
  namespace           = local.ns
  metric_name         = "JobFailed"
  statistic           = "Sum"
  period              = 3600
  evaluation_periods  = 1
  threshold           = 10
  comparison_operator = "GreaterThanThreshold"
  treat_missing_data  = "notBreaching"
  alarm_actions       = [aws_sns_topic.alarms.arn]
  depends_on          = [aws_cloudwatch_log_metric_filter.app]
}

resource "aws_cloudwatch_dashboard" "app" {
  dashboard_name = var.name
  dashboard_body = jsonencode({
    widgets = [
      {
        type = "metric", x = 0, y = 0, width = 12, height = 6
        properties = {
          title  = "API requests and 5xx (per 5 min)"
          region = data.aws_region.this.region
          stat   = "Sum"
          period = 300
          metrics = [
            [local.ns, "ApiRequests"],
            [local.ns, "Api5xx", { color = "#d62728" }],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 0, width = 12, height = 6
        properties = {
          title  = "API response time (ms)"
          region = data.aws_region.this.region
          period = 300
          metrics = [
            [local.ns, "ApiLatencyMs", { stat = "Average", label = "average" }],
            [local.ns, "ApiLatencyMs", { stat = "Maximum", label = "slowest" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 6, width = 12, height = 6
        properties = {
          title  = "Air areas fetched, alerts sent (per hour)"
          region = data.aws_region.this.region
          stat   = "Sum"
          period = 3600
          metrics = [
            [local.ns, "AirFetched"],
            [local.ns, "AlertsSent"],
          ]
        }
      },
      {
        type = "metric", x = 12, y = 6, width = 12, height = 6
        properties = {
          title  = "Failures (per hour)"
          region = data.aws_region.this.region
          stat   = "Sum"
          period = 3600
          metrics = [
            [local.ns, "JobFailed", { color = "#d62728" }],
            [local.ns, "UpstreamFailed", { color = "#ff7f0e" }],
          ]
        }
      },
      {
        type = "metric", x = 0, y = 12, width = 12, height = 6
        properties = {
          title  = "Queue backlog (messages waiting)"
          region = data.aws_region.this.region
          stat   = "Maximum"
          period = 300
          metrics = [
            for q in concat(var.queue_names, var.dlq_names) :
            ["AWS/SQS", "ApproximateNumberOfMessagesVisible", "QueueName", q]
          ]
        }
      },
      {
        type = "metric", x = 12, y = 12, width = 12, height = 6
        properties = {
          title  = "Server CPU % and CPU credits"
          region = data.aws_region.this.region
          period = 300
          metrics = [
            ["AWS/EC2", "CPUUtilization", "InstanceId", var.instance_id, { stat = "Average" }],
            ["AWS/EC2", "CPUCreditBalance", "InstanceId", var.instance_id, { stat = "Minimum", yAxis = "right" }],
          ]
        }
      },
      {
        type = "log", x = 0, y = 18, width = 24, height = 6
        properties = {
          title  = "Warnings and errors by event (last period shown)"
          region = data.aws_region.this.region
          view   = "table"
          query  = "SOURCE '${aws_cloudwatch_log_group.app.name}' | filter level in ['warning', 'error', 'critical'] | stats count(*) as n by event | sort n desc | limit 20"
        }
      },
    ]
  })
}

output "dashboard_name" { value = aws_cloudwatch_dashboard.app.dashboard_name }

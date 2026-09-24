# Log Analytics + Application Insights + the alert rules we actually act on.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
  }
}

resource "azurerm_log_analytics_workspace" "this" {
  name                = "log-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  sku                 = "PerGB2018"
  retention_in_days   = var.retention_in_days
  tags                = var.tags
}

resource "azurerm_application_insights" "this" {
  name                = "appi-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  workspace_id        = azurerm_log_analytics_workspace.this.id
  application_type    = "web"
  sampling_percentage = var.sampling_percentage
  tags                = var.tags
}

resource "azurerm_monitor_action_group" "oncall" {
  name                = "ag-${var.name_prefix}"
  resource_group_name = var.resource_group_name
  short_name          = "baatx"

  dynamic "email_receiver" {
    for_each = var.alert_emails
    content {
      name                    = "email-${email_receiver.key}"
      email_address           = email_receiver.value
      use_common_alert_schema = true
    }
  }

  tags = var.tags
}

# API failure rate
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "api_errors" {
  name                 = "alert-api-5xx-${var.name_prefix}"
  location             = var.location
  resource_group_name  = var.resource_group_name
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [azurerm_application_insights.this.id]
  severity             = 1

  criteria {
    query                   = <<-KQL
      requests
      | where timestamp > ago(15m)
      | summarize failures = countif(success == false), total = count()
      | extend failure_rate = todouble(failures) / todouble(max_of(total, 1)) * 100
      | project failure_rate
    KQL
    time_aggregation_method = "Maximum"
    threshold               = 5
    operator                = "GreaterThan"
    metric_measure_column   = "failure_rate"
  }

  action {
    action_groups = [azurerm_monitor_action_group.oncall.id]
  }
  tags = var.tags
}

# AI / speech / storage pipeline failures surfaced by the worker
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "ai_failures" {
  name                 = "alert-ai-failures-${var.name_prefix}"
  location             = var.location
  resource_group_name  = var.resource_group_name
  evaluation_frequency = "PT5M"
  window_duration      = "PT30M"
  scopes               = [azurerm_application_insights.this.id]
  severity             = 2

  criteria {
    query                   = <<-KQL
      traces
      | where timestamp > ago(30m)
      | where message has_any ("job_failed", "llm_call_failed", "azure_speech_rejected", "audio_delete_failed")
      | summarize failures = count()
    KQL
    time_aggregation_method = "Total"
    threshold               = 10
    operator                = "GreaterThan"
    metric_measure_column   = "failures"
  }

  action {
    action_groups = [azurerm_monitor_action_group.oncall.id]
  }
  tags = var.tags
}

# Authentication failure spike - possible credential stuffing
resource "azurerm_monitor_scheduled_query_rules_alert_v2" "auth_failures" {
  name                 = "alert-auth-failures-${var.name_prefix}"
  location             = var.location
  resource_group_name  = var.resource_group_name
  evaluation_frequency = "PT5M"
  window_duration      = "PT15M"
  scopes               = [azurerm_application_insights.this.id]
  severity             = 2

  criteria {
    query                   = <<-KQL
      requests
      | where timestamp > ago(15m) and name has "/auth/login" and resultCode == "401"
      | summarize failures = count()
    KQL
    time_aggregation_method = "Total"
    threshold               = 50
    operator                = "GreaterThan"
    metric_measure_column   = "failures"
  }

  action {
    action_groups = [azurerm_monitor_action_group.oncall.id]
  }
  tags = var.tags
}

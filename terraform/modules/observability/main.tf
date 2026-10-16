variable "compartment_id" { type = string }
variable "application_id" { type = string }
variable "name" { type = string }
variable "notification_topic_id" { type = string }
resource "oci_logging_log_group" "rotation" {
  compartment_id = var.compartment_id
  display_name   = var.name
}
resource "oci_logging_log" "rotation" {
  display_name       = var.name
  log_group_id       = oci_logging_log_group.rotation.id
  log_type           = "SERVICE"
  is_enabled         = true
  retention_duration = 30
  configuration {
    compartment_id = var.compartment_id
    source {
      category    = "invoke"
      resource    = var.application_id
      service     = "functions"
      source_type = "OCISERVICE"
    }
  }
}
resource "oci_monitoring_alarm" "failed" {
  count                 = var.notification_topic_id == "" ? 0 : 1
  compartment_id        = var.compartment_id
  metric_compartment_id = var.compartment_id
  display_name          = "${var.name}-failed"
  namespace             = "pg_vault_rotation"
  query                 = "RotationFailure[5m].sum() > 0"
  severity              = "CRITICAL"
  is_enabled            = true
  destinations          = [var.notification_topic_id]
  pending_duration      = "PT1M"
}
resource "oci_monitoring_alarm" "overdue" {
  count                 = var.notification_topic_id == "" ? 0 : 1
  compartment_id        = var.compartment_id
  metric_compartment_id = var.compartment_id
  display_name          = "${var.name}-overdue"
  namespace             = "pg_vault_rotation"
  query                 = "RotationOverdue[5m].max() > 0"
  severity              = "CRITICAL"
  is_enabled            = true
  destinations          = [var.notification_topic_id]
  pending_duration      = "PT1M"
}
resource "oci_monitoring_alarm" "monitor_missing" {
  count                 = var.notification_topic_id == "" ? 0 : 1
  compartment_id        = var.compartment_id
  metric_compartment_id = var.compartment_id
  display_name          = "${var.name}-monitor-missing"
  namespace             = "pg_vault_rotation"
  query                 = "MonitorHeartbeat[1m].absent(2h)"
  severity              = "CRITICAL"
  is_enabled            = true
  destinations          = [var.notification_topic_id]
  pending_duration      = "PT1M"
}

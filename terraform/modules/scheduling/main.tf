variable "secret_id" { type = string }
variable "function_id" { type = string }
variable "compartment_id" { type = string }
variable "tenancy_id" { type = string }
variable "name" { type = string }
variable "rotation_days" {
  type = number
  validation {
    condition     = var.rotation_days >= 1 && var.rotation_days <= 360
    error_message = "Vault rotation interval must be between 1 and 360 days."
  }
}
# Do not import a customer's existing secret into Terraform or put its contents in state.
# The CLI applies this proposal via UpdateSecret after explicit schedule approval.
output "proposal" {
  value = {
    secret_id = var.secret_id
    rotation_config = {
      rotation_interval             = "P${var.rotation_days}D"
      is_scheduled_rotation_enabled = true
      target_system_details = {
        target_system_type = "FUNCTION"
        function_id        = var.function_id
      }
    }
  }
}

# Independent monitor continues to run when a Vault rotation invocation is missed.
resource "oci_resource_scheduler_schedule" "monitor" {
  compartment_id     = var.compartment_id
  display_name       = "${var.name}-monitor"
  action             = "START_RESOURCE"
  recurrence_type    = "CRON"
  recurrence_details = "*/15 * * * *"
  state              = "ACTIVE"
  resources {
    id = var.function_id
    parameters {
      parameter_type = "BODY"
      value          = [jsonencode({ action = "monitor" })]
    }
  }
}
resource "oci_identity_dynamic_group" "monitor" {
  compartment_id = var.tenancy_id
  name           = "${var.name}-monitor"
  description    = "Only the monitoring schedule"
  matching_rule  = "ALL {resource.type = 'resourceschedule', resource.id = '${oci_resource_scheduler_schedule.monitor.id}'}"
}
resource "oci_identity_policy" "monitor" {
  compartment_id = var.tenancy_id
  name           = "${var.name}-monitor"
  description    = "Monitoring schedule can invoke the selected function"
  statements     = ["Allow dynamic-group ${oci_identity_dynamic_group.monitor.name} to use functions-family in compartment id ${var.compartment_id} where target.function.id = '${var.function_id}'"]
}

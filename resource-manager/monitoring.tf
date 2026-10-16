# Independent monitor continues to run when a Vault rotation invocation is missed.
resource "oci_resource_scheduler_schedule" "monitor" {
  compartment_id     = var.compartment_ocid
  display_name       = "${var.name}-monitor"
  action             = "START_RESOURCE"
  recurrence_type    = "CRON"
  recurrence_details = "*/15 * * * *"
  state              = "ACTIVE"
  resources {
    id = module.function.id
    parameters {
      parameter_type = "BODY"
      value          = [jsonencode({ action = "monitor" })]
    }
  }
}
resource "oci_identity_dynamic_group" "monitor" {
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-monitor"
  description    = "Only the monitoring schedule"
  matching_rule  = "ALL {resource.type = 'resourceschedule', resource.id = '${oci_resource_scheduler_schedule.monitor.id}'}"
}
resource "oci_identity_policy" "monitor" {
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-monitor"
  description    = "Monitoring schedule can invoke the selected function"
  statements     = ["Allow dynamic-group ${oci_identity_dynamic_group.monitor.name} to use functions-family in compartment id ${var.compartment_ocid} where target.function.id = '${module.function.id}'"]
}

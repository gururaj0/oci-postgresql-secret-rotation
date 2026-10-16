variable "tenancy_id" { type = string }
variable "compartment_id" { type = string }
variable "function_id" { type = string }
variable "secret_id" { type = string }
variable "bucket_name" { type = string }
variable "name" { type = string }
resource "oci_identity_dynamic_group" "rotation" {
  compartment_id = var.tenancy_id
  name           = var.name
  description    = "Only the selected PostgreSQL rotation Function"
  matching_rule  = "ALL {resource.type = 'fnfunc', resource.id = '${var.function_id}'}"
}
resource "oci_identity_policy" "rotation" {
  compartment_id = var.tenancy_id
  name           = var.name
  description    = "Restricted secret update and operation journal access"
  statements = [
    "Allow dynamic-group ${oci_identity_dynamic_group.rotation.name} to read secret-bundles in tenancy where target.secret.id = '${var.secret_id}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.rotation.name} to manage secrets in tenancy where all {target.secret.id = '${var.secret_id}', any {request.permission = 'SECRET_READ', request.permission = 'SECRET_UPDATE'}}",
    "Allow dynamic-group ${oci_identity_dynamic_group.rotation.name} to manage secret-versions in tenancy where all {target.secret.id = '${var.secret_id}', request.permission = 'SECRET_VERSION_INSPECT'}",
    "Allow dynamic-group ${oci_identity_dynamic_group.rotation.name} to manage objects in compartment id ${var.compartment_id} where target.bucket.name = '${var.bucket_name}'",
    "Allow dynamic-group ${oci_identity_dynamic_group.rotation.name} to use metrics in compartment id ${var.compartment_id} where target.metrics.namespace = 'pg_vault_rotation'",
    "Allow dynamic-group ${oci_identity_dynamic_group.secret.name} to use functions-family in compartment id ${var.compartment_id} where target.function.id = '${var.function_id}'"
  ]
}
resource "oci_identity_dynamic_group" "secret" {
  compartment_id = var.tenancy_id
  name           = "${var.name}-secret"
  description    = "Selected Vault secret may invoke the rotation Function"
  matching_rule  = "ALL {resource.type = 'vaultsecret', resource.id = '${var.secret_id}'}"
}

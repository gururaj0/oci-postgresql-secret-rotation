variable "compartment_id" { type = string }
variable "name" { type = string }
variable "create" {
  type    = bool
  default = false
}
# Optional bootstrap only. Secret values are never passed to Terraform.
resource "oci_kms_vault" "new" {
  count          = var.create ? 1 : 0
  compartment_id = var.compartment_id
  display_name   = var.name
  vault_type     = "DEFAULT"
  lifecycle { prevent_destroy = true }
}
resource "oci_kms_key" "new" {
  count               = var.create ? 1 : 0
  compartment_id      = var.compartment_id
  display_name        = var.name
  management_endpoint = oci_kms_vault.new[0].management_endpoint
  key_shape {
    algorithm = "AES"
    length    = 32
  }
  lifecycle { prevent_destroy = true }
}
output "vault_id" { value = try(oci_kms_vault.new[0].id, null) }
output "key_id" { value = try(oci_kms_key.new[0].id, null) }

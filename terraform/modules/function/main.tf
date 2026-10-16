variable "compartment_id" { type = string }
variable "name" { type = string }
variable "subnet_id" { type = string }
variable "image" { type = string }
variable "config" { type = any }
variable "shape" {
  type    = string
  default = "GENERIC_X86"
}
variable "network_security_group_ids" {
  type    = list(string)
  default = []
}
resource "oci_functions_application" "rotation" {
  compartment_id             = var.compartment_id
  display_name               = var.name
  subnet_ids                 = [var.subnet_id]
  shape                      = var.shape
  network_security_group_ids = var.network_security_group_ids
  config                     = { ROTATION_CONFIG = jsonencode(var.config) }
}
resource "oci_functions_function" "rotation" {
  application_id = oci_functions_application.rotation.id
  display_name   = var.name
  source_details {
    source_type  = "CONTAINER_IMAGE"
    image        = split("@", var.image)[0]
    image_digest = try(split("@", var.image)[1], null)
  }
  memory_in_mbs      = 256
  timeout_in_seconds = 300
}
output "id" { value = oci_functions_function.rotation.id }
output "application_id" { value = oci_functions_application.rotation.id }

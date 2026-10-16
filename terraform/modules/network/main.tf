variable "subnet_id" { type = string }
data "oci_core_subnet" "selected" { subnet_id = var.subnet_id }
output "subnet_id" {
  value = data.oci_core_subnet.selected.id
  precondition {
    condition     = data.oci_core_subnet.selected.prohibit_public_ip_on_vnic
    error_message = "Select an existing private subnet with service gateway/NAT access to OCI APIs and DB routing."
  }
}

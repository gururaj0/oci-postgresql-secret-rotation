variable "tenancy_ocid" { type = string }
variable "compartment_ocid" { type = string }
variable "region" { type = string }
variable "db_system_id" { type = string }
variable "secret_id" { type = string }
variable "subnet_id" { type = string }
variable "db_nsg_id" {
  type        = string
  description = "An existing NSG already attached to the selected PostgreSQL system."
}
variable "database" {
  type    = string
  default = "postgres"
}
variable "username" {
  type        = string
  description = "Existing application LOGIN role matching the Vault secret."
}
variable "name" {
  type    = string
  default = "pg-vault-rotation"
  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{2,39}$", var.name))
    error_message = "Use 3–40 lowercase letters, numbers or hyphens, starting with a letter."
  }
}
variable "enable_automatic_rotation" {
  type    = bool
  default = false
}
variable "rotation_days" {
  type    = number
  default = 30
  validation {
    condition     = var.rotation_days >= 1 && var.rotation_days <= 360 && floor(var.rotation_days) == var.rotation_days
    error_message = "Choose a whole number of days between 1 and 360."
  }
}
variable "notification_topic_id" {
  type    = string
  default = ""
}
variable "build_revision" {
  type        = string
  default     = "1"
  description = "Change this value to rebuild the image, for example after a base-image security update."
}

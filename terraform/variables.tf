variable "tenancy_id" { type = string }
variable "region" { type = string }
variable "profile" {
  type    = string
  default = "DEFAULT"
}
variable "compartment_id" { type = string }
variable "db_system_id" { type = string }
variable "secret_id" { type = string }
variable "subnet_id" { type = string }
variable "state_namespace" { type = string }
variable "state_bucket" { type = string }
variable "function_image" {
  type = string
  validation {
    condition     = can(regex("@sha256:[a-f0-9]{64}$", var.function_image))
    error_message = "Pin the customer-built OCIR image by digest."
  }
}
variable "runtime_config" {
  # Enumerate permitted settings so credential content cannot enter Function config/state.
  type = object({
    tenancy_id            = string
    region                = string
    compartment_id        = string
    db_system_id          = string
    host                  = string
    database              = string
    username              = string
    secret_id             = string
    subnet_id             = string
    state_namespace       = string
    state_bucket          = string
    ca_file               = string
    function_image        = string
    port                  = number
    rotation_days         = number
    credential_type       = string
    function_id           = string
    notification_topic_id = string
    vault_id              = string
  })
  validation {
    condition     = var.runtime_config.credential_type == "application"
    error_message = "Only the tested application-role strategy can be deployed."
  }
}
variable "notification_topic_id" {
  type    = string
  default = ""
}
variable "create_state_bucket" {
  type    = bool
  default = true
}
variable "name" {
  type    = string
  default = "pg-vault-rotation"
}
variable "create_vault" {
  type    = bool
  default = false
}

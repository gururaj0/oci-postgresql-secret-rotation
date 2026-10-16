terraform {
  required_version = ">= 1.6.0, < 2.0.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "9.9.0"
    }
  }
}
provider "oci" {
  region              = var.region
  tenancy_ocid        = var.tenancy_id
  config_file_profile = var.profile
}
module "vault" {
  source         = "./modules/vault"
  compartment_id = var.compartment_id
  name           = var.name
  create         = var.create_vault
}

module "network" {
  source    = "./modules/network"
  subnet_id = var.subnet_id
}

resource "oci_objectstorage_bucket" "journal" {
  count          = var.create_state_bucket ? 1 : 0
  compartment_id = var.compartment_id
  namespace      = var.state_namespace
  name           = var.state_bucket
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  storage_tier   = "Standard"
  lifecycle { prevent_destroy = true }
}

module "function" {
  source         = "./modules/function"
  compartment_id = var.compartment_id
  name           = var.name
  subnet_id      = module.network.subnet_id
  image          = var.function_image
  config         = var.runtime_config
}

module "iam" {
  source         = "./modules/iam"
  tenancy_id     = var.tenancy_id
  compartment_id = var.compartment_id
  function_id    = module.function.id
  secret_id      = var.secret_id
  bucket_name    = var.state_bucket
  name           = var.name
}

module "observability" {
  source                = "./modules/observability"
  compartment_id        = var.compartment_id
  application_id        = module.function.application_id
  name                  = var.name
  notification_topic_id = var.notification_topic_id
}

module "scheduling" {
  source         = "./modules/scheduling"
  secret_id      = var.secret_id
  function_id    = module.function.id
  rotation_days  = var.runtime_config.rotation_days
  compartment_id = var.compartment_id
  tenancy_id     = var.tenancy_id
  name           = var.name
}

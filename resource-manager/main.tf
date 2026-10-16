terraform {
  required_version = ">= 1.5.0, < 2.0.0"
  required_providers {
    oci = {
      source  = "oracle/oci"
      version = "9.9.0"
    }
  }
}
# Resource Manager supplies authentication. No API keys or local profiles are inputs.
provider "oci" { region = var.region }
data "oci_identity_regions" "all" {}
data "oci_identity_tenancy" "selected" { tenancy_id = var.tenancy_ocid }
locals {
  home_region = one([for r in data.oci_identity_regions.all.regions : r.name if r.key == data.oci_identity_tenancy.selected.home_region_key])
  region_key  = lower(one([for r in data.oci_identity_regions.all.regions : r.key if r.name == var.region]))
}
provider "oci" {
  alias  = "home"
  region = local.home_region
}
data "oci_objectstorage_namespace" "selected" { compartment_id = var.tenancy_ocid }
data "oci_psql_db_system" "selected" { db_system_id = var.db_system_id }
data "oci_psql_db_system_connection_detail" "selected" { db_system_id = var.db_system_id }
data "oci_core_subnet" "selected" { subnet_id = var.subnet_id }
data "oci_core_network_security_group" "database" { network_security_group_id = var.db_nsg_id }

resource "terraform_data" "preflight" {
  input = { db = var.db_system_id, subnet = var.subnet_id, nsg = var.db_nsg_id, username = var.username }
  lifecycle {
    precondition {
      condition     = data.oci_psql_db_system.selected.compartment_id == var.compartment_ocid && data.oci_psql_db_system.selected.state == "ACTIVE"
      error_message = "Select an ACTIVE PostgreSQL system in the deployment compartment."
    }
    precondition {
      condition     = var.username != data.oci_psql_db_system.selected.admin_username
      error_message = "Use an existing application role; managed-administrator rotation is not supported."
    }
    precondition {
      condition     = data.oci_core_subnet.selected.prohibit_public_ip_on_vnic && data.oci_core_subnet.selected.vcn_id == data.oci_core_network_security_group.database.vcn_id && contains(data.oci_psql_db_system.selected.network_details[0].nsg_ids, var.db_nsg_id)
      error_message = "Select a private Function subnet in the database NSG's VCN and an NSG already attached to this database."
    }
  }
}
resource "oci_artifacts_container_repository" "rotation" {
  compartment_id = var.compartment_ocid
  display_name   = var.name
  is_public      = false
}
resource "oci_identity_policy" "image_pull" {
  provider       = oci.home
  compartment_id = var.tenancy_ocid
  name           = "${var.name}-image-pull"
  description    = "Functions service can read only this rotation image repository"
  statements     = ["Allow service faas to read repos in compartment id ${var.compartment_ocid} where target.repo.name = '${oci_artifacts_container_repository.rotation.display_name}'"]
}
locals {
  # The packaging script includes only allowlisted source files here.
  source_hash = sha256(join("", [for f in sort(tolist(fileset("${path.module}/bundle", "**"))) : filesha256("${path.module}/bundle/${f}")]))
  image_tag   = "build-${substr(sha256(join(":", [local.source_hash, data.oci_psql_db_system_connection_detail.selected.ca_certificate, var.build_revision, filesha256("${path.module}/scripts/runner.py")])), 0, 24)}"
  registry    = "${local.region_key}.ocir.io"
  image       = "${local.registry}/${data.oci_objectstorage_namespace.selected.namespace}/${oci_artifacts_container_repository.rotation.display_name}:${local.image_tag}"
}
resource "terraform_data" "image" {
  triggers_replace = [local.image, local.source_hash]
  depends_on       = [terraform_data.preflight]
  provisioner "local-exec" {
    command     = "python3 scripts/runner.py build"
    working_dir = path.module
    environment = {
      ROTATION_REGION   = var.region
      ROTATION_IMAGE    = local.image
      ROTATION_REGISTRY = local.registry
      ROTATION_CA       = data.oci_psql_db_system_connection_detail.selected.ca_certificate
    }
  }
}
data "oci_artifacts_container_images" "built" {
  compartment_id = var.compartment_ocid
  repository_id  = oci_artifacts_container_repository.rotation.id
  version        = local.image_tag
  depends_on     = [terraform_data.image]
}
locals {
  image_digest = one(data.oci_artifacts_container_images.built.container_image_collection[0].items).digest
  pinned_image = "${local.image}@${local.image_digest}"
  config = {
    tenancy_id      = var.tenancy_ocid, region = var.region, compartment_id = var.compartment_ocid
    db_system_id    = var.db_system_id, host = data.oci_psql_db_system_connection_detail.selected.primary_db_endpoint[0].fqdn
    database        = var.database, username = var.username, secret_id = var.secret_id, subnet_id = var.subnet_id
    state_namespace = data.oci_objectstorage_namespace.selected.namespace, state_bucket = oci_objectstorage_bucket.journal.name
    ca_file         = "/function/certs/postgresql-ca.pem", function_image = local.pinned_image
    port            = data.oci_psql_db_system_connection_detail.selected.primary_db_endpoint[0].port, rotation_days = var.rotation_days
    credential_type = "application", function_id = "", notification_topic_id = var.notification_topic_id, vault_id = ""
  }
}
resource "oci_objectstorage_bucket" "journal" {
  compartment_id = var.compartment_ocid
  namespace      = data.oci_objectstorage_namespace.selected.namespace
  name           = "${var.name}-journal"
  access_type    = "NoPublicAccess"
  versioning     = "Enabled"
  lifecycle { prevent_destroy = true }
}
resource "oci_core_network_security_group" "function" {
  compartment_id = var.compartment_ocid
  vcn_id         = data.oci_core_subnet.selected.vcn_id
  display_name   = "${var.name}-function"
}
resource "oci_core_network_security_group_security_rule" "database" {
  network_security_group_id = var.db_nsg_id
  direction                 = "INGRESS"
  protocol                  = "6"
  source_type               = "NETWORK_SECURITY_GROUP"
  source                    = oci_core_network_security_group.function.id
  tcp_options {
    destination_port_range {
      min = local.config.port
      max = local.config.port
    }
  }
  depends_on = [terraform_data.preflight]
}
resource "oci_core_network_security_group_security_rule" "https" {
  network_security_group_id = oci_core_network_security_group.function.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination_type          = "CIDR_BLOCK"
  destination               = "0.0.0.0/0"
  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}
resource "oci_core_network_security_group_security_rule" "postgres" {
  network_security_group_id = oci_core_network_security_group.function.id
  direction                 = "EGRESS"
  protocol                  = "6"
  destination_type          = "NETWORK_SECURITY_GROUP"
  destination               = var.db_nsg_id
  tcp_options {
    destination_port_range {
      min = local.config.port
      max = local.config.port
    }
  }
}
module "function" {
  source                     = "../terraform/modules/function"
  compartment_id             = var.compartment_ocid
  name                       = var.name
  subnet_id                  = var.subnet_id
  image                      = local.pinned_image
  config                     = local.config
  network_security_group_ids = [oci_core_network_security_group.function.id]
  depends_on                 = [oci_identity_policy.image_pull]
}
module "iam" {
  source         = "../terraform/modules/iam"
  providers      = { oci = oci.home }
  compartment_id = var.compartment_ocid
  tenancy_id     = var.tenancy_ocid
  name           = var.name
  function_id    = module.function.id
  secret_id      = var.secret_id
  bucket_name    = oci_objectstorage_bucket.journal.name
}
module "observability" {
  source                = "../terraform/modules/observability"
  compartment_id        = var.compartment_ocid
  name                  = var.name
  application_id        = module.function.application_id
  notification_topic_id = var.notification_topic_id
}
resource "terraform_data" "console_rotation" {
  triggers_replace = [module.function.id, var.secret_id, var.rotation_days, var.enable_automatic_rotation, local.pinned_image, sha256(jsonencode(local.config)), filesha256("${path.module}/scripts/runner.py")]
  depends_on       = [module.iam, module.observability, oci_identity_policy.monitor, oci_core_network_security_group_security_rule.database, oci_core_network_security_group_security_rule.https, oci_core_network_security_group_security_rule.postgres]
  provisioner "local-exec" {
    command     = "python3 scripts/runner.py configure"
    working_dir = path.module
    environment = {
      ROTATION_REGION      = var.region
      ROTATION_FUNCTION_ID = module.function.id
      ROTATION_SECRET_ID   = var.secret_id
      ROTATION_DAYS        = tostring(var.rotation_days)
      ROTATION_ENABLED     = tostring(var.enable_automatic_rotation)
    }
  }
}

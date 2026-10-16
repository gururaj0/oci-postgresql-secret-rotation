output "function_id" { value = module.function.id }
output "function_image" { value = local.pinned_image }
output "secret_id" { value = var.secret_id }
output "automatic_rotation_enabled" { value = var.enable_automatic_rotation }
output "next_step" {
  value      = "Open the selected Vault secret and choose Rotate. Verify a newer CURRENT version and a fresh application login."
  depends_on = [terraform_data.console_rotation]
}

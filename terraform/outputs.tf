output "function_id" { value = module.function.id }
output "new_vault_id" { value = module.vault.vault_id }
output "new_key_id" { value = module.vault.key_id }
output "schedule_proposal" { value = module.scheduling.proposal }
output "next_step" { value = "Set function_id in rotation.yaml; run validate, Function validate, then schedule --confirm after application refresh acceptance." }

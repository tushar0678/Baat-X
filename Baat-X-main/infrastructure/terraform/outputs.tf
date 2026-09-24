output "api_url" {
  description = "Public HTTPS endpoint for the BaatX API."
  value       = module.container_app.api_url
}
output "resource_group" { value = azurerm_resource_group.this.name }
output "key_vault_uri" { value = module.keyvault.vault_uri }
output "postgres_fqdn" { value = module.postgres.fqdn }
output "storage_account" { value = module.storage.account_name }
output "managed_identity_client_id" { value = azurerm_user_assigned_identity.app.client_id }

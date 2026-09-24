output "id" { value = azurerm_key_vault.this.id }
output "vault_uri" { value = azurerm_key_vault.this.vault_uri }
output "secret_ids" {
  value = { for k, v in azurerm_key_vault_secret.items : k => v.versionless_id }
}

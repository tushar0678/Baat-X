output "server_id" { value = azurerm_postgresql_flexible_server.this.id }
output "fqdn" { value = azurerm_postgresql_flexible_server.this.fqdn }
output "database_name" { value = azurerm_postgresql_flexible_server_database.baatx.name }
output "connection_string" {
  value = format(
    "postgresql+asyncpg://%s:%s@%s:5432/%s?ssl=require",
    var.admin_username,
    var.admin_password,
    azurerm_postgresql_flexible_server.this.fqdn,
    azurerm_postgresql_flexible_server_database.baatx.name,
  )
  sensitive = true
}

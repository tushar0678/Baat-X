output "vnet_id" { value = azurerm_virtual_network.this.id }
output "apps_subnet_id" { value = azurerm_subnet.apps.id }
output "postgres_subnet_id" { value = azurerm_subnet.postgres.id }
output "private_endpoint_subnet_id" { value = azurerm_subnet.private_endpoints.id }
output "postgres_dns_zone_id" { value = azurerm_private_dns_zone.postgres.id }
output "blob_dns_zone_id" { value = azurerm_private_dns_zone.blob.id }

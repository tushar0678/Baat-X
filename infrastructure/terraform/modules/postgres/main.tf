# Azure Database for PostgreSQL Flexible Server, VNet-injected (no public access).

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
  }
}

resource "azurerm_postgresql_flexible_server" "this" {
  name                          = "psql-${var.name_prefix}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  version                       = "16"
  delegated_subnet_id           = var.subnet_id
  private_dns_zone_id           = var.private_dns_zone_id
  public_network_access_enabled = false

  administrator_login    = var.admin_username
  administrator_password = var.admin_password

  sku_name   = var.sku_name
  storage_mb = var.storage_mb
  zone       = "1"

  backup_retention_days        = var.backup_retention_days
  geo_redundant_backup_enabled = var.geo_redundant_backup

  dynamic "high_availability" {
    for_each = var.high_availability ? [1] : []
    content {
      mode                      = "ZoneRedundant"
      standby_availability_zone = "2"
    }
  }

  maintenance_window {
    day_of_week  = 0
    start_hour   = 18 # 23:30 IST
    start_minute = 0
  }

  tags = var.tags

  lifecycle {
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "baatx" {
  name      = "baatx"
  server_id = azurerm_postgresql_flexible_server.this.id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

# Enforce TLS for every client connection.
resource "azurerm_postgresql_flexible_server_configuration" "require_ssl" {
  name      = "require_secure_transport"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "ON"
}

# Log slow queries only - never statement contents by default.
resource "azurerm_postgresql_flexible_server_configuration" "log_min_duration" {
  name      = "log_min_duration_statement"
  server_id = azurerm_postgresql_flexible_server.this.id
  value     = "2000"
}

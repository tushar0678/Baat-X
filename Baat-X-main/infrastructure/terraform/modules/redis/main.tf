# Azure Cache for Redis - queue transport (arq) and rate-limit counters.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
  }
}

resource "azurerm_redis_cache" "this" {
  name                          = "redis-${var.name_prefix}"
  location                      = var.location
  resource_group_name           = var.resource_group_name
  capacity                      = var.capacity
  family                        = var.family
  sku_name                      = var.sku_name
  minimum_tls_version           = "1.2"
  non_ssl_port_enabled          = false
  public_network_access_enabled = var.public_network_access

  redis_configuration {
    maxmemory_policy = "noeviction" # queued jobs must never be evicted
  }

  tags = var.tags
}

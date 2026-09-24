# Private Blob Storage for TEMPORARY audio.
# Defence in depth: no public access, TLS 1.2+, infrastructure encryption,
# a private endpoint, and a lifecycle rule that deletes anything the app
# somehow failed to delete itself.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
  }
}

resource "azurerm_storage_account" "this" {
  name                              = var.storage_account_name
  resource_group_name               = var.resource_group_name
  location                          = var.location
  account_tier                      = "Standard"
  account_replication_type          = var.replication_type
  account_kind                      = "StorageV2"
  min_tls_version                   = "TLS1_2"
  https_traffic_only_enabled        = true
  allow_nested_items_to_be_public   = false
  shared_access_key_enabled         = var.shared_access_key_enabled
  public_network_access_enabled     = false
  infrastructure_encryption_enabled = true

  blob_properties {
    delete_retention_policy {
      days = 1 # minimum soft-delete; audio must not linger
    }
    container_delete_retention_policy {
      days = 1
    }
  }

  identity {
    type = "SystemAssigned"
  }

  network_rules {
    default_action = "Deny"
    bypass         = ["AzureServices"]
  }

  tags = var.tags
}

resource "azurerm_storage_container" "temp_audio" {
  name                  = var.container_name
  storage_account_id    = azurerm_storage_account.this.id
  container_access_type = "private"
}

resource "azurerm_storage_management_policy" "lifecycle" {
  storage_account_id = azurerm_storage_account.this.id

  rule {
    name    = "delete-temp-audio"
    enabled = true
    filters {
      prefix_match = ["${var.container_name}/"]
      blob_types   = ["blockBlob"]
    }
    actions {
      base_blob {
        delete_after_days_since_creation_greater_than = var.audio_retention_days
      }
      snapshot {
        delete_after_days_since_creation_greater_than = 1
      }
    }
  }
}

resource "azurerm_private_endpoint" "blob" {
  name                = "pe-blob-${var.name_prefix}"
  location            = var.location
  resource_group_name = var.resource_group_name
  subnet_id           = var.private_endpoint_subnet_id

  private_service_connection {
    name                           = "psc-blob"
    private_connection_resource_id = azurerm_storage_account.this.id
    subresource_names              = ["blob"]
    is_manual_connection           = false
  }

  private_dns_zone_group {
    name                 = "blob-dns"
    private_dns_zone_ids = [var.blob_dns_zone_id]
  }

  tags = var.tags
}

# The app writes and deletes audio with its Managed Identity - no account keys.
resource "azurerm_role_assignment" "app_blob_contributor" {
  scope                = azurerm_storage_account.this.id
  role_definition_name = "Storage Blob Data Contributor"
  principal_id         = var.app_principal_id
}

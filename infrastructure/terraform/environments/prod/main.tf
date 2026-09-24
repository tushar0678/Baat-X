# prod environment wrapper. State lives in Azure Storage; never local.

terraform {
  required_version = ">= 1.9.0"

  backend "azurerm" {
    resource_group_name  = "rg-baatx-tfstate"
    storage_account_name = "stbaatxtfstate"
    container_name       = "tfstate"
    key                  = "prod.terraform.tfstate"
    use_azuread_auth     = true
  }
}

module "baatx" {
  source = "../../"

  environment               = "prod"
  location                  = var.location
  storage_account_name      = var.storage_account_name
  key_vault_name            = var.key_vault_name
  container_registry_server = var.container_registry_server
  container_registry_id     = var.container_registry_id
  api_image                 = var.api_image
  worker_image              = var.worker_image
  azure_openai_endpoint     = var.azure_openai_endpoint
  azure_openai_resource_id  = var.azure_openai_resource_id
  azure_speech_region       = var.azure_speech_region
  azure_speech_key          = var.azure_speech_key
  alert_emails              = var.alert_emails

  # Production: HA database, geo-redundant backups, zone-redundant ACA.
  postgres_sku                   = "GP_Standard_D4ds_v5"
  postgres_storage_mb            = 262144
  postgres_backup_retention_days = 35
  postgres_geo_redundant         = true
  postgres_high_availability     = true
  redis_sku                      = "Standard"
  redis_capacity                 = 2
  storage_replication_type       = "ZRS"
  api_min_replicas               = 2
  api_max_replicas               = 30
  worker_min_replicas            = 2
  worker_max_replicas            = 30
  log_retention_days             = 90
  vnet_address_space             = "10.43.0.0/16"
}

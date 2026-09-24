# staging environment wrapper. State lives in Azure Storage; never local.

terraform {
  required_version = ">= 1.9.0"

  backend "azurerm" {
    resource_group_name  = "rg-baatx-tfstate"
    storage_account_name = "stbaatxtfstate"
    container_name       = "tfstate"
    key                  = "staging.terraform.tfstate"
    use_azuread_auth     = true
  }
}

module "baatx" {
  source = "../../"

  environment               = "staging"
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

  postgres_sku                   = "GP_Standard_D2ds_v5"
  postgres_backup_retention_days = 7
  api_min_replicas               = 1
  api_max_replicas               = 4
  worker_min_replicas            = 1
  worker_max_replicas            = 4
  vnet_address_space             = "10.42.0.0/16"
}

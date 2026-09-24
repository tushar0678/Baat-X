# dev environment wrapper. State lives in Azure Storage; never local.

terraform {
  required_version = ">= 1.9.0"

  backend "azurerm" {
    resource_group_name  = "rg-baatx-tfstate"
    storage_account_name = "stbaatxtfstate"
    container_name       = "tfstate"
    key                  = "dev.terraform.tfstate"
    use_azuread_auth     = true
  }
}

module "baatx" {
  source = "../../"

  environment               = "dev"
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

  # Small and cheap; scale-to-zero is fine for development.
  postgres_sku        = "B_Standard_B1ms"
  postgres_storage_mb = 32768
  redis_sku           = "Basic"
  api_min_replicas    = 0
  api_max_replicas    = 2
  worker_min_replicas = 0
  worker_max_replicas = 2
  log_level           = "DEBUG"
  vnet_address_space  = "10.41.0.0/16"
}

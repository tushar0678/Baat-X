# Root composition for a single BaatX environment.
# Used by environments/{dev,staging,prod} through a thin wrapper.

terraform {
  required_version = ">= 1.9.0"
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
    random  = { source = "hashicorp/random", version = "~> 3.6" }
  }
}

provider "azurerm" {
  features {
    key_vault {
      purge_soft_delete_on_destroy    = false
      recover_soft_deleted_key_vaults = true
    }
  }
}

locals {
  name_prefix = "baatx-${var.environment}"
  tags = merge(
    {
      product     = "baatx"
      environment = var.environment
      managed_by  = "terraform"
    },
    var.extra_tags,
  )
}

resource "azurerm_resource_group" "this" {
  name     = "rg-${local.name_prefix}"
  location = var.location
  tags     = local.tags
}

resource "azurerm_user_assigned_identity" "app" {
  name                = "id-${local.name_prefix}"
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  tags                = local.tags
}

# Generated in Terraform and stored only in Key Vault - never printed or committed.
resource "random_password" "postgres_admin" {
  length           = 32
  special          = true
  override_special = "!#$%&*()-_=+[]{}<>:?"
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

module "networking" {
  source              = "./modules/networking"
  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  address_space       = var.vnet_address_space
  tags                = local.tags
}

module "monitoring" {
  source              = "./modules/monitoring"
  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  retention_in_days   = var.log_retention_days
  alert_emails        = var.alert_emails
  tags                = local.tags
}

module "postgres" {
  source                = "./modules/postgres"
  name_prefix           = local.name_prefix
  location              = var.location
  resource_group_name   = azurerm_resource_group.this.name
  subnet_id             = module.networking.postgres_subnet_id
  private_dns_zone_id   = module.networking.postgres_dns_zone_id
  admin_password        = random_password.postgres_admin.result
  sku_name              = var.postgres_sku
  storage_mb            = var.postgres_storage_mb
  backup_retention_days = var.postgres_backup_retention_days
  geo_redundant_backup  = var.postgres_geo_redundant
  high_availability     = var.postgres_high_availability
  tags                  = local.tags
}

module "redis" {
  source              = "./modules/redis"
  name_prefix         = local.name_prefix
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  sku_name            = var.redis_sku
  capacity            = var.redis_capacity
  tags                = local.tags
}

module "storage" {
  source                     = "./modules/storage"
  name_prefix                = local.name_prefix
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  storage_account_name       = var.storage_account_name
  private_endpoint_subnet_id = module.networking.private_endpoint_subnet_id
  blob_dns_zone_id           = module.networking.blob_dns_zone_id
  app_principal_id           = azurerm_user_assigned_identity.app.principal_id
  replication_type           = var.storage_replication_type
  tags                       = local.tags
}

module "keyvault" {
  source              = "./modules/keyvault"
  key_vault_name      = var.key_vault_name
  location            = var.location
  resource_group_name = azurerm_resource_group.this.name
  app_principal_id    = azurerm_user_assigned_identity.app.principal_id
  purge_protection    = var.environment == "prod"
  tags                = local.tags

  secrets = {
    "database-url"                  = module.postgres.connection_string
    "redis-url"                     = module.redis.connection_string
    "jwt-secret"                    = random_password.jwt_secret.result
    "azure-speech-key"              = var.azure_speech_key
    "appinsights-connection-string" = module.monitoring.app_insights_connection_string
    "whatsapp-access-token"         = var.whatsapp_access_token
  }
}

module "container_app" {
  source                     = "./modules/container_app"
  name_prefix                = local.name_prefix
  location                   = var.location
  resource_group_name        = azurerm_resource_group.this.name
  environment                = var.environment
  log_level                  = var.log_level
  log_analytics_workspace_id = module.monitoring.workspace_id
  infrastructure_subnet_id   = module.networking.apps_subnet_id
  zone_redundant             = var.environment == "prod"
  managed_identity_id        = azurerm_user_assigned_identity.app.id
  managed_identity_client_id = azurerm_user_assigned_identity.app.client_id
  container_registry_server  = var.container_registry_server
  api_image                  = var.api_image
  worker_image               = var.worker_image
  key_vault_secret_ids       = module.keyvault.secret_ids
  storage_blob_endpoint      = module.storage.primary_blob_endpoint
  storage_container          = module.storage.container_name
  azure_openai_endpoint      = var.azure_openai_endpoint
  azure_openai_deployment    = var.azure_openai_deployment
  azure_speech_region        = var.azure_speech_region
  api_min_replicas           = var.api_min_replicas
  api_max_replicas           = var.api_max_replicas
  worker_min_replicas        = var.worker_min_replicas
  worker_max_replicas        = var.worker_max_replicas
  tags                       = local.tags
}

# The API and worker call Azure OpenAI with the same Managed Identity.
resource "azurerm_role_assignment" "openai_user" {
  count                = var.azure_openai_resource_id == "" ? 0 : 1
  scope                = var.azure_openai_resource_id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

resource "azurerm_role_assignment" "acr_pull" {
  count                = var.container_registry_id == "" ? 0 : 1
  scope                = var.container_registry_id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.app.principal_id
}

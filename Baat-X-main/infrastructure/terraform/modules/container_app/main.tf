# Azure Container Apps: the API (HTTP, autoscaled on concurrency) and the
# background worker (scaled on Redis queue depth via KEDA).
#
# Secrets are Key Vault references resolved at runtime with the user-assigned
# Managed Identity, so no secret value is ever stored in the app definition.

terraform {
  required_providers {
    azurerm = { source = "hashicorp/azurerm", version = "~> 4.20" }
  }
}

resource "azurerm_container_app_environment" "this" {
  name                           = "cae-${var.name_prefix}"
  location                       = var.location
  resource_group_name            = var.resource_group_name
  log_analytics_workspace_id     = var.log_analytics_workspace_id
  infrastructure_subnet_id       = var.infrastructure_subnet_id
  internal_load_balancer_enabled = false
  zone_redundancy_enabled        = var.zone_redundant
  tags                           = var.tags
}

locals {
  base_env = [
    { name = "ENVIRONMENT", value = var.environment },
    { name = "LOG_LEVEL", value = var.log_level },
    { name = "LOG_JSON", value = "true" },
    { name = "AZURE_CLIENT_ID", value = var.managed_identity_client_id },
    { name = "AZURE_STORAGE_ACCOUNT_URL", value = var.storage_blob_endpoint },
    { name = "AZURE_STORAGE_CONTAINER", value = var.storage_container },
    { name = "STORAGE_PROVIDER", value = "azure_blob" },
    { name = "STT_PROVIDER", value = "azure_speech" },
    { name = "LLM_PROVIDER", value = "azure_openai" },
    { name = "AZURE_OPENAI_ENDPOINT", value = var.azure_openai_endpoint },
    { name = "AZURE_OPENAI_DEPLOYMENT", value = var.azure_openai_deployment },
    { name = "AZURE_OPENAI_USE_MANAGED_IDENTITY", value = "true" },
    { name = "AZURE_SPEECH_REGION", value = var.azure_speech_region },
    # Privacy defaults are pinned here so they cannot drift per revision.
    { name = "DELETE_AUDIO_AFTER_PROCESSING", value = "true" },
    { name = "RETAIN_TRANSCRIPTS", value = "false" },
  ]

  secret_env = [
    { name = "DATABASE_URL", secret_name = "database-url" },
    { name = "REDIS_URL", secret_name = "redis-url" },
    { name = "JWT_SECRET", secret_name = "jwt-secret" },
    { name = "AZURE_SPEECH_KEY", secret_name = "azure-speech-key" },
    { name = "APPLICATIONINSIGHTS_CONNECTION_STRING", secret_name = "appinsights-connection-string" },
  ]
}

resource "azurerm_container_app" "api" {
  name                         = "ca-api-${var.name_prefix}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.managed_identity_id]
  }

  registry {
    server   = var.container_registry_server
    identity = var.managed_identity_id
  }

  dynamic "secret" {
    for_each = var.key_vault_secret_ids
    content {
      name                = secret.key
      key_vault_secret_id = secret.value
      identity            = var.managed_identity_id
    }
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"
    # TLS is terminated by Container Apps; plain HTTP is rejected.
    allow_insecure_connections = false

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    min_replicas = var.api_min_replicas
    max_replicas = var.api_max_replicas

    container {
      name   = "api"
      image  = var.api_image
      cpu    = var.api_cpu
      memory = var.api_memory

      dynamic "env" {
        for_each = local.base_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name        = env.value.name
          secret_name = env.value.secret_name
        }
      }

      liveness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/health"
        initial_delay           = 15
        interval_seconds        = 30
        failure_count_threshold = 3
      }

      readiness_probe {
        transport               = "HTTP"
        port                    = 8000
        path                    = "/ready"
        interval_seconds        = 15
        failure_count_threshold = 3
      }
    }

    http_scale_rule {
      name                = "http-concurrency"
      concurrent_requests = "50"
    }
  }
}

resource "azurerm_container_app" "worker" {
  name                         = "ca-worker-${var.name_prefix}"
  container_app_environment_id = azurerm_container_app_environment.this.id
  resource_group_name          = var.resource_group_name
  revision_mode                = "Single"
  tags                         = var.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [var.managed_identity_id]
  }

  registry {
    server   = var.container_registry_server
    identity = var.managed_identity_id
  }

  dynamic "secret" {
    for_each = var.key_vault_secret_ids
    content {
      name                = secret.key
      key_vault_secret_id = secret.value
      identity            = var.managed_identity_id
    }
  }

  template {
    min_replicas = var.worker_min_replicas
    max_replicas = var.worker_max_replicas

    container {
      name   = "worker"
      image  = var.worker_image
      cpu    = var.worker_cpu
      memory = var.worker_memory

      dynamic "env" {
        for_each = local.base_env
        content {
          name  = env.value.name
          value = env.value.value
        }
      }

      dynamic "env" {
        for_each = local.secret_env
        content {
          name        = env.value.name
          secret_name = env.value.secret_name
        }
      }
    }

    # Scale out when audio jobs pile up; scale back when the queue drains.
    custom_scale_rule {
      name             = "redis-queue-depth"
      custom_rule_type = "redis"
      metadata = {
        listName       = "arq:queue"
        listLength     = "5"
        enableTLS      = "true"
        databaseIndex  = "0"
        addressFromEnv = "REDIS_HOST_PORT"
      }
    }
  }
}

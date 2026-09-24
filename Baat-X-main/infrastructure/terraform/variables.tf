variable "environment" {
  type = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging or prod."
  }
}
variable "location" {
  type    = string
  default = "centralindia"
}
variable "vnet_address_space" {
  type    = string
  default = "10.40.0.0/16"
}
variable "log_level" {
  type    = string
  default = "INFO"
}
variable "log_retention_days" {
  type    = number
  default = 30
}
variable "alert_emails" {
  type    = list(string)
  default = []
}

# --- data services ---
variable "postgres_sku" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}
variable "postgres_storage_mb" {
  type    = number
  default = 65536
}
variable "postgres_backup_retention_days" {
  type    = number
  default = 14
}
variable "postgres_geo_redundant" {
  type    = bool
  default = false
}
variable "postgres_high_availability" {
  type    = bool
  default = false
}
variable "redis_sku" {
  type    = string
  default = "Standard"
}
variable "redis_capacity" {
  type    = number
  default = 1
}
variable "storage_account_name" { type = string }
variable "storage_replication_type" {
  type    = string
  default = "LRS"
}
variable "key_vault_name" { type = string }

# --- containers ---
variable "container_registry_server" { type = string }
variable "container_registry_id" {
  type    = string
  default = ""
}
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "api_min_replicas" {
  type    = number
  default = 1
}
variable "api_max_replicas" {
  type    = number
  default = 10
}
variable "worker_min_replicas" {
  type    = number
  default = 1
}
variable "worker_max_replicas" {
  type    = number
  default = 10
}

# --- AI ---
variable "azure_openai_endpoint" { type = string }
variable "azure_openai_deployment" {
  type    = string
  default = "gpt-4o"
}
variable "azure_openai_resource_id" {
  type    = string
  default = ""
}
variable "azure_speech_region" {
  type    = string
  default = "centralindia"
}
variable "azure_speech_key" {
  type      = string
  sensitive = true
  default   = ""
}
variable "whatsapp_access_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "extra_tags" {
  type    = map(string)
  default = {}
}

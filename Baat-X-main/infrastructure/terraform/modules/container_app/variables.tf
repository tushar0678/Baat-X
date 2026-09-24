variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "environment" { type = string }
variable "log_level" {
  type    = string
  default = "INFO"
}
variable "log_analytics_workspace_id" { type = string }
variable "infrastructure_subnet_id" { type = string }
variable "zone_redundant" {
  type    = bool
  default = false
}
variable "managed_identity_id" { type = string }
variable "managed_identity_client_id" { type = string }
variable "container_registry_server" { type = string }
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "key_vault_secret_ids" {
  type        = map(string)
  description = "secretName => Key Vault versionless secret id"
}
variable "storage_blob_endpoint" { type = string }
variable "storage_container" { type = string }
variable "azure_openai_endpoint" { type = string }
variable "azure_openai_deployment" {
  type    = string
  default = "gpt-4o"
}
variable "azure_speech_region" { type = string }
variable "api_min_replicas" {
  type    = number
  default = 1
}
variable "api_max_replicas" {
  type    = number
  default = 10
}
variable "api_cpu" {
  type    = number
  default = 0.5
}
variable "api_memory" {
  type    = string
  default = "1Gi"
}
variable "worker_min_replicas" {
  type    = number
  default = 1
}
variable "worker_max_replicas" {
  type    = number
  default = 10
}
variable "worker_cpu" {
  type    = number
  default = 1.0
}
variable "worker_memory" {
  type    = string
  default = "2Gi"
}
variable "tags" {
  type    = map(string)
  default = {}
}

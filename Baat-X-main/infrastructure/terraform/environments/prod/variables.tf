variable "location" {
  type    = string
  default = "centralindia"
}
variable "storage_account_name" { type = string }
variable "key_vault_name" { type = string }
variable "container_registry_server" { type = string }
variable "container_registry_id" {
  type    = string
  default = ""
}
variable "api_image" { type = string }
variable "worker_image" { type = string }
variable "azure_openai_endpoint" { type = string }
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
variable "alert_emails" {
  type    = list(string)
  default = []
}

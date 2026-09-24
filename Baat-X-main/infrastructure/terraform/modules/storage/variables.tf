variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "storage_account_name" {
  type        = string
  description = "Globally unique, 3-24 lowercase alphanumeric characters."
}
variable "container_name" {
  type    = string
  default = "baatx-temp-audio"
}
variable "replication_type" {
  type    = string
  default = "LRS"
}
variable "shared_access_key_enabled" {
  type    = bool
  default = false
}
variable "audio_retention_days" {
  type        = number
  default     = 1
  description = "Backstop only - the application deletes audio right after processing."
}
variable "private_endpoint_subnet_id" { type = string }
variable "blob_dns_zone_id" { type = string }
variable "app_principal_id" { type = string }
variable "tags" {
  type    = map(string)
  default = {}
}

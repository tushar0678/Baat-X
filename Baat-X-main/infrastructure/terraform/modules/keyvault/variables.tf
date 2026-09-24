variable "key_vault_name" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "app_principal_id" { type = string }
variable "purge_protection" {
  type    = bool
  default = true
}
variable "public_network_access" {
  type    = bool
  default = false
}
variable "secrets" {
  type      = map(string)
  default   = {}
  sensitive = true
}
variable "tags" {
  type    = map(string)
  default = {}
}

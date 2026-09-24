variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "subnet_id" { type = string }
variable "private_dns_zone_id" { type = string }
variable "admin_username" {
  type    = string
  default = "baatxadmin"
}
variable "admin_password" {
  type      = string
  sensitive = true
}
variable "sku_name" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}
variable "storage_mb" {
  type    = number
  default = 65536
}
variable "backup_retention_days" {
  type    = number
  default = 14
}
variable "geo_redundant_backup" {
  type    = bool
  default = false
}
variable "high_availability" {
  type    = bool
  default = false
}
variable "tags" {
  type    = map(string)
  default = {}
}

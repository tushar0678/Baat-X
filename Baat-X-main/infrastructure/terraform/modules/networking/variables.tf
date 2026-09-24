variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "address_space" {
  type        = string
  default     = "10.40.0.0/16"
  description = "VNet CIDR. Container Apps needs a large free block."
}
variable "tags" {
  type    = map(string)
  default = {}
}

variable "name_prefix" { type = string }
variable "location" { type = string }
variable "resource_group_name" { type = string }
variable "retention_in_days" {
  type    = number
  default = 30
}
variable "sampling_percentage" {
  type    = number
  default = 100
}
variable "alert_emails" {
  type    = list(string)
  default = []
}
variable "tags" {
  type    = map(string)
  default = {}
}

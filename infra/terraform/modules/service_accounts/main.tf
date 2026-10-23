# One service account per workload (security.md §3.8), with only the project roles it needs.

variable "project_id" {
  type = string
}

variable "prefix" {
  type = string
}

variable "accounts" {
  type = map(object({
    display_name = string
    roles        = list(string)
  }))
}

locals {
  bindings = merge([
    for name, acct in var.accounts : {
      for r in acct.roles : "${name}|${r}" => { name = name, role = r }
    }
  ]...)
}

resource "google_service_account" "this" {
  for_each     = var.accounts
  project      = var.project_id
  account_id   = "${var.prefix}-${each.key}"
  display_name = each.value.display_name
}

resource "google_project_iam_member" "this" {
  for_each = local.bindings
  project  = var.project_id
  role     = each.value.role
  member   = "serviceAccount:${google_service_account.this[each.value.name].email}"
}

output "emails" {
  value = { for k, sa in google_service_account.this : k => sa.email }
}

output "members" {
  value = { for k, sa in google_service_account.this : k => "serviceAccount:${sa.email}" }
}

output "ids" {
  value = { for k, sa in google_service_account.this : k => sa.name }
}

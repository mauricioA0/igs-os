# APIs the stack needs. disable_on_destroy=false: tearing down an env never disables an API
# another env (or the console) still uses.

variable "project_id" {
  type = string
}

variable "services" {
  type = list(string)
}

resource "google_project_service" "this" {
  for_each           = toset(var.services)
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

output "enabled" {
  value = [for s in google_project_service.this : s.service]
}

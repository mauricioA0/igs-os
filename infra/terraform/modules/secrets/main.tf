# Secret Manager secrets. Terraform owns the *names* and who can read them. Values:
# - generated here (random): DB passwords, the Temporal payload codec key, the proposal signing key.
#   They land in Terraform state, which lives in a private, versioned bucket (bootstrap/).
# - set by a person, never in code or state: openai-api-key (`gcloud secrets versions add`).

terraform {
  required_providers {
    random = {
      source = "hashicorp/random"
    }
  }
}

variable "project_id" {
  type = string
}

variable "manual_secrets" {
  type        = list(string)
  description = "Secrets whose versions are added by hand (e.g. openai-api-key)."
}

variable "generated_secrets" {
  type        = list(string)
  description = "Secrets Terraform fills with a random 48-char password."
  default     = []
}

variable "generated_keys" {
  type        = list(string)
  description = "Secrets Terraform fills with 32 random bytes, base64 (AES-256 keys)."
  default     = []
}

variable "accessors" {
  type        = map(list(string))
  description = "secret id -> members allowed roles/secretmanager.secretAccessor."
  default     = {}
}

locals {
  all = toset(concat(var.manual_secrets, var.generated_secrets, var.generated_keys))
  bindings = merge([
    for secret, members in var.accessors : {
      for m in members : "${secret}|${m}" => { secret = secret, member = m }
    }
  ]...)
}

resource "google_secret_manager_secret" "this" {
  for_each  = local.all
  project   = var.project_id
  secret_id = each.value

  replication {
    auto {}
  }

  labels = {
    app = "igs-os"
  }
}

resource "random_password" "generated" {
  for_each = toset(var.generated_secrets)
  length   = 48
  special  = false
}

resource "google_secret_manager_secret_version" "generated" {
  for_each    = toset(var.generated_secrets)
  secret      = google_secret_manager_secret.this[each.value].id
  secret_data = random_password.generated[each.value].result
}

resource "random_bytes" "key" {
  for_each = toset(var.generated_keys)
  length   = 32
}

resource "google_secret_manager_secret_version" "key" {
  for_each    = toset(var.generated_keys)
  secret      = google_secret_manager_secret.this[each.value].id
  secret_data = random_bytes.key[each.value].base64
}

resource "google_secret_manager_secret_iam_member" "accessor" {
  for_each  = local.bindings
  project   = var.project_id
  secret_id = google_secret_manager_secret.this[each.value.secret].secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = each.value.member
}

output "ids" {
  value = { for k, s in google_secret_manager_secret.this : k => s.secret_id }
}

output "generated_values" {
  value     = { for k, p in random_password.generated : k => p.result }
  sensitive = true
}

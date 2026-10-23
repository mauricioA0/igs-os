# Keyless CI/CD: GitHub Actions OIDC tokens from mauricioA0/igs-os (and only that repo)
# impersonate the deployer service account. No JSON keys anywhere.

variable "project_id" {
  type = string
}

variable "pool_id" {
  type    = string
  default = "github"
}

variable "repository" {
  type        = string
  description = "owner/name allowed to deploy."
}

variable "deployer_service_account_id" {
  type        = string
  description = "Full resource name: projects/<p>/serviceAccounts/<email>."
}

variable "allowed_refs" {
  type        = list(string)
  default     = ["refs/heads/main"]
  description = "Git refs allowed to impersonate (tags/branches)."
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = var.pool_id
  display_name              = "GitHub Actions"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-oidc"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.actor"      = "assertion.actor"
  }

  # Reject tokens from any other repository or ref before they reach IAM.
  attribute_condition = format(
    "assertion.repository == '%s' && assertion.ref in [%s]",
    var.repository,
    join(", ", [for r in var.allowed_refs : "'${r}'"]),
  )

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "deployer" {
  service_account_id = var.deployer_service_account_id
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.repository}"
}

# Value for google-github-actions/auth `workload_identity_provider`.
output "provider_name" {
  value = google_iam_workload_identity_pool_provider.github.name
}

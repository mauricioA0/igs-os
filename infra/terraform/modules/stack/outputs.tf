output "api_url" {
  value = module.core.uri
}

output "models_url" {
  value = module.models.uri
}

output "image_prefix" {
  value = module.registry.image_prefix
}

output "gke_cluster" {
  value = module.gke.name
}

output "app_sql_connection_name" {
  value = module.sql_app.connection_name
}

output "temporal_sql_host" {
  value     = local.temporal_sql_host
  sensitive = true
}

output "documents_bucket" {
  value = google_storage_bucket.documents.name
}

output "github_workload_identity_provider" {
  value = module.github.provider_name
}

output "deployer_service_account" {
  value = module.sa.emails["deployer"]
}

output "service_accounts" {
  value = module.sa.emails
}

output "vector_store" {
  value = module.vector_search.store
}

output "digest_job" {
  value       = var.enable_daily_digest ? module.digest[0].job_name : null
  description = "Cloud Run job of the morning digest (null while disabled)."
}

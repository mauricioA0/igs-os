output "api_url" {
  value = module.stack.api_url
}

output "image_prefix" {
  value = module.stack.image_prefix
}

output "gke_cluster" {
  value = module.stack.gke_cluster
}

output "github_workload_identity_provider" {
  value = module.stack.github_workload_identity_provider
}

output "deployer_service_account" {
  value = module.stack.deployer_service_account
}

output "documents_bucket" {
  value = module.stack.documents_bucket
}

output "vector_store" {
  value = module.stack.vector_store
}

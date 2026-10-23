# Prod: separate HA Cloud SQL for the app and Temporal, warm API, Vertex Vector Search.
module "stack" {
  source = "../../modules/stack"

  project_id      = var.project_id
  region          = var.region
  env             = "prod"
  billing_account = var.billing_account
  alert_email     = var.alert_email
  budget_usd      = 2500
  web_origins     = var.web_origins

  demo_mode            = false
  shared_sql           = false
  sql_edition          = "ENTERPRISE"
  app_sql_tier         = "db-custom-2-8192"
  temporal_sql_tier    = "db-custom-4-16384"
  sql_ha               = true
  sql_disk_gb          = 50
  sql_pitr             = true
  core_min_instances   = 2
  core_max_instances   = 50
  models_min_instances = 1
  models_gpu           = true
  enable_vector_search = true

  gke_authorized_networks = var.gke_authorized_networks
  deletion_protection     = true
}

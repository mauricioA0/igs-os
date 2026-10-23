# Demo: the public portfolio deployment. Lowest idle cost; everything scales to zero except
# the shared Cloud SQL and the Temporal pods (Spot, set in infra/helm).
module "stack" {
  source = "../../modules/stack"

  project_id = var.project_id
  # Outputs of the first apply / the GKE internal LB (stable once created).
  temporal_address = "10.10.0.7:7233"
  public_api_url   = "https://igs-demo-core-fujfenyt5a-uc.a.run.app"
  region           = var.region
  env              = "demo"
  billing_account  = var.billing_account
  alert_email      = var.alert_email
  budget_usd       = 150
  web_origins      = var.web_origins

  demo_mode            = true
  shared_sql           = true
  app_sql_tier         = "db-g1-small"
  sql_ha               = false
  sql_disk_gb          = 20
  sql_pitr             = false
  core_min_instances   = 0
  models_min_instances = 0
  models_gpu           = false
  enable_vector_search = false # pgvector on the app Cloud SQL

  gke_authorized_networks = var.gke_authorized_networks
  deletion_protection     = false # demo can be torn down and recreated
}

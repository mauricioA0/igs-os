# The whole IGS OS footprint in one project. envs/demo and envs/prod differ only in variables.

terraform {
  required_providers {
    google = {
      source = "hashicorp/google"
    }
    random = {
      source = "hashicorp/random"
    }
  }
}

locals {
  name   = "igs-${var.env}"
  labels = { app = "igs-os", env = var.env }

  apis = [
    "artifactregistry.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "compute.googleapis.com",
    "container.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "cloudtrace.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "servicenetworking.googleapis.com",
    "sqladmin.googleapis.com",
    "storage.googleapis.com",
    "billingbudgets.googleapis.com",
    "sts.googleapis.com",
  ]

  observability_roles = [
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/cloudtrace.agent",
  ]
}

data "google_project" "this" {
  project_id = var.project_id
}

module "apis" {
  source     = "../project_services"
  project_id = var.project_id
  services   = local.apis
}

module "network" {
  source     = "../network"
  project_id = var.project_id
  region     = var.region
  name       = local.name
  depends_on = [module.apis]
}

module "registry" {
  source        = "../registry"
  project_id    = var.project_id
  region        = var.region
  repository_id = local.name
  depends_on    = [module.apis]
}

# ---------------------------------------------------------------- identities

module "sa" {
  source     = "../service_accounts"
  project_id = var.project_id
  prefix     = local.name
  accounts = {
    core = {
      display_name = "IGS OS core API (Cloud Run)"
      roles = concat(local.observability_roles, [
        "roles/cloudsql.client",
        "roles/cloudsql.instanceUser",
      ])
    }
    worker = {
      display_name = "IGS OS Temporal workers (GKE)"
      roles = concat(local.observability_roles, [
        "roles/cloudsql.client",
        "roles/cloudsql.instanceUser",
      ])
    }
    models = {
      display_name = "IGS OS embeddings + reranker (Cloud Run)"
      roles        = local.observability_roles
    }
    temporal = {
      display_name = "Temporal server (GKE)"
      roles        = concat(local.observability_roles, ["roles/cloudsql.client"])
    }
    deployer = {
      display_name = "GitHub Actions deployer (WIF)"
      roles = [
        "roles/artifactregistry.writer",
        "roles/run.developer",
        "roles/container.developer",
      ]
    }
  }
  depends_on = [module.apis]
}

# Pausing/resuming the demo (scripts/deploy/demo-pause.sh) changes the Cloud SQL activation
# policy. A narrow custom role instead of roles/cloudsql.editor (which can also create/clone).
resource "google_project_iam_custom_role" "deployer_sql_activation" {
  project     = var.project_id
  role_id     = "igs_${replace(var.env, "-", "_")}_sql_activation"
  title       = "IGS ${var.env} — Cloud SQL start/stop"
  description = "Lets the deployer pause and resume the demo database."
  permissions = ["cloudsql.instances.get", "cloudsql.instances.update"]
}

resource "google_project_iam_member" "deployer_sql_activation" {
  project = var.project_id
  role    = google_project_iam_custom_role.deployer_sql_activation.id
  member  = module.sa.members["deployer"]
}

# The deployer may act as the runtime SAs (to deploy Cloud Run revisions/jobs), nothing more.
resource "google_service_account_iam_member" "deployer_acts_as" {
  for_each           = toset(["core", "worker", "models"])
  service_account_id = module.sa.ids[each.value]
  role               = "roles/iam.serviceAccountUser"
  member             = module.sa.members["deployer"]
}

# GKE Workload Identity: Kubernetes SAs -> Google SAs (names match infra/helm).
resource "google_service_account_iam_member" "wi_worker" {
  service_account_id = module.sa.ids["worker"]
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespaces.workers}/igs-worker]"
  depends_on         = [module.gke]
}

resource "google_service_account_iam_member" "wi_temporal" {
  service_account_id = module.sa.ids["temporal"]
  role               = "roles/iam.workloadIdentityUser"
  member             = "serviceAccount:${var.project_id}.svc.id.goog[${var.k8s_namespaces.temporal}/temporal]"
  depends_on         = [module.gke]
}

module "github" {
  source                      = "../github_wif"
  project_id                  = var.project_id
  pool_id                     = "${local.name}-github"
  repository                  = var.github_repository
  deployer_service_account_id = module.sa.ids["deployer"]
  depends_on                  = [module.apis]
}

# ---------------------------------------------------------------- secrets

module "secrets" {
  source     = "../secrets"
  project_id = var.project_id
  manual_secrets = [
    "openai-api-key",
  ]
  generated_secrets = [
    "${local.name}-app-db-password",
    "${local.name}-temporal-db-password",
    "igs-proposal-signing-key",
    "igs-proxy-shared-secret",
  ]
  generated_keys = [
    "igs-temporal-codec-key",
  ]
  accessors = {
    "openai-api-key"                     = [module.sa.members["core"], module.sa.members["worker"]]
    "igs-proposal-signing-key"           = [module.sa.members["core"]]
    "igs-proxy-shared-secret"            = [module.sa.members["core"]]
    "igs-temporal-codec-key"             = [module.sa.members["core"], module.sa.members["worker"]]
    "${local.name}-temporal-db-password" = [module.sa.members["temporal"]]
  }
  depends_on = [module.apis]
}

# ---------------------------------------------------------------- data

locals {
  app_db_user      = "igs_login"
  temporal_db_user = "temporal"
  app_databases    = ["igs"]
  temporal_dbs     = ["temporal", "temporal_visibility"]
}

module "sql_app" {
  source                      = "../cloudsql"
  project_id                  = var.project_id
  region                      = var.region
  name                        = var.shared_sql ? "${local.name}-pg" : "${local.name}-app-pg"
  network_id                  = module.network.network_id
  private_services_connection = module.network.private_services_connection
  tier                        = var.app_sql_tier
  edition                     = var.sql_edition
  high_availability           = var.sql_ha
  disk_size_gb                = var.sql_disk_gb
  point_in_time_recovery      = var.sql_pitr
  deletion_protection         = var.deletion_protection
  databases                   = var.shared_sql ? concat(local.app_databases, local.temporal_dbs) : local.app_databases
  iam_service_accounts        = [module.sa.emails["core"], module.sa.emails["worker"]]
  builtin_users = merge(
    { (local.app_db_user) = module.secrets.generated_values["${local.name}-app-db-password"] },
    var.shared_sql ? { (local.temporal_db_user) = module.secrets.generated_values["${local.name}-temporal-db-password"] } : {},
  )
}

module "sql_temporal" {
  count                       = var.shared_sql ? 0 : 1
  source                      = "../cloudsql"
  project_id                  = var.project_id
  region                      = var.region
  name                        = "${local.name}-temporal-pg"
  network_id                  = module.network.network_id
  private_services_connection = module.network.private_services_connection
  tier                        = var.temporal_sql_tier
  edition                     = var.sql_edition
  high_availability           = var.sql_ha
  disk_size_gb                = var.sql_disk_gb * 2
  point_in_time_recovery      = var.sql_pitr
  deletion_protection         = var.deletion_protection
  max_connections             = 400
  databases                   = local.temporal_dbs
  builtin_users = {
    (local.temporal_db_user) = module.secrets.generated_values["${local.name}-temporal-db-password"]
  }
}

locals {
  temporal_sql_host = var.shared_sql ? module.sql_app.private_ip : module.sql_temporal[0].private_ip
}

# DATABASE_URL for the core API / workers (password user that SET ROLEs to igs_app for RLS).
resource "google_secret_manager_secret" "database_url" {
  project   = var.project_id
  secret_id = "igs-core-database-url"
  labels    = local.labels
  replication {
    auto {}
  }
  depends_on = [module.apis]
}

resource "google_secret_manager_secret_version" "database_url" {
  secret = google_secret_manager_secret.database_url.id
  secret_data = format(
    "postgresql+asyncpg://%s:%s@%s:5432/igs?ssl=require",
    local.app_db_user,
    module.secrets.generated_values["${local.name}-app-db-password"],
    module.sql_app.private_ip,
  )
}

resource "google_secret_manager_secret_iam_member" "database_url" {
  for_each  = toset(["core", "worker"])
  project   = var.project_id
  secret_id = google_secret_manager_secret.database_url.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = module.sa.members[each.value]
}

# RAG source documents (ingestion reads, the API uploads).
resource "google_storage_bucket" "documents" {
  project                     = var.project_id
  name                        = "${var.project_id}-${local.name}-documents"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = !var.deletion_protection
  labels                      = local.labels

  versioning {
    enabled = true
  }
}

resource "google_storage_bucket_iam_member" "documents" {
  for_each = {
    core   = "roles/storage.objectCreator"
    worker = "roles/storage.objectViewer"
  }
  bucket = google_storage_bucket.documents.name
  role   = each.value
  member = module.sa.members[each.key]
}

module "vector_search" {
  source         = "../vector_search"
  project_id     = var.project_id
  enabled        = var.enable_vector_search
  writer_members = [module.sa.members["worker"]]
  reader_members = [module.sa.members["core"]]
}

# ---------------------------------------------------------------- compute

module "gke" {
  source              = "../gke_autopilot"
  project_id          = var.project_id
  region              = var.region
  name                = local.name
  network             = module.network.network_id
  subnetwork          = module.network.subnet_id
  pods_range_name     = module.network.pods_range_name
  services_range_name = module.network.services_range_name
  authorized_networks = var.gke_authorized_networks
  deletion_protection = var.deletion_protection
}

module "models" {
  source          = "../cloud_run_service"
  project_id      = var.project_id
  region          = var.region
  name            = "${local.name}-models"
  image           = var.bootstrap_image
  service_account = module.sa.emails["models"]
  internal_only   = true
  invokers        = [module.sa.members["core"], module.sa.members["worker"]]
  cpu             = "4"
  memory          = var.models_gpu ? "16Gi" : "8Gi"
  gpu             = var.models_gpu
  min_instances   = var.models_min_instances
  max_instances   = var.models_gpu ? 1 : 3
  concurrency     = 8
  port            = 8080
  env = {
    HF_HUB_OFFLINE = "1"
  }
}

module "core" {
  source          = "../cloud_run_service"
  project_id      = var.project_id
  region          = var.region
  name            = "${local.name}-core"
  image           = var.bootstrap_image
  service_account = module.sa.emails["core"]
  public          = true
  cpu             = "1"
  memory          = "1Gi"
  min_instances   = var.core_min_instances
  max_instances   = var.core_max_instances
  concurrency     = 80
  port            = 8080
  network         = module.network.network_id
  subnetwork      = module.network.subnet_id
  env = {
    IGS_ENVIRONMENT        = "production"
    IGS_DEMO_MODE          = tostring(var.demo_mode)
    IGS_DB_APP_ROLE        = "igs_app"
    IGS_TEMPORAL_ADDRESS   = var.temporal_address
    IGS_TEMPORAL_NAMESPACE = "igs"
    IGS_MODELS_URL         = module.models.uri
    IGS_VECTOR_STORE       = module.vector_search.store
    IGS_CORS_ORIGINS       = jsonencode(var.web_origins) # pydantic list[str] from JSON
    IGS_LLM_MODELS         = jsonencode(var.llm_models)
    IGS_MODELS_TIMEOUT     = "240" # models scale to zero; a cold start loads ~4.5 GB of weights
    # Deployment-wide model spend fuse, shared with the workers (igs_common.llm.budget).
    IGS_LLM_DAILY_BUDGET_USD  = var.llm_daily_budget_usd
    IGS_LLM_MAX_OUTPUT_TOKENS = "2000"
    IGS_TRUSTED_PROXY_HOPS    = "1" # Cloud Run's front end appends exactly one X-Forwarded-For hop
    # MCP behind the public URL (DNS-rebinding protection checks Host/Origin).
    IGS_MCP_PUBLIC_URL      = "${var.public_api_url}/mcp"
    IGS_MCP_ISSUER_URL      = var.public_api_url
    IGS_MCP_ALLOWED_HOSTS   = jsonencode([replace(var.public_api_url, "https://", "")])
    IGS_MCP_ALLOWED_ORIGINS = jsonencode(concat([var.public_api_url], var.web_origins))
  }
  secret_env = {
    IGS_DATABASE_URL        = google_secret_manager_secret.database_url.secret_id
    OPENAI_API_KEY          = module.secrets.ids["openai-api-key"]
    IGS_TEMPORAL_CODEC_KEY  = module.secrets.ids["igs-temporal-codec-key"]
    IGS_PROXY_SHARED_SECRET = module.secrets.ids["igs-proxy-shared-secret"]
  }
  depends_on = [google_secret_manager_secret_version.database_url, module.secrets]
}

module "budget" {
  source          = "../budget"
  project_id      = var.project_id
  project_number  = data.google_project.this.number
  billing_account = var.billing_account
  amount_usd      = var.budget_usd
  alert_email     = var.alert_email
  display_name    = "IGS OS ${var.env}"
  depends_on      = [module.apis]
}

# ---------------------------------------------------------------- morning digest

module "digest" {
  count           = var.enable_daily_digest ? 1 : 0
  source          = "../digest_job"
  project_id      = var.project_id
  region          = var.region
  name            = "${local.name}-digest"
  image           = coalesce(var.digest_image, var.bootstrap_image)
  service_account = module.sa.emails["core"]
  network         = module.network.network_id
  subnetwork      = module.network.subnet_id
  tenants         = ["igs"]
  env = {
    IGS_ENVIRONMENT        = "production"
    IGS_DB_APP_ROLE        = "igs_app"
    IGS_LLM_MODELS         = jsonencode(var.llm_models)
    IGS_WEB_BASE_URL       = var.web_base_url
    IGS_DIGEST_TO          = join(",", var.digest_recipients)
    IGS_DIGEST_WEBHOOK_URL = var.digest_webhook_url
  }
  secret_env = {
    IGS_DATABASE_URL = google_secret_manager_secret.database_url.secret_id
    OPENAI_API_KEY   = module.secrets.ids["openai-api-key"]
  }
  depends_on = [google_secret_manager_secret_version.database_url, module.secrets]
}

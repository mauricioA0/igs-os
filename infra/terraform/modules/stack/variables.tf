variable "project_id" {
  type = string
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "env" {
  type = string
  validation {
    condition     = contains(["demo", "prod"], var.env)
    error_message = "env must be demo or prod."
  }
}

variable "billing_account" {
  type        = string
  description = "Billing account id (XXXXXX-XXXXXX-XXXXXX) for the budget."
}

variable "budget_usd" {
  type = number
}

variable "alert_email" {
  type = string
}

variable "github_repository" {
  type    = string
  default = "mauricioA0/igs-os"
}

variable "web_origins" {
  type        = list(string)
  description = "Browser origins allowed by the API (Vercel production + previews regex is in code)."
  default     = []
}

variable "bootstrap_image" {
  type        = string
  default     = "us-docker.pkg.dev/cloudrun/container/hello"
  description = "Placeholder until the first CD rollout pushes real images."
}

# ---- sizing (demo defaults are the cheap ones) ----

variable "demo_mode" {
  type    = bool
  default = true
}

variable "shared_sql" {
  type        = bool
  default     = true
  description = "One Cloud SQL instance for app + Temporal (demo). Prod uses two."
}

variable "app_sql_tier" {
  type    = string
  default = "db-g1-small"
}

variable "temporal_sql_tier" {
  type    = string
  default = "db-g1-small"
}

variable "sql_edition" {
  type    = string
  default = "ENTERPRISE"
}

variable "sql_ha" {
  type    = bool
  default = false
}

variable "sql_disk_gb" {
  type    = number
  default = 20
}

variable "sql_pitr" {
  type    = bool
  default = false
}

variable "core_min_instances" {
  type    = number
  default = 0
}

variable "core_max_instances" {
  type    = number
  default = 10
}

variable "models_min_instances" {
  type    = number
  default = 0
}

variable "models_gpu" {
  type        = bool
  default     = false
  description = "Serve embeddings/reranker on an L4 (always-on GPU cost if min instances = 1)."
}

variable "enable_vector_search" {
  type        = bool
  default     = false
  description = "Vertex Vector Search 2.0 instead of pgvector (keeps a deployed index running while idle)."
}

variable "temporal_address" {
  type        = string
  default     = "temporal-frontend.igs.internal:7233"
  description = "Temporal frontend reachable from Cloud Run (internal LB from infra/helm)."
}

variable "gke_authorized_networks" {
  type    = map(string)
  default = {}
}

variable "deletion_protection" {
  type    = bool
  default = true
}

variable "k8s_namespaces" {
  type = object({
    workers  = string
    temporal = string
  })
  default = {
    workers  = "igs"
    temporal = "temporal"
  }
}

variable "llm_models" {
  type        = map(string)
  description = "Role -> OpenAI model id (verified via the Models API, see .env.example)."
  default = {
    agent     = "gpt-6.1-sol"
    chat      = "gpt-6-luna"
    extractor = "gpt-6-luna"
    judge     = "gpt-6.1-sol"
    simulator = "gpt-6-luna"
    reasoning = "gpt-6-astra"
    fast      = "gpt-6-luna"
  }
}

variable "public_api_url" {
  type        = string
  description = "Public URL of the core API (Cloud Run), used for MCP resource metadata and host checks."
  default     = "http://localhost:8000"
}

variable "llm_daily_budget_usd" {
  type        = string
  description = "Model spend per UTC day, across the API and workers, before calls are refused. Empty disables the cap."
  default     = "10"
}

# ---------------------------------------------------------------- morning digest

variable "enable_daily_digest" {
  type        = bool
  description = "Create the weekday digest job + scheduler (modules/digest_job). Off until ops wants it."
  default     = false
}

variable "digest_image" {
  type        = string
  description = "Ops image for the digest job (scripts/deploy/ops.Dockerfile), e.g. …/igs-ops:sha-<commit>."
  default     = ""
}

variable "web_base_url" {
  type        = string
  description = "Public URL of the web app; the digest email links into it."
  default     = "https://igs-os.vercel.app"
}

variable "digest_recipients" {
  type        = list(string)
  description = "Who gets the digest email (via the relay webhook). Empty = no email, event only."
  default     = []
}

variable "digest_webhook_url" {
  type        = string
  description = "Mail relay endpoint that accepts {to, subject, html, text}. Empty = no email."
  default     = ""
}

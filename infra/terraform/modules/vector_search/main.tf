# Vertex AI Vector Search 2.0 ("Agent Retrieval"), behind a flag. Demo mode keeps it off and
# retrieves from pgvector (docs/architecture/rag.md: same VectorStore adapter).
#
# Collections and indexes are created by `scripts/deploy/vector_search_bootstrap.py` through the
# google-cloud-vectorsearch client: as of 2026-10 the Terraform provider has no stable resource
# for 2.0 collections, and filter/store fields are fixed at index creation (rag.md §2), so they
# live next to the code that queries them. Terraform owns the API and who may use it.

variable "project_id" {
  type = string
}

variable "enabled" {
  type    = bool
  default = false
}

variable "writer_members" {
  type        = list(string)
  default     = []
  description = "Ingestion workers (upsert/delete data objects)."
}

variable "reader_members" {
  type        = list(string)
  default     = []
  description = "Core API (search)."
}

resource "google_project_service" "vectorsearch" {
  count              = var.enabled ? 1 : 0
  project            = var.project_id
  service            = "vectorsearch.googleapis.com"
  disable_on_destroy = false
}

# Built-in reranker (semantic-ranker) is served through Discovery Engine.
resource "google_project_service" "discoveryengine" {
  count              = var.enabled ? 1 : 0
  project            = var.project_id
  service            = "discoveryengine.googleapis.com"
  disable_on_destroy = false
}

resource "google_project_iam_member" "writer" {
  for_each = var.enabled ? toset(var.writer_members) : toset([])
  project  = var.project_id
  role     = "roles/vectorsearch.dataObjectWriter"
  member   = each.value
}

resource "google_project_iam_member" "reader" {
  for_each = var.enabled ? toset(var.reader_members) : toset([])
  project  = var.project_id
  role     = "roles/vectorsearch.viewer"
  member   = each.value
}

resource "google_project_iam_member" "ranker" {
  for_each = var.enabled ? toset(var.reader_members) : toset([])
  project  = var.project_id
  role     = "roles/discoveryengine.viewer"
  member   = each.value
}

output "store" {
  value = var.enabled ? "vertex" : "pgvector"
}

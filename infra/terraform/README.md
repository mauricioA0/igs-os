# IGS OS — Terraform (GCP `mv-cloud-509914`, `us-central1`)

Infrastructure as code for the stack in `docs/PLAN.md`. **The demo environment is applied in mv-cloud-509914 (us-central1) — see docs/infra/deployment.md.** Every
directory validates offline (`terraform fmt -check`, `init -backend=false`, `validate`) with
Terraform 1.9.8, google provider `~> 8.8`, random `~> 3.9`.

```
bootstrap/           one-time: versioned, private GCS bucket for remote state
envs/demo/           public portfolio deployment (cheapest)
envs/prod/           production sizing
modules/stack/       everything, parameterized by env
modules/*            network, cloudsql, registry, secrets, service_accounts,
                     cloud_run_service, gke_autopilot, github_wif, budget,
                     vector_search, project_services
```

## What each env creates

| Component | demo | prod |
|---|---|---|
| VPC, subnet (pods/services ranges), private services access, Cloud NAT | ✓ | ✓ |
| Cloud SQL Postgres 17, private IP only, IAM auth on, TLS only | 1 shared zonal `db-g1-small` (dbs `igs`, `temporal`, `temporal_visibility`) | app `db-custom-2-8192` + Temporal `db-custom-4-16384`, both regional HA, PITR |
| Artifact Registry (Docker, immutable tags, cleanup) | ✓ | ✓ |
| Secret Manager | `openai-api-key` (set by hand), generated: DB passwords, `igs-proposal-signing-key`, `igs-temporal-codec-key` (32 random bytes, base64), `igs-core-database-url` | same |
| Service accounts, least privilege | core, worker, models, temporal, deployer | same |
| Cloud Run `core` (public API, Direct VPC egress) | min 0 | min 2, max 50 |
| Cloud Run `models` (BGE-M3 + reranker, internal ingress, invokers: core + worker) | CPU, 4 vCPU / 8 GiB, min 0 | L4 GPU, 4 vCPU / 16 GiB, min 1 |
| GKE Autopilot (private nodes) for Temporal + KEDA-scaled workers | ✓ (Spot pods via infra/helm) | ✓ |
| Workload Identity: `igs/igs-worker` → worker SA, `temporal/temporal` → temporal SA | ✓ | ✓ |
| GitHub Actions WIF (only `mauricioA0/igs-os`, only `refs/heads/main`) → deployer SA | ✓ | ✓ |
| GCS bucket for RAG source documents (versioned, no public access) | ✓ | ✓ |
| Vertex Vector Search 2.0 (APIs + IAM; collections via app bootstrap script) | off → **pgvector** | on |
| Billing budget + e-mail alerts (50/90/100% actual, 100% forecast) | ✓ | ✓ |

## Idle footprint

| Mode | Notes |
|---|---|
| demo | Dominated by Cloud SQL `db-g1-small` and Temporal on Spot pods; retrieval from pgvector, no Vector Search. |
| prod | Cloud SQL HA, an always-on L4 for models, Vector Search, a warm API. |
| paused | runbook (Y3): scale GKE workloads to 0, stop Cloud SQL, keep storage/registry. |

Price it in the GCP pricing calculator before the first apply.

## First apply (when approved)

```sh
# 0. who/where
gcloud config set project mv-cloud-509914 && gcloud auth application-default login

# 1. state bucket (local state, once)
cd bootstrap && terraform init && terraform apply -var project_id=mv-cloud-509914

# 2. env
cd ../envs/demo && cp terraform.tfvars.example terraform.tfvars   # fill billing account, email, your IP
terraform init -backend-config="bucket=mv-cloud-509914-tfstate"
terraform plan -out tfplan && terraform apply tfplan

# 3. secrets set by a person (never in code or state)
printf '%s' "$OPENAI_API_KEY" | gcloud secrets versions add openai-api-key --data-file=-
```

After the first migration (Y3's pipeline runs Alembic as a Cloud Run job), grant the RLS role to
the login user: `GRANT igs_app TO igs_login;` — the API connects as `igs_login` and `SET ROLE
igs_app` (`IGS_DB_APP_ROLE`), so tenant isolation applies.

## Notes and known gaps

- **Generated secrets are in Terraform state.** The state bucket is private, versioned and only
  readable by the project owners; rotate with `terraform apply -replace=…random_password…`.
- **Images:** services start from a placeholder image and Terraform ignores later image changes;
  rollouts belong to the deploy pipeline (Y3).
- **Temporal address:** `IGS_TEMPORAL_ADDRESS` defaults to `temporal-frontend.igs.internal:7233`;
  infra/helm (Y2) must expose the frontend on an internal load balancer reachable from Cloud Run's
  Direct VPC egress and match this name (or override `temporal_address`).
- **Models auth:** `models` only accepts authenticated calls from the core/worker SAs; the core's
  `HttpEmbedder` must send an ID token (the client supports an auth callback; wiring it to the
  metadata server is application work).
- **Vertex Vector Search 2.0:** the provider has no stable resource for 2.0 collections yet, so
  Terraform enables the APIs and IAM and the collection is created by an app-side bootstrap script.
- `gke_authorized_networks` empty means the control plane accepts any source with valid
  credentials; set it to your IP / CI egress for real use.

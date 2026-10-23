# Deployment — what runs where

| | |
|---|---|
| Web | Vercel, project `igs-os` (team `navy-labs`) → `https://igs-os.vercel.app` |
| API | GCP project `mv-cloud-509914`, region `us-central1`, Cloud Run `igs-demo-core` → `https://igs-demo-core-fujfenyt5a-uc.a.run.app` |
| MCP | `https://igs-demo-core-fujfenyt5a-uc.a.run.app/mcp` (Streamable HTTP, bearer API key) |
| Temporal UI | GKE Autopilot cluster `igs-demo`, behind IAP (no public access) |
| State | Terraform remote state in `gs://mv-cloud-509914-tfstate` (versioned, private) |

Status (2026-10-22): the state bucket is applied, the `demo` environment is being applied from a reviewed plan (100 resources to add, 0 to change, 0 to destroy), and images are built with Cloud Build. URLs are filled in once the first deploy passes its smoke checks.

## What Terraform creates in `demo`

Source: `infra/terraform/envs/demo` → `modules/stack`. Full table per environment: `infra/terraform/README.md`.

| Component | Demo configuration |
|---|---|
| Network | VPC + subnet with pod/service ranges, private services access, Cloud Router + NAT |
| Cloud SQL Postgres 17 | One zonal `db-g1-small`, private IP only, IAM auth, TLS only; databases `igs`, `temporal`, `temporal_visibility` |
| Cloud Run `core` | Public API, Direct VPC egress to Cloud SQL, min 0 / max 10 instances |
| Cloud Run `models` | BGE-M3 + reranker on CPU (4 vCPU / 8 GiB), internal ingress, invokable only by the core and worker service accounts, min 0 |
| GKE Autopilot | Private nodes; Temporal server (Helm, `infra/helm/temporal`) and KEDA-scaled workers (`infra/k8s`), Spot pods in demo |
| Artifact Registry | `us-central1-docker.pkg.dev/mv-cloud-509914/igs-demo` (`igs-core`, `igs-worker`, `igs-ops`, `igs-models`) |
| Secret Manager | `openai-api-key` (set by a person), generated DB passwords, `igs-proposal-signing-key`, `igs-temporal-codec-key`, `igs-core-database-url` |
| Identity | One service account per workload (core, worker, models, temporal, deployer); GKE Workload Identity; GitHub Actions Workload Identity Federation limited to `mauricioA0/igs-os` on `main` — no JSON keys |
| Storage | GCS bucket for RAG source documents (versioned, no public access) |
| Vector store | pgvector on the app database (`enable_vector_search = false`); Vertex Vector Search is the prod option behind the same adapter |
| Budget | Billing budget with e-mail alerts at 50 / 90 / 100 % actual and 100 % forecast |

## Cost per mode

| Mode | What drives fixed cost |
|---|---|
| demo | Cloud SQL `db-g1-small` and the Temporal pods; everything on Cloud Run scales to zero |
| paused | storage and registry only |
| prod | HA Cloud SQL, an always-on L4 GPU for models, Vector Search, a warm API |

Variable cost is dominated by the LLM: ≈ US$11 per 1,000 coach conversations on the chat tier, ≈ US$65 per 1,000 inbound-inquiry flow runs. Details: [`../architecture/cost-and-scale.md`](../architecture/cost-and-scale.md).

## Pause and resume the demo

```sh
scripts/deploy/demo-pause.sh    # Cloud Run min 0, Temporal + workers to 0, KEDA paused, Cloud SQL stopped
scripts/deploy/demo-resume.sh   # reverse, then smoke checks
```

The deployer service account holds a narrow custom role (`cloudsql.instances.get/update`) for exactly this.

## How a deploy runs

1. Images: `gcloud builds submit --config scripts/deploy/cloudbuild.yaml` (native linux/amd64), or the `images` job in `.github/workflows/deploy.yml`.
2. Migrations, seed and reindex run as Cloud Run jobs from the `igs-ops` image (the API image carries no migrations or fixtures).
3. API and models: new Cloud Run revisions tagged `sha-<short>` (rollback = route traffic to the previous tag).
4. GKE: Temporal Helm upgrade, schema job, worker rollout.
5. Web: `vercel build` + `vercel deploy --prebuilt --prod` with `API_URL` pointing to the API.
6. Smoke: `/healthz`, `/readyz`, `/v1/trips`, web `/` and `/ops`; optional demo reset (`services/core/scripts/demo_reset.py`) that also parks a live Lakeshore workflow on its approval.

CD stays off until the repository variable `DEPLOY_ENABLED` is `true`; prod requires reviewers on the GitHub `prod` environment.

Bootstrap order, rollback per component, codec-key rotation, demo reset and incident checklist: [`runbook.md`](runbook.md).

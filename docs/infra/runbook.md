# Runbook — deploying and operating IGS OS on GCP

Project `mv-cloud-509914`, region `us-central1`. gcloud account `<owner-account>`
(**always** pass `--project mv-cloud-509914 --account <owner-account>` or export
`CLOUDSDK_CORE_PROJECT=mv-cloud-509914`, so a different default gcloud project is never used).

| Piece | Where | Managed by |
|---|---|---|
| VPC, Cloud SQL (app + Temporal), Artifact Registry, Secret Manager, service accounts, Cloud Run services (config), GKE Autopilot, WIF, budget | `infra/terraform/envs/<env>` | Terraform |
| Namespaces, KSAs, Temporal schema job, Temporal UI behind IAP, frontend ILB, workers + KEDA | `infra/k8s/overlays/<env>` | Kustomize (CD) |
| Temporal server | chart `temporal/temporal`, values `infra/helm/temporal/values{,-<env>}.yaml` | Helm (CD) |
| Images (core, worker, ops, models) and Cloud Run revisions | `.github/workflows/deploy.yml` + `scripts/deploy/*` | CD |
| Web | Vercel project per environment | CD (`vercel deploy --prebuilt`) |

Names follow the Terraform stack: `igs-<env>` (network, AR repository, GKE cluster),
`igs-<env>-core` / `igs-<env>-models` (Cloud Run), `igs-<env>-<role>@…` (service accounts),
`igs-<env>-pg` (shared SQL) or `igs-<env>-app-pg` + `igs-<env>-temporal-pg`.
`scripts/deploy/lib.sh` derives these from `IGS_ENV`, so overrides are rarely needed.

## Configuration

Repository variable (Settings → Variables → Actions):

| Variable | Value |
|---|---|
| `DEPLOY_ENABLED` | `true` once bootstrap is done. Until then `deploy.yml` is a no-op on push. |

Per GitHub **environment** (`demo`, `prod`) — values come from `terraform output` in the env dir:

| Variable | Source / example |
|---|---|
| `GCP_PROJECT_ID` | `mv-cloud-509914` |
| `GCP_REGION` | `us-central1` |
| `GCP_WIF_PROVIDER` | `terraform output -raw github_workload_identity_provider` |
| `GCP_DEPLOY_SA` | `terraform output -raw deployer_service_account` |
| `TEMPORAL_CHART_VERSION` | `1.7.0` (pinned; matches `infra/helm/temporal/values.yaml`) |
| `TEMPORAL_DB_HOST` | `terraform output -raw temporal_sql_host` (private IP) |
| `API_URL` | `terraform output -raw api_url` (or the custom domain) |
| `WEB_URL` | the Vercel production URL for this environment |
| `MODELS_URL` | `terraform output -raw models_url` (used by reset/index jobs) |
| `VERCEL_ORG_ID`, `VERCEL_PROJECT_ID` | `apps/web/.vercel/project.json` after `vercel link` |

Environment **secret**: `VERCEL_TOKEN`. GCP credentials never live in GitHub: jobs authenticate
through Workload Identity Federation, restricted to this repository and ref.

`prod` environment: Settings → Environments → `prod` → required reviewers (you), deployment
branches = `main` only. Every prod job then waits for an approval.

Secrets in Secret Manager (created by Terraform, values below are set by hand once):
`openai-api-key` (manual), `igs-core-database-url`, `igs-proposal-signing-key`,
`igs-temporal-codec-key` (generated).

## First-time bootstrap (order matters)

1. **Budget guard first.** Confirm the billing account and alert email in
   `infra/terraform/envs/demo/terraform.tfvars`. The budget alert is part of the stack.
2. **State bucket.** `cd infra/terraform/bootstrap && terraform init && terraform apply` →
   bucket `mv-cloud-509914-tfstate`.
3. **Stack.** `cd infra/terraform/envs/demo && terraform init && terraform plan` → review cost
   items (Cloud SQL tier, GKE, models service, Vector Search flag off) → `terraform apply`.
   Cloud Run services start on `bootstrap_image`; CD replaces the image.
4. **Manual secret.** `gcloud secrets versions add openai-api-key --data-file=- <<<"$KEY"`
   (personal key only — never the MoP one).
5. **GitHub config.** Fill the environment variables above from `terraform output`, add
   `VERCEL_TOKEN`, configure `prod` protection, `vercel link` the web app.
6. **Images + DB.** Run `deploy` manually: Actions → deploy → `environment=demo`,
   `build_models=true`, `skip_temporal=false`, `reset_demo=true`. It builds the four images,
   runs `alembic upgrade head` as a Cloud Run job, applies the Kubernetes base (Temporal schema
   job first), installs Temporal, rolls workers, deploys Cloud Run + Vercel, smoke-tests and
   resets the demo story.
7. **Index the demo knowledge.** One-off job:
   `scripts/deploy/run-job.sh igs-demo-index <ops image> python -m igs_common.ingest index-all --tenant igs`
   (needs `MODELS_URL`).
8. **MCP key (optional).** `DATABASE_URL=… uv run python services/core/scripts/mint_api_key.py --tenant igs --name "Claude Code" --scope igs:read`
   through a Cloud SQL proxy, or as a job with the ops image. The key prints once.
9. Set `DEPLOY_ENABLED=true`. From now on every push to `main` deploys demo (without touching
   the Temporal server, and rebuilding the models image only when `services/models` changes).

## Deploy

- **Demo:** push to `main`, or Actions → deploy → `environment=demo`.
- **Prod:** Actions → deploy → `environment=prod`, approve each gated job.
- Order inside a run: images → migrations → (Cloud Run API ∥ GKE workers) → web → smoke.
  Migrations are additive (expand/contract): a new revision can run against the old schema
  for one release, so a failed rollout never needs a down-migration.
- Locally (break-glass), with the same env vars:
  `IGS_ENV=demo GCP_PROJECT_ID=mv-cloud-509914 GCP_REGION=us-central1 scripts/deploy/deploy-run.sh core <image>`.

## Rollback

| Component | How |
|---|---|
| Core API / models (Cloud Run) | Every revision is tagged `sha-<short>`. `gcloud run services update-traffic igs-<env>-core --to-tags sha-<good>=100` (instant). Or re-run deploy on the good commit. |
| Workers (GKE) | `kubectl -n igs rollout undo deployment/<name>` (all `app.kubernetes.io/part-of=igs-workers`). Replay tests guard determinism, but if a bad interpreter change reached prod, roll back **before** new executions start; running executions resume on the old code. |
| Temporal server | `helm -n temporal rollback temporal <revision>`. Never roll back across a schema migration; the schema job only moves forward. |
| Database | Fix forward with a new migration. PITR (prod, `sql_pitr=true`) for data loss: clone to a new instance at a timestamp, verify, swap the `igs-core-database-url` secret. |
| Web | Vercel dashboard → promote the previous deployment, or `vercel rollback <url>`. |
| Infra | `git revert` the Terraform change, `terraform plan` / `apply`. |

## Codec key rotation (Temporal payload encryption)

`igs_common.temporal.codec` keeps a map of key ids → keys and encrypts with the active one, so
old payloads stay readable. **Gap:** settings today expose a single key (`IGS_TEMPORAL_CODEC_KEY`
+ `…_KEY_ID`); add a `previous keys` setting before the first rotation. Then:

1. Generate: `head -c 32 /dev/urandom | base64`; add as a new version of
   `igs-temporal-codec-key`; keep the old value in the previous-keys secret.
2. Set the new key id (`IGS_TEMPORAL_CODEC_KEY_ID=k2`) on core and workers; deploy both.
3. Keep the old key until every execution started before the switch has closed (check the
   oldest running execution in the Temporal UI), then drop it.

Never deploy core and workers with different active keys and no shared previous key.

## Demo data: seed, reset, re-index

- **Reset to the scripted Lakeshore story** (removes what visitors created, keeps audit_log):
  Actions → deploy with `reset_demo=true`, or
  `scripts/deploy/run-job.sh igs-demo-reset-demo <ops image> python -m igs_common.seed --reset-demo`.
  Only works on the `igs` demo tenant by design.
- **Seed only (idempotent upsert):** same job with `python -m igs_common.seed`.
- **Re-index RAG after fixture changes:** the index job in bootstrap step 7.
- Check after reset: `/v1/accounts/<lakeshore>` health `red`, approval `a-9003` pending,
  execution `ex-lak-inbound` waiting.

## Pause / resume the demo (cut idle cost)

Pausing scales the GKE workloads to zero and stops Cloud SQL; only storage and the registry keep billing.

```bash
export IGS_ENV=demo GCP_PROJECT_ID=mv-cloud-509914 GCP_REGION=us-central1
scripts/deploy/demo-pause.sh     # Cloud Run min 0, Temporal + workers to 0, KEDA paused, Cloud SQL stopped
scripts/deploy/demo-resume.sh    # needs API_URL, WEB_URL, OPS_IMAGE: starts SQL, scales up, resets the story, smoke
```

Resume ~5–10 minutes before showing the demo (Cloud SQL start + Temporal + first cold starts).
The GKE Autopilot control plane fee is covered by the free tier for one cluster; if Vector
Search is enabled, undeploy its index while paused (`enable_vector_search=false` + apply).

## Cost alert response

The budget (Terraform `budget` module) emails at 50 / 90 / 100 % of `budget_usd`.

1. Billing → Reports, group by SKU, last 7 days. Usual suspects: Cloud SQL tier/HA, a models
   service left at `min_instances>0` (or GPU), Vector Search index replicas, GKE pods not scaling
   to zero, LLM spend (separate, on the OpenAI dashboard).
2. Demo: `demo-pause.sh` immediately; investigate after.
3. LLM: check `agent_runs` cost per run in the traces view; lower roles to `gpt-6-luna` via
   `IGS_LLM_MODELS`; the evals harness never spends without `--allow-paid`.
4. Record what happened and the fix in this file.

## Incident checklist

1. **Scope:** `/healthz` (process), `/readyz` (DB), web home, Temporal UI (through IAP),
   Cloud Run + GKE dashboards. Note the start time.
2. **Recent change?** Last deploy run / last Terraform apply → roll back first (table above),
   debug second.
3. **API 5xx:** Cloud Logging, filter `resource.labels.service_name="igs-<env>-core" severity>=ERROR`;
   every response carries `x-request-id`; problem+json bodies include it.
4. **DB:** connection count vs `max_connections`, CPU, storage. RLS denials show as empty
   results, not errors — check `app.tenant_id` is set (session_scope).
5. **Flows stuck:** Temporal UI → workflow history; workers' KEDA scaler and pod logs; a
   non-determinism error means an interpreter change without `workflow.patched` → roll workers back.
6. **AI unavailable (503 `ai-unavailable` / `copilot-unavailable`):** `openai-api-key` secret,
   `IGS_LLM_MODELS`, OpenAI status/quota.
7. **Security event** (leaked key, suspicious MCP use): revoke API keys (`api_keys.revoked_at`),
   rotate the affected secret (new version + redeploy), review `audit_log` for the window.
8. **Close:** write a short note here (what, impact, cause, fix, follow-ups).

## Assumptions to confirm with infra owners

- Terraform's Cloud Run module ignores `containers[0].image` (true today), so CD only changes images.
- Worker Deployments carry `app.kubernetes.io/part-of=igs-workers` and their container is named `worker`;
  the schema Job carries `app.kubernetes.io/name=temporal-schema` (infra/k8s).
- The deployer SA has `run.developer`, `run.jobs` create/execute, `iam.serviceAccountUser` on the
  runtime SAs, `artifactregistry.writer`, `container.developer` and `cloudsql.instances.update`
  (pause/resume).
- The ops image (`scripts/deploy/ops.Dockerfile`) exists because the core image does not ship
  `alembic.ini`, migrations or fixtures.

# Kubernetes: Temporal + IGS workers on GKE Autopilot

Temporal server comes from the official chart (`infra/helm/temporal`); everything around it is
here: namespaces, Workload Identity service accounts, the schema Job, the internal LB the API
uses, the IAP-protected Web UI, the workers, KEDA scaling, NetworkPolicies and metrics.

```
infra/helm/temporal/values.yaml        base (postgres12_pgx, 512 shards, SQL visibility, no ES)
infra/helm/temporal/values-{demo,prod}.yaml
infra/k8s/base/                        manifests (kustomize)
infra/k8s/overlays/{demo,prod}/        Spot + scale-to-zero (demo) / warm worker, bigger (prod)
services/worker/Dockerfile             worker image (non-root, read-only rootfs friendly)
```

## Cluster prerequisites (once)

- GKE Autopilot with Dataplane V2 (default) — enforces the NetworkPolicies.
- KEDA ≥ 2.17 (the `temporal` scaler): `helm install keda kedacore/keda -n keda --create-namespace`.
- Terraform-managed: GSAs `igs-temporal@` / `igs-worker@` + Workload Identity bindings, Temporal
  Cloud SQL (private IP, databases `temporal` and `temporal_visibility`, user `temporal`), static
  IP `igs-temporal-ui-ip`, SSL policy `igs-modern-tls`, IAP OAuth client, IAP accessor IAM.

## Deploy order (the pipeline does this)

1. `kubectl apply -f base/namespaces.yaml -f base/serviceaccounts.yaml`
2. Secrets from Secret Manager (never committed):
   - `temporal/temporal-db` — key `password`
   - `temporal/temporal-ui-iap-oauth` — keys `client_id`, `client_secret`
   - `igs-workers/igs-worker` — `DATABASE_URL`, `IGS_TEMPORAL_CODEC_KEY`, `OPENAI_API_KEY`
3. `temporal-db` ConfigMap `host` ← Temporal Cloud SQL private IP; then run the schema Job and
   wait: `kubectl -n temporal wait --for=condition=complete job/temporal-schema --timeout=10m`.
4. `helm upgrade --install temporal temporal/temporal --version 1.7.0 -n temporal -f values.yaml
   -f values-<env>.yaml --set-string server.config.persistence.datastores.{default,visibility}.sql.connectAddr=<ip>:5432`
5. `kubectl apply -k overlays/<env>` (images pinned to the git SHA via `kustomize edit set image`).

## Values replaced per environment

| Placeholder | Where | Source |
|---|---|---|
| `TEMPORAL_DB_HOST` | helm `connectAddr`, `temporal-db` ConfigMap | Terraform output |
| `10.10.0.0/16` | ILB `loadBalancerSourceRanges`, frontend NetworkPolicy | Cloud Run Direct VPC egress subnet |
| `temporal.igs-os.example` | ManagedCertificate | DNS name for the Temporal UI |
| `https://igs-models.example.run.app` | worker ConfigMap `IGS_MODELS_URL` | Cloud Run URL of `services/models` |

## Decisions worth knowing

- **Schema outside Helm**: `manageSchema: false`; `temporal-sql-tool` (admin-tools pinned by
  digest) runs as a Job before each upgrade. Bump the digest together with `server.image.tag`.
- **512 history shards** are fixed at cluster creation.
- **No privileged init containers**: chart 1.7.0 has no `configure-sysctl` step, so it's
  Autopilot-safe as is.
- **The API reaches Temporal through an internal L4 LB on 7233 only**; membership ports stay in
  the cluster.
- **Web UI only through IAP** (BackendConfig); Temporal UI's own OIDC can't restrict accounts.
- **Workers scale on backlog** (KEDA `temporal` scaler, workflow + activity queues). Timers and
  signals create workflow tasks, so scale-to-zero still wakes up; prod keeps one warm `flows`
  replica to avoid a cold start on approvals.

## Offline validation (no cluster)

```sh
# chart lint + render
docker run --rm --entrypoint sh -v $PWD/infra/helm/temporal:/v alpine/helm -c \
  'helm repo add temporal https://go.temporal.io/helm-charts >/dev/null && helm pull temporal/temporal --version 1.7.0 --untar -d /tmp &&
   helm lint /tmp/temporal -f /v/values.yaml -f /v/values-demo.yaml'
# manifests incl. CRDs (KEDA, BackendConfig, ManagedCertificate, PodMonitoring)
kubectl kustomize infra/k8s/overlays/demo > /tmp/k8s.yaml
docker run --rm -v /tmp:/w ghcr.io/yannh/kubeconform -strict -summary -kubernetes-version 1.33.0 \
  -schema-location default \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' /w/k8s.yaml
```

#!/usr/bin/env bash
# Deploy the GKE side: Kubernetes base (namespaces, KSAs, Temporal schema job, IAP, ILB,
# workers + KEDA) via Kustomize, the Temporal server via its Helm chart, then roll the workers
# to the new image.
#   scripts/deploy/gke-deploy.sh <worker-image>
# Layout (Y2): infra/k8s/overlays/<env> (Kustomize), infra/helm/temporal/values{,-<env>}.yaml.
# Workers are Deployments labelled app.kubernetes.io/name=igs-worker in namespace $WORKERS_NS (igs-workers).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
require IGS_ENV

worker_image="$1"
overlay="infra/k8s/overlays/${IGS_ENV}"

log "kubectl apply -k $overlay"
kubectl apply -k "$overlay"
# The schema job (temporal-sql-tool, pinned) must finish before the server starts on a new
# schema version. Jobs are immutable: the overlay names them per Temporal version.
kubectl -n temporal wait --for=condition=complete job -l app.kubernetes.io/name=temporal-schema --timeout=10m
endlog

if [[ "${SKIP_TEMPORAL:-false}" != true ]]; then
  require TEMPORAL_CHART_VERSION
  log "helm upgrade temporal ${TEMPORAL_CHART_VERSION}"
  helm repo add temporal https://go.temporal.io/helm-charts >/dev/null 2>&1 || true
  helm repo update temporal >/dev/null
  extra=()
  if [[ -n "${TEMPORAL_DB_HOST:-}" ]]; then
    extra+=(
      --set-string "server.config.persistence.datastores.default.sql.connectAddr=${TEMPORAL_DB_HOST}:5432"
      --set-string "server.config.persistence.datastores.visibility.sql.connectAddr=${TEMPORAL_DB_HOST}:5432"
    )
  fi
  helm upgrade --install temporal temporal/temporal \
    --namespace temporal \
    --version "$TEMPORAL_CHART_VERSION" \
    --values infra/helm/temporal/values.yaml \
    --values "infra/helm/temporal/values-${IGS_ENV}.yaml" \
    "${extra[@]}" \
    --wait --timeout 15m --atomic
  endlog
fi

log "roll workers → $worker_image"
mapfile -t deployments < <(kubectl -n "$WORKERS_NS" get deployment \
  -l app.kubernetes.io/name=igs-worker -o name)
if ((${#deployments[@]} == 0)); then
  echo "no worker deployments found (label app.kubernetes.io/name=igs-worker)" >&2
  exit 1
fi
for d in "${deployments[@]}"; do
  kubectl -n "$WORKERS_NS" set image "$d" "worker=${worker_image}"
done
for d in "${deployments[@]}"; do
  kubectl -n "$WORKERS_NS" rollout status "$d" --timeout=10m
done
endlog

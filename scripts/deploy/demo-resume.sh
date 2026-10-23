#!/usr/bin/env bash
# Resume a paused demo, then reset it to the scripted Lakeshore story and smoke-test it.
#   IGS_ENV=demo scripts/deploy/demo-resume.sh
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
require GCP_PROJECT_ID GCP_REGION IGS_ENV GKE_CLUSTER API_URL WEB_URL OPS_IMAGE
# Every Cloud SQL instance of this stack (`igs-demo-pg` when shared, or app + temporal).
mapfile -t sql_instances < <(gcloud sql instances list --project "$GCP_PROJECT_ID" \
  --filter="name~^${STACK}-" --format='value(name)')
[[ "$IGS_ENV" == demo ]] || { echo "demo-resume only runs on the demo environment" >&2; exit 64; }

log "start Cloud SQL"
for inst in "${sql_instances[@]}"; do
  gcloud sql instances patch "$inst" --project "$GCP_PROJECT_ID" --activation-policy ALWAYS --quiet
done
endlog

log "scale Temporal and workers back up"
gcloud container clusters get-credentials "$GKE_CLUSTER" --project "$GCP_PROJECT_ID" --region "$GCP_REGION"
kubectl -n temporal scale deployment --all --replicas=1
kubectl -n temporal rollout status deployment --timeout=10m
kubectl -n "$WORKERS_NS" annotate scaledobject --all autoscaling.keda.sh/paused- || true
kubectl -n "$WORKERS_NS" scale deployment --all --replicas=1
endlog

"$(dirname "$0")/run-job.sh" "${STACK}-reset-demo" "$OPS_IMAGE" python -m igs_common.seed --reset-demo
"$(dirname "$0")/smoke.sh" "$API_URL" "$WEB_URL"

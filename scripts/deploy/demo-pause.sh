#!/usr/bin/env bash
# Pause the demo environment to cut idle cost (storage and a few always-on pieces keep billing).
#   IGS_ENV=demo scripts/deploy/demo-pause.sh
# Stops Cloud SQL, scales Temporal + workers to zero and keeps Cloud Run at min 0.
# Reverse with demo-resume.sh. Never run against prod.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
require GCP_PROJECT_ID GCP_REGION IGS_ENV GKE_CLUSTER
# Every Cloud SQL instance of this stack (`igs-demo-pg` when shared, or app + temporal).
mapfile -t sql_instances < <(gcloud sql instances list --project "$GCP_PROJECT_ID" \
  --filter="name~^${STACK}-" --format='value(name)')
[[ "$IGS_ENV" == demo ]] || { echo "demo-pause only runs on the demo environment" >&2; exit 64; }

log "scale Cloud Run to zero"
for svc in core models; do
  gcloud run services update "${STACK}-${svc}" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
    --min-instances 0 --quiet || true
done
endlog

log "scale GKE workloads to zero"
gcloud container clusters get-credentials "$GKE_CLUSTER" --project "$GCP_PROJECT_ID" --region "$GCP_REGION"
# Pause KEDA first, or it scales the workers back up on backlog.
kubectl -n "$WORKERS_NS" annotate scaledobject --all autoscaling.keda.sh/paused=true --overwrite || true
kubectl -n "$WORKERS_NS" scale deployment --all --replicas=0
kubectl -n temporal scale deployment --all --replicas=0
endlog

log "stop Cloud SQL"
for inst in "${sql_instances[@]}"; do
  gcloud sql instances patch "$inst" --project "$GCP_PROJECT_ID" --activation-policy NEVER --quiet
done
endlog
echo "demo paused. Resume with scripts/deploy/demo-resume.sh"

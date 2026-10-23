#!/usr/bin/env bash
# Roll a Cloud Run service to a new image. Terraform owns the service configuration (CPU,
# memory, env, secrets, VPC) and ignores the image, so CD only changes the image — no drift.
#   scripts/deploy/deploy-run.sh <core|models> <image>
# The new revision is tagged `sha-<short>` so a rollback is one traffic command (runbook).
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
require GCP_PROJECT_ID GCP_REGION IGS_ENV

component="$1"
image="$2"
service="${STACK}-${component}"
short="${GITHUB_SHA:-manual}"
short="${short:0:7}"

log "deploy $service → $image"
gcloud run services update "$service" \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --image "$image" \
  --revision-suffix "${short}-$(date +%s)" \
  --update-labels "commit=${short}" \
  --tag "sha-${short}" \
  --quiet >&2
gcloud run services update-traffic "$service" \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --to-latest --quiet >&2
endlog
gcloud run services describe "$service" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --format='value(status.url)'

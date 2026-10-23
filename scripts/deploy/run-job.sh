#!/usr/bin/env bash
# Create/update a Cloud Run job from an image and execute it, waiting for completion.
#   scripts/deploy/run-job.sh <job-name> <image> <command> [args...]
# Used for migrations (`alembic upgrade head`) and demo seeding/reset.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"
require GCP_PROJECT_ID GCP_REGION IGS_ENV RUN_SA VPC_NETWORK VPC_SUBNET

job="$1"
image="$2"
shift 2
command="$1"
shift
args="$(IFS=,; echo "$*")"

log "job $job: $command $*"
gcloud run jobs deploy "$job" \
  --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
  --image "$image" \
  --service-account "$RUN_SA" \
  --network "$VPC_NETWORK" --subnet "$VPC_SUBNET" --vpc-egress all-traffic \
  --set-secrets "DATABASE_URL=igs-core-database-url:latest,IGS_DATABASE_URL=igs-core-database-url:latest" \
  --set-env-vars "IGS_MODELS_URL=${MODELS_URL:-}" \
  --command "$command" ${args:+"--args=$args"} \
  --tasks 1 --max-retries 0 --task-timeout 15m \
  --quiet
gcloud run jobs execute "$job" --project "$GCP_PROJECT_ID" --region "$GCP_REGION" --wait
endlog

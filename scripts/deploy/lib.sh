#!/usr/bin/env bash
# Shared helpers for the deploy scripts. Sourced, not executed.
# Values come from the environment (GitHub environment vars in CI, your shell locally). Names
# default to the Terraform naming in infra/terraform/modules/stack (`igs-<env>-…`), so in most
# cases only GCP_PROJECT_ID, GCP_REGION and IGS_ENV are needed. See docs/infra/runbook.md.
set -euo pipefail

require() {
  local missing=()
  for name in "$@"; do
    [[ -n "${!name:-}" ]] || missing+=("$name")
  done
  if ((${#missing[@]})); then
    echo "missing required env: ${missing[*]}" >&2
    exit 64
  fi
}

# Worker Deployments and their KEDA ScaledObjects (infra/k8s/base/workers.yaml).
: "${WORKERS_NS:=igs-workers}"
export WORKERS_NS

# Derive Terraform-aligned names from IGS_ENV unless overridden.
if [[ -n "${IGS_ENV:-}" ]]; then
  STACK="igs-${IGS_ENV}"
  : "${AR_REPO:=$STACK}"
  : "${GKE_CLUSTER:=$STACK}"
  : "${VPC_NETWORK:=$STACK}"
  : "${VPC_SUBNET:=${STACK}-${GCP_REGION:-us-central1}}"
  if [[ -n "${GCP_PROJECT_ID:-}" ]]; then
    : "${RUN_SA:=${STACK}-core@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"
  fi
  export STACK AR_REPO GKE_CLUSTER VPC_NETWORK VPC_SUBNET RUN_SA
fi

# Artifact Registry image URI: <region>-docker.pkg.dev/<project>/<repo>/<name>:<tag>
image_uri() {
  require GCP_PROJECT_ID GCP_REGION AR_REPO
  echo "${GCP_REGION}-docker.pkg.dev/${GCP_PROJECT_ID}/${AR_REPO}/$1:$2"
}

log() { printf '::group::%s\n' "$*"; }
endlog() { printf '::endgroup::\n'; }

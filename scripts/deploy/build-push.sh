#!/usr/bin/env bash
# Build one component image and push it to Artifact Registry.
#   scripts/deploy/build-push.sh <core|worker|models|ops> <tag>
# Prints the pushed image URI (with digest) on stdout.
# shellcheck source=lib.sh
source "$(dirname "$0")/lib.sh"

component="$1"
tag="$2"
case "$component" in
  core) dockerfile=services/core/Dockerfile ;;
  worker) dockerfile=services/worker/Dockerfile ;;
  ops) dockerfile=scripts/deploy/ops.Dockerfile ;;
  # The models image converts upstream weights to safetensors at build time (~4.5 GB).
  models) dockerfile=services/models/Dockerfile ;;
  *) echo "unknown component: $component" >&2; exit 64 ;;
esac
context=.
[[ "$component" == models ]] && context=services/models

uri="$(image_uri "igs-$component" "$tag")"
latest="$(image_uri "igs-$component" latest)"
log "build $component → $uri"
docker buildx build \
  --platform linux/amd64 \
  --file "$dockerfile" \
  --tag "$uri" \
  --cache-from "type=registry,ref=${uri}" \
  --cache-to type=inline \
  --provenance=false \
  --push \
  "$context" >&2
endlog
digest="$(gcloud artifacts docker images describe "$uri" --format='value(image_summary.digest)')"
echo "${uri%:*}@${digest}"

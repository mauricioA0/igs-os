#!/usr/bin/env bash
# Post-deploy smoke checks. Fails the deploy if any check fails.
#   scripts/deploy/smoke.sh <api-url> <web-url>
set -euo pipefail
api="${1%/}"
web="${2%/}"

check() {
  local name="$1" url="$2" expect="${3:-200}"
  local code
  for attempt in 1 2 3 4 5; do
    code="$(curl -s -o /dev/null -w '%{http_code}' --max-time 20 "$url" || true)"
    if [[ "$code" == "$expect" ]]; then
      echo "ok   $name ($code)"
      return 0
    fi
    sleep $((attempt * 5))  # cold starts on min-instances=0
  done
  echo "FAIL $name: $url → $code (expected $expect)" >&2
  return 1
}

failed=0
check "api liveness" "$api/healthz" || failed=1
check "api readiness (DB)" "$api/readyz" || failed=1
check "api demo read" "$api/v1/trips?limit=1" || failed=1
check "web home" "$web/" || failed=1
check "web ops" "$web/ops" || failed=1
exit "$failed"

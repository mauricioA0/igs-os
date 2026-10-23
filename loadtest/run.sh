#!/usr/bin/env bash
# Load-test runner: mock LLM + API on an isolated database, k6 in Docker. No paid calls.
#
#   loadtest/run.sh reads            # API read path
#   loadtest/run.sh copilot          # copilot SSE turns against the mock model
#   API_KEY=igs_... loadtest/run.sh approvals   # first-writer-wins race on a-9003
#
# Env: DB (default igs_loadtest), VUS, DURATION/HOLD, MOCK_LATENCY_MS, API_PORT (8062).
# Results land in loadtest/results/<timestamp>-<suite>/ (k6 summary JSON + log).
set -euo pipefail
cd "$(dirname "$0")/.."

SUITE=${1:-reads}
DB=${DB:-igs_loadtest}
API_PORT=${API_PORT:-8062}
MOCK_PORT=${MOCK_PORT:-8099}
OUT="loadtest/results/$(date -u +%Y%m%dT%H%M%SZ)-$SUITE"
mkdir -p "$OUT"
export DATABASE_URL="postgres://igs:igs@localhost:5433/$DB"
export IGS_DATABASE_URL="postgresql+asyncpg://igs:igs@localhost:5433/$DB"

pids=()
cleanup() { for p in "${pids[@]:-}"; do kill "$p" 2>/dev/null || true; done; }
trap cleanup EXIT

if [[ "${PREPARE:-1}" == 1 ]]; then
  echo "▸ preparing $DB (migrate + seed + demo reset)"
  docker compose exec -T db psql -U igs -d postgres -qc "DROP DATABASE IF EXISTS $DB WITH (FORCE)" -c "CREATE DATABASE $DB"
  uv run alembic -c packages/py-common/alembic.ini -x "url=$DATABASE_URL" upgrade head >/dev/null
  uv run python -m igs_common.seed >/dev/null
  uv run python services/core/scripts/demo_reset.py --no-temporal 2>/dev/null
fi

echo "▸ mock LLM on :$MOCK_PORT (latency ${MOCK_LATENCY_MS:-400} ms)"
uv run --with fastapi --with uvicorn uvicorn loadtest.mock_llm.server:app --port "$MOCK_PORT" \
  --log-level warning >"$OUT/mock.log" 2>&1 &
pids+=($!)

echo "▸ API on :$API_PORT"
OPENAI_API_KEY=mock-key IGS_LLM_OPENAI_BASE_URL="http://localhost:$MOCK_PORT/v1" \
  IGS_LLM_MODELS='{"agent":"gpt-6.1-sol","chat":"gpt-6-luna","extractor":"gpt-6-luna","judge":"gpt-6.1-sol","simulator":"gpt-6-luna","reasoning":"gpt-6-astra","fast":"gpt-6-luna"}' \
  IGS_ENVIRONMENT=local uv run uvicorn igs_core.app:create_app --factory --port "$API_PORT" \
  --workers "${API_WORKERS:-1}" --log-level warning >"$OUT/api.log" 2>&1 &
pids+=($!)
for _ in $(seq 1 60); do curl -sf "localhost:$API_PORT/readyz" >/dev/null && break; sleep 0.5; done
for _ in $(seq 1 60); do curl -sf "localhost:$MOCK_PORT/healthz" >/dev/null && break; sleep 0.5; done

# Authenticated suites: the public demo is rate limited per client (igs_core.ratelimit), so
# copilot and approvals run as an ops user's API key. The mint script can't bind a user or the
# igs:approve scope yet, so both are set directly on the fresh row.
if [[ "$SUITE" != reads && -z "${API_KEY:-}" ]]; then
  API_KEY=$(uv run python services/core/scripts/mint_api_key.py --tenant igs --name loadtest \
    --scope igs:read --scope igs:write 2>/dev/null)
  docker compose exec -T db psql -U igs -d "$DB" -qc "update api_keys set
    created_by = (select id from users where role = 'ops' limit 1),
    scopes = array['igs:read','igs:write','igs:approve'] where name = 'loadtest'"
  export API_KEY
fi

case "$SUITE" in
  reads) script=api_reads.js ;;
  copilot) script=copilot_sse.js ;;
  approvals) script=approvals_race.js ;;
  *) echo "unknown suite $SUITE" >&2; exit 2 ;;
esac

echo "▸ k6 $script"
docker run --rm -i -v "$PWD/loadtest:/lt" \
  -e API_URL="http://host.docker.internal:$API_PORT" -e VUS -e DURATION -e HOLD -e RAMP -e API_KEY \
  grafana/k6:1.3.0 run --summary-export "/lt/${OUT#loadtest/}/summary.json" "/lt/k6/$script" \
  | tee "$OUT/k6.log"
echo "▸ results in $OUT"

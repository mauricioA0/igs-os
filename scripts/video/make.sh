#!/usr/bin/env bash
# One command to (re)record the demo video end to end on the local stack.
#
#   scripts/video/make.sh            # full: reset demo, build web, TTS, record, assemble
#   SKIP_TTS=1 scripts/video/make.sh # reuse existing narration audio
#   scripts/video/make.sh 03-account # re-record only some scenes, then re-assemble
#
# Needs: Docker (db + temporal), uv, Node 24, ffmpeg, OPENAI_API_KEY in .env.local (TTS, and the
# account brief the first time it's generated — cents). The copilot runs in its scripted fake
# mode. Starts its own API (:8000), worker and web (:3320) and stops them on exit; the web is
# built from an isolated copy so other builds of apps/web can't swap chunks under the recording.
# The approval scene approves IGS-2711 for real, so every full run resets the demo first.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
export PATH="$HOME/.nvm/versions/node/v24.13.0/bin:$PATH"
WORK="$ROOT/build/video"
LOGS="$WORK/logs"
COPY="$WORK/webcopy"
mkdir -p "$LOGS"

env_value() { grep -m1 "^$1=" .env.local | cut -d= -f2-; }
export OPENAI_API_KEY="$(env_value OPENAI_API_KEY)"
export IGS_LLM_MODELS="$(env_value IGS_LLM_MODELS)"
export DATABASE_URL=postgres://igs:igs@localhost:5433/igs
export IGS_DATABASE_URL="$DATABASE_URL"
export TEMPORAL_ADDRESS=localhost:7233 TEMPORAL_NAMESPACE=igs IGS_TEMPORAL_NAMESPACE=igs
export IGS_MODELS_URL="${IGS_MODELS_URL:-http://localhost:8090}"
export IGS_DB_APP_ROLE=igs_app

PIDS=()
cleanup() {
  for p in "${PIDS[@]:-}"; do [[ -n "$p" ]] && kill "$p" 2>/dev/null || true; done
  # pnpm/uv may leave their child servers behind: stop only listeners started from this repo.
  for port in 3320 8000; do
    for pid in $(lsof -ti "tcp:$port" -sTCP:LISTEN 2>/dev/null); do
      [[ "$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')" == "$ROOT"* ]] && kill "$pid" 2>/dev/null || true
    done
  done
}
trap cleanup EXIT

# wait_http <url> [seconds]
wait_http() {
  for _ in $(seq 1 "${2:-90}"); do curl -sf "$1" >/dev/null && return 0; sleep 1; done
  echo "timeout: $1 (see $LOGS)" >&2
  exit 1
}

echo "▸ stack"
docker compose up -d db temporal >/dev/null
for _ in $(seq 1 60); do
  docker compose exec -T temporal temporal operator cluster health --address localhost:7233 >/dev/null 2>&1 && break
  sleep 2
done
uv run alembic -c packages/py-common/alembic.ini upgrade head >/dev/null

if [[ $# -eq 0 ]]; then
  echo "▸ worker + demo reset (parks a live Lakeshore workflow at ops_review)"
  uv run python -m igs_worker >"$LOGS/worker.log" 2>&1 & PIDS+=($!)
  uv run python services/core/scripts/demo_reset.py
  uv run python -m igs_common.ingest index-all --tenant igs >/dev/null
fi

echo "▸ API"
uv run uvicorn igs_core.app:create_app --factory --port 8000 >"$LOGS/api.log" 2>&1 & PIDS+=($!)
wait_http http://localhost:8000/readyz

echo "▸ ops key for the web (acts as the seeded ops user; expires in a day)"
KEY="$(uv run python services/core/scripts/mint_api_key.py --tenant igs --name "video recording" \
  --scope igs:read --scope igs:write --scope igs:approve --expires-days 1 \
  --as-user lucia.fernandez@igs-demo.example 2>/dev/null)"

echo "▸ pre-warm the Lakeshore brief (cached, so Account 360 renders instantly)"
curl -sf --max-time 240 -H "Authorization: Bearer $KEY" \
  "http://localhost:8000/v1/accounts/17e97bd0-4cd1-52f0-b0bb-4bb8a22d91c8/brief" >/dev/null \
  || echo "warning: brief pre-warm failed (Account 360 will generate it live)" >&2

echo "▸ web (isolated build)"
mkdir -p "$COPY"
rsync -a --delete --exclude /services/models/models --exclude .venv --exclude .git \
  --exclude /apps/web/.next --exclude /build --exclude /spikes --exclude /infra "$ROOT/" "$COPY/"
(
  cd "$COPY/apps/web"
  rm -f .env.local
  export API_URL=http://localhost:8000 NEXT_PUBLIC_API_URL=http://localhost:8000
  export NEXT_PUBLIC_COPILOT_FAKE=1 IGS_WEB_ALLOW_SHARED_KEY=1 IGS_API_KEY="$KEY"
  pnpm build >"$LOGS/web-build.log" 2>&1 || { echo "web build failed: $LOGS/web-build.log" >&2; exit 1; }
  exec pnpm start -p 3320 >"$LOGS/web.log" 2>&1
) & PIDS+=($!)
wait_http http://localhost:3320/ 900

if [[ -z "${SKIP_TTS:-}" ]]; then
  echo "▸ narration (TTS; existing clips are reused)"
  uv run python scripts/video/tts.py
fi

echo "▸ record"
node scripts/video/record.mjs "$@"

echo "▸ assemble"
node scripts/video/assemble.mjs
ls -lh docs/delivery/video/*.mp4

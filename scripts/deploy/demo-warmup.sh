#!/usr/bin/env bash
# Wake and verify the live demo before showing it. Read-only by default.
#   scripts/deploy/demo-warmup.sh            # API + web + Lakeshore brief + one account question
#   scripts/deploy/demo-warmup.sh --chat     # also opens one coach chat turn (creates a conversation)
# Exit code 1 if any check is red. Never resets or edits demo data, never prints secrets.
set -uo pipefail

: "${CLOUDSDK_CORE_ACCOUNT:?set CLOUDSDK_CORE_ACCOUNT to the project owner account}"
export CLOUDSDK_CORE_ACCOUNT
export CLOUDSDK_CORE_PROJECT="${CLOUDSDK_CORE_PROJECT:-mv-cloud-509914}"
API="${IGS_API_URL:-https://igs-demo-core-fujfenyt5a-uc.a.run.app}"
WEB="${IGS_WEB_URL:-https://igs-os.vercel.app}"
REGION="${GCP_REGION:-us-central1}"
CHAT=0
[[ "${1:-}" == "--chat" ]] && CHAT=1

if [[ -t 1 ]]; then G=$'\e[32m'; R=$'\e[31m'; Y=$'\e[33m'; N=$'\e[0m'; else G= R= Y= N=; fi
rows=()
failed=0
body="$(mktemp)"
trap 'rm -f "$body"' EXIT

# record <name> <status> <ms> <detail>
record() {
  local mark
  case "$2" in ok) mark="${G}ok  ${N}" ;; warn) mark="${Y}warn${N}" ;; *) mark="${R}FAIL${N}"; failed=1 ;; esac
  rows+=("$(printf '%s  %-34s %7s ms  %s' "$mark" "$1" "$3" "$4")")
}

# call <name> <expected-code> <curl args...>; retries cold starts, keeps the body in $body
call() {
  local name="$1" expect="$2" out code secs ms
  shift 2
  for attempt in 1 2 3 4; do
    out="$(curl -s -o "$body" -w '%{http_code} %{time_total}' --max-time 120 "$@" || echo "000 0")"
    code="${out%% *}"
    secs="${out##* }"
    [[ "$code" == "$expect" ]] && break
    sleep $((attempt * 4))
  done
  ms="$(awk -v s="$secs" 'BEGIN { printf "%d", s * 1000 }')"
  if [[ "$code" == "$expect" ]]; then record "$name" ok "$ms" "$code"; return 0; fi
  record "$name" fail "$ms" "$code $(head -c 120 "$body" | tr '\n' ' ')"
  return 1
}

json() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(eval(sys.argv[2]))" "$body" "$1" 2>/dev/null; }

echo "IGS OS demo warm-up · api=$API · web=$WEB"

# ── Infra ─────────────────────────────────────────────────────────────────────
for svc in igs-demo-core igs-demo-models; do
  ready="$(gcloud run services describe "$svc" --region "$REGION" \
    --format='value(status.conditions[0].status)' 2>/dev/null || echo "?")"
  [[ "$ready" == True ]] && record "cloud run $svc" ok 0 "Ready" || record "cloud run $svc" fail 0 "$ready"
done
sql="$(gcloud sql instances describe igs-demo-pg --format='value(state,settings.activationPolicy)' 2>/dev/null || echo "?")"
[[ "$sql" == RUNNABLE* && "$sql" != *NEVER* ]] && record "cloud sql igs-demo-pg" ok 0 "$sql" \
  || record "cloud sql igs-demo-pg" fail 0 "$sql (paused? run demo-resume.sh)"

# ── API ───────────────────────────────────────────────────────────────────────
call "api /readyz (DB)" 200 "$API/readyz"
call "api accounts" 200 "$API/v1/accounts?limit=50"
lakeshore="$(json '[a["id"] for a in d["items"] if a["name"].startswith("Lakeshore")][0]')"
[[ -n "$lakeshore" ]] && record "lakeshore in accounts" ok 0 "$lakeshore" || record "lakeshore in accounts" fail 0 "not found"
call "api approvals/counts" 200 "$API/v1/approvals/counts" \
  && record "approvals pending" "$( [[ "$(json 'd["pending"]')" -ge 1 ]] 2>/dev/null && echo ok || echo warn)" 0 "pending=$(json 'd["pending"]')"
call "api approvals (pending)" 200 "$API/v1/approvals?status=pending&limit=10"
call "api trips" 200 "$API/v1/trips?limit=20"
call "api leads" 200 "$API/v1/leads?limit=20"
call "api flows" 200 "$API/v1/flows"
call "api executions" 200 "$API/v1/executions?limit=20"

if [[ -n "$lakeshore" ]]; then
  if call "api lakeshore 360" 200 "$API/v1/accounts/$lakeshore"; then
    health="$(json 'd["health"]')"
    [[ "$health" == red ]] && record "lakeshore health" ok 0 red || record "lakeshore health" fail 0 "${health:-?} (expected red)"
  fi
  # Generates (or serves the cached) cited brief: wakes OpenAI and the brief cache.
  call "api lakeshore brief (LLM)" 200 "$API/v1/accounts/$lakeshore/brief" \
    && record "brief cached" ok 0 "cached=$(json 'd.get("cached")')"
  # Answering spends tokens but writes nothing: wakes the models service (embed + rerank) via core.
  call "api lakeshore ask (RAG)" 200 -X POST -H 'content-type: application/json' \
    -d '{"question":"Why is this account red and what is due next?"}' \
    "$API/v1/accounts/$lakeshore/ask" \
    && record "ask citations" "$( [[ "$(json 'len(d.get("citations",[]))')" -ge 1 ]] 2>/dev/null && echo ok || echo warn)" 0 \
      "citations=$(json 'len(d.get("citations",[]))')"
fi

if ((CHAT)); then
  if call "chat start" 201 -X POST -H 'content-type: application/json' \
    -d '{"source":"warmup","message":"Hi, I coach a D1 womens soccer team. Spring tour to Buenos Aires?"}' \
    "$API/v1/chat/conversations"; then
    conv="$(json 'd.get("conversation_id") or d.get("id")')"
    reply=""
    for _ in $(seq 1 20); do
      curl -s -o "$body" --max-time 20 "$API/v1/chat/conversations/$conv/messages" || true
      reply="$(json 'len([m for m in (d if isinstance(d,list) else d.get("items",[])) if m.get("role") in ("assistant","bot")])')"
      [[ "${reply:-0}" -ge 1 ]] && break
      sleep 3
    done
    [[ "${reply:-0}" -ge 1 ]] && record "chat bot reply" ok 0 "conversation $conv" || record "chat bot reply" fail 0 "no reply in 60s"
  fi
else
  record "chat turn" warn 0 "skipped (read-only run; use --chat)"
fi

# ── Web (Vercel) ──────────────────────────────────────────────────────────────
routes=(/ /chat /ops /ops/accounts /ops/approvals /ops/trips /ops/leads /ops/flows /design)
[[ -n "$lakeshore" ]] && routes+=("/ops/accounts/$lakeshore")
for r in "${routes[@]}"; do
  call "web $r" 200 -L "$WEB$r"
done
grep -q "Lakeshore" "$body" && record "web lakeshore page shows name" ok 0 "" \
  || record "web lakeshore page shows name" warn 0 "name not in HTML (client-rendered?)"

echo
printf '%s\n' "${rows[@]}"
echo
if ((failed)); then echo "${R}NOT READY${N}: fix the red rows (docs/infra/runbook.md)"; exit 1; fi
echo "${G}READY${N} — open $WEB/ops"

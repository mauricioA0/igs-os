#!/usr/bin/env bash
# Regenerate the Python and TypeScript models from flow.schema.json.
# Usage: packages/flow-schema/scripts/gen.sh [--check]
#   --check  regenerate into a temp dir and fail if the committed files differ (CI).
set -euo pipefail

root="$(cd "$(dirname "$0")/../../.." && pwd)"
schema="$root/packages/flow-schema/flow.schema.json"
py_out="$root/packages/py-common/src/igs_common/flows/schema.py"
ts_out="$root/apps/web/src/lib/flow-schema.ts"

check=false
[[ "${1:-}" == "--check" ]] && check=true

header=$'# Generated from packages/flow-schema/flow.schema.json by scripts/gen.sh. Do not edit.\n# ruff: noqa: E501\n# pyright: reportAssignmentType=false, reportIncompatibleVariableOverride=false'

tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

python3 "$root/packages/flow-schema/scripts/codegen_schema.py" "$schema" > "$tmp/codegen.json"

(cd "$root" && uv run --quiet datamodel-codegen \
  --input "$tmp/codegen.json" \
  --input-file-type jsonschema \
  --output "$tmp/schema.py" \
  --output-model-type pydantic_v2.BaseModel \
  --target-python-version 3.13 \
  --use-annotated \
  --field-constraints \
  --use-standard-collections \
  --use-union-operator \
  --enum-field-as-literal all \
  --use-title-as-name \
  --use-schema-description \
  --disable-timestamp \
  --custom-file-header "$header" \
  --formatters ruff-format ruff-check 2>/dev/null)

# Format with the repo's ruff settings (the temp dir has no pyproject to pick them up from).
(cd "$root" && uv run --quiet ruff format --quiet --config "$root/pyproject.toml" "$tmp/schema.py")

python3 "$root/packages/flow-schema/scripts/gen_ts.py" "$tmp/codegen.json" > "$tmp/flow-schema.ts"

if $check; then
  diff -u "$py_out" "$tmp/schema.py"
  diff -u "$ts_out" "$tmp/flow-schema.ts"
  echo "flow-schema: generated files are up to date"
else
  cp "$tmp/schema.py" "$py_out"
  cp "$tmp/flow-schema.ts" "$ts_out"
  echo "flow-schema: wrote $py_out and $ts_out"
fi

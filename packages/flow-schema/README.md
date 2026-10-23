# flow-schema

`flow.schema.json` is the source of truth for flow definitions (spec:
`docs/architecture/flow-engine.md`). Examples in `examples/` are the three demo flows.

Generated from it — never edit by hand:

| Output | Used by |
|---|---|
| `packages/py-common/src/igs_common/flows/schema.py` (Pydantic v2, tagged unions on `type`) | API, worker, validator |
| `apps/web/src/lib/flow-schema.ts` | Flow editor |

```bash
packages/flow-schema/scripts/gen.sh          # regenerate both
packages/flow-schema/scripts/gen.sh --check  # CI: fail if the committed files are stale
```

Models are provider-neutral: nodes reference a model **role** (`{"role": "agent" | "fast" |
"reasoning"}`) and the tenant's model registry maps roles to concrete provider model ids.

Runtime pieces next to the generated models (`igs_common.flows`):
- `cel.py` — CEL expressions and `{{ }}` templates (compile at publish, evaluate at run time).
- `validate.py` — publish-time validation (§13 rules + the approval security rule).

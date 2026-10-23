"""The generated TypeScript types must match the schema (Python models: gen.sh --check)."""

import json
import subprocess
import sys
from pathlib import Path


def test_typescript_types_are_up_to_date(flow_schema_dir: Path, tmp_path: Path) -> None:
    scripts = flow_schema_dir / "scripts"
    codegen = subprocess.run(  # noqa: S603 (repo scripts, fixed args)
        [sys.executable, scripts / "codegen_schema.py", flow_schema_dir / "flow.schema.json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    json.loads(codegen)
    (tmp_path / "codegen.json").write_text(codegen)
    ts = subprocess.run(  # noqa: S603 (repo scripts, fixed args)
        [sys.executable, scripts / "gen_ts.py", tmp_path / "codegen.json"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    committed = flow_schema_dir.parents[1] / "apps" / "web" / "src" / "lib" / "flow-schema.ts"
    assert ts == committed.read_text(), "run packages/flow-schema/scripts/gen.sh"

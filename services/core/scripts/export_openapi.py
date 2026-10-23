"""Write the OpenAPI document to apps/web/openapi.json (input for the typed web client).

    uv run python services/core/scripts/export_openapi.py [--check]

``--check`` exits 1 if the committed file is stale (used in CI).
"""

import json
import sys
from pathlib import Path

from igs_core.app import create_app
from igs_core.config import Settings
from igs_core.repositories import Repositories

ROOT = Path(__file__).resolve().parents[3]
TARGET = ROOT / "apps" / "web" / "openapi.json"


def render() -> str:
    # No database needed: the schema only depends on routes and models.
    app = create_app(
        Settings(environment="test"),
        repos=Repositories(directory=None, trips=None, accounts=None),  # type: ignore[arg-type]
    )
    return json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = TARGET.read_text() if TARGET.exists() else ""
        if current != content:
            print(f"{TARGET} is stale; run scripts/export_openapi.py", file=sys.stderr)
            return 1
        return 0
    TARGET.write_text(content)
    print(f"wrote {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

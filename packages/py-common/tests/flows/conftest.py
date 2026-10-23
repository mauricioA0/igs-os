import copy
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

FLOW_SCHEMA_DIR = Path(__file__).resolve().parents[4] / "packages" / "flow-schema"

Loader = Callable[[str], dict[str, Any]]


@pytest.fixture(scope="session")
def flow_schema_dir() -> Path:
    return FLOW_SCHEMA_DIR


@pytest.fixture
def example() -> Loader:
    """Load a fresh, mutable copy of an example flow by name."""

    def load(name: str) -> dict[str, Any]:
        raw = json.loads((FLOW_SCHEMA_DIR / "examples" / f"{name}.json").read_text())
        return copy.deepcopy(raw)

    return load

"""Shared constants for the core API tests (unique module name: tests dirs are not packages)."""

import importlib.util
from pathlib import Path
from types import ModuleType
from uuid import UUID

DEMO_TENANT = UUID("00000000-0000-0000-0000-00000000d3e0")
OTHER_TENANT = UUID("00000000-0000-0000-0000-0000000000aa")
API_KEY = "igs_test_key_123"


def load_export_script() -> ModuleType:
    path = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"
    spec = importlib.util.spec_from_file_location("igs_core_export_openapi", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

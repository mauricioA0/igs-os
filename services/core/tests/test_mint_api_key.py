"""The mint script stores only the hash, and the key it prints resolves to its tenant."""

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import select, text

from igs_common.db import system_scope
from igs_common.db.models import ApiKey, Tenant
from igs_common.testing import database_url

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "mint_api_key.py"


def _load():
    spec = importlib.util.spec_from_file_location("mint_api_key", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_new_key_has_prefix_and_entropy() -> None:
    mod = _load()
    a, b = mod.new_key(), mod.new_key()
    assert a.startswith("igs_") and a != b and len(a) > 40


async def test_mint_stores_hash_and_resolves() -> None:
    from igs_common.db.session import configure
    from igs_common.seed import load
    from igs_core.deps import hash_api_key

    # Own database (created and migrated by conftest), seeded with the demo tenant.
    try:
        configure(database_url("igs_test_mint", driver="postgresql+asyncpg"))
        async with system_scope() as s:
            if await s.scalar(select(Tenant).where(Tenant.slug == "igs")) is None:
                await load(s)
    except OSError as exc:  # pragma: no cover - env dependent
        pytest.skip(f"Postgres not reachable: {exc}")
    mod = _load()
    key, row = await mod.mint("igs", "test-mint", ["igs:read", "igs:write"], 1)
    async with system_scope() as s:
        stored = await s.scalar(select(ApiKey).where(ApiKey.id == row.id))
        assert stored is not None and stored.hash == hash_api_key(key)
        assert key not in (stored.hash, stored.prefix) and stored.prefix == key[:10]
        resolved = (
            await s.execute(
                text("select tenant_id, scopes from resolve_api_key(:h)"), {"h": stored.hash}
            )
        ).one()
        assert resolved.tenant_id == stored.tenant_id
        assert sorted(resolved.scopes) == ["igs:read", "igs:write"]
        await s.delete(stored)

"""Mint an API key for a tenant (MCP clients, service-to-service callers).

The plaintext key is printed exactly once; only its sha256 is stored. Example:

    DATABASE_URL=postgres://igs:igs@localhost:5433/igs \\
    uv run python services/core/scripts/mint_api_key.py --tenant igs --name "Claude Code" \\
        --scope igs:read --scope igs:write

    claude mcp add --transport http igs-os http://localhost:8000/mcp \\
        --header "Authorization: Bearer <printed key>"
"""

import argparse
import asyncio
import secrets
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from igs_common.db import system_scope
from igs_common.db.models import ApiKey, Tenant, User
from igs_common.domain.tools import SCOPE_EXTERNAL, SCOPE_READ, SCOPE_WRITE
from igs_core.deps import API_KEY_PREFIX, hash_api_key

# igs:approve lets a key decide approvals over REST. Give it only to automation a person owns;
# MCP clients (Claude Code/Desktop) must never get it — a human approves in the ops panel.
SCOPE_APPROVE = "igs:approve"
SCOPE_ADMIN = "igs:admin"
SCOPES = (SCOPE_READ, SCOPE_WRITE, SCOPE_EXTERNAL, SCOPE_APPROVE, SCOPE_ADMIN)


def new_key() -> str:
    return API_KEY_PREFIX + secrets.token_urlsafe(32)


async def mint(
    tenant_slug: str,
    name: str,
    scopes: Sequence[str],
    expires_days: int | None,
    as_user: str | None = None,
) -> tuple[str, ApiKey]:
    """`as_user` (email) binds the key to a user: the key acts with that user's role."""
    key = new_key()
    async with system_scope() as s:
        tenant = await s.scalar(select(Tenant).where(Tenant.slug == tenant_slug))
        if tenant is None:
            raise SystemExit(f"tenant {tenant_slug!r} not found")
        owner = None
        if as_user:
            owner = await s.scalar(
                select(User).where(User.tenant_id == tenant.id, User.email == as_user)
            )
            if owner is None:
                raise SystemExit(f"user {as_user!r} not found in tenant {tenant_slug!r}")
        row = ApiKey(
            created_by=owner.id if owner else None,
            tenant_id=tenant.id,
            name=name,
            hash=hash_api_key(key),
            prefix=key[: len(API_KEY_PREFIX) + 6],
            scopes=sorted(set(scopes)),
            expires_at=datetime.now(UTC) + timedelta(days=expires_days) if expires_days else None,
        )
        s.add(row)
    return key, row


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mint an API key for a tenant (printed once).")
    parser.add_argument("--tenant", required=True, help="tenant slug, e.g. igs")
    parser.add_argument("--name", required=True, help="who uses the key, e.g. 'Claude Code'")
    parser.add_argument(
        "--scope", action="append", choices=SCOPES, help="repeatable; default igs:read"
    )
    parser.add_argument("--expires-days", type=int, default=90, help="0 = never")
    parser.add_argument(
        "--as-user", help="email of the user the key acts for (its role); default viewer"
    )
    args = parser.parse_args(argv)
    scopes = args.scope or [SCOPE_READ]
    key, row = asyncio.run(
        mint(args.tenant, args.name, scopes, args.expires_days or None, args.as_user)
    )
    print(key)
    expires = row.expires_at.date().isoformat() if row.expires_at else "never"
    print(
        f"# {row.name}: scopes {', '.join(row.scopes)}, expires {expires}. "
        "Shown once; store it in a secret manager.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()

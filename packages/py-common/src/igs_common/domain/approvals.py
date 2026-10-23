"""Approval binding: an approval is valid only for the exact action it was shown.

The hash covers the action name and its canonicalized arguments. Any change to the payload after
approval produces a different hash, so the approval no longer matches and must be requested again.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import math
from collections.abc import Mapping
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from pydantic import BaseModel

HASH_PREFIX = "sha256:"


def _normalize(value: Any) -> Any:
    match value:
        case None | bool() | int() | str():
            return value
        case float():
            if not math.isfinite(value):
                raise ValueError("non-finite floats can't be hashed")
            # Integral floats hash like ints so 3 and 3.0 are the same payload.
            return int(value) if value.is_integer() else value
        case Decimal():
            if not value.is_finite():
                raise ValueError("non-finite decimals can't be hashed")
            return format(value.normalize(), "f")
        case Enum():
            return _normalize(value.value)
        case UUID():
            return str(value)
        case datetime():
            if value.tzinfo is None:
                raise ValueError("naive datetimes are ambiguous; use timezone-aware values")
            return value.astimezone(UTC).isoformat()
        case date():
            return value.isoformat()
        case BaseModel():
            return _normalize(value.model_dump(mode="python"))
        case Mapping():
            keys = [str(k) for k in value]
            if len(set(keys)) != len(keys):
                raise ValueError("mapping keys collide after str()")
            return {str(k): _normalize(v) for k, v in value.items()}
        case set() | frozenset():
            return sorted((_normalize(v) for v in value), key=canonical_json)
        case list() | tuple():
            return [_normalize(v) for v in value]
        case _:
            raise TypeError(f"unsupported type in approval payload: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    """Stable JSON: sorted keys, no whitespace, UTF-8, normalized scalars."""
    return json.dumps(
        _normalize(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )


def payload_hash(action: str, payload: Any) -> str:
    if not action:
        raise ValueError("action is required")
    body = canonical_json({"action": action, "payload": payload})
    return HASH_PREFIX + hashlib.sha256(body.encode()).hexdigest()


def verify_payload(expected_hash: str, action: str, payload: Any) -> bool:
    """Constant-time check that ``payload`` is exactly what was approved."""
    return hmac.compare_digest(expected_hash, payload_hash(action, payload))

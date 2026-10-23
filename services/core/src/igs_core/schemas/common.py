import base64
import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict

from igs_core.errors import ProblemError


class Schema(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None = None


def encode_cursor(*values: Any) -> str:
    raw = json.dumps([str(v) for v in values]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str, arity: int) -> list[str]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded))
    except ValueError as exc:
        raise ProblemError(400, "invalid-cursor", "The cursor is not valid.") from exc
    if not isinstance(values, list) or len(values) != arity:
        raise ProblemError(400, "invalid-cursor", "The cursor is not valid.")
    return [str(v) for v in values]


def parse_cursor_value[T](parse: Callable[[str], T], value: str) -> T:
    try:
        return parse(value)
    except ValueError as exc:
        raise ProblemError(400, "invalid-cursor", "The cursor is not valid.") from exc

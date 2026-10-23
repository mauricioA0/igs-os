"""Filter validation, tenant injection and evaluation, shared by every store.

User filters use the Agent Retrieval syntax restricted to what survives the service's two-level
limit once the tenant clause is added:

    {"source": {"$eq": "contract"}, "valid_until": {"$gte": 20500}}   # implicit AND
    {"$or": [{"country": {"$eq": "AR"}}, {"country": {"$eq": "BR"}}]}  # one logical level
    {"account_id": "…"}                                                 # shorthand for $eq

The tenant clause is always added here, never by the caller: a filter that mentions `tenant_id`
is rejected.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from igs_common.rag.types import Filter

STRING_FIELDS = frozenset(
    {"account_id", "source_kind", "source_id", "source", "doc_type", "country", "city"}
)
NUMBER_FIELDS = frozenset({"valid_from", "valid_until"})
FILTER_FIELDS = STRING_FIELDS | NUMBER_FIELDS

COMPARISON_OPS = frozenset({"$eq", "$ne", "$gt", "$gte", "$lt", "$lte", "$in", "$nin"})
LOGICAL_OPS = frozenset({"$and", "$or"})

# (field, op, value) after normalization
Clause = tuple[str, str, Any]


class FilterError(ValueError):
    pass


def normalize(user: Filter | None) -> tuple[str, list[Clause]]:
    """Validate a user filter → ("$and" | "$or", single-field clauses)."""
    if not user:
        return "$and", []
    logical = [k for k in user if k in LOGICAL_OPS]
    if logical:
        if len(user) != 1:
            raise FilterError("a logical operator must be the only key at the top level")
        op = logical[0]
        items = user[op]
        if not isinstance(items, list) or not items:
            raise FilterError(f"{op} needs a non-empty list")
        clauses: list[Clause] = []
        for item in items:
            if not isinstance(item, Mapping) or len(item) != 1:
                raise FilterError(f"each {op} item must hold exactly one field (max two levels)")
            clauses.extend(_field_clauses(dict(item)))
        return op, clauses
    return "$and", _field_clauses(user)


def _field_clauses(fields: Mapping[str, Any]) -> list[Clause]:
    clauses: list[Clause] = []
    for name, cond in fields.items():
        if name == "tenant_id":
            raise FilterError("tenant_id is set by the server, not by the caller")
        if name.startswith("$"):
            raise FilterError(f"nested logical operator {name!r} exceeds the two-level limit")
        if name not in FILTER_FIELDS:
            raise FilterError(f"unknown filter field {name!r}")
        ops = cond if isinstance(cond, Mapping) else {"$eq": cond}
        if not ops:
            raise FilterError(f"empty condition for {name!r}")
        for op, value in ops.items():
            if op not in COMPARISON_OPS:
                raise FilterError(f"unsupported operator {op!r} on {name!r}")
            _check_value(name, op, value)
            clauses.append((name, op, value))
    return clauses


def _check_value(name: str, op: str, value: Any) -> None:
    if op in ("$in", "$nin"):
        if name in NUMBER_FIELDS:
            raise FilterError(f"{op} works on string fields only ({name!r} is numeric)")
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise FilterError(f"{op} on {name!r} needs a list of strings")
        return
    if name in NUMBER_FIELDS:
        if isinstance(value, bool) or not isinstance(value, int | float):
            raise FilterError(f"{name!r} compares against numbers (unix days)")
    elif op in ("$gt", "$gte", "$lt", "$lte"):
        raise FilterError(f"range operators only apply to numeric fields, not {name!r}")
    elif not isinstance(value, str):
        raise FilterError(f"{name!r} compares against strings")


def with_tenant(tenant_id: str, user: Filter | None) -> Filter:
    """The filter actually sent to a store: tenant clause AND the user's filter."""
    tenant = {"tenant_id": {"$eq": tenant_id}}
    logic, clauses = normalize(user)
    singles = [{name: {op: value}} for name, op, value in clauses]
    if not singles:
        return {"$and": [tenant]}
    if logic == "$or" and len(singles) > 1:
        return {"$and": [tenant, {"$or": singles}]}
    return {"$and": [tenant, *singles]}


def matches(payload: Mapping[str, Any], user: Filter | None) -> bool:
    """Evaluate a user filter against a chunk payload (in-memory store and fakes)."""
    logic, clauses = normalize(user)
    if not clauses:
        return True
    results = (_match_clause(payload.get(name), op, value) for name, op, value in clauses)
    return any(results) if logic == "$or" else all(results)


def _match_clause(actual: Any, op: str, expected: Any) -> bool:
    if op == "$ne":
        return actual != expected
    if op == "$nin":
        return actual not in expected
    if actual is None:
        return False
    match op:
        case "$eq":
            return actual == expected
        case "$in":
            return actual in expected
        case "$gt":
            return actual > expected
        case "$gte":
            return actual >= expected
        case "$lt":
            return actual < expected
        case "$lte":
            return actual <= expected
    raise FilterError(f"unsupported operator {op!r}")  # pragma: no cover - validated earlier


def to_sql(user: Filter | None, *, prefix: str = "f") -> tuple[str, dict[str, Any]]:
    """Compile a user filter to a SQL boolean over `document_chunks` (payload jsonb + account_id).

    Returns ("TRUE", {}) for no filter. Parameter names are `{prefix}{n}`. `$ne`/`$nin` use
    `IS DISTINCT FROM` so rows missing the field match, like the in-memory evaluator.
    """
    logic, clauses = normalize(user)
    if not clauses:
        return "TRUE", {}
    parts: list[str] = []
    params: dict[str, Any] = {}
    for i, (name, op, value) in enumerate(clauses):
        p = f"{prefix}{i}"
        parts.append(_clause_sql(name, op, p))
        params[p] = value
    joiner = " OR " if logic == "$or" else " AND "
    return "(" + joiner.join(parts) + ")", params


def _clause_sql(name: str, op: str, p: str) -> str:
    if name == "account_id":
        col, cast, array_cast = "account_id", "CAST(:{p} AS uuid)", "CAST(:{p} AS uuid[])"
    elif name in NUMBER_FIELDS:
        col = f"((payload->>'{name}')::numeric)"
        cast, array_cast = "CAST(:{p} AS numeric)", ""
    else:
        col, cast, array_cast = (
            f"(payload->>'{name}')",
            "CAST(:{p} AS text)",
            "CAST(:{p} AS text[])",
        )
    rhs = cast.format(p=p)
    match op:
        case "$eq":
            return f"{col} = {rhs}"
        case "$ne":
            return f"{col} IS DISTINCT FROM {rhs}"
        case "$gt":
            return f"{col} > {rhs}"
        case "$gte":
            return f"{col} >= {rhs}"
        case "$lt":
            return f"{col} < {rhs}"
        case "$lte":
            return f"{col} <= {rhs}"
        case "$in":
            return f"{col} = ANY({array_cast.format(p=p)})"
        case "$nin":
            return f"(NOT ({col} = ANY({array_cast.format(p=p)})) OR {col} IS NULL)"
    raise FilterError(f"unsupported operator {op!r}")  # pragma: no cover - validated earlier

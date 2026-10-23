"""CEL expressions and `{{ }}` templates for flow definitions.

Spec: docs/architecture/flow-engine.md §3.2 (scopes) and §6 (expressions).

- `compile_expression` parses once (publish time) and rejects syntax errors, oversize
  expressions and unknown top-level scopes.
- `evaluate` runs a compiled expression against a context of plain JSON-like values and
  returns plain Python values.
- Templates: a string that is exactly one placeholder evaluates to the typed value;
  anything else renders each placeholder as text.

Cost limits. CEL has no loops or recursion: evaluation is bounded by the size of the
expression and of the data it walks. We cap the expression (length and parse-tree size),
the number of nested comprehension macros, and the rendered output. Python cannot preempt
a running evaluation, so there is no wall-clock timeout; the caps above are what keep
evaluation cheap, together with the 256 KB cap on node outputs (§14).

Determinism. There is no `now()`; time comes from `execution.now`, which the engine sets
from workflow time, so replays evaluate identically.
"""

from __future__ import annotations

import datetime as dt
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

import celpy
from celpy import celtypes
from celpy.adapter import json_to_cel
from celpy.celparser import CELParseError
from celpy.evaluation import CELEvalError

MAX_EXPRESSION_LENGTH = 4_000
MAX_PARSE_NODES = 1_500
MAX_COMPREHENSION_DEPTH = 3
MAX_RENDERED_BYTES = 64 * 1024

SCOPES: frozenset[str] = frozenset({"trigger", "vars", "nodes", "execution"})

_PLACEHOLDER = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)
_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"")
_MACRO_VAR = re.compile(r"\.(?:map|filter|exists|exists_one|all)\(\s*([A-Za-z_]\w*)\s*,")
_IDENT = re.compile(r"(?<![\w.])([A-Za-z_]\w*)\b(?!\s*\()")
# `nodes.<id>` or, for ids with a hyphen (not valid after a dot in CEL), `nodes['<id>']`.
_NODE_REF = re.compile(
    r"(?<![\w.])nodes(?:\.([a-z][a-z0-9_]{0,62})|\[\s*['\"]([a-z][a-z0-9_-]{0,62})['\"]\s*\])"
)
_CALL = re.compile(r"(\.)?\b([A-Za-z_]\w*)\s*\(")
_MACRO_CALL = re.compile(r"\.(?:map|filter|exists|exists_one|all)$")
_RESERVED = frozenset({"true", "false", "null", "in"})
_MACROS = frozenset({"map", "filter", "exists", "exists_one", "all"})
# CEL standard functions/methods available in cel-python, plus the engine library below.
_STD_FUNCTIONS = frozenset(
    {
        "size", "has", "int", "uint", "double", "string", "bytes", "bool", "type", "dyn",
        "timestamp", "duration", "matches", "contains", "startsWith", "endsWith",
        "getDate", "getDayOfMonth", "getDayOfWeek", "getDayOfYear", "getFullYear",
        "getHours", "getMilliseconds", "getMinutes", "getMonth", "getSeconds",
    }
)  # fmt: skip

ErrorKind = Literal[
    "syntax",
    "too_long",
    "too_complex",
    "unknown_scope",
    "unknown_function",
    "evaluation",
    "output",
]


class ExpressionError(Exception):
    """Error class `expression` (§11): never retried."""

    def __init__(self, kind: ErrorKind, message: str, source: str) -> None:
        super().__init__(f"{message} in expression: {source[:200]}")
        self.kind = kind
        self.message = message
        self.source = source


# ── Engine library ──────────────────────────────────────────────────────────


def _join(items: celtypes.ListType, sep: celtypes.StringType | None = None) -> celtypes.StringType:
    return celtypes.StringType(str(sep or "").join(str(_to_text(i)) for i in items))


def _split(text: celtypes.StringType, sep: celtypes.StringType) -> celtypes.ListType:
    return celtypes.ListType([celtypes.StringType(p) for p in str(text).split(str(sep))])


def _replace(
    text: celtypes.StringType, old: celtypes.StringType, new: celtypes.StringType
) -> celtypes.StringType:
    return celtypes.StringType(str(text).replace(str(old), str(new)))


def _date(ts: celtypes.TimestampType) -> celtypes.StringType:
    """`date(ts)` → `YYYY-MM-DD` in the timestamp's own offset."""
    return celtypes.StringType(ts.date().isoformat())


_MONTHS = {
    "en": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
    "es": ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"],
}


def _format_date(ts: celtypes.TimestampType, locale: celtypes.StringType) -> celtypes.StringType:
    """`formatDate(ts, 'en')` → `Mar 7, 2027`; `formatDate(ts, 'es')` → `7 mar 2027`."""
    lang = str(locale).split("-")[0].lower()
    month = _MONTHS.get(lang, _MONTHS["en"])[ts.month - 1]
    text = f"{ts.day} {month} {ts.year}" if lang == "es" else f"{month} {ts.day}, {ts.year}"
    return celtypes.StringType(text)


FUNCTIONS: dict[str, Callable[..., Any]] = {
    "join": _join,
    "split": _split,
    "replace": _replace,
    "lowerAscii": lambda s: celtypes.StringType(str(s).lower()),
    "upperAscii": lambda s: celtypes.StringType(str(s).upper()),
    "trim": lambda s: celtypes.StringType(str(s).strip()),
    "date": _date,
    "formatDate": _format_date,
}

_ENV = celpy.Environment()


# ── `default(x, fallback)` ──────────────────────────────────────────────────
#
# CEL functions never see an argument that failed to evaluate (a missing field is an
# error, not null), so `default` is expanded at compile time into plain CEL:
#   default(a.b.c, y)  →  (has(a.b) && has(a.b.c) && a.b.c != null) ? a.b.c : y
# The first argument must be a field path (`scope.field...`); that is the case it exists
# for (optional fields in trigger payloads and node outputs).

_DEFAULT_CALL = re.compile(r"(?<![\w.])default\s*\(")
_FIELD_PATH = re.compile(r"^[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)+$")


def _split_args(text: str, start: int) -> tuple[list[str], int]:
    """Split the call arguments starting after `(` at `start`; returns (args, end index)."""
    args, depth, quote, buf = [], 0, "", []
    i = start
    while i < len(text):
        ch = text[i]
        if quote:
            buf.append(ch)
            if ch == "\\":
                buf.append(text[i + 1])
                i += 1
            elif ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
            buf.append(ch)
        elif ch in "([{":
            depth += 1
            buf.append(ch)
        elif ch in ")]}" and depth:
            depth -= 1
            buf.append(ch)
        elif ch == ")":
            args.append("".join(buf).strip())
            return args, i
        elif ch == "," and not depth:
            args.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
        i += 1
    raise ExpressionError("syntax", "unclosed default(", text)


def _expand_default(source: str) -> str:
    while match := _DEFAULT_CALL.search(source):
        args, end = _split_args(source, match.end())
        if len(args) != 2 or not all(args):
            raise ExpressionError("syntax", "default() takes exactly 2 arguments", source)
        value, fallback = (_expand_default(a) for a in args)
        if not _FIELD_PATH.match(value):
            raise ExpressionError(
                "syntax", "default() needs a field path as first argument (e.g. vars.x.y)", source
            )
        parts = value.split(".")
        checks = [f"has({'.'.join(parts[: i + 1])})" for i in range(1, len(parts))]
        guard = " && ".join([*checks, f"{value} != null"])
        expanded = f"(({guard}) ? {value} : {fallback})"
        source = source[: match.start()] + expanded + source[end + 1 :]
    return source


# ── Compile ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompiledExpression:
    source: str
    scopes: frozenset[str]
    node_refs: frozenset[str]
    _program: celpy.Runner = field(repr=False, compare=False)


def referenced_scopes(source: str) -> tuple[frozenset[str], frozenset[str]]:
    """Top-level identifiers and `nodes.<id>` references, ignoring string literals and
    variables bound by comprehension macros (`items.map(i, i.id)`)."""
    node_refs = frozenset(a or b for a, b in _NODE_REF.findall(_mask_strings_keep_index(source)))
    code = _STRING_LITERAL.sub("''", source)
    bound = set(_MACRO_VAR.findall(code))
    idents = {
        name
        for name in _IDENT.findall(code)
        if name not in bound and name not in _RESERVED and name not in _MACROS
    }
    return frozenset(idents), node_refs


def _mask_strings_keep_index(source: str) -> str:
    """Blank out string literals except the ones used as `nodes['<id>']` keys."""

    def keep(match: re.Match[str]) -> str:
        before = source[: match.start()].rstrip()
        return match.group() if before.endswith("nodes[") else "''"

    return _STRING_LITERAL.sub(keep, source)


def called_functions(source: str) -> frozenset[str]:
    code = _STRING_LITERAL.sub("''", source)
    return frozenset(name for _, name in _CALL.findall(code))


def _comprehension_depth(source: str) -> int:
    """Deepest nesting of map/filter/exists/all macros (string literals ignored)."""
    code = _STRING_LITERAL.sub("''", source)
    stack: list[bool] = []
    best = 0
    for i, ch in enumerate(code):
        if ch == "(":
            stack.append(bool(_MACRO_CALL.search(code[:i])))
            best = max(best, sum(stack))
        elif ch == ")" and stack:
            stack.pop()
    return best


def compile_expression(source: str, *, scopes: frozenset[str] = SCOPES) -> CompiledExpression:
    source = source.strip()
    if not source:
        raise ExpressionError("syntax", "empty expression", source)
    if len(source) > MAX_EXPRESSION_LENGTH:
        raise ExpressionError(
            "too_long", f"expression longer than {MAX_EXPRESSION_LENGTH} characters", source
        )
    try:
        tree = _ENV.compile(_expand_default(source))
    except CELParseError as exc:
        message = f"syntax error: {str(exc).splitlines()[0]}"
        raise ExpressionError("syntax", message, source) from exc
    if sum(1 for _ in tree.iter_subtrees()) > MAX_PARSE_NODES:
        raise ExpressionError("too_complex", "expression is too complex", source)
    if _comprehension_depth(source) > MAX_COMPREHENSION_DEPTH:
        raise ExpressionError(
            "too_complex",
            f"more than {MAX_COMPREHENSION_DEPTH} nested map/filter/exists/all macros",
            source,
        )
    used, node_refs = referenced_scopes(source)
    used -= {"default"}
    unknown_fns = sorted(called_functions(source) - _STD_FUNCTIONS - _MACROS - FUNCTIONS.keys())
    unknown_fns = [f for f in unknown_fns if f != "default"]
    if unknown_fns:
        raise ExpressionError(
            "unknown_function",
            f"unknown function(s) {', '.join(unknown_fns)}"
            + ("; use execution.now for the current time" if "now" in unknown_fns else ""),
            source,
        )
    unknown = sorted(used - scopes)
    if unknown:
        raise ExpressionError(
            "unknown_scope",
            f"unknown name(s) {', '.join(unknown)}; available: {', '.join(sorted(scopes))}",
            source,
        )
    program = _ENV.program(tree, functions=FUNCTIONS)
    return CompiledExpression(source, used, node_refs, program)


# ── Evaluate ────────────────────────────────────────────────────────────────


def evaluate(expr: CompiledExpression | str, context: Mapping[str, Any]) -> Any:
    """Evaluate against `context` (scope name → JSON-like value). Returns plain Python."""
    compiled = compile_expression(expr) if isinstance(expr, str) else expr
    activation = {k: _to_cel(v) for k, v in context.items()}
    try:
        result = compiled._program.evaluate(activation)
    except CELEvalError as exc:
        raise ExpressionError("evaluation", _eval_message(exc), compiled.source) from exc
    except (TypeError, ValueError, ArithmeticError, KeyError, IndexError) as exc:
        raise ExpressionError("evaluation", str(exc), compiled.source) from exc
    if isinstance(result, CELEvalError):
        raise ExpressionError("evaluation", _eval_message(result), compiled.source)
    return to_native(result)


def evaluate_bool(expr: CompiledExpression | str, context: Mapping[str, Any]) -> bool:
    """For `condition`, `switch` cases and trigger `filter`: must return a bool."""
    value = evaluate(expr, context)
    if not isinstance(value, bool):
        source = expr if isinstance(expr, str) else expr.source
        raise ExpressionError("evaluation", f"expected bool, got {type(value).__name__}", source)
    return value


def _eval_message(exc: CELEvalError) -> str:
    args = exc.args
    return str(args[0]) if args else "evaluation failed"


def _to_cel(value: Any) -> Any:
    """Context → CEL values. Datetimes become timestamps so `execution.now + duration('48h')`
    works; everything else goes through CEL's JSON bridge."""
    if isinstance(value, dt.datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=dt.UTC)
        return celtypes.TimestampType(value.astimezone(dt.UTC))
    if isinstance(value, Mapping):
        return celtypes.MapType({celtypes.StringType(str(k)): _to_cel(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return celtypes.ListType([_to_cel(v) for v in value])
    return json_to_cel(value)


def to_native(value: Any) -> Any:
    """CEL values → plain Python (JSON-compatible; timestamps/durations as ISO strings)."""
    if isinstance(value, celtypes.BoolType):
        return bool(value)
    if isinstance(value, celtypes.TimestampType):
        return value.isoformat()
    if isinstance(value, celtypes.DurationType):
        return _iso_duration(value)
    if isinstance(value, (celtypes.IntType, celtypes.UintType)):
        return int(value)
    if isinstance(value, celtypes.DoubleType):
        return float(value)
    if isinstance(value, celtypes.StringType):
        return str(value)
    if isinstance(value, celtypes.BytesType):
        return bytes(value)
    if isinstance(value, celtypes.MapType):
        return {str(to_native(k)): to_native(v) for k, v in value.items()}
    if isinstance(value, celtypes.ListType):
        return [to_native(v) for v in value]
    if value is None:
        return None
    return value


def _iso_duration(value: dt.timedelta) -> str:
    seconds = value.total_seconds()
    sign = "-" if seconds < 0 else ""
    seconds = abs(seconds)
    days, rest = divmod(seconds, 86_400)
    text = f"{sign}P{int(days)}D" if days else f"{sign}P"
    if rest or not days:
        whole = int(rest) if float(rest).is_integer() else rest
        text += f"T{whole}S"
    return text


def _to_text(value: Any) -> str:
    native = to_native(value)
    if isinstance(native, bool):
        return "true" if native else "false"
    if native is None:
        return ""
    if isinstance(native, (dict, list)):
        import json

        return json.dumps(native, ensure_ascii=False, separators=(",", ":"))
    return str(native)


# ── Templates ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class CompiledTemplate:
    source: str
    parts: tuple[str | CompiledExpression, ...]

    @property
    def is_single_placeholder(self) -> bool:
        return len(self.parts) == 1 and isinstance(self.parts[0], CompiledExpression)

    @property
    def expressions(self) -> tuple[CompiledExpression, ...]:
        return tuple(p for p in self.parts if isinstance(p, CompiledExpression))


def has_placeholders(text: str) -> bool:
    return bool(_PLACEHOLDER.search(text))


def compile_template(text: str, *, scopes: frozenset[str] = SCOPES) -> CompiledTemplate:
    parts: list[str | CompiledExpression] = []
    pos = 0
    for match in _PLACEHOLDER.finditer(text):
        if match.start() > pos:
            parts.append(text[pos : match.start()])
        parts.append(compile_expression(match.group(1), scopes=scopes))
        pos = match.end()
    if pos < len(text):
        parts.append(text[pos:])
    stray = [p for p in parts if isinstance(p, str) and ("{{" in p or "}}" in p)]
    if stray:
        raise ExpressionError("syntax", "unbalanced '{{' / '}}' in template", text)
    return CompiledTemplate(text, tuple(parts))


def render_template(template: CompiledTemplate | str, context: Mapping[str, Any]) -> Any:
    """Single placeholder → typed value; otherwise concatenated text (≤ 64 KB)."""
    compiled = compile_template(template) if isinstance(template, str) else template
    if compiled.is_single_placeholder:
        return evaluate(compiled.parts[0], context)  # type: ignore[arg-type]
    out = "".join(
        part if isinstance(part, str) else _to_text(evaluate(part, context))
        for part in compiled.parts
    )
    if len(out.encode()) > MAX_RENDERED_BYTES:
        raise ExpressionError("output", "rendered template exceeds 64 KB", compiled.source)
    return out


def render_value(value: Any, context: Mapping[str, Any]) -> Any:
    """Render every template string inside a config value (dicts, lists, scalars)."""
    if isinstance(value, str):
        return render_template(value, context) if has_placeholders(value) else value
    if isinstance(value, Mapping):
        return {k: render_value(v, context) for k, v in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return [render_value(v, context) for v in value]
    return value

"""Emit TypeScript types for the flow schema (stdout).

Input is the codegen copy produced by codegen_schema.py. Covers the JSON Schema
subset the flow schema uses: $ref, allOf (base + variant), oneOf/anyOf, const,
enum, type (incl. arrays of types), properties/required, additionalProperties,
items. Constraints (patterns, lengths) are left to runtime validation.
"""

import json
import re
import sys
from pathlib import Path

HEADER = """// Generated from packages/flow-schema/flow.schema.json by scripts/gen.sh. Do not edit.
"""

PRIMITIVES = {
    "string": "string",
    "integer": "number",
    "number": "number",
    "boolean": "boolean",
    "null": "null",
}


def pascal(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[_\-\s]+", name) if p)


def ident(key: str) -> str:
    return key if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", key) else json.dumps(key)


class Emitter:
    def __init__(self, schema: dict) -> None:
        self.defs: dict = schema["$defs"]
        self.names = {key: self.def_name(key, sub) for key, sub in self.defs.items()}

    @staticmethod
    def def_name(key: str, sub: dict) -> str:
        title = sub.get("title") if isinstance(sub, dict) else None
        return title or pascal(key)

    def ref(self, ref: str) -> str:
        return self.names[ref.removeprefix("#/$defs/")]

    def type_of(self, s: object, indent: str = "") -> str:
        if s is True or s == {}:
            return "unknown"
        if not isinstance(s, dict):
            return "unknown"
        if "$ref" in s:
            return self.ref(s["$ref"])
        if "const" in s:
            return json.dumps(s["const"])
        if "enum" in s:
            return " | ".join(json.dumps(v) for v in s["enum"])
        for key in ("oneOf", "anyOf"):
            if key in s:
                return " | ".join(self.type_of(v, indent) for v in s[key])
        if "allOf" in s:
            # if/then branches (conditional requirements) carry no type of their own.
            parts = [t for v in s["allOf"] if (t := self.type_of(v, indent)) != "unknown"]
            own = {k: v for k, v in s.items() if k != "allOf"}
            if own.get("properties"):
                parts.append(self.object_type(own, indent))
            return " & ".join(parts) or "unknown"
        t = s.get("type")
        if isinstance(t, list):
            return " | ".join(self.type_of({**s, "type": x}, indent) for x in t)
        if t == "array":
            inner = self.type_of(s.get("items", {}), indent)
            return f"Array<{inner}>"
        if t == "object" or "properties" in s:
            return self.object_type(s, indent)
        return PRIMITIVES.get(t, "unknown") if isinstance(t, str) else "unknown"

    def object_type(self, s: dict, indent: str) -> str:
        props: dict = s.get("properties", {})
        extra = s.get("additionalProperties")
        if not props:
            if isinstance(extra, dict):
                return f"Record<string, {self.type_of(extra, indent)}>"
            return "Record<string, unknown>"
        required = set(s.get("required", []))
        inner = indent + "  "
        lines = ["{"]
        for key, sub in props.items():
            doc = sub.get("description") if isinstance(sub, dict) else None
            if doc:
                lines.append(f"{inner}/** {doc.replace('*/', '* /')} */")
            # A const property is a union discriminator: always present.
            is_tag = isinstance(sub, dict) and "const" in sub
            opt = "" if key in required or is_tag else "?"
            lines.append(f"{inner}{ident(key)}{opt}: {self.type_of(sub, inner)};")
        if isinstance(extra, dict):
            lines.append(f"{inner}[key: string]: unknown;")
        lines.append(indent + "}")
        return "\n".join(lines)

    def emit(self, root: dict) -> str:
        out = [HEADER]
        for key, sub in self.defs.items():
            name = self.names[key]
            if isinstance(sub, dict) and sub.get("description"):
                out.append(f"/** {sub['description'].replace('*/', '* /')} */")
            out.append(f"export type {name} = {self.type_of(sub)};\n")
        root_body = {k: v for k, v in root.items() if k != "$defs"}
        if root.get("description"):
            out.append(f"/** {root['description']} */")
        out.append(f"export type FlowDefinition = {self.type_of(root_body)};\n")
        out.append("export type FlowNode = Node;")
        out.append('export type FlowNodeType = FlowNode["type"];')
        out.append("export type FlowTrigger = Trigger;\n")
        return "\n".join(out)


def main(path: str) -> None:
    schema = json.loads(Path(path).read_text())
    sys.stdout.write(Emitter(schema).emit(schema))


if __name__ == "__main__":
    main(sys.argv[1])

"""Rewrite flow.schema.json into a codegen-friendly copy (stdout).

The published schema stays the source of truth for validation. This copy only
changes what affects generated class names and union shape:
- `node` / `trigger` become plain `oneOf` + `discriminator` on `type`, so the
  generators emit tagged unions instead of numbered wrapper classes;
- `format: email` is dropped (plain strings; no email-validator dependency);
- every node `config` object gets a title (`AgentConfig`, ...), every nested
  anonymous object a title derived from its parent, so names are stable;
- `jsonSchemaObject` (an embedded JSON Schema) keeps its other keywords
  (`properties`, `required`, ...): the generated model allows extra fields instead of
  silently dropping them.
"""

import json
import re
import sys
from pathlib import Path


def pascal(name: str) -> str:
    return "".join(p[:1].upper() + p[1:] for p in re.split(r"[_\-\s]+", name) if p)


def title_objects(node: object, prefix: str) -> None:
    """Give a title to anonymous object schemas nested under `prefix`."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict):
            for key, sub in props.items():
                if isinstance(sub, dict):
                    name = prefix + pascal(key)
                    if sub.get("type") == "object" and "title" not in sub and "$ref" not in sub:
                        sub["title"] = name
                    title_objects(sub, name)
        items = node.get("items")
        if isinstance(items, dict):
            name = prefix + "Item"
            if items.get("type") == "object" and "title" not in items:
                items["title"] = name
            title_objects(items, name)


def drop_email_format(node: object) -> None:
    """Keep emails as plain strings so generated models don't need email-validator."""
    if isinstance(node, dict):
        if node.get("format") == "email":
            del node["format"]
        for value in node.values():
            drop_email_format(value)
    elif isinstance(node, list):
        for value in node:
            drop_email_format(value)


def inline_version_unions(node: object) -> None:
    """`version: oneOf[const "published", integer]` → inline anyOf, so the generator doesn't
    push the "published" default into a separate integer root model."""
    if isinstance(node, dict):
        props = node.get("properties")
        if isinstance(props, dict) and isinstance(props.get("version"), dict):
            version = props["version"]
            if "oneOf" in version:
                version["anyOf"] = version.pop("oneOf")
                for branch in version["anyOf"]:
                    if branch.get("type") == "integer":
                        branch["title"] = "VersionNumber"
        for value in node.values():
            inline_version_unions(value)
    elif isinstance(node, list):
        for value in node:
            inline_version_unions(value)


def main(path: str) -> None:
    schema = json.loads(Path(path).read_text())
    drop_email_format(schema)
    inline_version_unions(schema)
    defs = schema["$defs"]
    defs["jsonSchemaObject"]["additionalProperties"] = True
    for union, prefix in (("node", "node"), ("trigger", "trigger")):
        variants = [k for k in defs if k.startswith(prefix) and k not in (union, f"{union}Base")]
        defs[union] = {
            "oneOf": [{"$ref": f"#/$defs/{k}"} for k in variants],
            "discriminator": {"propertyName": "type"},
        }
    for key, sub in defs.items():
        if key.startswith("node") and key not in ("node", "nodeBase"):
            name = pascal(key.removeprefix("node"))
            config = sub.get("properties", {}).get("config")
            if isinstance(config, dict):
                config["title"] = f"{name}Config"
                title_objects(config, name)
            sub["title"] = f"{name}Node"
        elif key.startswith("trigger") and key != "trigger":
            name = pascal(key.removeprefix("trigger"))
            sub["title"] = f"{name}Trigger"
            title_objects(sub, f"{name}Trigger")
        elif isinstance(sub, dict) and sub.get("type") == "object":
            sub.setdefault("title", pascal(key))
            title_objects(sub, pascal(key))
    schema["title"] = "FlowDefinition"
    json.dump(schema, sys.stdout, indent=2)


if __name__ == "__main__":
    main(sys.argv[1])

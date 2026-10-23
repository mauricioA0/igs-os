"""Versioned entry-requirement rules (``rules/<YYYY-MM>.yaml``), validated on load.

The rules are data, not code: ops (or whoever re-checks the official sources each quarter) edits
or adds a YAML file; ``load_rules()`` returns the latest version. Research and citations live in
docs/ops/requisitos-viaje.md.
"""

from __future__ import annotations

from datetime import date
from functools import cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

RULES_DIR = Path(__file__).parent / "rules"

Severity = Literal["blocker", "required", "recommended"]
SEVERITY_RANK: dict[str, int] = {"recommended": 0, "required": 1, "blocker": 2}


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Source(_Model):
    title: str
    url: str
    official: bool


class RequirementDef(_Model):
    label: str
    kind: Literal["passport", "document"]
    due_days_before: int = Field(ge=0, le=365)
    hint: str | None = None


class When(_Model):
    minor: bool | None = None
    max_age: int | None = Field(default=None, ge=0, le=17)


class PassportRule(_Model):
    valid_through: Literal["trip_end"] = "trip_end"
    months_after: int = Field(default=0, ge=0, le=12)
    max_issued_years: int | None = Field(default=None, ge=1, le=20)
    blank_pages: int | None = Field(default=None, ge=0, le=10)
    recommended_months_after_return: int | None = Field(default=None, ge=0, le=12)


class RequirementRule(_Model):
    key: str
    severity: Severity
    sources: tuple[str, ...] = ()
    when: When = When()
    note: str | None = None
    # Known but not in force yet (ETIAS): null, or a date after the trip, keeps it inactive.
    effective_from: date | None = Field(default=None)
    # Distinguishes "no key" (always in force) from an explicit `effective_from: null`.
    pending: bool = False

    @model_validator(mode="before")
    @classmethod
    def _pending(cls, data: object) -> object:
        if isinstance(data, dict) and "effective_from" in data and data["effective_from"] is None:
            return {**data, "pending": True}
        return data

    def in_force(self, on: date) -> bool:
        if self.pending:
            return False
        return self.effective_from is None or self.effective_from <= on


class Destination(_Model):
    code: str = Field(pattern=r"^[A-Z]{2}$")
    names: tuple[str, ...]
    passport: PassportRule | None = None
    requirements: tuple[RequirementRule, ...] = ()


class Defaults(_Model):
    requirements: tuple[RequirementRule, ...] = ()
    passport: PassportRule = PassportRule()


class RuleSet(_Model):
    version: str
    checked_on: date
    nationality: str
    sources: dict[str, Source]
    requirements: dict[str, RequirementDef]
    defaults: Defaults = Defaults()
    destinations: tuple[Destination, ...]

    @model_validator(mode="after")
    def _references(self) -> RuleSet:
        rules = [*self.defaults.requirements]
        for d in self.destinations:
            rules.extend(d.requirements)
        for r in rules:
            if r.key not in self.requirements:
                raise ValueError(f"unknown requirement {r.key!r}")
            missing = [s for s in r.sources if s not in self.sources]
            if missing:
                raise ValueError(f"{r.key}: unknown source(s) {missing}")
        return self

    def destination(self, country: str) -> Destination | None:
        needle = country.strip().casefold()
        for d in self.destinations:
            if needle == d.code.casefold() or needle in (n.casefold() for n in d.names):
                return d
        return None

    def rules_for(self, destination: Destination | None) -> list[RequirementRule]:
        """Defaults overlaid by the destination: a destination rule replaces the default with the
        same key and the same `when`; otherwise both apply (e.g. a stricter rule for under-13s)."""
        merged: dict[tuple[str, When], RequirementRule] = {
            (r.key, r.when): r for r in self.defaults.requirements
        }
        for r in destination.requirements if destination else ():
            merged[(r.key, r.when)] = r
        return list(merged.values())

    def passport_rule(self, destination: Destination | None) -> PassportRule:
        base = self.defaults.passport
        if destination is None or destination.passport is None:
            return base
        own = destination.passport
        return own.model_copy(
            update={
                "recommended_months_after_return": own.recommended_months_after_return
                if own.recommended_months_after_return is not None
                else base.recommended_months_after_return
            }
        )


def parse_rules(text: str) -> RuleSet:
    return RuleSet.model_validate(yaml.safe_load(text))


@cache
def load_rules(version: str | None = None) -> RuleSet:
    """The given version (file stem), or the latest one in ``rules/``."""
    files = sorted(RULES_DIR.glob("*.yaml"))
    if not files:
        raise FileNotFoundError(f"no rule files in {RULES_DIR}")
    path = RULES_DIR / f"{version}.yaml" if version else files[-1]
    return parse_rules(path.read_text(encoding="utf-8"))

"""Morning ops digest: deterministic facts, a model-phrased opening checked number by number."""

from .build import OPS_TZ, add_business_days, build_digest, business_days_between
from .numbers import NumberCheck, allowed_numbers, check_numbers
from .phrase import Phrased, phrase_summary, template_summary
from .render import render_html, render_json, render_text
from .service import Digest, generate_digest
from .types import (
    ApprovalInput,
    DigestFacts,
    DigestInputs,
    DigestRules,
    IncidentInput,
    LeadInput,
    TripInput,
)

__all__ = [
    "OPS_TZ",
    "ApprovalInput",
    "Digest",
    "DigestFacts",
    "DigestInputs",
    "DigestRules",
    "IncidentInput",
    "LeadInput",
    "NumberCheck",
    "Phrased",
    "TripInput",
    "add_business_days",
    "allowed_numbers",
    "build_digest",
    "business_days_between",
    "check_numbers",
    "generate_digest",
    "phrase_summary",
    "render_html",
    "render_json",
    "render_text",
    "template_summary",
]

"""Account 360 intelligence: verified fact extraction, deterministic health, cited briefs, Q&A.

See docs/design/account-360.md. Structured state comes from SQL; narrative from interactions.
"""

from .ask import Answer, Passage, PassageRetriever, RagRetriever, ask, detect_language
from .brief import Brief, cached_brief, generate_brief, inputs_hash, store_brief
from .extraction import (
    AcceptedFact,
    ExtractionResult,
    InteractionInput,
    Rejection,
    StakeholderSuggestion,
    apply_extraction,
    extract,
    verify_evidence,
)
from .health import HealthRules, compute_health
from .service import AccountIntelligence
from .snapshot import load_snapshot
from .types import AccountNotFoundError, AccountSnapshot, Citation, HealthResult

__all__ = [
    "AcceptedFact",
    "AccountIntelligence",
    "AccountNotFoundError",
    "AccountSnapshot",
    "Answer",
    "Brief",
    "Citation",
    "ExtractionResult",
    "HealthResult",
    "HealthRules",
    "InteractionInput",
    "Passage",
    "PassageRetriever",
    "RagRetriever",
    "Rejection",
    "StakeholderSuggestion",
    "apply_extraction",
    "ask",
    "cached_brief",
    "compute_health",
    "detect_language",
    "extract",
    "generate_brief",
    "inputs_hash",
    "load_snapshot",
    "store_brief",
    "verify_evidence",
]

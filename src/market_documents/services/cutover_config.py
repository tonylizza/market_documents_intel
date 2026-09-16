"""Track 7C.6 scoped production-cutover configuration
(docs/7c6-production-cutover.md).

The exact, explicit scope for which a longitudinal-comparison request may
be served by the new semantic-unit/structured-table pipeline instead of the
legacy passage-alignment pipeline -- fixed to precisely what 7C.5's
shadow-evaluation verdict validated as ready: BEL's `gross_margin` and
ACT's `cfo_conclusion` narrative units, plus ACT's two remuneration
structured-table families. Mirrors `semantic_unit_config.py`/
`structured_table_config.py`'s shape: a small frozen registry, never a
dynamic "does a row exist" check (docs/7c6-...md Section 3: "do NOT infer
support dynamically from whether rows happen to exist in the database").

Expanding this scope is explicitly out of 7C.6's own stated scope -- see
the milestone's hard-stop instructions.
"""

import hashlib
import json

from market_documents.models.enums import NormalizedSchedule

# v1.0.0 = initial scoped cutover: BEL gross_margin, ACT cfo_conclusion
# (both FINANCIAL_PERFORMANCE), ACT's two REMUNERATION table families.
CONFIG_VERSION = "1.0.0"

NEW_PIPELINE_NARRATIVE_SCOPE: frozenset[tuple[str, NormalizedSchedule, str]] = frozenset(
    {
        ("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE, "gross_margin"),
        ("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "cfo_conclusion"),
    }
)

NEW_PIPELINE_STRUCTURED_SCOPE: frozenset[tuple[str, str]] = frozenset(
    {
        ("ACT", "ned_remuneration_policy_table"),
        ("ACT", "total_remuneration_outcomes"),
    }
)


def is_narrative_unit_in_scope(ticker: str, schedule: NormalizedSchedule, unit_key: str) -> bool:
    return (ticker.upper(), schedule, unit_key) in NEW_PIPELINE_NARRATIVE_SCOPE


def is_structured_table_in_scope(ticker: str, table_family_key: str) -> bool:
    return (ticker.upper(), table_family_key) in NEW_PIPELINE_STRUCTURED_SCOPE


def compute_configuration_hash() -> str:
    """Deterministic fingerprint of the cutover-scope configuration in
    effect, so widening/narrowing scope is always an explicit, auditable
    change -- never silently inferred."""
    payload = {
        "config_version": CONFIG_VERSION,
        "narrative_scope": sorted(f"{t}:{s.value}:{u}" for t, s, u in NEW_PIPELINE_NARRATIVE_SCOPE),
        "structured_scope": sorted(f"{t}:{k}" for t, k in NEW_PIPELINE_STRUCTURED_SCOPE),
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

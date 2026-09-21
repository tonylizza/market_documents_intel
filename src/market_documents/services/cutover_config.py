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
the milestone's hard-stop instructions. Track 7D.2c is the first deliberate
promotion beyond that original scope: ACT's `healthcare_services_review`
(docs/7d2c-healthcare-services-review-production-promotion.md), validated
as a production candidate by Track 7D.2/7D.2a/7D.2b.

Track 7E.2a (docs/7e2a-production-scope-finalization.md) is the second
deliberate promotion: a conservative, evidence-based re-evaluation of every
`UNIT_CONFIGS`/`TABLE_FAMILY_CONFIGS` entry against the latest hardening
results (Track 7D.4a's start-heading false-positive fix in particular),
adding eight CORPORATE_GOVERNANCE/REMUNERATION narrative units that meet
either the ENABLE_NOW or ENABLE_WITH_KNOWN_CAVEAT bar. See
docs/7e2a-production-scope-finalization.md Section 6/13 for the full
release-scope matrix and the rationale for every unit left out
(BEL `board_composition_diversity`, BEL `variable_remuneration`, SUR
`remuneration_policy_shareholder_engagement` -- all KEEP_SHADOW_ONLY).
"""

import hashlib
import json

from market_documents.models.enums import NormalizedSchedule

# v1.1.0 = 7D.2c promotion: added ACT healthcare_services_review
# (FINANCIAL_PERFORMANCE) on top of the v1.0.0 scope (BEL gross_margin,
# ACT cfo_conclusion, ACT's two REMUNERATION table families).
# v1.2.0 = Track 7E.2a production-scope finalization
# (docs/7e2a-production-scope-finalization.md): added eight
# CORPORATE_GOVERNANCE/REMUNERATION narrative units re-evaluated against
# the latest evidence (in particular Track 7D.4a's fix, which moved
# `combined_assurance` and `remuneration_governance` from NOT_READY to
# READY_WITH_CAVEAT). No structured-table scope change. Three researched
# candidates were deliberately left out as KEEP_SHADOW_ONLY: BEL
# `board_composition_diversity` (STRUCTURED_COMPARISON_PREFERRED with no
# comparison engine implemented), BEL `variable_remuneration` (0/6 pairs
# ever resolve), SUR `remuneration_policy_shareholder_engagement` (0/3
# years ever resolve -- the heading sits outside the schedule's own
# localized end boundary every year).
CONFIG_VERSION = "1.2.0"

NEW_PIPELINE_NARRATIVE_SCOPE: frozenset[tuple[str, NormalizedSchedule, str]] = frozenset(
    {
        # v1.0.0 / v1.1.0 scope -- unchanged.
        ("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE, "gross_margin"),
        ("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "cfo_conclusion"),
        ("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review"),
        # v1.2.0 (7E.2a) -- ENABLE_NOW: no known defect, reliable
        # localization/boundary/alignment across the large majority of
        # resolved years.
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "information_security_governance"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remuneration_policy_changes"),
        # v1.2.0 (7E.2a) -- ENABLE_WITH_KNOWN_CAVEAT: correct wherever
        # resolved, with one bounded, documented, non-fatal limitation.
        # See docs/7e2a-production-scope-finalization.md Section 6/13 for
        # the exact caveat text per unit.
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "governance_policies_processes"),
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "combined_assurance"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remco_chairperson_report"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remuneration_governance"),
        ("SUR", NormalizedSchedule.REMUNERATION, "remuneration_policy_changes_and_focus"),
        ("SUR", NormalizedSchedule.REMUNERATION, "fair_responsible_remuneration"),
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

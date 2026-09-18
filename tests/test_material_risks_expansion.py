"""Track 7D.5 (docs/7d5-corpus-wide-material-risks-expansion.md): corpus-wide
MATERIAL_RISKS evaluation. Real-corpus inspection found MATERIAL_RISKS
content is structurally different from every narrative schedule implemented
so far (FINANCIAL_PERFORMANCE, CORPORATE_GOVERNANCE, REMUNERATION) -- a
materiality-matrix/risk-card layout (ACT), a risk register whose named
topics reorganize year to year (BEL), or a pure risk-landscape infographic
with no extractable narrative text (SUR) -- so this milestone configured
*zero* `UnitConfig`/`UNIT_ANALYTICAL_MODES` entries for MATERIAL_RISKS,
deliberately, per the milestone's own "it is acceptable for an issuer to
have zero selected units" instruction. These tests document and guard that
decision, not a mistake to be silently "fixed" by a future track without
re-doing the real-corpus structural inventory.
"""

from market_documents.models.enums import NormalizedSchedule
from market_documents.services import coverage_registry
from market_documents.services.analytical_eligibility import UNIT_ANALYTICAL_MODES
from market_documents.services.cutover_config import NEW_PIPELINE_NARRATIVE_SCOPE
from market_documents.services.schedule_config import SCHEDULE_CONFIG
from market_documents.services.semantic_unit_config import UNIT_CONFIGS


def test_material_risks_has_no_configured_narrative_units():
    """Deliberate, documented outcome (Section 8/21 of the milestone doc) --
    not an oversight. A future track that adds a real MATERIAL_RISKS unit
    should update this test alongside the new UnitConfig, not delete it
    blindly."""
    assert not [c for c in UNIT_CONFIGS if c.schedule == NormalizedSchedule.MATERIAL_RISKS]


def test_material_risks_has_no_analytical_routing_entries():
    # UNIT_ANALYTICAL_MODES keys are (ticker, unit_key) with no unit_key
    # belonging to MATERIAL_RISKS, since no MATERIAL_RISKS UnitConfig exists.
    material_risks_unit_keys = {c.unit_key for c in UNIT_CONFIGS if c.schedule == NormalizedSchedule.MATERIAL_RISKS}
    assert not material_risks_unit_keys
    assert not any(unit_key in material_risks_unit_keys for _, unit_key in UNIT_ANALYTICAL_MODES)


def test_material_risks_has_no_coverage_registry_entries():
    assert not [e for e in coverage_registry.COVERAGE_REGISTRY if e.schedule == NormalizedSchedule.MATERIAL_RISKS]


def test_material_risks_not_in_cutover_scope():
    assert not [
        entry for entry in NEW_PIPELINE_NARRATIVE_SCOPE if entry[1] == NormalizedSchedule.MATERIAL_RISKS
    ]


def test_material_risks_vocabulary_excludes_risk_governance_phrases():
    """Section 2 of the milestone doc: MATERIAL_RISKS must never be
    conflated with risk-governance/oversight content (Audit and Risk
    Committee, Enterprise Risk Management, combined assurance, three lines
    of defence). Confirmed absent from the configured vocabulary as a
    standalone phrase -- a regression guard against a future track
    accidentally widening the vocabulary with one of these. Deliberately
    does NOT forbid the bare substring "risk management": BEL's own
    genuine, real-corpus-confirmed chapter title, "Strategic overview and
    risk management", legitimately contains it as part of a WHAT-are-the-
    risks chapter name, not a HOW-is-risk-governed heading."""
    vocabulary = SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.MATERIAL_RISKS]
    normalized = {v.lower() for v in vocabulary}
    forbidden_standalone_phrases = (
        "audit and risk committee",
        "enterprise risk management",
        "risk management",
        "combined assurance",
        "three lines of defence",
    )
    for phrase in normalized:
        assert phrase not in forbidden_standalone_phrases, f"{phrase!r} is a risk-governance phrase, not a Material Risks chapter title"


def test_material_risks_vocabulary_excludes_generic_navigational_label():
    """Real-corpus defect (see docs/7d5-...md Section 19 / schedule_config.py
    comment): the bare phrase "Risks and opportunities" matches a
    value-creation-model navigational cross-reference label on ACT's
    overview page, not the real risk chapter, in years lacking a more
    specific chapter title. Deliberately excluded from the vocabulary."""
    vocabulary = SCHEDULE_CONFIG.heading_vocabulary[NormalizedSchedule.MATERIAL_RISKS]
    normalized = {v.strip().lower() for v in vocabulary}
    assert "risks and opportunities" not in normalized

"""Tests for `services.coverage_registry` (Track 7D.2): the registry is
derived entirely from `semantic_unit_config`, `analytical_eligibility`, and
`cutover_config` -- never a second, independently-maintained source of
truth for any of them.
"""

from market_documents.models.enums import AnalyticalMode, NormalizedSchedule
from market_documents.services import coverage_registry


def test_every_configured_unit_has_a_registry_entry():
    from market_documents.services.semantic_unit_config import UNIT_CONFIGS

    for config in UNIT_CONFIGS:
        entry = coverage_registry.coverage_for(config.ticker, config.schedule, config.unit_key)
        assert entry is not None
        assert entry.extraction_supported is True
        assert entry.alignment_supported is True


def test_promoted_7d2c_unit_is_lexical_only_and_enabled_in_production():
    entry = coverage_registry.coverage_for("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review")

    assert entry is not None
    assert entry.analytical_mode == AnalyticalMode.LEXICAL_ONLY
    assert entry.production_status == "enabled"


def test_unconfigured_unit_has_no_registry_entry_and_is_not_promoted():
    # Not a HEADED_NARRATIVE_UNIT extraction config at all -- must not be
    # confused with an in-scope-but-not-enabled "candidate".
    assert coverage_registry.coverage_for("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "capital_management") is None


def test_existing_cutover_units_are_enabled_in_the_registry():
    entry = coverage_registry.coverage_for("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE, "gross_margin")

    assert entry is not None
    assert entry.production_status == "enabled"


def test_unconfigured_unit_returns_none():
    assert coverage_registry.coverage_for("XYZ", NormalizedSchedule.FINANCIAL_PERFORMANCE, "nonexistent") is None


def test_configuration_hash_is_deterministic():
    assert coverage_registry.compute_configuration_hash() == coverage_registry.compute_configuration_hash()


# --------------------------------------------------------------------------
# Track 7D.3 / 7E.2a: CORPORATE_GOVERNANCE units
# --------------------------------------------------------------------------


def test_promoted_governance_units_are_enabled_in_production():
    """7E.2a promoted these CORPORATE_GOVERNANCE units to production scope
    (docs/7e2a-production-scope-finalization.md Section 6/13) --
    `information_security_governance` as ENABLE_NOW; `governance_policies_
    processes` and `combined_assurance` as ENABLE_WITH_KNOWN_CAVEAT
    (`combined_assurance` after its 7D.4a defect fix)."""
    for ticker, unit_key in (
        ("ACT", "information_security_governance"),
        ("ACT", "governance_policies_processes"),
        ("ACT", "combined_assurance"),
    ):
        entry = coverage_registry.coverage_for(ticker, NormalizedSchedule.CORPORATE_GOVERNANCE, unit_key)
        assert entry is not None
        assert entry.production_status == "enabled"


def test_bel_board_composition_diversity_remains_shadow_only():
    """KEEP_SHADOW_ONLY (7E.2a): STRUCTURED_COMPARISON_PREFERRED with no
    comparison engine implemented -- never enabled in production."""
    entry = coverage_registry.coverage_for("BEL", NormalizedSchedule.CORPORATE_GOVERNANCE, "board_composition_diversity")

    assert entry is not None
    assert entry.production_status == "candidate"
    assert entry.analytical_mode == AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED


# --------------------------------------------------------------------------
# Track 7D.4 / 7E.2a: REMUNERATION units
# --------------------------------------------------------------------------


def test_promoted_remuneration_units_are_enabled_in_production():
    """7E.2a promoted these REMUNERATION units to production scope
    (docs/7e2a-production-scope-finalization.md Section 6/13)."""
    for ticker, unit_key in (
        ("ACT", "remco_chairperson_report"),
        ("ACT", "remuneration_policy_changes"),
        ("ACT", "remuneration_governance"),
        ("SUR", "remuneration_policy_changes_and_focus"),
        ("SUR", "fair_responsible_remuneration"),
    ):
        entry = coverage_registry.coverage_for(ticker, NormalizedSchedule.REMUNERATION, unit_key)
        assert entry is not None
        assert entry.production_status == "enabled"
        assert entry.analytical_mode == AnalyticalMode.LEXICAL_ONLY


def test_shadow_only_remuneration_units_remain_candidates():
    """KEEP_SHADOW_ONLY (7E.2a): BEL `variable_remuneration` (0/6 pairs
    ever resolve) and SUR `remuneration_policy_shareholder_engagement`
    (0/3 years ever resolve) -- neither is promoted."""
    for ticker, unit_key in (
        ("BEL", "variable_remuneration"),
        ("SUR", "remuneration_policy_shareholder_engagement"),
    ):
        entry = coverage_registry.coverage_for(ticker, NormalizedSchedule.REMUNERATION, unit_key)
        assert entry is not None
        assert entry.production_status == "candidate"
        assert entry.analytical_mode == AnalyticalMode.LEXICAL_ONLY


def test_existing_structured_remuneration_scope_unaffected_by_narrative_units():
    """Track 7C.4's ACT structured remuneration table families remain
    exactly as already configured -- 7D.4 adds narrative units only, no
    structured-table config changed."""
    from market_documents.services.cutover_config import NEW_PIPELINE_STRUCTURED_SCOPE

    assert ("ACT", "ned_remuneration_policy_table") in NEW_PIPELINE_STRUCTURED_SCOPE
    assert ("ACT", "total_remuneration_outcomes") in NEW_PIPELINE_STRUCTURED_SCOPE

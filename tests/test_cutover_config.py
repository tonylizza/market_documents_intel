"""Tests for `services.cutover_config` (Track 7E.2a production-scope
finalization, docs/7e2a-production-scope-finalization.md): the exact,
explicit narrative/structured scope enabled through the new comparison
path in production.
"""

from market_documents.models.enums import NormalizedSchedule
from market_documents.services import cutover_config


def test_exact_narrative_production_scope():
    """The 7E.2a release-scope matrix (Section 13): 11 narrative units,
    no more, no less."""
    expected = {
        ("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE, "gross_margin"),
        ("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "cfo_conclusion"),
        ("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review"),
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "information_security_governance"),
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "governance_policies_processes"),
        ("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE, "combined_assurance"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remco_chairperson_report"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remuneration_policy_changes"),
        ("ACT", NormalizedSchedule.REMUNERATION, "remuneration_governance"),
        ("SUR", NormalizedSchedule.REMUNERATION, "remuneration_policy_changes_and_focus"),
        ("SUR", NormalizedSchedule.REMUNERATION, "fair_responsible_remuneration"),
    }
    assert cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE == expected


def test_exact_structured_production_scope_unchanged():
    """7E.2a made no structured-table scope change -- both ACT families
    already in scope since Track 7C.6 remain exactly as configured."""
    assert cutover_config.NEW_PIPELINE_STRUCTURED_SCOPE == {
        ("ACT", "ned_remuneration_policy_table"),
        ("ACT", "total_remuneration_outcomes"),
    }


def test_shadow_only_units_remain_out_of_scope():
    """KEEP_SHADOW_ONLY candidates (docs/7e2a-production-scope-finalization.md
    Section 6): researched, configured, but not production-ready."""
    shadow_only = (
        ("BEL", NormalizedSchedule.CORPORATE_GOVERNANCE, "board_composition_diversity"),
        ("BEL", NormalizedSchedule.REMUNERATION, "variable_remuneration"),
        ("SUR", NormalizedSchedule.REMUNERATION, "remuneration_policy_shareholder_engagement"),
    )
    for entry in shadow_only:
        assert entry not in cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE


def test_is_narrative_unit_in_scope_matches_frozenset():
    assert cutover_config.is_narrative_unit_in_scope(
        "act", NormalizedSchedule.CORPORATE_GOVERNANCE, "combined_assurance"
    )
    assert not cutover_config.is_narrative_unit_in_scope(
        "BEL", NormalizedSchedule.CORPORATE_GOVERNANCE, "board_composition_diversity"
    )


def test_config_version_bumped_for_7e2a():
    assert cutover_config.CONFIG_VERSION == "1.2.0"


def test_configuration_hash_is_deterministic():
    assert cutover_config.compute_configuration_hash() == cutover_config.compute_configuration_hash()

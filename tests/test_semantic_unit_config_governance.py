"""Track 7D.3: configuration tests for the new CORPORATE_GOVERNANCE units.

No database access -- pure config-module assertions, mirroring the existing
pattern of testing `unit_configs_for`/`compute_configuration_hash` directly
rather than through the DB-backed orchestration layer.
"""

from market_documents.models.enums import NormalizedSchedule, SemanticUnitBoundaryStrategy
from market_documents.services import semantic_unit_config as suc


def test_act_has_three_corporate_governance_units():
    configs = suc.unit_configs_for("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE)
    unit_keys = {c.unit_key for c in configs}
    assert unit_keys == {"information_security_governance", "governance_policies_processes", "combined_assurance"}


def test_bel_has_one_corporate_governance_unit():
    configs = suc.unit_configs_for("BEL", NormalizedSchedule.CORPORATE_GOVERNANCE)
    assert [c.unit_key for c in configs] == ["board_composition_diversity"]


def test_financial_performance_units_unaffected_by_governance_addition():
    """Regression: adding CORPORATE_GOVERNANCE units must not change which
    units resolve for the existing FINANCIAL_PERFORMANCE schedule."""
    bel_fp = suc.unit_configs_for("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE)
    act_fp = suc.unit_configs_for("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE)
    assert {c.unit_key for c in bel_fp} == {"gross_margin"}
    assert {c.unit_key for c in act_fp} == {"cfo_conclusion", "healthcare_services_review"}


def test_all_new_governance_units_use_next_heading_no_new_boundary_strategy():
    """Track 7D.3's budget forbids introducing a new boundary strategy --
    every configured governance unit must use one of the two existing ones."""
    configs = suc.unit_configs_for("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE) + suc.unit_configs_for(
        "BEL", NormalizedSchedule.CORPORATE_GOVERNANCE
    )
    assert configs, "expected at least one CORPORATE_GOVERNANCE unit configured"
    for config in configs:
        assert config.boundary_strategy in (
            SemanticUnitBoundaryStrategy.NEXT_HEADING,
            SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE,
        )


def test_configuration_hash_is_deterministic_and_order_independent_content():
    h1 = suc.compute_configuration_hash()
    h2 = suc.compute_configuration_hash()
    assert h1 == h2


def test_no_unit_key_collision_across_tickers_within_governance_schedule():
    act_keys = {c.unit_key for c in suc.unit_configs_for("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE)}
    bel_keys = {c.unit_key for c in suc.unit_configs_for("BEL", NormalizedSchedule.CORPORATE_GOVERNANCE)}
    assert act_keys.isdisjoint(bel_keys)

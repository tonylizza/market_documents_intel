"""Track 7D.4: configuration tests for the new REMUNERATION units.

No database access -- pure config-module assertions, mirroring the existing
pattern of testing `unit_configs_for`/`compute_configuration_hash` directly
rather than through the DB-backed orchestration layer.
"""

from market_documents.models.enums import NormalizedSchedule, SemanticUnitBoundaryStrategy
from market_documents.services import semantic_unit_config as suc


def test_act_has_three_remuneration_units():
    configs = suc.unit_configs_for("ACT", NormalizedSchedule.REMUNERATION)
    unit_keys = {c.unit_key for c in configs}
    assert unit_keys == {"remco_chairperson_report", "remuneration_policy_changes", "remuneration_governance"}


def test_bel_has_one_remuneration_unit():
    configs = suc.unit_configs_for("BEL", NormalizedSchedule.REMUNERATION)
    assert [c.unit_key for c in configs] == ["variable_remuneration"]


def test_sur_has_three_remuneration_units():
    configs = suc.unit_configs_for("SUR", NormalizedSchedule.REMUNERATION)
    unit_keys = {c.unit_key for c in configs}
    assert unit_keys == {
        "remuneration_policy_changes_and_focus",
        "fair_responsible_remuneration",
        "remuneration_policy_shareholder_engagement",
    }


def test_kp2_sbp_sdl_have_no_remuneration_units():
    """No candidate was configured for these issuers -- see the milestone
    doc's localization/inventory sections for why (fused headings, no
    standalone schedule, etc.)."""
    for ticker in ("KP2", "SBP", "SDL"):
        assert suc.unit_configs_for(ticker, NormalizedSchedule.REMUNERATION) == ()


def test_governance_and_financial_performance_units_unaffected_by_remuneration_addition():
    """Regression: adding REMUNERATION units must not change which units
    resolve for the existing FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE
    schedules."""
    bel_fp = suc.unit_configs_for("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE)
    act_fp = suc.unit_configs_for("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE)
    assert {c.unit_key for c in bel_fp} == {"gross_margin"}
    assert {c.unit_key for c in act_fp} == {"cfo_conclusion", "healthcare_services_review"}

    act_gov = suc.unit_configs_for("ACT", NormalizedSchedule.CORPORATE_GOVERNANCE)
    bel_gov = suc.unit_configs_for("BEL", NormalizedSchedule.CORPORATE_GOVERNANCE)
    assert {c.unit_key for c in act_gov} == {
        "information_security_governance",
        "governance_policies_processes",
        "combined_assurance",
    }
    assert {c.unit_key for c in bel_gov} == {"board_composition_diversity"}


def test_all_new_remuneration_units_use_next_heading_no_new_boundary_strategy():
    """Track 7D.4's budget forbids introducing a new boundary strategy --
    every configured remuneration unit must use one of the two existing
    ones."""
    configs = (
        suc.unit_configs_for("ACT", NormalizedSchedule.REMUNERATION)
        + suc.unit_configs_for("BEL", NormalizedSchedule.REMUNERATION)
        + suc.unit_configs_for("SUR", NormalizedSchedule.REMUNERATION)
    )
    assert configs, "expected at least one REMUNERATION unit configured"
    for config in configs:
        assert config.boundary_strategy in (
            SemanticUnitBoundaryStrategy.NEXT_HEADING,
            SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE,
        )


def test_configuration_hash_is_deterministic():
    h1 = suc.compute_configuration_hash()
    h2 = suc.compute_configuration_hash()
    assert h1 == h2


def test_no_unit_key_collision_across_tickers_within_remuneration_schedule():
    act_keys = {c.unit_key for c in suc.unit_configs_for("ACT", NormalizedSchedule.REMUNERATION)}
    bel_keys = {c.unit_key for c in suc.unit_configs_for("BEL", NormalizedSchedule.REMUNERATION)}
    sur_keys = {c.unit_key for c in suc.unit_configs_for("SUR", NormalizedSchedule.REMUNERATION)}
    assert act_keys.isdisjoint(bel_keys)
    assert act_keys.isdisjoint(sur_keys)
    assert bel_keys.isdisjoint(sur_keys)


def test_no_unit_key_collision_across_all_tickers_globally():
    """A given (ticker, unit_key) pair must be unique across every schedule
    -- `remuneration_policy_changes` (ACT) and
    `remuneration_policy_changes_and_focus` (SUR) were deliberately named
    differently to avoid a same-ticker-different-schedule collision risk."""
    keys = [(c.ticker, c.unit_key) for c in suc.UNIT_CONFIGS]
    assert len(keys) == len(set(keys))

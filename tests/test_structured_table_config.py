"""Pure tests for `services.structured_table_config` (Track 7C.4)."""

from market_documents.services.structured_table_config import (
    NED_REMUNERATION_POLICY_TABLE,
    TOTAL_REMUNERATION_OUTCOMES,
    compute_configuration_hash,
    schema_change_for,
    table_family_config_for_key,
    table_family_configs_for,
)
from market_documents.models.enums import NormalizedSchedule


def test_configuration_hash_is_deterministic():
    assert compute_configuration_hash() == compute_configuration_hash()


def test_configuration_hash_changes_with_config():
    baseline = compute_configuration_hash()
    changed = compute_configuration_hash((NED_REMUNERATION_POLICY_TABLE,))
    assert baseline != changed


def test_table_family_configs_for_act_remuneration():
    configs = table_family_configs_for("ACT", NormalizedSchedule.REMUNERATION)
    keys = {c.table_family_key for c in configs}
    assert keys == {"ned_remuneration_policy_table", "total_remuneration_outcomes"}


def test_table_family_configs_for_unconfigured_ticker_is_empty():
    assert table_family_configs_for("BEL", NormalizedSchedule.REMUNERATION) == ()


def test_table_family_config_for_key():
    assert table_family_config_for_key("ned_remuneration_policy_table") is NED_REMUNERATION_POLICY_TABLE
    assert table_family_config_for_key("total_remuneration_outcomes") is TOTAL_REMUNERATION_OUTCOMES
    assert table_family_config_for_key("not_a_real_table") is None


def test_ned_heading_pattern_is_year_agnostic():
    pattern = NED_REMUNERATION_POLICY_TABLE.heading_pattern
    assert pattern.search("Non-executive Directors' 2020 remuneration")
    assert pattern.search("NON-EXECUTIVE DIRECTORS' 2023 REMUNERATION")
    assert pattern.search("Non-executive Directors' 2024 remuneration")


def test_outcomes_heading_pattern_matches_case_variants():
    pattern = TOTAL_REMUNERATION_OUTCOMES.heading_pattern
    assert pattern.search("Total remuneration outcomes")
    assert pattern.search("TOTAL REMUNERATION OUTCOMES")


def test_schema_change_applies_only_to_transition_crossing_the_change_year():
    change = schema_change_for(TOTAL_REMUNERATION_OUTCOMES, "sti", earlier_year=2022, later_year=2023)
    assert change is not None
    assert change.first_affected_year == 2023

    # Both sides before the change -- no schema-change event.
    assert schema_change_for(TOTAL_REMUNERATION_OUTCOMES, "sti", earlier_year=2020, later_year=2021) is None
    # Both sides after the change -- no schema-change event (already stable
    # under the new label).
    assert schema_change_for(TOTAL_REMUNERATION_OUTCOMES, "sti", earlier_year=2023, later_year=2024) is None
    # A different metric is unaffected.
    assert schema_change_for(TOTAL_REMUNERATION_OUTCOMES, "lti", earlier_year=2022, later_year=2023) is None

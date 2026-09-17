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


def test_new_7d2_unit_is_lexical_only_and_a_production_candidate():
    entry = coverage_registry.coverage_for("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review")

    assert entry is not None
    assert entry.analytical_mode == AnalyticalMode.LEXICAL_ONLY
    assert entry.production_status == "candidate"


def test_existing_cutover_units_are_enabled_in_the_registry():
    entry = coverage_registry.coverage_for("BEL", NormalizedSchedule.FINANCIAL_PERFORMANCE, "gross_margin")

    assert entry is not None
    assert entry.production_status == "enabled"


def test_unconfigured_unit_returns_none():
    assert coverage_registry.coverage_for("XYZ", NormalizedSchedule.FINANCIAL_PERFORMANCE, "nonexistent") is None


def test_configuration_hash_is_deterministic():
    assert coverage_registry.compute_configuration_hash() == coverage_registry.compute_configuration_hash()

"""Tests for Track 7C.6's `services.comparison_routing.ComparisonPathRouter`
-- pure, deterministic, config-driven routing. No DB required: routing
never reads persisted data, per docs/7c6-production-cutover.md Section 3.
"""

from market_documents.models.enums import ComparisonBackend, NormalizedSchedule
from market_documents.services.comparison_routing import ComparisonPathRouter

FP = NormalizedSchedule.FINANCIAL_PERFORMANCE


# --- routing: in-scope narrative units -------------------------------------------


def test_bel_gross_margin_routes_semantic_unit_when_enabled():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_narrative(ticker="BEL", schedule=FP, unit_key="gross_margin") == ComparisonBackend.SEMANTIC_UNIT


def test_act_cfo_conclusion_routes_semantic_unit_when_enabled():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_narrative(ticker="ACT", schedule=FP, unit_key="cfo_conclusion") == ComparisonBackend.SEMANTIC_UNIT


def test_bel_gross_margin_ticker_case_insensitive():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_narrative(ticker="bel", schedule=FP, unit_key="gross_margin") == ComparisonBackend.SEMANTIC_UNIT


# --- routing: in-scope structured tables -----------------------------------------


def test_act_supported_table_routes_structured_table_when_enabled():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert (
        router.route_structured(ticker="ACT", table_family_key="ned_remuneration_policy_table")
        == ComparisonBackend.STRUCTURED_TABLE
    )
    assert (
        router.route_structured(ticker="ACT", table_family_key="total_remuneration_outcomes")
        == ComparisonBackend.STRUCTURED_TABLE
    )


# --- routing: out-of-scope falls back to legacy ----------------------------------


def test_unsupported_schedule_routes_legacy():
    router = ComparisonPathRouter(cutover_enabled=True)
    result = router.route_narrative(ticker="BEL", schedule=NormalizedSchedule.STRATEGY, unit_key="gross_margin")
    assert result == ComparisonBackend.LEGACY_PASSAGE


def test_unsupported_unit_key_routes_legacy():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_narrative(ticker="BEL", schedule=FP, unit_key="net_debt") == ComparisonBackend.LEGACY_PASSAGE


def test_unsupported_ticker_routes_legacy():
    for ticker in ("KP2", "SBP", "SDL", "SUR"):
        router = ComparisonPathRouter(cutover_enabled=True)
        assert router.route_narrative(ticker=ticker, schedule=FP, unit_key="gross_margin") == ComparisonBackend.LEGACY_PASSAGE


def test_unsupported_table_family_routes_legacy():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_structured(ticker="ACT", table_family_key="some_other_table") == ComparisonBackend.LEGACY_PASSAGE


def test_supported_table_wrong_ticker_routes_legacy():
    router = ComparisonPathRouter(cutover_enabled=True)
    assert router.route_structured(ticker="BEL", table_family_key="ned_remuneration_policy_table") == ComparisonBackend.LEGACY_PASSAGE


# --- feature flag: disabled restores legacy behavior everywhere -----------------


def test_disabled_flag_routes_legacy_even_for_in_scope_narrative_unit():
    router = ComparisonPathRouter(cutover_enabled=False)
    assert router.route_narrative(ticker="BEL", schedule=FP, unit_key="gross_margin") == ComparisonBackend.LEGACY_PASSAGE


def test_disabled_flag_routes_legacy_even_for_in_scope_table():
    router = ComparisonPathRouter(cutover_enabled=False)
    assert router.route_structured(ticker="ACT", table_family_key="ned_remuneration_policy_table") == ComparisonBackend.LEGACY_PASSAGE


def test_rollback_toggle_restores_prior_path():
    """Flipping cutover_enabled True -> False on an otherwise-identical
    router is the entire rollback mechanism -- no other state changes."""
    enabled_router = ComparisonPathRouter(cutover_enabled=True)
    disabled_router = ComparisonPathRouter(cutover_enabled=False)
    assert enabled_router.route_narrative(ticker="BEL", schedule=FP, unit_key="gross_margin") == ComparisonBackend.SEMANTIC_UNIT
    assert disabled_router.route_narrative(ticker="BEL", schedule=FP, unit_key="gross_margin") == ComparisonBackend.LEGACY_PASSAGE


def test_router_reads_live_settings_when_not_overridden(monkeypatch):
    from market_documents.services import comparison_routing as routing_module

    class _FakeSettings:
        semantic_comparison_cutover_enabled = True

    monkeypatch.setattr(routing_module, "get_settings", lambda: _FakeSettings())
    router = ComparisonPathRouter()
    assert router.route_narrative(ticker="BEL", schedule=FP, unit_key="gross_margin") == ComparisonBackend.SEMANTIC_UNIT

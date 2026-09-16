"""Pure tests for `services.analytical_eligibility.route_alignment` (Track
7C.3): deterministic, configuration-driven routing with no DB access.
"""

from market_documents.models.enums import AlignmentConfidence, AnalyticalMode, SemanticUnitAlignmentStatus
from market_documents.services.analytical_eligibility import route_alignment


def test_configured_unit_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED, ticker="BEL", earlier_unit_key="gross_margin", later_unit_key="gross_margin"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY
    assert decision.confidence == AlignmentConfidence.HIGH
    assert decision.review_reason is None


def test_configured_act_unit_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED, ticker="ACT", earlier_unit_key="cfo_conclusion", later_unit_key="cfo_conclusion"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_unconfigured_unit_does_not_silently_become_lexical():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED, ticker="BEL", earlier_unit_key="unknown_unit", later_unit_key="unknown_unit"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.NOT_ELIGIBLE
    assert decision.confidence == AlignmentConfidence.NEEDS_REVIEW
    assert decision.review_reason is not None


def test_unconfigured_ticker_does_not_silently_become_lexical():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED, ticker="XYZ", earlier_unit_key="gross_margin", later_unit_key="gross_margin"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.NOT_ELIGIBLE


def test_renamed_status_routes_like_matched():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.RENAMED, ticker="BEL", earlier_unit_key="gross_margin", later_unit_key="gross_margin"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_unresolved_upstream_produces_no_decision():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM, ticker="BEL", earlier_unit_key="gross_margin", later_unit_key=None
    )

    assert decision is None


def test_ambiguous_produces_no_decision():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.AMBIGUOUS, ticker="BEL", earlier_unit_key="gross_margin", later_unit_key=None
    )

    assert decision is None


def test_added_routes_to_presence_status_only_not_lexical():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.ADDED, ticker="BEL", earlier_unit_key=None, later_unit_key="gross_margin"
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.PRESENCE_STATUS_ONLY


def test_removed_routes_to_presence_status_only_not_lexical():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.REMOVED, ticker="BEL", earlier_unit_key="gross_margin", later_unit_key=None
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.PRESENCE_STATUS_ONLY

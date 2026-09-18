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


def test_configured_act_healthcare_services_review_routes_to_lexical_only():
    """Track 7D.2."""
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="healthcare_services_review",
        later_unit_key="healthcare_services_review",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY
    assert decision.confidence == AlignmentConfidence.HIGH


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


# --------------------------------------------------------------------------
# Track 7D.3: CORPORATE_GOVERNANCE routing
# --------------------------------------------------------------------------


def test_act_information_security_governance_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="information_security_governance",
        later_unit_key="information_security_governance",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_act_governance_policies_processes_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="governance_policies_processes",
        later_unit_key="governance_policies_processes",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_act_combined_assurance_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="combined_assurance",
        later_unit_key="combined_assurance",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_bel_board_composition_diversity_routes_to_structured_not_lexical():
    """Table content (demographic composition), not prose -- must not be
    silently treated as LEXICAL_ONLY just because it's MATCHED."""
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="BEL",
        earlier_unit_key="board_composition_diversity",
        later_unit_key="board_composition_diversity",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED


# --------------------------------------------------------------------------
# Track 7D.4: REMUNERATION routing
# --------------------------------------------------------------------------


def test_act_remco_chairperson_report_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="remco_chairperson_report",
        later_unit_key="remco_chairperson_report",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_act_remuneration_policy_changes_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="remuneration_policy_changes",
        later_unit_key="remuneration_policy_changes",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_act_remuneration_governance_routes_to_lexical_only():
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="ACT",
        earlier_unit_key="remuneration_governance",
        later_unit_key="remuneration_governance",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_bel_variable_remuneration_routes_to_lexical_only():
    """Unlike BEL's CORPORATE_GOVERNANCE board_composition_diversity unit,
    this is genuine narrative describing STI/LTI scheme mechanics, not a
    table -- must route LEXICAL_ONLY."""
    decision = route_alignment(
        status=SemanticUnitAlignmentStatus.MATCHED,
        ticker="BEL",
        earlier_unit_key="variable_remuneration",
        later_unit_key="variable_remuneration",
    )

    assert decision is not None
    assert decision.mode == AnalyticalMode.LEXICAL_ONLY


def test_sur_remuneration_units_route_to_lexical_only():
    for unit_key in (
        "remuneration_policy_changes_and_focus",
        "fair_responsible_remuneration",
        "remuneration_policy_shareholder_engagement",
    ):
        decision = route_alignment(
            status=SemanticUnitAlignmentStatus.MATCHED, ticker="SUR", earlier_unit_key=unit_key, later_unit_key=unit_key
        )
        assert decision is not None
        assert decision.mode == AnalyticalMode.LEXICAL_ONLY

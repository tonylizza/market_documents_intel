"""Track 7F.7a.1: unit tests for the M3-G (governance_share_change) and
M6-G (governance_topic_mix_change) formulas.

These reuse the exact same `custom_taxonomy_hit_share` / `custom_subcategory
_totals` / `subcategory_share_vector` / `cosine_distance` helpers introduced
for financial_condition's M3/M6b in Track 7F.4 (`financial_language_metrics
.py`) -- there is no separate governance hit-counting path. Coverage here
was previously entirely absent for these category-agnostic helpers (only
exercised indirectly via the publishing integration tests and the read-only
7F.7a research script), so this file also closes that gap for the
financial_condition case by construction (identical code path, different
category argument).
"""

import pytest

from market_documents.models.enums import ReportSide
from market_documents.services.financial_language_config import GOVERNANCE_SUBCATEGORIES
from market_documents.services.financial_language_metrics import (
    SidePopulation,
    cosine_distance,
    custom_subcategory_totals,
    custom_taxonomy_hit_share,
    subcategory_share_vector,
)


def _side(**custom_category_totals: int) -> SidePopulation:
    return SidePopulation(
        count=1,
        words=1000.0,
        category_totals={},
        custom_category_totals=dict(custom_category_totals),
        dictionary_hit_total=0,
    )


# --- governance_share formula ---


def test_governance_share_formula():
    side = _side(risk=10, financial_condition=20, governance=30, strategy=40)
    # governance_share = governance_hits / total_custom_taxonomy_hits = 30/100
    assert custom_taxonomy_hit_share(side, "governance") == 0.30


def test_governance_share_bounds_zero_and_one():
    all_governance = _side(risk=0, financial_condition=0, governance=50, strategy=0)
    assert custom_taxonomy_hit_share(all_governance, "governance") == 1.0

    no_governance = _side(risk=10, financial_condition=10, governance=0, strategy=10)
    assert custom_taxonomy_hit_share(no_governance, "governance") == 0.0


def test_governance_share_is_none_when_total_taxonomy_hits_zero():
    empty = _side(risk=0, financial_condition=0, governance=0, strategy=0)
    assert custom_taxonomy_hit_share(empty, "governance") is None


def test_governance_share_always_in_unit_interval():
    for gov, risk, fc, strat in [(1, 1, 1, 1), (0, 5, 5, 5), (100, 1, 1, 1), (3, 0, 0, 0)]:
        side = _side(risk=risk, financial_condition=fc, governance=gov, strategy=strat)
        share = custom_taxonomy_hit_share(side, "governance")
        assert share is None or 0.0 <= share <= 1.0


# --- governance_share_change (M3-G) formula ---


def test_governance_share_change_is_later_minus_earlier():
    earlier = _side(risk=40, financial_condition=30, governance=20, strategy=10)  # gov share 0.20
    later = _side(risk=10, financial_condition=10, governance=70, strategy=10)  # gov share 0.70
    share_e = custom_taxonomy_hit_share(earlier, "governance")
    share_l = custom_taxonomy_hit_share(later, "governance")
    change = share_l - share_e
    assert share_e == 0.20
    assert share_l == 0.70
    assert change == pytest.approx(0.50)


def test_governance_share_change_bounded_minus_one_to_one():
    min_side = _side(risk=100, financial_condition=0, governance=0, strategy=0)  # share 0.0
    max_side = _side(risk=0, financial_condition=0, governance=100, strategy=0)  # share 1.0
    change_up = custom_taxonomy_hit_share(max_side, "governance") - custom_taxonomy_hit_share(min_side, "governance")
    change_down = custom_taxonomy_hit_share(min_side, "governance") - custom_taxonomy_hit_share(max_side, "governance")
    assert change_up == 1.0
    assert change_down == -1.0
    assert -1.0 <= change_up <= 1.0
    assert -1.0 <= change_down <= 1.0


def test_share_relative_movement_from_other_categories_without_governance_volume_change():
    # Track 7F.7a section 9 (share-relative case handling): governance hits
    # identical (20) on both sides, but total taxonomy hits grew because
    # risk/financial_condition/strategy grew -- share still moves even
    # though governance's own volume is flat. This is the "type B" case
    # (SUR 2023->2024 / BEL 2020->2021 / ACT 2022->2023 pattern).
    earlier = _side(risk=10, financial_condition=10, governance=20, strategy=10)  # total 50, share 0.40
    later = _side(risk=40, financial_condition=40, governance=20, strategy=40)  # total 140, share ~0.1429
    share_e = custom_taxonomy_hit_share(earlier, "governance")
    share_l = custom_taxonomy_hit_share(later, "governance")
    assert share_e == 0.40
    assert round(share_l, 4) == 0.1429
    # Own governance hit count is unchanged -- this is the signal a
    # share-relative interpretation branch must distinguish from actual
    # governance-language volume movement.
    assert earlier.custom_category_totals["governance"] == later.custom_category_totals["governance"] == 20
    assert share_l - share_e < 0  # share fell purely because other categories grew


# --- governance_topic_mix_change (M6-G) formula ---


def test_governance_topic_mix_change_zero_when_identical_mix():
    totals = {"board": 30, "audit": 20, "internal_controls": 50}
    vec = subcategory_share_vector(totals, GOVERNANCE_SUBCATEGORIES)
    distance = cosine_distance(vec, vec)
    assert distance is not None
    assert abs(distance) < 1e-9


def test_governance_topic_mix_change_positive_when_mix_shifts():
    earlier = subcategory_share_vector({"board": 100}, GOVERNANCE_SUBCATEGORIES)
    later = subcategory_share_vector({"audit": 100}, GOVERNANCE_SUBCATEGORIES)
    distance = cosine_distance(earlier, later)
    # orthogonal one-hot vectors -> cosine similarity 0 -> distance 1
    assert distance == 1.0


def test_governance_topic_mix_change_zero_vector_behavior_is_none():
    # 7F.7a research script: if either side has zero governance hits at
    # all, cosine similarity is undefined -- must be None, never a
    # fabricated 0.0 (no change) or 1.0 (maximal change).
    zero_vec = subcategory_share_vector({}, GOVERNANCE_SUBCATEGORIES)
    nonzero_vec = subcategory_share_vector({"board": 10}, GOVERNANCE_SUBCATEGORIES)
    assert cosine_distance(zero_vec, nonzero_vec) is None
    assert cosine_distance(nonzero_vec, zero_vec) is None
    assert cosine_distance(zero_vec, zero_vec) is None


def test_governance_subcategory_vector_has_nine_dimensions_fixed_order():
    assert GOVERNANCE_SUBCATEGORIES == (
        "board",
        "audit",
        "internal_controls",
        "remuneration",
        "ethics",
        "regulatory_compliance",
        "litigation",
        "shareholder_rights",
        "related_party",
    )
    vec = subcategory_share_vector({"remuneration": 5}, GOVERNANCE_SUBCATEGORIES)
    assert len(vec) == 9
    assert sum(vec) == 1.0


def test_custom_subcategory_totals_scoped_to_governance_category_and_side():
    from market_documents.models.enums import AlignmentConfidence, AlignmentStatus
    from market_documents.services.financial_language_metrics import SignalRowInput

    rows = [
        SignalRowInput(
            report_side=ReportSide.EARLIER,
            alignment_status=AlignmentStatus.SUBSTANTIALLY_MODIFIED,
            confidence=AlignmentConfidence.HIGH,
            passage_word_count=100,
            structured_content_category=None,
            feature_eligible=True,
            positive_count=0,
            negative_count=0,
            uncertainty_count=0,
            litigious_count=0,
            constraining_count=0,
            strong_modal_count=0,
            weak_modal_count=0,
            total_dictionary_hits=5,
            custom_subcategory_hits={("governance", "board"): 3, ("financial_condition", "debt"): 7},
        ),
        SignalRowInput(
            report_side=ReportSide.LATER,
            alignment_status=AlignmentStatus.SUBSTANTIALLY_MODIFIED,
            confidence=AlignmentConfidence.HIGH,
            passage_word_count=100,
            structured_content_category=None,
            feature_eligible=True,
            positive_count=0,
            negative_count=0,
            uncertainty_count=0,
            litigious_count=0,
            constraining_count=0,
            strong_modal_count=0,
            weak_modal_count=0,
            total_dictionary_hits=5,
            custom_subcategory_hits={("governance", "audit"): 4},
        ),
    ]
    earlier_totals = custom_subcategory_totals(rows, ReportSide.EARLIER, "governance")
    later_totals = custom_subcategory_totals(rows, ReportSide.LATER, "governance")
    assert earlier_totals == {"board": 3}  # financial_condition hit excluded
    assert later_totals == {"audit": 4}

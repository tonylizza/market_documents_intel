"""Track 7F.9: pure topic-change helpers (C_min conjunction, count/density
legs, alignment-unit diagnostics) and golden anchor cases reproduced from
the raw 7F.8a hit/word inputs."""

import math
import uuid

import pytest

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, ReportSide
from market_documents.services.financial_language_metrics import (
    SignalRowInput,
    change_consistency_ratio,
    compute_topic_change,
    density_change,
    largest_passage_share,
    pair_mean_count_change,
    topic_change_conjunction,
    topic_change_diagnostics,
    topic_unit_deltas,
)

# --- pair_mean_count_change / density_change ---


def test_pair_mean_count_change_uses_average_words():
    assert pair_mean_count_change(10, 30, 1000, 3000) == pytest.approx(1000 * 20 / 2000)


def test_pair_mean_count_change_zero_denominator_is_none():
    assert pair_mean_count_change(0, 5, 0, 0) is None


def test_density_change_matches_rate_difference():
    assert density_change(10, 30, 1000, 3000) == pytest.approx(0.0)
    assert density_change(10, 20, 1000, 1000) == pytest.approx(10.0)


def test_density_change_zero_side_is_none():
    assert density_change(1, 1, 0, 100) is None
    assert density_change(1, 1, 100, 0) is None


def test_density_decomposes_into_volume_and_length_parts():
    # 7F.8 Shapley identity: M1 = 1000*dh/HM(w1,w2) + 1000*hbar*(1/w2-1/w1).
    h1, h2, w1, w2 = 117, 67, 30210.0, 16450.0
    hm = 2 * w1 * w2 / (w1 + w2)
    volume = 1000 * (h2 - h1) / hm
    length = 1000 * ((h1 + h2) / 2) * (1 / w2 - 1 / w1)
    assert density_change(h1, h2, w1, w2) == pytest.approx(volume + length, abs=1e-12)


# --- topic_change_conjunction ---


@pytest.mark.parametrize(
    "d,m,expected",
    [
        (1.0, 0.3, 0.3),
        (0.3, 1.0, 0.3),
        (-1.0, -0.4, -0.4),
        (-0.2, -3.0, -0.2),
        (1.0, -0.5, 0.0),  # disagree
        (-1.0, 0.5, 0.0),  # disagree
        (0.0, 1.0, 0.0),  # count leg flat
        (1.0, 0.0, 0.0),  # density leg flat
        (0.0, 0.0, 0.0),
    ],
)
def test_conjunction_cases(d, m, expected):
    assert topic_change_conjunction(d, m) == expected


def test_conjunction_undefined_leg_is_none():
    assert topic_change_conjunction(None, 1.0) is None
    assert topic_change_conjunction(1.0, None) is None


def test_conjunction_sign_follows_count_leg():
    assert math.copysign(1, topic_change_conjunction(-2.0, -1.0)) == -1


# --- diagnostics ---


def test_change_consistency_ratio_and_largest_share():
    deltas = [5, -2, 3]
    assert change_consistency_ratio(deltas) == pytest.approx(6 / 10)
    assert largest_passage_share(deltas) == pytest.approx(5 / 10)


def test_diagnostics_zero_gross_are_zero():
    assert change_consistency_ratio([]) == 0.0
    assert largest_passage_share([]) == 0.0
    d = topic_change_diagnostics([])
    assert (d.supporting_hits, d.opposing_hits, d.change_consistency_ratio, d.largest_passage_share) == (0, 0, 0.0, 0.0)


def test_supporting_opposing_relative_to_net_direction():
    up = topic_change_diagnostics([5, -2, 3])
    assert (up.supporting_hits, up.opposing_hits) == (8, 2)
    down = topic_change_diagnostics([-5, 2, -3])
    assert (down.supporting_hits, down.opposing_hits) == (8, 2)
    assert down.change_consistency_ratio == pytest.approx(-0.6)


def test_diagnostics_net_zero_has_no_direction():
    d = topic_change_diagnostics([-8, 8])  # moved passage signature
    assert (d.supporting_hits, d.opposing_hits) == (0, 0)
    assert d.change_consistency_ratio == 0.0
    assert d.largest_passage_share == pytest.approx(0.5)


def _row(side: ReportSide, alignment_id: uuid.UUID | None, words: int, uncertainty: int, fc: int = 0) -> SignalRowInput:
    return SignalRowInput(
        report_side=side,
        alignment_status=AlignmentStatus.SUBSTANTIALLY_MODIFIED,
        confidence=AlignmentConfidence.HIGH,
        passage_word_count=words,
        structured_content_category=None,
        feature_eligible=True,
        positive_count=0,
        negative_count=0,
        uncertainty_count=uncertainty,
        litigious_count=0,
        constraining_count=0,
        strong_modal_count=0,
        weak_modal_count=0,
        total_dictionary_hits=uncertainty + fc,
        custom_category_hits={"financial_condition": fc} if fc else {},
        passage_alignment_id=alignment_id,
    )


def test_unit_deltas_group_by_alignment_unit():
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    rows = [
        _row(ReportSide.EARLIER, a, 100, 2),
        _row(ReportSide.LATER, a, 100, 5),  # +3
        _row(ReportSide.EARLIER, b, 100, 4),  # REMOVED-like: -4
        _row(ReportSide.LATER, c, 100, 1),  # NEW-like: +1
        _row(ReportSide.LATER, b, 100, 4),  # b back to 0 net
    ]
    assert sorted(topic_unit_deltas(rows, lambda r: r.uncertainty_count)) == [1, 3]


def test_compute_topic_change_end_to_end():
    a, b = uuid.uuid4(), uuid.uuid4()
    rows = [
        _row(ReportSide.EARLIER, a, 1000, 10, fc=1),
        _row(ReportSide.LATER, a, 1000, 14, fc=1),
        _row(ReportSide.EARLIER, b, 1000, 6),
        _row(ReportSide.LATER, b, 1000, 4),
    ]
    tc = compute_topic_change(rows, lambda r: r.uncertainty_count, 2000, 2000)
    assert (tc.hits_earlier, tc.hits_later) == (16, 18)
    assert tc.count_change_per_1000 == pytest.approx(1.0)
    assert tc.density_change == pytest.approx(1.0)
    assert tc.topic_change == pytest.approx(1.0)
    assert (tc.diagnostics.supporting_hits, tc.diagnostics.opposing_hits) == (4, 2)
    assert tc.diagnostics.change_consistency_ratio == pytest.approx(2 / 6)
    assert tc.diagnostics.largest_passage_share == pytest.approx(4 / 6)


# --- Golden anchor cases: C_min from the D/M1 legs reported by
# scripts/research_7f8a_topic_conjunction_evidence.py (7F.8a Sections 3-5).
# The exact persisted values are cross-checked against the research script
# in docs/discover-metrics-unified-implementation-7f9.md Section 13. ---


@pytest.mark.parametrize(
    "label,d,m1,expected",
    [
        ("FC ACT 2017->2018", -0.0263, 1.0019, 0.0),
        ("FC BEL 2019->2020", -1.3475, 0.1494, 0.0),
        ("FC SBP 2023->2024", -0.9016, -1.1027, -0.902),
        ("FC BEL 2020->2021", 1.8921, 0.2783, 0.278),
        ("FC ACT 2016->2017", -1.0924, -0.9256, -0.926),
        ("GOV SUR 2023->2024", 0.0, 0.0915, 0.0),
        ("GOV BEL 2018->2019", -0.1391, -1.0697, -0.139),
        ("GOV ACT 2017->2018", 0.4998, 1.7360, 0.500),
        ("GOV BEL 2016->2017", 1.1889, 1.2790, 1.189),
        ("GOV ACT 2023->2024", -0.9168, -1.0545, -0.917),
        ("UNC BEL 2019->2020", -3.0185, 2.1753, 0.0),
        ("UNC BEL 2020->2021", 2.5678, -2.4952, 0.0),
        ("UNC ACT 2019->2020", 1.3493, 0.7596, 0.760),
    ],
)
def test_anchor_conjunction(label, d, m1, expected):
    assert topic_change_conjunction(d, m1) == pytest.approx(expected, abs=5e-4), label

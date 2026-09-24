"""Governance Discover candidate under Track 7F.9: `largest_governance_shift`
ranks on `governance_topic_change` (C_min, |value| >= 0.25 per 1,000 words,
both directions). M3-G (`governance_share_change`, the 7F.7a.1 ranking
metric), M1-G, and M6-G are supporting detail only.

Anchor values are the persisted 7F.9 C_min values for the 7F.8a governance
anchors and expected findings (docs/discover-metrics-unified-
implementation-7f9.md Sections 11-12).
"""

from market_documents.publishing.findings import (
    CANDIDATE_KEY_ORDER,
    ComparisonMetrics,
    eligible_candidates,
    select_findings,
)


def _base_metrics(**overrides) -> ComparisonMetrics:
    defaults = dict(
        disclosure_change_score=None,
        feature_quality_ok=False,
        feature_primary_eligible=False,
        net_tone_change=None,
        uncertainty_intensity_change=None,
        risk_language_introduction=None,
        risk_language_removal=None,
        governance_language_change=None,
        financial_condition_language_change=None,
        financial_condition_share_change=None,
        financial_condition_topic_mix_change=None,
        governance_share_change=None,
        governance_topic_mix_change=None,
        financial_condition_topic_change=None,
        governance_topic_change=None,
        uncertainty_topic_change=None,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
        new_rate_words=None,
    )
    defaults.update(overrides)
    return ComparisonMetrics(**defaults)


def test_governance_candidate_maps_to_topic_change_metric():
    primary, _, _ = select_findings(_base_metrics(governance_topic_change=0.5))
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.metric_key == "governance_topic_change"


def test_m3g_and_m1g_no_longer_drive_ranking():
    # BEL 2018->2019: M3-G -0.0635 (eligible under 7F.7a.1) and M1-G -1.07,
    # but C_min is -0.139 -- below threshold, not a governance finding.
    metrics = _base_metrics(
        governance_language_change=-1.0697,
        governance_share_change=-0.0635,
        governance_topic_mix_change=0.0056,
        governance_topic_change=-0.1391,
    )
    assert select_findings(metrics)[0] is None
    assert metrics.governance_share_change == -0.0635  # retained as supporting detail


def test_flat_count_is_not_a_finding():
    # SUR 2023->2024: governance hits 152 -> 152, C_min = 0.
    assert select_findings(_base_metrics(governance_share_change=0.06, governance_topic_change=0.0))[0] is None


def test_quality_gate_unchanged():
    metrics = _base_metrics(
        governance_topic_change=3.0, report_side_quality_ok=False, report_side_primary_eligible=False
    )
    assert select_findings(metrics)[0] is None


def test_expected_governance_findings_rank_by_magnitude():
    # The five expected 7F.9 governance findings, in expected rank order.
    anchors = {
        "BEL 2016->2017": 1.1889,
        "ACT 2023->2024": -0.9168,
        "ACT 2017->2018": 0.4998,
        "SDL 2024->2025": -0.452,
        "ACT 2020->2021": -0.269,
    }
    magnitudes = []
    for label, value in anchors.items():
        primary, _, _ = select_findings(_base_metrics(governance_topic_change=value))
        assert primary is not None and primary.key == "largest_governance_shift", label
        assert primary.value == value
        magnitudes.append(primary.magnitude)
    assert magnitudes == sorted(magnitudes, reverse=True)


def test_other_candidates_unaffected_by_governance():
    metrics = _base_metrics(net_tone_change=-9.0, governance_topic_change=None)
    assert {f.key for f in eligible_candidates(metrics)} == {"largest_negative_tone_shift"}


def test_candidate_key_order_unchanged_for_governance_position():
    assert CANDIDATE_KEY_ORDER.index("largest_governance_shift") == 5

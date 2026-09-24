"""CandidateSpec behaviour under the frozen Track 7F.8/7F.8a methodology,
implemented in Track 7F.9 (C_min topic-change metrics, net tone decline,
disabled alignment/feature-gated types, no evidence gate)."""

import pytest

from market_documents.publishing.findings import (
    CANDIDATE_KEY_ORDER,
    CANDIDATES,
    DISABLED_CANDIDATE_KEYS,
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
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
        new_rate_words=None,
    )
    defaults.update(overrides)
    return ComparisonMetrics(**defaults)


def _report_side(**overrides) -> ComparisonMetrics:
    return _base_metrics(report_side_quality_ok=True, report_side_primary_eligible=True, **overrides)


def test_candidate_specs_match_frozen_methodology():
    specs = {s.key: s for s in CANDIDATES}
    assert set(specs) == {
        "largest_uncertainty_increase",
        "largest_negative_tone_shift",
        "largest_governance_shift",
        "largest_financial_condition_shift",
    }
    assert (specs["largest_financial_condition_shift"].metric_key, specs["largest_financial_condition_shift"].epsilon) == (
        "financial_condition_topic_change", 0.25,
    )
    assert (specs["largest_governance_shift"].metric_key, specs["largest_governance_shift"].epsilon) == (
        "governance_topic_change", 0.25,
    )
    assert (specs["largest_uncertainty_increase"].metric_key, specs["largest_uncertainty_increase"].epsilon) == (
        "uncertainty_topic_change", 0.75,
    )
    assert (specs["largest_negative_tone_shift"].metric_key, specs["largest_negative_tone_shift"].epsilon) == (
        "net_tone_change", 2.25,
    )
    assert all(s.unit == "rate_per_1000_words" for s in CANDIDATES)


def test_disabled_keys_are_exactly_the_frozen_set_and_have_no_spec():
    assert set(DISABLED_CANDIDATE_KEYS) == {
        "largest_overall_change",
        "largest_new_disclosure_share",
        "largest_risk_introduction",
        "largest_risk_removal",
    }
    assert not set(DISABLED_CANDIDATE_KEYS) & {s.key for s in CANDIDATES}
    # Vocabulary is unchanged: every key is either published or disabled.
    assert set(CANDIDATE_KEY_ORDER) == {s.key for s in CANDIDATES} | set(DISABLED_CANDIDATE_KEYS)


def test_disabled_types_never_selected_even_when_every_gate_passes():
    metrics = _base_metrics(
        disclosure_change_score=0.99,
        feature_quality_ok=True,
        feature_primary_eligible=True,
        new_rate_words=0.9,
        risk_language_introduction=50.0,
        risk_language_removal=50.0,
        alignment_change_quality_ok=True,
        alignment_change_primary_eligible=True,
    )
    assert eligible_candidates(metrics) == []
    assert select_findings(metrics) == (None, None, None)


def test_no_eligible_candidates_yields_all_none_findings():
    assert select_findings(_base_metrics()) == (None, None, None)


@pytest.mark.parametrize(
    "field,key",
    [
        ("financial_condition_topic_change", "largest_financial_condition_shift"),
        ("governance_topic_change", "largest_governance_shift"),
    ],
)
def test_topic_threshold_is_quarter_per_1000_both_directions(field, key):
    assert select_findings(_report_side(**{field: 0.2499}))[0] is None
    assert select_findings(_report_side(**{field: -0.2499}))[0] is None
    for value in (0.25, -0.25, 1.2, -0.9):
        primary = select_findings(_report_side(**{field: value}))[0]
        assert primary is not None and primary.key == key and primary.value == value


def test_uncertainty_is_increase_only_at_three_quarters():
    assert select_findings(_report_side(uncertainty_topic_change=0.7499))[0] is None
    assert select_findings(_report_side(uncertainty_topic_change=-5.0))[0] is None
    primary = select_findings(_report_side(uncertainty_topic_change=0.75))[0]
    assert primary is not None and primary.key == "largest_uncertainty_increase"


def test_uncertainty_ranks_on_topic_change_not_density():
    # BEL 2019->2020: density +2.18 but hits fell (C_min = 0) -- no finding.
    metrics = _report_side(uncertainty_intensity_change=2.1753, uncertainty_topic_change=0.0)
    assert select_findings(metrics)[0] is None


def test_net_tone_decline_only_at_minus_two_and_a_quarter():
    assert select_findings(_report_side(net_tone_change=5.0))[0] is None
    assert select_findings(_report_side(net_tone_change=-2.2499))[0] is None
    primary = select_findings(_report_side(net_tone_change=-2.25))[0]
    assert primary is not None and primary.key == "largest_negative_tone_shift"


def test_supporting_metrics_never_drive_findings():
    # Large M1 / M3 / topic-mix values alone never produce a finding.
    metrics = _report_side(
        financial_condition_language_change=50.0,
        financial_condition_share_change=0.5,
        financial_condition_topic_mix_change=0.9,
        governance_language_change=50.0,
        governance_share_change=0.5,
        governance_topic_mix_change=0.9,
        uncertainty_intensity_change=50.0,
    )
    assert select_findings(metrics) == (None, None, None)


def test_report_side_gate_still_required():
    metrics = _base_metrics(financial_condition_topic_change=5.0, net_tone_change=-9.0)
    assert select_findings(metrics) == (None, None, None)


def test_magnitude_descending_order_and_top_three():
    metrics = _report_side(
        net_tone_change=-9.0,  # 9 / 2.25 = 4.0
        financial_condition_topic_change=-0.5,  # 2.0
        governance_topic_change=1.25,  # 5.0
        uncertainty_topic_change=0.9,  # 1.2
    )
    primary, secondary, tertiary = select_findings(metrics)
    assert [primary.key, secondary.key, tertiary.key] == [
        "largest_governance_shift",
        "largest_negative_tone_shift",
        "largest_financial_condition_shift",
    ]


def test_fixed_order_tiebreak_on_exact_ties():
    # 0.5 / 0.25 == 4.5 / 2.25 == 2.0 exactly.
    metrics = _report_side(net_tone_change=-4.5, governance_topic_change=0.5)
    magnitudes = {s.key: s.magnitude for s in eligible_candidates(metrics)}
    assert magnitudes["largest_negative_tone_shift"] == magnitudes["largest_governance_shift"]
    primary, secondary, _ = select_findings(metrics)
    assert primary.key == "largest_negative_tone_shift"
    assert secondary.key == "largest_governance_shift"


# --- Golden anchor cases (persisted values; see
# tests/test_topic_change_metrics.py for the formula-level anchors). ---


@pytest.mark.parametrize(
    "field,value,eligible",
    [
        ("financial_condition_topic_change", 0.0, False),  # ACT FC 2017->2018
        ("financial_condition_topic_change", 0.0, False),  # BEL FC 2019->2020
        ("financial_condition_topic_change", -0.9016, True),  # SBP FC 2023->2024
        ("financial_condition_topic_change", 0.2783, True),  # BEL FC 2020->2021
        ("financial_condition_topic_change", -0.9256, True),  # ACT FC 2016->2017
        ("governance_topic_change", 0.0, False),  # SUR GOV 2023->2024
        ("governance_topic_change", -0.1391, False),  # BEL GOV 2018->2019, below threshold
        ("governance_topic_change", 0.4998, True),  # ACT GOV 2017->2018
        ("governance_topic_change", 1.1889, True),  # BEL GOV 2016->2017
        ("governance_topic_change", -0.9168, True),  # ACT GOV 2023->2024
        ("uncertainty_topic_change", 0.0, False),  # BEL UNC 2019->2020
        ("uncertainty_topic_change", 0.0, False),  # BEL UNC 2020->2021
        ("uncertainty_topic_change", 0.7596, True),  # ACT UNC 2019->2020
    ],
)
def test_anchor_case_eligibility(field, value, eligible):
    assert (select_findings(_report_side(**{field: value}))[0] is not None) is eligible

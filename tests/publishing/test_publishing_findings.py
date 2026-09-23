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
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
        new_rate_words=None,
    )
    defaults.update(overrides)
    return ComparisonMetrics(**defaults)


def test_no_eligible_candidates_yields_all_none_findings():
    metrics = _base_metrics()
    primary, secondary, tertiary = select_findings(metrics)
    assert primary is None and secondary is None and tertiary is None


def test_ineligible_but_huge_value_never_selected():
    # feature gate fails (feature_quality_ok False) despite a huge score.
    metrics = _base_metrics(disclosure_change_score=0.99, feature_quality_ok=False, feature_primary_eligible=True)
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_sub_epsilon_candidate_never_selected():
    # disclosure_change_score epsilon is 0.05; well below that is immaterial.
    metrics = _base_metrics(disclosure_change_score=0.01, feature_quality_ok=True, feature_primary_eligible=True)
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_single_eligible_candidate_fills_only_primary():
    metrics = _base_metrics(disclosure_change_score=0.5, feature_quality_ok=True, feature_primary_eligible=True)
    primary, secondary, tertiary = select_findings(metrics)
    assert primary is not None and primary.key == "largest_overall_change"
    assert secondary is None and tertiary is None


def test_magnitude_descending_order():
    metrics = _base_metrics(
        disclosure_change_score=0.10,
        feature_quality_ok=True,
        feature_primary_eligible=True,
        net_tone_change=-8.0,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, secondary, tertiary = select_findings(metrics)
    # net_tone_change magnitude (8.0/1.0=8) beats disclosure_change_score (0.10/0.05=2)
    assert primary.key == "largest_negative_tone_shift"
    assert secondary.key == "largest_overall_change"
    assert tertiary is None


def test_negative_tone_shift_requires_negative_value():
    metrics = _base_metrics(
        net_tone_change=5.0,  # positive == tone improved, not a "negative tone shift"
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_uncertainty_increase_requires_positive_value():
    metrics = _base_metrics(
        uncertainty_intensity_change=-5.0,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_risk_introduction_gated_by_alignment_change_not_report_side():
    metrics = _base_metrics(
        risk_language_introduction=10.0,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None  # wrong gate satisfied, not the required one


def test_fixed_order_tiebreak_on_exact_ties():
    # governance_share_change (M3-G, epsilon 0.05) magnitude 5.0/0.05=100 vs
    # net_tone_change (epsilon 1.0) magnitude 5.0/1.0=5 would not tie -- use
    # a governance_share_change value whose /epsilon magnitude exactly
    # matches net_tone_change's (5.0/1.0=5 -> 0.25/0.05=5).
    metrics = _base_metrics(
        net_tone_change=-5.0,
        governance_share_change=0.25,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    survivors = eligible_candidates(metrics)
    magnitudes = {s.key: s.magnitude for s in survivors}
    assert magnitudes["largest_negative_tone_shift"] == magnitudes["largest_governance_shift"]
    primary, secondary, _ = select_findings(metrics)
    # net_tone_change appears before governance_share_change in CANDIDATE_KEY_ORDER
    assert CANDIDATE_KEY_ORDER.index("largest_negative_tone_shift") < CANDIDATE_KEY_ORDER.index(
        "largest_governance_shift"
    )
    assert primary.key == "largest_negative_tone_shift"
    assert secondary.key == "largest_governance_shift"


def test_top_three_selected_when_more_than_three_eligible():
    metrics = _base_metrics(
        disclosure_change_score=0.9,
        feature_quality_ok=True,
        feature_primary_eligible=True,
        net_tone_change=-9.0,
        uncertainty_intensity_change=8.0,
        governance_language_change=7.0,
        financial_condition_share_change=0.06,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, secondary, tertiary = select_findings(metrics)
    assert None not in (primary, secondary, tertiary)
    magnitudes = [primary.magnitude, secondary.magnitude, tertiary.magnitude]
    assert magnitudes == sorted(magnitudes, reverse=True)


# --- Track 7F.4: M3 (financial_condition_share_change) is now the
# `largest_financial_condition_shift` candidate, epsilon=0.04, M1
# (financial_condition_language_change) no longer drives ranking. ---


def test_financial_condition_candidate_uses_m3_not_m1():
    # Large M1 alone (old metric) is not enough -- M3 absent means no finding.
    metrics = _base_metrics(
        financial_condition_language_change=50.0,
        financial_condition_share_change=None,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_financial_condition_epsilon_is_point_zero_four():
    below = _base_metrics(
        financial_condition_share_change=0.039,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    assert select_findings(below)[0] is None

    at_threshold = _base_metrics(
        financial_condition_share_change=0.04,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(at_threshold)
    assert primary is not None and primary.key == "largest_financial_condition_shift"


def test_act_2017_2018_artifact_demoted_by_m3():
    # ACT 2017->2018: M1 +1.0019 (old metric, would have been eligible under
    # epsilon=1.0) but M3 +0.0182 is well below the 0.04 materiality bar --
    # this is the flagship denominator-shrinkage artifact 7F.1 diagnosed.
    metrics = _base_metrics(
        financial_condition_language_change=1.0019,
        financial_condition_share_change=0.0182,
        financial_condition_topic_mix_change=0.0043,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_sbp_2023_2024_positive_control_retained():
    metrics = _base_metrics(
        financial_condition_language_change=-1.1027,
        financial_condition_share_change=-0.0725,
        financial_condition_topic_mix_change=0.0126,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_financial_condition_shift"
    assert primary.value == -0.0725


def test_financial_condition_quality_gate_unchanged():
    # ACT 2016->2024: large M3 but quality-excluded (report-side gate fails)
    # -- must stay excluded regardless of M3 magnitude.
    metrics = _base_metrics(
        financial_condition_share_change=0.5,
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_other_discovery_candidates_unaffected_by_m3_change():
    metrics = _base_metrics(
        disclosure_change_score=0.9,
        feature_quality_ok=True,
        feature_primary_eligible=True,
        net_tone_change=-9.0,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
        financial_condition_share_change=None,
    )
    survivors = {f.key for f in eligible_candidates(metrics)}
    assert survivors == {"largest_overall_change", "largest_negative_tone_shift"}

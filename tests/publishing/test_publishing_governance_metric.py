"""Track 7F.7a.1: governance moves from M1-G (governance_language_change,
rate-difference heuristic) to M3-G (governance_share_change, epsilon=0.05
per docs/governance-metric-redesign-7f7a.md's
ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD decision) as the `largest_governance_
shift` Discover candidate -- exact mirror of the financial-condition M1->M3
switch validated in `test_publishing_findings.py`.

Anchor values below are the validated 7F.7a corpus results (see
docs/governance-metric-redesign-7f7a.md section 13/14/15).
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
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
        alignment_change_quality_ok=False,
        alignment_change_primary_eligible=False,
        new_rate_words=None,
    )
    defaults.update(overrides)
    return ComparisonMetrics(**defaults)


def test_governance_candidate_uses_m3g_not_m1g():
    # Large M1-G alone (old metric) is not enough -- M3-G absent means no finding.
    metrics = _base_metrics(
        governance_language_change=50.0,
        governance_share_change=None,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_governance_candidate_key_maps_to_share_change_metric():
    metrics = _base_metrics(
        governance_share_change=0.10,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.metric_key == "governance_share_change"


def test_governance_epsilon_is_point_zero_five():
    below = _base_metrics(
        governance_share_change=0.049,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    assert select_findings(below)[0] is None

    at_threshold = _base_metrics(
        governance_share_change=0.05,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(at_threshold)
    assert primary is not None and primary.key == "largest_governance_shift"


def test_governance_quality_gate_unchanged():
    # ACT long-gap pair: large M3-G but quality-excluded (report-side gate
    # fails) -- must stay excluded regardless of M3-G magnitude.
    metrics = _base_metrics(
        governance_share_change=0.5,
        report_side_quality_ok=False,
        report_side_primary_eligible=False,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is None


def test_other_discovery_candidates_unaffected_by_governance_change():
    metrics = _base_metrics(
        disclosure_change_score=0.9,
        feature_quality_ok=True,
        feature_primary_eligible=True,
        net_tone_change=-9.0,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
        governance_share_change=None,
    )
    survivors = {f.key for f in eligible_candidates(metrics)}
    assert survivors == {"largest_overall_change", "largest_negative_tone_shift"}


# --- Anchor regression checks (docs/governance-metric-redesign-7f7a.md sec 14/15) ---


def test_act_2017_2018_retained_under_m3g():
    # M1-G +1.7360 (old metric, inflated by report-length change) but the
    # real signal is M3-G +0.0865 -- must clear the 0.05 bar and remain
    # eligible (unlike the financial-condition ACT 2017->2018 case, which
    # was *demoted* by its M3 switch -- governance's M3-G tells the
    # opposite story here: the share increase is real, not an artifact).
    metrics = _base_metrics(
        governance_language_change=1.7360,
        governance_share_change=0.0865,
        governance_topic_mix_change=0.0193,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.value == 0.0865


def test_bel_2018_2019_retained_under_m3g():
    # M1-G -1.0697 (absolute volume roughly flat) but relative share
    # declined (M3-G -0.0635) because other custom-taxonomy categories
    # expanded -- share-relative movement, must remain eligible.
    metrics = _base_metrics(
        governance_language_change=-1.0697,
        governance_share_change=-0.0635,
        governance_topic_mix_change=0.0056,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.value == -0.0635


def test_bel_2016_2017_retained_under_m3g():
    metrics = _base_metrics(
        governance_language_change=1.2790,
        governance_share_change=0.0993,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.value == 0.0993


def test_act_2023_2024_becomes_rank_one_by_magnitude():
    # |M3-G| = 0.1093 is the largest of the 6 validated eligible pairs --
    # confirm its magnitude beats the next-largest anchor (BEL 2016->2017,
    # |M3-G|=0.0993).
    act_2023 = _base_metrics(
        governance_language_change=-1.0545,
        governance_share_change=-0.1093,
        governance_topic_mix_change=0.0660,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    bel_2016 = _base_metrics(
        governance_share_change=0.0993,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    act_primary, _, _ = select_findings(act_2023)
    bel_primary, _, _ = select_findings(bel_2016)
    assert act_primary is not None and bel_primary is not None
    assert act_primary.magnitude > bel_primary.magnitude


def test_sdl_2024_2025_becomes_eligible():
    metrics = _base_metrics(
        governance_share_change=-0.0609,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.value == -0.0609


def test_sbp_2023_2024_becomes_eligible():
    metrics = _base_metrics(
        governance_share_change=0.0589,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    primary, _, _ = select_findings(metrics)
    assert primary is not None
    assert primary.key == "largest_governance_shift"
    assert primary.value == 0.0589


def test_m1g_remains_available_as_supporting_detail():
    # M1-G stays populated on ComparisonMetrics regardless of ranking
    # eligibility -- it is dropped from `CandidateSpec` wiring only, never
    # removed from the data model.
    metrics = _base_metrics(
        governance_language_change=1.7360,
        governance_share_change=0.0865,
        report_side_quality_ok=True,
        report_side_primary_eligible=True,
    )
    assert metrics.governance_language_change == 1.7360
    primary, _, _ = select_findings(metrics)
    assert primary.metric_key == "governance_share_change"  # not governance_language_change


def test_candidate_key_order_unchanged_for_governance_position():
    assert "largest_governance_shift" in CANDIDATE_KEY_ORDER
    # Position in the fixed evaluation/tie-break order is unchanged by the
    # metric-key swap (only the underlying value source changed).
    assert CANDIDATE_KEY_ORDER.index("largest_governance_shift") == 5

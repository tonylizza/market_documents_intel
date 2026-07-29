"""Deterministic `finding_key` (primary/secondary/tertiary) selection for one
`report_comparisons` row, and the shared candidate-signal table that
`discovery.py` also ranks across the whole corpus.

Pure and database-free: operates only on `ComparisonMetrics`, a plain
extraction of the exact already-computed research values a comparison
needs (see `publisher.py` for how it's built from `ReportPairFeatures`/
`ReportPairLanguageFeatures`). Quality/eligibility flags are read verbatim
from that source -- never re-derived here.
"""

from collections.abc import Callable
from dataclasses import dataclass

# The brief's 8 discovery types, used directly as finding-candidate keys too
# (no separate vocabulary) -- fixed evaluation order used as the
# deterministic tie-break when two candidates have identical magnitude.
CANDIDATE_KEY_ORDER: tuple[str, ...] = (
    "largest_overall_change",
    "largest_uncertainty_increase",
    "largest_negative_tone_shift",
    "largest_risk_introduction",
    "largest_risk_removal",
    "largest_governance_shift",
    "largest_financial_condition_shift",
    "largest_new_disclosure_share",
)


@dataclass(frozen=True)
class ComparisonMetrics:
    """Plain, already-extracted values for one comparison. Quality/
    eligibility booleans are read verbatim from `ReportPairFeatures`/
    `ReportPairLanguageFeatures` -- never re-derived (see
    `publisher.py::_comparison_metrics`)."""

    disclosure_change_score: float | None
    feature_quality_ok: bool
    feature_primary_eligible: bool

    net_tone_change: float | None
    uncertainty_intensity_change: float | None
    risk_language_introduction: float | None
    risk_language_removal: float | None
    governance_language_change: float | None
    financial_condition_language_change: float | None
    report_side_quality_ok: bool
    report_side_primary_eligible: bool
    alignment_change_quality_ok: bool
    alignment_change_primary_eligible: bool

    new_rate_words: float | None


def _gate_feature(m: ComparisonMetrics) -> bool:
    return m.feature_quality_ok and m.feature_primary_eligible


def _gate_report_side(m: ComparisonMetrics) -> bool:
    return m.report_side_quality_ok and m.report_side_primary_eligible


def _gate_alignment_change(m: ComparisonMetrics) -> bool:
    return m.alignment_change_quality_ok and m.alignment_change_primary_eligible


@dataclass(frozen=True)
class CandidateSpec:
    key: str
    metric_key: str
    unit: str
    # Materiality bar: a candidate whose |value| is below `epsilon` is
    # dropped even if it is the only eligible candidate in the pool --
    # never headline a change too small to matter.
    epsilon: float
    get_value: Callable[[ComparisonMetrics], float | None]
    gate: Callable[[ComparisonMetrics], bool]
    # Direction filter: e.g. "negative tone shift" is only a real finding
    # when the value is actually negative, not merely large in magnitude.
    direction_ok: Callable[[float], bool] = lambda _v: True


CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        "largest_overall_change", "disclosure_change_score", "score_0_1", 0.05,
        lambda m: m.disclosure_change_score, _gate_feature,
    ),
    CandidateSpec(
        "largest_uncertainty_increase", "uncertainty_intensity_change", "rate_per_1000_words", 1.0,
        lambda m: m.uncertainty_intensity_change, _gate_report_side, lambda v: v > 0,
    ),
    CandidateSpec(
        "largest_negative_tone_shift", "net_tone_change", "rate_per_1000_words", 1.0,
        lambda m: m.net_tone_change, _gate_report_side, lambda v: v < 0,
    ),
    CandidateSpec(
        "largest_risk_introduction", "risk_language_introduction", "rate_per_1000_words", 1.0,
        lambda m: m.risk_language_introduction, _gate_alignment_change,
    ),
    CandidateSpec(
        "largest_risk_removal", "risk_language_removal", "rate_per_1000_words", 1.0,
        lambda m: m.risk_language_removal, _gate_alignment_change,
    ),
    CandidateSpec(
        "largest_governance_shift", "governance_language_change", "rate_per_1000_words", 1.0,
        lambda m: m.governance_language_change, _gate_report_side,
    ),
    CandidateSpec(
        "largest_financial_condition_shift", "financial_condition_language_change", "rate_per_1000_words", 1.0,
        lambda m: m.financial_condition_language_change, _gate_report_side,
    ),
    CandidateSpec(
        "largest_new_disclosure_share", "new_rate_words", "share", 0.02,
        lambda m: m.new_rate_words, _gate_feature,
    ),
)

_CANDIDATE_INDEX = {spec.key: i for i, spec in enumerate(CANDIDATES)}


@dataclass(frozen=True)
class FindingResult:
    key: str
    metric_key: str
    value: float
    magnitude: float


def eligible_candidates(metrics: ComparisonMetrics) -> list[FindingResult]:
    """Every candidate that survives its gate, direction filter, and
    materiality epsilon for one comparison -- the shared building block for
    both per-comparison `finding_key` selection and corpus-wide
    `discovery_items` ranking."""
    survivors: list[FindingResult] = []
    for spec in CANDIDATES:
        if not spec.gate(metrics):
            continue
        value = spec.get_value(metrics)
        if value is None:
            continue
        if not spec.direction_ok(value):
            continue
        magnitude = abs(value) / spec.epsilon
        if magnitude < 1.0:
            continue
        survivors.append(FindingResult(spec.key, spec.metric_key, value, magnitude))
    return survivors


def select_findings(metrics: ComparisonMetrics) -> tuple[FindingResult | None, FindingResult | None, FindingResult | None]:
    """Primary/secondary/tertiary finding for one comparison: eligible
    candidates sorted by descending magnitude, fixed-order tie-break,
    `None` for any slot beyond how many actually survived -- never
    zero-filled or arbitrarily backfilled."""
    survivors = sorted(
        eligible_candidates(metrics), key=lambda f: (-f.magnitude, _CANDIDATE_INDEX[f.key])
    )
    top3 = survivors[:3]
    slots: list[FindingResult | None] = list(top3) + [None] * (3 - len(top3))
    return slots[0], slots[1], slots[2]

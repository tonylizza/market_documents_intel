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
# Keys are stable identifiers (URLs, stored finding keys), not product copy:
# `largest_negative_tone_shift` is presented as "Net tone decline" since
# Track 7F.9 without renaming the key.
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

# Track 7F.9 (frozen in docs/discover-metrics-methodology-consolidation-
# 7f8.md, Sections 9-10 and 21): discovery types with no CandidateSpec -- they
# are never ranked and never selected as a comparison finding. This is a
# "methodology not currently published / under review" state, never a claim
# that no change occurred. The value is the documented reason.
DISABLED_CANDIDATE_KEYS: dict[str, str] = {
    "largest_overall_change": (
        "Disclosure-change score gate fails on alignment-confidence share and similarity-disagreement "
        "rules pending upstream alignment-quality work (7F.8 Section 12)."
    ),
    "largest_new_disclosure_share": (
        "Shares the failing feature-quality gate of the disclosure-change score (7F.8 Sections 12, 21)."
    ),
    "largest_risk_introduction": (
        "NEW-passage attribution is unreliable (moved passages, alignment misses); needs a moved-content "
        "guard (7F.8 Section 9)."
    ),
    "largest_risk_removal": (
        "REMOVED-passage attribution is unreliable (moved passages, alignment misses); needs a moved-content "
        "guard (7F.8 Section 9)."
    ),
}


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
    # Track 7F.4: M3 (primary Discover ranking/materiality metric for
    # financial-condition shifts) and M6b (supporting detail only, never a
    # ranking candidate). `financial_condition_language_change` above (M1)
    # stays populated but is no longer used by any CandidateSpec.
    financial_condition_share_change: float | None
    financial_condition_topic_mix_change: float | None
    # Track 7F.7a.1: M3-G (primary Discover ranking/materiality metric for
    # governance shifts) and M6-G (supporting detail only, never a ranking
    # candidate). `governance_language_change` above (M1-G) stays populated
    # but is no longer used by any CandidateSpec.
    governance_share_change: float | None
    governance_topic_mix_change: float | None
    # Track 7F.9: C_min topic change -- the primary Discover ranking/
    # materiality metric for financial-condition, governance, and
    # uncertainty (M3/M3-G and M1 are supporting detail only).
    financial_condition_topic_change: float | None
    governance_topic_change: float | None
    uncertainty_topic_change: float | None
    report_side_quality_ok: bool
    report_side_primary_eligible: bool
    alignment_change_quality_ok: bool
    alignment_change_primary_eligible: bool

    new_rate_words: float | None


# `_gate_feature`/`_gate_alignment_change` currently gate no CandidateSpec
# (every type they gated is in `DISABLED_CANDIDATE_KEYS`); retained as the
# documented gates those types return to once re-enabled.
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


# Track 7F.9: the four published report-side metrics under the frozen
# 7F.8/7F.8a methodology. No evidence gate -- the alignment-unit diagnostics
# are supporting detail only. Specs for `DISABLED_CANDIDATE_KEYS` are
# deliberately absent (not merely thresholded to zero).
CANDIDATES: tuple[CandidateSpec, ...] = (
    CandidateSpec(
        "largest_uncertainty_increase", "uncertainty_topic_change", "rate_per_1000_words", 0.75,
        lambda m: m.uncertainty_topic_change, _gate_report_side, lambda v: v > 0,
    ),
    CandidateSpec(
        # Net tone decline: formula unchanged, threshold 2.25, decline only.
        "largest_negative_tone_shift", "net_tone_change", "rate_per_1000_words", 2.25,
        lambda m: m.net_tone_change, _gate_report_side, lambda v: v < 0,
    ),
    CandidateSpec(
        "largest_governance_shift", "governance_topic_change", "rate_per_1000_words", 0.25,
        lambda m: m.governance_topic_change, _gate_report_side,
    ),
    CandidateSpec(
        "largest_financial_condition_shift", "financial_condition_topic_change", "rate_per_1000_words", 0.25,
        lambda m: m.financial_condition_topic_change, _gate_report_side,
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

"""Language-signal-result quality diagnostics and primary-analysis
eligibility.

Milestone 6 recalibration: the original single blended `assess_language_
quality` conflated two genuinely different kinds of trustworthiness --
confidence in report-level lexical measurements (category counts/rates, net
tone, custom-taxonomy rates) versus confidence in exact passage-to-passage
attribution (NEW/REMOVED language, SUBSTANTIALLY_MODIFIED deltas). The
calibration audit found that alignment confidence share is dominated (~83%
of NEEDS_REVIEW rows) by candidate-collision detection -- duplicate/
boilerplate content that is *non-unique*, not *wrong* -- and that gating
report-side rates on it discarded ~70% of the corpus for no analytical
reason (report-side rates only ever sum words/hits per side; they never
required a proven one-to-one correspondence in the first place).

This module now produces two independent assessments:

- `assess_report_side_quality` / `ReportSideQualityInputs`: gates on
  lineage/coverage/dictionary-availability facts only. Never takes
  alignment confidence, collision, or margin as input -- there is no such
  field on `ReportSideQualityInputs`, enforced at the type level the same
  way the original module enforced "no language-direction input".
- `assess_alignment_change_quality` / `AlignmentChangeQualityInputs`: gates
  on alignment confidence/ambiguity/collision-share, since NEW/REMOVED
  attribution genuinely requires a trustworthy correspondence.

Every threshold comes from `FinancialLanguageConfig`. Direction of language
change is still never a quality input, in either layer.
"""

from dataclasses import dataclass

from market_documents.models.enums import AlignmentRunStatus, FeatureQuality, LanguageSignalQuality
from market_documents.services.financial_language_config import FINANCIAL_LANGUAGE_CONFIG, FinancialLanguageConfig

# Strictness ordering, most conservative first -- used to compute the
# deprecated composite `language_signal_quality` field (see
# `combine_quality_for_deprecated_composite`).
_QUALITY_STRICTNESS = (
    LanguageSignalQuality.FAILED,
    LanguageSignalQuality.NEEDS_REVIEW,
    LanguageSignalQuality.USABLE,
    LanguageSignalQuality.GOOD,
)


@dataclass(frozen=True)
class ReportSideQualityInputs:
    """Everything `assess_report_side_quality` may consider. Deliberately
    has no alignment-confidence, collision, margin, or uniqueness field --
    report-side rates never depend on exact passage correspondence."""

    is_transition: bool
    irregular_gap: bool
    primary_narrative_word_coverage_earlier: float | None
    primary_narrative_word_coverage_later: float | None
    dictionary_match_rate_earlier: float | None
    dictionary_match_rate_later: float | None


@dataclass(frozen=True)
class QualityAssessment:
    quality: LanguageSignalQuality
    warning_reasons: str | None
    primary_eligible: bool
    exclusion_reasons: str | None


def assess_report_side_quality(
    inputs: ReportSideQualityInputs, config: FinancialLanguageConfig = FINANCIAL_LANGUAGE_CONFIG
) -> QualityAssessment:
    """Report-side quality depends only on: current valid lineage (assumed --
    a `ReportPairLanguageFeatures` row only ever exists for a successful
    current run), primary-narrative word coverage, dictionary coverage, and
    reporting-gap policy. Upstream `FeatureQuality` is deliberately NOT an
    input here: report-side lexical rates are sums over the primary-
    narrative population and do not depend on the Milestone 3 disclosure-
    change feature computation whose quality that enum describes (contrast
    with `assess_alignment_change_quality`, which does use it)."""
    reasons: list[str] = []
    # Quality-affecting warnings (GOOD -> USABLE), distinct from
    # `context_notes` below (recorded for the reader, but never change the
    # quality verdict on their own).
    informational: list[str] = []
    context_notes: list[str] = []

    if inputs.irregular_gap and not inputs.is_transition:
        reasons.append("irregular reporting gap: unexplained, not a flagged transition period")
    elif inputs.irregular_gap:
        context_notes.append("irregular gap on an approved transition-period pair")

    for label, coverage in (
        ("earlier", inputs.primary_narrative_word_coverage_earlier),
        ("later", inputs.primary_narrative_word_coverage_later),
    ):
        if coverage is not None and coverage < config.minimum_primary_narrative_word_coverage:
            reasons.append(
                f"{label} primary-narrative word coverage {coverage:.2f} below threshold "
                f"({config.minimum_primary_narrative_word_coverage})"
            )

    for label, rate in (
        ("earlier", inputs.dictionary_match_rate_earlier),
        ("later", inputs.dictionary_match_rate_later),
    ):
        if rate is None:
            continue
        if rate < config.dictionary_match_rate_anomalous_threshold:
            reasons.append(
                f"{label} dictionary match rate {rate:.3f} is anomalously low "
                f"(< {config.dictionary_match_rate_anomalous_threshold})"
            )
        elif rate < config.dictionary_match_rate_borderline_threshold:
            informational.append(
                f"{label} dictionary match rate {rate:.3f} is borderline "
                f"(< {config.dictionary_match_rate_borderline_threshold}) -- plausible but worth spot-checking"
            )

    needs_review = bool(reasons)
    if needs_review:
        quality = LanguageSignalQuality.NEEDS_REVIEW
    elif informational:
        quality = LanguageSignalQuality.USABLE
    else:
        quality = LanguageSignalQuality.GOOD

    primary_eligible = (
        quality in (LanguageSignalQuality.GOOD, LanguageSignalQuality.USABLE)
        and not inputs.is_transition
        and not inputs.irregular_gap
    )
    exclusion_parts: list[str] = []
    if not primary_eligible:
        if quality not in (LanguageSignalQuality.GOOD, LanguageSignalQuality.USABLE):
            exclusion_parts.append(f"report-side quality is {quality.value}")
        if inputs.is_transition:
            exclusion_parts.append("transition-period pair excluded from primary analysis by default")
        if inputs.irregular_gap:
            exclusion_parts.append("irregular reporting gap excluded from primary analysis by default")

    all_notes = reasons + informational + context_notes
    return QualityAssessment(
        quality=quality,
        warning_reasons="; ".join(all_notes) if all_notes else None,
        primary_eligible=primary_eligible,
        exclusion_reasons="; ".join(exclusion_parts) if exclusion_parts else None,
    )


@dataclass(frozen=True)
class AlignmentChangeQualityInputs:
    """Everything `assess_alignment_change_quality` may consider -- unlike
    `ReportSideQualityInputs`, alignment confidence/ambiguity/collision are
    legitimate inputs here, since NEW/REMOVED attribution and
    SUBSTANTIALLY_MODIFIED deltas require a trustworthy correspondence."""

    alignment_run_status: AlignmentRunStatus
    alignment_review_reason: str | None
    feature_quality: FeatureQuality
    is_transition: bool
    irregular_gap: bool
    ambiguous_word_share: float | None
    collision_flagged_word_share: float | None
    unmatched_word_share: float | None


def assess_alignment_change_quality(
    inputs: AlignmentChangeQualityInputs, config: FinancialLanguageConfig = FINANCIAL_LANGUAGE_CONFIG
) -> QualityAssessment:
    """Alignment-change quality depends on alignment confidence/ambiguity/
    collision, and (unlike report-side quality) does propagate upstream
    `FeatureQuality`: NEW/REMOVED/SUBSTANTIALLY_MODIFIED attribution
    fundamentally reuses the same alignment lineage that Milestone 3's
    feature-quality assessment evaluates. A collision-flagged share above
    `collision_flagged_word_share_warning_threshold` is a WARNING, never an
    automatic NEEDS_REVIEW/mismatch on its own -- collision means
    *non-unique*, not *wrong* (see module docstring); only a share above
    `collision_flagged_word_share_needs_review_threshold` (a genuine
    corpus-relative outlier) triggers NEEDS_REVIEW. `unmatched_word_share`
    (NEW+REMOVED) is informational only -- high turnover is a legitimate
    report characteristic."""
    if inputs.feature_quality == FeatureQuality.FAILED:
        reason = "upstream feature quality is FAILED"
        return QualityAssessment(
            quality=LanguageSignalQuality.FAILED, warning_reasons=reason, primary_eligible=False, exclusion_reasons=reason
        )

    reasons: list[str] = []
    informational: list[str] = []
    context_notes: list[str] = []

    weak_source = (
        inputs.alignment_run_status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS
        or inputs.feature_quality == FeatureQuality.NEEDS_REVIEW
    )
    if inputs.alignment_run_status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS:
        informational.append(f"alignment run completed with warnings: {inputs.alignment_review_reason or 'unspecified'}")
    if inputs.feature_quality == FeatureQuality.NEEDS_REVIEW:
        informational.append("upstream feature quality is NEEDS_REVIEW")

    if inputs.irregular_gap and not inputs.is_transition:
        reasons.append("irregular reporting gap: unexplained, not a flagged transition period")
    elif inputs.irregular_gap:
        context_notes.append("irregular gap on an approved transition-period pair")

    if inputs.ambiguous_word_share is not None and inputs.ambiguous_word_share > config.ambiguous_word_share_threshold:
        reasons.append(
            f"ambiguous word share {inputs.ambiguous_word_share:.2f} exceeds tolerance "
            f"({config.ambiguous_word_share_threshold}) -- genuine non-correspondence, not just non-uniqueness"
        )

    if inputs.collision_flagged_word_share is not None:
        share = inputs.collision_flagged_word_share
        if share > config.collision_flagged_word_share_needs_review_threshold:
            reasons.append(
                f"collision-flagged word share {share:.2f} exceeds tolerance "
                f"({config.collision_flagged_word_share_needs_review_threshold})"
            )
        elif share > config.collision_flagged_word_share_warning_threshold:
            informational.append(
                f"collision-flagged word share {share:.2f} above "
                f"{config.collision_flagged_word_share_warning_threshold} -- non-unique correspondence "
                "(duplicate/boilerplate content), not a demonstrated mismatch"
            )

    if inputs.unmatched_word_share is not None and inputs.unmatched_word_share > config.unmatched_word_share_warning_threshold:
        informational.append(
            f"unmatched word share {inputs.unmatched_word_share:.2f} above "
            f"{config.unmatched_word_share_warning_threshold} -- high content turnover, not necessarily a defect"
        )

    needs_review = bool(reasons)
    if needs_review:
        quality = LanguageSignalQuality.NEEDS_REVIEW
    elif weak_source or informational:
        quality = LanguageSignalQuality.USABLE
    else:
        quality = LanguageSignalQuality.GOOD

    primary_eligible = (
        quality in (LanguageSignalQuality.GOOD, LanguageSignalQuality.USABLE)
        and not inputs.is_transition
        and not inputs.irregular_gap
    )
    exclusion_parts: list[str] = []
    if not primary_eligible:
        if quality not in (LanguageSignalQuality.GOOD, LanguageSignalQuality.USABLE):
            exclusion_parts.append(f"alignment-change quality is {quality.value}")
        if inputs.is_transition:
            exclusion_parts.append("transition-period pair excluded from primary analysis by default")
        if inputs.irregular_gap:
            exclusion_parts.append("irregular reporting gap excluded from primary analysis by default")

    all_notes = reasons + informational + context_notes
    return QualityAssessment(
        quality=quality,
        warning_reasons="; ".join(all_notes) if all_notes else None,
        primary_eligible=primary_eligible,
        exclusion_reasons="; ".join(exclusion_parts) if exclusion_parts else None,
    )


def combine_quality_for_deprecated_composite(
    report_side: QualityAssessment, alignment_change: QualityAssessment
) -> QualityAssessment:
    """Builds the deprecated composite `language_signal_quality`/
    `primary_eligible`/`warning_reasons`/`exclusion_reasons` fields from the
    two independent assessments: quality is the stricter (more
    conservative) of the two, `primary_eligible` requires both, and reasons
    from each layer are kept but prefixed so a reader can tell which layer
    they came from. This is the one place the two layers are ever merged
    back into a single value -- new code should read `report_side_*`/
    `alignment_change_*` directly instead."""
    quality = min(
        (report_side.quality, alignment_change.quality), key=lambda q: _QUALITY_STRICTNESS.index(q)
    )
    primary_eligible = report_side.primary_eligible and alignment_change.primary_eligible

    def _prefixed(prefix: str, text: str | None) -> list[str]:
        return [f"[{prefix}] {part}" for part in text.split("; ")] if text else []

    warning_parts = _prefixed("report-side", report_side.warning_reasons) + _prefixed(
        "alignment-change", alignment_change.warning_reasons
    )
    exclusion_parts = _prefixed("report-side", report_side.exclusion_reasons) + _prefixed(
        "alignment-change", alignment_change.exclusion_reasons
    )
    return QualityAssessment(
        quality=quality,
        warning_reasons="; ".join(warning_parts) if warning_parts else None,
        primary_eligible=primary_eligible,
        exclusion_reasons="; ".join(exclusion_parts) if exclusion_parts else None,
    )

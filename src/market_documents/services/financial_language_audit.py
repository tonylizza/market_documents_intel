"""Corpus-level financial-language-signal audit rows.

Mirrors `feature_audit.py`/`structured_content_audit.py`: every field is
optional and simply blank when the corresponding data doesn't exist yet.
Produces the Milestone 6 audit CSVs: `language_dictionary_audit.csv`,
`passage_language_signal_audit.csv`, `report_pair_language_review.csv`,
`financial_language_component_summary.csv`, four population-sensitivity
CSVs (structured-content / list / table-context / currency-exposure) plus a
confidence-sensitivity CSV, `language_signal_company_summary.csv`, and
`deterministic_language_review_sample.csv`.

Sensitivity rows are recomputed in-memory from persisted `PassageLanguage
Signal`/`PassageLanguageCategoryHit` rows (mirroring `structured_content_
audit.py`'s variant A/B/C approach) rather than cached on `ReportPairLanguage
Features` -- this reproduces exactly from lineage already durable in the
database, without ever needing to rerun a build.
"""

import csv
import random
import statistics
from collections import defaultdict
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, LanguageSignalRunStatus, ReportSide
from market_documents.models.financial_language import (
    FinancialLanguageDictionary,
    LanguageSignalRun,
    PassageLanguageCategoryHit,
    PassageLanguageSignal,
    ReportPairLanguageFeatures,
)
from market_documents.models.report_pair import ReportPair
from market_documents.services.financial_language_config import CORE_CATEGORIES
from market_documents.services.financial_language_metrics import (
    SignalRowInput,
    aggregate_side,
    compute_core_category_change,
    net_tone,
    rate_change,
    safe_ratio,
)
from market_documents.services.financial_language_signals import (
    get_current_language_signal_runs_by_pair,
    get_current_pair_language_features_by_pair,
)

DEFAULT_SEED = 42
DEFAULT_PER_CATEGORY = 3


def _write_csv(rows: list, row_type: type, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(row_type)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            record = vars(row)
            writer.writerow({k: ("" if v is None else v) for k, v in record.items()})


# --------------------------------------------------------------------------
# language_dictionary_audit.csv
# --------------------------------------------------------------------------


@dataclass
class DictionaryAuditRow:
    name: str
    version: str
    source: str
    source_hash: str
    license_notes: str
    term_count: int
    created_at: str


def build_dictionary_audit_rows(session: Session) -> list[DictionaryAuditRow]:
    dictionaries = session.scalars(
        select(FinancialLanguageDictionary).order_by(FinancialLanguageDictionary.name, FinancialLanguageDictionary.created_at)
    ).all()
    return [
        DictionaryAuditRow(
            name=d.name,
            version=d.version,
            source=d.source,
            source_hash=d.source_hash,
            license_notes=d.license_notes,
            term_count=d.term_count,
            created_at=d.created_at.isoformat(),
        )
        for d in dictionaries
    ]


def write_dictionary_audit_csv(rows: list[DictionaryAuditRow], output_path: Path) -> None:
    _write_csv(rows, DictionaryAuditRow, output_path)


# --------------------------------------------------------------------------
# passage_language_signal_audit.csv / report_pair_language_review.csv /
# financial_language_component_summary.csv / language_signal_company_summary.csv
# --------------------------------------------------------------------------


@dataclass
class LanguageRunAuditRow:
    ticker: str
    report_pair_id: str
    status: str | None
    language_signal_quality: str | None
    primary_eligible: bool | None
    net_tone_earlier: float | None
    net_tone_later: float | None
    net_tone_change: float | None
    uncertainty_rate_change: float | None
    negative_rate_change: float | None
    positive_rate_change: float | None
    risk_language_introduction: float | None
    risk_language_removal: float | None
    governance_language_change: float | None
    financial_condition_language_change: float | None
    forward_looking_caution_change: float | None
    analyzed_word_coverage: float | None
    primary_narrative_coverage: float | None
    dictionary_match_rate: float | None
    configuration_hash: str | None
    warning_reasons: str | None
    exclusion_reasons: str | None


def build_language_run_audit_rows(session: Session) -> list[LanguageRunAuditRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()
    pair_ids = [p.id for p in pairs]
    current_runs = get_current_language_signal_runs_by_pair(session, pair_ids)
    features_by_pair = get_current_pair_language_features_by_pair(session, pair_ids)

    rows: list[LanguageRunAuditRow] = []
    for pair in pairs:
        run = current_runs.get(pair.id)
        feat = features_by_pair.get(pair.id)
        rows.append(
            LanguageRunAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                status=run.status.value if run else None,
                language_signal_quality=feat.language_signal_quality.value if feat else None,
                primary_eligible=feat.primary_eligible if feat else None,
                net_tone_earlier=feat.net_tone_earlier if feat else None,
                net_tone_later=feat.net_tone_later if feat else None,
                net_tone_change=feat.net_tone_change if feat else None,
                uncertainty_rate_change=feat.uncertainty_rate_change if feat else None,
                negative_rate_change=feat.negative_rate_change if feat else None,
                positive_rate_change=feat.positive_rate_change if feat else None,
                risk_language_introduction=feat.risk_language_introduction if feat else None,
                risk_language_removal=feat.risk_language_removal if feat else None,
                governance_language_change=feat.governance_language_change if feat else None,
                financial_condition_language_change=feat.financial_condition_language_change if feat else None,
                forward_looking_caution_change=feat.forward_looking_caution_change if feat else None,
                analyzed_word_coverage=feat.analyzed_word_coverage if feat else None,
                primary_narrative_coverage=feat.primary_narrative_coverage if feat else None,
                dictionary_match_rate=feat.dictionary_match_rate if feat else None,
                configuration_hash=run.configuration_hash if run else None,
                warning_reasons=run.review_reason if run else None,
                exclusion_reasons=feat.exclusion_reasons if feat else None,
            )
        )
    return rows


def write_language_run_audit_csv(rows: list[LanguageRunAuditRow], output_path: Path) -> None:
    _write_csv(rows, LanguageRunAuditRow, output_path)


def build_language_review_rows(session: Session) -> list[LanguageRunAuditRow]:
    """Pairs needing manual attention: not yet built, mechanically failed or
    warned, NEEDS_REVIEW/FAILED quality, or excluded from primary ranking."""
    rows = build_language_run_audit_rows(session)
    return [
        row
        for row in rows
        if row.status is None
        or row.status in ("FAILED", "COMPLETED_WITH_WARNINGS")
        or row.language_signal_quality in ("NEEDS_REVIEW", "FAILED")
        or row.primary_eligible is False
    ]


def write_language_review_csv(rows: list[LanguageRunAuditRow], output_path: Path) -> None:
    _write_csv(rows, LanguageRunAuditRow, output_path)


@dataclass
class ComponentSummaryRow:
    metric: str
    count: int
    minimum: float | None
    median: float | None
    maximum: float | None
    mean: float | None


_SUMMARY_METRICS = [
    "net_tone_earlier",
    "net_tone_later",
    "net_tone_change",
    "uncertainty_rate_change",
    "negative_rate_change",
    "positive_rate_change",
    "litigious_rate_change",
    "constraining_rate_change",
    "strong_modal_rate_change",
    "weak_modal_rate_change",
    "risk_language_introduction",
    "risk_language_removal",
    "governance_language_change",
    "financial_condition_language_change",
    "forward_looking_caution_change",
    "analyzed_word_coverage",
    "primary_narrative_coverage",
    "dictionary_match_rate",
]


def build_component_summary_rows(session: Session) -> list[ComponentSummaryRow]:
    pair_ids = list(session.scalars(select(ReportPair.id)).all())
    features_by_pair = get_current_pair_language_features_by_pair(session, pair_ids)
    features = list(features_by_pair.values())

    rows: list[ComponentSummaryRow] = []
    for metric in _SUMMARY_METRICS:
        values = [v for v in (getattr(f, metric) for f in features) if v is not None]
        rows.append(
            ComponentSummaryRow(
                metric=metric,
                count=len(values),
                minimum=min(values) if values else None,
                median=statistics.median(values) if values else None,
                maximum=max(values) if values else None,
                mean=statistics.mean(values) if values else None,
            )
        )
    return rows


def write_component_summary_csv(rows: list[ComponentSummaryRow], output_path: Path) -> None:
    _write_csv(rows, ComponentSummaryRow, output_path)


@dataclass
class CompanySummaryRow:
    ticker: str
    pairs_current: int
    pairs_primary_eligible: int
    mean_net_tone_change: float | None
    mean_uncertainty_rate_change: float | None
    mean_risk_language_introduction: float | None
    mean_governance_language_change: float | None
    mean_financial_condition_language_change: float | None
    mean_dictionary_match_rate: float | None


def build_company_summary_rows(session: Session) -> list[CompanySummaryRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pair_ids = [p.id for p in pairs]
    features_by_pair = get_current_pair_language_features_by_pair(session, pair_ids)

    by_ticker: dict[str, list[ReportPairLanguageFeatures]] = defaultdict(list)
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        if feat is not None:
            by_ticker[pair.company.ticker].append(feat)

    def _mean(feats: list[ReportPairLanguageFeatures], attr: str) -> float | None:
        values = [v for v in (getattr(f, attr) for f in feats) if v is not None]
        return statistics.mean(values) if values else None

    rows: list[CompanySummaryRow] = []
    for ticker in sorted(by_ticker):
        feats = by_ticker[ticker]
        rows.append(
            CompanySummaryRow(
                ticker=ticker,
                pairs_current=len(feats),
                pairs_primary_eligible=sum(1 for f in feats if f.primary_eligible),
                mean_net_tone_change=_mean(feats, "net_tone_change"),
                mean_uncertainty_rate_change=_mean(feats, "uncertainty_rate_change"),
                mean_risk_language_introduction=_mean(feats, "risk_language_introduction"),
                mean_governance_language_change=_mean(feats, "governance_language_change"),
                mean_financial_condition_language_change=_mean(feats, "financial_condition_language_change"),
                mean_dictionary_match_rate=_mean(feats, "dictionary_match_rate"),
            )
        )
    return rows


def write_company_summary_csv(rows: list[CompanySummaryRow], output_path: Path) -> None:
    _write_csv(rows, CompanySummaryRow, output_path)


# --------------------------------------------------------------------------
# Population/confidence sensitivity -- recomputed in-memory from persisted
# PassageLanguageSignal (+ PassageLanguageCategoryHit) rows.
# --------------------------------------------------------------------------


def _signal_rows_for_run(session: Session, language_signal_run_id) -> list[SignalRowInput]:
    signals = session.scalars(
        select(PassageLanguageSignal).where(PassageLanguageSignal.language_signal_run_id == language_signal_run_id)
    ).all()
    signal_ids = [s.id for s in signals]
    hits_by_signal: dict = defaultdict(dict)
    if signal_ids:
        hit_rows = session.scalars(
            select(PassageLanguageCategoryHit).where(PassageLanguageCategoryHit.passage_language_signal_id.in_(signal_ids))
        ).all()
        for hit in hit_rows:
            hits_by_signal[hit.passage_language_signal_id][hit.category] = (
                hits_by_signal[hit.passage_language_signal_id].get(hit.category, 0) + hit.hit_count
            )

    return [
        SignalRowInput(
            report_side=s.report_side,
            alignment_status=s.alignment_status,
            confidence=s.confidence,
            passage_word_count=s.passage_word_count,
            structured_content_category=s.structured_content_category,
            feature_eligible=s.feature_eligible,
            positive_count=s.positive_count,
            negative_count=s.negative_count,
            uncertainty_count=s.uncertainty_count,
            litigious_count=s.litigious_count,
            constraining_count=s.constraining_count,
            strong_modal_count=s.strong_modal_count,
            weak_modal_count=s.weak_modal_count,
            total_dictionary_hits=s.total_dictionary_hits,
            custom_category_hits=dict(hits_by_signal.get(s.id, {})),
        )
        for s in signals
        if s.feature_eligible and s.primary_narrative_eligible
    ]


@dataclass
class SensitivityRow:
    ticker: str
    report_pair_id: str
    baseline_net_tone_change: float | None
    variant_net_tone_change: float | None
    baseline_uncertainty_rate_change: float | None
    variant_uncertainty_rate_change: float | None
    baseline_words: float
    variant_words: float
    words_excluded: float
    pct_words_excluded: float | None


def _pair_net_tone_and_uncertainty(rows: list[SignalRowInput]) -> tuple[float | None, float | None, float]:
    earlier = aggregate_side(rows, ReportSide.EARLIER)
    later = aggregate_side(rows, ReportSide.LATER)
    positive_change = compute_core_category_change("positive", earlier, later)
    negative_change = compute_core_category_change("negative", earlier, later)
    uncertainty_change = compute_core_category_change("uncertainty", earlier, later)
    tone_change = rate_change(
        net_tone(positive_change.rate_later, negative_change.rate_later),
        net_tone(positive_change.rate_earlier, negative_change.rate_earlier),
    )
    total_words = earlier.words + later.words
    return tone_change, uncertainty_change.rate_change, total_words


def build_sensitivity_rows(
    session: Session, variant_filter: Callable[[SignalRowInput], bool]
) -> list[SensitivityRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker)
    ).all()
    pair_ids = [p.id for p in pairs]
    current_runs = get_current_language_signal_runs_by_pair(session, pair_ids)

    rows: list[SensitivityRow] = []
    for pair in pairs:
        run = current_runs.get(pair.id)
        if run is None:
            continue
        baseline_rows = _signal_rows_for_run(session, run.id)
        variant_rows = [r for r in baseline_rows if variant_filter(r)]

        baseline_tone, baseline_uncertainty, baseline_words = _pair_net_tone_and_uncertainty(baseline_rows)
        variant_tone, variant_uncertainty, variant_words = _pair_net_tone_and_uncertainty(variant_rows)
        excluded = baseline_words - variant_words
        rows.append(
            SensitivityRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                baseline_net_tone_change=baseline_tone,
                variant_net_tone_change=variant_tone,
                baseline_uncertainty_rate_change=baseline_uncertainty,
                variant_uncertainty_rate_change=variant_uncertainty,
                baseline_words=baseline_words,
                variant_words=variant_words,
                words_excluded=excluded,
                pct_words_excluded=safe_ratio(excluded, baseline_words),
            )
        )
    return rows


def write_sensitivity_csv(rows: list[SensitivityRow], output_path: Path) -> None:
    _write_csv(rows, SensitivityRow, output_path)


def build_structured_content_sensitivity_rows(session: Session) -> list[SensitivityRow]:
    """Variant excludes every non-primary-narrative structured-content
    category -- but `_signal_rows_for_run` already restricts to primary-
    narrative-eligible rows, so this variant equals baseline by construction
    and instead reports zero exclusion as a sanity check that primary
    narrative itself is already "structured-content-clean"."""
    return build_sensitivity_rows(session, lambda r: True)


def build_list_sensitivity_rows(session: Session) -> list[SensitivityRow]:
    return build_sensitivity_rows(session, lambda r: r.structured_content_category != "list_content")


def build_table_context_sensitivity_rows(session: Session) -> list[SensitivityRow]:
    return build_sensitivity_rows(session, lambda r: r.structured_content_category != "table_context")


def build_currency_exposure_sensitivity_rows(session: Session) -> list[SensitivityRow]:
    return build_sensitivity_rows(session, lambda r: r.structured_content_category != "currency_exposure_table_mixed")


def build_confidence_sensitivity_rows(session: Session) -> list[SensitivityRow]:
    """Variant restricts to HIGH/MEDIUM confidence only (drops LOW/
    NEEDS_REVIEW and, implicitly, AMBIGUOUS rows lacking a confident
    alignment) -- ambiguous-alignment sensitivity is this same filter's
    natural byproduct, since AMBIGUOUS rows are always LOW or NEEDS_REVIEW
    confidence by construction (see `passage_alignment.py`)."""
    return build_sensitivity_rows(
        session, lambda r: r.confidence in (AlignmentConfidence.HIGH, AlignmentConfidence.MEDIUM)
    )


# --------------------------------------------------------------------------
# deterministic_language_review_sample.csv
# --------------------------------------------------------------------------


@dataclass
class ReviewSampleRow:
    category: str
    ticker: str
    report_pair_id: str
    language_signal_quality: str
    primary_eligible: bool
    net_tone_change: float | None
    uncertainty_rate_change: float | None
    risk_language_introduction: float | None
    risk_language_removal: float | None
    governance_language_change: float | None
    warning_reasons: str | None
    exclusion_reasons: str | None


def _category_predicates() -> dict[str, Callable[[ReportPairLanguageFeatures], bool]]:
    return {
        "rising_negative": lambda f: (f.negative_rate_change or 0.0) > 0,
        "falling_negative": lambda f: (f.negative_rate_change or 0.0) < 0,
        "rising_uncertainty": lambda f: (f.uncertainty_rate_change or 0.0) > 0,
        "risk_introduced": lambda f: (f.risk_language_introduction or 0.0) > 0,
        "risk_removed": lambda f: (f.risk_language_removal or 0.0) > 0,
        "governance_change": lambda f: abs(f.governance_language_change or 0.0) > 0,
        "list_content_present": lambda f: f.list_content_count > 0,
        "table_context_present": lambda f: f.table_context_count > 0,
        "currency_exposure_mixed_present": lambda f: f.currency_exposure_mixed_count > 0,
        "uncertain_present": lambda f: f.uncertain_count > 0,
        "needs_review": lambda f: f.language_signal_quality.value == "NEEDS_REVIEW",
        "not_primary_eligible": lambda f: not f.primary_eligible,
    }


def build_deterministic_review_sample(
    session: Session, *, seed: int = DEFAULT_SEED, per_category: int = DEFAULT_PER_CATEGORY
) -> list[ReviewSampleRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    features_by_pair = get_current_pair_language_features_by_pair(session, list(pairs_by_id))
    if not features_by_pair:
        return []

    def _row(category: str, pair_id, feat: ReportPairLanguageFeatures) -> ReviewSampleRow:
        pair = pairs_by_id[pair_id]
        return ReviewSampleRow(
            category=category,
            ticker=pair.company.ticker,
            report_pair_id=str(pair.id),
            language_signal_quality=feat.language_signal_quality.value,
            primary_eligible=feat.primary_eligible,
            net_tone_change=feat.net_tone_change,
            uncertainty_rate_change=feat.uncertainty_rate_change,
            risk_language_introduction=feat.risk_language_introduction,
            risk_language_removal=feat.risk_language_removal,
            governance_language_change=feat.governance_language_change,
            warning_reasons=feat.warning_reasons,
            exclusion_reasons=feat.exclusion_reasons,
        )

    rows: list[ReviewSampleRow] = []
    rng = random.Random(seed)
    for category, predicate in _category_predicates().items():
        matches = [(pid, f) for pid, f in features_by_pair.items() if predicate(f)]
        matches_sorted = sorted(matches, key=lambda item: str(item[0]))
        rng.shuffle(matches_sorted)
        for pid, feat in matches_sorted[:per_category]:
            rows.append(_row(category, pid, feat))
    return rows


def write_review_sample_csv(rows: list[ReviewSampleRow], output_path: Path) -> None:
    _write_csv(rows, ReviewSampleRow, output_path)


# --------------------------------------------------------------------------
# Milestone 6 recalibration: report_side_language_quality_audit.csv /
# alignment_change_language_quality_audit.csv /
# language_quality_recalibration_comparison.csv
# --------------------------------------------------------------------------


@dataclass
class ReportSideQualityAuditRow:
    ticker: str
    report_pair_id: str
    report_side_signal_quality: str
    report_side_primary_eligible: bool
    dictionary_match_rate_earlier: float | None
    dictionary_match_rate_later: float | None
    primary_narrative_coverage: float | None
    ambiguous_words_in_report_side: float
    report_side_warning_reasons: str | None
    report_side_exclusion_reasons: str | None


def build_report_side_quality_audit_rows(session: Session) -> list[ReportSideQualityAuditRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker)
    ).all()
    features_by_pair = get_current_pair_language_features_by_pair(session, [p.id for p in pairs])
    rows = []
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        if feat is None:
            continue
        rows.append(
            ReportSideQualityAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                report_side_signal_quality=feat.report_side_signal_quality.value,
                report_side_primary_eligible=feat.report_side_primary_eligible,
                dictionary_match_rate_earlier=feat.dictionary_match_rate_earlier,
                dictionary_match_rate_later=feat.dictionary_match_rate_later,
                primary_narrative_coverage=feat.primary_narrative_coverage,
                ambiguous_words_in_report_side=feat.ambiguous_words_in_report_side,
                report_side_warning_reasons=feat.report_side_warning_reasons,
                report_side_exclusion_reasons=feat.report_side_exclusion_reasons,
            )
        )
    return rows


def write_report_side_quality_audit_csv(rows: list[ReportSideQualityAuditRow], output_path: Path) -> None:
    _write_csv(rows, ReportSideQualityAuditRow, output_path)


@dataclass
class AlignmentChangeQualityAuditRow:
    ticker: str
    report_pair_id: str
    alignment_change_signal_quality: str
    alignment_change_primary_eligible: bool
    ambiguous_alignment_share: float | None
    collision_flagged_word_share: float | None
    unmatched_word_share: float | None
    low_confidence_share: float | None
    alignment_change_analyzed_words_all: float
    alignment_change_analyzed_words_excl_ambiguous: float
    alignment_change_analyzed_words_hml: float
    alignment_change_analyzed_words_hm: float
    alignment_change_analyzed_words_h: float
    alignment_change_warning_reasons: str | None
    alignment_change_exclusion_reasons: str | None


def build_alignment_change_quality_audit_rows(session: Session) -> list[AlignmentChangeQualityAuditRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker)
    ).all()
    features_by_pair = get_current_pair_language_features_by_pair(session, [p.id for p in pairs])
    rows = []
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        if feat is None:
            continue
        rows.append(
            AlignmentChangeQualityAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                alignment_change_signal_quality=feat.alignment_change_signal_quality.value,
                alignment_change_primary_eligible=feat.alignment_change_primary_eligible,
                ambiguous_alignment_share=feat.ambiguous_alignment_share,
                collision_flagged_word_share=feat.collision_flagged_word_share,
                unmatched_word_share=feat.unmatched_word_share,
                low_confidence_share=feat.low_confidence_share,
                alignment_change_analyzed_words_all=feat.alignment_change_analyzed_words_all,
                alignment_change_analyzed_words_excl_ambiguous=feat.alignment_change_analyzed_words_excl_ambiguous,
                alignment_change_analyzed_words_hml=feat.alignment_change_analyzed_words_hml,
                alignment_change_analyzed_words_hm=feat.alignment_change_analyzed_words_hm,
                alignment_change_analyzed_words_h=feat.alignment_change_analyzed_words_h,
                alignment_change_warning_reasons=feat.alignment_change_warning_reasons,
                alignment_change_exclusion_reasons=feat.alignment_change_exclusion_reasons,
            )
        )
    return rows


def write_alignment_change_quality_audit_csv(rows: list[AlignmentChangeQualityAuditRow], output_path: Path) -> None:
    _write_csv(rows, AlignmentChangeQualityAuditRow, output_path)


@dataclass
class RecalibrationComparisonRow:
    ticker: str
    report_pair_id: str
    pre_recalibration_configuration_hash: str | None
    post_recalibration_configuration_hash: str | None
    pre_recalibration_composite_quality: str | None
    pre_recalibration_composite_primary_eligible: bool | None
    post_report_side_quality: str | None
    post_report_side_primary_eligible: bool | None
    post_alignment_change_quality: str | None
    post_alignment_change_primary_eligible: bool | None
    positive_rate_earlier_diff: float | None
    negative_rate_earlier_diff: float | None
    net_tone_change_diff: float | None
    dictionary_match_rate_diff: float | None


def _second_most_recent_successful_run(session: Session, report_pair_id) -> LanguageSignalRun | None:
    """The run immediately prior to the current one -- used to compare
    pre-/post-recalibration results for the *same* dictionary bundle
    (custom-taxonomy + Loughran-McDonald), never the original custom-
    taxonomy-only run further back in history."""
    runs = session.scalars(
        select(LanguageSignalRun)
        .where(
            LanguageSignalRun.report_pair_id == report_pair_id,
            LanguageSignalRun.status.in_(
                (LanguageSignalRunStatus.COMPLETED, LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(LanguageSignalRun.completed_at.desc())
        .limit(2)
    ).all()
    return runs[1] if len(runs) > 1 else None


def build_recalibration_comparison_rows(session: Session) -> list[RecalibrationComparisonRow]:
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker)
    ).all()
    pair_ids = [p.id for p in pairs]
    current_runs = get_current_language_signal_runs_by_pair(session, pair_ids)
    current_features = get_current_pair_language_features_by_pair(session, pair_ids)

    rows = []
    for pair in pairs:
        current_run = current_runs.get(pair.id)
        current_feat = current_features.get(pair.id)
        if current_run is None or current_feat is None:
            continue
        previous_run = _second_most_recent_successful_run(session, pair.id)
        previous_feat = (
            session.scalar(
                select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id == previous_run.id)
            )
            if previous_run is not None
            else None
        )

        def _diff(a: float | None, b: float | None) -> float | None:
            return (a - b) if a is not None and b is not None else None

        rows.append(
            RecalibrationComparisonRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                pre_recalibration_configuration_hash=previous_run.configuration_hash if previous_run else None,
                post_recalibration_configuration_hash=current_run.configuration_hash,
                pre_recalibration_composite_quality=previous_feat.language_signal_quality.value if previous_feat else None,
                pre_recalibration_composite_primary_eligible=previous_feat.primary_eligible if previous_feat else None,
                post_report_side_quality=current_feat.report_side_signal_quality.value,
                post_report_side_primary_eligible=current_feat.report_side_primary_eligible,
                post_alignment_change_quality=current_feat.alignment_change_signal_quality.value,
                post_alignment_change_primary_eligible=current_feat.alignment_change_primary_eligible,
                positive_rate_earlier_diff=_diff(
                    current_feat.positive_rate_earlier, previous_feat.positive_rate_earlier if previous_feat else None
                ),
                negative_rate_earlier_diff=_diff(
                    current_feat.negative_rate_earlier, previous_feat.negative_rate_earlier if previous_feat else None
                ),
                net_tone_change_diff=_diff(
                    current_feat.net_tone_change, previous_feat.net_tone_change if previous_feat else None
                ),
                dictionary_match_rate_diff=_diff(
                    current_feat.dictionary_match_rate, previous_feat.dictionary_match_rate if previous_feat else None
                ),
            )
        )
    return rows


def write_recalibration_comparison_csv(rows: list[RecalibrationComparisonRow], output_path: Path) -> None:
    _write_csv(rows, RecalibrationComparisonRow, output_path)

"""Research-ready financial-language-signal exports.

Mirrors `feature_export.py`: column order is fixed by each `ExportRow`'s
declaration order and must not be reordered between releases. Undefined
optional metrics are written as empty CSV cells, never fabricated zeroes.
"""

import csv
import uuid
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus
from market_documents.models.financial_language import PassageLanguageSignal, ReportPairLanguageFeatures
from market_documents.models.report_pair import ReportPair
from market_documents.services.financial_language_signals import (
    get_current_language_signal_runs_by_pair,
    get_current_pair_language_features_by_pair,
)


@dataclass
class PairExportRow:
    company_id: str
    ticker: str
    company_name: str
    report_pair_id: str
    earlier_report_id: str
    later_report_id: str
    earlier_period_end: str | None
    later_period_end: str | None

    all_passages_earlier_count: int
    all_passages_later_count: int
    all_passages_earlier_words: int
    all_passages_later_words: int
    primary_narrative_earlier_count: int
    primary_narrative_later_count: int
    primary_narrative_earlier_words: float
    primary_narrative_later_words: float
    excluded_structured_content_count: int
    excluded_structured_content_words: float
    list_content_count: int
    list_content_words: float
    table_context_count: int
    table_context_words: float
    currency_exposure_mixed_count: int
    currency_exposure_mixed_words: float
    uncertain_count: int
    uncertain_words: float

    positive_count_earlier: int
    positive_count_later: int
    positive_rate_earlier: float | None
    positive_rate_later: float | None
    positive_rate_change: float | None
    negative_count_earlier: int
    negative_count_later: int
    negative_rate_earlier: float | None
    negative_rate_later: float | None
    negative_rate_change: float | None
    uncertainty_count_earlier: int
    uncertainty_count_later: int
    uncertainty_rate_earlier: float | None
    uncertainty_rate_later: float | None
    uncertainty_rate_change: float | None
    litigious_count_earlier: int
    litigious_count_later: int
    litigious_rate_earlier: float | None
    litigious_rate_later: float | None
    litigious_rate_change: float | None
    constraining_count_earlier: int
    constraining_count_later: int
    constraining_rate_earlier: float | None
    constraining_rate_later: float | None
    constraining_rate_change: float | None
    strong_modal_count_earlier: int
    strong_modal_count_later: int
    strong_modal_rate_earlier: float | None
    strong_modal_rate_later: float | None
    strong_modal_rate_change: float | None
    weak_modal_count_earlier: int
    weak_modal_count_later: int
    weak_modal_rate_earlier: float | None
    weak_modal_rate_later: float | None
    weak_modal_rate_change: float | None

    positive_hits_new: int
    positive_hits_removed: int
    negative_hits_new: int
    negative_hits_removed: int
    uncertainty_hits_new: int
    uncertainty_hits_removed: int
    substantially_modified_positive_rate_change: float | None
    substantially_modified_negative_rate_change: float | None
    substantially_modified_uncertainty_rate_change: float | None

    net_tone_earlier: float | None
    net_tone_later: float | None
    net_tone_change: float | None
    uncertainty_intensity_change: float | None
    negative_language_introduction: float | None
    negative_language_removal: float | None
    positive_language_introduction: float | None
    positive_language_removal: float | None
    risk_language_introduction: float | None
    risk_language_removal: float | None
    forward_looking_caution_change: float | None
    governance_language_change: float | None
    financial_condition_language_change: float | None

    risk_rate_earlier: float | None
    risk_rate_later: float | None
    financial_condition_rate_earlier: float | None
    financial_condition_rate_later: float | None
    governance_rate_earlier: float | None
    governance_rate_later: float | None
    strategy_rate_earlier: float | None
    strategy_rate_later: float | None

    analyzed_word_coverage: float | None
    primary_narrative_coverage: float | None
    dictionary_match_rate: float | None
    list_content_share: float | None
    uncertain_content_share: float | None
    ambiguous_alignment_share: float | None
    low_confidence_share: float | None

    language_signal_quality: str
    primary_eligible: bool
    warning_reasons: str | None
    exclusion_reasons: str | None
    feature_run_id: str
    alignment_run_id: str
    language_signal_run_id: str
    configuration_hash: str
    generated_at: str


_PAIR_FIELDNAMES = [f.name for f in fields(PairExportRow)]


def build_pair_export_rows(session: Session, *, primary_only: bool = False) -> list[PairExportRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(joinedload(ReportPair.company), joinedload(ReportPair.earlier_report), joinedload(ReportPair.later_report))
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()
    pair_ids = [p.id for p in pairs]

    current_runs = get_current_language_signal_runs_by_pair(session, pair_ids)
    features_by_pair = get_current_pair_language_features_by_pair(session, pair_ids)
    generated_at = datetime.now(UTC).isoformat()

    rows: list[PairExportRow] = []
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        if feat is None:
            continue
        if primary_only and not feat.primary_eligible:
            continue
        run = current_runs[pair.id]
        rows.append(
            PairExportRow(
                company_id=str(pair.company_id),
                ticker=pair.company.ticker,
                company_name=pair.company.company_name,
                report_pair_id=str(pair.id),
                earlier_report_id=str(pair.earlier_report_id),
                later_report_id=str(pair.later_report_id),
                earlier_period_end=pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None,
                later_period_end=pair.later_report.period_end.isoformat() if pair.later_report.period_end else None,
                all_passages_earlier_count=feat.all_passages_earlier_count,
                all_passages_later_count=feat.all_passages_later_count,
                all_passages_earlier_words=feat.all_passages_earlier_words,
                all_passages_later_words=feat.all_passages_later_words,
                primary_narrative_earlier_count=feat.primary_narrative_earlier_count,
                primary_narrative_later_count=feat.primary_narrative_later_count,
                primary_narrative_earlier_words=feat.primary_narrative_earlier_words,
                primary_narrative_later_words=feat.primary_narrative_later_words,
                excluded_structured_content_count=feat.excluded_structured_content_count,
                excluded_structured_content_words=feat.excluded_structured_content_words,
                list_content_count=feat.list_content_count,
                list_content_words=feat.list_content_words,
                table_context_count=feat.table_context_count,
                table_context_words=feat.table_context_words,
                currency_exposure_mixed_count=feat.currency_exposure_mixed_count,
                currency_exposure_mixed_words=feat.currency_exposure_mixed_words,
                uncertain_count=feat.uncertain_count,
                uncertain_words=feat.uncertain_words,
                positive_count_earlier=feat.positive_count_earlier,
                positive_count_later=feat.positive_count_later,
                positive_rate_earlier=feat.positive_rate_earlier,
                positive_rate_later=feat.positive_rate_later,
                positive_rate_change=feat.positive_rate_change,
                negative_count_earlier=feat.negative_count_earlier,
                negative_count_later=feat.negative_count_later,
                negative_rate_earlier=feat.negative_rate_earlier,
                negative_rate_later=feat.negative_rate_later,
                negative_rate_change=feat.negative_rate_change,
                uncertainty_count_earlier=feat.uncertainty_count_earlier,
                uncertainty_count_later=feat.uncertainty_count_later,
                uncertainty_rate_earlier=feat.uncertainty_rate_earlier,
                uncertainty_rate_later=feat.uncertainty_rate_later,
                uncertainty_rate_change=feat.uncertainty_rate_change,
                litigious_count_earlier=feat.litigious_count_earlier,
                litigious_count_later=feat.litigious_count_later,
                litigious_rate_earlier=feat.litigious_rate_earlier,
                litigious_rate_later=feat.litigious_rate_later,
                litigious_rate_change=feat.litigious_rate_change,
                constraining_count_earlier=feat.constraining_count_earlier,
                constraining_count_later=feat.constraining_count_later,
                constraining_rate_earlier=feat.constraining_rate_earlier,
                constraining_rate_later=feat.constraining_rate_later,
                constraining_rate_change=feat.constraining_rate_change,
                strong_modal_count_earlier=feat.strong_modal_count_earlier,
                strong_modal_count_later=feat.strong_modal_count_later,
                strong_modal_rate_earlier=feat.strong_modal_rate_earlier,
                strong_modal_rate_later=feat.strong_modal_rate_later,
                strong_modal_rate_change=feat.strong_modal_rate_change,
                weak_modal_count_earlier=feat.weak_modal_count_earlier,
                weak_modal_count_later=feat.weak_modal_count_later,
                weak_modal_rate_earlier=feat.weak_modal_rate_earlier,
                weak_modal_rate_later=feat.weak_modal_rate_later,
                weak_modal_rate_change=feat.weak_modal_rate_change,
                positive_hits_new=feat.positive_hits_new,
                positive_hits_removed=feat.positive_hits_removed,
                negative_hits_new=feat.negative_hits_new,
                negative_hits_removed=feat.negative_hits_removed,
                uncertainty_hits_new=feat.uncertainty_hits_new,
                uncertainty_hits_removed=feat.uncertainty_hits_removed,
                substantially_modified_positive_rate_change=feat.substantially_modified_positive_rate_change,
                substantially_modified_negative_rate_change=feat.substantially_modified_negative_rate_change,
                substantially_modified_uncertainty_rate_change=feat.substantially_modified_uncertainty_rate_change,
                net_tone_earlier=feat.net_tone_earlier,
                net_tone_later=feat.net_tone_later,
                net_tone_change=feat.net_tone_change,
                uncertainty_intensity_change=feat.uncertainty_intensity_change,
                negative_language_introduction=feat.negative_language_introduction,
                negative_language_removal=feat.negative_language_removal,
                positive_language_introduction=feat.positive_language_introduction,
                positive_language_removal=feat.positive_language_removal,
                risk_language_introduction=feat.risk_language_introduction,
                risk_language_removal=feat.risk_language_removal,
                forward_looking_caution_change=feat.forward_looking_caution_change,
                governance_language_change=feat.governance_language_change,
                financial_condition_language_change=feat.financial_condition_language_change,
                risk_rate_earlier=feat.risk_rate_earlier,
                risk_rate_later=feat.risk_rate_later,
                financial_condition_rate_earlier=feat.financial_condition_rate_earlier,
                financial_condition_rate_later=feat.financial_condition_rate_later,
                governance_rate_earlier=feat.governance_rate_earlier,
                governance_rate_later=feat.governance_rate_later,
                strategy_rate_earlier=feat.strategy_rate_earlier,
                strategy_rate_later=feat.strategy_rate_later,
                analyzed_word_coverage=feat.analyzed_word_coverage,
                primary_narrative_coverage=feat.primary_narrative_coverage,
                dictionary_match_rate=feat.dictionary_match_rate,
                list_content_share=feat.list_content_share,
                uncertain_content_share=feat.uncertain_content_share,
                ambiguous_alignment_share=feat.ambiguous_alignment_share,
                low_confidence_share=feat.low_confidence_share,
                language_signal_quality=feat.language_signal_quality.value,
                primary_eligible=feat.primary_eligible,
                warning_reasons=feat.warning_reasons,
                exclusion_reasons=feat.exclusion_reasons,
                feature_run_id=str(run.feature_run_id),
                alignment_run_id=str(run.alignment_run_id),
                language_signal_run_id=str(run.id),
                configuration_hash=run.configuration_hash,
                generated_at=generated_at,
            )
        )
    return rows


def write_pair_export_csv(rows: list[PairExportRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PAIR_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            record = vars(row)
            writer.writerow({k: ("" if v is None else v) for k, v in record.items()})


# --------------------------------------------------------------------------
# Passage-level export
# --------------------------------------------------------------------------


@dataclass
class PassageExportRow:
    ticker: str
    report_pair_id: str
    language_signal_run_id: str
    passage_id: str
    passage_alignment_id: str
    report_side: str
    alignment_status: str
    confidence: str
    passage_type: str
    passage_word_count: int
    structured_content_category: str | None
    primary_narrative_eligible: bool
    feature_eligible: bool
    positive_count: int
    negative_count: int
    uncertainty_count: int
    litigious_count: int
    constraining_count: int
    strong_modal_count: int
    weak_modal_count: int
    negated_hit_count: int
    total_dictionary_hits: int
    category_hit_count: int


_PASSAGE_FIELDNAMES = [f.name for f in fields(PassageExportRow)]


def build_passage_export_rows(
    session: Session,
    *,
    ticker: str | None = None,
    pair_id: uuid.UUID | None = None,
    alignment_status: AlignmentStatus | None = None,
    confidence: AlignmentConfidence | None = None,
    category: str | None = None,
) -> list[PassageExportRow]:
    """One row per current `PassageLanguageSignal` (across every pair's
    current successful `LanguageSignalRun`), with optional filters -- never
    includes passage text."""
    pairs = session.scalars(
        select(ReportPair).options(joinedload(ReportPair.company)).join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    current_runs = get_current_language_signal_runs_by_pair(session, list(pairs_by_id))
    run_id_to_pair_id = {run.id: pid for pid, run in current_runs.items()}
    if not run_id_to_pair_id:
        return []

    query = select(PassageLanguageSignal).where(PassageLanguageSignal.language_signal_run_id.in_(list(run_id_to_pair_id)))
    if alignment_status is not None:
        query = query.where(PassageLanguageSignal.alignment_status == alignment_status)
    if confidence is not None:
        query = query.where(PassageLanguageSignal.confidence == confidence)
    if category is not None:
        query = query.where(PassageLanguageSignal.structured_content_category == category)

    signals = session.scalars(query).all()

    rows: list[PassageExportRow] = []
    for signal in signals:
        pair_id_for_signal = run_id_to_pair_id.get(signal.language_signal_run_id)
        pair = pairs_by_id.get(pair_id_for_signal)
        if pair is None:
            continue
        if pair_id is not None and pair.id != pair_id:
            continue
        if ticker is not None and pair.company.ticker.upper() != ticker.upper():
            continue
        rows.append(
            PassageExportRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                language_signal_run_id=str(signal.language_signal_run_id),
                passage_id=str(signal.passage_id),
                passage_alignment_id=str(signal.passage_alignment_id),
                report_side=signal.report_side.value,
                alignment_status=signal.alignment_status.value,
                confidence=signal.confidence.value,
                passage_type=signal.passage_type.value,
                passage_word_count=signal.passage_word_count,
                structured_content_category=signal.structured_content_category,
                primary_narrative_eligible=signal.primary_narrative_eligible,
                feature_eligible=signal.feature_eligible,
                positive_count=signal.positive_count,
                negative_count=signal.negative_count,
                uncertainty_count=signal.uncertainty_count,
                litigious_count=signal.litigious_count,
                constraining_count=signal.constraining_count,
                strong_modal_count=signal.strong_modal_count,
                weak_modal_count=signal.weak_modal_count,
                negated_hit_count=signal.negated_hit_count,
                total_dictionary_hits=signal.total_dictionary_hits,
                category_hit_count=signal.category_hit_count,
            )
        )
    return rows


def write_passage_export_csv(rows: list[PassageExportRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_PASSAGE_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            record = vars(row)
            writer.writerow({k: ("" if v is None else v) for k, v in record.items()})

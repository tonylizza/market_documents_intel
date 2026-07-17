"""Research-ready pair-level disclosure-change feature export.

One row per ReportPair with a current successful `ReportPairFeatures`
result. Column order is fixed by `_FIELDNAMES` (derived from `ExportRow`'s
declaration order) and must not be reordered between releases -- consumers
depend on stable columns for downstream statistical analysis. Undefined
optional metrics are written as empty CSV cells, never fabricated zeroes.
"""

import csv
from dataclasses import dataclass, fields
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.feature import ReportPairFeatures
from market_documents.models.report_pair import ReportPair
from market_documents.services.feature_extraction import (
    get_current_feature_runs_by_pair,
    get_current_report_pair_features_by_pair,
)


@dataclass
class ExportRow:
    # --- Identifiers ---
    company_id: str
    ticker: str
    company_name: str
    report_pair_id: str
    earlier_report_id: str
    later_report_id: str

    # --- Time ---
    earlier_period_end: str | None
    later_period_end: str | None
    reporting_gap_months: int
    transition_report: bool
    irregular_gap: bool

    # --- Document-level metrics ---
    document_cosine_similarity: float | None
    document_bigram_jaccard: float | None
    document_edit_similarity: float | None
    document_diff_similarity: float | None
    document_cosine_change: float | None
    document_bigram_jaccard_change: float | None
    document_edit_similarity_change: float | None
    document_diff_similarity_change: float | None
    document_word_change_ratio: float | None
    document_word_change_ratio_abs: float | None
    document_metric_disagreement_spread: float | None
    document_quality: str | None
    document_primary_eligible: bool | None

    # --- Passage outcome counts (all-passage / raw) ---
    earlier_passage_count: int
    later_passage_count: int
    aligned_passage_count: int
    unchanged_count: int
    lightly_modified_count: int
    substantially_modified_count: int
    new_count: int
    removed_count: int
    ambiguous_count: int

    # --- Passage outcome word totals (all-passage / raw) ---
    earlier_word_count: int
    later_word_count: int
    unchanged_words: float
    lightly_modified_words: float
    substantially_modified_words: float
    new_words: float
    removed_words: float
    ambiguous_words: float

    # --- Feature-eligible passage counts and word-weighted rates ---
    eligible_earlier_passage_count: int
    eligible_later_passage_count: int
    eligible_aligned_passage_count: int
    eligible_unchanged_count: int
    eligible_lightly_modified_count: int
    eligible_substantially_modified_count: int
    eligible_new_count: int
    eligible_removed_count: int
    eligible_ambiguous_count: int
    unchanged_rate_count: float | None
    lightly_modified_rate_count: float | None
    substantially_modified_rate_count: float | None
    new_rate_count: float | None
    removed_rate_count: float | None
    ambiguous_rate_count: float | None
    unchanged_rate_words: float | None
    lightly_modified_rate_words: float | None
    substantially_modified_rate_words: float | None
    new_rate_words: float | None
    removed_rate_words: float | None
    ambiguous_rate_words: float | None

    # --- Excluded fragment diagnostics ---
    excluded_low_information_count: int
    excluded_low_information_words: float
    excluded_heading_fragment_count: int
    excluded_heading_fragment_words: float
    heading_fragment_share_earlier: float | None
    heading_fragment_share_later: float | None

    # --- Coverage ---
    embedded_coverage_earlier: float | None
    embedded_coverage_later: float | None
    skipped_embedding_count_earlier: int
    skipped_embedding_count_later: int
    alignment_coverage_count: float | None
    alignment_coverage_words: float | None
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    needs_review_confidence_count: int
    high_confidence_share: float | None
    review_required_share: float | None

    # --- Signals ---
    disclosure_change_score: float | None
    score_version: str
    score_unchanged_component: float | None
    score_lightly_modified_component: float | None
    score_substantially_modified_component: float | None
    score_new_component: float | None
    score_removed_component: float | None
    score_ambiguous_component: float | None

    # --- Quality / provenance ---
    feature_quality: str
    primary_eligible: bool
    warning_reasons: str | None
    exclusion_reasons: str | None
    similarity_run_id: str
    alignment_run_id: str
    feature_run_id: str
    configuration_hash: str
    generated_at: str


_FIELDNAMES = [f.name for f in fields(ExportRow)]


def build_export_rows(session: Session, *, primary_only: bool = False) -> list[ExportRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(
            joinedload(ReportPair.company),
            joinedload(ReportPair.earlier_report),
            joinedload(ReportPair.later_report),
        )
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()
    pair_ids = [p.id for p in pairs]

    current_runs = get_current_feature_runs_by_pair(session, pair_ids)
    features_by_pair = get_current_report_pair_features_by_pair(session, pair_ids)
    generated_at = datetime.now(UTC).isoformat()

    rows: list[ExportRow] = []
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        if feat is None:
            continue
        if primary_only and not feat.primary_eligible:
            continue
        run = current_runs[pair.id]
        rows.append(
            ExportRow(
                company_id=str(pair.company_id),
                ticker=pair.company.ticker,
                company_name=pair.company.company_name,
                report_pair_id=str(pair.id),
                earlier_report_id=str(pair.earlier_report_id),
                later_report_id=str(pair.later_report_id),
                earlier_period_end=(
                    pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None
                ),
                later_period_end=(
                    pair.later_report.period_end.isoformat() if pair.later_report.period_end else None
                ),
                reporting_gap_months=feat.reporting_gap_months,
                transition_report=feat.transition_report,
                irregular_gap=feat.irregular_gap,
                document_cosine_similarity=feat.document_cosine_similarity,
                document_bigram_jaccard=feat.document_bigram_jaccard,
                document_edit_similarity=feat.document_edit_similarity,
                document_diff_similarity=feat.document_diff_similarity,
                document_cosine_change=feat.document_cosine_change,
                document_bigram_jaccard_change=feat.document_bigram_jaccard_change,
                document_edit_similarity_change=feat.document_edit_similarity_change,
                document_diff_similarity_change=feat.document_diff_similarity_change,
                document_word_change_ratio=feat.document_word_change_ratio,
                document_word_change_ratio_abs=feat.document_word_change_ratio_abs,
                document_metric_disagreement_spread=feat.document_metric_disagreement_spread,
                document_quality=feat.document_quality.value if feat.document_quality else None,
                document_primary_eligible=feat.document_primary_eligible,
                earlier_passage_count=feat.earlier_passage_count,
                later_passage_count=feat.later_passage_count,
                aligned_passage_count=feat.aligned_passage_count,
                unchanged_count=feat.unchanged_count,
                lightly_modified_count=feat.lightly_modified_count,
                substantially_modified_count=feat.substantially_modified_count,
                new_count=feat.new_count,
                removed_count=feat.removed_count,
                ambiguous_count=feat.ambiguous_count,
                earlier_word_count=feat.earlier_word_count,
                later_word_count=feat.later_word_count,
                unchanged_words=feat.unchanged_words,
                lightly_modified_words=feat.lightly_modified_words,
                substantially_modified_words=feat.substantially_modified_words,
                new_words=feat.new_words,
                removed_words=feat.removed_words,
                ambiguous_words=feat.ambiguous_words,
                eligible_earlier_passage_count=feat.eligible_earlier_passage_count,
                eligible_later_passage_count=feat.eligible_later_passage_count,
                eligible_aligned_passage_count=feat.eligible_aligned_passage_count,
                eligible_unchanged_count=feat.eligible_unchanged_count,
                eligible_lightly_modified_count=feat.eligible_lightly_modified_count,
                eligible_substantially_modified_count=feat.eligible_substantially_modified_count,
                eligible_new_count=feat.eligible_new_count,
                eligible_removed_count=feat.eligible_removed_count,
                eligible_ambiguous_count=feat.eligible_ambiguous_count,
                unchanged_rate_count=feat.unchanged_rate_count,
                lightly_modified_rate_count=feat.lightly_modified_rate_count,
                substantially_modified_rate_count=feat.substantially_modified_rate_count,
                new_rate_count=feat.new_rate_count,
                removed_rate_count=feat.removed_rate_count,
                ambiguous_rate_count=feat.ambiguous_rate_count,
                unchanged_rate_words=feat.unchanged_rate_words,
                lightly_modified_rate_words=feat.lightly_modified_rate_words,
                substantially_modified_rate_words=feat.substantially_modified_rate_words,
                new_rate_words=feat.new_rate_words,
                removed_rate_words=feat.removed_rate_words,
                ambiguous_rate_words=feat.ambiguous_rate_words,
                excluded_low_information_count=feat.excluded_low_information_count,
                excluded_low_information_words=feat.excluded_low_information_words,
                excluded_heading_fragment_count=feat.excluded_heading_fragment_count,
                excluded_heading_fragment_words=feat.excluded_heading_fragment_words,
                heading_fragment_share_earlier=feat.heading_fragment_share_earlier,
                heading_fragment_share_later=feat.heading_fragment_share_later,
                embedded_coverage_earlier=feat.embedded_coverage_earlier,
                embedded_coverage_later=feat.embedded_coverage_later,
                skipped_embedding_count_earlier=feat.skipped_embedding_count_earlier,
                skipped_embedding_count_later=feat.skipped_embedding_count_later,
                alignment_coverage_count=feat.alignment_coverage_count,
                alignment_coverage_words=feat.alignment_coverage_words,
                high_confidence_count=feat.high_confidence_count,
                medium_confidence_count=feat.medium_confidence_count,
                low_confidence_count=feat.low_confidence_count,
                needs_review_confidence_count=feat.needs_review_confidence_count,
                high_confidence_share=feat.high_confidence_share,
                review_required_share=feat.review_required_share,
                disclosure_change_score=feat.disclosure_change_score,
                score_version=feat.score_version,
                score_unchanged_component=feat.score_unchanged_component,
                score_lightly_modified_component=feat.score_lightly_modified_component,
                score_substantially_modified_component=feat.score_substantially_modified_component,
                score_new_component=feat.score_new_component,
                score_removed_component=feat.score_removed_component,
                score_ambiguous_component=feat.score_ambiguous_component,
                feature_quality=feat.feature_quality.value,
                primary_eligible=feat.primary_eligible,
                warning_reasons=feat.warning_reasons,
                exclusion_reasons=feat.exclusion_reasons,
                similarity_run_id=str(run.similarity_run_id),
                alignment_run_id=str(run.alignment_run_id),
                feature_run_id=str(run.id),
                configuration_hash=run.configuration_hash,
                generated_at=generated_at,
            )
        )
    return rows


def write_export_csv(rows: list[ExportRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            record = vars(row)
            # Empty cells for undefined optional metrics, never fabricated zeroes.
            writer.writerow({k: ("" if v is None else v) for k, v in record.items()})

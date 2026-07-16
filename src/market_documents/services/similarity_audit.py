"""Corpus-level similarity audit rows and per-metric ranking.

Works even when some pairs have never been scored, some runs failed, some
reports have since been re-extracted, some pairs are transitions, or some
results are excluded from primary analysis -- every field is optional and
simply blank when the corresponding data doesn't exist yet.
"""

import csv
import uuid
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.enums import SimilarityResultQuality
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.extraction import get_current_runs_by_report
from market_documents.services.similarity import (
    get_current_document_similarities_by_pair,
    get_current_similarity_runs_by_pair,
    get_latest_similarity_runs_by_pair,
)

RANKABLE_FIELDS = (
    "lexical_cosine_similarity",
    "jaccard_similarity",
    "diff_similarity",
    "edit_similarity",
    "word_count_change_ratio",
    "word_count_change",
    "character_count_change_ratio",
    "character_count_change",
)


@dataclass
class SimilarityAuditRow:
    ticker: str
    report_pair_id: str
    earlier_report_id: str
    later_report_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    gap_months: int
    is_transition: bool
    earlier_extraction_quality: str | None
    later_extraction_quality: str | None
    earlier_narrative_document_id: str | None
    later_narrative_document_id: str | None
    earlier_narrative_word_count: int | None
    later_narrative_word_count: int | None
    lexical_cosine_similarity: float | None
    jaccard_similarity: float | None
    diff_similarity: float | None
    diff_mode: str | None
    diff_duration_ms: float | None
    edit_similarity: float | None
    word_count_change_ratio: float | None
    similarity_run_status: str | None
    result_quality: str | None
    primary_analysis_eligible: bool | None
    exclusion_or_review_reason: str | None
    configuration_hash: str | None
    algorithm_version: str | None


def build_similarity_audit_rows(session: Session) -> list[SimilarityAuditRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(joinedload(ReportPair.company))
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()

    report_ids = list({p.earlier_report_id for p in pairs} | {p.later_report_id for p in pairs})
    reports_by_id = {r.id: r for r in session.scalars(select(Report).where(Report.id.in_(report_ids)))}
    current_extraction_runs = get_current_runs_by_report(session, report_ids)

    pair_ids = [p.id for p in pairs]
    current_similarity_runs = get_current_similarity_runs_by_pair(session, pair_ids)
    doc_similarities_by_pair = get_current_document_similarities_by_pair(session, pair_ids)
    latest_similarity_runs = get_latest_similarity_runs_by_pair(session, pair_ids)

    rows: list[SimilarityAuditRow] = []
    for pair in pairs:
        earlier_report = reports_by_id.get(pair.earlier_report_id)
        later_report = reports_by_id.get(pair.later_report_id)
        earlier_extraction_run = current_extraction_runs.get(pair.earlier_report_id)
        later_extraction_run = current_extraction_runs.get(pair.later_report_id)

        similarity_run = current_similarity_runs.get(pair.id) or latest_similarity_runs.get(pair.id)
        doc_similarity = doc_similarities_by_pair.get(pair.id)

        exclusion_or_review_reason = None
        if doc_similarity is not None:
            exclusion_or_review_reason = (
                doc_similarity.primary_analysis_exclusion_reason or doc_similarity.review_reason
            )
        elif similarity_run is not None and similarity_run.error_message:
            exclusion_or_review_reason = similarity_run.error_message

        rows.append(
            SimilarityAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                earlier_report_id=str(pair.earlier_report_id),
                later_report_id=str(pair.later_report_id),
                earlier_period_end=(
                    earlier_report.period_end.isoformat()
                    if earlier_report and earlier_report.period_end
                    else None
                ),
                later_period_end=(
                    later_report.period_end.isoformat()
                    if later_report and later_report.period_end
                    else None
                ),
                gap_months=pair.gap_months,
                is_transition=pair.is_transition,
                earlier_extraction_quality=(
                    earlier_extraction_run.extraction_quality.value
                    if earlier_extraction_run and earlier_extraction_run.extraction_quality
                    else None
                ),
                later_extraction_quality=(
                    later_extraction_run.extraction_quality.value
                    if later_extraction_run and later_extraction_run.extraction_quality
                    else None
                ),
                earlier_narrative_document_id=(
                    str(similarity_run.earlier_narrative_document_id) if similarity_run else None
                ),
                later_narrative_document_id=(
                    str(similarity_run.later_narrative_document_id) if similarity_run else None
                ),
                earlier_narrative_word_count=doc_similarity.earlier_word_count if doc_similarity else None,
                later_narrative_word_count=doc_similarity.later_word_count if doc_similarity else None,
                lexical_cosine_similarity=doc_similarity.lexical_cosine_similarity if doc_similarity else None,
                jaccard_similarity=doc_similarity.jaccard_similarity if doc_similarity else None,
                diff_similarity=doc_similarity.diff_similarity if doc_similarity else None,
                diff_mode=doc_similarity.diff_mode.value if doc_similarity and doc_similarity.diff_mode else None,
                diff_duration_ms=doc_similarity.diff_duration_ms if doc_similarity else None,
                edit_similarity=doc_similarity.edit_similarity if doc_similarity else None,
                word_count_change_ratio=doc_similarity.word_count_change_ratio if doc_similarity else None,
                similarity_run_status=similarity_run.status.value if similarity_run else None,
                result_quality=doc_similarity.quality_status.value if doc_similarity else None,
                primary_analysis_eligible=(
                    doc_similarity.primary_analysis_eligible if doc_similarity else None
                ),
                exclusion_or_review_reason=exclusion_or_review_reason,
                configuration_hash=similarity_run.configuration_hash if similarity_run else None,
                algorithm_version=similarity_run.algorithm_version if similarity_run else None,
            )
        )
    return rows


def write_similarity_audit_csv(rows: list[SimilarityAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(SimilarityAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


@dataclass
class RankedSimilarityRow:
    rank: int
    report_pair_id: uuid.UUID
    ticker: str
    metric_name: str
    metric_value: float
    quality_status: SimilarityResultQuality
    is_transition: bool
    primary_analysis_eligible: bool


def rank_by_metric(
    session: Session,
    metric_name: str,
    *,
    ascending: bool = True,
    ticker: str | None = None,
    include_transitions: bool = False,
    quality_filter: SimilarityResultQuality | None = None,
    limit: int | None = None,
) -> list[RankedSimilarityRow]:
    """Rank current similarity results by one metric.

    Lower values mean "more changed" for the four similarity metrics
    (cosine/Jaccard/diff/edit); higher values mean "more changed" for the
    word/character count-change metrics -- callers choose `ascending`
    accordingly. Failed or missing comparisons (a `None` metric value) are
    never ranked. Ties are broken deterministically by `report_pair_id`.
    """
    if metric_name not in RANKABLE_FIELDS:
        raise ValueError(f"unsupported ranking metric: {metric_name!r}, must be one of {RANKABLE_FIELDS}")

    pairs = session.scalars(select(ReportPair).options(joinedload(ReportPair.company))).all()
    pairs_by_id = {p.id: p for p in pairs}
    doc_similarities_by_pair = get_current_document_similarities_by_pair(session, list(pairs_by_id))

    candidates: list[tuple[float, ReportPair, SimilarityResultQuality, bool]] = []
    for pair_id, doc_similarity in doc_similarities_by_pair.items():
        pair = pairs_by_id[pair_id]
        if not include_transitions and pair.is_transition:
            continue
        if quality_filter is not None and doc_similarity.quality_status != quality_filter:
            continue
        if ticker is not None and pair.company.ticker.upper() != ticker.upper():
            continue

        value = getattr(doc_similarity, metric_name)
        if value is None:
            continue

        candidates.append((value, pair, doc_similarity.quality_status, doc_similarity.primary_analysis_eligible))

    candidates.sort(key=lambda c: (c[0], str(c[1].id)), reverse=not ascending)

    if limit is not None:
        candidates = candidates[:limit]

    return [
        RankedSimilarityRow(
            rank=i + 1,
            report_pair_id=pair.id,
            ticker=pair.company.ticker,
            metric_name=metric_name,
            metric_value=value,
            quality_status=quality_status,
            is_transition=pair.is_transition,
            primary_analysis_eligible=primary_eligible,
        )
        for i, (value, pair, quality_status, primary_eligible) in enumerate(candidates)
    ]

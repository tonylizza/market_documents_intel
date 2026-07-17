"""Corpus-level passage-alignment audit rows.

Mirrors `similarity_audit.py`: every field is optional and simply blank when
the corresponding data doesn't exist yet (unaligned pairs, missing
document-level similarity results, failed latest runs). Document-level
similarity status (M3) and passage-alignment quality (M4) are surfaced
side by side but remain separate concepts -- a pair with NEEDS_REVIEW
document similarity is not excluded here.
"""

import csv
import statistics
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus
from market_documents.models.alignment import PassageAlignment
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.passage_alignment import get_current_alignment_runs_by_pair
from market_documents.services.similarity import get_current_document_similarities_by_pair


@dataclass
class AlignmentAuditRow:
    ticker: str
    report_pair_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    gap_months: int
    is_transition: bool
    document_similarity_quality: str | None
    document_lexical_cosine_similarity: float | None
    earlier_passage_count: int | None
    later_passage_count: int | None
    matched_count: int | None
    unchanged_count: int | None
    lightly_modified_count: int | None
    substantially_modified_count: int | None
    new_count: int | None
    removed_count: int | None
    ambiguous_count: int | None
    high_confidence_count: int
    medium_confidence_count: int
    low_confidence_count: int
    needs_review_confidence_count: int
    disagreement_count: int
    likely_split_merge_count: int
    mean_semantic_similarity: float | None
    mean_lexical_similarity: float | None
    percent_later_matched: float | None
    percent_earlier_removed: float | None
    model_revision: str | None
    algorithm_version: str | None
    configuration_hash: str | None
    status: str | None
    warnings: str | None


def build_alignment_audit_rows(session: Session) -> list[AlignmentAuditRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(joinedload(ReportPair.company), joinedload(ReportPair.earlier_report), joinedload(ReportPair.later_report))
        .order_by(Company.ticker, ReportPair.gap_months)
        .join(Company, ReportPair.company_id == Company.id)
    ).all()

    pair_ids = [p.id for p in pairs]
    current_alignment_runs = get_current_alignment_runs_by_pair(session, pair_ids)
    doc_similarities = get_current_document_similarities_by_pair(session, pair_ids)

    run_ids = [run.id for run in current_alignment_runs.values()]
    all_alignments: list[PassageAlignment] = (
        session.scalars(select(PassageAlignment).where(PassageAlignment.alignment_run_id.in_(run_ids))).all()
        if run_ids
        else []
    )
    alignments_by_run: dict = {}
    for a in all_alignments:
        alignments_by_run.setdefault(a.alignment_run_id, []).append(a)

    rows: list[AlignmentAuditRow] = []
    for pair in pairs:
        run = current_alignment_runs.get(pair.id)
        doc_similarity = doc_similarities.get(pair.id)
        alignments = alignments_by_run.get(run.id, []) if run else []

        confidence_counts = {c: 0 for c in AlignmentConfidence}
        for a in alignments:
            confidence_counts[a.confidence] += 1

        disagreement_count = sum(
            1 for a in alignments if a.review_reason and ("paraphrase" in a.review_reason or "boilerplate" in a.review_reason)
        )
        split_merge_count = sum(
            1 for a in alignments if a.review_reason and ("split" in a.review_reason or "merge" in a.review_reason)
        )

        semantic_values = [a.semantic_similarity for a in alignments if a.semantic_similarity is not None]
        lexical_values = [
            statistics.mean(
                v
                for v in (a.lexical_cosine_similarity, a.jaccard_similarity, a.edit_similarity)
                if v is not None
            )
            for a in alignments
            if any(v is not None for v in (a.lexical_cosine_similarity, a.jaccard_similarity, a.edit_similarity))
        ]

        later_total = run.matched_count + run.new_count if run and run.new_count is not None and run.matched_count is not None else None
        earlier_total = (
            run.matched_count + run.removed_count if run and run.removed_count is not None and run.matched_count is not None else None
        )
        percent_later_matched = (
            run.matched_count / later_total * 100 if later_total else None
        )
        percent_earlier_removed = (
            run.removed_count / earlier_total * 100 if earlier_total else None
        )

        rows.append(
            AlignmentAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                earlier_period_end=pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None,
                later_period_end=pair.later_report.period_end.isoformat() if pair.later_report.period_end else None,
                gap_months=pair.gap_months,
                is_transition=pair.is_transition,
                document_similarity_quality=doc_similarity.quality_status.value if doc_similarity else None,
                document_lexical_cosine_similarity=doc_similarity.lexical_cosine_similarity if doc_similarity else None,
                earlier_passage_count=earlier_total,
                later_passage_count=later_total,
                matched_count=run.matched_count if run else None,
                unchanged_count=run.unchanged_count if run else None,
                lightly_modified_count=run.lightly_modified_count if run else None,
                substantially_modified_count=run.substantially_modified_count if run else None,
                new_count=run.new_count if run else None,
                removed_count=run.removed_count if run else None,
                ambiguous_count=run.ambiguous_count if run else None,
                high_confidence_count=confidence_counts[AlignmentConfidence.HIGH],
                medium_confidence_count=confidence_counts[AlignmentConfidence.MEDIUM],
                low_confidence_count=confidence_counts[AlignmentConfidence.LOW],
                needs_review_confidence_count=confidence_counts[AlignmentConfidence.NEEDS_REVIEW],
                disagreement_count=disagreement_count,
                likely_split_merge_count=split_merge_count,
                mean_semantic_similarity=round(statistics.mean(semantic_values), 4) if semantic_values else None,
                mean_lexical_similarity=round(statistics.mean(lexical_values), 4) if lexical_values else None,
                percent_later_matched=round(percent_later_matched, 1) if percent_later_matched is not None else None,
                percent_earlier_removed=round(percent_earlier_removed, 1) if percent_earlier_removed is not None else None,
                model_revision=run.later_embedding_run.model_revision if run else None,
                algorithm_version=run.algorithm_version if run else None,
                configuration_hash=run.configuration_hash if run else None,
                status=run.status.value if run else None,
                warnings=run.review_reason if run else None,
            )
        )
    return rows


def write_alignment_audit_csv(rows: list[AlignmentAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(AlignmentAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))

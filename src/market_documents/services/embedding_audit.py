"""Corpus-level passage-embedding audit rows.

Mirrors `segmentation_audit.py`/`similarity_audit.py`: every field is
optional and simply blank when the corresponding data doesn't exist yet
(unsegmented reports, unembedded segmentation runs, different model
versions across reports).
"""

import csv
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from market_documents.models.embedding import EmbeddingRun, PassageEmbedding
from market_documents.models.extraction import NarrativeDocument
from market_documents.models.passage import PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services.extraction import get_current_runs_by_report
from market_documents.services.passage_embedding import get_current_embedding_runs_by_segmentation_run
from market_documents.services.passage_segmentation import get_current_segmentation_runs_by_narrative_document


@dataclass
class EmbeddingAuditRow:
    ticker: str
    report_id: str
    segmentation_run_id: str | None
    embedding_run_id: str | None
    model_name: str | None
    model_revision: str | None
    tokenizer_revision: str | None
    embedding_dimension: int | None
    eligible_passage_count: int | None
    embedded_count: int | None
    skipped_count: int | None
    truncated_count: int
    failed_count: int
    runtime_seconds: float | None
    status: str | None
    warnings: str | None
    configuration_hash: str | None


def _failed_count(review_reason: str | None) -> int:
    if not review_reason:
        return 0
    return sum(1 for msg in review_reason.split("; ") if "embedding failed for a passage" in msg)


def build_embedding_audit_rows(session: Session) -> list[EmbeddingAuditRow]:
    reports = session.scalars(select(Report).order_by(Report.directory_year, Report.local_path)).all()
    report_ids = [r.id for r in reports]
    current_extraction_runs = get_current_runs_by_report(session, report_ids)

    extraction_run_ids = [run.id for run in current_extraction_runs.values()]
    narratives = session.scalars(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id.in_(extraction_run_ids))
    ).all()
    narrative_by_report_id = {n.report_id: n for n in narratives}

    narrative_ids = [n.id for n in narratives]
    current_segmentation_runs = get_current_segmentation_runs_by_narrative_document(session, narrative_ids)

    segmentation_run_ids = [run.id for run in current_segmentation_runs.values()]
    current_embedding_runs = get_current_embedding_runs_by_segmentation_run(session, segmentation_run_ids)

    embedding_run_ids = [run.id for run in current_embedding_runs.values()]
    truncated_counts: dict = {}
    if embedding_run_ids:
        rows = session.execute(
            select(PassageEmbedding.embedding_run_id, func.count())
            .where(PassageEmbedding.embedding_run_id.in_(embedding_run_ids), PassageEmbedding.truncated.is_(True))
            .group_by(PassageEmbedding.embedding_run_id)
        ).all()
        truncated_counts = dict(rows)

    result: list[EmbeddingAuditRow] = []
    for report in reports:
        narrative = narrative_by_report_id.get(report.id)
        segmentation_run: PassageSegmentationRun | None = (
            current_segmentation_runs.get(narrative.id) if narrative else None
        )
        embedding_run: EmbeddingRun | None = (
            current_embedding_runs.get(segmentation_run.id) if segmentation_run else None
        )

        eligible_passage_count = None
        if segmentation_run is not None and segmentation_run.passage_count is not None:
            eligible_passage_count = segmentation_run.passage_count - (segmentation_run.excluded_passage_count or 0)

        runtime_seconds = None
        if embedding_run is not None and embedding_run.started_at and embedding_run.completed_at:
            runtime_seconds = (embedding_run.completed_at - embedding_run.started_at).total_seconds()

        result.append(
            EmbeddingAuditRow(
                ticker=report.company.ticker if report.company else "?",
                report_id=str(report.id),
                segmentation_run_id=str(segmentation_run.id) if segmentation_run else None,
                embedding_run_id=str(embedding_run.id) if embedding_run else None,
                model_name=embedding_run.model_name if embedding_run else None,
                model_revision=embedding_run.model_revision if embedding_run else None,
                tokenizer_revision=embedding_run.tokenizer_revision if embedding_run else None,
                embedding_dimension=embedding_run.embedding_dimension if embedding_run else None,
                eligible_passage_count=eligible_passage_count,
                embedded_count=embedding_run.embedded_passage_count if embedding_run else None,
                skipped_count=embedding_run.skipped_passage_count if embedding_run else None,
                truncated_count=truncated_counts.get(embedding_run.id, 0) if embedding_run else 0,
                failed_count=_failed_count(embedding_run.review_reason) if embedding_run else 0,
                runtime_seconds=runtime_seconds,
                status=embedding_run.status.value if embedding_run else None,
                warnings=embedding_run.review_reason if embedding_run else None,
                configuration_hash=embedding_run.configuration_hash if embedding_run else None,
            )
        )
    return result


def write_embedding_audit_csv(rows: list[EmbeddingAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(EmbeddingAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))

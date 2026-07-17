"""Corpus-level passage-segmentation audit rows.

Mirrors `similarity_audit.py`'s shape: every field is optional and simply
blank when the corresponding data doesn't exist yet (unsegmented reports,
unresolved metadata, failed latest runs with an earlier successful run).
"""

import csv
import statistics
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company
from market_documents.models.extraction import NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.services.extraction import get_current_runs_by_report
from market_documents.services.passage_segmentation import get_current_segmentation_runs_by_narrative_document


@dataclass
class SegmentationAuditRow:
    ticker: str
    report_id: str
    period_end: str | None
    narrative_document_id: str | None
    segmentation_run_id: str | None
    source_word_count: int | None
    passage_count: int | None
    excluded_passage_count: int | None
    min_passage_word_count: int | None
    median_passage_word_count: float | None
    mean_passage_word_count: float | None
    max_passage_word_count: int | None
    multi_page_passage_count: int | None
    heading_associated_passage_count: int | None
    provenance_warning_count: int
    run_status: str | None
    warnings: str | None
    configuration_hash: str | None


def build_segmentation_audit_rows(session: Session) -> list[SegmentationAuditRow]:
    reports = session.scalars(
        select(Report).order_by(Report.directory_year, Report.local_path)
    ).all()
    report_ids = [r.id for r in reports]
    current_extraction_runs = get_current_runs_by_report(session, report_ids)

    extraction_run_ids = [run.id for run in current_extraction_runs.values()]
    narratives = session.scalars(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id.in_(extraction_run_ids))
    ).all()
    narrative_by_report_id = {n.report_id: n for n in narratives}

    narrative_ids = [n.id for n in narratives]
    current_segmentation_runs = get_current_segmentation_runs_by_narrative_document(session, narrative_ids)

    run_ids = [run.id for run in current_segmentation_runs.values()]
    all_passages = (
        session.scalars(select(Passage).where(Passage.segmentation_run_id.in_(run_ids))).all()
        if run_ids
        else []
    )
    passages_by_run: dict = {}
    for p in all_passages:
        passages_by_run.setdefault(p.segmentation_run_id, []).append(p)

    rows: list[SegmentationAuditRow] = []
    for report in reports:
        narrative = narrative_by_report_id.get(report.id)
        run: PassageSegmentationRun | None = (
            current_segmentation_runs.get(narrative.id) if narrative else None
        )
        passages = passages_by_run.get(run.id, []) if run else []

        word_counts = [p.word_count for p in passages]
        provenance_warning_count = (
            len(run.review_reason.split("; ")) if run and run.review_reason else 0
        )

        rows.append(
            SegmentationAuditRow(
                ticker=report.company.ticker if report.company else "?",
                report_id=str(report.id),
                period_end=report.period_end.isoformat() if report.period_end else None,
                narrative_document_id=str(narrative.id) if narrative else None,
                segmentation_run_id=str(run.id) if run else None,
                source_word_count=narrative.word_count if narrative else None,
                passage_count=run.passage_count if run else None,
                excluded_passage_count=run.excluded_passage_count if run else None,
                min_passage_word_count=min(word_counts) if word_counts else None,
                median_passage_word_count=statistics.median(word_counts) if word_counts else None,
                mean_passage_word_count=(
                    round(statistics.mean(word_counts), 1) if word_counts else None
                ),
                max_passage_word_count=max(word_counts) if word_counts else None,
                multi_page_passage_count=sum(
                    1 for p in passages if p.first_page_number != p.last_page_number
                ),
                heading_associated_passage_count=sum(1 for p in passages if p.heading_text is not None),
                provenance_warning_count=provenance_warning_count,
                run_status=run.status.value if run else None,
                warnings=run.review_reason if run else None,
                configuration_hash=run.configuration_hash if run else None,
            )
        )
    return rows


def write_segmentation_audit_csv(rows: list[SegmentationAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(SegmentationAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))

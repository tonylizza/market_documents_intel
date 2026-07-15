"""Corpus-level audit rows, joining Report and its current extraction run.

Works even when some reports have never been extracted or have only
failed runs -- extraction fields are simply blank in that case, since
`get_current_runs_by_report` only ever returns COMPLETED /
COMPLETED_WITH_WARNINGS runs.
"""

import csv
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company
from market_documents.models.report import Report
from market_documents.services.extraction import get_current_runs_by_report
from market_documents.services.pdf_access import is_encrypted


@dataclass
class CorpusAuditRow:
    ticker: str
    report_id: str
    filename: str
    directory_year: int
    fiscal_label: str | None
    period_end: str | None
    metadata_status: str
    pdf_page_count: int | None
    processed_page_count: int | None
    total_extracted_words: int | None
    usable_page_percentage: float | None
    low_text_page_count: int | None
    image_only_page_count: int | None
    extraction_status: str | None
    extraction_quality: str | None
    review_reason: str | None
    encrypted_pdf_handled: bool


def build_corpus_audit_rows(session: Session) -> list[CorpusAuditRow]:
    reports = session.scalars(
        select(Report).join(Company).order_by(Company.ticker, Report.directory_year)
    ).all()
    current_runs = get_current_runs_by_report(session, [r.id for r in reports])

    rows: list[CorpusAuditRow] = []
    for report in reports:
        run = current_runs.get(report.id)
        usable_page_percentage = (
            run.usable_page_count / run.processed_page_count
            if run and run.usable_page_count is not None and run.processed_page_count
            else None
        )
        rows.append(
            CorpusAuditRow(
                ticker=report.company.ticker,
                report_id=str(report.id),
                filename=report.filename,
                directory_year=report.directory_year,
                fiscal_label=report.fiscal_label,
                period_end=report.period_end.isoformat() if report.period_end else None,
                metadata_status=report.metadata_status.value,
                pdf_page_count=report.page_count,
                processed_page_count=run.processed_page_count if run else None,
                total_extracted_words=run.total_word_count if run else None,
                usable_page_percentage=usable_page_percentage,
                low_text_page_count=run.low_text_page_count if run else None,
                image_only_page_count=run.image_only_page_count if run else None,
                extraction_status=run.status.value if run else None,
                extraction_quality=run.extraction_quality.value if run and run.extraction_quality else None,
                review_reason=run.review_reason if run else None,
                encrypted_pdf_handled=run.encrypted_pdf_handled if run else is_encrypted(Path(report.local_path)),
            )
        )
    return rows


def write_corpus_audit_csv(rows: list[CorpusAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(CorpusAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))

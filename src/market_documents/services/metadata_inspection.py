import re
from dataclasses import dataclass, field
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report

INSPECT_PAGE_COUNT = 5

_FISCAL_LABEL_RE = re.compile(
    r"(?i)(?:year|period)\s+ended\s+\d{1,2}\s+\w+\s+\d{4}"
)
_REPORTING_MONTHS_RE = re.compile(r"(?i)(\d{1,2})[\s-]?months?\s+(?:period\s+)?ended")
_TRANSITION_RE = re.compile(r"(?i)transitional?\s+period")


@dataclass
class InspectionOutcome:
    inspected: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def inspect_report(report: Report) -> None:
    """Read the first few pages of a report's PDF to enrich provisional metadata.

    Never overwrites a field that already carries a MANUAL source, and only
    ever fills fields that are currently unset -- this is a lightweight hint
    pass, not authoritative extraction.
    """
    path = Path(report.local_path)
    reader = PdfReader(str(path))
    report.page_count = len(reader.pages)

    pages_to_read = reader.pages[: min(INSPECT_PAGE_COUNT, len(reader.pages))]
    text = "\n".join(page.extract_text() or "" for page in pages_to_read)

    notes: list[str] = []
    is_manual = report.metadata_source == MetadataSource.MANUAL

    if not is_manual:
        if report.fiscal_label is None:
            match = _FISCAL_LABEL_RE.search(text)
            if match:
                report.fiscal_label = match.group(0)
                notes.append(f"fiscal_label candidate from PDF text: {match.group(0)!r}")

        if report.reporting_months is None:
            match = _REPORTING_MONTHS_RE.search(text)
            if match:
                report.reporting_months = int(match.group(1))
                notes.append(f"reporting_months candidate from PDF text: {match.group(1)}")

        if _TRANSITION_RE.search(text):
            report.transition_report = True
            notes.append("transition wording detected in PDF text")

        if notes:
            report.metadata_source = MetadataSource.PDF

    title = reader.metadata.title if reader.metadata else None
    if title:
        notes.append(f"pdf title: {title!r}")

    if notes:
        existing = report.validation_notes or ""
        report.validation_notes = (existing + "\n" if existing else "") + "; ".join(notes)

    if report.metadata_status == MetadataStatus.DISCOVERED:
        report.metadata_status = MetadataStatus.INSPECTED


def inspect_discovered_reports(session: Session) -> InspectionOutcome:
    outcome = InspectionOutcome()
    reports = session.scalars(
        select(Report).where(Report.metadata_status == MetadataStatus.DISCOVERED)
    ).all()
    for report in reports:
        try:
            inspect_report(report)
            outcome.inspected.append(report.local_path)
        except Exception as exc:  # corrupt/unreadable PDF
            report.validation_notes = f"inspection failed: {exc}"
            outcome.failed.append((report.local_path, str(exc)))
    return outcome

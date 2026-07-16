import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report

INSPECT_PAGE_COUNT = 5

# Bump whenever a detection regex or parsing rule below changes -- exported
# review rows record this so a human can tell whether "no match" means
# "genuinely nothing found" or "found by an older/different rule version".
METADATA_DETECTION_RULE_VERSION = 1

_FISCAL_LABEL_RE = re.compile(
    r"(?i)(?:year|period)\s+ended\s+\d{1,2}\s+\w+\s+\d{4}"
)
_FISCAL_PERIOD_DATE_RE = re.compile(
    r"(?i)(?:year|period)\s+ended\s+(\d{1,2})\s+(\w+)\s+(\d{4})"
)
_REPORTING_MONTHS_RE = re.compile(r"(?i)(\d{1,2})[\s-]?months?\s+(?:period\s+)?ended")
_TRANSITION_RE = re.compile(r"(?i)transitional?\s+period")

_MONTH_NAMES = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}  # fmt: skip


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


def parse_period_end_from_phrase(phrase: str) -> date | None:
    """Parse a "year/period ended DD Month YYYY" phrase into a calendar date.

    Returns None for an unrecognized month name or an impossible date (e.g.
    31 February) rather than raising -- callers treat that the same as "no
    date could be determined from this phrase".
    """
    match = _FISCAL_PERIOD_DATE_RE.search(phrase)
    if not match:
        return None
    day_str, month_str, year_str = match.groups()
    month = _MONTH_NAMES.get(month_str.lower())
    if month is None:
        return None
    try:
        return date(int(year_str), month, int(day_str))
    except ValueError:
        return None


@dataclass(frozen=True)
class FiscalPeriodEvidence:
    """One fiscal-period-date match found on a specific page.

    Kept deliberately small -- a short matched phrase and its page number,
    never the surrounding page text -- so this is safe to write to a CSV
    review export.
    """

    page_number: int
    phrase: str
    period_end: date | None


def find_fiscal_period_evidence(
    reader: PdfReader, max_pages: int = INSPECT_PAGE_COUNT
) -> list[FiscalPeriodEvidence]:
    """Scan the first `max_pages` pages individually for fiscal-period phrases.

    Unlike `inspect_report` (which concatenates pages before matching, for a
    single best-effort hint), this scans page-by-page and returns every
    match with its page number and parsed date, so `metadata_review` can
    show provenance and detect when a document mentions more than one
    distinct period-end date (e.g. current-year statement plus a prior-year
    comparative).
    """
    evidence: list[FiscalPeriodEvidence] = []
    pages_to_read = reader.pages[: min(max_pages, len(reader.pages))]
    for page_number, page in enumerate(pages_to_read, start=1):
        text = page.extract_text() or ""
        for match in _FISCAL_LABEL_RE.finditer(text):
            phrase = match.group(0)
            evidence.append(
                FiscalPeriodEvidence(
                    page_number=page_number,
                    phrase=phrase,
                    period_end=parse_period_end_from_phrase(phrase),
                )
            )
    return evidence


@dataclass(frozen=True)
class ReportingMonthsEvidence:
    page_number: int
    months: int


def find_reporting_months_evidence(
    reader: PdfReader, max_pages: int = INSPECT_PAGE_COUNT
) -> ReportingMonthsEvidence | None:
    """First "N months ended" match across the first `max_pages` pages, if any."""
    pages_to_read = reader.pages[: min(max_pages, len(reader.pages))]
    for page_number, page in enumerate(pages_to_read, start=1):
        text = page.extract_text() or ""
        match = _REPORTING_MONTHS_RE.search(text)
        if match:
            return ReportingMonthsEvidence(page_number=page_number, months=int(match.group(1)))
    return None


def find_transition_evidence(reader: PdfReader, max_pages: int = INSPECT_PAGE_COUNT) -> int | None:
    """Page number of the first "transition(al) period" wording, if any."""
    pages_to_read = reader.pages[: min(max_pages, len(reader.pages))]
    for page_number, page in enumerate(pages_to_read, start=1):
        text = page.extract_text() or ""
        if _TRANSITION_RE.search(text):
            return page_number
    return None


def detect_publication_date_hint(reader: PdfReader) -> date | None:
    """PDF-metadata creation date, as a low-confidence publication-date hint.

    This is document-metadata provenance (when the PDF file was produced),
    not a statement from the report's own text -- weaker evidence than a
    detected fiscal-period phrase, surfaced only as a starting point for
    human review.
    """
    metadata = reader.metadata
    if metadata is None or metadata.creation_date is None:
        return None
    return metadata.creation_date.date()

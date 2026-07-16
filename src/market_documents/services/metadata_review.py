"""Human-in-the-loop fiscal-period metadata remediation.

Bridges the gap between `metadata_inspection`'s lightweight regex hints and
`validation`'s all-or-nothing rule (period_end is not None -> VALIDATED):
this module exports a CSV a human can review, and imports only the rows
they explicitly confirmed or corrected.

Detection evidence (matched phrase, page number, confidence, rule version)
is deliberately never persisted to the database -- it is recomputed fresh
from the PDF at export time and lives only in the CSV artifact, which is
itself the reviewable/auditable record. This keeps `Report` free of a
parallel "detection state" that could drift from the PDF it was read from,
and avoids a schema change for what is fundamentally derived, regenerable
data (see `NarrativeDocument`'s docstring for the same philosophy applied
to extracted text).

Never marks a report VALIDATED -- that remains `validation.validate_reports`'s
job, run as an explicit separate step after import.
"""

import csv
from dataclasses import dataclass, field, fields
from pathlib import Path

from pydantic import ValidationError
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company
from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report
from market_documents.schemas.metadata_review import (
    APPLICABLE_REVIEWER_STATUSES,
    DetectionConfidence,
    MetadataReviewImportRow,
    ReviewerStatus,
)
from market_documents.services.metadata_inspection import (
    INSPECT_PAGE_COUNT,
    METADATA_DETECTION_RULE_VERSION,
    detect_publication_date_hint,
    find_fiscal_period_evidence,
    find_reporting_months_evidence,
    find_transition_evidence,
)

DETECTION_METHOD = "regex:fiscal_period_v1"

# Reports in these statuses have not yet been through metadata review and
# are therefore export candidates by default. VALIDATED reports are
# excluded by default (their period_end is already established) but can be
# included via `include_validated=True` for a full re-review.
DEFAULT_EXPORT_STATUSES = (
    MetadataStatus.DISCOVERED,
    MetadataStatus.INSPECTED,
    MetadataStatus.NEEDS_REVIEW,
)


@dataclass
class MetadataReviewExportRow:
    report_id: str
    ticker: str
    company_name: str
    filename: str
    local_path: str
    directory_year: int
    fiscal_label: str | None
    current_period_start: str | None
    current_period_end: str | None
    current_publication_date: str | None
    current_reporting_months: int | None
    current_transition_report: bool
    metadata_status: str
    metadata_source: str
    pdf_page_count: int | None
    detected_fiscal_phrase: str | None
    detected_phrase_page: int | None
    detection_method: str
    detection_rule_version: int
    detected_period_start: str | None
    detected_period_end: str | None
    detected_publication_date: str | None
    detected_reporting_months: int | None
    transition_hint: bool
    confidence: str
    ambiguity_reason: str | None
    proposed_period_start: str | None
    proposed_period_end: str | None
    proposed_publication_date: str | None
    proposed_reporting_months: int | None
    proposed_transition_report: bool
    reviewer_status: str
    reviewer_notes: str | None


EXPORT_CSV_FIELDNAMES = [f.name for f in fields(MetadataReviewExportRow)]


def _detect_row_evidence(report: Report) -> MetadataReviewExportRow:
    """Read `report`'s PDF fresh and build one export row from scratch."""
    detected_phrase: str | None = None
    detected_phrase_page: int | None = None
    detected_period_end = None
    detected_reporting_months: int | None = None
    transition_hint = False
    publication_date_hint = None
    confidence = DetectionConfidence.NONE
    ambiguity_reason: str | None = None

    try:
        reader = PdfReader(report.local_path)
        evidence = find_fiscal_period_evidence(reader, max_pages=INSPECT_PAGE_COUNT)
        reporting_months_evidence = find_reporting_months_evidence(reader, max_pages=INSPECT_PAGE_COUNT)
        transition_page = find_transition_evidence(reader, max_pages=INSPECT_PAGE_COUNT)
        publication_date_hint = detect_publication_date_hint(reader)
    except Exception as exc:  # corrupt/unreadable PDF -- no evidence, not a crash
        ambiguity_reason = f"PDF unreadable during detection: {exc}"
    else:
        transition_hint = transition_page is not None
        if reporting_months_evidence is not None:
            detected_reporting_months = reporting_months_evidence.months

        if not evidence:
            ambiguity_reason = "no fiscal-period phrase detected in scanned pages"
        else:
            detected_phrase = evidence[0].phrase
            detected_phrase_page = evidence[0].page_number
            parsed_dates_in_order = [e.period_end for e in evidence if e.period_end is not None]
            distinct_dates = sorted(set(parsed_dates_in_order))

            if not parsed_dates_in_order:
                ambiguity_reason = f"phrase found but date unparseable: {evidence[0].phrase!r}"
            elif len(distinct_dates) == 1:
                confidence = DetectionConfidence.HIGH
                detected_period_end = distinct_dates[0]
            else:
                # Multiple distinct dates are common (current-year statement
                # plus prior-year comparatives) -- propose the first
                # occurrence (earliest page/position, typically the cover
                # statement) rather than leaving the row blank, but flag the
                # alternates so review is fast to verify, not fast to miss.
                confidence = DetectionConfidence.MEDIUM
                detected_period_end = parsed_dates_in_order[0]
                alternates = sorted(d for d in distinct_dates if d != detected_period_end)
                ambiguity_reason = f"also found: {', '.join(d.isoformat() for d in alternates)}"

    return MetadataReviewExportRow(
        report_id=str(report.id),
        ticker=report.company.ticker,
        company_name=report.company.company_name,
        filename=report.filename,
        local_path=report.local_path,
        directory_year=report.directory_year,
        fiscal_label=report.fiscal_label,
        current_period_start=report.period_start.isoformat() if report.period_start else None,
        current_period_end=report.period_end.isoformat() if report.period_end else None,
        current_publication_date=report.publication_date.isoformat() if report.publication_date else None,
        current_reporting_months=report.reporting_months,
        current_transition_report=report.transition_report,
        metadata_status=report.metadata_status.value,
        metadata_source=report.metadata_source.value,
        pdf_page_count=report.page_count,
        detected_fiscal_phrase=detected_phrase,
        detected_phrase_page=detected_phrase_page,
        detection_method=DETECTION_METHOD,
        detection_rule_version=METADATA_DETECTION_RULE_VERSION,
        detected_period_start=None,  # no reliable phrase pattern detects a start date
        detected_period_end=detected_period_end.isoformat() if detected_period_end else None,
        detected_publication_date=publication_date_hint.isoformat() if publication_date_hint else None,
        detected_reporting_months=detected_reporting_months,
        transition_hint=transition_hint,
        confidence=confidence.value,
        ambiguity_reason=ambiguity_reason,
        proposed_period_start=None,
        proposed_period_end=detected_period_end.isoformat() if detected_period_end else None,
        proposed_publication_date=publication_date_hint.isoformat() if publication_date_hint else None,
        proposed_reporting_months=detected_reporting_months,
        proposed_transition_report=transition_hint,
        reviewer_status=ReviewerStatus.UNREVIEWED.value,
        reviewer_notes=None,
    )


def build_metadata_review_rows(
    session: Session, *, include_validated: bool = False
) -> list[MetadataReviewExportRow]:
    statuses = list(DEFAULT_EXPORT_STATUSES) + ([MetadataStatus.VALIDATED] if include_validated else [])
    reports = session.scalars(
        select(Report)
        .join(Company)
        .where(Report.metadata_status.in_(statuses))
        .order_by(Company.ticker, Report.directory_year)
    ).all()
    return [_detect_row_evidence(report) for report in reports]


def write_metadata_review_csv(rows: list[MetadataReviewExportRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=EXPORT_CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


@dataclass
class MetadataReviewImportOutcome:
    applied: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    conflicted: list[tuple[str, str]] = field(default_factory=list)
    invalid: list[tuple[int, str]] = field(default_factory=list)


def _read_import_rows(csv_path: Path) -> list[tuple[int, dict]]:
    """Parse the CSV into raw dicts, dropping blank cells entirely.

    A dropped key lets Pydantic apply the field's own default (e.g.
    `proposed_transition_report: bool = False`); explicitly setting it to
    `None` instead would fail validation for any non-Optional field with a
    non-None default.
    """
    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        return [
            (row_number, {k: v for k, v in raw.items() if v not in (None, "")})
            for row_number, raw in enumerate(reader, start=2)
        ]


def _fields_already_match(report: Report, row: MetadataReviewImportRow) -> bool:
    return (
        report.period_start == row.proposed_period_start
        and report.period_end == row.proposed_period_end
        and report.publication_date == row.proposed_publication_date
        and report.reporting_months == row.proposed_reporting_months
        and report.transition_report == row.proposed_transition_report
        and report.metadata_source == MetadataSource.MANUAL
    )


def import_metadata_review(session: Session, csv_path: Path) -> MetadataReviewImportOutcome:
    """Apply CONFIRMED/CORRECTED rows from a reviewed metadata CSV.

    Idempotent: reimporting the same file after a successful apply produces
    only "unchanged" rows (no DB writes, no duplicate notes) because the
    report's fields already match the proposed values. A row whose
    `proposed_period_end` conflicts with a *different* already-set value --
    on the same report, or on another report for the same company (which
    would violate the partial unique index on company_id/period_end) -- is
    reported as a conflict and never silently overwritten.
    """
    outcome = MetadataReviewImportOutcome()

    for row_number, raw in _read_import_rows(csv_path):
        try:
            row = MetadataReviewImportRow.model_validate(raw)
        except ValidationError as exc:
            outcome.invalid.append((row_number, str(exc)))
            continue

        report_id_str = str(row.report_id)

        if row.reviewer_status not in APPLICABLE_REVIEWER_STATUSES:
            outcome.skipped.append((report_id_str, f"reviewer_status is {row.reviewer_status.value}"))
            continue

        report = session.get(Report, row.report_id)
        if report is None:
            outcome.invalid.append((row_number, f"no report found with id {report_id_str}"))
            continue

        if report.period_end is not None and report.period_end != row.proposed_period_end:
            outcome.conflicted.append(
                (
                    report_id_str,
                    f"existing period_end {report.period_end.isoformat()} conflicts with "
                    f"proposed {row.proposed_period_end.isoformat()}",
                )
            )
            continue

        conflicting_report = session.scalar(
            select(Report).where(
                Report.company_id == report.company_id,
                Report.period_end == row.proposed_period_end,
                Report.id != report.id,
            )
        )
        if conflicting_report is not None:
            outcome.conflicted.append(
                (
                    report_id_str,
                    f"period_end {row.proposed_period_end.isoformat()} already used by "
                    f"report {conflicting_report.id} for this company",
                )
            )
            continue

        if _fields_already_match(report, row):
            outcome.unchanged.append(report_id_str)
            continue

        try:
            with session.begin_nested():
                report.period_start = row.proposed_period_start
                report.period_end = row.proposed_period_end
                report.publication_date = row.proposed_publication_date
                report.reporting_months = row.proposed_reporting_months
                report.transition_report = row.proposed_transition_report
                report.metadata_source = MetadataSource.MANUAL
                if row.reviewer_notes:
                    existing = report.validation_notes or ""
                    report.validation_notes = (
                        (existing + "\n" if existing else "")
                        + f"manual review ({row.reviewer_status.value}): {row.reviewer_notes}"
                    )
                session.flush()
        except Exception as exc:
            outcome.invalid.append((row_number, f"unexpected error applying row: {exc}"))
            continue

        outcome.applied.append(report_id_str)

    return outcome

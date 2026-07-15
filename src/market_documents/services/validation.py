from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import MetadataStatus
from market_documents.models.report import Report


@dataclass
class ValidationOutcome:
    validated: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    rejected: list[str] = field(default_factory=list)


def validate_report(report: Report) -> MetadataStatus:
    """Determine whether a report has sufficient metadata for downstream analysis.

    A report may legitimately remain provisional (NEEDS_REVIEW) indefinitely --
    period_end is only known once a human or a later milestone's extraction
    step has confirmed it, never inferred here.
    """
    if report.page_count is None or report.page_count == 0:
        report.metadata_status = MetadataStatus.REJECTED
        report.validation_notes = (
            (report.validation_notes + "\n" if report.validation_notes else "")
            + "rejected: unreadable or empty PDF (no page count)"
        )
        return report.metadata_status

    if report.period_end is not None:
        report.metadata_status = MetadataStatus.VALIDATED
        report.validation_notes = (
            (report.validation_notes + "\n" if report.validation_notes else "")
            + "validated: period_end is established"
        )
        return report.metadata_status

    report.metadata_status = MetadataStatus.NEEDS_REVIEW
    report.validation_notes = (
        (report.validation_notes + "\n" if report.validation_notes else "")
        + "needs_review: period_end not yet established"
    )
    return report.metadata_status


def validate_reports(session: Session) -> ValidationOutcome:
    outcome = ValidationOutcome()
    reports = session.scalars(
        select(Report).where(Report.metadata_status != MetadataStatus.DISCOVERED)
    ).all()
    for report in reports:
        status = validate_report(report)
        if status == MetadataStatus.VALIDATED:
            outcome.validated.append(report.local_path)
        elif status == MetadataStatus.NEEDS_REVIEW:
            outcome.needs_review.append(report.local_path)
        else:
            outcome.rejected.append(report.local_path)
    return outcome

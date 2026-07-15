from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company
from market_documents.models.enums import MetadataStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair


@dataclass
class PairingOutcome:
    created: list[tuple[str, str]] = field(default_factory=list)
    skipped_existing: int = 0


def _gap_months(earlier: Report, later: Report) -> int:
    return (later.period_end.year - earlier.period_end.year) * 12 + (
        later.period_end.month - earlier.period_end.month
    )


def build_pairs(session: Session) -> PairingOutcome:
    """Pair each validated report with its immediate predecessor by period_end.

    Only operates on VALIDATED reports with a non-null period_end. Rerunning
    is a no-op for pairs that already exist (unique on earlier/later ids).

    Transition pairs are still recorded (for the audit trail) but flagged via
    is_transition, driven only by the reports' own explicitly-set
    transition_report flags -- never inferred from gap_months.
    """
    outcome = PairingOutcome()
    existing_pairs = {
        (p.earlier_report_id, p.later_report_id) for p in session.scalars(select(ReportPair))
    }

    companies = session.scalars(select(Company)).all()
    for company in companies:
        reports = session.scalars(
            select(Report)
            .where(
                Report.company_id == company.id,
                Report.metadata_status == MetadataStatus.VALIDATED,
                Report.period_end.isnot(None),
            )
            .order_by(Report.period_end)
        ).all()

        for earlier, later in zip(reports, reports[1:]):
            if (earlier.id, later.id) in existing_pairs:
                outcome.skipped_existing += 1
                continue

            pair = ReportPair(
                company_id=company.id,
                earlier_report_id=earlier.id,
                later_report_id=later.id,
                gap_months=_gap_months(earlier, later),
                is_transition=earlier.transition_report or later.transition_report,
            )
            session.add(pair)
            existing_pairs.add((earlier.id, later.id))
            outcome.created.append((earlier.local_path, later.local_path))

    return outcome

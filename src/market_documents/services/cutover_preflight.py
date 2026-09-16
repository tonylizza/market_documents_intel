"""Track 7C.6 cutover preflight (docs/7c6-production-cutover.md Section 14).

Read-only check of whether the exact 7C.6 scope
(`cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE`/`NEW_PIPELINE_STRUCTURED_SCOPE`)
has the persisted 7C.1-7C.5 output it needs before the
`SEMANTIC_COMPARISON_CUTOVER_ENABLED` flag is turned on. Never mutates or
backfills anything -- a MISSING_DATA/UNRESOLVED verdict means "run the
relevant `units` pipeline stage first," not "fixed automatically."
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.company import Company
from market_documents.models.enums import ComparisonResponseStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.comparison_routing import ComparisonPathRouter
from market_documents.services.cutover_comparison import (
    NarrativeComparisonResponse,
    StructuredComparisonResponse,
    get_narrative_comparison,
    get_structured_comparison,
)
from market_documents.services.cutover_config import (
    NEW_PIPELINE_NARRATIVE_SCOPE,
    NEW_PIPELINE_STRUCTURED_SCOPE,
)

READY = "READY"
MISSING_DATA = "MISSING_DATA"
UNRESOLVED = "UNRESOLVED"
UNSUPPORTED = "UNSUPPORTED"


@dataclass(frozen=True)
class CutoverPreflightResult:
    scope_label: str
    verdict: str
    detail: str


def _reports_for_ticker(session: Session, ticker: str) -> list[Report]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        return []
    return session.scalars(select(Report).where(Report.company_id == company.id)).all()


def _pairs_for_ticker(session: Session, ticker: str) -> list[ReportPair]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        return []
    return session.scalars(select(ReportPair).where(ReportPair.company_id == company.id)).all()


def run_cutover_preflight(session: Session) -> list[CutoverPreflightResult]:
    """One result per configured 7C.6 scope entry -- never a global
    aggregate, since one narrative unit or table family can be READY while
    another is still MISSING_DATA."""
    router = ComparisonPathRouter(cutover_enabled=True)
    results: list[CutoverPreflightResult] = []

    for ticker, schedule, unit_key in sorted(NEW_PIPELINE_NARRATIVE_SCOPE, key=lambda t: (t[0], t[2])):
        label = f"{ticker} {schedule.value} {unit_key}"
        if not _reports_for_ticker(session, ticker):
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no reports found for this ticker"))
            continue
        pairs = _pairs_for_ticker(session, ticker)
        if not pairs:
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no report pairs found for this ticker"))
            continue
        responses = [
            r
            for p in pairs
            if isinstance(r := get_narrative_comparison(session, p, schedule, unit_key, router=router), NarrativeComparisonResponse)
        ]
        resolved = sum(1 for r in responses if r.status == ComparisonResponseStatus.RESOLVED)
        if resolved:
            results.append(CutoverPreflightResult(label, READY, f"{resolved}/{len(pairs)} pairs resolve MATCHED with lexical metrics"))
        elif responses:
            results.append(CutoverPreflightResult(label, UNRESOLVED, f"0/{len(pairs)} pairs resolved -- all UNRESOLVED_UPSTREAM/AMBIGUOUS/REVIEW_REQUIRED"))
        else:
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no SemanticUnitAlignmentRun found for any pair"))

    for ticker, table_family_key in sorted(NEW_PIPELINE_STRUCTURED_SCOPE):
        label = f"{ticker} {table_family_key}"
        if not _reports_for_ticker(session, ticker):
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no reports found for this ticker"))
            continue
        pairs = _pairs_for_ticker(session, ticker)
        if not pairs:
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no report pairs found for this ticker"))
            continue
        responses = [
            r
            for p in pairs
            if isinstance(r := get_structured_comparison(session, p, table_family_key, router=router), StructuredComparisonResponse)
        ]
        resolved = sum(1 for r in responses if r.status == ComparisonResponseStatus.RESOLVED)
        if resolved:
            results.append(CutoverPreflightResult(label, READY, f"{resolved}/{len(pairs)} pairs resolve with row/column/value-change data"))
        elif responses:
            results.append(CutoverPreflightResult(label, UNRESOLVED, f"0/{len(pairs)} pairs resolved"))
        else:
            results.append(CutoverPreflightResult(label, MISSING_DATA, "no StructuredTableAlignmentRun found for any pair"))

    return results

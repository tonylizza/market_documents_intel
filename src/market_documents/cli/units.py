"""Track 7C.1 CLI: schedule localization and headed-narrative semantic-unit
extraction, independent of the existing passage pipeline.

Deliberately minimal, per docs/7c1-schedule-localization-plan.md Section
5.4: `localize`, `extract`, `status` only. No `align` or `compare`
subcommand exists in 7C.1 -- alignment and comparison are out of scope for
this milestone.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
import typer

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.enums import NormalizedSchedule
from market_documents.models.report import Report
from market_documents.models.schedule import ScheduleInstance
from market_documents.models.semantic_unit import SemanticUnit
from market_documents.services.schedule_localization import get_current_localization_run, run_localization
from market_documents.services.semantic_unit_extraction import get_current_unit_run, run_extraction

app = typer.Typer(help="Track 7C.1: schedule localization + headed narrative semantic units.")

_DEFAULT_SCHEDULE = NormalizedSchedule.FINANCIAL_PERFORMANCE


def _reports_for_ticker(session: Session, ticker: str) -> list[Report]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        typer.echo(f"no company found for ticker {ticker!r}")
        raise typer.Exit(code=1)
    return sorted(
        session.scalars(select(Report).where(Report.company_id == company.id)).all(),
        key=lambda r: r.directory_year,
    )


def _resolve_schedule(schedule: str) -> NormalizedSchedule:
    try:
        return NormalizedSchedule(schedule.upper())
    except ValueError as exc:
        valid = ", ".join(s.value for s in NormalizedSchedule)
        typer.echo(f"unknown schedule {schedule!r}; valid values: {valid}")
        raise typer.Exit(code=1) from exc


@app.command("localize")
def localize_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
    force: bool = typer.Option(False, "--force", help="Re-run even if an identical successful run exists."),
) -> None:
    """Localize one normalized schedule for every report of one company."""
    resolved_schedule = _resolve_schedule(schedule)
    with get_session() as session:
        reports = _reports_for_ticker(session, ticker)
        for report in reports:
            outcome = run_localization(session, report, resolved_schedule, force=force)
            if outcome.ineligible:
                typer.echo(f"{report.directory_year}: ineligible -- {outcome.ineligible_reason}")
            elif outcome.skipped:
                typer.echo(f"{report.directory_year}: skipped -- {outcome.skip_reason}")
            else:
                run = outcome.run
                typer.echo(f"{report.directory_year}: {run.status.value}" + (f" -- {run.review_reason}" if run.review_reason else ""))


@app.command("extract")
def extract_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
    force: bool = typer.Option(False, "--force", help="Re-run even if an identical successful run exists."),
) -> None:
    """Extract every configured HEADED_NARRATIVE_UNIT for every report of one company."""
    resolved_schedule = _resolve_schedule(schedule)
    with get_session() as session:
        reports = _reports_for_ticker(session, ticker)
        for report in reports:
            outcome = run_extraction(session, report, resolved_schedule, force=force)
            if outcome.ineligible:
                typer.echo(f"{report.directory_year}: ineligible -- {outcome.ineligible_reason}")
            elif outcome.skipped:
                typer.echo(f"{report.directory_year}: skipped -- {outcome.skip_reason}")
            else:
                run = outcome.run
                typer.echo(f"{report.directory_year}: {run.status.value}" + (f" -- {run.review_reason}" if run.review_reason else ""))


@app.command("status")
def status_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
) -> None:
    """Print current schedule-localization and semantic-unit-extraction state per report."""
    resolved_schedule = _resolve_schedule(schedule)
    with get_session() as session:
        reports = _reports_for_ticker(session, ticker)
        for report in reports:
            loc_run = get_current_localization_run(session, report.id, resolved_schedule)
            loc_label = "none" if loc_run is None else loc_run.status.value
            instance_label = ""
            if loc_run is not None:
                instance = session.scalar(
                    select(ScheduleInstance).where(ScheduleInstance.schedule_localization_run_id == loc_run.id)
                )
                if instance is not None:
                    instance_label = f" schedule={instance.status.value} pp.{instance.start_page}-{instance.end_page}"

            unit_run = get_current_unit_run(session, report.id, resolved_schedule)
            unit_label = "none"
            unit_details = ""
            if unit_run is not None:
                unit_label = unit_run.status.value
                units = session.scalars(select(SemanticUnit).where(SemanticUnit.semantic_unit_run_id == unit_run.id)).all()
                parts = [f"{u.unit_key}={u.boundary_status.value}" for u in units]
                unit_details = " " + ", ".join(parts) if parts else ""

            typer.echo(f"{report.directory_year}: localization={loc_label}{instance_label} | units={unit_label}{unit_details}")

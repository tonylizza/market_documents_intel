"""Track 7C.1/7C.2/7C.3 CLI: schedule localization, headed-narrative
semantic-unit extraction, cross-year semantic-unit alignment, and
analytical eligibility routing + lexical comparison -- independent of the
existing passage pipeline.

Deliberately minimal, per docs/7c1-schedule-localization-plan.md Section
5.4, docs/7c2-semantic-unit-alignment.md, and
docs/7c3-analytical-eligibility-and-lexical-comparison.md: `localize`,
`extract`, `align`, `classify`, `status` only. No structured-table
subcommand exists yet -- that is out of scope for 7C.3.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
import typer

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.enums import AnalyticalMode, NormalizedSchedule
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.schedule import ScheduleInstance
from market_documents.models.semantic_unit import SemanticUnit
from market_documents.services.analytical_eligibility import get_current_decision_run, run_analytical_comparison
from market_documents.services.schedule_localization import get_current_localization_run, run_localization
from market_documents.services.semantic_unit_alignment import get_current_alignment_run, run_alignment
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


def _report_pairs_for_ticker(session: Session, ticker: str) -> list[ReportPair]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        typer.echo(f"no company found for ticker {ticker!r}")
        raise typer.Exit(code=1)
    return sorted(
        session.scalars(select(ReportPair).where(ReportPair.company_id == company.id)).all(),
        key=lambda p: p.earlier_report.directory_year,
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


@app.command("align")
def align_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
    force: bool = typer.Option(False, "--force", help="Re-run even if an identical successful run exists."),
) -> None:
    """Align SemanticUnit records across every adjacent-year ReportPair of one company (Track 7C.2)."""
    resolved_schedule = _resolve_schedule(schedule)
    with get_session() as session:
        pairs = _report_pairs_for_ticker(session, ticker)
        for pair in pairs:
            label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
            outcome = run_alignment(session, pair, resolved_schedule, force=force)
            if outcome.ineligible:
                typer.echo(f"{label}: ineligible -- {outcome.ineligible_reason}")
            elif outcome.skipped:
                typer.echo(f"{label}: skipped -- {outcome.skip_reason}")
            else:
                run = outcome.run
                typer.echo(f"{label}: {run.status.value}" + (f" -- {run.review_reason}" if run.review_reason else ""))
                for alignment in run.alignments:
                    earlier_key = alignment.earlier_semantic_unit.unit_key if alignment.earlier_semantic_unit else "-"
                    later_key = alignment.later_semantic_unit.unit_key if alignment.later_semantic_unit else "-"
                    typer.echo(
                        f"    {earlier_key} -> {later_key}: {alignment.status.value} ({alignment.confidence.value}) -- {alignment.evidence}"
                    )


@app.command("classify")
def classify_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
    force: bool = typer.Option(False, "--force", help="Re-run even if an identical successful run exists."),
) -> None:
    """Route SemanticUnitAlignments to an analytical comparison mode, and compute lexical metrics for LEXICAL_ONLY units (Track 7C.3)."""
    resolved_schedule = _resolve_schedule(schedule)
    with get_session() as session:
        pairs = _report_pairs_for_ticker(session, ticker)
        for pair in pairs:
            label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
            outcome = run_analytical_comparison(session, pair, resolved_schedule, force=force)
            if outcome.ineligible:
                typer.echo(f"{label}: ineligible -- {outcome.ineligible_reason}")
            elif outcome.skipped:
                typer.echo(f"{label}: skipped -- {outcome.skip_reason}")
            else:
                run = outcome.run
                typer.echo(f"{label}: {run.status.value}" + (f" -- {run.review_reason}" if run.review_reason else ""))
                for decision in run.decisions:
                    alignment = decision.semantic_unit_alignment
                    unit_key = (
                        alignment.later_semantic_unit.unit_key
                        if alignment.later_semantic_unit
                        else alignment.earlier_semantic_unit.unit_key
                    )
                    line = f"    {unit_key}: {decision.analytical_mode.value} ({decision.confidence.value}) -- {decision.reason}"
                    if decision.analytical_mode == AnalyticalMode.LEXICAL_ONLY and decision.lexical_comparison:
                        m = decision.lexical_comparison
                        line += (
                            f"\n        tfidf_cosine={m.tfidf_cosine} unigram_jaccard={m.unigram_jaccard} "
                            f"bigram_jaccard={m.bigram_jaccard} edit_sim={m.edit_similarity} seq_sim={m.sequence_similarity} "
                            f"words={m.earlier_word_count}->{m.later_word_count} ({m.word_count_change:+d})"
                        )
                    typer.echo(line)


@app.command("status")
def status_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    schedule: str = typer.Option("financial_performance", "--schedule", help="Only financial_performance is implemented in 7C.1."),
) -> None:
    """Print current schedule-localization, semantic-unit-extraction, semantic-unit-alignment, and analytical-decision state."""
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

        pairs = _report_pairs_for_ticker(session, ticker)
        for pair in pairs:
            label = f"{pair.earlier_report.directory_year}->{pair.later_report.directory_year}"
            alignment_run = get_current_alignment_run(session, pair.id, resolved_schedule)
            alignment_label = "none" if alignment_run is None else alignment_run.status.value
            decision_run = get_current_decision_run(session, pair.id, resolved_schedule)
            decision_label = "none" if decision_run is None else decision_run.status.value
            typer.echo(f"{label}: alignment={alignment_label} | analytical={decision_label}")

"""Track 7C.1a CLI: canonical PDF source extraction, independent of the
legacy extraction pipeline and of the 7C.1 schedule/unit CLI.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session
import typer

from market_documents.db.session import get_session
from market_documents.models.company import Company
from market_documents.models.report import Report
from market_documents.services.canonical_extraction import get_current_canonical_run, run_canonical_extraction

app = typer.Typer(help="Track 7C.1a: canonical, source-faithful PDF extraction.")


def _reports_for_ticker(session: Session, ticker: str) -> list[Report]:
    company = session.scalar(select(Company).where(Company.ticker == ticker.upper()))
    if company is None:
        typer.echo(f"no company found for ticker {ticker!r}")
        raise typer.Exit(code=1)
    return sorted(
        session.scalars(select(Report).where(Report.company_id == company.id)).all(),
        key=lambda r: r.directory_year,
    )


@app.command("extract")
def extract_cmd(
    ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL."),
    force: bool = typer.Option(False, "--force", help="Re-run even if an identical successful run exists."),
) -> None:
    """Build the canonical source representation for every report of one company."""
    with get_session() as session:
        reports = _reports_for_ticker(session, ticker)
        for report in reports:
            outcome = run_canonical_extraction(session, report, force=force)
            if outcome.skipped:
                typer.echo(f"{report.directory_year}: skipped -- {outcome.skip_reason}")
            else:
                run = outcome.run
                typer.echo(
                    f"{report.directory_year}: {run.status.value}"
                    + (f" -- {run.error_message}" if run.error_message else "")
                )


@app.command("status")
def status_cmd(ticker: str = typer.Argument(..., help="Company ticker, e.g. BEL.")) -> None:
    """Print current canonical-extraction state per report."""
    with get_session() as session:
        reports = _reports_for_ticker(session, ticker)
        for report in reports:
            run = get_current_canonical_run(session, report.id)
            label = "none" if run is None else f"{run.status.value} ({run.processed_page_count} pages)"
            typer.echo(f"{report.directory_year}: {label}")

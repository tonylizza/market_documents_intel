import typer
from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.pairing import build_pairs

app = typer.Typer(help="Report pair construction.")


@app.command()
def build() -> None:
    """Pair each validated report with its immediate predecessor by period_end."""
    with get_session() as session:
        outcome = build_pairs(session)

    typer.echo(f"Created {len(outcome.created)} pair(s), skipped {outcome.skipped_existing} existing")


@app.command("list")
def list_cmd() -> None:
    """List all report pairs."""
    with get_session() as session:
        pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id)).all()
        for pair in pairs:
            earlier = session.get(Report, pair.earlier_report_id)
            later = session.get(Report, pair.later_report_id)
            transition_flag = " [TRANSITION]" if pair.is_transition else ""
            typer.echo(
                f"{earlier.filename} -> {later.filename} "
                f"| gap={pair.gap_months}mo{transition_flag}"
            )

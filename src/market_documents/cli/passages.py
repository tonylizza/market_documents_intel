from pathlib import Path

import typer

from market_documents.db.session import get_session
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus
from market_documents.services import financial_language_export

app = typer.Typer(help="Passage-level financial-language signal export.")


@app.command("language-export")
def language_export_cmd(
    output: Path = typer.Option(..., "--output", "-o", help="Output CSV path."),
    ticker: str | None = typer.Option(None, "--ticker", help="Filter to one company ticker."),
    alignment_status: str | None = typer.Option(None, "--alignment-status", help="Filter to one AlignmentStatus."),
    confidence: str | None = typer.Option(None, "--confidence", help="Filter to one AlignmentConfidence."),
    category: str | None = typer.Option(None, "--category", help="Filter to one structured-content audit category."),
) -> None:
    """Export passage-level financial-language signals to CSV. Never
    includes passage text."""
    status_filter = AlignmentStatus(alignment_status.upper()) if alignment_status else None
    confidence_filter = AlignmentConfidence(confidence.upper()) if confidence else None

    with get_session() as session:
        rows = financial_language_export.build_passage_export_rows(
            session,
            ticker=ticker,
            alignment_status=status_filter,
            confidence=confidence_filter,
            category=category,
        )

    financial_language_export.write_passage_export_csv(rows, output)
    typer.echo(f"Wrote {len(rows)} row(s) to {output}")

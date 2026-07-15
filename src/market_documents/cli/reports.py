from pathlib import Path

import typer

from market_documents.config import get_settings
from market_documents.db.session import get_session
from market_documents.services.importing import import_manifest
from market_documents.services.metadata_inspection import inspect_discovered_reports
from market_documents.services.scanning import scan_directory, write_manifest_csv
from market_documents.services.validation import validate_reports

app = typer.Typer(help="Corpus discovery, import, and validation.")


@app.command()
def scan(
    directory: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    output: Path = typer.Option(
        Path("data/report_scan_manifest.csv"), "--output", "-o", help="Where to write the CSV manifest."
    ),
) -> None:
    """Recursively discover PDFs and emit a manifest CSV for human review."""
    rows = scan_directory(directory)
    write_manifest_csv(rows, output)
    typer.echo(f"Discovered {len(rows)} PDF(s). Manifest written to {output}")


@app.command("import")
def import_cmd(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Import a reviewed manifest CSV as provisional Report records."""
    settings = get_settings()
    with get_session() as session:
        outcome = import_manifest(session, manifest, settings.companies_config_path)

    typer.echo(f"Created {len(outcome.created)} report(s)")
    for path, reason in outcome.skipped:
        typer.echo(f"  skipped {path}: {reason}")
    for row_number, message in outcome.errors:
        typer.echo(f"  error (row {row_number}): {message}")

    if outcome.errors:
        raise typer.Exit(code=1)


@app.command("inspect-metadata")
def inspect_metadata_cmd() -> None:
    """Read the first pages of each DISCOVERED report's PDF to enrich metadata."""
    with get_session() as session:
        outcome = inspect_discovered_reports(session)

    typer.echo(f"Inspected {len(outcome.inspected)} report(s)")
    for path, reason in outcome.failed:
        typer.echo(f"  failed {path}: {reason}")


@app.command()
def validate() -> None:
    """Determine whether each report has sufficient metadata for downstream analysis."""
    with get_session() as session:
        outcome = validate_reports(session)

    typer.echo(
        f"Validated: {len(outcome.validated)}, "
        f"Needs review: {len(outcome.needs_review)}, "
        f"Rejected: {len(outcome.rejected)}"
    )

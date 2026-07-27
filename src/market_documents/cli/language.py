from pathlib import Path

import typer
from sqlalchemy import select

from market_documents.db.session import get_session
from market_documents.models.financial_language import FinancialLanguageDictionary
from market_documents.services import financial_language_audit as language_audit
from market_documents.services import financial_language_dictionary_import as dictionary_import

app = typer.Typer(help="Financial-language dictionary registration and audit.")


@app.command("dictionaries-list")
def dictionaries_list_cmd() -> None:
    """List every imported financial-language dictionary."""
    with get_session() as session:
        dictionaries = session.scalars(
            select(FinancialLanguageDictionary).order_by(
                FinancialLanguageDictionary.name, FinancialLanguageDictionary.created_at
            )
        ).all()
        for d in dictionaries:
            typer.echo(
                f"{d.name:24} version={d.version} terms={d.term_count} hash={d.source_hash[:12]} lang={d.language}"
            )


@app.command("dictionary-import")
def dictionary_import_cmd(
    name: str = typer.Option(..., "--name", help="Dictionary name (e.g. loughran_mcdonald, custom_domain_taxonomy)."),
    version: str = typer.Option(..., "--version", help="Dictionary version string."),
    path: Path = typer.Option(..., "--path", help="Local file path (CSV for Loughran-McDonald, YAML for custom taxonomy)."),
) -> None:
    """Import a financial-language dictionary from a local file.

    Never downloads anything -- the Loughran-McDonald dictionary's license
    requires obtaining the file directly; point this at your own local copy.
    """
    importer = dictionary_import.import_loughran_mcdonald if name == "loughran_mcdonald" else dictionary_import.import_custom_taxonomy
    with get_session() as session:
        try:
            dictionary, created = importer(session, path, version=version, name=name)
        except dictionary_import.DictionaryVersionConflictError as exc:
            typer.echo(f"Error: {exc}")
            raise typer.Exit(code=1) from exc

    if created:
        typer.echo(f"Imported {dictionary.name!r} version {dictionary.version!r}: {dictionary.term_count} term rows")
    else:
        typer.echo(f"Skipped: {dictionary.name!r} version {dictionary.version!r} already imported (identical file)")
    typer.echo(f"  source_hash={dictionary.source_hash[:16]} license={dictionary.license_notes}")


@app.command("dictionary-audit")
def dictionary_audit_cmd(
    csv_output: Path | None = typer.Option(None, "--csv", help="Write results to this CSV path instead of printing."),
) -> None:
    """Show every imported dictionary's lineage: source, version, hash, license, term count."""
    with get_session() as session:
        rows = language_audit.build_dictionary_audit_rows(session)

    if csv_output is not None:
        language_audit.write_dictionary_audit_csv(rows, csv_output)
        typer.echo(f"Wrote {len(rows)} row(s) to {csv_output}")
        return

    for row in rows:
        typer.echo(f"{row.name:24} version={row.version} terms={row.term_count} hash={row.source_hash[:12]}")
        typer.echo(f"  license: {row.license_notes}")

import typer

from market_documents.cli import db, pairs, reports
from market_documents.logging import setup_logging

app = typer.Typer(name="market-documents", help="JSE annual-report disclosure intelligence CLI.")
app.add_typer(db.app, name="db")
app.add_typer(reports.app, name="reports")
app.add_typer(pairs.app, name="pairs")


@app.callback()
def main() -> None:
    setup_logging()


if __name__ == "__main__":
    app()

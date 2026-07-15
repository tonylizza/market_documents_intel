from typer.testing import CliRunner

from market_documents.cli.main import app

runner = CliRunner()


def test_db_check_reports_all_ok(engine):
    result = runner.invoke(app, ["db", "check"])

    assert result.exit_code == 0, result.stdout
    assert "[OK]   database connectivity" in result.stdout
    assert "[OK]   pgvector extension enabled" in result.stdout
    assert "[OK]   migrations up to date" in result.stdout

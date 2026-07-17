from typer.testing import CliRunner

from market_documents.cli.main import app
from market_documents.services import feature_extraction as fe

from tests._feature_fixtures import build_ready_pair

runner = CliRunner()


def test_features_build_cmd_reports_quality_and_score(db_session, monkeypatch):
    pair, *_ = build_ready_pair(db_session, ticker="CLIB1")
    monkeypatch.setattr("market_documents.cli.pairs.get_session", lambda: _SessionCtx(db_session))

    result = runner.invoke(app, ["pairs", "features-build", str(pair.id)])

    assert result.exit_code == 0, result.stdout
    assert "quality=" in result.stdout


def test_features_status_cmd_filters_by_ticker(db_session, monkeypatch):
    pair_a, *_ = build_ready_pair(db_session, ticker="CLIFA")
    pair_b, *_ = build_ready_pair(db_session, ticker="CLIFB")
    fe.build_features(db_session, pair_a)
    fe.build_features(db_session, pair_b)
    monkeypatch.setattr("market_documents.cli.pairs.get_session", lambda: _SessionCtx(db_session))

    result = runner.invoke(app, ["pairs", "features-status", "--ticker", "CLIFA"])

    assert result.exit_code == 0, result.stdout
    assert "CLIFA" in result.stdout
    assert "CLIFB" not in result.stdout


class _SessionCtx:
    def __init__(self, session):
        self._session = session

    def __enter__(self):
        return self._session

    def __exit__(self, *exc_info):
        return False

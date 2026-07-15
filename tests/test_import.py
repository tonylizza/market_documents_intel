import csv
from pathlib import Path

from market_documents.models.company import Company
from market_documents.models.report import Report
from market_documents.services.importing import import_manifest

FIELDNAMES = ["ticker", "local_path", "filename", "sha256", "file_bytes", "directory_year"]


def _write_manifest(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def _row(local_path: str, sha256: str, ticker: str = "SUR", year: int = 2024) -> dict:
    return {
        "ticker": ticker,
        "local_path": local_path,
        "filename": Path(local_path).name,
        "sha256": sha256,
        "file_bytes": 1234,
        "directory_year": year,
    }


def test_import_creates_provisional_reports_with_unknown_period_end(
    db_session, tmp_path, companies_config_path
):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [_row("data/raw/SUR/2024/annual_report.pdf", "a" * 64)])

    outcome = import_manifest(db_session, manifest, companies_config_path)

    assert outcome.created == ["data/raw/SUR/2024/annual_report.pdf"]
    assert not outcome.errors

    report = db_session.query(Report).one()
    assert report.period_end is None
    assert report.directory_year == 2024

    company = db_session.query(Company).filter_by(ticker="SUR").one()
    assert report.company_id == company.id


def test_import_is_idempotent_on_rerun(db_session, tmp_path, companies_config_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [_row("data/raw/SUR/2024/annual_report.pdf", "a" * 64)])

    import_manifest(db_session, manifest, companies_config_path)
    outcome = import_manifest(db_session, manifest, companies_config_path)

    assert outcome.created == []
    assert outcome.skipped == [
        ("data/raw/SUR/2024/annual_report.pdf", "already imported (local_path exists)")
    ]
    assert db_session.query(Report).count() == 1


def test_import_detects_duplicate_hash_across_different_paths(
    db_session, tmp_path, companies_config_path
):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(
        manifest,
        [
            _row("data/raw/SUR/2024/annual_report.pdf", "b" * 64),
            _row("data/raw/SUR/2024/annual_report_copy.pdf", "b" * 64),
        ],
    )

    outcome = import_manifest(db_session, manifest, companies_config_path)

    assert outcome.created == ["data/raw/SUR/2024/annual_report.pdf"]
    assert outcome.skipped == [
        ("data/raw/SUR/2024/annual_report_copy.pdf", "duplicate sha256 within manifest")
    ]
    assert db_session.query(Report).count() == 1


def test_import_rejects_unknown_ticker(db_session, tmp_path, companies_config_path):
    manifest = tmp_path / "manifest.csv"
    _write_manifest(manifest, [_row("data/raw/ZZZ/2024/annual_report.pdf", "d" * 64, ticker="ZZZ")])

    outcome = import_manifest(db_session, manifest, companies_config_path)

    assert outcome.created == []
    assert len(outcome.errors) == 1
    assert "unknown ticker: ZZZ" in outcome.errors[0][1]
    assert db_session.query(Report).count() == 0

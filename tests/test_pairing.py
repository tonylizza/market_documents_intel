from datetime import date

from market_documents.models.company import Company
from market_documents.models.enums import MetadataStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.pairing import build_pairs


def _validated_report(company: Company, year: int, period_end: date) -> Report:
    return Report(
        company_id=company.id,
        local_path=f"data/raw/{company.ticker}/{year}/annual_report.pdf",
        filename="annual_report.pdf",
        sha256=f"{year}".rjust(64, "0"),
        directory_year=year,
        period_end=period_end,
        metadata_status=MetadataStatus.VALIDATED,
    )


def test_build_pairs_links_consecutive_validated_reports(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    r2021 = _validated_report(company, 2021, date(2021, 12, 31))
    r2022 = _validated_report(company, 2022, date(2022, 12, 31))
    r2023 = _validated_report(company, 2023, date(2023, 12, 31))
    db_session.add_all([r2021, r2022, r2023])
    db_session.flush()

    outcome = build_pairs(db_session)

    assert len(outcome.created) == 2
    pairs = db_session.query(ReportPair).order_by(ReportPair.gap_months).all()
    assert len(pairs) == 2
    assert all(p.gap_months == 12 for p in pairs)
    assert all(p.is_transition is False for p in pairs)


def test_build_pairs_is_idempotent(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    r2021 = _validated_report(company, 2021, date(2021, 12, 31))
    r2022 = _validated_report(company, 2022, date(2022, 12, 31))
    db_session.add_all([r2021, r2022])
    db_session.flush()

    first = build_pairs(db_session)
    second = build_pairs(db_session)

    assert len(first.created) == 1
    assert len(second.created) == 0
    assert second.skipped_existing == 1
    assert db_session.query(ReportPair).count() == 1


def test_build_pairs_excludes_reports_without_period_end_or_not_validated(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    validated_no_period_end = Report(
        company_id=company.id,
        local_path="data/raw/TST/2021/annual_report.pdf",
        filename="annual_report.pdf",
        sha256="1" * 64,
        directory_year=2021,
        period_end=None,
        metadata_status=MetadataStatus.VALIDATED,
    )
    needs_review_with_period_end = Report(
        company_id=company.id,
        local_path="data/raw/TST/2022/annual_report.pdf",
        filename="annual_report.pdf",
        sha256="2" * 64,
        directory_year=2022,
        period_end=date(2022, 12, 31),
        metadata_status=MetadataStatus.NEEDS_REVIEW,
    )
    db_session.add_all([validated_no_period_end, needs_review_with_period_end])
    db_session.flush()

    outcome = build_pairs(db_session)

    assert outcome.created == []
    assert db_session.query(ReportPair).count() == 0

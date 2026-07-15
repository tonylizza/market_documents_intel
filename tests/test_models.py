from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError

from market_documents.models.company import Company
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair


def _make_report(company: Company, suffix: str, **overrides) -> Report:
    defaults = dict(
        company_id=company.id,
        local_path=f"data/raw/{company.ticker}/{suffix}/annual_report.pdf",
        filename="annual_report.pdf",
        sha256=f"{suffix:0>64}",
        directory_year=2024,
    )
    defaults.update(overrides)
    return Report(**defaults)


def test_reports_with_null_period_end_can_coexist(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    db_session.add(_make_report(company, "a"))
    db_session.add(_make_report(company, "b"))
    db_session.flush()  # both period_end is None -- must not violate uniqueness

    reports = db_session.query(Report).filter_by(company_id=company.id).all()
    assert len(reports) == 2


def test_duplicate_period_end_for_same_company_rejected(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    db_session.add(_make_report(company, "a", period_end=date(2024, 12, 31)))
    db_session.flush()

    db_session.add(_make_report(company, "b", period_end=date(2024, 12, 31)))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_afrocentric_style_distinct_period_ends_for_same_label_allowed(db_session):
    """Two reports can both carry fiscal_label '2024' as long as period_end differs."""
    company = Company(ticker="ACT", company_name="AfroCentric Investment Corporation Limited")
    db_session.add(company)
    db_session.flush()

    db_session.add(
        _make_report(company, "a", fiscal_label="2024", period_end=date(2024, 2, 29))
    )
    db_session.add(
        _make_report(company, "b", fiscal_label="2024", period_end=date(2024, 12, 31))
    )
    db_session.flush()

    reports = db_session.query(Report).filter_by(company_id=company.id).all()
    assert len(reports) == 2
    assert {r.fiscal_label for r in reports} == {"2024"}
    assert {r.period_end for r in reports} == {date(2024, 2, 29), date(2024, 12, 31)}


def test_duplicate_local_path_rejected(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    r1 = _make_report(company, "a")
    db_session.add(r1)
    db_session.flush()

    r2 = _make_report(company, "a", sha256="b" * 64)
    db_session.add(r2)
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_sha256_rejected(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    db_session.add(_make_report(company, "a", sha256="c" * 64))
    db_session.flush()

    db_session.add(_make_report(company, "b", sha256="c" * 64))
    with pytest.raises(IntegrityError):
        db_session.flush()


def test_duplicate_report_pair_rejected_at_db_level(db_session):
    company = Company(ticker="TST", company_name="Test Co")
    db_session.add(company)
    db_session.flush()

    r1 = _make_report(company, "a", period_end=date(2022, 12, 31))
    r2 = _make_report(company, "b", period_end=date(2023, 12, 31))
    db_session.add_all([r1, r2])
    db_session.flush()

    db_session.add(
        ReportPair(company_id=company.id, earlier_report_id=r1.id, later_report_id=r2.id, gap_months=12)
    )
    db_session.flush()

    db_session.add(
        ReportPair(company_id=company.id, earlier_report_id=r1.id, later_report_id=r2.id, gap_months=12)
    )
    with pytest.raises(IntegrityError):
        db_session.flush()

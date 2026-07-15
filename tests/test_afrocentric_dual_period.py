from datetime import date

from market_documents.models.company import Company
from market_documents.models.enums import MetadataStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.pairing import build_pairs


def test_afrocentric_dual_2024_reports_register_and_pair_distinctly(db_session):
    """AfroCentric-style case: two reports both labeled fiscal_label '2024' but
    covering different, non-overlapping periods (e.g. a short stub period
    followed by a realigned year-end) must both be registered and validated
    independently, never merged or treated as duplicates.
    """
    company = Company(ticker="ACT", company_name="AfroCentric Investment Corporation Limited")
    db_session.add(company)
    db_session.flush()

    stub_period = Report(
        company_id=company.id,
        local_path="data/raw/ACT/2024/annual_report_stub.pdf",
        filename="annual_report_stub.pdf",
        sha256="1" * 64,
        directory_year=2024,
        fiscal_label="2024",
        period_end=date(2024, 2, 29),
        reporting_months=2,
        transition_report=True,
        metadata_status=MetadataStatus.VALIDATED,
    )
    realigned_period = Report(
        company_id=company.id,
        local_path="data/raw/ACT/2024/annual_report.pdf",
        filename="annual_report.pdf",
        sha256="2" * 64,
        directory_year=2024,
        fiscal_label="2024",
        period_end=date(2024, 12, 31),
        reporting_months=12,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add_all([stub_period, realigned_period])
    db_session.flush()  # must not raise -- distinct period_end values coexist

    reports = db_session.query(Report).filter_by(company_id=company.id).all()
    assert len(reports) == 2

    outcome = build_pairs(db_session)

    assert outcome.created == [
        ("data/raw/ACT/2024/annual_report_stub.pdf", "data/raw/ACT/2024/annual_report.pdf")
    ]

    pair = db_session.query(ReportPair).one()
    assert pair.earlier_report_id == stub_period.id
    assert pair.later_report_id == realigned_period.id
    assert pair.gap_months == 10
    # The stub period is explicitly flagged as a transition report -- the pair
    # must be flagged too, so downstream analysis can exclude it as "primary".
    assert pair.is_transition is True

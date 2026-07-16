import csv
from datetime import date
from pathlib import Path

import fitz
import pytest

from market_documents.models.company import Company
from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services import metadata_review
from market_documents.services.pairing import build_pairs
from market_documents.services.validation import validate_reports


def _build_pdf(path: Path, page_texts: list[str]) -> None:
    doc = fitz.open()
    for text in page_texts:
        page = doc.new_page(width=400, height=600)
        page.insert_textbox(fitz.Rect(50, 50, 350, 550), text, fontsize=10)
    doc.save(str(path))
    doc.close()


def _company(db_session, ticker="TST") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, tmp_path: Path, name: str, page_texts: list[str], **overrides) -> Report:
    pdf_path = tmp_path / f"{name}.pdf"
    _build_pdf(pdf_path, page_texts)
    defaults = dict(
        company_id=company.id,
        local_path=str(pdf_path),
        filename=pdf_path.name,
        sha256=name.rjust(64, "0"),
        directory_year=2024,
        page_count=len(page_texts),
        metadata_status=MetadataStatus.NEEDS_REVIEW,
        metadata_source=MetadataSource.PDF,
    )
    defaults.update(overrides)
    report = Report(**defaults)
    db_session.add(report)
    db_session.flush()
    return report


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_export_includes_unresolved_reports(db_session, tmp_path):
    company = _company(db_session)
    _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    rows = metadata_review.build_metadata_review_rows(db_session)

    assert len(rows) == 1
    assert rows[0].metadata_status == "NEEDS_REVIEW"


def test_export_excludes_validated_reports_by_default(db_session, tmp_path):
    company = _company(db_session)
    _report(
        db_session,
        company,
        tmp_path,
        "a",
        ["year ended 30 June 2023"],
        metadata_status=MetadataStatus.VALIDATED,
        period_end=date(2023, 6, 30),
    )

    rows = metadata_review.build_metadata_review_rows(db_session)
    assert rows == []


def test_export_includes_validated_reports_when_requested(db_session, tmp_path):
    company = _company(db_session)
    _report(
        db_session,
        company,
        tmp_path,
        "a",
        ["year ended 30 June 2023"],
        metadata_status=MetadataStatus.VALIDATED,
        period_end=date(2023, 6, 30),
    )

    rows = metadata_review.build_metadata_review_rows(db_session, include_validated=True)
    assert len(rows) == 1


def test_export_detects_evidence_phrase_and_page(db_session, tmp_path):
    company = _company(db_session)
    _report(
        db_session,
        company,
        tmp_path,
        "a",
        ["some cover text", "financial statements for the year ended 30 June 2023"],
    )

    rows = metadata_review.build_metadata_review_rows(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert row.detected_fiscal_phrase is not None
    assert "30 June 2023" in row.detected_fiscal_phrase
    assert row.detected_phrase_page == 2
    assert row.confidence == "HIGH"
    assert row.detected_period_end == "2023-06-30"
    assert row.proposed_period_end == "2023-06-30"


def test_export_ambiguous_when_multiple_distinct_dates_found(db_session, tmp_path):
    company = _company(db_session)
    _report(
        db_session,
        company,
        tmp_path,
        "a",
        [
            "financial statements for the year ended 30 June 2023",
            "comparative figures for the year ended 30 June 2022",
        ],
    )

    rows = metadata_review.build_metadata_review_rows(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert row.confidence == "MEDIUM"
    # First-found date is proposed; the alternate is surfaced, not hidden.
    assert row.proposed_period_end == "2023-06-30"
    assert row.ambiguity_reason is not None
    assert "2022-06-30" in row.ambiguity_reason


def test_export_no_detection_represented_explicitly(db_session, tmp_path):
    company = _company(db_session)
    _report(db_session, company, tmp_path, "a", ["nothing relevant here"])

    rows = metadata_review.build_metadata_review_rows(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert row.confidence == "NONE"
    assert row.detected_period_end is None
    assert row.proposed_period_end is None
    assert row.ambiguity_reason == "no fiscal-period phrase detected in scanned pages"


def test_export_ordering_is_deterministic(db_session, tmp_path):
    company_a = _company(db_session, ticker="AAA")
    company_b = _company(db_session, ticker="BBB")
    _report(db_session, company_b, tmp_path, "b2024", ["nothing"], directory_year=2024)
    _report(db_session, company_a, tmp_path, "a2023", ["nothing"], directory_year=2023)
    _report(db_session, company_a, tmp_path, "a2022", ["nothing"], directory_year=2022)

    first = metadata_review.build_metadata_review_rows(db_session)
    second = metadata_review.build_metadata_review_rows(db_session)

    order = [(r.ticker, r.directory_year) for r in first]
    assert order == [("AAA", 2022), ("AAA", 2023), ("BBB", 2024)]
    assert order == [(r.ticker, r.directory_year) for r in second]


def test_write_metadata_review_csv_round_trips(db_session, tmp_path):
    company = _company(db_session)
    _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    rows = metadata_review.build_metadata_review_rows(db_session)
    csv_path = tmp_path / "review.csv"
    metadata_review.write_metadata_review_csv(rows, csv_path)

    with csv_path.open() as f:
        csv_rows = list(csv.DictReader(f))

    assert len(csv_rows) == 1
    assert csv_rows[0]["proposed_period_end"] == "2023-06-30"
    assert csv_rows[0]["reviewer_status"] == "UNREVIEWED"


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _write_import_csv(path: Path, rows: list[dict]) -> None:
    fieldnames = [
        "report_id",
        "reviewer_status",
        "proposed_period_start",
        "proposed_period_end",
        "proposed_publication_date",
        "proposed_reporting_months",
        "proposed_transition_report",
        "reviewer_notes",
    ]
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({name: row.get(name, "") for name in fieldnames})


def test_import_confirmed_row_applies(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [{"report_id": str(report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2023-06-30"}],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == [str(report.id)]
    db_session.refresh(report)
    assert report.period_end == date(2023, 6, 30)
    assert report.metadata_source == MetadataSource.MANUAL


def test_import_corrected_row_applies(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {
                "report_id": str(report.id),
                "reviewer_status": "CORRECTED",
                "proposed_period_end": "2023-12-31",
                "reviewer_notes": "cover page date was misleading; confirmed via note 1",
            }
        ],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == [str(report.id)]
    db_session.refresh(report)
    assert report.period_end == date(2023, 12, 31)
    assert "misleading" in report.validation_notes


@pytest.mark.parametrize("status", ["UNREVIEWED", "REJECTED", "NEEDS_FURTHER_REVIEW"])
def test_import_non_applicable_status_is_skipped(db_session, tmp_path, status):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(csv_path, [{"report_id": str(report.id), "reviewer_status": status}])

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.skipped) == 1
    db_session.refresh(report)
    assert report.period_end is None


def test_import_missing_period_end_rejected(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(csv_path, [{"report_id": str(report.id), "reviewer_status": "CONFIRMED"}])

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.invalid) == 1


def test_import_invalid_date_rejected(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [{"report_id": str(report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "not-a-date"}],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.invalid) == 1


def test_import_period_start_after_period_end_rejected(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {
                "report_id": str(report.id),
                "reviewer_status": "CONFIRMED",
                "proposed_period_start": "2023-07-01",
                "proposed_period_end": "2023-06-30",
            }
        ],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.invalid) == 1


def test_import_inconsistent_reporting_months_rejected(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {
                "report_id": str(report.id),
                "reviewer_status": "CONFIRMED",
                "proposed_period_start": "2023-01-01",
                "proposed_period_end": "2023-06-30",
                "proposed_reporting_months": "12",
            }
        ],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.invalid) == 1


def test_import_duplicate_company_period_end_conflict(db_session, tmp_path):
    company = _company(db_session)
    existing = _report(
        db_session,
        company,
        tmp_path,
        "existing",
        ["year ended 30 June 2023"],
        period_end=date(2023, 6, 30),
        metadata_status=MetadataStatus.VALIDATED,
    )
    new_report = _report(db_session, company, tmp_path, "new", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [{"report_id": str(new_report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2023-06-30"}],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.conflicted) == 1
    db_session.refresh(new_report)
    assert new_report.period_end is None
    db_session.refresh(existing)
    assert existing.period_end == date(2023, 6, 30)  # untouched


def test_import_existing_different_period_end_conflict(db_session, tmp_path):
    company = _company(db_session)
    report = _report(
        db_session,
        company,
        tmp_path,
        "a",
        ["year ended 30 June 2023"],
        period_end=date(2023, 6, 30),
        metadata_status=MetadataStatus.VALIDATED,
    )

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [{"report_id": str(report.id), "reviewer_status": "CORRECTED", "proposed_period_end": "2023-12-31"}],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == []
    assert len(outcome.conflicted) == 1
    db_session.refresh(report)
    assert report.period_end == date(2023, 6, 30)  # never silently overwritten


def test_import_sets_manual_source_provenance(db_session, tmp_path):
    company = _company(db_session)
    report = _report(
        db_session, company, tmp_path, "a", ["year ended 30 June 2023"], metadata_source=MetadataSource.PDF
    )

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [{"report_id": str(report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2023-06-30"}],
    )
    metadata_review.import_metadata_review(db_session, csv_path)

    db_session.refresh(report)
    assert report.metadata_source == MetadataSource.MANUAL


def test_import_reviewer_notes_preserved(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {
                "report_id": str(report.id),
                "reviewer_status": "CONFIRMED",
                "proposed_period_end": "2023-06-30",
                "reviewer_notes": "verified against page 1 cover statement",
            }
        ],
    )
    metadata_review.import_metadata_review(db_session, csv_path)

    db_session.refresh(report)
    assert "verified against page 1 cover statement" in report.validation_notes


def test_import_identical_reimport_is_idempotent(db_session, tmp_path):
    company = _company(db_session)
    report = _report(db_session, company, tmp_path, "a", ["year ended 30 June 2023"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {
                "report_id": str(report.id),
                "reviewer_status": "CONFIRMED",
                "proposed_period_end": "2023-06-30",
                "reviewer_notes": "confirmed",
            }
        ],
    )

    first = metadata_review.import_metadata_review(db_session, csv_path)
    second = metadata_review.import_metadata_review(db_session, csv_path)

    assert first.applied == [str(report.id)]
    assert second.applied == []
    assert second.unchanged == [str(report.id)]

    db_session.refresh(report)
    # Notes must not accumulate duplicate text across repeated imports.
    assert report.validation_notes.count("confirmed") == 1


def test_import_mixed_valid_and_invalid_rows(db_session, tmp_path):
    company = _company(db_session)
    good_report = _report(db_session, company, tmp_path, "good", ["year ended 30 June 2023"])
    bad_report = _report(db_session, company, tmp_path, "bad", ["year ended 30 June 2022"])

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {"report_id": str(good_report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2023-06-30"},
            {"report_id": str(bad_report.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "not-a-date"},
        ],
    )

    outcome = metadata_review.import_metadata_review(db_session, csv_path)

    assert outcome.applied == [str(good_report.id)]
    assert len(outcome.invalid) == 1


# ---------------------------------------------------------------------------
# End-to-end: export -> (simulated review) -> import -> validate -> pair
# ---------------------------------------------------------------------------


def test_confirmed_metadata_becomes_eligible_for_validation_and_pairing(db_session, tmp_path):
    company = _company(db_session)
    earlier = _report(db_session, company, tmp_path, "earlier", ["year ended 30 June 2022"], directory_year=2022)
    later = _report(db_session, company, tmp_path, "later", ["year ended 30 June 2023"], directory_year=2023)

    csv_path = tmp_path / "reviewed.csv"
    _write_import_csv(
        csv_path,
        [
            {"report_id": str(earlier.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2022-06-30"},
            {"report_id": str(later.id), "reviewer_status": "CONFIRMED", "proposed_period_end": "2023-06-30"},
        ],
    )
    import_outcome = metadata_review.import_metadata_review(db_session, csv_path)
    assert len(import_outcome.applied) == 2

    validate_outcome = validate_reports(db_session)
    assert set(validate_outcome.validated) == {earlier.local_path, later.local_path}

    pairing_outcome = build_pairs(db_session)
    assert pairing_outcome.created == [(earlier.local_path, later.local_path)]

    pairs = db_session.query(ReportPair).all()
    assert len(pairs) == 1
    assert pairs[0].gap_months == 12


def test_unresolved_metadata_remains_ineligible_for_pairing(db_session, tmp_path):
    company = _company(db_session)
    _report(db_session, company, tmp_path, "a", ["nothing detected here"])

    validate_reports(db_session)
    outcome = build_pairs(db_session)

    assert outcome.created == []

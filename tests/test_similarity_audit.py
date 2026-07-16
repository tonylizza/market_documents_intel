import csv
from datetime import UTC, datetime, date

import pytest

from market_documents.models.company import Company
from market_documents.models.enums import ExtractionQuality, ExtractionStatus, MetadataStatus, SimilarityResultQuality
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services import similarity
from market_documents.services.narrative_construction import compute_content_hash
from market_documents.services.similarity_audit import (
    build_similarity_audit_rows,
    rank_by_metric,
    write_similarity_audit_csv,
)

TEXT_A = (
    "The group delivered a resilient operating performance during the period "
    "under review, with revenue growth recorded across all reporting segments."
)
TEXT_B = (
    "The group delivered a strong operating performance during the period "
    "under review, with revenue growth recorded across most reporting segments."
)


def _company(db_session, ticker="TST") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, path_suffix: str, period_end: date | None = None) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{path_suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{path_suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
        period_end=period_end or date(year, 12, 31),
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    return report


def _extraction_run(
    db_session,
    report: Report,
    *,
    status: ExtractionStatus = ExtractionStatus.COMPLETED,
    extraction_quality: ExtractionQuality | None = ExtractionQuality.GOOD,
) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="test-hash",
        status=status,
        extraction_quality=extraction_quality,
        started_at=datetime.now(UTC),
        completed_at=datetime.now(UTC),
        encrypted_pdf_handled=False,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _narrative(db_session, run: ExtractionRun, text: str) -> NarrativeDocument:
    doc = NarrativeDocument(
        extraction_run_id=run.id,
        report_id=run.report_id,
        cleaned_text=text,
        word_count=len(text.split()),
        content_hash=compute_content_hash(text),
    )
    db_session.add(doc)
    db_session.flush()
    return doc


def _pair(db_session, company: Company, earlier: Report, later: Report, **kwargs) -> ReportPair:
    pair = ReportPair(
        company_id=company.id,
        earlier_report_id=earlier.id,
        later_report_id=later.id,
        gap_months=kwargs.pop("gap_months", 12),
        is_transition=kwargs.pop("is_transition", False),
    )
    db_session.add(pair)
    db_session.flush()
    return pair


def _scored_pair(db_session, ticker: str, *, text_a=TEXT_A, text_b=TEXT_B, **pair_kwargs) -> ReportPair:
    company = _company(db_session, ticker=ticker)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, text_a)
    _narrative(db_session, later_run, text_b)
    pair = _pair(db_session, company, earlier_report, later_report, **pair_kwargs)
    similarity.score_pair(db_session, pair)
    return pair


# ---------------------------------------------------------------------------
# Audit rows
# ---------------------------------------------------------------------------


def test_audit_works_with_no_pairs_scored_at_all(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    _pair(db_session, company, earlier_report, later_report)

    rows = build_similarity_audit_rows(db_session)

    assert len(rows) == 1
    assert rows[0].similarity_run_status is None
    assert rows[0].result_quality is None
    assert rows[0].lexical_cosine_similarity is None


def test_audit_includes_metrics_after_scoring(db_session):
    pair = _scored_pair(db_session, "TST")

    rows = build_similarity_audit_rows(db_session)

    assert len(rows) == 1
    row = rows[0]
    assert row.ticker == "TST"
    assert row.report_pair_id == str(pair.id)
    assert row.similarity_run_status is not None
    assert row.result_quality is not None
    assert row.lexical_cosine_similarity is not None
    assert 0.0 <= row.lexical_cosine_similarity <= 1.0
    assert row.earlier_narrative_word_count is not None
    assert row.configuration_hash is not None
    assert row.algorithm_version is not None


def test_audit_surfaces_failed_run_when_no_successful_run_exists(db_session, monkeypatch):
    company = _company(db_session, ticker="FLD")
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, TEXT_A)
    _narrative(db_session, later_run, TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic failure")

    monkeypatch.setattr(similarity, "compute_metrics", _boom)
    similarity.score_pair(db_session, pair)

    rows = build_similarity_audit_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.similarity_run_status == "FAILED"
    assert row.result_quality is None
    assert row.exclusion_or_review_reason is not None
    assert "synthetic failure" in row.exclusion_or_review_reason


def test_audit_handles_transition_pairs(db_session):
    pair = _scored_pair(db_session, "TRN", is_transition=True)

    rows = build_similarity_audit_rows(db_session)

    assert len(rows) == 1
    assert rows[0].is_transition is True
    assert rows[0].primary_analysis_eligible is False


def test_audit_handles_mix_of_scored_and_unscored_pairs(db_session):
    _scored_pair(db_session, "AAA")

    company = _company(db_session, ticker="BBB")
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    _pair(db_session, company, earlier_report, later_report)

    rows = build_similarity_audit_rows(db_session)
    assert len(rows) == 2
    by_ticker = {r.ticker: r for r in rows}
    assert by_ticker["AAA"].similarity_run_status is not None
    assert by_ticker["BBB"].similarity_run_status is None


def test_write_similarity_audit_csv_round_trips(db_session, tmp_path):
    _scored_pair(db_session, "CSV")

    rows = build_similarity_audit_rows(db_session)
    csv_path = tmp_path / "similarity_audit.csv"
    write_similarity_audit_csv(rows, csv_path)

    with csv_path.open() as f:
        reader = csv.DictReader(f)
        csv_rows = list(reader)

    assert len(csv_rows) == 1
    assert csv_rows[0]["ticker"] == "CSV"
    assert csv_rows[0]["lexical_cosine_similarity"] != ""


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------


def test_rank_by_metric_ascending_and_descending(db_session):
    # Pair A: near-identical documents -> high similarity (low change).
    _scored_pair(db_session, "HIGH", text_a=TEXT_A, text_b=TEXT_A)
    # Pair B: substantially different documents -> lower similarity (high change).
    _scored_pair(
        db_session,
        "LOW",
        text_a="revenue increased due to strong regional demand and pricing power",
        text_b="a wholly unrelated discussion about supply chain logistics disruptions",
    )

    ascending = rank_by_metric(db_session, "lexical_cosine_similarity", ascending=True)
    assert [r.ticker for r in ascending] == ["LOW", "HIGH"]

    descending = rank_by_metric(db_session, "lexical_cosine_similarity", ascending=False)
    assert [r.ticker for r in descending] == ["HIGH", "LOW"]


def test_rank_by_metric_assigns_sequential_ranks(db_session):
    _scored_pair(db_session, "AAA")
    _scored_pair(db_session, "BBB")

    rows = rank_by_metric(db_session, "lexical_cosine_similarity")
    assert [r.rank for r in rows] == list(range(1, len(rows) + 1))


def test_rank_by_metric_excludes_transitions_by_default(db_session):
    _scored_pair(db_session, "NRM")
    _scored_pair(db_session, "TRN", is_transition=True)

    rows = rank_by_metric(db_session, "lexical_cosine_similarity")
    assert "TRN" not in [r.ticker for r in rows]


def test_rank_by_metric_includes_transitions_when_requested(db_session):
    _scored_pair(db_session, "NRM")
    _scored_pair(db_session, "TRN", is_transition=True)

    rows = rank_by_metric(db_session, "lexical_cosine_similarity", include_transitions=True)
    assert "TRN" in [r.ticker for r in rows]


def test_rank_by_metric_ticker_filter(db_session):
    _scored_pair(db_session, "AAA")
    _scored_pair(db_session, "BBB")

    rows = rank_by_metric(db_session, "lexical_cosine_similarity", ticker="aaa")
    assert [r.ticker for r in rows] == ["AAA"]


def test_rank_by_metric_quality_filter(db_session):
    # TEXT_A/TEXT_B are short enough to trip the min-words review trigger,
    # so this test needs its own long-enough text to actually reach GOOD.
    long_text_a = " ".join(f"paragraph{i} discusses financial performance" for i in range(60))
    long_text_b = long_text_a + " with an additional closing remark appended"
    _scored_pair(db_session, "GOD", text_a=long_text_a, text_b=long_text_b)

    rows_good = rank_by_metric(
        db_session, "lexical_cosine_similarity", quality_filter=SimilarityResultQuality.GOOD
    )
    rows_needs_review = rank_by_metric(
        db_session, "lexical_cosine_similarity", quality_filter=SimilarityResultQuality.NEEDS_REVIEW
    )
    assert len(rows_good) == 1
    assert len(rows_needs_review) == 0


def test_rank_by_metric_limit(db_session):
    _scored_pair(db_session, "AAA")
    _scored_pair(db_session, "BBB")

    rows = rank_by_metric(db_session, "lexical_cosine_similarity", limit=1)
    assert len(rows) == 1


def test_rank_by_metric_never_ranks_missing_comparisons(db_session):
    _scored_pair(db_session, "AAA")

    company = _company(db_session, ticker="NEV")
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    _pair(db_session, company, earlier_report, later_report)  # never scored

    rows = rank_by_metric(db_session, "lexical_cosine_similarity")
    assert "NEV" not in [r.ticker for r in rows]


def test_rank_by_metric_deterministic_ties(db_session):
    # Identical texts on both pairs -> identical cosine score -> tie broken
    # deterministically by report_pair_id.
    _scored_pair(db_session, "AAA", text_a=TEXT_A, text_b=TEXT_A)
    _scored_pair(db_session, "BBB", text_a=TEXT_A, text_b=TEXT_A)

    first_run = rank_by_metric(db_session, "lexical_cosine_similarity")
    second_run = rank_by_metric(db_session, "lexical_cosine_similarity")
    assert [r.report_pair_id for r in first_run] == [r.report_pair_id for r in second_run]


def test_rank_by_metric_word_count_change_higher_means_more_growth(db_session):
    short_growth = _scored_pair(
        db_session, "SML", text_a="alpha beta gamma", text_b="alpha beta gamma delta"
    )
    big_growth = _scored_pair(
        db_session,
        "BIG",
        text_a="alpha beta gamma",
        text_b=" ".join(f"word{i}" for i in range(500)),
    )

    rows = rank_by_metric(db_session, "word_count_change", ascending=False)
    assert rows[0].ticker == "BIG"


def test_rank_by_metric_rejects_unsupported_metric(db_session):
    with pytest.raises(ValueError, match="unsupported ranking metric"):
        rank_by_metric(db_session, "not_a_real_metric")

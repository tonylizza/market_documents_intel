from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from market_documents.exceptions import PairNotEligibleError
from market_documents.models.company import Company
from market_documents.models.enums import (
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    SimilarityResultQuality,
    SimilarityRunStatus,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.similarity import DocumentSimilarity, SimilarityRun
from market_documents.services import similarity
from market_documents.services.narrative_construction import compute_content_hash

GOOD_TEXT_A = (
    "The group delivered a resilient operating performance during the period "
    "under review, with revenue growth recorded across all reporting segments "
    "and continued margin discipline throughout the year."
)
GOOD_TEXT_B = (
    "The group delivered a strong operating performance during the period "
    "under review, with revenue growth recorded across most reporting segments "
    "and improved margin discipline throughout the year."
)


def _company(db_session, ticker="TST") -> Company:
    company = Company(ticker=ticker, company_name="Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, path_suffix: str) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{path_suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{path_suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
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
    completed_at: datetime | None = None,
) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="test-hash",
        status=status,
        extraction_quality=extraction_quality,
        started_at=datetime.now(UTC),
        completed_at=completed_at or datetime.now(UTC),
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


def _fully_scoreable_pair(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)
    return pair


# ---------------------------------------------------------------------------
# select_source_narratives (eligibility)
# ---------------------------------------------------------------------------


def test_select_source_narratives_success(db_session):
    pair = _fully_scoreable_pair(db_session)
    selection = similarity.select_source_narratives(db_session, pair)
    assert selection.earlier_narrative.cleaned_text == GOOD_TEXT_A
    assert selection.later_narrative.cleaned_text == GOOD_TEXT_B


def test_select_source_narratives_missing_extraction_raises(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    with pytest.raises(PairNotEligibleError, match="earlier report has no current successful extraction"):
        similarity.select_source_narratives(db_session, pair)


def test_select_source_narratives_extraction_quality_failed_raises(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report, extraction_quality=ExtractionQuality.FAILED)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    with pytest.raises(PairNotEligibleError, match="FAILED"):
        similarity.select_source_narratives(db_session, pair)


def test_select_source_narratives_needs_review_extraction_is_eligible(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report, extraction_quality=ExtractionQuality.NEEDS_REVIEW)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    selection = similarity.select_source_narratives(db_session, pair)
    assert selection.earlier_run.extraction_quality == ExtractionQuality.NEEDS_REVIEW


def test_select_source_narratives_usable_extraction_is_eligible(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report, extraction_quality=ExtractionQuality.USABLE)
    later_run = _extraction_run(db_session, later_report, extraction_quality=ExtractionQuality.USABLE)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    selection = similarity.select_source_narratives(db_session, pair)
    assert selection.earlier_run.extraction_quality == ExtractionQuality.USABLE


def test_select_source_narratives_missing_narrative_document_raises(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    _extraction_run(db_session, earlier_report)  # no NarrativeDocument attached
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    with pytest.raises(PairNotEligibleError, match="no narrative document"):
        similarity.select_source_narratives(db_session, pair)


def test_select_source_narratives_empty_narrative_raises(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, "")
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    with pytest.raises(PairNotEligibleError, match="empty"):
        similarity.select_source_narratives(db_session, pair)


def test_select_source_narratives_prefers_latest_successful_extraction_over_failed_rerun(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")

    first_run = _extraction_run(
        db_session, earlier_report, completed_at=datetime(2024, 1, 1, tzinfo=UTC)
    )
    first_narrative = _narrative(db_session, first_run, GOOD_TEXT_A)
    # A later rerun that mechanically failed must never become "current".
    _extraction_run(
        db_session,
        earlier_report,
        status=ExtractionStatus.FAILED,
        extraction_quality=None,
        completed_at=datetime(2024, 6, 1, tzinfo=UTC),
    )

    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair = _pair(db_session, company, earlier_report, later_report)

    selection = similarity.select_source_narratives(db_session, pair)
    assert selection.earlier_narrative.id == first_narrative.id


# ---------------------------------------------------------------------------
# score_pair persistence and idempotency
# ---------------------------------------------------------------------------


def test_score_pair_persists_similarity_run_and_document_similarity(db_session):
    pair = _fully_scoreable_pair(db_session)
    outcome = similarity.score_pair(db_session, pair)

    assert not outcome.ineligible
    assert not outcome.skipped
    run = outcome.run
    assert run is not None
    assert run.status in (SimilarityRunStatus.COMPLETED, SimilarityRunStatus.COMPLETED_WITH_WARNINGS)
    assert run.completed_at is not None
    assert run.algorithm_version
    assert run.configuration_hash

    doc_similarity = db_session.scalar(
        select(DocumentSimilarity).where(DocumentSimilarity.similarity_run_id == run.id)
    )
    assert doc_similarity is not None
    assert doc_similarity.lexical_cosine_similarity is not None
    assert 0.0 <= doc_similarity.lexical_cosine_similarity <= 1.0
    assert doc_similarity.report_pair_id == pair.id
    assert doc_similarity.earlier_report_id == pair.earlier_report_id
    assert doc_similarity.later_report_id == pair.later_report_id


def test_score_pair_ineligible_creates_no_similarity_run(db_session):
    company = _company(db_session)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    pair = _pair(db_session, company, earlier_report, later_report)

    outcome = similarity.score_pair(db_session, pair)

    assert outcome.ineligible
    assert outcome.run is None
    assert db_session.query(SimilarityRun).filter_by(report_pair_id=pair.id).count() == 0


def test_score_pair_skips_identical_successful_run(db_session):
    pair = _fully_scoreable_pair(db_session)
    first = similarity.score_pair(db_session, pair)
    second = similarity.score_pair(db_session, pair)

    assert not first.skipped
    assert second.skipped
    assert second.run.id == first.run.id
    assert db_session.query(SimilarityRun).filter_by(report_pair_id=pair.id).count() == 1


def test_score_pair_force_creates_new_run(db_session):
    pair = _fully_scoreable_pair(db_session)
    first = similarity.score_pair(db_session, pair)
    second = similarity.score_pair(db_session, pair, force=True)

    assert not second.skipped
    assert second.run.id != first.run.id
    assert db_session.query(SimilarityRun).filter_by(report_pair_id=pair.id).count() == 2


def test_score_pair_new_narrative_document_triggers_new_run(db_session):
    pair = _fully_scoreable_pair(db_session)
    first = similarity.score_pair(db_session, pair)

    later_report = db_session.get(Report, pair.later_report_id)
    new_run = _extraction_run(db_session, later_report, completed_at=datetime.now(UTC))
    _narrative(db_session, new_run, GOOD_TEXT_B + " an additional disclosure was added this year.")

    second = similarity.score_pair(db_session, pair)

    assert not second.skipped
    assert second.run.id != first.run.id
    assert second.run.later_narrative_document_id != first.run.later_narrative_document_id


def test_score_pair_failed_scoring_leaves_no_document_similarity(db_session, monkeypatch):
    pair = _fully_scoreable_pair(db_session)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic scoring failure")

    monkeypatch.setattr(similarity, "compute_metrics", _boom)

    outcome = similarity.score_pair(db_session, pair)

    assert outcome.run is not None
    assert outcome.run.status == SimilarityRunStatus.FAILED
    assert "synthetic scoring failure" in outcome.run.error_message
    assert (
        db_session.query(DocumentSimilarity).filter_by(similarity_run_id=outcome.run.id).count() == 0
    )
    # A FAILED run must never become the "current" result.
    assert similarity.get_current_similarity_run(db_session, pair.id) is None


def test_failed_run_does_not_replace_prior_successful_run(db_session, monkeypatch):
    pair = _fully_scoreable_pair(db_session)
    good_outcome = similarity.score_pair(db_session, pair)

    def _boom(*args, **kwargs):
        raise RuntimeError("synthetic scoring failure")

    monkeypatch.setattr(similarity, "compute_metrics", _boom)
    failed_outcome = similarity.score_pair(db_session, pair, force=True)

    assert failed_outcome.run.status == SimilarityRunStatus.FAILED
    current = similarity.get_current_similarity_run(db_session, pair.id)
    assert current is not None
    assert current.id == good_outcome.run.id


# ---------------------------------------------------------------------------
# Current-result selection
# ---------------------------------------------------------------------------


def test_get_current_document_similarity_returns_latest_completed(db_session):
    pair = _fully_scoreable_pair(db_session)
    similarity.score_pair(db_session, pair)

    current = similarity.get_current_document_similarity(db_session, pair.id)
    assert current is not None
    assert current.report_pair_id == pair.id


def test_get_current_document_similarity_none_when_never_scored(db_session):
    pair = _fully_scoreable_pair(db_session)
    assert similarity.get_current_document_similarity(db_session, pair.id) is None


# ---------------------------------------------------------------------------
# Batch scoring
# ---------------------------------------------------------------------------


def test_score_eligible_pairs_buckets_outcomes(db_session):
    scoreable_pair = _fully_scoreable_pair(db_session)

    company = _company(db_session, ticker="INE")
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    ineligible_pair = _pair(db_session, company, earlier_report, later_report)

    outcome = similarity.score_eligible_pairs(db_session)

    assert scoreable_pair.id in outcome.completed or scoreable_pair.id in outcome.completed_with_warnings
    assert any(pair_id == ineligible_pair.id for pair_id, _ in outcome.ineligible)


def test_score_eligible_pairs_continues_after_individual_failure(db_session, monkeypatch):
    pair_one = _fully_scoreable_pair(db_session)

    company = _company(db_session, ticker="TW2")
    earlier_report = _report(db_session, company, 2022, "earlier2")
    later_report = _report(db_session, company, 2023, "later2")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    pair_two = _pair(db_session, company, earlier_report, later_report)

    original = similarity.select_source_narratives
    calls = {"count": 0}

    def _flaky(session, pair):
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("unexpected orchestration blowup")
        return original(session, pair)

    monkeypatch.setattr(similarity, "select_source_narratives", _flaky)

    outcome = similarity.score_eligible_pairs(db_session)

    all_pair_ids = {pair_one.id, pair_two.id}
    handled_ids = (
        set(outcome.completed)
        | set(outcome.completed_with_warnings)
        | {pid for pid, _ in outcome.failed}
    )
    assert all_pair_ids.issubset(handled_ids)
    assert len(outcome.failed) == 1


def test_score_eligible_pairs_respects_limit(db_session):
    _fully_scoreable_pair(db_session)
    company = _company(db_session, ticker="LIM")
    earlier_report = _report(db_session, company, 2022, "earlier3")
    later_report = _report(db_session, company, 2023, "later3")
    earlier_run = _extraction_run(db_session, earlier_report)
    later_run = _extraction_run(db_session, later_report)
    _narrative(db_session, earlier_run, GOOD_TEXT_A)
    _narrative(db_session, later_run, GOOD_TEXT_B)
    _pair(db_session, company, earlier_report, later_report)

    outcome = similarity.score_eligible_pairs(db_session, limit=1)

    total_handled = (
        len(outcome.completed)
        + len(outcome.completed_with_warnings)
        + len(outcome.skipped)
        + len(outcome.ineligible)
        + len(outcome.failed)
    )
    assert total_handled == 1

import math
from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.embedding import EMBEDDING_DIMENSION, EmbeddingRun, PassageEmbedding
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentRunStatus,
    AlignmentStatus,
    AlignmentType,
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services import passage_alignment as pa
from market_documents.services.narrative_construction import compute_content_hash


def _vec(similarity_to_e0: float, dim: int = EMBEDDING_DIMENSION) -> list[float]:
    theta = math.acos(max(-1.0, min(1.0, similarity_to_e0)))
    v = [0.0] * dim
    v[0] = math.cos(theta)
    v[1] = math.sin(theta)
    return v


BASE_VEC = _vec(1.0)


def _company(db_session, ticker: str) -> Company:
    company = Company(ticker=ticker, company_name="Alignment Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, suffix: str) -> Report:
    report = Report(
        company_id=company.id,
        local_path=f"data/raw/{company.ticker}/{year}/{suffix}.pdf",
        filename=f"{suffix}.pdf",
        sha256=compute_content_hash(f"{company.ticker}-{suffix}"),
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    return report


def _extraction_run(db_session, report: Report, quality=ExtractionQuality.GOOD) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id, extractor_name="test", extractor_version="1", configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED, extraction_quality=quality,
        started_at=datetime.now(UTC), completed_at=datetime.now(UTC), encrypted_pdf_handled=False,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _narrative(db_session, extraction_run: ExtractionRun, report: Report) -> NarrativeDocument:
    doc = NarrativeDocument(
        extraction_run_id=extraction_run.id, report_id=report.id, cleaned_text="text",
        word_count=1, content_hash=compute_content_hash(f"narrative-{extraction_run.id}"),
    )
    db_session.add(doc)
    db_session.flush()
    return doc


def _segmentation_run(db_session, narrative: NarrativeDocument, extraction_run: ExtractionRun) -> PassageSegmentationRun:
    run = PassageSegmentationRun(
        narrative_document_id=narrative.id, extraction_run_id=extraction_run.id,
        algorithm_version="1.0.0", configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.flush()
    return run


def _embedding_run(db_session, segmentation_run: PassageSegmentationRun, *, model_revision: str = "rev1") -> EmbeddingRun:
    run = EmbeddingRun(
        segmentation_run_id=segmentation_run.id, model_name="test-model", model_revision=model_revision,
        tokenizer_name="test-model", tokenizer_revision=model_revision, embedding_dimension=EMBEDDING_DIMENSION,
        pooling_strategy="cls", normalization_method="l2", maximum_model_tokens=512,
        configuration_hash=f"emb-hash-{model_revision}", status=EmbeddingRunStatus.COMPLETED,
        completed_at=datetime.now(UTC),
    )
    db_session.add(run)
    db_session.flush()
    return run


def _passage(
    db_session, segmentation_run: PassageSegmentationRun, report: Report, *, index: int, text: str,
    heading: str | None = None, excluded: bool = False,
) -> Passage:
    passage = Passage(
        segmentation_run_id=segmentation_run.id,
        narrative_document_id=segmentation_run.narrative_document_id,
        report_id=report.id,
        extraction_run_id=segmentation_run.extraction_run_id,
        passage_index=index,
        raw_text=text,
        normalized_text=text.lower(),
        content_hash=compute_content_hash(f"{text}-{index}-{segmentation_run.id}"),
        first_page_number=1,
        last_page_number=1,
        word_count=len(text.split()),
        token_count=len(text.split()),
        character_count=len(text),
        heading_text=heading,
        passage_type=PassageType.HEADING_WITH_BODY if heading else PassageType.PARAGRAPH,
        excluded_from_alignment=excluded,
    )
    db_session.add(passage)
    db_session.flush()
    return passage


def _embed(db_session, embedding_run: EmbeddingRun, passage: Passage, vector: list[float]) -> PassageEmbedding:
    embedding = PassageEmbedding(
        embedding_run_id=embedding_run.id, passage_id=passage.id, embedding=vector,
        input_token_count=passage.token_count, truncated=False,
    )
    db_session.add(embedding)
    db_session.flush()
    return embedding


def _pair(db_session, company, earlier: Report, later: Report, *, gap_months=12, is_transition=False) -> ReportPair:
    pair = ReportPair(
        company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id,
        gap_months=gap_months, is_transition=is_transition,
    )
    db_session.add(pair)
    db_session.flush()
    return pair


class PairSetup:
    def __init__(self, pair, earlier_report, later_report, earlier_seg, later_seg, earlier_emb, later_emb):
        self.pair = pair
        self.earlier_report = earlier_report
        self.later_report = later_report
        self.earlier_seg = earlier_seg
        self.later_seg = later_seg
        self.earlier_emb = earlier_emb
        self.later_emb = later_emb


def _setup_pair(db_session, *, ticker="ALN", gap_months=12, is_transition=False, earlier_quality=ExtractionQuality.GOOD, later_quality=ExtractionQuality.GOOD) -> PairSetup:
    company = _company(db_session, ticker)
    earlier_report = _report(db_session, company, 2022, "earlier")
    later_report = _report(db_session, company, 2023, "later")
    earlier_extraction = _extraction_run(db_session, earlier_report, quality=earlier_quality)
    later_extraction = _extraction_run(db_session, later_report, quality=later_quality)
    earlier_narrative = _narrative(db_session, earlier_extraction, earlier_report)
    later_narrative = _narrative(db_session, later_extraction, later_report)
    earlier_seg = _segmentation_run(db_session, earlier_narrative, earlier_extraction)
    later_seg = _segmentation_run(db_session, later_narrative, later_extraction)
    earlier_emb = _embedding_run(db_session, earlier_seg)
    later_emb = _embedding_run(db_session, later_seg)
    pair = _pair(db_session, company, earlier_report, later_report, gap_months=gap_months, is_transition=is_transition)
    return PairSetup(pair, earlier_report, later_report, earlier_seg, later_seg, earlier_emb, later_emb)


# ---------------------------------------------------------------------------
# Eligibility
# ---------------------------------------------------------------------------


def test_ineligible_missing_segmentation(db_session):
    company = _company(db_session, "NOSEG")
    earlier = _report(db_session, company, 2022, "earlier")
    later = _report(db_session, company, 2023, "later")
    earlier_extraction = _extraction_run(db_session, earlier)
    later_extraction = _extraction_run(db_session, later)
    _narrative(db_session, earlier_extraction, earlier)
    _narrative(db_session, later_extraction, later)
    pair = _pair(db_session, company, earlier, later)

    outcome = pa.align_pair(db_session, pair)
    assert outcome.ineligible
    assert "segmentation" in outcome.ineligible_reason


def test_ineligible_missing_embedding(db_session):
    setup = _setup_pair(db_session, ticker="NOEMB")
    _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="some earlier text here")
    _passage(db_session, setup.later_seg, setup.later_report, index=0, text="some later text here")
    # No embeddings created for either side, and no embedding run either --
    # remove the embedding runs the helper created to simulate "not embedded yet".
    db_session.delete(setup.earlier_emb)
    db_session.delete(setup.later_emb)
    db_session.flush()

    outcome = pa.align_pair(db_session, setup.pair)
    assert outcome.ineligible
    assert "embedding" in outcome.ineligible_reason


def test_ineligible_incompatible_embedding_models(db_session):
    setup = _setup_pair(db_session, ticker="INCOMPAT")
    db_session.delete(setup.later_emb)
    db_session.flush()
    mismatched = _embedding_run(db_session, setup.later_seg, model_revision="rev2")

    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="earlier text words")
    later_p = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="later text words")
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, mismatched, later_p, BASE_VEC)

    outcome = pa.align_pair(db_session, setup.pair)
    assert outcome.ineligible
    assert "incompatible" in outcome.ineligible_reason


def test_ineligible_no_eligible_passages(db_session):
    setup = _setup_pair(db_session, ticker="NOPASS")
    _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="earlier text", excluded=True)
    _passage(db_session, setup.later_seg, setup.later_report, index=0, text="later text", excluded=True)

    outcome = pa.align_pair(db_session, setup.pair)
    assert outcome.ineligible


# ---------------------------------------------------------------------------
# Classification via the full pipeline
# ---------------------------------------------------------------------------


def test_identical_passage_is_unchanged_high_confidence(db_session):
    setup = _setup_pair(db_session, ticker="UNCH")
    text = "the group delivered resilient operating performance across all segments"
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text=text)
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text=text)
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, BASE_VEC)

    outcome = pa.align_pair(db_session, setup.pair)
    assert outcome.run.status == AlignmentRunStatus.COMPLETED
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.alignment_status == AlignmentStatus.UNCHANGED
    assert row.alignment_type == AlignmentType.ONE_TO_ONE
    assert row.confidence == AlignmentConfidence.HIGH
    assert row.earlier_passage_id == e.id
    assert row.later_passage_id == l.id
    assert outcome.run.unchanged_count == 1
    assert outcome.run.matched_count == 1


def test_no_viable_candidate_yields_new_and_removed(db_session):
    setup = _setup_pair(db_session, ticker="NEWREM")
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="completely unrelated earlier content alpha")
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="totally different later content beta")
    _embed(db_session, setup.earlier_emb, e, _vec(0.05))
    _embed(db_session, setup.later_emb, l, BASE_VEC)  # orthogonal-ish, similarity ~0.05

    outcome = pa.align_pair(db_session, setup.pair)
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    statuses = {(r.alignment_status, r.earlier_passage_id, r.later_passage_id) for r in rows}
    assert (AlignmentStatus.NEW, None, l.id) in statuses
    assert (AlignmentStatus.REMOVED, e.id, None) in statuses
    assert outcome.run.new_count == 1
    assert outcome.run.removed_count == 1
    assert outcome.run.matched_count == 0


def test_lightly_modified_paraphrase_not_penalized_for_low_lexical(db_session):
    setup = _setup_pair(db_session, ticker="LMOD")
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="alpha bravo charlie delta echo foxtrot")
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="golf hotel india juliet kilo lima")
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, _vec(0.90))  # high semantic, ~zero lexical overlap

    outcome = pa.align_pair(db_session, setup.pair)
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    row = next(r for r in rows if r.later_passage_id == l.id)
    assert row.alignment_status == AlignmentStatus.LIGHTLY_MODIFIED
    assert row.semantic_similarity == pytest_approx(0.90)
    assert (row.lexical_cosine_similarity or 0) < 0.1


def pytest_approx(value, tol=1e-3):
    import pytest

    return pytest.approx(value, abs=tol)


def test_substantially_modified_moderate_semantic(db_session):
    setup = _setup_pair(db_session, ticker="SMOD")
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="revenue grew across all regions this year strongly")
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="revenue declined across most regions this year")
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, _vec(0.65))

    outcome = pa.align_pair(db_session, setup.pair)
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    row = next(r for r in rows if r.later_passage_id == l.id)
    assert row.alignment_status == AlignmentStatus.SUBSTANTIALLY_MODIFIED


def test_low_margin_between_competing_candidates_yields_low_confidence(db_session):
    setup = _setup_pair(db_session, ticker="MARGIN")
    text = "shared later passage text about risk"
    # Two earlier passages at indices 0 and 1 (earlier_total=2 -> normalized
    # positions 0.0 and 1.0) both propose the same later passage at index 1
    # of 3 (later_total=3 -> normalized position 0.5) -- both are exactly
    # 0.5 away from the later passage, so position_difference is identical
    # for both candidates, isolating the margin to the semantic difference.
    filler_l0 = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="unrelated filler alpha")
    l = _passage(db_session, setup.later_seg, setup.later_report, index=1, text=text)
    filler_l2 = _passage(db_session, setup.later_seg, setup.later_report, index=2, text="unrelated filler beta")
    e1 = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text=text)
    e2 = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=1, text=text)
    _embed(db_session, setup.later_emb, filler_l0, _vec(-0.9, dim=EMBEDDING_DIMENSION))
    _embed(db_session, setup.later_emb, l, BASE_VEC)
    _embed(db_session, setup.later_emb, filler_l2, _vec(-0.9, dim=EMBEDDING_DIMENSION))
    _embed(db_session, setup.earlier_emb, e1, _vec(0.90))
    _embed(db_session, setup.earlier_emb, e2, _vec(0.895))

    outcome = pa.align_pair(db_session, setup.pair)
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id, later_passage_id=l.id).all()
    accepted = next(r for r in rows if r.earlier_passage_id in (e1.id, e2.id))
    assert accepted.best_second_margin is not None
    assert accepted.best_second_margin < 0.03
    assert accepted.confidence == AlignmentConfidence.LOW


def test_split_detection_flags_ambiguous_instead_of_new(db_session):
    setup = _setup_pair(db_session, ticker="SPLIT")
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text="the full original section text before it was split")
    l1 = _passage(db_session, setup.later_seg, setup.later_report, index=0, text="the full original section text before it was split")
    l2 = _passage(db_session, setup.later_seg, setup.later_report, index=1, text="the full original section text before it was split")
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l1, BASE_VEC)  # wins the claim on e (identical text -> higher combined score)
    _embed(db_session, setup.later_emb, l2, _vec(0.80))  # loses, but still strongly proposes the same earlier passage

    outcome = pa.align_pair(db_session, setup.pair)
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    row_l1 = next(r for r in rows if r.later_passage_id == l1.id)
    row_l2 = next(r for r in rows if r.later_passage_id == l2.id)
    assert row_l1.earlier_passage_id == e.id
    assert row_l2.alignment_status == AlignmentStatus.AMBIGUOUS
    assert row_l2.confidence == AlignmentConfidence.NEEDS_REVIEW
    assert "split" in (row_l2.review_reason or "")


def test_irregular_gap_and_transition_propagate_to_run_and_confidence(db_session):
    setup = _setup_pair(db_session, ticker="IRREG", gap_months=96, is_transition=True)
    text = "boilerplate risk disclosure language reused across periods"
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text=text)
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text=text)
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, BASE_VEC)

    outcome = pa.align_pair(db_session, setup.pair)
    assert outcome.run.status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS
    assert "irregular reporting gap" in outcome.run.review_reason
    assert "transition-period pair" in outcome.run.review_reason

    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    row = rows[0]
    assert row.confidence == AlignmentConfidence.MEDIUM
    assert "irregular reporting gap" in row.review_reason


def test_needs_review_extraction_quality_does_not_block_alignment(db_session):
    setup = _setup_pair(db_session, ticker="NRQ", later_quality=ExtractionQuality.NEEDS_REVIEW)
    text = "some narrative disclosure text for this test"
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text=text)
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text=text)
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, BASE_VEC)

    outcome = pa.align_pair(db_session, setup.pair)
    assert not outcome.ineligible
    assert outcome.run.status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS
    rows = db_session.query(pa.PassageAlignment).filter_by(alignment_run_id=outcome.run.id).all()
    assert "NEEDS_REVIEW" in (rows[0].review_reason or "")


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def _simple_matched_pair(db_session, ticker):
    setup = _setup_pair(db_session, ticker=ticker)
    text = "a simple matched passage used for idempotency tests"
    e = _passage(db_session, setup.earlier_seg, setup.earlier_report, index=0, text=text)
    l = _passage(db_session, setup.later_seg, setup.later_report, index=0, text=text)
    _embed(db_session, setup.earlier_emb, e, BASE_VEC)
    _embed(db_session, setup.later_emb, l, BASE_VEC)
    return setup


def test_align_pair_skips_identical_successful_run(db_session):
    setup = _simple_matched_pair(db_session, "SKIP")
    first = pa.align_pair(db_session, setup.pair)
    second = pa.align_pair(db_session, setup.pair)
    assert second.skipped
    assert second.run.id == first.run.id


def test_align_pair_force_reruns(db_session):
    setup = _simple_matched_pair(db_session, "FORCE")
    first = pa.align_pair(db_session, setup.pair)
    second = pa.align_pair(db_session, setup.pair, force=True)
    assert not second.skipped
    assert second.run.id != first.run.id


def test_align_pair_configuration_change_triggers_new_run(db_session, monkeypatch):
    setup = _simple_matched_pair(db_session, "CFGCHG")
    first = pa.align_pair(db_session, setup.pair)

    from market_documents.services import alignment_config

    monkeypatch.setattr(alignment_config, "SCORING_CONFIG_VERSION", 999)
    second = pa.align_pair(db_session, setup.pair)
    assert not second.skipped
    assert second.run.configuration_hash != first.run.configuration_hash


def test_align_pair_new_embedding_run_triggers_new_alignment(db_session):
    setup = _simple_matched_pair(db_session, "NEWEMB")
    first = pa.align_pair(db_session, setup.pair)

    # Simulate a re-embed: a new, different EmbeddingRun becomes current for
    # the later side (same passages, new vectors).
    new_later_emb = _embedding_run(db_session, setup.later_seg, model_revision="rev2")
    later_passage = db_session.query(pa.Passage).filter_by(segmentation_run_id=setup.later_seg.id).first()
    _embed(db_session, new_later_emb, later_passage, BASE_VEC)
    # The earlier side must also use a compatible (matching) model_revision
    # for eligibility -- re-embed it too.
    new_earlier_emb = _embedding_run(db_session, setup.earlier_seg, model_revision="rev2")
    earlier_passage = db_session.query(pa.Passage).filter_by(segmentation_run_id=setup.earlier_seg.id).first()
    _embed(db_session, new_earlier_emb, earlier_passage, BASE_VEC)

    second = pa.align_pair(db_session, setup.pair)
    assert not second.skipped
    assert second.run.id != first.run.id
    assert second.run.later_embedding_run_id == new_later_emb.id
    assert second.run.earlier_embedding_run_id == new_earlier_emb.id


def test_current_alignment_run_selection_prefers_latest_successful(db_session):
    setup = _simple_matched_pair(db_session, "CURRENT")
    first = pa.align_pair(db_session, setup.pair)
    forced = pa.align_pair(db_session, setup.pair, force=True)

    current = pa.get_current_alignment_run(db_session, setup.pair.id)
    assert current.id == forced.run.id

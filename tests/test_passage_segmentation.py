import uuid
from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.enums import BlockType, ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.passage import PassageSegmentationRun, PassageSourceBlock
from market_documents.models.report import Report
from market_documents.services import passage_segmentation as ps
from market_documents.services.narrative_construction import build_narrative_text, compute_content_hash
from market_documents.services.passage_config import PassageConfig

# ---------------------------------------------------------------------------
# Pure-algorithm fixtures (no DB)
# ---------------------------------------------------------------------------


def _block(
    page: int,
    order: int,
    text: str,
    block_type: BlockType = BlockType.PARAGRAPH,
    excluded: bool = False,
) -> ps.SegmentableBlock:
    return ps.SegmentableBlock(
        id=uuid.uuid4(),
        page_number=page,
        reading_order=order,
        block_type=block_type,
        text=text,
        excluded_from_narrative=excluded,
        exclusion_reason=None,
    )


def _words(n: int, filler: str = "word") -> str:
    return " ".join(f"{filler}{i}" for i in range(n))


SMALL_CONFIG = PassageConfig(
    min_preferred_words=10,
    target_min_words=20,
    target_max_words=30,
    max_words=40,
    min_words_hard_floor=3,
    numeric_density_exclusion_threshold=0.35,
    numeric_density_min_words=5,
)


# ---------------------------------------------------------------------------
# segment_blocks: structural rules
# ---------------------------------------------------------------------------


def test_segmentation_is_deterministic():
    blocks = [
        _block(1, 0, "Overview", BlockType.HEADING_CANDIDATE),
        _block(1, 1, _words(15)),
        _block(1, 2, _words(15)),
    ]
    first = ps.segment_blocks(blocks, SMALL_CONFIG)
    second = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert [p.content_hash for p in first] == [p.content_hash for p in second]
    assert [p.passage_index for p in first] == [p.passage_index for p in second]


def test_source_block_ordering_is_preserved():
    blocks = [
        _block(1, 0, "Overview", BlockType.HEADING_CANDIDATE),
        _block(1, 1, _words(10)),
        _block(2, 0, _words(10)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    all_ids_in_order = [bid for p in passages for bid in p.source_block_ids]
    expected_order = [blocks[0].id, blocks[1].id, blocks[2].id]
    assert all_ids_in_order == expected_order


def test_heading_with_body_grouping():
    blocks = [
        _block(1, 0, "Risk Factors", BlockType.HEADING_CANDIDATE),
        _block(1, 1, _words(15)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 1
    assert passages[0].heading_text == "Risk Factors"
    from market_documents.models.enums import PassageType

    assert passages[0].passage_type == PassageType.HEADING_WITH_BODY


def test_short_coherent_paragraph_not_merged_across_heading_boundary():
    blocks = [
        _block(1, 0, _words(12)),  # standalone short paragraph, no heading
        _block(1, 1, "Next Section", BlockType.HEADING_CANDIDATE),
        _block(1, 2, _words(15)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 2
    assert passages[0].heading_text is None
    assert passages[0].source_block_ids == (blocks[0].id,)
    assert passages[1].heading_text == "Next Section"


def test_list_items_grouped_as_list_type():
    from market_documents.models.enums import PassageType

    blocks = [
        _block(1, 0, "- item one", BlockType.LIST_ITEM),
        _block(1, 1, "- item two", BlockType.LIST_ITEM),
        _block(1, 2, "- item three", BlockType.LIST_ITEM),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 1
    assert passages[0].passage_type == PassageType.LIST


def test_major_heading_boundary_is_never_crossed():
    blocks = [
        _block(1, 0, "Section A", BlockType.HEADING_CANDIDATE),
        _block(1, 1, _words(5)),
        _block(1, 2, "Section B", BlockType.HEADING_CANDIDATE),
        _block(1, 3, _words(5)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 2
    assert passages[0].heading_text == "Section A"
    assert passages[1].heading_text == "Section B"
    ids_a = set(passages[0].source_block_ids)
    ids_b = set(passages[1].source_block_ids)
    assert ids_a.isdisjoint(ids_b)


def test_page_provenance_for_single_page_passage():
    blocks = [_block(3, 0, _words(15)), _block(3, 1, _words(5))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 1
    assert passages[0].first_page_number == 3
    assert passages[0].last_page_number == 3


def test_multi_page_passage_allowed():
    blocks = [_block(1, 0, _words(10)), _block(2, 0, _words(10))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 1
    assert passages[0].first_page_number == 1
    assert passages[0].last_page_number == 2


def test_oversized_run_is_split_deterministically():
    blocks = [_block(1, i, _words(12)) for i in range(6)]  # 72 words total, max_words=40
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) > 1
    for p in passages:
        assert p.word_count <= SMALL_CONFIG.max_words


def test_numeric_heavy_passage_is_excluded():
    numeric_text = " ".join(str(i) for i in range(20))
    blocks = [_block(1, 0, numeric_text)]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 1
    assert passages[0].excluded_from_alignment is True
    assert "numeric density" in passages[0].exclusion_reason


def test_excluded_blocks_never_appear_in_any_passage():
    blocks = [
        _block(1, 0, _words(15)),
        _block(1, 1, "12,345 6,789 numbers", BlockType.TABLE_LIKE, excluded=True),
        _block(1, 2, _words(15)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    all_ids = {bid for p in passages for bid in p.source_block_ids}
    assert blocks[1].id not in all_ids
    assert blocks[0].id in all_ids
    assert blocks[2].id in all_ids


def test_paragraph_adjacent_to_excluded_table_is_table_context():
    from market_documents.models.enums import PassageType

    table_block = ps.SegmentableBlock(
        id=uuid.uuid4(),
        page_number=1,
        reading_order=1,
        block_type=BlockType.TABLE_LIKE,
        text="1,234 5,678",
        excluded_from_narrative=True,
        exclusion_reason="table-like numeric content",
    )
    blocks = [_block(1, 0, _words(15)), table_block, _block(1, 2, _words(15))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert all(p.passage_type == PassageType.TABLE_CONTEXT for p in passages)


def test_hard_floor_excludes_tiny_non_heading_passage_but_not_heading():
    blocks = [
        _block(1, 0, _words(2)),  # below hard floor of 3, no heading
        _block(1, 1, "Small Heading", BlockType.HEADING_CANDIDATE),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    tiny = next(p for p in passages if p.heading_text is None)
    heading = next(p for p in passages if p.heading_text is not None)
    assert tiny.excluded_from_alignment is True
    assert heading.excluded_from_alignment is False


def test_duplicate_text_at_different_positions_remains_distinguishable():
    # Each block alone already exceeds target_max_words (30), so the greedy
    # packer closes each as its own passage without a heading in between --
    # two passages with byte-identical text, at different report positions.
    repeated = _words(35)
    blocks = [_block(1, 0, repeated), _block(2, 0, repeated)]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 2
    assert passages[0].raw_text == passages[1].raw_text == repeated
    assert passages[0].content_hash == passages[1].content_hash
    assert passages[0].passage_index != passages[1].passage_index
    assert passages[0].source_block_ids != passages[1].source_block_ids


def test_no_duplicated_or_omitted_source_blocks_across_a_realistic_document():
    blocks = [
        _block(1, 0, "Overview", BlockType.HEADING_CANDIDATE),
        _block(1, 1, _words(20)),
        _block(1, 2, _words(20)),
        _block(1, 3, "1,234 numbers only", BlockType.TABLE_LIKE, excluded=True),
        _block(2, 0, "- item one", BlockType.LIST_ITEM),
        _block(2, 1, "- item two", BlockType.LIST_ITEM),
        _block(2, 2, "Conclusion", BlockType.HEADING_CANDIDATE),
        _block(2, 3, _words(50)),
    ]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    included_ids = {b.id for b in blocks if not b.excluded_from_narrative}
    seen_ids: list[uuid.UUID] = [bid for p in passages for bid in p.source_block_ids]
    assert set(seen_ids) == included_ids
    assert len(seen_ids) == len(set(seen_ids))


# ---------------------------------------------------------------------------
# check_provenance
# ---------------------------------------------------------------------------


def test_check_provenance_reports_no_issues_for_clean_segmentation():
    blocks = [_block(1, 0, _words(15)), _block(1, 1, _words(15))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    narrative_word_count = sum(p.word_count for p in passages)
    diagnostics = ps.check_provenance(blocks, passages, narrative_word_count)
    assert diagnostics.fatal_errors == []
    assert diagnostics.warnings == []


def test_check_provenance_detects_omitted_block():
    # Two blocks that each exceed target_max_words alone become two separate
    # passages; dropping one leaves its source block genuinely omitted.
    blocks = [_block(1, 0, _words(35)), _block(2, 0, _words(35))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    assert len(passages) == 2
    truncated = [passages[0]]  # drop the passage covering the second block
    diagnostics = ps.check_provenance(blocks, truncated, sum(p.word_count for p in truncated))
    assert any("omitted" in e for e in diagnostics.fatal_errors)


def test_check_provenance_detects_duplicated_block():
    blocks = [_block(1, 0, _words(15))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    duplicated = passages + passages
    diagnostics = ps.check_provenance(blocks, duplicated, sum(p.word_count for p in duplicated))
    assert any("duplicated" in e for e in diagnostics.fatal_errors)


def test_check_provenance_warns_on_material_word_count_mismatch():
    blocks = [_block(1, 0, _words(15)), _block(1, 1, _words(15))]
    passages = ps.segment_blocks(blocks, SMALL_CONFIG)
    diagnostics = ps.check_provenance(blocks, passages, narrative_word_count=1000)
    assert diagnostics.fatal_errors == []
    assert any("diverges" in w for w in diagnostics.warnings)


# ---------------------------------------------------------------------------
# Orchestration (DB-backed)
# ---------------------------------------------------------------------------


def _company(db_session, ticker="SEG") -> Company:
    company = Company(ticker=ticker, company_name="Segmentation Test Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, path_suffix: str, **kwargs) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{path_suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{path_suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
        metadata_status=kwargs.pop("metadata_status", MetadataStatus.VALIDATED),
        **kwargs,
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


def _page(db_session, run: ExtractionRun, report: Report, page_number: int, text: str) -> Page:
    page = Page(
        extraction_run_id=run.id,
        report_id=report.id,
        page_number=page_number,
        raw_text=text,
        cleaned_text=text,
        character_count=len(text),
        word_count=len(text.split()),
        block_count=1,
        native_text_available=True,
        suspected_image_only=False,
        extraction_quality=ExtractionQuality.GOOD,
    )
    db_session.add(page)
    db_session.flush()
    return page


def _text_block(
    db_session,
    run: ExtractionRun,
    page: Page,
    report: Report,
    *,
    block_index: int,
    reading_order: int,
    text: str,
    block_type: BlockType = BlockType.PARAGRAPH,
    excluded: bool = False,
) -> TextBlock:
    block = TextBlock(
        extraction_run_id=run.id,
        page_id=page.id,
        report_id=report.id,
        block_index=block_index,
        reading_order=reading_order,
        raw_text=text,
        cleaned_text=text,
        block_type=block_type,
        excluded_from_narrative=excluded,
        exclusion_reason="test exclusion" if excluded else None,
    )
    db_session.add(block)
    db_session.flush()
    return block


def _segmentable_report(db_session, *, ticker="SEG", extraction_quality=ExtractionQuality.GOOD):
    """A report with two pages of realistic, segmentation-eligible TextBlocks."""
    company = _company(db_session, ticker)
    report = _report(db_session, company, 2023, "annual")
    run = _extraction_run(db_session, report, extraction_quality=extraction_quality)

    page1 = _page(db_session, run, report, 1, "page one text")
    page2 = _page(db_session, run, report, 2, "page two text")

    _text_block(db_session, run, page1, report, block_index=0, reading_order=0, text="Overview", block_type=BlockType.HEADING_CANDIDATE)
    _text_block(db_session, run, page1, report, block_index=1, reading_order=1, text=_words(80))
    _text_block(db_session, run, page2, report, block_index=0, reading_order=0, text=_words(80))

    narrative_text = build_narrative_text(db_session, run.id)
    narrative = NarrativeDocument(
        extraction_run_id=run.id,
        report_id=report.id,
        cleaned_text=narrative_text,
        word_count=len(narrative_text.split()),
        content_hash=compute_content_hash(narrative_text),
    )
    db_session.add(narrative)
    db_session.flush()
    return report, run, narrative


def test_segment_report_ineligible_no_extraction(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2023, "annual")
    outcome = ps.segment_report(db_session, report)
    assert outcome.ineligible
    assert "no current successful extraction" in outcome.ineligible_reason


def test_segment_report_ineligible_failed_extraction_quality(db_session):
    company = _company(db_session)
    report = _report(db_session, company, 2023, "annual")
    _extraction_run(db_session, report, extraction_quality=ExtractionQuality.FAILED)
    outcome = ps.segment_report(db_session, report)
    assert outcome.ineligible
    assert "FAILED" in outcome.ineligible_reason


def test_segment_report_needs_review_extraction_quality_still_eligible(db_session):
    report, _run, _narrative = _segmentable_report(db_session, extraction_quality=ExtractionQuality.NEEDS_REVIEW)
    outcome = ps.segment_report(db_session, report)
    assert not outcome.ineligible
    assert outcome.run is not None


def test_segment_report_without_period_end_is_still_eligible(db_session):
    report, _run, _narrative = _segmentable_report(db_session)
    assert report.period_end is None
    outcome = ps.segment_report(db_session, report)
    assert not outcome.ineligible
    assert outcome.run is not None


def test_segment_report_success_persists_passages_and_source_blocks(db_session):
    report, run, narrative = _segmentable_report(db_session)
    outcome = ps.segment_report(db_session, report)

    assert outcome.run is not None
    assert outcome.run.passage_count is not None and outcome.run.passage_count > 0

    passages = db_session.query(ps.Passage).filter_by(segmentation_run_id=outcome.run.id).all()
    assert len(passages) == outcome.run.passage_count

    source_blocks = (
        db_session.query(PassageSourceBlock).filter_by(segmentation_run_id=outcome.run.id).all()
    )
    assert len(source_blocks) == 3  # all three TextBlocks in the fixture


def test_segment_report_skips_identical_successful_run(db_session):
    report, _run, _narrative = _segmentable_report(db_session)
    first = ps.segment_report(db_session, report)
    second = ps.segment_report(db_session, report)
    assert second.skipped
    assert second.run.id == first.run.id


def test_segment_report_force_reruns(db_session):
    report, _run, _narrative = _segmentable_report(db_session)
    first = ps.segment_report(db_session, report)
    second = ps.segment_report(db_session, report, force=True)
    assert not second.skipped
    assert second.run.id != first.run.id


def test_segment_report_configuration_change_triggers_new_run(db_session, monkeypatch):
    report, _run, _narrative = _segmentable_report(db_session)
    first = ps.segment_report(db_session, report)

    from market_documents.services import passage_config

    # BOUNDARY_RULES_VERSION is read as a module global inside
    # compute_configuration_hash's body (not a frozen default parameter), so
    # patching it here changes the hash on the next call without needing a
    # different PassageConfig instance.
    monkeypatch.setattr(passage_config, "BOUNDARY_RULES_VERSION", 999)

    second = ps.segment_report(db_session, report)
    assert not second.skipped
    assert second.run.configuration_hash != first.run.configuration_hash


def test_segment_report_new_extraction_triggers_new_run(db_session):
    report, run, _narrative = _segmentable_report(db_session)
    first = ps.segment_report(db_session, report)

    # Re-extraction: a brand-new ExtractionRun + NarrativeDocument supersede
    # the old one as "current".
    new_run = _extraction_run(db_session, report)
    page = _page(db_session, new_run, report, 1, "new content")
    _text_block(db_session, new_run, page, report, block_index=0, reading_order=0, text=_words(80))
    narrative_text = build_narrative_text(db_session, new_run.id)
    new_narrative = NarrativeDocument(
        extraction_run_id=new_run.id,
        report_id=report.id,
        cleaned_text=narrative_text,
        word_count=len(narrative_text.split()),
        content_hash=compute_content_hash(narrative_text),
    )
    db_session.add(new_narrative)
    db_session.flush()

    second = ps.segment_report(db_session, report)
    assert not second.skipped
    assert second.run.id != first.run.id
    assert second.run.extraction_run_id == new_run.id


def test_segment_eligible_reports_continues_after_failure_and_summarizes(db_session):
    good_report, _run, _narrative = _segmentable_report(db_session, ticker="GOOD")
    company2 = _company(db_session, "BAD")
    bad_report = _report(db_session, company2, 2023, "annual")  # no extraction at all

    outcome = ps.segment_eligible_reports(db_session)
    assert good_report.local_path in outcome.completed or good_report.local_path in outcome.completed_with_warnings
    assert any(bad_report.local_path == path for path, _ in outcome.ineligible)


def test_current_segmentation_run_selection_prefers_latest_successful(db_session):
    report, _run, narrative = _segmentable_report(db_session)
    first = ps.segment_report(db_session, report)
    forced = ps.segment_report(db_session, report, force=True)

    current = ps.get_current_segmentation_run(db_session, narrative.id)
    assert current.id == forced.run.id
    assert current.id != first.run.id or first.run.id == forced.run.id

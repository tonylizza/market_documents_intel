import csv
from datetime import UTC, datetime

from market_documents.models.company import Company
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentStatus,
    BlockType,
    ExtractionQuality,
    ExtractionStatus,
    MetadataStatus,
    PassageSegmentationRunStatus,
    PassageType,
)
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.feature import FeatureRun
from market_documents.models.report import Report
from market_documents.services import structured_content_audit as sca
from market_documents.services.narrative_construction import compute_content_hash

from tests._feature_fixtures import build_manual_alignment_pair

# --------------------------------------------------------------------------
# Fixture helpers (mirrors tests/test_segmentation_audit.py / _feature_fixtures.py)
# --------------------------------------------------------------------------


def _company(db_session, ticker="SCA") -> Company:
    company = Company(ticker=ticker, company_name=f"{ticker} Structured Content Co")
    db_session.add(company)
    db_session.flush()
    return company


def _report(db_session, company: Company, year: int, suffix: str) -> Report:
    local_path = f"data/raw/{company.ticker}/{year}/{suffix}.pdf"
    report = Report(
        company_id=company.id,
        local_path=local_path,
        filename=f"{suffix}.pdf",
        sha256=compute_content_hash(local_path),
        directory_year=year,
        metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add(report)
    db_session.flush()
    return report


def _extraction_run(db_session, report: Report, completed_at: datetime) -> ExtractionRun:
    run = ExtractionRun(
        report_id=report.id,
        extractor_name="test",
        extractor_version="1",
        configuration_hash="test-hash",
        status=ExtractionStatus.COMPLETED,
        extraction_quality=ExtractionQuality.GOOD,
        started_at=completed_at,
        completed_at=completed_at,
        encrypted_pdf_handled=False,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _narrative(db_session, run: ExtractionRun, report: Report, text: str) -> NarrativeDocument:
    doc = NarrativeDocument(
        extraction_run_id=run.id,
        report_id=report.id,
        cleaned_text=text,
        word_count=len(text.split()),
        content_hash=compute_content_hash(f"narrative-{run.id}"),
    )
    db_session.add(doc)
    db_session.flush()
    return doc


def _segmentation_run(db_session, narrative: NarrativeDocument, run: ExtractionRun, completed_at: datetime) -> PassageSegmentationRun:
    seg = PassageSegmentationRun(
        narrative_document_id=narrative.id,
        extraction_run_id=run.id,
        algorithm_version="1.0.0",
        configuration_hash="seg-hash",
        status=PassageSegmentationRunStatus.COMPLETED,
        completed_at=completed_at,
    )
    db_session.add(seg)
    db_session.flush()
    return seg


def _passage(db_session, seg: PassageSegmentationRun, report: Report, index: int, text: str, *, heading_text=None, ptype=PassageType.PARAGRAPH) -> Passage:
    passage = Passage(
        segmentation_run_id=seg.id,
        narrative_document_id=seg.narrative_document_id,
        report_id=report.id,
        extraction_run_id=seg.extraction_run_id,
        passage_index=index,
        raw_text=text,
        normalized_text=text.lower(),
        content_hash=compute_content_hash(f"{text}-{index}-{seg.id}"),
        first_page_number=1,
        last_page_number=1,
        word_count=len(text.split()),
        token_count=len(text.split()),
        character_count=len(text),
        heading_text=heading_text,
        passage_type=ptype,
        excluded_from_alignment=False,
    )
    db_session.add(passage)
    db_session.flush()
    return passage


# --------------------------------------------------------------------------
# 1 & 2: current-run resolution excludes historical extraction generations
# --------------------------------------------------------------------------


def test_current_run_resolution_ignores_prior_extraction_generation(db_session):
    company = _company(db_session, "GEN")
    report = _report(db_session, company, 2023, "annual")

    old_run = _extraction_run(db_session, report, datetime(2023, 1, 1, tzinfo=UTC))
    old_narrative = _narrative(db_session, old_run, report, "old narrative text")
    old_seg = _segmentation_run(db_session, old_narrative, old_run, datetime(2023, 1, 1, tzinfo=UTC))
    old_passage = _passage(db_session, old_seg, report, 0, "STALE_MARKER_TEXT " * 20)

    new_run = _extraction_run(db_session, report, datetime(2023, 6, 1, tzinfo=UTC))
    new_narrative = _narrative(db_session, new_run, report, "new narrative text")
    new_seg = _segmentation_run(db_session, new_narrative, new_run, datetime(2023, 6, 1, tzinfo=UTC))
    new_passage = _passage(db_session, new_seg, report, 0, "FRESH_MARKER_TEXT " * 20)

    resolved = sca.current_segmentation_run_for_report(db_session, report)
    assert resolved.id == new_seg.id
    assert resolved.id != old_seg.id

    rows, contexts, passages_by_id, _ = sca.build_passage_audit_rows(db_session)
    assert new_passage.id in passages_by_id
    assert old_passage.id not in passages_by_id
    ctx = next(c for c in contexts if c.report.id == report.id)
    assert ctx.segmentation_run.id == new_seg.id


# --------------------------------------------------------------------------
# 3: one-word two-character fragment classification
# --------------------------------------------------------------------------


def test_one_word_lowercase_two_char_heading_is_short_fragment_invalid_exclude():
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text="rs", heading_text="rs", word_count=1, passage_type=PassageType.HEADING_WITH_BODY
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.SHORT_FRAGMENT_INVALID
    assert result.suggested_action == sca.EXCLUDE
    assert result.is_two_char_heading is True


def test_one_word_uppercase_two_char_heading_is_short_fragment_invalid_review():
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text="FX", heading_text="FX", word_count=1, passage_type=PassageType.HEADING_WITH_BODY
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.SHORT_FRAGMENT_INVALID
    assert result.suggested_action == sca.REVIEW


# --------------------------------------------------------------------------
# 4: legitimate two-character abbreviation with body text
# --------------------------------------------------------------------------


def test_two_char_heading_with_coherent_body_is_legitimate_abbreviation():
    text = (
        "NC\n\nUsing natural resources is a key trade-off for generating value across the other capitals. "
        "We are continuously focusing on how we can minimise our impact."
    )
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text="NC", word_count=len(text.split()), passage_type=PassageType.HEADING_WITH_BODY
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.LEGITIMATE_SHORT_ABBREVIATION
    assert result.suggested_action == sca.RETAIN


# --------------------------------------------------------------------------
# 5: broken-fragment sequence (with and without a corrupted heading)
# --------------------------------------------------------------------------


def test_two_char_heading_with_shattered_body_is_broken_fragment_sequence():
    text = "al\n\nRe\n\ngu\n\nlat\n\nors\n\nIn\n\ndu\n\nstr\n\ny b\n\nod\n\nies\n\nov\n\ner\n\nnm\n\nen\n\nEmployees"
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text="al", word_count=len(text.split()), passage_type=PassageType.HEADING_WITH_BODY
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.BROKEN_FRAGMENT_SEQUENCE
    assert result.suggested_action == sca.EXCLUDE


def test_broken_fragment_sequence_without_any_heading():
    text = "\n\n".join(["ab", "cd", "ef", "gh", "ij", "kl", "mn", "op", "qr", "st", "uv", "wx"])
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.PARAGRAPH
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.BROKEN_FRAGMENT_SEQUENCE
    assert result.is_two_char_heading is False


# --------------------------------------------------------------------------
# 6: LIST passages are tracked, never auto-invalidated
# --------------------------------------------------------------------------


def test_list_passage_type_is_list_content_with_no_auto_exclude_action():
    text = "\n\n".join([f"- disclosure item number {i} about a real governance policy" for i in range(5)])
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.LIST
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.LIST_CONTENT
    assert result.suggested_action is None
    assert sca.excluded_in_variant_b(result.category, result.is_two_char_heading) is False
    assert sca.excluded_in_variant_c(result.category, result.is_two_char_heading) is False


def test_mixed_list_and_prose_passage_detected_via_source_blocks():
    text = "Some ordinary paragraph text followed by a list of items in the same passage for thirty words total here now."
    ctx = sca.PassageAuditInput(
        passage_id=None,
        raw_text=text,
        heading_text=None,
        word_count=len(text.split()),
        passage_type=PassageType.MULTI_PARAGRAPH,
        block_types=(BlockType.PARAGRAPH, BlockType.LIST_ITEM),
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.LIST_CONTENT


# --------------------------------------------------------------------------
# 7: TABLE_CONTEXT is adjacency, not automatic leakage
# --------------------------------------------------------------------------


def test_short_table_context_passage_is_flagged_but_not_auto_excluded():
    ctx = sca.PassageAuditInput(
        passage_id=None,
        raw_text="Segment revenue grew year on year.",
        heading_text=None,
        word_count=6,
        passage_type=PassageType.TABLE_CONTEXT,
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.TABLE_CONTEXT
    assert result.suggested_action is None
    assert sca.excluded_in_variant_b(result.category, result.is_two_char_heading) is False


def test_long_coherent_table_context_passage_is_ordinary_prose_false_positive():
    sentence = "Our segment reporting continues to reflect the underlying performance of each division. "
    text = sentence * 12
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.TABLE_CONTEXT
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.ORDINARY_PROSE_FALSE_POSITIVE
    assert result.suggested_action == sca.RETAIN


# --------------------------------------------------------------------------
# 8: contents/index-like patterns
# --------------------------------------------------------------------------


def test_dot_leader_pattern_is_contents_or_index_like():
    text = "Corporate governance report ............ 42\nRemuneration report .................... 58"
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.PARAGRAPH
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.CONTENTS_OR_INDEX_LIKE


def test_gri_keyword_is_contents_or_index_like():
    text = "GRI 305-1 Direct greenhouse gas emissions GRI 305-2 Energy indirect emissions disclosure reference"
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.PARAGRAPH
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.CONTENTS_OR_INDEX_LIKE


# --------------------------------------------------------------------------
# 9: caption/label-like patterns
# --------------------------------------------------------------------------


def test_figure_caption_prefix_is_caption_or_label_like():
    ctx = sca.PassageAuditInput(
        passage_id=None,
        raw_text="Figure 3: Revenue by operating segment, 2023 vs 2022",
        heading_text=None,
        word_count=9,
        passage_type=PassageType.PARAGRAPH,
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.CAPTION_OR_LABEL_LIKE


# --------------------------------------------------------------------------
# 10: ordinary prose false-positive preservation (numeric-elevated case)
# --------------------------------------------------------------------------


def test_numeric_elevated_but_coherent_prose_is_false_positive():
    sentence = (
        "Revenue in 2023 was R4 200 000 000 compared to R3 800 000 000 in 2022 representing growth of 11 "
        "percent driven by 4 new stores across 9 regions in the current financial year under review overall. "
    )
    text = sentence * 2
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.PARAGRAPH
    )
    result = sca.classify_passage(ctx)
    assert sca.digit_ratio(text) >= sca.NUMERIC_ELEVATED_THRESHOLD
    assert result.category == sca.ORDINARY_PROSE_FALSE_POSITIVE
    assert result.suggested_action == sca.RETAIN


def test_short_numeric_elevated_passage_without_coherence_stays_numeric_or_table_like():
    text = "12 45 67 R1 234 R2 345 total 8 9 10 11 categories listed briefly"
    ctx = sca.PassageAuditInput(
        passage_id=None, raw_text=text, heading_text=None, word_count=len(text.split()), passage_type=PassageType.PARAGRAPH
    )
    result = sca.classify_passage(ctx)
    assert result.category == sca.NUMERIC_OR_TABLE_LIKE_SOURCE
    assert result.suggested_action == sca.EXCLUDE


# --------------------------------------------------------------------------
# 11: deterministic review sampling
# --------------------------------------------------------------------------


def test_deterministic_review_sample_is_stable_across_repeated_calls(db_session):
    company = _company(db_session, "SAMP")
    report = _report(db_session, company, 2023, "annual")
    run = _extraction_run(db_session, report, datetime.now(UTC))
    narrative = _narrative(db_session, run, report, "text")
    seg = _segmentation_run(db_session, narrative, run, datetime.now(UTC))
    _passage(db_session, seg, report, 0, "rs", heading_text="rs", ptype=PassageType.HEADING_WITH_BODY)
    _passage(db_session, seg, report, 1, "FX", heading_text="FX", ptype=PassageType.HEADING_WITH_BODY)

    rows, _contexts, passages_by_id, _classifications = sca.build_passage_audit_rows(db_session)
    sample_1 = sca.build_deterministic_review_sample(db_session, rows, passages_by_id)
    sample_2 = sca.build_deterministic_review_sample(db_session, rows, passages_by_id)

    assert [r.passage_id for r in sample_1] == [r.passage_id for r in sample_2]
    assert len(sample_1) > 0


# --------------------------------------------------------------------------
# 12: stable CSV column order
# --------------------------------------------------------------------------


def test_passage_audit_csv_header_is_stable(tmp_path):
    row = sca.PassageAuditRow(
        ticker="AAA",
        company_name="AAA Co",
        report_id="r1",
        directory_year=2023,
        period_end=None,
        extraction_run_id="e1",
        segmentation_run_id="s1",
        passage_id="p1",
        passage_index=0,
        first_page_number=1,
        last_page_number=1,
        passage_type="PARAGRAPH",
        heading_text=None,
        word_count=10,
        character_count=50,
        excluded_from_alignment=False,
        feature_eligible=False,
        category=sca.NUMERIC_OR_TABLE_LIKE_SOURCE,
        rule_evidence="evidence",
        suggested_action=sca.EXCLUDE,
        is_two_char_heading=False,
        constituent_block_types="",
        source_block_ids="",
        text_excerpt="excerpt",
    )
    out1 = tmp_path / "out1.csv"
    out2 = tmp_path / "out2.csv"
    sca.write_passage_audit_csv([row], out1)
    sca.write_passage_audit_csv([row], out2)

    header1 = out1.read_text().splitlines()[0]
    header2 = out2.read_text().splitlines()[0]
    assert header1 == header2
    assert header1.split(",") == [f.name for f in __import__("dataclasses").fields(sca.PassageAuditRow)]


# --------------------------------------------------------------------------
# 13: feature-variant recomputation reuses feature_metrics formulas
# --------------------------------------------------------------------------


def test_feature_sensitivity_variant_b_excludes_numeric_or_table_like_passage(db_session):
    # >=40 words so it clears the pre-existing feature-eligibility word floor
    # (FeatureConfig.minimum_feature_passage_words) -- otherwise it would
    # already be excluded from the eligible aggregate regardless of any
    # structured-leak classification, and variant B's *incremental* exclusion
    # would trivially show zero words removed.
    numeric_text = ("12 45 67 R1 234 R2 345 total 8 9 10 11 categories listed briefly here now more " * 3).strip()
    pair, alignment_run, earlier_passages, later_passages, _sim = build_manual_alignment_pair(
        db_session,
        ticker="SENS1",
        earlier_texts=[
            (" ".join(["matched"] * 45), PassageType.PARAGRAPH),
            (numeric_text, PassageType.PARAGRAPH),
        ],
        later_texts=[
            (" ".join(["matched"] * 45), PassageType.PARAGRAPH),
            (numeric_text, PassageType.PARAGRAPH),
        ],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {
                "earlier": 1,
                "later": 1,
                "status": AlignmentStatus.SUBSTANTIALLY_MODIFIED,
                "confidence": AlignmentConfidence.HIGH,
            },
        ],
    )

    all_passages = {p.id: p for p in earlier_passages + later_passages}
    classifications = {}
    for p in all_passages.values():
        ctx = sca.to_audit_input(p)
        result = sca.classify_passage(ctx)
        classifications[p.id] = result if result is not None else sca.Classification(None, "", None, False)

    numeric_passage_id = earlier_passages[1].id
    assert classifications[numeric_passage_id].category == sca.NUMERIC_OR_TABLE_LIKE_SOURCE

    rows = sca.build_feature_sensitivity_rows(db_session, all_passages, classifications)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))

    # Variant A includes the numeric-flagged row; variant B/C exclude it,
    # so fewer eligible passages are considered and the words-excluded
    # counters reflect the numeric passage's own word count.
    assert row.words_excluded_b > 0
    assert row.words_excluded_c >= row.words_excluded_b


def test_feature_sensitivity_preserves_list_and_legitimate_abbreviation(db_session):
    list_text = "\n\n".join([f"- item {i} about a real disclosure policy point" for i in range(8)])
    pair, alignment_run, earlier_passages, later_passages, _sim = build_manual_alignment_pair(
        db_session,
        ticker="SENS2",
        earlier_texts=[(" ".join(["matched"] * 45), PassageType.PARAGRAPH), (list_text, PassageType.LIST)],
        later_texts=[(" ".join(["matched"] * 45), PassageType.PARAGRAPH), (list_text, PassageType.LIST)],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {"earlier": 1, "later": 1, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
        ],
    )
    all_passages = {p.id: p for p in earlier_passages + later_passages}
    classifications = {}
    for p in all_passages.values():
        ctx = sca.to_audit_input(p)
        result = sca.classify_passage(ctx)
        classifications[p.id] = result if result is not None else sca.Classification(None, "", None, False)

    list_passage_id = earlier_passages[1].id
    assert classifications[list_passage_id].category == sca.LIST_CONTENT
    assert sca.excluded_in_variant_b(sca.LIST_CONTENT, False) is False
    assert sca.excluded_in_variant_c(sca.LIST_CONTENT, False) is False

    rows = sca.build_feature_sensitivity_rows(db_session, all_passages, classifications)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.words_excluded_b == 0
    assert row.words_excluded_c == 0


# --------------------------------------------------------------------------
# 14: no database writes
# --------------------------------------------------------------------------


def test_running_audit_does_not_write_feature_runs(db_session):
    company = _company(db_session, "NOWRITE")
    report = _report(db_session, company, 2023, "annual")
    run = _extraction_run(db_session, report, datetime.now(UTC))
    narrative = _narrative(db_session, run, report, "text")
    seg = _segmentation_run(db_session, narrative, run, datetime.now(UTC))
    _passage(db_session, seg, report, 0, "FX", heading_text="FX", ptype=PassageType.HEADING_WITH_BODY)

    before = db_session.query(FeatureRun).count()
    sca.run_structured_content_audit(db_session)
    db_session.flush()
    after = db_session.query(FeatureRun).count()
    assert before == after == 0


# --------------------------------------------------------------------------
# 15: undefined feature values exported as empty cells
# --------------------------------------------------------------------------


def test_undefined_values_export_as_empty_csv_cells(tmp_path):
    row = sca.TwoCharHeadingRow(
        ticker="AAA",
        report_id="r1",
        directory_year=2023,
        passage_id="p1",
        heading_text="rs",
        word_count=1,
        body_present=False,
        first_page_number=1,
        passage_type="HEADING_WITH_BODY",
        constituent_block_types="",
        text_excerpt="rs",
        category=sca.SHORT_FRAGMENT_INVALID,
        rule_evidence="evidence",
        suggested_action=sca.EXCLUDE,
    )
    out = tmp_path / "out.csv"
    sca.write_two_char_heading_csv([row], out)

    with out.open() as f:
        reader = csv.DictReader(f)
        record = next(reader)
    assert record["constituent_block_types"] == ""

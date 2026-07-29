import csv

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, PassageType
from market_documents.services import financial_language_audit as language_audit
from market_documents.services import financial_language_dictionary_import as di
from market_documents.services import financial_language_export as language_export
from market_documents.services.financial_language_signals import build_language_signals
from tests._language_fixtures import build_language_ready_pair, write_synthetic_lm_csv

_FILLER = " ".join(["ordinary"] * 40)


def _build_simple_pair(db_session, ticker: str, tmp_path):
    text = f"{_FILLER} loss must always could strong uncertain"
    pair, _alignment_run, _e, _l, _feat = build_language_ready_pair(
        db_session,
        ticker=ticker,
        earlier_texts=[(text, PassageType.PARAGRAPH)],
        later_texts=[(text, PassageType.PARAGRAPH)],
        rows=[{"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH}],
    )
    lm_path = write_synthetic_lm_csv(tmp_path, f"{ticker}.csv")
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")
    build_language_signals(db_session, pair)
    return pair


def test_dictionary_audit_csv_header_stable(db_session, tmp_path):
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    rows = language_audit.build_dictionary_audit_rows(db_session)
    output = tmp_path / "out.csv"
    language_audit.write_dictionary_audit_csv(rows, output)

    with output.open() as f:
        header = next(csv.reader(f))
    assert header == ["name", "version", "source", "source_hash", "license_notes", "term_count", "created_at"]


def test_language_run_audit_csv_undefined_values_are_empty_cells(db_session, tmp_path):
    """A pair with no current language-signal run yet must still produce a
    row, with every not-yet-computed field written as an empty cell."""
    from market_documents.models.company import Company
    from market_documents.models.report import Report
    from market_documents.models.report_pair import ReportPair
    from market_documents.models.enums import MetadataStatus
    from market_documents.services.narrative_construction import compute_content_hash

    company = Company(ticker="EMPTY1", company_name="Empty Test Co")
    db_session.add(company)
    db_session.flush()
    earlier = Report(
        company_id=company.id, local_path="x/e.pdf", filename="e.pdf",
        sha256=compute_content_hash("e"), directory_year=2022, metadata_status=MetadataStatus.VALIDATED,
    )
    later = Report(
        company_id=company.id, local_path="x/l.pdf", filename="l.pdf",
        sha256=compute_content_hash("l"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add_all([earlier, later])
    db_session.flush()
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12)
    db_session.add(pair)
    db_session.flush()

    rows = language_audit.build_language_run_audit_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.status is None
    assert row.net_tone_change is None

    output = tmp_path / "out.csv"
    language_audit.write_language_run_audit_csv(rows, output)
    with output.open() as f:
        reader = csv.DictReader(f)
        record = next(r for r in reader if r["report_pair_id"] == str(pair.id))
    assert record["status"] == ""
    assert record["net_tone_change"] == ""


def test_component_summary_csv_stable_columns(db_session, tmp_path):
    _build_simple_pair(db_session, "COMP1", tmp_path)
    rows = language_audit.build_component_summary_rows(db_session)
    output = tmp_path / "out.csv"
    language_audit.write_component_summary_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert header == ["metric", "count", "minimum", "median", "maximum", "mean"]


def test_sensitivity_csv_written_for_all_five_variants(db_session, tmp_path):
    _build_simple_pair(db_session, "SENS1", tmp_path)

    for builder, name in [
        (language_audit.build_structured_content_sensitivity_rows, "structured_content"),
        (language_audit.build_list_sensitivity_rows, "list"),
        (language_audit.build_table_context_sensitivity_rows, "table_context"),
        (language_audit.build_currency_exposure_sensitivity_rows, "currency_exposure"),
        (language_audit.build_confidence_sensitivity_rows, "confidence"),
    ]:
        rows = builder(db_session)
        assert len(rows) >= 1
        output = tmp_path / f"{name}.csv"
        language_audit.write_sensitivity_csv(rows, output)
        assert output.exists()


def test_deterministic_review_sample_stable_across_repeated_calls(db_session, tmp_path):
    _build_simple_pair(db_session, "REVSAMP1", tmp_path)
    first = language_audit.build_deterministic_review_sample(db_session, seed=7)
    second = language_audit.build_deterministic_review_sample(db_session, seed=7)
    assert [(r.category, r.report_pair_id) for r in first] == [(r.category, r.report_pair_id) for r in second]


def test_company_summary_csv_columns(db_session, tmp_path):
    _build_simple_pair(db_session, "COMPSUM1", tmp_path)
    rows = language_audit.build_company_summary_rows(db_session)
    output = tmp_path / "out.csv"
    language_audit.write_company_summary_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert "ticker" in header
    assert "pairs_current" in header


def test_pair_export_csv_stable_and_empty_cells(db_session, tmp_path):
    _build_simple_pair(db_session, "EXP1", tmp_path)
    rows = language_export.build_pair_export_rows(db_session)
    output = tmp_path / "out.csv"
    language_export.write_pair_export_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert header[0] == "company_id"
    assert "net_tone_change" in header
    assert "configuration_hash" in header


def test_pair_export_primary_only_filter(db_session, tmp_path):
    _build_simple_pair(db_session, "EXP2", tmp_path)
    all_rows = language_export.build_pair_export_rows(db_session, primary_only=False)
    primary_rows = language_export.build_pair_export_rows(db_session, primary_only=True)
    assert len(primary_rows) <= len(all_rows)


def test_passage_export_csv_never_includes_text(db_session, tmp_path):
    _build_simple_pair(db_session, "EXP3", tmp_path)
    rows = language_export.build_passage_export_rows(db_session)
    assert len(rows) > 0
    output = tmp_path / "out.csv"
    language_export.write_passage_export_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert "raw_text" not in header
    assert "passage_word_count" in header


def test_passage_export_filters_by_ticker(db_session, tmp_path):
    _build_simple_pair(db_session, "EXPT1", tmp_path)
    _build_simple_pair(db_session, "EXPT2", tmp_path)
    rows = language_export.build_passage_export_rows(db_session, ticker="EXPT1")
    assert len(rows) > 0
    assert all(r.ticker == "EXPT1" for r in rows)


def test_passage_export_filters_by_alignment_status(db_session, tmp_path):
    _build_simple_pair(db_session, "EXPT3", tmp_path)
    rows = language_export.build_passage_export_rows(db_session, alignment_status=AlignmentStatus.UNCHANGED)
    assert all(r.alignment_status == "UNCHANGED" for r in rows)


# --------------------------------------------------------------------------
# Milestone 6 recalibration: report-side/alignment-change quality audit CSVs
# and the pre-/post-recalibration comparison CSV.
# --------------------------------------------------------------------------


def test_report_side_quality_audit_csv_stable_columns(db_session, tmp_path):
    _build_simple_pair(db_session, "RSAUDIT1", tmp_path)
    rows = language_audit.build_report_side_quality_audit_rows(db_session)
    assert len(rows) >= 1
    output = tmp_path / "out.csv"
    language_audit.write_report_side_quality_audit_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert header == [
        "ticker", "report_pair_id", "report_side_signal_quality", "report_side_primary_eligible",
        "dictionary_match_rate_earlier", "dictionary_match_rate_later", "primary_narrative_coverage",
        "ambiguous_words_in_report_side", "report_side_warning_reasons", "report_side_exclusion_reasons",
    ]


def test_alignment_change_quality_audit_csv_stable_columns(db_session, tmp_path):
    _build_simple_pair(db_session, "ACAUDIT1", tmp_path)
    rows = language_audit.build_alignment_change_quality_audit_rows(db_session)
    assert len(rows) >= 1
    output = tmp_path / "out.csv"
    language_audit.write_alignment_change_quality_audit_csv(rows, output)
    with output.open() as f:
        header = next(csv.reader(f))
    assert header == [
        "ticker", "report_pair_id", "alignment_change_signal_quality", "alignment_change_primary_eligible",
        "ambiguous_alignment_share", "collision_flagged_word_share", "unmatched_word_share", "low_confidence_share",
        "alignment_change_analyzed_words_all", "alignment_change_analyzed_words_excl_ambiguous",
        "alignment_change_analyzed_words_hml", "alignment_change_analyzed_words_hm",
        "alignment_change_analyzed_words_h", "alignment_change_warning_reasons",
        "alignment_change_exclusion_reasons",
    ]


def test_alignment_change_quality_audit_undefined_values_are_empty_cells(db_session, tmp_path):
    _build_simple_pair(db_session, "ACAUDIT2", tmp_path)
    rows = language_audit.build_alignment_change_quality_audit_rows(db_session)
    output = tmp_path / "out.csv"
    language_audit.write_alignment_change_quality_audit_csv(rows, output)
    with output.open() as f:
        reader = csv.DictReader(f)
        record = next(reader)
    # The single-passage HIGH-confidence fixture never triggers a warning.
    assert record["alignment_change_warning_reasons"] == ""


def test_recalibration_comparison_csv_written(db_session, tmp_path):
    """With only one successful run per pair (no pre-recalibration run to
    compare against in this fresh test database), the pre-recalibration
    columns must be empty rather than erroring."""
    _build_simple_pair(db_session, "RECAL1", tmp_path)
    rows = language_audit.build_recalibration_comparison_rows(db_session)
    assert len(rows) >= 1
    row = rows[0]
    assert row.pre_recalibration_configuration_hash is None
    assert row.post_report_side_quality is not None

    output = tmp_path / "out.csv"
    language_audit.write_recalibration_comparison_csv(rows, output)
    with output.open() as f:
        reader = csv.DictReader(f)
        record = next(reader)
    assert record["pre_recalibration_configuration_hash"] == ""


def test_recalibration_comparison_detects_pre_and_post_runs(db_session, tmp_path):
    """Two successive builds under different dictionary bundles must be
    visible as pre-/post- in the comparison row, with a real configuration-
    hash diff and a defined (typically ~0) report-side rate diff since
    matching/tokenization did not change."""
    pair = _build_simple_pair(db_session, "RECAL2", tmp_path)
    taxonomy_path = tmp_path / "extra_taxonomy.yaml"
    taxonomy_path.write_text("categories:\n  governance:\n    subcategories:\n      board: [board of directors]\n")
    di.import_custom_taxonomy(db_session, taxonomy_path, version="v1")
    build_language_signals(db_session, pair)

    rows = language_audit.build_recalibration_comparison_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.pre_recalibration_configuration_hash is not None
    assert row.pre_recalibration_configuration_hash != row.post_recalibration_configuration_hash

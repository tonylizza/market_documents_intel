from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, LanguageSignalRunStatus, PassageType, ReportSide
from market_documents.models.financial_language import LanguageSignalRun, PassageLanguageSignal
from market_documents.services import financial_language_dictionary_import as di
from market_documents.services.financial_language_signals import (
    build_eligible_language_signals,
    build_language_signals,
    get_current_language_signal_run,
    get_current_pair_language_features,
)
from tests._feature_fixtures import build_manual_alignment_pair
from tests._language_fixtures import build_language_ready_pair, write_synthetic_lm_csv, write_synthetic_taxonomy_yaml

_FILLER = " ".join(["ordinary"] * 40)

# A rendered-financial-table passage (reused from the structured-content-
# audit calibration set) -- TABLE_CONTEXT passage_type puts it on the
# simplest coherence-proxy rescue path, where financial_table_rendered_as_
# prose evidence overrides the rescue.
_TABLE_TEXT = (
    "NOTES TO THE FINANCIAL STATEMENTS Net cash generated from operating activities 88 339 (350 390) "
    "Net cash utilised in investing activities (117 390) (54 194) Net cash generated from financing "
    "activities (33 470) 79 836 Net (decrease) increase in cash and cash equivalents (401 024) (324 748) "
    "Cash and cash equivalents at the beginning of the year for reconciliation purposes only here today. "
)


def _build_scenario_pair(db_session, ticker: str, tmp_path):
    earlier_texts = [
        (f"{_FILLER} loss", PassageType.PARAGRAPH),  # 0: UNCHANGED partner
        (f"{_FILLER} must", PassageType.PARAGRAPH),  # 1: REMOVED
        (f"{_FILLER} loss loss", PassageType.PARAGRAPH),  # 2: SUBSTANTIALLY_MODIFIED earlier side
        (f"{_FILLER} uncertain", PassageType.PARAGRAPH),  # 3: AMBIGUOUS earlier-only
        (_TABLE_TEXT, PassageType.TABLE_CONTEXT),  # 4: rendered-table (UNCHANGED partner)
    ]
    later_texts = [
        (f"{_FILLER} loss", PassageType.PARAGRAPH),  # 0: UNCHANGED partner
        (f"{_FILLER} loss must not always could", PassageType.PARAGRAPH),  # 1: NEW
        (f"{_FILLER} loss loss loss strong", PassageType.PARAGRAPH),  # 2: SUBSTANTIALLY_MODIFIED later side
        (f"{_FILLER} strong", PassageType.PARAGRAPH),  # 3: AMBIGUOUS later-only
        (_TABLE_TEXT, PassageType.TABLE_CONTEXT),  # 4: rendered-table (UNCHANGED partner)
    ]
    rows = [
        {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
        {"earlier": 1, "later": None, "status": AlignmentStatus.REMOVED, "confidence": AlignmentConfidence.HIGH},
        {
            "earlier": 2,
            "later": 2,
            "status": AlignmentStatus.SUBSTANTIALLY_MODIFIED,
            "confidence": AlignmentConfidence.MEDIUM,
        },
        {"earlier": 3, "later": None, "status": AlignmentStatus.AMBIGUOUS, "confidence": AlignmentConfidence.LOW},
        {"earlier": None, "later": 1, "status": AlignmentStatus.NEW, "confidence": AlignmentConfidence.HIGH},
        {
            "earlier": None,
            "later": 3,
            "status": AlignmentStatus.AMBIGUOUS,
            "confidence": AlignmentConfidence.NEEDS_REVIEW,
        },
        {"earlier": 4, "later": 4, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
    ]
    pair, alignment_run, earlier_passages, later_passages, feature_outcome = build_language_ready_pair(
        db_session, ticker=ticker, earlier_texts=earlier_texts, later_texts=later_texts, rows=rows
    )
    lm_path = write_synthetic_lm_csv(tmp_path, f"{ticker}_lm.csv")
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")
    return pair, alignment_run, earlier_passages, later_passages, feature_outcome


def test_ineligible_without_feature_run(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _sim = build_manual_alignment_pair(
        db_session,
        ticker="NOFEAT",
        earlier_texts=[(f"{_FILLER} loss", PassageType.PARAGRAPH)],
        later_texts=[(f"{_FILLER} loss", PassageType.PARAGRAPH)],
        rows=[{"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH}],
    )
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    outcome = build_language_signals(db_session, pair)
    assert outcome.ineligible is True
    assert "feature run" in outcome.ineligible_reason


def test_ineligible_without_dictionary(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = build_language_ready_pair(
        db_session,
        ticker="NODICT",
        earlier_texts=[(f"{_FILLER} loss", PassageType.PARAGRAPH)],
        later_texts=[(f"{_FILLER} loss", PassageType.PARAGRAPH)],
        rows=[{"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH}],
    )
    outcome = build_language_signals(db_session, pair)
    assert outcome.ineligible is True
    assert "dictionary" in outcome.ineligible_reason


def test_build_creates_expected_passage_signal_count(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG1", tmp_path)
    outcome = build_language_signals(db_session, pair)

    assert outcome.ineligible is False
    assert outcome.run is not None
    assert outcome.run.status in (LanguageSignalRunStatus.COMPLETED, LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS)

    signals = db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
    # 7 rows: UNCHANGED(2 sides) + REMOVED(1) + SUBSTANTIALLY_MODIFIED(2) +
    # AMBIGUOUS earlier-only(1) + NEW(1) + AMBIGUOUS later-only(1) +
    # UNCHANGED table-text(2 sides) = 10 signal rows.
    assert len(signals) == 10


def test_negation_reduces_apparent_strong_modal_signal(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG2", tmp_path)
    outcome = build_language_signals(db_session, pair)

    new_signal = next(
        s
        for s in db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
        if s.alignment_status == AlignmentStatus.NEW
    )
    # text: "... loss must not always could" -- "always" (strong_modal) is
    # negated by "not"; loss (negative+litigious), must (constraining), and
    # could (weak_modal) are not negated.
    assert new_signal.strong_modal_count == 1
    assert new_signal.negated_hit_count >= 1
    assert new_signal.negative_count == 1
    assert new_signal.litigious_count == 1
    assert new_signal.constraining_count == 1
    assert new_signal.weak_modal_count == 1


def test_removed_passage_signal_preserved_and_reflected_in_pair_features(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG3", tmp_path)
    outcome = build_language_signals(db_session, pair)

    removed_signal = next(
        s
        for s in db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
        if s.alignment_status == AlignmentStatus.REMOVED
    )
    assert removed_signal.report_side == ReportSide.EARLIER
    assert removed_signal.constraining_count == 1

    feat = get_current_pair_language_features(db_session, pair.id)
    assert feat.constraining_hits_removed >= 1


def test_new_passage_signal_reflected_as_introduction(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG4", tmp_path)
    build_language_signals(db_session, pair)

    feat = get_current_pair_language_features(db_session, pair.id)
    assert feat.negative_hits_new >= 1
    assert feat.negative_language_introduction is not None
    assert feat.negative_language_introduction > 0


def test_ambiguous_rows_are_not_silently_dropped(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG5", tmp_path)
    outcome = build_language_signals(db_session, pair)

    ambiguous_signals = [
        s
        for s in db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
        if s.alignment_status == AlignmentStatus.AMBIGUOUS
    ]
    assert len(ambiguous_signals) == 2
    assert {s.confidence for s in ambiguous_signals} == {AlignmentConfidence.LOW, AlignmentConfidence.NEEDS_REVIEW}


def test_rendered_table_passage_excluded_from_primary_narrative(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG6", tmp_path)
    outcome = build_language_signals(db_session, pair)

    table_signals = [
        s
        for s in db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
        if s.structured_content_category == "financial_table_rendered_as_prose"
    ]
    assert len(table_signals) == 2  # both sides of the UNCHANGED table-text row
    assert all(s.primary_narrative_eligible is False for s in table_signals)

    feat = get_current_pair_language_features(db_session, pair.id)
    assert feat.excluded_structured_content_count >= 2


def test_idempotent_rerun_skips(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG7", tmp_path)
    first = build_language_signals(db_session, pair)
    second = build_language_signals(db_session, pair)

    assert second.skipped is True
    assert second.run.id == first.run.id


def test_force_rebuild_creates_new_run(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG8", tmp_path)
    first = build_language_signals(db_session, pair)
    second = build_language_signals(db_session, pair, force=True)

    assert second.skipped is False
    assert second.run.id != first.run.id

    run_count = db_session.query(LanguageSignalRun).filter_by(report_pair_id=pair.id).count()
    assert run_count == 2


def test_new_run_after_dictionary_change(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG9", tmp_path)
    first = build_language_signals(db_session, pair)

    taxonomy_path = write_synthetic_taxonomy_yaml(tmp_path)
    di.import_custom_taxonomy(db_session, taxonomy_path, version="test-v1")

    second = build_language_signals(db_session, pair)  # no force -- dictionary set changed the hash
    assert second.skipped is False
    assert second.run.id != first.run.id
    assert second.run.configuration_hash != first.run.configuration_hash


def test_get_current_language_signal_run_returns_latest_successful(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG10", tmp_path)
    outcome = build_language_signals(db_session, pair)
    current = get_current_language_signal_run(db_session, pair.id)
    assert current is not None
    assert current.id == outcome.run.id


def test_primary_eligible_true_for_clean_pair(db_session, tmp_path):
    """Unlike `_build_scenario_pair` (deliberately edge-case-heavy: two
    AMBIGUOUS rows, LOW/NEEDS_REVIEW confidence, sparse dictionary density
    -- exercised separately by the AMBIGUOUS-preservation and quality-
    threshold tests), a pair with only HIGH-confidence UNCHANGED rows and
    dense dictionary hits should assess as primary-eligible."""
    dense_text = f"{_FILLER} loss must always could strong uncertain"
    pair, _alignment_run, _e, _l, _feat = build_language_ready_pair(
        db_session,
        ticker="SIG11",
        earlier_texts=[(dense_text, PassageType.PARAGRAPH)],
        later_texts=[(dense_text, PassageType.PARAGRAPH)],
        rows=[{"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH}],
    )
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)
    assert feat.language_signal_quality.value == "GOOD"
    assert feat.primary_eligible is True


def test_failed_build_leaves_no_partial_persistence(db_session, tmp_path, monkeypatch):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "SIG12", tmp_path)

    import market_documents.services.financial_language_signals as signals_module

    def _boom(*args, **kwargs):
        raise RuntimeError("forced failure for test")

    monkeypatch.setattr(signals_module, "match_passage", _boom)

    outcome = build_language_signals(db_session, pair)
    assert outcome.run is not None
    assert outcome.run.status == LanguageSignalRunStatus.FAILED
    assert "forced failure" in outcome.run.error_message

    signals = db_session.query(PassageLanguageSignal).filter_by(language_signal_run_id=outcome.run.id).all()
    assert signals == []
    assert get_current_pair_language_features(db_session, pair.id) is None


def _dense_dict_text(n_words: int = 40) -> str:
    """`n_words` filler words plus every LM-fixture core term once, dense
    enough to keep dictionary_match_rate well clear of the borderline band
    for these recalibration tests."""
    return " ".join(["ordinary"] * n_words) + " loss must always could strong uncertain"


# --------------------------------------------------------------------------
# Milestone 6 recalibration: report-side vs. alignment-change independence.
# --------------------------------------------------------------------------


def test_report_side_quality_unaffected_by_collision_flagged_rows(db_session, tmp_path):
    """A pair whose only alignment row is collision-flagged (non-unique,
    duplicate/boilerplate correspondence) must still be report-side GOOD/
    eligible -- report-side rates never depend on alignment confidence or
    collision."""
    text = _dense_dict_text()
    pair, _alignment_run, _e, _l, _feat = build_language_ready_pair(
        db_session,
        ticker="RS1",
        earlier_texts=[(text, PassageType.PARAGRAPH)],
        later_texts=[(text, PassageType.PARAGRAPH)],
        rows=[
            {
                "earlier": 0,
                "later": 0,
                "status": AlignmentStatus.UNCHANGED,
                "confidence": AlignmentConfidence.NEEDS_REVIEW,
                "review_reason": (
                    "earlier passage's text exactly duplicates another earlier passage -- "
                    "match cannot be disambiguated from content alone"
                ),
            }
        ],
    )
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)

    assert feat.report_side_signal_quality.value == "GOOD"
    assert feat.report_side_primary_eligible is True
    # The alignment-change layer, in contrast, does see the collision.
    assert feat.collision_flagged_word_share == 1.0


def test_ambiguous_words_included_in_report_side_totals(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "RS2", tmp_path)
    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)

    # _build_scenario_pair has two AMBIGUOUS rows (earlier-only and
    # later-only) -- their words must be counted, not silently dropped.
    assert feat.ambiguous_words_in_report_side > 0
    assert feat.all_passages_earlier_words > 0
    assert feat.all_passages_later_words > 0


def test_alignment_change_analyzed_words_excludes_ambiguous_from_default_minus_variant(db_session, tmp_path):
    pair, _alignment_run, _e, _l, _feat = _build_scenario_pair(db_session, "RS3", tmp_path)
    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)

    assert feat.alignment_change_analyzed_words_excl_ambiguous < feat.alignment_change_analyzed_words_all
    assert feat.alignment_change_analyzed_words_h <= feat.alignment_change_analyzed_words_hm
    assert feat.alignment_change_analyzed_words_hm <= feat.alignment_change_analyzed_words_hml
    assert feat.alignment_change_analyzed_words_hml <= feat.alignment_change_analyzed_words_all


def test_report_side_and_alignment_change_primary_eligibility_are_independent(db_session, tmp_path):
    """A large AMBIGUOUS passage dominating word share must fail
    alignment-change eligibility (genuine non-correspondence) while the
    two small, dense, HIGH-confidence matched passages keep report-side
    eligibility intact."""
    dense = _dense_dict_text()
    big_ambiguous = " ".join(["ordinary"] * 200)
    pair, _alignment_run, _e, _l, _feat = build_language_ready_pair(
        db_session,
        ticker="RS4",
        earlier_texts=[
            (dense, PassageType.PARAGRAPH),
            (dense, PassageType.PARAGRAPH),
            (big_ambiguous, PassageType.PARAGRAPH),
        ],
        later_texts=[
            (dense, PassageType.PARAGRAPH),
            (dense, PassageType.PARAGRAPH),
        ],
        rows=[
            {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {"earlier": 1, "later": 1, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
            {"earlier": 2, "later": None, "status": AlignmentStatus.AMBIGUOUS, "confidence": AlignmentConfidence.LOW},
        ],
    )
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)

    assert feat.report_side_primary_eligible is True
    assert feat.alignment_change_primary_eligible is False
    assert feat.alignment_change_signal_quality.value == "NEEDS_REVIEW"


def test_report_side_quality_does_not_propagate_upstream_feature_needs_review(db_session, tmp_path, monkeypatch):
    """Report-side quality must stay GOOD even when upstream FeatureQuality
    is NEEDS_REVIEW -- only alignment-change quality propagates it."""
    from market_documents.models.enums import FeatureQuality
    from market_documents.services.feature_extraction import get_current_report_pair_features

    pair, _alignment_run, _e, _l, _feature_outcome = build_language_ready_pair(
        db_session,
        ticker="RS5",
        earlier_texts=[(_dense_dict_text(), PassageType.PARAGRAPH)],
        later_texts=[(_dense_dict_text(), PassageType.PARAGRAPH)],
        rows=[{"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH}],
    )
    report_pair_features = get_current_report_pair_features(db_session, pair.id)
    report_pair_features.feature_quality = FeatureQuality.NEEDS_REVIEW
    db_session.flush()
    lm_path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="test-v1")

    build_language_signals(db_session, pair)
    feat = get_current_pair_language_features(db_session, pair.id)

    assert feat.report_side_signal_quality.value == "GOOD"
    assert feat.alignment_change_signal_quality.value == "USABLE"
    assert "upstream feature quality" in (feat.alignment_change_warning_reasons or "")
    assert feat.report_side_warning_reasons is None


def test_build_eligible_language_signals_batch(db_session, tmp_path):
    pair1, _a1, _e1, _l1, _f1 = _build_scenario_pair(db_session, "BATCH1", tmp_path)
    pair2, _a2, _e2, _l2, _f2 = _build_scenario_pair(db_session, "BATCH2", tmp_path)

    outcome = build_eligible_language_signals(db_session)
    completed_ids = set(outcome.completed) | set(outcome.completed_with_warnings)
    assert pair1.id in completed_ids
    assert pair2.id in completed_ids
    assert len(outcome.failed) == 0

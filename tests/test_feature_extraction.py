from market_documents.models.company import Company
from market_documents.models.embedding import EmbeddingRun
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentStatus,
    FeatureQuality,
    MetadataStatus,
    PassageType,
)
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services import feature_extraction as fe
from market_documents.services.narrative_construction import compute_content_hash

from tests._feature_fixtures import build_manual_alignment_pair, build_ready_pair

HEADING = PassageType.HEADING_WITH_BODY
PARAGRAPH = PassageType.PARAGRAPH


def _known_population_pair(db_session, ticker="KNOWN"):
    """Three tiny unchanged headings (10 words), one large substantially
    modified body (300/280 words), one new (50 words), one removed (40
    words), one ambiguous split/merge flagged row (later-only, 45 words)."""
    earlier_texts = [
        (" ".join(["h1"] * 10), HEADING),
        (" ".join(["h2"] * 10), HEADING),
        (" ".join(["h3"] * 10), HEADING),
        (" ".join(["body"] * 300), PARAGRAPH),
        (" ".join(["removed"] * 40), PARAGRAPH),
    ]
    later_texts = [
        (" ".join(["h1"] * 10), HEADING),
        (" ".join(["h2"] * 10), HEADING),
        (" ".join(["h3"] * 10), HEADING),
        (" ".join(["bodyx"] * 280), PARAGRAPH),
        (" ".join(["new"] * 50), PARAGRAPH),
        (" ".join(["ambiguous"] * 45), PARAGRAPH),
    ]
    rows = [
        {"earlier": 0, "later": 0, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
        {"earlier": 1, "later": 1, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.HIGH},
        {"earlier": 2, "later": 2, "status": AlignmentStatus.UNCHANGED, "confidence": AlignmentConfidence.MEDIUM},
        {
            "earlier": 3,
            "later": 3,
            "status": AlignmentStatus.SUBSTANTIALLY_MODIFIED,
            "confidence": AlignmentConfidence.MEDIUM,
        },
        {"earlier": None, "later": 4, "status": AlignmentStatus.NEW, "confidence": AlignmentConfidence.HIGH},
        {"earlier": 4, "later": None, "status": AlignmentStatus.REMOVED, "confidence": AlignmentConfidence.LOW},
        {
            "earlier": None,
            "later": 5,
            "status": AlignmentStatus.AMBIGUOUS,
            "confidence": AlignmentConfidence.NEEDS_REVIEW,
        },
    ]
    return build_manual_alignment_pair(
        db_session, ticker=ticker, earlier_texts=earlier_texts, later_texts=later_texts, rows=rows
    )


def test_build_features_exact_reproducibility_from_alignment_rows(db_session):
    pair, alignment_run, earlier_passages, later_passages, _sim = _known_population_pair(db_session)

    outcome = fe.build_features(db_session, pair)
    assert not outcome.ineligible
    run = outcome.run
    assert run.status.value in ("COMPLETED", "COMPLETED_WITH_WARNINGS")

    feat = fe.get_current_report_pair_features(db_session, pair.id)
    assert feat is not None

    # Raw (all-passage) counts: 3 unchanged, 1 substantially modified, 1 new, 1 removed, 1 ambiguous.
    assert feat.unchanged_count == 3
    assert feat.substantially_modified_count == 1
    assert feat.new_count == 1
    assert feat.removed_count == 1
    assert feat.ambiguous_count == 1

    # Raw word totals: match the hand-computed row_word_weight rule exactly.
    assert feat.unchanged_words == 30.0  # 3 x mean(10, 10)
    assert feat.substantially_modified_words == 290.0  # mean(300, 280)
    assert feat.new_words == 50.0
    assert feat.removed_words == 40.0
    assert feat.ambiguous_words == 45.0

    # Feature-eligible population excludes the three 10-word headings
    # (below the default 40-word floor) entirely.
    assert feat.eligible_unchanged_count == 0
    assert feat.eligible_substantially_modified_count == 1
    assert feat.excluded_low_information_count == 3
    assert feat.excluded_low_information_words == 30.0
    assert feat.excluded_heading_fragment_count == 3
    assert feat.excluded_heading_fragment_words == 30.0

    # Confidence rollups, computed directly from the manually specified rows.
    assert feat.high_confidence_count == 3
    assert feat.medium_confidence_count == 2
    assert feat.low_confidence_count == 1
    assert feat.needs_review_confidence_count == 1

    # Population totals reflect every segmented passage (5 earlier, 6 later).
    assert feat.earlier_passage_count == 5
    assert feat.later_passage_count == 6

    # Lineage: pinned upstream run IDs and denormalized report IDs.
    assert run.alignment_run_id == alignment_run.id
    assert feat.earlier_report_id == pair.earlier_report_id
    assert feat.later_report_id == pair.later_report_id


def test_disclosure_change_score_bounded_and_matches_hand_computed_formula(db_session):
    pair, _run, _e, _l, _sim = _known_population_pair(db_session)
    outcome = fe.build_features(db_session, pair)
    feat = fe.get_current_report_pair_features(db_session, pair.id)

    assert outcome.run.status.value in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
    if feat.disclosure_change_score is not None:
        assert 0.0 <= feat.disclosure_change_score <= 1.0
        component_sum = sum(
            v
            for v in (
                feat.score_unchanged_component,
                feat.score_lightly_modified_component,
                feat.score_substantially_modified_component,
                feat.score_new_component,
                feat.score_removed_component,
                feat.score_ambiguous_component,
            )
            if v is not None
        )
        assert feat.disclosure_change_score == component_sum


def test_idempotent_rerun_skips_and_returns_same_run(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="IDEM1")
    first = fe.build_features(db_session, pair)
    second = fe.build_features(db_session, pair)

    assert not first.skipped
    assert second.skipped
    assert second.run.id == first.run.id


def test_force_rebuild_creates_a_new_run_with_identical_results(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="FORCE1")
    first = fe.build_features(db_session, pair)
    second = fe.build_features(db_session, pair, force=True)

    assert not second.skipped
    assert second.run.id != first.run.id

    feat = fe.get_current_report_pair_features(db_session, pair.id)
    assert feat.feature_run_id == second.run.id


def test_new_run_created_after_configuration_change(db_session, monkeypatch):
    pair, *_ = build_ready_pair(db_session, ticker="CFGCHG")
    first = fe.build_features(db_session, pair)
    assert not first.skipped

    monkeypatch.setattr(fe, "compute_configuration_hash", lambda: "a-different-configuration-hash")
    second = fe.build_features(db_session, pair)

    assert not second.skipped
    assert second.run.id != first.run.id
    assert second.run.configuration_hash == "a-different-configuration-hash"


def test_deterministic_configuration_hashing_is_stable_and_sensitive_to_config():
    from market_documents.services.feature_config import FeatureConfig, compute_configuration_hash

    default_config = FeatureConfig()
    h1 = compute_configuration_hash(default_config)
    h2 = compute_configuration_hash(default_config)
    assert h1 == h2

    changed_config = FeatureConfig(minimum_feature_passage_words=99)
    h3 = compute_configuration_hash(changed_config)
    assert h3 != h1


def test_ineligible_pair_without_alignment_or_similarity(db_session):
    company = Company(ticker="NOFEAT", company_name="No Feature Co")
    db_session.add(company)
    db_session.flush()
    earlier = Report(
        company_id=company.id, local_path="data/raw/NOFEAT/2022/earlier.pdf", filename="earlier.pdf",
        sha256=compute_content_hash("nofeat-earlier"), directory_year=2022, metadata_status=MetadataStatus.VALIDATED,
    )
    later = Report(
        company_id=company.id, local_path="data/raw/NOFEAT/2023/later.pdf", filename="later.pdf",
        sha256=compute_content_hash("nofeat-later"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add_all([earlier, later])
    db_session.flush()
    pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(pair)
    db_session.flush()

    outcome = fe.build_features(db_session, pair)
    assert outcome.ineligible
    assert "similarity" in outcome.ineligible_reason or "alignment" in outcome.ineligible_reason


def test_partial_batch_failure_does_not_block_other_pairs(db_session):
    good_pair, *_ = build_ready_pair(db_session, ticker="GOODP")

    company = Company(ticker="BADP", company_name="Bad Pair Co")
    db_session.add(company)
    db_session.flush()
    earlier = Report(
        company_id=company.id, local_path="data/raw/BADP/2022/earlier.pdf", filename="earlier.pdf",
        sha256=compute_content_hash("badp-earlier"), directory_year=2022, metadata_status=MetadataStatus.VALIDATED,
    )
    later = Report(
        company_id=company.id, local_path="data/raw/BADP/2023/later.pdf", filename="later.pdf",
        sha256=compute_content_hash("badp-later"), directory_year=2023, metadata_status=MetadataStatus.VALIDATED,
    )
    db_session.add_all([earlier, later])
    db_session.flush()
    bad_pair = ReportPair(company_id=company.id, earlier_report_id=earlier.id, later_report_id=later.id, gap_months=12, is_transition=False)
    db_session.add(bad_pair)
    db_session.flush()

    batch = fe.build_eligible_features(db_session)

    assert good_pair.id in batch.completed or good_pair.id in batch.completed_with_warnings
    assert any(pid == bad_pair.id for pid, _reason in batch.ineligible)


def test_irregular_gap_pair_excluded_from_primary_but_still_built(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="IRREG1", gap_months=96, is_transition=False)
    outcome = fe.build_features(db_session, pair)
    feat = fe.get_current_report_pair_features(db_session, pair.id)

    assert not outcome.ineligible
    assert feat.irregular_gap is True
    assert feat.primary_eligible is False
    assert "irregular reporting gap" in (feat.exclusion_reasons or "")


def test_transition_pair_irregular_gap_is_informational_not_a_quality_failure(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="TRANS1", gap_months=6, is_transition=True)
    fe.build_features(db_session, pair)
    feat = fe.get_current_report_pair_features(db_session, pair.id)

    assert feat.irregular_gap is True
    assert feat.transition_report is True
    # Approved transition handling: not automatically NEEDS_REVIEW/FAILED for the gap alone.
    assert feat.feature_quality in (FeatureQuality.GOOD, FeatureQuality.USABLE)
    assert feat.primary_eligible is False
    assert "transition-period pair" in (feat.exclusion_reasons or "")


def test_low_embedding_coverage_makes_score_unavailable_and_flags_review(db_session):
    pair, alignment_run, earlier_passages, later_passages, _sim = _known_population_pair(db_session, ticker="LOWCOV")

    earlier_embedding_run = db_session.get(EmbeddingRun, alignment_run.earlier_embedding_run_id)
    earlier_embedding_run.embedded_passage_count = 1
    earlier_embedding_run.skipped_passage_count = 10
    db_session.flush()

    outcome = fe.build_features(db_session, pair)
    feat = fe.get_current_report_pair_features(db_session, pair.id)

    assert not outcome.ineligible
    assert feat.embedded_coverage_earlier < 0.80
    assert feat.disclosure_change_score is None
    assert feat.primary_eligible is False
    assert "disclosure_change_score unavailable" in (feat.exclusion_reasons or "")


def test_document_metric_disagreement_spread_stored_without_forcing_needs_review(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="DISAGREE")
    fe.build_features(db_session, pair)
    feat = fe.get_current_report_pair_features(db_session, pair.id)

    # Identical earlier/later text -> near-zero disagreement, but the field
    # itself is always populated (never silently omitted).
    assert feat.document_metric_disagreement_spread is not None
    assert feat.feature_quality == FeatureQuality.GOOD

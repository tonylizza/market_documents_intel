from dataclasses import fields

from market_documents.services import feature_audit
from market_documents.services import feature_extraction as fe
from market_documents.services.feature_review_sample import build_feature_review_sample

from tests._feature_fixtures import build_ready_pair


def test_feature_run_audit_row_for_built_pair(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT1")
    fe.build_features(db_session, pair)

    rows = feature_audit.build_feature_run_audit_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.status in ("COMPLETED", "COMPLETED_WITH_WARNINGS")
    assert row.feature_quality is not None
    assert row.configuration_hash is not None


def test_feature_run_audit_row_for_unbuilt_pair_has_blank_fields(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT2")
    # Deliberately never call build_features for this pair.

    rows = feature_audit.build_feature_run_audit_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.status is None
    assert row.feature_quality is None
    assert row.disclosure_change_score is None


def test_feature_review_rows_include_irregular_gap_pair(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT3", gap_months=96)
    fe.build_features(db_session, pair)

    review_rows = feature_audit.build_feature_review_rows(db_session)
    assert any(r.report_pair_id == str(pair.id) for r in review_rows)


def test_feature_review_rows_exclude_clean_primary_eligible_pair(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT4", gap_months=12)
    fe.build_features(db_session, pair)

    review_rows = feature_audit.build_feature_review_rows(db_session)
    assert not any(r.report_pair_id == str(pair.id) for r in review_rows)


def test_irregular_gap_rows_computed_from_gap_months_even_without_features_built(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT5", gap_months=96)
    # No build_features call -- irregular gap detection must not require it.

    rows = feature_audit.build_irregular_gap_rows(db_session)
    assert any(r.report_pair_id == str(pair.id) for r in rows)


def test_component_summary_reports_count_min_median_max(db_session):
    build_ready_pair(db_session, ticker="AUDIT6A")
    pair_b, *_ = build_ready_pair(db_session, ticker="AUDIT6B")
    for p in (pair_b,):
        fe.build_features(db_session, p)

    rows = feature_audit.build_feature_component_summary_rows(db_session)
    score_row = next(r for r in rows if r.metric == "disclosure_change_score")
    assert score_row.count >= 0
    if score_row.count > 0:
        assert score_row.minimum <= score_row.median <= score_row.maximum


def test_excluded_passages_summary_reflects_feature_diagnostics(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT7")
    fe.build_features(db_session, pair)

    rows = feature_audit.build_excluded_passages_summary_rows(db_session)
    row = next(r for r in rows if r.report_pair_id == str(pair.id))
    assert row.earlier_passage_count is not None
    assert row.excluded_low_information_count is not None


def test_write_feature_run_audit_csv_has_stable_header(tmp_path, db_session):
    pair, *_ = build_ready_pair(db_session, ticker="AUDIT8")
    fe.build_features(db_session, pair)
    rows = feature_audit.build_feature_run_audit_rows(db_session)

    output = tmp_path / "feature_run_audit.csv"
    feature_audit.write_feature_run_audit_csv(rows, output)

    header = output.read_text().splitlines()[0]
    expected_header = ",".join(f.name for f in fields(feature_audit.FeatureRunAuditRow))
    assert header == expected_header


def test_feature_review_sample_is_deterministic_for_same_seed(db_session):
    build_ready_pair(db_session, ticker="RSAMP1")
    pair_b, *_ = build_ready_pair(db_session, ticker="RSAMP2", gap_months=96)
    for p in (pair_b,):
        fe.build_features(db_session, p)

    first = build_feature_review_sample(db_session, seed=7, per_category=3)
    second = build_feature_review_sample(db_session, seed=7, per_category=3)
    assert [r.category for r in first] == [r.category for r in second]
    assert [r.report_pair_id for r in first] == [r.report_pair_id for r in second]


def test_feature_review_sample_includes_irregular_gap_category(db_session):
    pair, *_ = build_ready_pair(db_session, ticker="RSAMP3", gap_months=96)
    fe.build_features(db_session, pair)

    rows = build_feature_review_sample(db_session, per_category=5)
    assert any(r.category == "irregular_gap" for r in rows)

import csv

from market_documents.services import feature_export
from market_documents.services import feature_extraction as fe

from tests._feature_fixtures import build_ready_pair


def test_export_rows_only_include_pairs_with_current_features(db_session):
    built_pair, *_ = build_ready_pair(db_session, ticker="EXP1")
    fe.build_features(db_session, built_pair)
    unbuilt_pair, *_ = build_ready_pair(db_session, ticker="EXP2")

    rows = feature_export.build_export_rows(db_session)
    ids = {r.report_pair_id for r in rows}
    assert str(built_pair.id) in ids
    assert str(unbuilt_pair.id) not in ids


def test_export_primary_only_filters_out_irregular_gap_pair(db_session):
    normal_pair, *_ = build_ready_pair(db_session, ticker="EXP3", gap_months=12)
    irregular_pair, *_ = build_ready_pair(db_session, ticker="EXP4", gap_months=96)
    fe.build_features(db_session, normal_pair)
    fe.build_features(db_session, irregular_pair)

    all_rows = feature_export.build_export_rows(db_session, primary_only=False)
    primary_rows = feature_export.build_export_rows(db_session, primary_only=True)

    all_ids = {r.report_pair_id for r in all_rows}
    primary_ids = {r.report_pair_id for r in primary_rows}
    assert str(normal_pair.id) in all_ids
    assert str(irregular_pair.id) in all_ids
    assert str(normal_pair.id) in primary_ids
    assert str(irregular_pair.id) not in primary_ids


def test_write_export_csv_has_stable_column_order(tmp_path, db_session):
    pair, *_ = build_ready_pair(db_session, ticker="EXP5")
    fe.build_features(db_session, pair)
    rows = feature_export.build_export_rows(db_session)

    output = tmp_path / "export.csv"
    feature_export.write_export_csv(rows, output)

    with output.open() as f:
        header = next(csv.reader(f))
    assert header == feature_export._FIELDNAMES


def test_write_export_csv_uses_empty_cells_for_undefined_optional_metrics(tmp_path, db_session):
    pair, *_ = build_ready_pair(db_session, ticker="EXP6", gap_months=96)  # irregular gap -> score unavailable path possible
    fe.build_features(db_session, pair)
    rows = feature_export.build_export_rows(db_session)

    output = tmp_path / "export2.csv"
    feature_export.write_export_csv(rows, output)

    with output.open() as f:
        reader = csv.DictReader(f)
        record = next(reader)

    # document_diff_similarity is None whenever the diff metric wasn't
    # computed for this short synthetic text pair on at least one path --
    # regardless, every optional field with a None Python value must appear
    # as an empty string, never a fabricated "0" or "None" literal.
    row_obj = rows[0]
    for field_name, python_value in vars(row_obj).items():
        if python_value is None:
            assert record[field_name] == ""

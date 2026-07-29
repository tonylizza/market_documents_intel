import shutil

from sqlalchemy import select

from market_documents.models.financial_language import FinancialLanguageDictionary, FinancialLanguageTerm
from market_documents.services import financial_language_dictionary_import as di
from tests._language_fixtures import write_synthetic_lm_csv, write_synthetic_taxonomy_yaml

# Real Loughran-McDonald Master Dictionary column order (1993-2025 vintage):
# Word, Seq_num, Word Count, Word Proportion, Average Proportion, Std Dev,
# Doc Count, Negative, Positive, Uncertainty, Litigious, Strong_Modal,
# Weak_Modal, Constraining, Complexity, Syllables, Source -- the numeric
# stats/indicator columns sit *between* Word and the category columns, and a
# per-word Source tag column follows them, unlike the tests' minimal
# synthetic fixture (Word directly followed by category columns).
REAL_SCHEMA_HEADER = (
    "Word,Seq_num,Word Count,Word Proportion,Average Proportion,Std Dev,Doc Count,"
    "Negative,Positive,Uncertainty,Litigious,Strong_Modal,Weak_Modal,Constraining,"
    "Complexity,Syllables,Source\n"
)
REAL_SCHEMA_ROWS = (
    "ABANDON,10,161792,6.13e-06,4.84e-06,3.24e-05,79131,2009,0,0,0,0,0,0,0,3,10K_2009\n"
    "STRONG,86000,100,1e-08,1e-08,1e-08,50,0,2009,0,0,0,0,0,0,1,12of12inf\n"
    "ZERO_HIT,86001,0,0.0,0.0,0.0,0,0,0,0,0,0,0,0,0,2,12of12inf\n"
)


def write_real_schema_lm_csv(tmp_path):
    path = tmp_path / "lm_real_schema.csv"
    path.write_text(REAL_SCHEMA_HEADER + REAL_SCHEMA_ROWS)
    return path


def test_dictionary_registration_creates_dictionary_and_terms(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    dictionary, created = di.import_loughran_mcdonald(db_session, path, version="test-v1")

    assert created is True
    assert dictionary.name == "loughran_mcdonald"
    assert dictionary.version == "test-v1"
    assert dictionary.term_count > 0

    terms = db_session.scalars(
        select(FinancialLanguageTerm).where(FinancialLanguageTerm.dictionary_id == dictionary.id)
    ).all()
    assert len(terms) == dictionary.term_count


def test_dictionary_hash_matches_file_content(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    expected_hash = di.compute_file_hash(path)
    dictionary, _ = di.import_loughran_mcdonald(db_session, path, version="test-v1")
    assert dictionary.source_hash == expected_hash


def test_duplicate_term_row_in_source_file_is_not_double_inserted(db_session, tmp_path):
    """The synthetic fixture CSV repeats the LOSS row verbatim -- import
    must not create two identical (normalized_term, category) rows."""
    path = write_synthetic_lm_csv(tmp_path)
    dictionary, _ = di.import_loughran_mcdonald(db_session, path, version="test-v1")

    loss_terms = db_session.scalars(
        select(FinancialLanguageTerm).where(
            FinancialLanguageTerm.dictionary_id == dictionary.id, FinancialLanguageTerm.normalized_term == "loss"
        )
    ).all()
    categories = sorted(t.category for t in loss_terms)
    assert categories == ["litigious", "negative"]


def test_multi_category_term_creates_one_row_per_category(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    dictionary, _ = di.import_loughran_mcdonald(db_session, path, version="test-v1")

    loss_terms = db_session.scalars(
        select(FinancialLanguageTerm).where(
            FinancialLanguageTerm.dictionary_id == dictionary.id, FinancialLanguageTerm.normalized_term == "loss"
        )
    ).all()
    assert {t.category for t in loss_terms} == {"negative", "litigious"}
    assert all(t.is_phrase is False for t in loss_terms)


def test_single_word_term_expands_regular_plural(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    dictionary, _ = di.import_loughran_mcdonald(db_session, path, version="test-v1")

    negative_terms = {
        t.normalized_term
        for t in db_session.scalars(
            select(FinancialLanguageTerm).where(
                FinancialLanguageTerm.dictionary_id == dictionary.id, FinancialLanguageTerm.category == "negative"
            )
        ).all()
    }
    assert "loss" in negative_terms
    assert "losses" in negative_terms


def test_idempotent_reimport_of_unchanged_file_skips_term_insertion(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    first, created_first = di.import_loughran_mcdonald(db_session, path, version="test-v1")
    second, created_second = di.import_loughran_mcdonald(db_session, path, version="test-v1")

    assert created_first is True
    assert created_second is False
    assert first.id == second.id

    terms = db_session.scalars(
        select(FinancialLanguageTerm).where(FinancialLanguageTerm.dictionary_id == first.id)
    ).all()
    assert len(terms) == first.term_count  # not doubled


def test_reimport_same_name_version_different_content_raises(db_session, tmp_path):
    path = write_synthetic_lm_csv(tmp_path)
    di.import_loughran_mcdonald(db_session, path, version="test-v1")

    other_path = tmp_path / "different.csv"
    other_path.write_text(
        "Word,Negative,Positive,Uncertainty,Litigious,Constraining,Strong_Modal,Weak_Modal\nDIFFERENT,1,0,0,0,0,0,0\n"
    )
    import pytest

    with pytest.raises(di.DictionaryVersionConflictError):
        di.import_loughran_mcdonald(db_session, other_path, version="test-v1")


def test_new_version_of_same_dictionary_creates_separate_row(db_session, tmp_path):
    path_v1 = write_synthetic_lm_csv(tmp_path, "v1.csv")
    path_v2 = tmp_path / "v2.csv"
    path_v2.write_text(path_v1.read_text() + "EXTRA,1,0,0,0,0,0,0\n")

    v1, _ = di.import_loughran_mcdonald(db_session, path_v1, version="v1")
    v2, _ = di.import_loughran_mcdonald(db_session, path_v2, version="v2")

    assert v1.id != v2.id
    assert v1.source_hash != v2.source_hash


def test_custom_taxonomy_import_from_yaml(db_session, tmp_path):
    path = write_synthetic_taxonomy_yaml(tmp_path)
    dictionary, created = di.import_custom_taxonomy(db_session, path, version="test-v1")

    assert created is True
    assert dictionary.name == "custom_domain_taxonomy"
    terms = db_session.scalars(
        select(FinancialLanguageTerm).where(FinancialLanguageTerm.dictionary_id == dictionary.id)
    ).all()
    by_key = {(t.normalized_term, t.category, t.subcategory) for t in terms}
    assert ("credit risk", "risk", "credit") in by_key
    assert ("board of directors", "governance", "board") in by_key
    assert all(t.is_phrase for t in terms)  # every synthetic taxonomy term here is multi-word


def test_no_live_network_dependency(tmp_path, db_session):
    """Both importers operate purely on local files -- this test's own
    success (no network fixture, no monkeypatching of a network client)
    is the assertion."""
    lm_path = write_synthetic_lm_csv(tmp_path)
    taxonomy_path = write_synthetic_taxonomy_yaml(tmp_path)
    di.import_loughran_mcdonald(db_session, lm_path, version="v1")
    di.import_custom_taxonomy(db_session, taxonomy_path, version="v1")


def test_missing_word_column_raises_clear_error(db_session, tmp_path):
    import pytest

    from market_documents.exceptions import MarketDocumentsError

    path = tmp_path / "bad.csv"
    path.write_text("NotWord,Negative\nFOO,1\n")
    with pytest.raises(MarketDocumentsError):
        di.import_loughran_mcdonald(db_session, path, version="v1")


def test_unsupported_schema_with_no_recognized_category_columns_raises(db_session, tmp_path):
    """A Word column with none of the seven recognized category columns
    (e.g. an unrelated CSV, or a Master Dictionary vintage predating the
    Negative/Positive/... naming) must raise rather than silently importing
    zero-category terms."""
    import pytest

    from market_documents.exceptions import MarketDocumentsError

    path = tmp_path / "wrong_schema.csv"
    path.write_text("Word,Superfluous,Interesting\nFOO,1,1\n")
    with pytest.raises(MarketDocumentsError):
        di.import_loughran_mcdonald(db_session, path, version="v1")


def test_real_master_dictionary_column_order_ignores_numeric_stat_columns(db_session, tmp_path):
    """The real file interleaves numeric stats (Seq_num, Word Count, Word
    Proportion, ...) and a trailing per-word Source tag around the category
    columns -- confirms these are ignored rather than mistaken for category
    columns, weights, or term text (spec: "Confirm the importer does not
    incorrectly treat numeric indicator columns as weights or term text")."""
    path = write_real_schema_lm_csv(tmp_path)
    dictionary, created = di.import_loughran_mcdonald(db_session, path, version="real-schema-v1")
    assert created is True

    terms = db_session.scalars(
        select(FinancialLanguageTerm).where(
            FinancialLanguageTerm.dictionary_id == dictionary.id, FinancialLanguageTerm.normalized_term == "abandon"
        )
    ).all()
    assert {t.category for t in terms} == {"negative"}
    assert all(t.weight == 1.0 for t in terms)  # the "2009" year-added value is a hit flag, never a weight

    # ZERO_HIT has every category column at 0 -- must contribute no rows.
    zero_hit_terms = db_session.scalars(
        select(FinancialLanguageTerm).where(
            FinancialLanguageTerm.dictionary_id == dictionary.id, FinancialLanguageTerm.normalized_term == "zero_hit"
        )
    ).all()
    assert zero_hit_terms == []


def test_source_hash_unchanged_after_move(tmp_path):
    """Moving the downloaded file to its permanent
    data/reference/financial_language/loughran_mcdonald/<version>/ location
    must not alter its SHA-256 -- the importer's lineage depends on this."""
    original = write_synthetic_lm_csv(tmp_path, "original.csv")
    original_hash = di.compute_file_hash(original)

    permanent_dir = tmp_path / "loughran_mcdonald" / "test-v1"
    permanent_dir.mkdir(parents=True)
    moved = permanent_dir / original.name
    shutil.move(str(original), str(moved))

    assert di.compute_file_hash(moved) == original_hash

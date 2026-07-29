import market_documents.services.financial_language_config as financial_language_config
from market_documents.services.financial_language_config import (
    FinancialLanguageConfig,
    DictionaryFingerprint,
    compute_configuration_hash,
)


def _fp(name="lm", version="1", source_hash="abc"):
    return DictionaryFingerprint(name=name, version=version, source_hash=source_hash)


def test_hash_is_deterministic_for_identical_inputs():
    a = compute_configuration_hash((_fp(),))
    b = compute_configuration_hash((_fp(),))
    assert a == b


def test_hash_changes_with_dictionary_source_hash():
    a = compute_configuration_hash((_fp(source_hash="abc"),))
    b = compute_configuration_hash((_fp(source_hash="def"),))
    assert a != b


def test_hash_changes_with_dictionary_version():
    a = compute_configuration_hash((_fp(version="1"),))
    b = compute_configuration_hash((_fp(version="2"),))
    assert a != b


def test_hash_independent_of_dictionary_tuple_order():
    a = compute_configuration_hash((_fp(name="a"), _fp(name="b")))
    b = compute_configuration_hash((_fp(name="b"), _fp(name="a")))
    assert a == b


def test_hash_changes_with_negation_window():
    default_config = FinancialLanguageConfig()
    changed_config = FinancialLanguageConfig(negation_window=99)
    a = compute_configuration_hash((_fp(),), default_config)
    b = compute_configuration_hash((_fp(),), changed_config)
    assert a != b


def test_hash_changes_with_quality_threshold():
    default_config = FinancialLanguageConfig()
    changed_config = FinancialLanguageConfig(ambiguous_word_share_threshold=0.99)
    a = compute_configuration_hash((_fp(),), default_config)
    b = compute_configuration_hash((_fp(),), changed_config)
    assert a != b


def test_hash_changes_with_extra_dictionary():
    a = compute_configuration_hash((_fp(name="lm"),))
    b = compute_configuration_hash((_fp(name="lm"), _fp(name="custom")))
    assert a != b


# --------------------------------------------------------------------------
# Milestone 6 recalibration: independent policy versions + dictionary
# coverage thresholds must all be hash-relevant.
# --------------------------------------------------------------------------


def test_hash_changes_with_eligibility_policy_version(monkeypatch):
    a = compute_configuration_hash((_fp(),))
    monkeypatch.setattr(financial_language_config, "ELIGIBILITY_POLICY_VERSION", 2)
    b = compute_configuration_hash((_fp(),))
    assert a != b


def test_hash_changes_with_report_side_quality_policy_version(monkeypatch):
    a = compute_configuration_hash((_fp(),))
    monkeypatch.setattr(financial_language_config, "REPORT_SIDE_QUALITY_POLICY_VERSION", 2)
    b = compute_configuration_hash((_fp(),))
    assert a != b


def test_hash_changes_with_alignment_change_quality_policy_version(monkeypatch):
    a = compute_configuration_hash((_fp(),))
    monkeypatch.setattr(financial_language_config, "ALIGNMENT_CHANGE_QUALITY_POLICY_VERSION", 2)
    b = compute_configuration_hash((_fp(),))
    assert a != b


def test_hash_changes_with_dictionary_match_rate_borderline_threshold():
    default_config = FinancialLanguageConfig()
    changed_config = FinancialLanguageConfig(dictionary_match_rate_borderline_threshold=0.10)
    a = compute_configuration_hash((_fp(),), default_config)
    b = compute_configuration_hash((_fp(),), changed_config)
    assert a != b


def test_hash_changes_with_collision_flagged_word_share_threshold():
    default_config = FinancialLanguageConfig()
    changed_config = FinancialLanguageConfig(collision_flagged_word_share_needs_review_threshold=0.5)
    a = compute_configuration_hash((_fp(),), default_config)
    b = compute_configuration_hash((_fp(),), changed_config)
    assert a != b


def test_dictionary_coverage_bands_are_ordered():
    """The anomalous floor must sit strictly below the borderline ceiling
    -- otherwise the three-band policy (NEEDS_REVIEW / WARNING / no
    penalty) collapses to two bands silently."""
    config = FinancialLanguageConfig()
    assert config.dictionary_match_rate_anomalous_threshold < config.dictionary_match_rate_borderline_threshold


def test_collision_share_bands_are_ordered():
    config = FinancialLanguageConfig()
    assert config.collision_flagged_word_share_warning_threshold < config.collision_flagged_word_share_needs_review_threshold

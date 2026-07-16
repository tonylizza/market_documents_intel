from market_documents.services.similarity_config import SimilarityConfig, compute_configuration_hash


def test_identical_configuration_is_idempotent():
    config = SimilarityConfig()
    assert compute_configuration_hash(config) == compute_configuration_hash(SimilarityConfig())


def test_configuration_hash_changes_when_diff_token_threshold_changes():
    default_hash = compute_configuration_hash(SimilarityConfig())
    changed_hash = compute_configuration_hash(SimilarityConfig(diff_token_threshold=50_000))
    assert default_hash != changed_hash


def test_configuration_hash_changes_when_diff_autojunk_policy_changes():
    default_hash = compute_configuration_hash(SimilarityConfig())
    changed_hash = compute_configuration_hash(SimilarityConfig(diff_autojunk=True))
    assert default_hash != changed_hash


def test_configuration_hash_unaffected_by_unrelated_field_order():
    """Canonical JSON serialization (sort_keys=True) means field order in
    the dataclass construction call must never affect the hash.
    """
    a = SimilarityConfig(jaccard_shingle_size=2, diff_token_threshold=100_000)
    b = SimilarityConfig(diff_token_threshold=100_000, jaccard_shingle_size=2)
    assert compute_configuration_hash(a) == compute_configuration_hash(b)

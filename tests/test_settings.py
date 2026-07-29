from market_documents.config import Settings


def test_loughran_mcdonald_dictionary_path_defaults_to_none():
    """No hardcoded default -- the file's own name encodes its version, so a
    fixed default would go stale on the next vintage (see config.py)."""
    assert Settings().loughran_mcdonald_dictionary_path is None


def test_loughran_mcdonald_dictionary_path_settable_via_env_var(monkeypatch):
    monkeypatch.setenv("LOUGHRAN_MCDONALD_DICTIONARY_PATH", "data/reference/financial_language/loughran_mcdonald/1993-2025/x.csv")
    settings = Settings()
    assert str(settings.loughran_mcdonald_dictionary_path) == "data/reference/financial_language/loughran_mcdonald/1993-2025/x.csv"

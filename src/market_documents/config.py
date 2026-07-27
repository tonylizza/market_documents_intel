from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://market_documents:market_documents@localhost:5432/market_documents"
    )
    data_raw_dir: Path = Path("data/raw")
    companies_config_path: Path = Path("config/companies.yaml")
    financial_language_taxonomy_path: Path = Path("config/financial_language_custom_taxonomy.yaml")
    # No hardcoded default -- the Loughran-McDonald file's own filename
    # encodes its version (e.g. .../loughran_mcdonald/1993-2025/...), so a
    # fixed default path would silently go stale on the next vintage. Set via
    # LOUGHRAN_MCDONALD_DICTIONARY_PATH for scripts/automation; the CLI's
    # `--path` remains the explicit, required mechanism (see
    # `data/reference/financial_language/loughran_mcdonald/README.md`).
    loughran_mcdonald_dictionary_path: Path | None = None
    log_level: str = "INFO"
    extraction_batch_limit: int = 50
    # Persistent Hugging Face cache, outside any Docker image -- first run
    # downloads the pinned embedding model (~130MB); later runs read from
    # here without a network round-trip.
    hf_cache_dir: Path = Path(".cache/huggingface")
    embedding_batch_size: int = 32


def get_settings() -> Settings:
    return Settings()

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = (
        "postgresql+psycopg://market_documents:market_documents@localhost:5432/market_documents"
    )
    data_raw_dir: Path = Path("data/raw")
    companies_config_path: Path = Path("config/companies.yaml")
    log_level: str = "INFO"
    extraction_batch_limit: int = 50


def get_settings() -> Settings:
    return Settings()

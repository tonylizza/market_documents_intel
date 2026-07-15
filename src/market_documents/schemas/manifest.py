import re

from pydantic import BaseModel, field_validator

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class ScanRow(BaseModel):
    """One row of the human-reviewable CSV produced by `reports scan`."""

    local_path: str
    filename: str
    sha256: str
    file_bytes: int | None = None
    directory_year: int | None = None
    company_hint: str | None = None

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256_RE.match(value):
            raise ValueError(f"not a valid sha256 hex digest: {value!r}")
        return value


class ImportRow(BaseModel):
    """One row of the CSV consumed by `reports import`, after human review."""

    ticker: str
    local_path: str
    filename: str
    sha256: str
    file_bytes: int | None = None
    directory_year: int

    @field_validator("ticker")
    @classmethod
    def _validate_ticker(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("ticker must not be empty")
        return value

    @field_validator("sha256")
    @classmethod
    def _validate_sha256(cls, value: str) -> str:
        value = value.lower()
        if not _SHA256_RE.match(value):
            raise ValueError(f"not a valid sha256 hex digest: {value!r}")
        return value

    @field_validator("directory_year")
    @classmethod
    def _validate_directory_year(cls, value: int) -> int:
        if not 1900 <= value <= 2100:
            raise ValueError(f"implausible directory_year: {value}")
        return value


SCAN_CSV_FIELDNAMES = [
    "local_path",
    "filename",
    "sha256",
    "file_bytes",
    "directory_year",
    "company_hint",
]

IMPORT_CSV_FIELDNAMES = [
    "ticker",
    "local_path",
    "filename",
    "sha256",
    "file_bytes",
    "directory_year",
]

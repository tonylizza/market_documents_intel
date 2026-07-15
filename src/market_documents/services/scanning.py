import csv
import hashlib
import re
from pathlib import Path

from market_documents.schemas.manifest import SCAN_CSV_FIELDNAMES, ScanRow

_YEAR_RE = re.compile(r"^(19|20)\d{2}$")


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _directory_year_and_hint(pdf_path: Path, root: Path) -> tuple[int | None, str | None]:
    """Derive directory_year from the nearest ancestor directory that looks like
    a 4-digit year, and company_hint from the directory immediately above it.

    This is a hint for human review only -- never treated as authoritative.
    """
    parts = pdf_path.relative_to(root).parts[:-1]
    for idx in reversed(range(len(parts))):
        if _YEAR_RE.match(parts[idx]):
            hint = parts[idx - 1] if idx > 0 else None
            return int(parts[idx]), hint
    return None, (parts[0] if parts else None)


def scan_directory(root: Path) -> list[ScanRow]:
    """Recursively discover PDFs under root and collect provisional file metadata.

    Does not attempt to infer fiscal dates -- output is intended for human review.
    """
    rows: list[ScanRow] = []
    for pdf_path in sorted(root.rglob("*.pdf")):
        if not pdf_path.is_file():
            continue
        directory_year, company_hint = _directory_year_and_hint(pdf_path, root)
        rows.append(
            ScanRow(
                local_path=str(pdf_path),
                filename=pdf_path.name,
                sha256=_sha256_of(pdf_path),
                file_bytes=pdf_path.stat().st_size,
                directory_year=directory_year,
                company_hint=company_hint,
            )
        )
    return rows


def write_manifest_csv(rows: list[ScanRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=SCAN_CSV_FIELDNAMES)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.model_dump())

import csv
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import MetadataSource, MetadataStatus
from market_documents.models.report import Report
from market_documents.schemas.manifest import ImportRow
from market_documents.services.companies import load_companies_from_yaml


@dataclass
class ImportOutcome:
    created: list[str] = field(default_factory=list)
    skipped: list[tuple[str, str]] = field(default_factory=list)
    errors: list[tuple[int, str]] = field(default_factory=list)


def import_manifest(session: Session, csv_path: Path, companies_config_path: Path) -> ImportOutcome:
    """Idempotently import reviewed manifest rows as provisional Report records.

    Never overwrites an existing Report; duplicate files (by local_path) and
    duplicate content (by sha256) are detected and skipped rather than merged.
    """
    outcome = ImportOutcome()
    companies = load_companies_from_yaml(session, companies_config_path)

    seen_paths: set[str] = set()
    seen_hashes: set[str] = set()

    with csv_path.open(newline="") as f:
        reader = csv.DictReader(f)
        for row_number, raw in enumerate(reader, start=2):
            try:
                row = ImportRow.model_validate(raw)
            except ValidationError as exc:
                outcome.errors.append((row_number, str(exc)))
                continue

            if row.local_path in seen_paths:
                outcome.skipped.append((row.local_path, "duplicate local_path within manifest"))
                continue
            if row.sha256 in seen_hashes:
                outcome.skipped.append((row.local_path, "duplicate sha256 within manifest"))
                continue

            company = companies.get(row.ticker)
            if company is None:
                outcome.errors.append((row_number, f"unknown ticker: {row.ticker}"))
                continue

            existing_by_path = session.scalar(
                select(Report).where(Report.local_path == row.local_path)
            )
            if existing_by_path is not None:
                outcome.skipped.append((row.local_path, "already imported (local_path exists)"))
                seen_paths.add(row.local_path)
                seen_hashes.add(row.sha256)
                continue

            existing_by_hash = session.scalar(select(Report).where(Report.sha256 == row.sha256))
            if existing_by_hash is not None:
                outcome.skipped.append(
                    (
                        row.local_path,
                        f"duplicate content hash of existing report {existing_by_hash.local_path}",
                    )
                )
                seen_paths.add(row.local_path)
                seen_hashes.add(row.sha256)
                continue

            report = Report(
                company_id=company.id,
                local_path=row.local_path,
                filename=row.filename,
                sha256=row.sha256,
                file_bytes=row.file_bytes,
                directory_year=row.directory_year,
                metadata_status=MetadataStatus.DISCOVERED,
                metadata_source=MetadataSource.DIRECTORY,
                transition_report=False,
            )
            session.add(report)
            session.flush()
            seen_paths.add(row.local_path)
            seen_hashes.add(row.sha256)
            outcome.created.append(row.local_path)

    return outcome

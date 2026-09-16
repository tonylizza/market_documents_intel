"""Canonical PDF source extraction: run lifecycle, idempotency, and
persistence (Track 7C.1a).

Mirrors `services/extraction.py`'s split of responsibilities, but persists
the block/line/span hierarchy from `pdf_source_extraction.py` verbatim --
no cleaning, classification, or quality assessment happens here. Reads only
`Report.local_path`; never reads or writes `ExtractionRun`/`Page`/
`TextBlock`, keeping this track fully independent of the legacy pipeline
(see docs/7c1a-canonical-source-representation.md).
"""

import hashlib
import importlib.metadata
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import PdfDecryptionError, PdfExtractionError
from market_documents.models.enums import CanonicalExtractionStatus
from market_documents.models.pdf_source import (
    CanonicalBlock,
    CanonicalExtractionRun,
    CanonicalLine,
    CanonicalPage,
    CanonicalSpan,
)
from market_documents.models.report import Report
from market_documents.services import pdf_access, pdf_source_extraction

logger = logging.getLogger(__name__)

EXTRACTOR_NAME = "pymupdf-canonical"

# v1.0.0 = initial block/line/span-granular capture, no sorting/cleaning/
# classification.
CANONICAL_SCHEMA_VERSION = 1


def _extractor_version() -> str:
    try:
        return importlib.metadata.version("pymupdf")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def compute_configuration_hash(extractor_version: str) -> str:
    payload = {
        "extractor_name": EXTRACTOR_NAME,
        "extractor_version": extractor_version,
        "canonical_schema_version": CANONICAL_SCHEMA_VERSION,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_current_canonical_run(session: Session, report_id: uuid.UUID) -> CanonicalExtractionRun | None:
    """The current successful canonical extraction for a report.

    Defined identically to `services.extraction.get_current_extraction_run`:
    the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS -- a query-time rule, never a stored flag.
    """
    return session.scalars(
        select(CanonicalExtractionRun)
        .where(
            CanonicalExtractionRun.report_id == report_id,
            CanonicalExtractionRun.status.in_(
                (CanonicalExtractionStatus.COMPLETED, CanonicalExtractionStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(CanonicalExtractionRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class CanonicalExtractionOutcome:
    report_local_path: str
    run: CanonicalExtractionRun | None
    skipped: bool = False
    skip_reason: str | None = None


def run_canonical_extraction(
    session: Session, report: Report, *, force: bool = False
) -> CanonicalExtractionOutcome:
    """Build the canonical source representation for one report.

    Skips (returning the existing run) if the current successful canonical
    extraction already used an identical configuration fingerprint and
    `force` was not set -- mirrors `extraction.extract_report` exactly.
    """
    extractor_version = _extractor_version()
    configuration_hash = compute_configuration_hash(extractor_version)

    current_run = get_current_canonical_run(session, report.id)
    if current_run is not None and current_run.configuration_hash == configuration_hash and not force:
        return CanonicalExtractionOutcome(
            report_local_path=report.local_path,
            run=current_run,
            skipped=True,
            skip_reason="identical successful canonical extraction already exists",
        )

    run = CanonicalExtractionRun(
        report_id=report.id,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=extractor_version,
        configuration_hash=configuration_hash,
        status=CanonicalExtractionStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_canonical_extraction(session, report, run)
    except PdfDecryptionError as exc:
        run.status = CanonicalExtractionStatus.FAILED
        run.error_message = f"decryption failure: {exc}"
        run.completed_at = datetime.now(UTC)
    except PdfExtractionError as exc:
        run.status = CanonicalExtractionStatus.FAILED
        run.error_message = f"extraction failure: {exc}"
        run.completed_at = datetime.now(UTC)
    except Exception as exc:  # never leave a run silently half-written
        run.status = CanonicalExtractionStatus.FAILED
        run.error_message = f"unexpected error: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("canonical extraction failed for %s", report.local_path)

    session.flush()
    return CanonicalExtractionOutcome(report_local_path=report.local_path, run=run)


def _run_canonical_extraction(session: Session, report: Report, run: CanonicalExtractionRun) -> None:
    local_path = Path(report.local_path)

    with pdf_access.open_for_extraction(local_path) as doc:
        expected_page_count = doc.page_count
        extracted_pages = pdf_source_extraction.extract_canonical_pages(doc)

    for extracted_page in extracted_pages:
        # UUIDPkMixin.id has a Python-side default (uuid.uuid4), so every
        # id is known before any INSERT is issued -- ids are assigned
        # explicitly here so the whole page's rows can be added and
        # flushed once, instead of once per block/line/span. A real report
        # can carry tens of thousands of spans; a flush per row made this
        # extraction impractically slow against the full corpus.
        page_id = uuid.uuid4()
        pending: list = [
            CanonicalPage(
                id=page_id,
                canonical_run_id=run.id,
                report_id=report.id,
                page_number=extracted_page.page_number,
                width=extracted_page.width,
                height=extracted_page.height,
            )
        ]

        for extracted_block in extracted_page.blocks:
            block_id = uuid.uuid4()
            pending.append(
                CanonicalBlock(
                    id=block_id,
                    page_id=page_id,
                    block_order=extracted_block.block_order,
                    native_type=extracted_block.native_type,
                    x0=extracted_block.x0,
                    y0=extracted_block.y0,
                    x1=extracted_block.x1,
                    y1=extracted_block.y1,
                    raw_text=extracted_block.raw_text,
                )
            )

            for extracted_line in extracted_block.lines:
                line_id = uuid.uuid4()
                pending.append(
                    CanonicalLine(
                        id=line_id,
                        block_id=block_id,
                        line_order=extracted_line.line_order,
                        x0=extracted_line.x0,
                        y0=extracted_line.y0,
                        x1=extracted_line.x1,
                        y1=extracted_line.y1,
                    )
                )

                for extracted_span in extracted_line.spans:
                    pending.append(
                        CanonicalSpan(
                            line_id=line_id,
                            span_order=extracted_span.span_order,
                            text=extracted_span.text,
                            x0=extracted_span.x0,
                            y0=extracted_span.y0,
                            x1=extracted_span.x1,
                            y1=extracted_span.y1,
                            font_name=extracted_span.font_name,
                            font_size=extracted_span.font_size,
                            font_flags=extracted_span.font_flags,
                            is_bold=extracted_span.is_bold,
                            color=extracted_span.color,
                        )
                    )

        session.add_all(pending)
        session.flush()

    run.expected_page_count = expected_page_count
    run.processed_page_count = len(extracted_pages)
    run.completed_at = datetime.now(UTC)
    run.status = CanonicalExtractionStatus.COMPLETED

    session.flush()

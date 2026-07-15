"""Extraction orchestration: run lifecycle, idempotency, and persistence.

Ties together PDF access/decryption, native extraction, cleaning,
classification, quality assessment, and narrative construction into one
auditable `ExtractionRun` per attempt. This module owns the only two
pieces of real domain logic in the pipeline: the configuration fingerprint
that drives idempotent skipping, and the query-time rule for selecting a
report's current successful extraction.
"""

import importlib.metadata
import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import PdfDecryptionError, PdfExtractionError
from market_documents.models.enums import ExtractionQuality, ExtractionStatus, MetadataStatus
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.report import Report
from market_documents.services import (
    block_classification,
    extraction_quality,
    header_footer_detection,
    narrative_construction,
    pdf_access,
    pdf_extraction,
    text_cleaning,
)
from market_documents.services.extraction_config import (
    EXTRACTION_CONFIG,
    EXTRACTOR_NAME,
    compute_configuration_hash,
)

logger = logging.getLogger(__name__)

# Reports whose validation state permits extraction: their PDF is known
# readable (page_count established) even if period_end is still
# unconfirmed. REJECTED reports are already known unreadable; DISCOVERED
# and INSPECTED have not been through the basic page-count check yet.
ELIGIBLE_METADATA_STATUSES = (MetadataStatus.VALIDATED, MetadataStatus.NEEDS_REVIEW)


def _extractor_version() -> str:
    try:
        return importlib.metadata.version("pymupdf")
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


def get_current_extraction_run(session: Session, report_id: uuid.UUID) -> ExtractionRun | None:
    """The current successful extraction for a report.

    Defined as the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS. FAILED and in-progress runs are never
    eligible. This is a query, not a stored flag, so a failed rerun can
    never silently replace prior successful output -- it simply never
    becomes the max.
    """
    return session.scalars(
        select(ExtractionRun)
        .where(
            ExtractionRun.report_id == report_id,
            ExtractionRun.status.in_(
                (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(ExtractionRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_runs_by_report(
    session: Session, report_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ExtractionRun]:
    """Bulk version of `get_current_extraction_run` for many reports at once."""
    if not report_ids:
        return {}
    candidate_runs = session.scalars(
        select(ExtractionRun)
        .where(
            ExtractionRun.report_id.in_(report_ids),
            ExtractionRun.status.in_(
                (ExtractionStatus.COMPLETED, ExtractionStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(ExtractionRun.report_id, ExtractionRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, ExtractionRun] = {}
    for run in candidate_runs:
        current.setdefault(run.report_id, run)
    return current


def get_narrative_document(session: Session, report_id: uuid.UUID) -> NarrativeDocument | None:
    current_run = get_current_extraction_run(session, report_id)
    if current_run is None:
        return None
    return session.scalar(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id == current_run.id)
    )


@dataclass
class ExtractionOutcome:
    report_local_path: str
    run: ExtractionRun | None
    skipped: bool = False
    skip_reason: str | None = None


def extract_report(session: Session, report: Report, *, force: bool = False) -> ExtractionOutcome:
    """Run extraction for one report, creating a new ExtractionRun.

    Skips (returning the existing run) if the current successful
    extraction already used an identical configuration fingerprint and
    `force` was not set. Never mutates or replaces a prior run's rows --
    a skip returns the same run object, and any new attempt always
    creates a fresh row.
    """
    extractor_version = _extractor_version()
    configuration_hash = compute_configuration_hash(extractor_version)

    current_run = get_current_extraction_run(session, report.id)
    if current_run is not None and current_run.configuration_hash == configuration_hash and not force:
        return ExtractionOutcome(
            report_local_path=report.local_path,
            run=current_run,
            skipped=True,
            skip_reason="identical successful extraction already exists",
        )

    run = ExtractionRun(
        report_id=report.id,
        extractor_name=EXTRACTOR_NAME,
        extractor_version=extractor_version,
        configuration_hash=configuration_hash,
        status=ExtractionStatus.RUNNING,
        started_at=datetime.now(UTC),
        encrypted_pdf_handled=pdf_access.is_encrypted(Path(report.local_path)),
    )
    session.add(run)
    session.flush()

    try:
        # A SAVEPOINT scopes every Page/TextBlock/NarrativeDocument write
        # for this attempt: on success they're released into the ongoing
        # transaction alongside the run's final status; on any exception
        # they're rolled back to the savepoint, leaving only the
        # already-flushed FAILED ExtractionRun row (set below) -- never a
        # half-written run.
        with session.begin_nested():
            _run_extraction(session, report, run)
    except PdfDecryptionError as exc:
        run.status = ExtractionStatus.FAILED
        run.error_message = f"decryption failure: {exc}"
        run.completed_at = datetime.now(UTC)
    except PdfExtractionError as exc:
        run.status = ExtractionStatus.FAILED
        run.error_message = f"extraction failure: {exc}"
        run.completed_at = datetime.now(UTC)
    except Exception as exc:  # unexpected -- never leave a run silently half-written
        run.status = ExtractionStatus.FAILED
        run.error_message = f"unexpected error: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("extraction failed for %s", report.local_path)

    session.flush()
    return ExtractionOutcome(report_local_path=report.local_path, run=run)


def _run_extraction(session: Session, report: Report, run: ExtractionRun) -> None:
    local_path = Path(report.local_path)

    with pdf_access.open_for_extraction(local_path) as doc:
        expected_page_count = doc.page_count
        extracted_pages = pdf_extraction.extract_pages(doc)

    header_footer_flags = header_footer_detection.detect_header_footer_blocks(
        extracted_pages, EXTRACTION_CONFIG
    )

    page_quality_results: list[extraction_quality.PageQualityResult] = []

    for extracted_page in extracted_pages:
        quality_result = extraction_quality.assess_page(extracted_page, EXTRACTION_CONFIG)
        page_quality_results.append(quality_result)

        page = Page(
            extraction_run_id=run.id,
            report_id=report.id,
            page_number=extracted_page.page_number,
            raw_text=extracted_page.raw_text,
            cleaned_text=text_cleaning.clean_text(extracted_page.raw_text),
            character_count=quality_result.character_count,
            word_count=quality_result.word_count,
            block_count=quality_result.block_count,
            image_count=extracted_page.image_count,
            native_text_available=quality_result.native_text_available,
            suspected_image_only=quality_result.suspected_image_only,
            extraction_quality=quality_result.extraction_quality,
        )
        session.add(page)
        session.flush()  # assign page.id for the text blocks below

        font_sizes = [b.font_size for b in extracted_page.blocks if b.font_size is not None]
        page_median_font_size = sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else None

        for reading_order, extracted_block in enumerate(extracted_page.blocks):
            hf_flags = header_footer_flags.get(
                (extracted_page.page_number, extracted_block.block_index)
            )
            is_header = bool(hf_flags and hf_flags.is_repeated_header)
            is_footer = bool(hf_flags and hf_flags.is_repeated_footer)

            block_type, excluded, exclusion_reason = block_classification.classify_block(
                extracted_block.text,
                is_repeated_header=is_header,
                is_repeated_footer=is_footer,
                font_size=extracted_block.font_size,
                is_bold=extracted_block.is_bold,
                page_median_font_size=page_median_font_size,
                config=EXTRACTION_CONFIG,
            )

            session.add(
                TextBlock(
                    extraction_run_id=run.id,
                    page_id=page.id,
                    report_id=report.id,
                    block_index=extracted_block.block_index,
                    reading_order=reading_order,
                    raw_text=extracted_block.text,
                    cleaned_text=text_cleaning.clean_text(extracted_block.text),
                    block_type=block_type,
                    x0=extracted_block.x0,
                    y0=extracted_block.y0,
                    x1=extracted_block.x1,
                    y1=extracted_block.y1,
                    font_size=extracted_block.font_size,
                    is_bold=extracted_block.is_bold,
                    is_repeated_header=is_header,
                    is_repeated_footer=is_footer,
                    excluded_from_narrative=excluded,
                    exclusion_reason=exclusion_reason,
                )
            )

    report_quality = extraction_quality.assess_report(
        page_quality_results,
        expected_page_count=expected_page_count,
        processed_page_count=len(extracted_pages),
        config=EXTRACTION_CONFIG,
    )

    run.expected_page_count = expected_page_count
    run.processed_page_count = len(extracted_pages)
    run.usable_page_count = report_quality.usable_page_count
    run.low_text_page_count = report_quality.low_text_page_count
    run.image_only_page_count = report_quality.image_only_page_count
    run.total_word_count = report_quality.total_word_count
    run.extraction_quality = report_quality.extraction_quality
    run.review_reason = report_quality.review_reason
    run.completed_at = datetime.now(UTC)
    # Status reflects whether the run mechanically succeeded, not content
    # quality: a run that opened the PDF and processed every page is
    # COMPLETED or COMPLETED_WITH_WARNINGS even if extraction_quality is
    # FAILED (e.g. a scanned, text-less report) -- that is a quality
    # problem for a human or a later OCR milestone to address, not a
    # processing failure to retry automatically.
    run.status = (
        ExtractionStatus.COMPLETED
        if report_quality.extraction_quality == ExtractionQuality.GOOD
        else ExtractionStatus.COMPLETED_WITH_WARNINGS
    )

    session.flush()
    narrative_construction.build_narrative_document(session, run)


@dataclass
class BatchExtractionOutcome:
    completed: list[str] = field(default_factory=list)
    completed_with_warnings: list[str] = field(default_factory=list)
    needs_review: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)


def extract_eligible_reports(
    session: Session, *, limit: int | None = None, force: bool = False
) -> BatchExtractionOutcome:
    """Extract every report whose validation state permits it.

    Continues past individual report failures so one bad PDF cannot abort
    a batch run.
    """
    outcome = BatchExtractionOutcome()

    reports = session.scalars(
        select(Report)
        .where(Report.metadata_status.in_(ELIGIBLE_METADATA_STATUSES))
        .order_by(Report.directory_year, Report.local_path)
    ).all()

    if limit is not None:
        reports = reports[:limit]

    for report in reports:
        try:
            result = extract_report(session, report, force=force)
        except Exception:
            logger.exception("unexpected orchestration error extracting %s", report.local_path)
            outcome.failed.append((report.local_path, "unexpected orchestration error"))
            continue

        if result.skipped:
            outcome.skipped.append(report.local_path)
            continue

        run = result.run
        if run is None:
            continue

        if run.status == ExtractionStatus.FAILED:
            outcome.failed.append((report.local_path, run.error_message or "unknown error"))
            continue

        if run.status == ExtractionStatus.COMPLETED:
            outcome.completed.append(report.local_path)
        elif run.status == ExtractionStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(report.local_path)

        if run.extraction_quality in (ExtractionQuality.NEEDS_REVIEW, ExtractionQuality.FAILED):
            outcome.needs_review.append(report.local_path)

    return outcome

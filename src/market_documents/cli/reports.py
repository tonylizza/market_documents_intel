import uuid as uuid_module
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.config import get_settings
from market_documents.db.session import get_session
from market_documents.models.enums import (
    EmbeddingRunStatus,
    ExtractionQuality,
    ExtractionStatus,
    PassageSegmentationRunStatus,
)
from market_documents.models.extraction import ExtractionRun, Page
from market_documents.models.report import Report
from market_documents.services import corpus_audit, embedding_audit, metadata_review, segmentation_audit
from market_documents.services.extraction import (
    extract_eligible_reports,
    extract_report,
    get_current_extraction_run,
    get_current_runs_by_report,
    get_narrative_document,
)
from market_documents.services.importing import import_manifest
from market_documents.services.metadata_inspection import inspect_discovered_reports
from market_documents.services.passage_embedding import embed_eligible_segmentation_runs, embed_segmentation_run
from market_documents.services.passage_segmentation import (
    get_current_segmentation_run,
    segment_eligible_reports,
    segment_report,
)
from market_documents.services.scanning import scan_directory, write_manifest_csv
from market_documents.services.validation import validate_reports

app = typer.Typer(help="Corpus discovery, import, validation, and extraction.")


def _resolve_report(session: Session, selector: str) -> Report:
    """Resolve a report by id (UUID) or local_path -- both are unique."""
    try:
        report_id = uuid_module.UUID(selector)
    except ValueError:
        report = session.scalar(select(Report).where(Report.local_path == selector))
    else:
        report = session.get(Report, report_id)

    if report is None:
        typer.echo(f"No report found matching {selector!r}")
        raise typer.Exit(code=1)
    return report


@app.command()
def scan(
    directory: Path = typer.Argument(..., exists=True, file_okay=False, dir_okay=True),
    output: Path = typer.Option(
        Path("data/report_scan_manifest.csv"), "--output", "-o", help="Where to write the CSV manifest."
    ),
) -> None:
    """Recursively discover PDFs and emit a manifest CSV for human review."""
    rows = scan_directory(directory)
    write_manifest_csv(rows, output)
    typer.echo(f"Discovered {len(rows)} PDF(s). Manifest written to {output}")


@app.command("import")
def import_cmd(
    manifest: Path = typer.Argument(..., exists=True, dir_okay=False),
) -> None:
    """Import a reviewed manifest CSV as provisional Report records."""
    settings = get_settings()
    with get_session() as session:
        outcome = import_manifest(session, manifest, settings.companies_config_path)

    typer.echo(f"Created {len(outcome.created)} report(s)")
    for path, reason in outcome.skipped:
        typer.echo(f"  skipped {path}: {reason}")
    for row_number, message in outcome.errors:
        typer.echo(f"  error (row {row_number}): {message}")

    if outcome.errors:
        raise typer.Exit(code=1)


@app.command("inspect-metadata")
def inspect_metadata_cmd() -> None:
    """Read the first pages of each DISCOVERED report's PDF to enrich metadata."""
    with get_session() as session:
        outcome = inspect_discovered_reports(session)

    typer.echo(f"Inspected {len(outcome.inspected)} report(s)")
    for path, reason in outcome.failed:
        typer.echo(f"  failed {path}: {reason}")


@app.command()
def validate() -> None:
    """Determine whether each report has sufficient metadata for downstream analysis."""
    with get_session() as session:
        outcome = validate_reports(session)

    typer.echo(
        f"Validated: {len(outcome.validated)}, "
        f"Needs review: {len(outcome.needs_review)}, "
        f"Rejected: {len(outcome.rejected)}"
    )


@app.command("metadata-review-export")
def metadata_review_export_cmd(
    output: Path = typer.Option(
        Path("data/metadata_review.csv"), "--output", "-o", help="Where to write the review CSV."
    ),
    include_validated: bool = typer.Option(
        False, "--include-validated", help="Also export reports already VALIDATED (for a full re-review)."
    ),
) -> None:
    """Export a human-reviewable CSV of fiscal-period metadata evidence and proposals.

    Detected values are hints only -- nothing is written to the database by
    this command. Review the CSV, set reviewer_status to CONFIRMED or
    CORRECTED (adjusting proposed_* fields as needed) for rows you want
    applied, then run `reports metadata-review-import`.
    """
    with get_session() as session:
        rows = metadata_review.build_metadata_review_rows(session, include_validated=include_validated)

    metadata_review.write_metadata_review_csv(rows, output)

    high = sum(1 for r in rows if r.confidence == "HIGH")
    medium = sum(1 for r in rows if r.confidence == "MEDIUM")
    none_ = sum(1 for r in rows if r.confidence == "NONE")
    typer.echo(f"Wrote {len(rows)} row(s) to {output}")
    typer.echo(f"  high-confidence proposals: {high}")
    typer.echo(f"  ambiguous (multiple dates found): {medium}")
    typer.echo(f"  no proposal (nothing detected): {none_}")


@app.command("metadata-review-import")
def metadata_review_import_cmd(
    reviewed_csv: Path = typer.Argument(..., exists=True, dir_okay=False, help="A reviewed metadata-review CSV."),
) -> None:
    """Import a reviewed metadata CSV, applying only CONFIRMED/CORRECTED rows.

    Never sets metadata_status -- run `reports validate` afterward to
    confirm which reports now qualify.
    """
    with get_session() as session:
        outcome = metadata_review.import_metadata_review(session, reviewed_csv)

    typer.echo(
        f"Applied: {len(outcome.applied)}, "
        f"Unchanged (already applied): {len(outcome.unchanged)}, "
        f"Skipped (not confirmed/corrected): {len(outcome.skipped)}, "
        f"Conflicted: {len(outcome.conflicted)}, "
        f"Invalid: {len(outcome.invalid)}"
    )
    for report_id, reason in outcome.conflicted:
        typer.echo(f"  conflict {report_id}: {reason}")
    for row_number, reason in outcome.invalid:
        typer.echo(f"  invalid (row {row_number}): {reason}")

    if outcome.applied:
        typer.echo("Run `market-documents reports validate` to confirm validation status.")

    if outcome.invalid:
        raise typer.Exit(code=1)


@app.command()
def extract(
    selector: str = typer.Argument(..., help="Report id (UUID) or local_path."),
    force: bool = typer.Option(
        False, "--force", help="Re-extract even if an identical successful run already exists."
    ),
) -> None:
    """Run extraction for one eligible report."""
    with get_session() as session:
        report = _resolve_report(session, selector)
        outcome = extract_report(session, report, force=force)

        if outcome.skipped:
            typer.echo(f"Skipped {report.local_path}: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        typer.echo(
            f"{report.local_path}: status={run.status.value} "
            f"quality={run.extraction_quality.value if run.extraction_quality else '-'} "
            f"pages={run.processed_page_count}/{run.expected_page_count} "
            f"words={run.total_word_count}"
        )
        if run.review_reason:
            typer.echo(f"  review: {run.review_reason}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")

        failed = run.status == ExtractionStatus.FAILED

    if failed:
        raise typer.Exit(code=1)


@app.command("extract-all")
def extract_all_cmd(
    limit: int | None = typer.Option(
        None, "--limit", help="Maximum number of reports to process (defaults to the configured batch limit)."
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-extract even if identical successful runs already exist."
    ),
) -> None:
    """Extract every report whose validation state permits extraction."""
    settings = get_settings()
    effective_limit = limit if limit is not None else settings.extraction_batch_limit

    with get_session() as session:
        outcome = extract_eligible_reports(session, limit=effective_limit, force=force)

    typer.echo(
        f"Completed: {len(outcome.completed)}, "
        f"Completed with warnings: {len(outcome.completed_with_warnings)}, "
        f"Skipped: {len(outcome.skipped)}, "
        f"Needs review: {len(outcome.needs_review)}, "
        f"Failed: {len(outcome.failed)}"
    )
    for path, reason in outcome.failed:
        typer.echo(f"  failed {path}: {reason}")


@app.command("extraction-status")
def extraction_status_cmd() -> None:
    """Show the current extraction status for every report."""
    with get_session() as session:
        reports = session.scalars(
            select(Report).order_by(Report.directory_year, Report.local_path)
        ).all()
        current_runs = get_current_runs_by_report(session, [r.id for r in reports])

        for report in reports:
            run = current_runs.get(report.id)
            ticker = report.company.ticker if report.company else "?"
            period_end = report.period_end.isoformat() if report.period_end else "-"
            status = run.status.value if run else "NOT_EXTRACTED"
            quality = run.extraction_quality.value if run and run.extraction_quality else "-"
            pages = f"{run.processed_page_count}/{run.expected_page_count}" if run else "-"
            words = run.total_word_count if run else "-"
            review = run.review_reason if run else "-"
            typer.echo(
                f"{ticker:6} {str(report.id):36} {report.filename:24} "
                f"dir_year={report.directory_year} period_end={period_end} "
                f"status={status} quality={quality} pages={pages} words={words} review={review}"
            )


@app.command("extraction-review")
def extraction_review_cmd() -> None:
    """List only reports (or their current run's diagnostics) that need manual review."""
    with get_session() as session:
        reports = session.scalars(
            select(Report).order_by(Report.directory_year, Report.local_path)
        ).all()
        current_runs = get_current_runs_by_report(session, [r.id for r in reports])

        flagged = 0
        for report in reports:
            ticker = report.company.ticker if report.company else "?"
            run = current_runs.get(report.id)

            if run is not None:
                # USABLE is a legitimate "fine, just not perfect" tier, not a
                # review flag -- only genuinely poor-quality extractions and
                # runs that mechanically failed belong here.
                needs_review = run.extraction_quality in (
                    ExtractionQuality.NEEDS_REVIEW,
                    ExtractionQuality.FAILED,
                )
                if needs_review:
                    flagged += 1
                    typer.echo(
                        f"{ticker:6} {report.filename:24} "
                        f"quality={run.extraction_quality.value if run.extraction_quality else '-'} "
                        f"review={run.review_reason or '-'}"
                    )
                continue

            latest_run = session.scalar(
                select(ExtractionRun)
                .where(ExtractionRun.report_id == report.id)
                .order_by(ExtractionRun.created_at.desc())
                .limit(1)
            )
            flagged += 1
            if latest_run is None:
                typer.echo(f"{ticker:6} {report.filename:24} not yet extracted")
            else:
                typer.echo(
                    f"{ticker:6} {report.filename:24} "
                    f"latest attempt failed: {latest_run.error_message or 'unknown error'}"
                )

        if flagged == 0:
            typer.echo("No reports currently flagged for review.")


@app.command("export-text")
def export_text_cmd(
    selector: str = typer.Argument(..., help="Report id (UUID) or local_path."),
    output: Path | None = typer.Option(
        None, "--output", "-o", help="Write to this file instead of stdout."
    ),
) -> None:
    """Export the cleaned, page-aware narrative text for a report's current extraction."""
    with get_session() as session:
        report = _resolve_report(session, selector)
        current_run = get_current_extraction_run(session, report.id)
        if current_run is None:
            typer.echo(f"No successful extraction for {report.local_path}")
            raise typer.Exit(code=1)

        pages = session.scalars(
            select(Page)
            .where(Page.extraction_run_id == current_run.id)
            .order_by(Page.page_number)
        ).all()

        rendered_pages = []
        for page in pages:
            kept_blocks = sorted(
                (b for b in page.text_blocks if not b.excluded_from_narrative),
                key=lambda b: b.reading_order,
            )
            page_text = "\n\n".join(
                content
                for b in kept_blocks
                if (content := (b.cleaned_text or b.raw_text).strip())
            )
            rendered_pages.append(f"--- Page {page.page_number} ---\n\n{page_text}")

        text = "\n\n".join(rendered_pages)
        page_count = len(pages)

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(text, encoding="utf-8")
        typer.echo(f"Exported {page_count} page(s) to {output}")
    else:
        typer.echo(text)


@app.command("corpus-audit")
def corpus_audit_cmd(
    csv_output: Path | None = typer.Option(
        None, "--csv", help="Write results to this CSV path instead of printing a summary."
    ),
) -> None:
    """Corpus-wide validation and extraction status, for manual review."""
    with get_session() as session:
        rows = corpus_audit.build_corpus_audit_rows(session)

    if csv_output is not None:
        corpus_audit.write_corpus_audit_csv(rows, csv_output)
        typer.echo(f"Wrote {len(rows)} row(s) to {csv_output}")
        return

    for row in rows:
        usable_pct = f"{row.usable_page_percentage:.0%}" if row.usable_page_percentage is not None else "-"
        typer.echo(
            f"{row.ticker:6} {row.filename:24} dir_year={row.directory_year} "
            f"status={row.metadata_status} pdf_pages={row.pdf_page_count} "
            f"extraction={row.extraction_status or '-'} quality={row.extraction_quality or '-'} "
            f"usable%={usable_pct}"
        )


@app.command()
def segment(
    selector: str = typer.Argument(..., help="Report id (UUID) or local_path."),
    force: bool = typer.Option(
        False, "--force", help="Re-segment even if an identical successful run already exists."
    ),
) -> None:
    """Segment one report's current successful NarrativeDocument into passages."""
    with get_session() as session:
        report = _resolve_report(session, selector)
        outcome = segment_report(session, report, force=force)

        if outcome.ineligible:
            typer.echo(f"Ineligible: {outcome.ineligible_reason}")
            raise typer.Exit(code=1)
        if outcome.skipped:
            typer.echo(f"Skipped {report.local_path}: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        typer.echo(
            f"{report.local_path}: status={run.status.value} "
            f"passages={run.passage_count} excluded={run.excluded_passage_count}"
        )
        if run.review_reason:
            typer.echo(f"  review: {run.review_reason}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")

        failed = run.status == PassageSegmentationRunStatus.FAILED

    if failed:
        raise typer.Exit(code=1)


@app.command("segment-all")
def segment_all_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of reports to process."),
    force: bool = typer.Option(
        False, "--force", help="Re-segment even if identical successful runs already exist."
    ),
) -> None:
    """Segment every report with a current successful extraction.

    Includes reports without a confirmed period_end -- segmentation
    eligibility never depends on metadata resolution state.
    """
    with get_session() as session:
        outcome = segment_eligible_reports(session, limit=limit, force=force)

    typer.echo(
        f"Completed: {len(outcome.completed)}, "
        f"Completed with warnings: {len(outcome.completed_with_warnings)}, "
        f"Skipped: {len(outcome.skipped)}, "
        f"Ineligible: {len(outcome.ineligible)}, "
        f"Failed: {len(outcome.failed)}"
    )
    for path, reason in outcome.ineligible:
        typer.echo(f"  ineligible {path}: {reason}")
    for path, reason in outcome.failed:
        typer.echo(f"  failed {path}: {reason}")


@app.command("segmentation-status")
def segmentation_status_cmd() -> None:
    """Show current segmentation status for every report."""
    with get_session() as session:
        rows = segmentation_audit.build_segmentation_audit_rows(session)

    for row in rows:
        typer.echo(
            f"{row.ticker:6} report={row.report_id} period_end={row.period_end or '-'} "
            f"status={row.run_status or 'NOT_SEGMENTED'} "
            f"passages={row.passage_count if row.passage_count is not None else '-'} "
            f"excluded={row.excluded_passage_count if row.excluded_passage_count is not None else '-'} "
            f"words(min/med/mean/max)="
            f"{row.min_passage_word_count if row.min_passage_word_count is not None else '-'}/"
            f"{row.median_passage_word_count if row.median_passage_word_count is not None else '-'}/"
            f"{row.mean_passage_word_count if row.mean_passage_word_count is not None else '-'}/"
            f"{row.max_passage_word_count if row.max_passage_word_count is not None else '-'}"
        )
        if row.warnings:
            typer.echo(f"       warnings: {row.warnings}")


@app.command("segmentation-review")
def segmentation_review_cmd() -> None:
    """List only reports (or their current segmentation run) that need manual review."""
    with get_session() as session:
        rows = segmentation_audit.build_segmentation_audit_rows(session)

    flagged = 0
    for row in rows:
        needs_review = (
            row.run_status is None
            or row.run_status == "COMPLETED_WITH_WARNINGS"
            or row.provenance_warning_count > 0
        )
        if needs_review:
            flagged += 1
            typer.echo(f"{row.ticker:6} report={row.report_id} status={row.run_status or 'NOT_SEGMENTED'}")
            if row.warnings:
                typer.echo(f"       review: {row.warnings}")

    if flagged == 0:
        typer.echo("No reports currently flagged for review.")


@app.command()
def embed(
    selector: str = typer.Argument(..., help="Report id (UUID) or local_path."),
    force: bool = typer.Option(
        False, "--force", help="Re-embed even if an identical successful run already exists."
    ),
    batch_size: int | None = typer.Option(
        None, "--batch-size", help="Override the configured embedding batch size."
    ),
) -> None:
    """Embed one report's current successful segmentation run."""
    with get_session() as session:
        report = _resolve_report(session, selector)
        narrative = get_narrative_document(session, report.id)
        if narrative is None:
            typer.echo(f"No narrative document for {report.local_path}")
            raise typer.Exit(code=1)

        segmentation_run = get_current_segmentation_run(session, narrative.id)
        if segmentation_run is None:
            typer.echo(f"No current successful segmentation run for {report.local_path}")
            raise typer.Exit(code=1)

        outcome = embed_segmentation_run(session, segmentation_run, force=force, batch_size=batch_size)

        if outcome.ineligible:
            typer.echo(f"Ineligible: {outcome.ineligible_reason}")
            raise typer.Exit(code=1)
        if outcome.skipped:
            typer.echo(f"Skipped: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        typer.echo(
            f"{report.local_path}: status={run.status.value} "
            f"embedded={run.embedded_passage_count} skipped={run.skipped_passage_count} "
            f"model={run.model_name}@{run.model_revision[:8]}"
        )
        if run.review_reason:
            typer.echo(f"  review: {run.review_reason}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")

        failed = run.status == EmbeddingRunStatus.FAILED

    if failed:
        raise typer.Exit(code=1)


@app.command("embed-all")
def embed_all_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of segmentation runs to process."),
    force: bool = typer.Option(
        False, "--force", help="Re-embed even if identical successful runs already exist."
    ),
    batch_size: int | None = typer.Option(
        None, "--batch-size", help="Override the configured embedding batch size."
    ),
) -> None:
    """Embed every current successful segmentation run."""
    with get_session() as session:
        outcome = embed_eligible_segmentation_runs(session, limit=limit, force=force, batch_size=batch_size)

    typer.echo(
        f"Completed: {len(outcome.completed)}, "
        f"Completed with warnings: {len(outcome.completed_with_warnings)}, "
        f"Skipped: {len(outcome.skipped)}, "
        f"Ineligible: {len(outcome.ineligible)}, "
        f"Failed: {len(outcome.failed)}"
    )
    for run_id, reason in outcome.ineligible:
        typer.echo(f"  ineligible {run_id}: {reason}")
    for run_id, reason in outcome.failed:
        typer.echo(f"  failed {run_id}: {reason}")


@app.command("embedding-status")
def embedding_status_cmd() -> None:
    """Show current embedding status for every report."""
    with get_session() as session:
        rows = embedding_audit.build_embedding_audit_rows(session)

    for row in rows:
        typer.echo(
            f"{row.ticker:6} report={row.report_id} "
            f"model={row.model_name or '-'}@{(row.model_revision or '-')[:8]} "
            f"dim={row.embedding_dimension if row.embedding_dimension is not None else '-'} "
            f"eligible={row.eligible_passage_count if row.eligible_passage_count is not None else '-'} "
            f"embedded={row.embedded_count if row.embedded_count is not None else '-'} "
            f"skipped={row.skipped_count if row.skipped_count is not None else '-'} "
            f"truncated={row.truncated_count} status={row.status or 'NOT_EMBEDDED'}"
        )
        if row.warnings:
            typer.echo(f"       warnings: {row.warnings}")

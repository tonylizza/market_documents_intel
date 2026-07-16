import uuid as uuid_module
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.db.session import get_session
from market_documents.models.enums import SimilarityResultQuality, SimilarityRunStatus
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.similarity import DocumentSimilarity
from market_documents.services import similarity_audit
from market_documents.services.pairing import build_pairs
from market_documents.services.similarity import (
    get_current_document_similarity,
    get_current_similarity_run,
    score_eligible_pairs,
    score_pair,
)

app = typer.Typer(help="Report pair construction and document-level similarity scoring.")


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


def _resolve_report_pair(session: Session, selector: str) -> ReportPair:
    """Resolve a ReportPair by id (UUID) or `<earlier selector> -> <later selector>`."""
    try:
        pair_id = uuid_module.UUID(selector)
    except ValueError:
        pass
    else:
        pair = session.get(ReportPair, pair_id)
        if pair is None:
            typer.echo(f"No report pair found matching {selector!r}")
            raise typer.Exit(code=1)
        return pair

    if "->" not in selector:
        typer.echo(f"No report pair found matching {selector!r} (expected a UUID or '<earlier> -> <later>')")
        raise typer.Exit(code=1)

    earlier_selector, later_selector = (part.strip() for part in selector.split("->", 1))
    earlier = _resolve_report(session, earlier_selector)
    later = _resolve_report(session, later_selector)
    pair = session.scalar(
        select(ReportPair).where(
            ReportPair.earlier_report_id == earlier.id,
            ReportPair.later_report_id == later.id,
        )
    )
    if pair is None:
        typer.echo(f"No report pair found for {earlier.local_path} -> {later.local_path}")
        raise typer.Exit(code=1)
    return pair


@app.command()
def build() -> None:
    """Pair each validated report with its immediate predecessor by period_end."""
    with get_session() as session:
        outcome = build_pairs(session)

    typer.echo(f"Created {len(outcome.created)} pair(s), skipped {outcome.skipped_existing} existing")


@app.command("list")
def list_cmd() -> None:
    """List all report pairs."""
    with get_session() as session:
        pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id)).all()
        for pair in pairs:
            earlier = session.get(Report, pair.earlier_report_id)
            later = session.get(Report, pair.later_report_id)
            transition_flag = " [TRANSITION]" if pair.is_transition else ""
            typer.echo(
                f"{earlier.filename} -> {later.filename} "
                f"| gap={pair.gap_months}mo{transition_flag}"
            )


@app.command()
def score(
    selector: str = typer.Argument(..., help="ReportPair id (UUID), or '<earlier report> -> <later report>'."),
    force: bool = typer.Option(
        False, "--force", help="Rescore even if an identical successful similarity run already exists."
    ),
) -> None:
    """Score one ReportPair's document-level lexical similarity."""
    with get_session() as session:
        pair = _resolve_report_pair(session, selector)
        outcome = score_pair(session, pair, force=force)

        if outcome.ineligible:
            typer.echo(f"Ineligible: {outcome.ineligible_reason}")
            raise typer.Exit(code=1)
        if outcome.skipped:
            typer.echo(f"Skipped: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        doc_similarity = get_current_document_similarity(session, pair.id) if run.status != SimilarityRunStatus.FAILED else None

        typer.echo(f"pair={pair.id} status={run.status.value}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")
        if doc_similarity is not None:
            typer.echo(
                f"  quality={doc_similarity.quality_status.value} "
                f"cosine={_fmt(doc_similarity.lexical_cosine_similarity)} "
                f"jaccard={_fmt(doc_similarity.jaccard_similarity)} "
                f"diff={_fmt(doc_similarity.diff_similarity)} (mode={_diff_mode_label(doc_similarity)}) "
                f"edit={_fmt(doc_similarity.edit_similarity)} "
                f"word_change_ratio={_fmt(doc_similarity.word_count_change_ratio)}"
            )
            typer.echo(
                f"  primary_eligible={doc_similarity.primary_analysis_eligible} "
                f"configuration_hash={run.configuration_hash[:12]}"
            )
            if doc_similarity.review_reason:
                typer.echo(f"  review: {doc_similarity.review_reason}")

        failed = run.status == SimilarityRunStatus.FAILED

    if failed:
        raise typer.Exit(code=1)


@app.command("score-all")
def score_all_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of pairs to process."),
    force: bool = typer.Option(
        False, "--force", help="Rescore even if identical successful similarity runs already exist."
    ),
) -> None:
    """Score every ReportPair currently eligible for similarity scoring."""
    with get_session() as session:
        outcome = score_eligible_pairs(session, limit=limit, force=force)

    typer.echo(
        f"Completed: {len(outcome.completed)}, "
        f"Completed with warnings: {len(outcome.completed_with_warnings)}, "
        f"Skipped: {len(outcome.skipped)}, "
        f"Ineligible: {len(outcome.ineligible)}, "
        f"Failed: {len(outcome.failed)}"
    )
    for pair_id, reason in outcome.ineligible:
        typer.echo(f"  ineligible {pair_id}: {reason}")
    for pair_id, reason in outcome.failed:
        typer.echo(f"  failed {pair_id}: {reason}")


def _fmt(value: float | None) -> str:
    return f"{value:.3f}" if value is not None else "-"


def _diff_mode_label(doc_similarity: DocumentSimilarity) -> str:
    return doc_similarity.diff_mode.value if doc_similarity.diff_mode else "-"


@app.command("similarity-status")
def similarity_status_cmd() -> None:
    """Show current similarity-scoring status for every report pair."""
    with get_session() as session:
        pairs = session.scalars(
            select(ReportPair).order_by(ReportPair.company_id, ReportPair.gap_months)
        ).all()

        for pair in pairs:
            earlier = session.get(Report, pair.earlier_report_id)
            later = session.get(Report, pair.later_report_id)
            ticker = pair.company.ticker if pair.company else "?"
            run = get_current_similarity_run(session, pair.id)
            doc_similarity = get_current_document_similarity(session, pair.id)
            transition_flag = " [TRANSITION]" if pair.is_transition else ""

            status = run.status.value if run else "NOT_SCORED"
            quality = doc_similarity.quality_status.value if doc_similarity else "-"
            eligible = doc_similarity.primary_analysis_eligible if doc_similarity else "-"

            typer.echo(
                f"{ticker:6} pair={pair.id} "
                f"{earlier.period_end or '?'} -> {later.period_end or '?'} "
                f"gap={pair.gap_months}mo{transition_flag} "
                f"status={status} quality={quality} primary_eligible={eligible}"
            )
            if doc_similarity is not None:
                typer.echo(
                    f"       cosine={_fmt(doc_similarity.lexical_cosine_similarity)} "
                    f"jaccard={_fmt(doc_similarity.jaccard_similarity)} "
                    f"diff={_fmt(doc_similarity.diff_similarity)} (mode={_diff_mode_label(doc_similarity)}) "
                    f"edit={_fmt(doc_similarity.edit_similarity)} "
                    f"word_change_ratio={_fmt(doc_similarity.word_count_change_ratio)}"
                )
                if doc_similarity.review_reason:
                    typer.echo(f"       review: {doc_similarity.review_reason}")


@app.command("similarity-review")
def similarity_review_cmd() -> None:
    """Show only results requiring review or excluded from primary analysis."""
    with get_session() as session:
        pairs = session.scalars(
            select(ReportPair).order_by(ReportPair.company_id, ReportPair.gap_months)
        ).all()

        flagged = 0
        for pair in pairs:
            ticker = pair.company.ticker if pair.company else "?"
            doc_similarity = get_current_document_similarity(session, pair.id)

            if doc_similarity is not None:
                needs_attention = (
                    not doc_similarity.primary_analysis_eligible
                    or doc_similarity.quality_status
                    in (SimilarityResultQuality.NEEDS_REVIEW, SimilarityResultQuality.FAILED)
                )
                if needs_attention:
                    flagged += 1
                    typer.echo(
                        f"{ticker:6} pair={pair.id} quality={doc_similarity.quality_status.value} "
                        f"primary_eligible={doc_similarity.primary_analysis_eligible}"
                    )
                    typer.echo(
                        f"       review: {doc_similarity.review_reason or '-'} | "
                        f"exclusion: {doc_similarity.primary_analysis_exclusion_reason or '-'}"
                    )
                continue

            run = get_current_similarity_run(session, pair.id)
            if run is None:
                flagged += 1
                typer.echo(f"{ticker:6} pair={pair.id} not yet scored")

        if flagged == 0:
            typer.echo("No similarity results currently flagged for review.")


@app.command("similarity-list")
def similarity_list_cmd(
    metric: str = typer.Option(
        "lexical_cosine_similarity", "--metric", help=f"One of: {', '.join(similarity_audit.RANKABLE_FIELDS)}"
    ),
    ascending: bool = typer.Option(True, "--ascending/--descending", help="Sort order."),
    ticker: str | None = typer.Option(None, "--ticker", help="Filter to one company ticker."),
    include_transitions: bool = typer.Option(
        False, "--include-transitions", help="Include transition-period pairs (excluded by default)."
    ),
    quality: str | None = typer.Option(
        None, "--quality", help="Filter to one result quality (GOOD, USABLE, NEEDS_REVIEW, FAILED)."
    ),
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of rows to show."),
) -> None:
    """List and rank current similarity results by a selected metric."""
    quality_filter = SimilarityResultQuality(quality.upper()) if quality else None

    with get_session() as session:
        rows = similarity_audit.rank_by_metric(
            session,
            metric,
            ascending=ascending,
            ticker=ticker,
            include_transitions=include_transitions,
            quality_filter=quality_filter,
            limit=limit,
        )

    for row in rows:
        transition_flag = " [TRANSITION]" if row.is_transition else ""
        typer.echo(
            f"{row.rank:4} {row.ticker:6} pair={row.report_pair_id} "
            f"{row.metric_name}={row.metric_value:.3f} quality={row.quality_status.value} "
            f"primary_eligible={row.primary_analysis_eligible}{transition_flag}"
        )


@app.command("similarity-audit")
def similarity_audit_cmd(
    csv_output: Path | None = typer.Option(
        None, "--csv", help="Write results to this CSV path instead of printing a summary."
    ),
) -> None:
    """Corpus-wide similarity-scoring status and metrics, for manual review."""
    with get_session() as session:
        rows = similarity_audit.build_similarity_audit_rows(session)

    if csv_output is not None:
        similarity_audit.write_similarity_audit_csv(rows, csv_output)
        typer.echo(f"Wrote {len(rows)} row(s) to {csv_output}")
        return

    for row in rows:
        transition_flag = " [TRANSITION]" if row.is_transition else ""
        typer.echo(
            f"{row.ticker:6} pair={row.report_pair_id} "
            f"{row.earlier_period_end or '?'} -> {row.later_period_end or '?'} "
            f"gap={row.gap_months}mo{transition_flag} "
            f"status={row.similarity_run_status or '-'} quality={row.result_quality or '-'} "
            f"cosine={_fmt(row.lexical_cosine_similarity)} jaccard={_fmt(row.jaccard_similarity)} "
            f"diff={_fmt(row.diff_similarity)} (mode={row.diff_mode or '-'}) edit={_fmt(row.edit_similarity)} "
            f"primary_eligible={row.primary_analysis_eligible if row.primary_analysis_eligible is not None else '-'} "
            f"configuration_hash={row.configuration_hash[:12] if row.configuration_hash else '-'}"
        )

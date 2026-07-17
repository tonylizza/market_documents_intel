import csv
import uuid as uuid_module
from pathlib import Path

import typer
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.db.session import get_session
from market_documents.models.alignment import PassageAlignment
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentRunStatus,
    AlignmentStatus,
    SimilarityResultQuality,
    SimilarityRunStatus,
)
from market_documents.models.passage import Passage
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.models.similarity import DocumentSimilarity
from market_documents.services import (
    alignment_audit,
    feature_audit,
    feature_export,
    feature_review_sample,
    passage_alignment,
    review_sample,
    similarity_audit,
)
from market_documents.services.feature_extraction import (
    build_eligible_features,
    build_features,
    get_current_feature_run,
    get_current_report_pair_features,
)
from market_documents.services.pairing import build_pairs
from market_documents.services.similarity import (
    get_current_document_similarity,
    get_current_similarity_run,
    score_eligible_pairs,
    score_pair,
)

app = typer.Typer(help="Report pair construction, document-level similarity scoring, and passage alignment.")


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


def _page_range(passage: Passage | None) -> str | None:
    if passage is None:
        return None
    if passage.first_page_number == passage.last_page_number:
        return str(passage.first_page_number)
    return f"{passage.first_page_number}-{passage.last_page_number}"


@app.command()
def align(
    selector: str = typer.Argument(..., help="ReportPair id (UUID), or '<earlier report> -> <later report>'."),
    force: bool = typer.Option(
        False, "--force", help="Realign even if an identical successful alignment run already exists."
    ),
) -> None:
    """Align one ReportPair's passages between its earlier and later reports."""
    with get_session() as session:
        pair = _resolve_report_pair(session, selector)
        outcome = passage_alignment.align_pair(session, pair, force=force)

        if outcome.ineligible:
            typer.echo(f"Ineligible: {outcome.ineligible_reason}")
            raise typer.Exit(code=1)
        if outcome.skipped:
            typer.echo(f"Skipped: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        typer.echo(f"pair={pair.id} status={run.status.value}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")
        else:
            typer.echo(
                f"  matched={run.matched_count} unchanged={run.unchanged_count} "
                f"lightly_modified={run.lightly_modified_count} "
                f"substantially_modified={run.substantially_modified_count} "
                f"new={run.new_count} removed={run.removed_count} ambiguous={run.ambiguous_count}"
            )
            if run.review_reason:
                typer.echo(f"  review: {run.review_reason}")

        failed = run.status == AlignmentRunStatus.FAILED

    if failed:
        raise typer.Exit(code=1)


@app.command("align-all")
def align_all_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of pairs to process."),
    force: bool = typer.Option(
        False, "--force", help="Realign even if identical successful alignment runs already exist."
    ),
) -> None:
    """Align every ReportPair currently eligible for passage alignment.

    Includes irregular-gap and transition pairs -- eligibility depends only
    on segmentation/embedding availability, never on document-level
    similarity quality.
    """
    with get_session() as session:
        outcome = passage_alignment.align_eligible_pairs(session, limit=limit, force=force)

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


@app.command("alignment-status")
def alignment_status_cmd() -> None:
    """Show current passage-alignment status for every report pair."""
    with get_session() as session:
        rows = alignment_audit.build_alignment_audit_rows(session)

    for row in rows:
        transition_flag = " [TRANSITION]" if row.is_transition else ""
        typer.echo(
            f"{row.ticker:6} pair={row.report_pair_id} "
            f"{row.earlier_period_end or '?'} -> {row.later_period_end or '?'} "
            f"gap={row.gap_months}mo{transition_flag} "
            f"doc_sim_quality={row.document_similarity_quality or '-'} "
            f"status={row.status or 'NOT_ALIGNED'}"
        )
        if row.status is not None:
            typer.echo(
                f"       matched={row.matched_count} unchanged={row.unchanged_count} "
                f"lightly_modified={row.lightly_modified_count} "
                f"substantially_modified={row.substantially_modified_count} "
                f"new={row.new_count} removed={row.removed_count} ambiguous={row.ambiguous_count}"
            )
            typer.echo(
                f"       confidence(high/med/low/needs_review)="
                f"{row.high_confidence_count}/{row.medium_confidence_count}/"
                f"{row.low_confidence_count}/{row.needs_review_confidence_count}"
            )
            if row.warnings:
                typer.echo(f"       review: {row.warnings}")


@app.command("alignment-review")
def alignment_review_cmd() -> None:
    """Show alignments/pairs needing manual review: ambiguous, LOW/NEEDS_REVIEW
    confidence, semantic/lexical disagreements, likely split/merge cases,
    irregular-gap pairs, and failed or warning runs."""
    with get_session() as session:
        rows = alignment_audit.build_alignment_audit_rows(session)

    flagged = 0
    for row in rows:
        needs_attention = (
            row.status is None
            or row.status in ("FAILED", "COMPLETED_WITH_WARNINGS")
            or (row.ambiguous_count or 0) > 0
            or row.low_confidence_count > 0
            or row.needs_review_confidence_count > 0
            or row.disagreement_count > 0
            or row.likely_split_merge_count > 0
        )
        if needs_attention:
            flagged += 1
            transition_flag = " [TRANSITION]" if row.is_transition else ""
            typer.echo(
                f"{row.ticker:6} pair={row.report_pair_id} gap={row.gap_months}mo{transition_flag} "
                f"status={row.status or 'NOT_ALIGNED'}"
            )
            typer.echo(
                f"       ambiguous={row.ambiguous_count or 0} low_conf={row.low_confidence_count} "
                f"needs_review_conf={row.needs_review_confidence_count} disagreement={row.disagreement_count} "
                f"split_merge={row.likely_split_merge_count}"
            )
            if row.warnings:
                typer.echo(f"       review: {row.warnings}")

    if flagged == 0:
        typer.echo("No alignment results currently flagged for review.")


@app.command("alignment-list")
def alignment_list_cmd(
    ticker: str | None = typer.Option(None, "--ticker", help="Filter to one company ticker."),
    pair_selector: str | None = typer.Option(
        None, "--pair", help="Filter to one ReportPair id or '<earlier> -> <later>'."
    ),
    status: str | None = typer.Option(None, "--status", help="Filter to one AlignmentStatus."),
    confidence: str | None = typer.Option(None, "--confidence", help="Filter to one AlignmentConfidence."),
    min_semantic: float | None = typer.Option(None, "--min-semantic", help="Minimum semantic_similarity."),
    min_lexical: float | None = typer.Option(None, "--min-lexical", help="Minimum lexical_cosine_similarity."),
    limit: int | None = typer.Option(None, "--limit"),
) -> None:
    """List individual passage alignments across all current alignment runs.

    Never prints source passage text by default.
    """
    status_filter = AlignmentStatus(status.upper()) if status else None
    confidence_filter = AlignmentConfidence(confidence.upper()) if confidence else None

    with get_session() as session:
        pair_id_filter = _resolve_report_pair(session, pair_selector).id if pair_selector is not None else None

        pairs = session.scalars(select(ReportPair).options(joinedload(ReportPair.company))).all()
        pairs_by_id = {p.id: p for p in pairs}
        current_runs = passage_alignment.get_current_alignment_runs_by_pair(session, list(pairs_by_id))
        run_id_to_pair_id = {run.id: pair_id for pair_id, run in current_runs.items()}

        if not run_id_to_pair_id:
            typer.echo("No current alignment results.")
            return

        query = select(PassageAlignment).where(PassageAlignment.alignment_run_id.in_(list(run_id_to_pair_id)))
        if status_filter is not None:
            query = query.where(PassageAlignment.alignment_status == status_filter)
        if confidence_filter is not None:
            query = query.where(PassageAlignment.confidence == confidence_filter)
        if min_semantic is not None:
            query = query.where(PassageAlignment.semantic_similarity >= min_semantic)
        if min_lexical is not None:
            query = query.where(PassageAlignment.lexical_cosine_similarity >= min_lexical)

        alignment_rows = session.scalars(query).all()

        results: list[tuple[ReportPair, PassageAlignment]] = []
        for alignment_row in alignment_rows:
            pair = pairs_by_id.get(run_id_to_pair_id.get(alignment_row.alignment_run_id))
            if pair is None:
                continue
            if pair_id_filter is not None and pair.id != pair_id_filter:
                continue
            if ticker is not None and pair.company.ticker.upper() != ticker.upper():
                continue
            results.append((pair, alignment_row))

        if limit is not None:
            results = results[:limit]

        for pair, alignment_row in results:
            typer.echo(
                f"{pair.company.ticker:6} pair={pair.id} "
                f"earlier_passage={alignment_row.earlier_passage_id or '-'} "
                f"later_passage={alignment_row.later_passage_id or '-'} "
                f"status={alignment_row.alignment_status.value} confidence={alignment_row.confidence.value} "
                f"semantic={_fmt(alignment_row.semantic_similarity)} "
                f"lexical={_fmt(alignment_row.lexical_cosine_similarity)} "
                f"combined={_fmt(alignment_row.combined_score)}"
            )


@app.command("alignment-audit")
def alignment_audit_cmd(
    csv_output: Path | None = typer.Option(
        None, "--csv", help="Write results to this CSV path instead of printing a summary."
    ),
) -> None:
    """Corpus-wide passage-alignment status and metrics, for manual review."""
    with get_session() as session:
        rows = alignment_audit.build_alignment_audit_rows(session)

    if csv_output is not None:
        alignment_audit.write_alignment_audit_csv(rows, csv_output)
        typer.echo(f"Wrote {len(rows)} row(s) to {csv_output}")
        return

    for row in rows:
        transition_flag = " [TRANSITION]" if row.is_transition else ""
        typer.echo(
            f"{row.ticker:6} pair={row.report_pair_id} gap={row.gap_months}mo{transition_flag} "
            f"status={row.status or 'NOT_ALIGNED'} "
            f"matched={row.matched_count if row.matched_count is not None else '-'} "
            f"new={row.new_count if row.new_count is not None else '-'} "
            f"removed={row.removed_count if row.removed_count is not None else '-'} "
            f"ambiguous={row.ambiguous_count if row.ambiguous_count is not None else '-'} "
            f"pct_later_matched={row.percent_later_matched if row.percent_later_matched is not None else '-'}"
        )


@app.command("export-alignment")
def export_alignment_cmd(
    pair_selector: str = typer.Argument(..., help="ReportPair id (UUID), or '<earlier report> -> <later report>'."),
    output: Path = typer.Option(..., "--output", "-o", help="Output CSV path."),
    include_text: bool = typer.Option(
        False, "--include-text", help="Include passage text -- never commit this export."
    ),
) -> None:
    """Export one ReportPair's current alignment results to CSV."""
    with get_session() as session:
        pair = _resolve_report_pair(session, pair_selector)
        run = passage_alignment.get_current_alignment_run(session, pair.id)
        if run is None:
            typer.echo(f"No current successful alignment run for pair {pair.id}")
            raise typer.Exit(code=1)

        rows = session.scalars(
            select(PassageAlignment).where(PassageAlignment.alignment_run_id == run.id)
        ).all()

        passage_ids = {r.earlier_passage_id for r in rows if r.earlier_passage_id} | {
            r.later_passage_id for r in rows if r.later_passage_id
        }
        passages_by_id = (
            {p.id: p for p in session.scalars(select(Passage).where(Passage.id.in_(passage_ids))).all()}
            if passage_ids
            else {}
        )

        output.parent.mkdir(parents=True, exist_ok=True)
        fieldnames = [
            "earlier_passage_id", "later_passage_id", "earlier_report_id", "later_report_id",
            "earlier_page_range", "later_page_range", "heading_text",
            "semantic_similarity", "lexical_cosine_similarity", "jaccard_similarity", "edit_similarity",
            "heading_similarity", "length_ratio", "position_difference", "combined_score",
            "alignment_status", "confidence", "review_reason",
        ]
        if include_text:
            fieldnames += ["earlier_text", "later_text"]

        with output.open("w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            for alignment_row in rows:
                earlier_passage = passages_by_id.get(alignment_row.earlier_passage_id)
                later_passage = passages_by_id.get(alignment_row.later_passage_id)
                record = {
                    "earlier_passage_id": alignment_row.earlier_passage_id,
                    "later_passage_id": alignment_row.later_passage_id,
                    "earlier_report_id": pair.earlier_report_id,
                    "later_report_id": pair.later_report_id,
                    "earlier_page_range": _page_range(earlier_passage),
                    "later_page_range": _page_range(later_passage),
                    "heading_text": (
                        (later_passage.heading_text if later_passage else None)
                        or (earlier_passage.heading_text if earlier_passage else None)
                    ),
                    "semantic_similarity": alignment_row.semantic_similarity,
                    "lexical_cosine_similarity": alignment_row.lexical_cosine_similarity,
                    "jaccard_similarity": alignment_row.jaccard_similarity,
                    "edit_similarity": alignment_row.edit_similarity,
                    "heading_similarity": alignment_row.heading_similarity,
                    "length_ratio": alignment_row.length_ratio,
                    "position_difference": alignment_row.position_difference,
                    "combined_score": alignment_row.combined_score,
                    "alignment_status": alignment_row.alignment_status.value,
                    "confidence": alignment_row.confidence.value,
                    "review_reason": alignment_row.review_reason,
                }
                if include_text:
                    record["earlier_text"] = earlier_passage.raw_text if earlier_passage else None
                    record["later_text"] = later_passage.raw_text if later_passage else None
                writer.writerow(record)

    typer.echo(f"Wrote {len(rows)} row(s) to {output}")
    if include_text:
        typer.echo("WARNING: this export includes passage text -- do not commit it.")


@app.command("review-sample")
def review_sample_cmd(
    output: Path = typer.Option(
        Path("data/alignment_review_sample.csv"), "--output", "-o", help="Where to write the review sample CSV."
    ),
    seed: int = typer.Option(42, "--seed", help="Deterministic sampling seed."),
    per_category: int = typer.Option(3, "--per-category", help="Maximum examples per category."),
    include_text: bool = typer.Option(
        False, "--include-text", help="Include passage text -- never commit this export."
    ),
) -> None:
    """Deterministic, balanced manual-review sample across all current alignment results."""
    with get_session() as session:
        rows = review_sample.build_review_sample(
            session, seed=seed, per_category=per_category, include_text=include_text
        )

    review_sample.write_review_sample_csv(rows, output)
    typer.echo(f"Wrote {len(rows)} row(s) to {output}")


# --------------------------------------------------------------------------
# Milestone 5: disclosure-change features
# --------------------------------------------------------------------------


@app.command("features-build")
def features_build_cmd(
    selector: str = typer.Argument(..., help="ReportPair id (UUID), or '<earlier report> -> <later report>'."),
    force: bool = typer.Option(
        False, "--force", help="Rebuild even if an identical successful feature run already exists."
    ),
) -> None:
    """Build disclosure-change features for one ReportPair."""
    with get_session() as session:
        pair = _resolve_report_pair(session, selector)
        outcome = build_features(session, pair, force=force)

        if outcome.ineligible:
            typer.echo(f"Ineligible: {outcome.ineligible_reason}")
            raise typer.Exit(code=1)
        if outcome.skipped:
            typer.echo(f"Skipped: {outcome.skip_reason}")
            return

        run = outcome.run
        assert run is not None
        typer.echo(f"pair={pair.id} status={run.status.value}")
        if run.error_message:
            typer.echo(f"  error: {run.error_message}")
        else:
            feat = get_current_report_pair_features(session, pair.id)
            if feat is not None:
                typer.echo(
                    f"  quality={feat.feature_quality.value} primary_eligible={feat.primary_eligible} "
                    f"score={_fmt(feat.disclosure_change_score)}"
                )
            if run.review_reason:
                typer.echo(f"  review: {run.review_reason}")

        failed = run.status.value == "FAILED"

    if failed:
        raise typer.Exit(code=1)


@app.command("features-build-all")
def features_build_all_cmd(
    limit: int | None = typer.Option(None, "--limit", help="Maximum number of pairs to process."),
    force: bool = typer.Option(
        False, "--force", help="Rebuild even if identical successful feature runs already exist."
    ),
) -> None:
    """Build disclosure-change features for every currently eligible ReportPair."""
    with get_session() as session:
        outcome = build_eligible_features(session, limit=limit, force=force)

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


@app.command("features-status")
def features_status_cmd(
    ticker: str | None = typer.Option(None, "--ticker", help="Filter to one company ticker."),
    quality: str | None = typer.Option(None, "--quality", help="Filter to one FeatureQuality."),
    primary_only: bool = typer.Option(False, "--primary-only", help="Only show primary-eligible pairs."),
) -> None:
    """Show current disclosure-change feature status for every report pair."""
    with get_session() as session:
        rows = feature_audit.build_feature_run_audit_rows(session)

    for row in rows:
        if ticker is not None and row.ticker.upper() != ticker.upper():
            continue
        if quality is not None and (row.feature_quality or "").upper() != quality.upper():
            continue
        if primary_only and not row.primary_eligible:
            continue

        transition_flag = " [TRANSITION]" if row.is_transition else ""
        irregular_flag = " [IRREGULAR_GAP]" if row.irregular_gap else ""
        typer.echo(
            f"{row.ticker:6} pair={row.report_pair_id} "
            f"{row.earlier_period_end or '?'} -> {row.later_period_end or '?'} "
            f"gap={row.gap_months}mo{transition_flag}{irregular_flag} "
            f"status={row.status or 'NOT_BUILT'} quality={row.feature_quality or '-'} "
            f"primary_eligible={row.primary_eligible if row.primary_eligible is not None else '-'}"
        )
        if row.disclosure_change_score is not None:
            typer.echo(
                f"       score={row.disclosure_change_score:.3f} "
                f"alignment_coverage_words={_fmt(row.alignment_coverage_words)} "
                f"embedded_coverage(e/l)={_fmt(row.embedded_coverage_earlier)}/{_fmt(row.embedded_coverage_later)}"
            )
        if row.warning_reasons:
            typer.echo(f"       warning: {row.warning_reasons}")
        if row.exclusion_reasons:
            typer.echo(f"       exclusion: {row.exclusion_reasons}")


@app.command("features-audit")
def features_audit_cmd(
    output_dir: Path = typer.Option(
        Path("data/audits"), "--output-dir", help="Directory to write the M5 audit CSVs into."
    ),
) -> None:
    """Write every Milestone 5 audit CSV: feature_run_audit, report_pair_feature_review,
    feature_component_summary, excluded_passages_summary, and irregular_gap_pairs."""
    with get_session() as session:
        run_rows = feature_audit.build_feature_run_audit_rows(session)
        review_rows = feature_audit.build_feature_review_rows(session)
        component_rows = feature_audit.build_feature_component_summary_rows(session)
        excluded_rows = feature_audit.build_excluded_passages_summary_rows(session)
        irregular_rows = feature_audit.build_irregular_gap_rows(session)

    feature_audit.write_feature_run_audit_csv(run_rows, output_dir / "feature_run_audit.csv")
    feature_audit.write_feature_review_csv(review_rows, output_dir / "report_pair_feature_review.csv")
    feature_audit.write_feature_component_summary_csv(component_rows, output_dir / "feature_component_summary.csv")
    feature_audit.write_excluded_passages_summary_csv(
        excluded_rows, output_dir / "excluded_passages_summary.csv"
    )
    feature_audit.write_irregular_gap_csv(irregular_rows, output_dir / "irregular_gap_pairs.csv")

    typer.echo(f"Wrote 5 audit CSV(s) to {output_dir}")


@app.command("features-export")
def features_export_cmd(
    output: Path = typer.Option(..., "--output", "-o", help="Output CSV path."),
    primary_only: bool = typer.Option(
        False, "--primary-only", help="Export only primary-eligible observations."
    ),
) -> None:
    """Export research-ready pair-level disclosure-change features to CSV."""
    with get_session() as session:
        rows = feature_export.build_export_rows(session, primary_only=primary_only)

    feature_export.write_export_csv(rows, output)
    typer.echo(f"Wrote {len(rows)} row(s) to {output}")


@app.command("features-review-export")
def features_review_export_cmd(
    output: Path = typer.Option(
        Path("data/audits/report_pair_feature_review.csv"), "--output", "-o", help="Output CSV path."
    ),
) -> None:
    """Export pairs with feature exclusions or warnings to CSV."""
    with get_session() as session:
        rows = feature_audit.build_feature_review_rows(session)

    feature_audit.write_feature_review_csv(rows, output)
    typer.echo(f"Wrote {len(rows)} row(s) to {output}")


@app.command("features-show")
def features_show_cmd(
    pair_id: str = typer.Option(
        ..., "--pair-id", help="ReportPair id (UUID), or '<earlier report> -> <later report>'."
    ),
) -> None:
    """Show one ReportPair's disclosure-change features in full detail."""
    with get_session() as session:
        pair = _resolve_report_pair(session, pair_id)
        run = get_current_feature_run(session, pair.id)
        if run is None:
            typer.echo(f"No current successful feature run for pair {pair.id}")
            raise typer.Exit(code=1)
        feat = get_current_report_pair_features(session, pair.id)
        assert feat is not None

        typer.echo(f"pair={pair.id} ticker={pair.company.ticker} gap={pair.gap_months}mo")
        typer.echo(
            f"quality={feat.feature_quality.value} primary_eligible={feat.primary_eligible} "
            f"irregular_gap={feat.irregular_gap} transition={feat.transition_report}"
        )
        typer.echo(f"disclosure_change_score={_fmt(feat.disclosure_change_score)} score_version={feat.score_version}")
        typer.echo(
            "score components: "
            f"unchanged={_fmt(feat.score_unchanged_component)} "
            f"lightly_modified={_fmt(feat.score_lightly_modified_component)} "
            f"substantially_modified={_fmt(feat.score_substantially_modified_component)} "
            f"new={_fmt(feat.score_new_component)} removed={_fmt(feat.score_removed_component)} "
            f"ambiguous={_fmt(feat.score_ambiguous_component)}"
        )
        typer.echo(
            "raw counts: "
            f"unchanged={feat.unchanged_count} lightly_modified={feat.lightly_modified_count} "
            f"substantially_modified={feat.substantially_modified_count} new={feat.new_count} "
            f"removed={feat.removed_count} ambiguous={feat.ambiguous_count}"
        )
        typer.echo(
            "eligible word rates: "
            f"unchanged={_fmt(feat.unchanged_rate_words)} lightly_modified={_fmt(feat.lightly_modified_rate_words)} "
            f"substantially_modified={_fmt(feat.substantially_modified_rate_words)} "
            f"new={_fmt(feat.new_rate_words)} removed={_fmt(feat.removed_rate_words)} "
            f"ambiguous={_fmt(feat.ambiguous_rate_words)}"
        )
        typer.echo(
            "coverage: "
            f"alignment(count/words)={_fmt(feat.alignment_coverage_count)}/{_fmt(feat.alignment_coverage_words)} "
            f"embedded(e/l)={_fmt(feat.embedded_coverage_earlier)}/{_fmt(feat.embedded_coverage_later)} "
            f"high_confidence_share={_fmt(feat.high_confidence_share)} "
            f"review_required_share={_fmt(feat.review_required_share)}"
        )
        typer.echo(
            "low-information: "
            f"excluded_count={feat.excluded_low_information_count} excluded_words={feat.excluded_low_information_words:.1f} "
            f"heading_fragment_share(e/l)={_fmt(feat.heading_fragment_share_earlier)}/{_fmt(feat.heading_fragment_share_later)}"
        )
        if feat.warning_reasons:
            typer.echo(f"warning: {feat.warning_reasons}")
        if feat.exclusion_reasons:
            typer.echo(f"exclusion: {feat.exclusion_reasons}")
    if include_text:
        typer.echo("WARNING: this export includes passage text -- do not commit it.")

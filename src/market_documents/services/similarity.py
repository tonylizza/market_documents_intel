"""Similarity-scoring orchestration: run lifecycle, idempotency, and persistence.

Directly parallels `services/extraction.py`: this module owns the
configuration fingerprint that drives idempotent skipping, and the
query-time rule for selecting a ReportPair's current successful similarity
result. Business logic (source selection, metric computation, quality
assessment) is delegated to `similarity_metrics` and `similarity_quality`;
this module only wires them together and persists the result.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import PairNotEligibleError
from market_documents.models.enums import ExtractionQuality, SimilarityResultQuality, SimilarityRunStatus
from market_documents.models.extraction import ExtractionRun, NarrativeDocument
from market_documents.models.report_pair import ReportPair
from market_documents.models.similarity import DocumentSimilarity, SimilarityRun
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.similarity_config import (
    ALGORITHM_VERSION,
    SIMILARITY_CONFIG,
    compute_configuration_hash,
)
from market_documents.services.similarity_metrics import compute_length_change_features, compute_metrics
from market_documents.services.similarity_quality import assess_similarity

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PairSourceSelection:
    earlier_run: ExtractionRun
    later_run: ExtractionRun
    earlier_narrative: NarrativeDocument
    later_narrative: NarrativeDocument


def select_source_narratives(session: Session, pair: ReportPair) -> PairSourceSelection:
    """Select the current successful NarrativeDocuments for both sides of a pair.

    Raises `PairNotEligibleError` when the pair cannot currently be scored:
    either report lacks a current successful extraction, either extraction's
    quality is FAILED, either report lacks a NarrativeDocument, or either
    narrative is empty. USABLE and NEEDS_REVIEW extraction quality are
    eligible (NEEDS_REVIEW is flagged downstream by `similarity_quality`,
    not excluded here).
    """
    earlier_run = get_current_extraction_run(session, pair.earlier_report_id)
    if earlier_run is None:
        raise PairNotEligibleError("earlier report has no current successful extraction")
    later_run = get_current_extraction_run(session, pair.later_report_id)
    if later_run is None:
        raise PairNotEligibleError("later report has no current successful extraction")

    if earlier_run.extraction_quality == ExtractionQuality.FAILED:
        raise PairNotEligibleError("earlier report extraction quality is FAILED")
    if later_run.extraction_quality == ExtractionQuality.FAILED:
        raise PairNotEligibleError("later report extraction quality is FAILED")

    earlier_narrative = session.scalar(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id == earlier_run.id)
    )
    if earlier_narrative is None:
        raise PairNotEligibleError("earlier report has no narrative document")
    later_narrative = session.scalar(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id == later_run.id)
    )
    if later_narrative is None:
        raise PairNotEligibleError("later report has no narrative document")

    if earlier_narrative.word_count == 0 or not earlier_narrative.cleaned_text.strip():
        raise PairNotEligibleError("earlier narrative document is empty")
    if later_narrative.word_count == 0 or not later_narrative.cleaned_text.strip():
        raise PairNotEligibleError("later narrative document is empty")

    return PairSourceSelection(
        earlier_run=earlier_run,
        later_run=later_run,
        earlier_narrative=earlier_narrative,
        later_narrative=later_narrative,
    )


def get_current_similarity_run(session: Session, report_pair_id: uuid.UUID) -> SimilarityRun | None:
    """The current successful similarity result for a pair.

    Defined as the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS. FAILED and in-progress runs are never
    eligible, so a failed rerun can never silently replace prior successful
    output -- it simply never becomes the max. This is the selection rule
    every downstream consumer (ranking, audit, CLI) must use.
    """
    return session.scalars(
        select(SimilarityRun)
        .where(
            SimilarityRun.report_pair_id == report_pair_id,
            SimilarityRun.status.in_(
                (SimilarityRunStatus.COMPLETED, SimilarityRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(SimilarityRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_similarity_runs_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SimilarityRun]:
    """Bulk version of `get_current_similarity_run` for many pairs at once."""
    if not report_pair_ids:
        return {}
    candidate_runs = session.scalars(
        select(SimilarityRun)
        .where(
            SimilarityRun.report_pair_id.in_(report_pair_ids),
            SimilarityRun.status.in_(
                (SimilarityRunStatus.COMPLETED, SimilarityRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(SimilarityRun.report_pair_id, SimilarityRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, SimilarityRun] = {}
    for run in candidate_runs:
        current.setdefault(run.report_pair_id, run)
    return current


def get_current_document_similarity(session: Session, report_pair_id: uuid.UUID) -> DocumentSimilarity | None:
    current_run = get_current_similarity_run(session, report_pair_id)
    if current_run is None:
        return None
    return session.scalar(
        select(DocumentSimilarity).where(DocumentSimilarity.similarity_run_id == current_run.id)
    )


def get_current_document_similarities_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, DocumentSimilarity]:
    """Bulk version of `get_current_document_similarity`, for audit/ranking."""
    current_runs = get_current_similarity_runs_by_pair(session, report_pair_ids)
    if not current_runs:
        return {}
    run_ids = [run.id for run in current_runs.values()]
    doc_similarities = session.scalars(
        select(DocumentSimilarity).where(DocumentSimilarity.similarity_run_id.in_(run_ids))
    ).all()
    by_run_id = {d.similarity_run_id: d for d in doc_similarities}
    return {
        pair_id: by_run_id[run.id]
        for pair_id, run in current_runs.items()
        if run.id in by_run_id
    }


def get_latest_similarity_runs_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, SimilarityRun]:
    """Bulk latest SimilarityRun per pair, regardless of status.

    Unlike `get_current_similarity_runs_by_pair`, this includes FAILED and
    in-progress runs -- used only where a caller (audit, review) needs
    visibility into a failed attempt when no successful run exists yet, not
    for selecting a scoring result.
    """
    if not report_pair_ids:
        return {}
    candidate_runs = session.scalars(
        select(SimilarityRun)
        .where(SimilarityRun.report_pair_id.in_(report_pair_ids))
        .order_by(SimilarityRun.report_pair_id, SimilarityRun.created_at.desc())
    ).all()
    latest: dict[uuid.UUID, SimilarityRun] = {}
    for run in candidate_runs:
        latest.setdefault(run.report_pair_id, run)
    return latest


@dataclass
class ScoringOutcome:
    report_pair_id: uuid.UUID
    run: SimilarityRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def score_pair(session: Session, pair: ReportPair, *, force: bool = False) -> ScoringOutcome:
    """Score one ReportPair, creating a new SimilarityRun.

    Skips (returning the existing run) if the current successful run
    already used identical source NarrativeDocuments and an identical
    configuration fingerprint, and `force` was not set. Never mutates or
    replaces a prior run's rows -- a skip returns the same run object, and
    any new attempt always creates a fresh row. Returns an ineligible
    outcome (no SimilarityRun created at all) when the pair's current
    inputs don't meet the scoring eligibility rule.
    """
    try:
        selection = select_source_narratives(session, pair)
    except PairNotEligibleError as exc:
        return ScoringOutcome(report_pair_id=pair.id, run=None, ineligible=True, ineligible_reason=str(exc))

    configuration_hash = compute_configuration_hash()

    current_run = get_current_similarity_run(session, pair.id)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.earlier_narrative_document_id == selection.earlier_narrative.id
        and current_run.later_narrative_document_id == selection.later_narrative.id
    ):
        return ScoringOutcome(
            report_pair_id=pair.id,
            run=current_run,
            skipped=True,
            skip_reason="identical successful similarity run already exists",
        )

    run = SimilarityRun(
        report_pair_id=pair.id,
        earlier_narrative_document_id=selection.earlier_narrative.id,
        later_narrative_document_id=selection.later_narrative.id,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=SimilarityRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        # A SAVEPOINT scopes the DocumentSimilarity write for this attempt:
        # on success it's released into the ongoing transaction alongside
        # the run's final status; on any exception it's rolled back to the
        # savepoint, leaving only the already-flushed FAILED SimilarityRun
        # row (set below) -- never a half-written result.
        with session.begin_nested():
            _run_scoring(session, pair, run, selection)
    except Exception as exc:  # never leave a run silently half-written
        run.status = SimilarityRunStatus.FAILED
        run.error_message = f"scoring failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("similarity scoring failed for pair %s", pair.id)

    session.flush()
    return ScoringOutcome(report_pair_id=pair.id, run=run)


def _run_scoring(
    session: Session, pair: ReportPair, run: SimilarityRun, selection: PairSourceSelection
) -> None:
    earlier_narrative = selection.earlier_narrative
    later_narrative = selection.later_narrative

    metrics = compute_metrics(earlier_narrative.cleaned_text, later_narrative.cleaned_text, SIMILARITY_CONFIG)
    length_features = compute_length_change_features(
        earlier_word_count=earlier_narrative.word_count,
        later_word_count=later_narrative.word_count,
        earlier_character_count=len(earlier_narrative.cleaned_text),
        later_character_count=len(later_narrative.cleaned_text),
    )
    assessment = assess_similarity(
        metrics=metrics,
        length_features=length_features,
        earlier_extraction_quality=selection.earlier_run.extraction_quality,
        later_extraction_quality=selection.later_run.extraction_quality,
        is_transition=pair.is_transition,
        gap_months=pair.gap_months,
        config=SIMILARITY_CONFIG,
    )

    session.add(
        DocumentSimilarity(
            similarity_run_id=run.id,
            report_pair_id=pair.id,
            earlier_report_id=pair.earlier_report_id,
            later_report_id=pair.later_report_id,
            lexical_cosine_similarity=metrics.lexical_cosine_similarity,
            jaccard_similarity=metrics.jaccard_similarity,
            diff_similarity=metrics.diff_similarity,
            diff_mode=metrics.diff_mode,
            diff_duration_ms=metrics.diff_duration_ms,
            edit_similarity=metrics.edit_similarity,
            earlier_word_count=length_features.earlier_word_count,
            later_word_count=length_features.later_word_count,
            word_count_change=length_features.word_count_change,
            word_count_change_ratio=length_features.word_count_change_ratio,
            earlier_character_count=length_features.earlier_character_count,
            later_character_count=length_features.later_character_count,
            character_count_change=length_features.character_count_change,
            character_count_change_ratio=length_features.character_count_change_ratio,
            quality_status=assessment.quality,
            review_reason=assessment.review_reason,
            primary_analysis_eligible=assessment.primary_analysis_eligible,
            primary_analysis_exclusion_reason=assessment.primary_analysis_exclusion_reason,
        )
    )

    run.completed_at = datetime.now(UTC)
    # Status reflects whether the run mechanically succeeded, not result
    # quality: a run that computed every metric is COMPLETED or
    # COMPLETED_WITH_WARNINGS even if quality_status is NEEDS_REVIEW or
    # FAILED -- that is a quality problem for a human to review, not a
    # processing failure to retry automatically.
    run.status = (
        SimilarityRunStatus.COMPLETED
        if assessment.quality == SimilarityResultQuality.GOOD
        else SimilarityRunStatus.COMPLETED_WITH_WARNINGS
    )


@dataclass
class BatchScoringOutcome:
    completed: list[uuid.UUID] = field(default_factory=list)
    completed_with_warnings: list[uuid.UUID] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)
    ineligible: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def score_eligible_pairs(
    session: Session, *, limit: int | None = None, force: bool = False
) -> BatchScoringOutcome:
    """Score every ReportPair, continuing past individual pair failures.

    "Eligible" is determined per pair inside `score_pair` (via
    `select_source_narratives`) rather than filtered here, since
    eligibility depends on each report's current extraction state, not a
    static ReportPair attribute.
    """
    outcome = BatchScoringOutcome()

    pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id, ReportPair.created_at)).all()
    if limit is not None:
        pairs = pairs[:limit]

    for pair in pairs:
        try:
            result = score_pair(session, pair, force=force)
        except Exception:
            logger.exception("unexpected orchestration error scoring pair %s", pair.id)
            outcome.failed.append((pair.id, "unexpected orchestration error"))
            continue

        if result.ineligible:
            outcome.ineligible.append((pair.id, result.ineligible_reason or "ineligible"))
            continue
        if result.skipped:
            outcome.skipped.append(pair.id)
            continue

        run = result.run
        if run is None:
            continue

        if run.status == SimilarityRunStatus.FAILED:
            outcome.failed.append((pair.id, run.error_message or "unknown error"))
            continue
        if run.status == SimilarityRunStatus.COMPLETED:
            outcome.completed.append(pair.id)
        elif run.status == SimilarityRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(pair.id)

    return outcome

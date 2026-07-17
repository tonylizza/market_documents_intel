"""Disclosure-change feature orchestration: run lifecycle, idempotency, and persistence.

Directly parallels `services/similarity.py` and `services/passage_alignment.py`:
this module owns the configuration fingerprint that drives idempotent
skipping, and the query-time rule for selecting a ReportPair's current
successful feature result. Aggregation/weighting/scoring logic is delegated
to `feature_metrics`; quality assessment to `feature_quality`; this module
only selects sources, wires them together, and persists the result.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import FeatureNotEligibleError
from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.embedding import EmbeddingRun
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, FeatureQuality, FeatureRunStatus
from market_documents.models.feature import FeatureRun, ReportPairFeatures
from market_documents.models.passage import Passage
from market_documents.models.report_pair import ReportPair
from market_documents.models.similarity import DocumentSimilarity, SimilarityRun
from market_documents.services.feature_config import (
    ALGORITHM_VERSION,
    FEATURE_CONFIG,
    FEATURE_VERSION,
    compute_configuration_hash,
)
from market_documents.services.feature_metrics import (
    AlignmentRowInput,
    aggregate_outcomes,
    compute_alignment_coverage,
    compute_document_change_transforms,
    compute_score_components,
    count_rates,
    is_heading_fragment,
    is_row_eligible,
    passage_excluded_from_features,
    row_exclusion_kind,
    row_word_weight,
    safe_ratio,
    word_rates,
)
from market_documents.services.feature_quality import QualityInputs, assess_feature_quality
from market_documents.services.passage_alignment import get_current_alignment_run
from market_documents.services.similarity import get_current_document_similarity, get_current_similarity_run

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Source selection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class FeatureSourceSelection:
    similarity_run: SimilarityRun
    document_similarity: DocumentSimilarity
    alignment_run: AlignmentRun


def select_feature_source(session: Session, pair: ReportPair) -> FeatureSourceSelection:
    """Select the current successful similarity and alignment runs for a pair.

    Raises `FeatureNotEligibleError` when features cannot currently be built:
    the pair lacks a current successful `SimilarityRun`/`DocumentSimilarity`,
    or lacks a current successful `AlignmentRun`. Never creates or infers
    either upstream result -- both must already exist.
    """
    similarity_run = get_current_similarity_run(session, pair.id)
    if similarity_run is None:
        raise FeatureNotEligibleError("pair has no current successful similarity run")
    document_similarity = get_current_document_similarity(session, pair.id)
    if document_similarity is None:
        raise FeatureNotEligibleError("pair has no current document similarity result")

    alignment_run = get_current_alignment_run(session, pair.id)
    if alignment_run is None:
        raise FeatureNotEligibleError("pair has no current successful alignment run")

    return FeatureSourceSelection(
        similarity_run=similarity_run, document_similarity=document_similarity, alignment_run=alignment_run
    )


# --------------------------------------------------------------------------
# Current-result query-time rules
# --------------------------------------------------------------------------


def get_current_feature_run(session: Session, report_pair_id: uuid.UUID) -> FeatureRun | None:
    """The current successful feature result for a pair: the most recently
    completed run with status COMPLETED or COMPLETED_WITH_WARNINGS."""
    return session.scalars(
        select(FeatureRun)
        .where(
            FeatureRun.report_pair_id == report_pair_id,
            FeatureRun.status.in_((FeatureRunStatus.COMPLETED, FeatureRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(FeatureRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_feature_runs_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FeatureRun]:
    """Bulk version of `get_current_feature_run` for many pairs at once."""
    if not report_pair_ids:
        return {}
    candidate_runs = session.scalars(
        select(FeatureRun)
        .where(
            FeatureRun.report_pair_id.in_(report_pair_ids),
            FeatureRun.status.in_((FeatureRunStatus.COMPLETED, FeatureRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(FeatureRun.report_pair_id, FeatureRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, FeatureRun] = {}
    for run in candidate_runs:
        current.setdefault(run.report_pair_id, run)
    return current


def get_latest_feature_runs_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, FeatureRun]:
    """Bulk latest FeatureRun per pair, regardless of status -- used only
    where a caller needs visibility into a failed attempt, never for
    selecting a scoring result."""
    if not report_pair_ids:
        return {}
    candidate_runs = session.scalars(
        select(FeatureRun)
        .where(FeatureRun.report_pair_id.in_(report_pair_ids))
        .order_by(FeatureRun.report_pair_id, FeatureRun.created_at.desc())
    ).all()
    latest: dict[uuid.UUID, FeatureRun] = {}
    for run in candidate_runs:
        latest.setdefault(run.report_pair_id, run)
    return latest


def get_current_report_pair_features(session: Session, report_pair_id: uuid.UUID) -> ReportPairFeatures | None:
    current_run = get_current_feature_run(session, report_pair_id)
    if current_run is None:
        return None
    return session.scalar(
        select(ReportPairFeatures).where(ReportPairFeatures.feature_run_id == current_run.id)
    )


def get_current_report_pair_features_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ReportPairFeatures]:
    """Bulk version of `get_current_report_pair_features`, for audit/export."""
    current_runs = get_current_feature_runs_by_pair(session, report_pair_ids)
    if not current_runs:
        return {}
    run_ids = [run.id for run in current_runs.values()]
    rows = session.scalars(
        select(ReportPairFeatures).where(ReportPairFeatures.feature_run_id.in_(run_ids))
    ).all()
    by_run_id = {r.feature_run_id: r for r in rows}
    return {
        pair_id: by_run_id[run.id] for pair_id, run in current_runs.items() if run.id in by_run_id
    }


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@dataclass
class BuildOutcome:
    report_pair_id: uuid.UUID
    run: FeatureRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def build_features(session: Session, pair: ReportPair, *, force: bool = False) -> BuildOutcome:
    """Build disclosure-change features for one ReportPair, creating a new FeatureRun.

    Skips (returning the existing run) if the current successful run already
    used identical source similarity/alignment runs and an identical
    configuration fingerprint, and `force` was not set. Never mutates or
    replaces a prior run's rows -- a skip returns the same run object, and
    any new attempt always creates a fresh row. Returns an ineligible
    outcome (no FeatureRun created at all) when the pair's current inputs
    don't meet the build eligibility rule.
    """
    try:
        selection = select_feature_source(session, pair)
    except FeatureNotEligibleError as exc:
        return BuildOutcome(report_pair_id=pair.id, run=None, ineligible=True, ineligible_reason=str(exc))

    configuration_hash = compute_configuration_hash()

    current_run = get_current_feature_run(session, pair.id)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.similarity_run_id == selection.similarity_run.id
        and current_run.alignment_run_id == selection.alignment_run.id
    ):
        return BuildOutcome(
            report_pair_id=pair.id,
            run=current_run,
            skipped=True,
            skip_reason="identical successful feature run already exists",
        )

    run = FeatureRun(
        report_pair_id=pair.id,
        similarity_run_id=selection.similarity_run.id,
        alignment_run_id=selection.alignment_run.id,
        algorithm_version=ALGORITHM_VERSION,
        feature_version=FEATURE_VERSION,
        configuration_hash=configuration_hash,
        status=FeatureRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        # A SAVEPOINT scopes the ReportPairFeatures write for this attempt:
        # on success it's released into the ongoing transaction alongside
        # the run's final status; on any exception it's rolled back to the
        # savepoint, leaving only the already-flushed FAILED FeatureRun row
        # (set below) -- never a half-written result.
        with session.begin_nested():
            _run_feature_build(session, pair, run, selection)
    except Exception as exc:  # never leave a run silently half-written
        run.status = FeatureRunStatus.FAILED
        run.error_message = f"feature build failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("feature build failed for pair %s", pair.id)

    session.flush()
    return BuildOutcome(report_pair_id=pair.id, run=run)


def _run_feature_build(
    session: Session, pair: ReportPair, run: FeatureRun, selection: FeatureSourceSelection
) -> None:
    alignment_run = selection.alignment_run
    doc_sim = selection.document_similarity
    config = FEATURE_CONFIG

    earlier_passages = session.scalars(
        select(Passage).where(Passage.segmentation_run_id == alignment_run.earlier_segmentation_run_id)
    ).all()
    later_passages = session.scalars(
        select(Passage).where(Passage.segmentation_run_id == alignment_run.later_segmentation_run_id)
    ).all()

    earlier_passage_count = len(earlier_passages)
    later_passage_count = len(later_passages)
    earlier_word_count = sum(p.word_count for p in earlier_passages)
    later_word_count = sum(p.word_count for p in later_passages)

    eligible_earlier_passage_count = sum(
        1 for p in earlier_passages if not passage_excluded_from_features(p.word_count, p.passage_type, config)
    )
    eligible_later_passage_count = sum(
        1 for p in later_passages if not passage_excluded_from_features(p.word_count, p.passage_type, config)
    )

    heading_fragment_earlier_count = sum(
        1 for p in earlier_passages if is_heading_fragment(p.word_count, p.passage_type, config)
    )
    heading_fragment_later_count = sum(
        1 for p in later_passages if is_heading_fragment(p.word_count, p.passage_type, config)
    )
    heading_fragment_share_earlier = safe_ratio(heading_fragment_earlier_count, earlier_passage_count)
    heading_fragment_share_later = safe_ratio(heading_fragment_later_count, later_passage_count)

    alignment_rows = session.scalars(
        select(PassageAlignment).where(
            PassageAlignment.alignment_run_id == alignment_run.id,
            PassageAlignment.primary_alignment.is_(True),
        )
    ).all()

    passage_ids = {r.earlier_passage_id for r in alignment_rows if r.earlier_passage_id} | {
        r.later_passage_id for r in alignment_rows if r.later_passage_id
    }
    passages_by_id = (
        {p.id: p for p in session.scalars(select(Passage).where(Passage.id.in_(passage_ids))).all()}
        if passage_ids
        else {}
    )

    row_inputs: list[AlignmentRowInput] = []
    confidence_counts = {c: 0 for c in AlignmentConfidence}
    for row in alignment_rows:
        earlier_p = passages_by_id.get(row.earlier_passage_id) if row.earlier_passage_id else None
        later_p = passages_by_id.get(row.later_passage_id) if row.later_passage_id else None
        row_inputs.append(
            AlignmentRowInput(
                alignment_status=row.alignment_status,
                confidence=row.confidence,
                earlier_word_count=earlier_p.word_count if earlier_p else None,
                later_word_count=later_p.word_count if later_p else None,
                earlier_passage_type=earlier_p.passage_type if earlier_p else None,
                later_passage_type=later_p.passage_type if later_p else None,
            )
        )
        confidence_counts[row.confidence] += 1

    raw = aggregate_outcomes(row_inputs, eligible_only=False, config=config)
    eligible = aggregate_outcomes(row_inputs, eligible_only=True, config=config)

    excluded_rows = [r for r in row_inputs if not is_row_eligible(r, config)]
    excluded_low_information_count = len(excluded_rows)
    excluded_low_information_words = sum(row_word_weight(r) for r in excluded_rows)
    heading_excluded_rows = [r for r in excluded_rows if row_exclusion_kind(r, config) == "heading_fragment"]
    excluded_heading_fragment_count = len(heading_excluded_rows)
    excluded_heading_fragment_words = sum(row_word_weight(r) for r in heading_excluded_rows)

    aligned_passage_count = len(row_inputs)
    eligible_aligned_passage_count = sum(eligible.counts.values())

    eligible_word_rate_map = word_rates(eligible)
    eligible_count_rate_map = count_rates(eligible)

    coverage = compute_alignment_coverage(
        row_inputs,
        earlier_total_count=earlier_passage_count,
        later_total_count=later_passage_count,
        earlier_total_words=earlier_word_count,
        later_total_words=later_word_count,
    )

    earlier_embedding_run = session.get(EmbeddingRun, alignment_run.earlier_embedding_run_id)
    later_embedding_run = session.get(EmbeddingRun, alignment_run.later_embedding_run_id)
    skipped_embedding_count_earlier = earlier_embedding_run.skipped_passage_count or 0
    skipped_embedding_count_later = later_embedding_run.skipped_passage_count or 0
    embedded_coverage_earlier = safe_ratio(
        earlier_embedding_run.embedded_passage_count or 0,
        (earlier_embedding_run.embedded_passage_count or 0) + skipped_embedding_count_earlier,
    )
    embedded_coverage_later = safe_ratio(
        later_embedding_run.embedded_passage_count or 0,
        (later_embedding_run.embedded_passage_count or 0) + skipped_embedding_count_later,
    )

    high_confidence_share = safe_ratio(confidence_counts[AlignmentConfidence.HIGH], aligned_passage_count)
    review_required_share = safe_ratio(
        confidence_counts[AlignmentConfidence.LOW] + confidence_counts[AlignmentConfidence.NEEDS_REVIEW],
        aligned_passage_count,
    )

    transforms = compute_document_change_transforms(
        cosine=doc_sim.lexical_cosine_similarity,
        bigram_jaccard=doc_sim.jaccard_similarity,
        edit_similarity=doc_sim.edit_similarity,
        diff_similarity=doc_sim.diff_similarity,
        word_change_ratio=doc_sim.word_count_change_ratio,
    )

    irregular_gap = not (config.primary_gap_months_min <= pair.gap_months <= config.primary_gap_months_max)

    score_components = compute_score_components(eligible_word_rate_map, config)
    disclosure_change_score = score_components.total
    coverage_sufficient = (
        coverage.coverage_words is not None
        and coverage.coverage_words >= config.minimum_alignment_coverage
        and embedded_coverage_earlier is not None
        and embedded_coverage_earlier >= config.minimum_embedding_coverage
        and embedded_coverage_later is not None
        and embedded_coverage_later >= config.minimum_embedding_coverage
    )
    if not coverage_sufficient:
        disclosure_change_score = None

    quality_inputs = QualityInputs(
        alignment_run_status=alignment_run.status,
        alignment_review_reason=alignment_run.review_reason,
        document_quality=doc_sim.quality_status,
        is_transition=pair.is_transition,
        irregular_gap=irregular_gap,
        alignment_coverage_count=coverage.coverage_count,
        alignment_coverage_words=coverage.coverage_words,
        embedded_coverage_earlier=embedded_coverage_earlier,
        embedded_coverage_later=embedded_coverage_later,
        ambiguous_word_share=eligible_word_rate_map.get(AlignmentStatus.AMBIGUOUS),
        low_confidence_share=review_required_share,
        disclosure_change_score=disclosure_change_score,
    )
    assessment = assess_feature_quality(quality_inputs, config)

    session.add(
        ReportPairFeatures(
            feature_run_id=run.id,
            report_pair_id=pair.id,
            earlier_report_id=pair.earlier_report_id,
            later_report_id=pair.later_report_id,
            document_cosine_similarity=doc_sim.lexical_cosine_similarity,
            document_bigram_jaccard=doc_sim.jaccard_similarity,
            document_edit_similarity=doc_sim.edit_similarity,
            document_diff_similarity=doc_sim.diff_similarity,
            document_word_change_ratio=doc_sim.word_count_change_ratio,
            document_metric_disagreement_spread=transforms.metric_disagreement_spread,
            document_quality=doc_sim.quality_status,
            document_primary_eligible=doc_sim.primary_analysis_eligible,
            document_cosine_change=transforms.cosine_change,
            document_bigram_jaccard_change=transforms.bigram_jaccard_change,
            document_edit_similarity_change=transforms.edit_similarity_change,
            document_diff_similarity_change=transforms.diff_similarity_change,
            document_word_change_ratio_abs=transforms.word_change_ratio_abs,
            earlier_passage_count=earlier_passage_count,
            later_passage_count=later_passage_count,
            aligned_passage_count=aligned_passage_count,
            unchanged_count=raw.counts[AlignmentStatus.UNCHANGED],
            lightly_modified_count=raw.counts[AlignmentStatus.LIGHTLY_MODIFIED],
            substantially_modified_count=raw.counts[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            new_count=raw.counts[AlignmentStatus.NEW],
            removed_count=raw.counts[AlignmentStatus.REMOVED],
            ambiguous_count=raw.counts[AlignmentStatus.AMBIGUOUS],
            high_confidence_count=confidence_counts[AlignmentConfidence.HIGH],
            medium_confidence_count=confidence_counts[AlignmentConfidence.MEDIUM],
            low_confidence_count=confidence_counts[AlignmentConfidence.LOW],
            needs_review_confidence_count=confidence_counts[AlignmentConfidence.NEEDS_REVIEW],
            skipped_embedding_count_earlier=skipped_embedding_count_earlier,
            skipped_embedding_count_later=skipped_embedding_count_later,
            earlier_word_count=earlier_word_count,
            later_word_count=later_word_count,
            unchanged_words=raw.words[AlignmentStatus.UNCHANGED],
            lightly_modified_words=raw.words[AlignmentStatus.LIGHTLY_MODIFIED],
            substantially_modified_words=raw.words[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            new_words=raw.words[AlignmentStatus.NEW],
            removed_words=raw.words[AlignmentStatus.REMOVED],
            ambiguous_words=raw.words[AlignmentStatus.AMBIGUOUS],
            eligible_earlier_passage_count=eligible_earlier_passage_count,
            eligible_later_passage_count=eligible_later_passage_count,
            eligible_aligned_passage_count=eligible_aligned_passage_count,
            eligible_unchanged_count=eligible.counts[AlignmentStatus.UNCHANGED],
            eligible_lightly_modified_count=eligible.counts[AlignmentStatus.LIGHTLY_MODIFIED],
            eligible_substantially_modified_count=eligible.counts[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            eligible_new_count=eligible.counts[AlignmentStatus.NEW],
            eligible_removed_count=eligible.counts[AlignmentStatus.REMOVED],
            eligible_ambiguous_count=eligible.counts[AlignmentStatus.AMBIGUOUS],
            eligible_unchanged_words=eligible.words[AlignmentStatus.UNCHANGED],
            eligible_lightly_modified_words=eligible.words[AlignmentStatus.LIGHTLY_MODIFIED],
            eligible_substantially_modified_words=eligible.words[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            eligible_new_words=eligible.words[AlignmentStatus.NEW],
            eligible_removed_words=eligible.words[AlignmentStatus.REMOVED],
            eligible_ambiguous_words=eligible.words[AlignmentStatus.AMBIGUOUS],
            excluded_low_information_count=excluded_low_information_count,
            excluded_low_information_words=excluded_low_information_words,
            excluded_heading_fragment_count=excluded_heading_fragment_count,
            excluded_heading_fragment_words=excluded_heading_fragment_words,
            heading_fragment_share_earlier=heading_fragment_share_earlier,
            heading_fragment_share_later=heading_fragment_share_later,
            unchanged_rate_count=eligible_count_rate_map[AlignmentStatus.UNCHANGED],
            lightly_modified_rate_count=eligible_count_rate_map[AlignmentStatus.LIGHTLY_MODIFIED],
            substantially_modified_rate_count=eligible_count_rate_map[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            new_rate_count=eligible_count_rate_map[AlignmentStatus.NEW],
            removed_rate_count=eligible_count_rate_map[AlignmentStatus.REMOVED],
            ambiguous_rate_count=eligible_count_rate_map[AlignmentStatus.AMBIGUOUS],
            unchanged_rate_words=eligible_word_rate_map[AlignmentStatus.UNCHANGED],
            lightly_modified_rate_words=eligible_word_rate_map[AlignmentStatus.LIGHTLY_MODIFIED],
            substantially_modified_rate_words=eligible_word_rate_map[AlignmentStatus.SUBSTANTIALLY_MODIFIED],
            new_rate_words=eligible_word_rate_map[AlignmentStatus.NEW],
            removed_rate_words=eligible_word_rate_map[AlignmentStatus.REMOVED],
            ambiguous_rate_words=eligible_word_rate_map[AlignmentStatus.AMBIGUOUS],
            alignment_coverage_count=coverage.coverage_count,
            alignment_coverage_words=coverage.coverage_words,
            embedded_coverage_earlier=embedded_coverage_earlier,
            embedded_coverage_later=embedded_coverage_later,
            high_confidence_share=high_confidence_share,
            review_required_share=review_required_share,
            irregular_gap=irregular_gap,
            reporting_gap_months=pair.gap_months,
            transition_report=pair.is_transition,
            feature_quality=assessment.quality,
            primary_eligible=assessment.primary_eligible,
            exclusion_reasons=assessment.exclusion_reasons,
            warning_reasons=assessment.warning_reasons,
            disclosure_change_score=disclosure_change_score,
            score_version=FEATURE_VERSION,
            score_unchanged_component=score_components.unchanged,
            score_lightly_modified_component=score_components.lightly_modified,
            score_substantially_modified_component=score_components.substantially_modified,
            score_new_component=score_components.new,
            score_removed_component=score_components.removed,
            score_ambiguous_component=score_components.ambiguous,
        )
    )

    run.completed_at = datetime.now(UTC)
    run.review_reason = assessment.warning_reasons
    # Status reflects whether the run mechanically succeeded, not result
    # quality: a run that computed every feature is COMPLETED or
    # COMPLETED_WITH_WARNINGS even if feature_quality is NEEDS_REVIEW or
    # FAILED -- that is a quality problem for a human to review, not a
    # processing failure to retry automatically.
    run.status = (
        FeatureRunStatus.COMPLETED
        if assessment.quality == FeatureQuality.GOOD
        else FeatureRunStatus.COMPLETED_WITH_WARNINGS
    )


@dataclass
class BatchBuildOutcome:
    completed: list[uuid.UUID] = field(default_factory=list)
    completed_with_warnings: list[uuid.UUID] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)
    ineligible: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def build_eligible_features(
    session: Session, *, limit: int | None = None, force: bool = False
) -> BatchBuildOutcome:
    """Build features for every ReportPair currently eligible, continuing
    past individual pair failures.

    "Eligible" is determined per pair inside `build_features` (via
    `select_feature_source`) rather than filtered here, since eligibility
    depends on each pair's current similarity/alignment state, not a static
    ReportPair attribute.
    """
    outcome = BatchBuildOutcome()

    pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id, ReportPair.created_at)).all()
    if limit is not None:
        pairs = pairs[:limit]

    for pair in pairs:
        try:
            result = build_features(session, pair, force=force)
        except Exception:
            logger.exception("unexpected orchestration error building features for pair %s", pair.id)
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

        if run.status == FeatureRunStatus.FAILED:
            outcome.failed.append((pair.id, run.error_message or "unknown error"))
            continue
        if run.status == FeatureRunStatus.COMPLETED:
            outcome.completed.append(pair.id)
        elif run.status == FeatureRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(pair.id)

    return outcome

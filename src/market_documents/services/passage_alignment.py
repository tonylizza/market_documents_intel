"""Passage alignment: lexical rescoring, combined scoring, greedy conflict
resolution, split/merge detection, and run orchestration.

Mirrors `services/similarity.py`: this module owns the configuration
fingerprint that drives idempotent skipping, and the query-time rule for
selecting a ReportPair's current successful alignment. Semantic candidates
come from `alignment_candidates.py`; change classification and confidence
come from `alignment_quality.py`; this module combines them, resolves
conflicts, and persists the result.

Conflict resolution is greedy (highest combined score first, across all
later passages at once), not Hungarian/optimal assignment: at this corpus's
scale (a few hundred passages per side), correctness and interpretability
matter more than asymptotic optimality, and greedy assignment is far easier
to audit ("this passage won because it had the single highest combined
score among unclaimed candidates").
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import AlignmentNotEligibleError
from market_documents.models.embedding import EmbeddingRun, PassageEmbedding
from market_documents.models.enums import AlignmentRunStatus, AlignmentStatus, AlignmentType, ExtractionQuality
from market_documents.models.passage import Passage, PassageSegmentationRun
from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.report_pair import ReportPair
from market_documents.services.alignment_candidates import CandidateMatch, get_semantic_candidates
from market_documents.services.alignment_config import ALGORITHM_VERSION, ALIGNMENT_CONFIG, AlignmentConfig, compute_configuration_hash
from market_documents.services.alignment_quality import assess_confidence, classify_alignment, detect_disagreement
from market_documents.services.extraction import get_current_extraction_run, get_narrative_document
from market_documents.services.passage_embedding import get_current_embedding_run
from market_documents.services.passage_segmentation import get_current_segmentation_run
from market_documents.services.similarity_metrics import edit_similarity, jaccard_similarity, lexical_cosine_similarity
from market_documents.services.similarity_tokenization import tokenize

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Lexical/structural scoring (pure, reuses M3 metrics)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LexicalFeatures:
    lexical_cosine_similarity: float | None
    jaccard_similarity: float | None
    edit_similarity: float | None
    heading_similarity: float | None
    length_ratio: float | None


def compute_lexical_features(earlier: Passage, later: Passage) -> LexicalFeatures:
    """Pair-local lexical/structural features for one candidate correspondence.

    Reuses M3's `lexical_cosine_similarity`/`jaccard_similarity`/
    `edit_similarity` unmodified. Deliberately excludes M3's
    `diff_similarity` (SequenceMatcher): at passage scale, with hundreds of
    candidate-pair evaluations per report pair, SequenceMatcher's
    contiguous-block-matching behavior (valuable for detecting a *relocated*
    block across a whole document) adds negligible signal beyond
    cosine+Jaccard+edit while being the most expensive of the four M3
    metrics -- not a good value trade at this scale.

    `length_ratio` is shorter/longer word count, bounded (0, 1] with 1.0
    meaning equal length -- a deliberately different (simpler, bounded)
    representation than M3's signed `word_count_change_ratio`.
    """
    tokens_a = tokenize(earlier.raw_text)
    tokens_b = tokenize(later.raw_text)

    heading_similarity = None
    if earlier.heading_text and later.heading_text:
        heading_similarity = lexical_cosine_similarity(tokenize(earlier.heading_text), tokenize(later.heading_text))

    shorter = min(earlier.word_count, later.word_count)
    longer = max(earlier.word_count, later.word_count)
    length_ratio = shorter / longer if longer else None

    return LexicalFeatures(
        lexical_cosine_similarity=lexical_cosine_similarity(tokens_a, tokens_b),
        jaccard_similarity=jaccard_similarity(tokens_a, tokens_b),
        edit_similarity=edit_similarity(tokens_a, tokens_b),
        heading_similarity=heading_similarity,
        length_ratio=length_ratio,
    )


def lexical_composite(features: LexicalFeatures) -> float | None:
    """Mean of the non-None lexical metrics -- kept separate from the
    combined score so semantic and lexical evidence remain independently
    inspectable."""
    values = [
        v
        for v in (features.lexical_cosine_similarity, features.jaccard_similarity, features.edit_similarity)
        if v is not None
    ]
    return sum(values) / len(values) if values else None


def compute_position_difference(earlier_index: int, earlier_total: int, later_index: int, later_total: int) -> float:
    """Normalized report-position difference in [0, 1]; 0 = same relative position."""
    earlier_pos = earlier_index / (earlier_total - 1) if earlier_total > 1 else 0.0
    later_pos = later_index / (later_total - 1) if later_total > 1 else 0.0
    return abs(earlier_pos - later_pos)


def compute_combined_score(
    *,
    semantic_similarity: float,
    lexical_composite: float | None,
    heading_similarity: float | None,
    position_difference: float,
    config: AlignmentConfig = ALIGNMENT_CONFIG,
) -> float:
    """Documented fixed-weight combination -- every component remains
    separately stored on `PassageAlignment`, never hidden behind this score."""
    lexical_component = lexical_composite if lexical_composite is not None else 0.0
    heading_component = heading_similarity if heading_similarity is not None else 0.0
    position_component = 1.0 - position_difference
    return (
        config.weight_semantic * semantic_similarity
        + config.weight_lexical * lexical_component
        + config.weight_heading * heading_component
        + config.weight_position * position_component
    )


@dataclass(frozen=True)
class ScoredCandidate:
    earlier_passage: Passage
    semantic_similarity: float
    lexical_features: LexicalFeatures
    position_difference: float
    combined_score: float


def score_candidates(
    later_passage: Passage,
    candidates: list[CandidateMatch],
    *,
    earlier_total: int,
    later_total: int,
    config: AlignmentConfig = ALIGNMENT_CONFIG,
) -> list[ScoredCandidate]:
    """Score and deterministically sort one later passage's semantic candidates."""
    scored: list[ScoredCandidate] = []
    for candidate in candidates:
        features = compute_lexical_features(candidate.passage, later_passage)
        composite = lexical_composite(features)
        position_difference = compute_position_difference(
            candidate.passage.passage_index, earlier_total, later_passage.passage_index, later_total
        )
        combined_score = compute_combined_score(
            semantic_similarity=candidate.semantic_similarity,
            lexical_composite=composite,
            heading_similarity=features.heading_similarity,
            position_difference=position_difference,
            config=config,
        )
        scored.append(
            ScoredCandidate(
                earlier_passage=candidate.passage,
                semantic_similarity=candidate.semantic_similarity,
                lexical_features=features,
                position_difference=position_difference,
                combined_score=combined_score,
            )
        )
    scored.sort(key=lambda s: (-s.combined_score, s.earlier_passage.passage_index))
    return scored


# --------------------------------------------------------------------------
# Split/merge detection (v1: detect + flag AMBIGUOUS only, see alignment_config.py)
# --------------------------------------------------------------------------


def detect_split_merge(
    *,
    accepted: dict[uuid.UUID, ScoredCandidate],
    candidates_by_later_id: dict[uuid.UUID, list[ScoredCandidate]],
    unmatched_later: list[Passage],
    unmatched_earlier: list[Passage],
    later_by_id: dict[uuid.UUID, Passage],
    config: AlignmentConfig = ALIGNMENT_CONFIG,
) -> tuple[dict[uuid.UUID, str], dict[uuid.UUID, str]]:
    """Flag likely split/merge cases rather than silently calling them NEW/REMOVED.

    Split: an unmatched later passage adjacent (by passage_index) to an
    accepted later passage also proposes that same accepted later passage's
    earlier match, above `split_merge_candidate_min_score` -- suggesting one
    earlier passage's content was split across two later passages.

    Merge: an unmatched earlier passage adjacent to an accepted match's
    earlier passage also appears (above the threshold) in that same later
    passage's own candidate list -- suggesting two earlier passages were
    merged into one later passage.

    This only ever *upgrades* a NEW/REMOVED classification to AMBIGUOUS; it
    never removes or overrides an accepted one-to-one match. Constrained
    one-to-two/two-to-one acceptance is deferred (see module docstring in
    alignment_config.py) -- this is deliberately detection-only.
    """
    split_flags: dict[uuid.UUID, str] = {}
    merge_flags: dict[uuid.UUID, str] = {}

    accepted_later_by_index = {later_by_id[later_id].passage_index: later_id for later_id in accepted}

    for later_passage in unmatched_later:
        for neighbor_index in (later_passage.passage_index - 1, later_passage.passage_index + 1):
            neighbor_later_id = accepted_later_by_index.get(neighbor_index)
            if neighbor_later_id is None:
                continue
            neighbor_earlier_id = accepted[neighbor_later_id].earlier_passage.id
            for candidate in candidates_by_later_id.get(later_passage.id, []):
                if (
                    candidate.earlier_passage.id == neighbor_earlier_id
                    and candidate.combined_score >= config.split_merge_candidate_min_score
                ):
                    split_flags[later_passage.id] = (
                        "likely split: also matches the earlier passage shared with adjacent "
                        f"later passage_index {neighbor_index}"
                    )
                    break
            if later_passage.id in split_flags:
                break

    unmatched_earlier_by_index = {p.passage_index: p.id for p in unmatched_earlier}
    for later_id, candidate in accepted.items():
        accepted_earlier_index = candidate.earlier_passage.passage_index
        for neighbor_index in (accepted_earlier_index - 1, accepted_earlier_index + 1):
            neighbor_earlier_id = unmatched_earlier_by_index.get(neighbor_index)
            if neighbor_earlier_id is None:
                continue
            for scored in candidates_by_later_id.get(later_id, []):
                if (
                    scored.earlier_passage.id == neighbor_earlier_id
                    and scored.combined_score >= config.split_merge_candidate_min_score
                ):
                    merge_flags[neighbor_earlier_id] = (
                        "likely merge: also proposed as a match for the later passage already matched "
                        f"to adjacent earlier passage_index {accepted_earlier_index}"
                    )
                    break

    return split_flags, merge_flags


# --------------------------------------------------------------------------
# Source selection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AlignmentSourceSelection:
    earlier_segmentation_run: PassageSegmentationRun
    later_segmentation_run: PassageSegmentationRun
    earlier_embedding_run: EmbeddingRun
    later_embedding_run: EmbeddingRun
    earlier_passages: list[Passage]
    later_passages: list[Passage]
    later_embeddings_by_passage_id: dict[uuid.UUID, list[float]]


def select_alignment_source(session: Session, pair: ReportPair) -> AlignmentSourceSelection:
    """Select the current successful segmentation/embedding runs for both
    sides of a pair.

    Raises `AlignmentNotEligibleError` when the pair cannot currently be
    aligned: either side lacks a current successful segmentation or
    embedding run, the two embedding runs use incompatible model
    configurations, or either side has no eligible passages. Never creates
    a ReportPair or infers dates -- the pair must already exist.
    """
    earlier_narrative = get_narrative_document(session, pair.earlier_report_id)
    if earlier_narrative is None:
        raise AlignmentNotEligibleError("earlier report has no current narrative document")
    later_narrative = get_narrative_document(session, pair.later_report_id)
    if later_narrative is None:
        raise AlignmentNotEligibleError("later report has no current narrative document")

    earlier_segmentation_run = get_current_segmentation_run(session, earlier_narrative.id)
    if earlier_segmentation_run is None:
        raise AlignmentNotEligibleError("earlier report has no current successful segmentation run")
    later_segmentation_run = get_current_segmentation_run(session, later_narrative.id)
    if later_segmentation_run is None:
        raise AlignmentNotEligibleError("later report has no current successful segmentation run")

    earlier_embedding_run = get_current_embedding_run(session, earlier_segmentation_run.id)
    if earlier_embedding_run is None:
        raise AlignmentNotEligibleError("earlier report has no current successful embedding run")
    later_embedding_run = get_current_embedding_run(session, later_segmentation_run.id)
    if later_embedding_run is None:
        raise AlignmentNotEligibleError("later report has no current successful embedding run")

    if (
        earlier_embedding_run.model_name,
        earlier_embedding_run.model_revision,
        earlier_embedding_run.embedding_dimension,
    ) != (
        later_embedding_run.model_name,
        later_embedding_run.model_revision,
        later_embedding_run.embedding_dimension,
    ):
        raise AlignmentNotEligibleError("earlier and later embedding runs use incompatible model configurations")

    earlier_passages = session.scalars(
        select(Passage)
        .where(Passage.segmentation_run_id == earlier_segmentation_run.id, Passage.excluded_from_alignment.is_(False))
        .order_by(Passage.passage_index)
    ).all()
    later_passages = session.scalars(
        select(Passage)
        .where(Passage.segmentation_run_id == later_segmentation_run.id, Passage.excluded_from_alignment.is_(False))
        .order_by(Passage.passage_index)
    ).all()
    if not earlier_passages:
        raise AlignmentNotEligibleError("earlier report has no eligible (non-excluded) passages")
    if not later_passages:
        raise AlignmentNotEligibleError("later report has no eligible (non-excluded) passages")

    later_passage_ids = [p.id for p in later_passages]
    later_embeddings = session.scalars(
        select(PassageEmbedding).where(
            PassageEmbedding.embedding_run_id == later_embedding_run.id,
            PassageEmbedding.passage_id.in_(later_passage_ids),
        )
    ).all()

    return AlignmentSourceSelection(
        earlier_segmentation_run=earlier_segmentation_run,
        later_segmentation_run=later_segmentation_run,
        earlier_embedding_run=earlier_embedding_run,
        later_embedding_run=later_embedding_run,
        earlier_passages=list(earlier_passages),
        later_passages=list(later_passages),
        later_embeddings_by_passage_id={e.passage_id: e.embedding for e in later_embeddings},
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_alignment_run(session: Session, report_pair_id: uuid.UUID) -> AlignmentRun | None:
    return session.scalars(
        select(AlignmentRun)
        .where(
            AlignmentRun.report_pair_id == report_pair_id,
            AlignmentRun.status.in_((AlignmentRunStatus.COMPLETED, AlignmentRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(AlignmentRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_alignment_runs_by_pair(session: Session, report_pair_ids: list[uuid.UUID]) -> dict[uuid.UUID, AlignmentRun]:
    if not report_pair_ids:
        return {}
    candidate_runs = session.scalars(
        select(AlignmentRun)
        .where(
            AlignmentRun.report_pair_id.in_(report_pair_ids),
            AlignmentRun.status.in_((AlignmentRunStatus.COMPLETED, AlignmentRunStatus.COMPLETED_WITH_WARNINGS)),
        )
        .order_by(AlignmentRun.report_pair_id, AlignmentRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, AlignmentRun] = {}
    for run in candidate_runs:
        current.setdefault(run.report_pair_id, run)
    return current


@dataclass
class AlignmentOutcome:
    report_pair_id: uuid.UUID
    run: AlignmentRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def align_pair(session: Session, pair: ReportPair, *, force: bool = False) -> AlignmentOutcome:
    """Align one ReportPair, creating a new AlignmentRun.

    Skips (returning the existing run) if the current successful run
    already used identical source segmentation/embedding runs and an
    identical configuration fingerprint, and `force` was not set. Never
    requires GOOD document-level similarity quality -- irregular-gap pairs
    and NEEDS_REVIEW similarity results are aligned where source passages
    are available, with irregular-gap/transition context surfaced via
    `review_reason` rather than used to reject the pair.
    """
    try:
        selection = select_alignment_source(session, pair)
    except AlignmentNotEligibleError as exc:
        return AlignmentOutcome(report_pair_id=pair.id, run=None, ineligible=True, ineligible_reason=str(exc))

    configuration_hash = compute_configuration_hash()
    current_run = get_current_alignment_run(session, pair.id)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.earlier_segmentation_run_id == selection.earlier_segmentation_run.id
        and current_run.later_segmentation_run_id == selection.later_segmentation_run.id
        and current_run.earlier_embedding_run_id == selection.earlier_embedding_run.id
        and current_run.later_embedding_run_id == selection.later_embedding_run.id
    ):
        return AlignmentOutcome(
            report_pair_id=pair.id, run=current_run, skipped=True,
            skip_reason="identical successful alignment run already exists",
        )

    run = AlignmentRun(
        report_pair_id=pair.id,
        earlier_segmentation_run_id=selection.earlier_segmentation_run.id,
        later_segmentation_run_id=selection.later_segmentation_run.id,
        earlier_embedding_run_id=selection.earlier_embedding_run.id,
        later_embedding_run_id=selection.later_embedding_run.id,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=AlignmentRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_alignment(session, pair, run, selection)
    except Exception as exc:  # never leave a run silently half-written
        run.status = AlignmentRunStatus.FAILED
        run.error_message = f"alignment failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("passage alignment failed for pair %s", pair.id)

    session.flush()
    return AlignmentOutcome(report_pair_id=pair.id, run=run)


def _run_alignment(
    session: Session, pair: ReportPair, run: AlignmentRun, selection: AlignmentSourceSelection
) -> None:
    earlier_extraction_run = get_current_extraction_run(session, pair.earlier_report_id)
    later_extraction_run = get_current_extraction_run(session, pair.later_report_id)
    earlier_quality = earlier_extraction_run.extraction_quality if earlier_extraction_run else None
    later_quality = later_extraction_run.extraction_quality if later_extraction_run else None

    earlier_total = len(selection.earlier_passages)
    later_total = len(selection.later_passages)
    later_by_id = {p.id: p for p in selection.later_passages}

    candidates_by_later_id: dict[uuid.UUID, list[ScoredCandidate]] = {}
    for later_passage in selection.later_passages:
        vector = selection.later_embeddings_by_passage_id.get(later_passage.id)
        if vector is None:
            candidates_by_later_id[later_passage.id] = []
            continue
        raw_candidates = get_semantic_candidates(
            session,
            later_embedding_vector=vector,
            earlier_embedding_run_id=selection.earlier_embedding_run.id,
            top_k=ALIGNMENT_CONFIG.top_k,
            min_semantic_similarity=ALIGNMENT_CONFIG.min_semantic_similarity,
        )
        candidates_by_later_id[later_passage.id] = score_candidates(
            later_passage, raw_candidates, earlier_total=earlier_total, later_total=later_total
        )

    proposals: list[tuple[Passage, ScoredCandidate]] = [
        (later_passage, candidate)
        for later_passage in selection.later_passages
        for candidate in candidates_by_later_id[later_passage.id]
        if candidate.combined_score >= ALIGNMENT_CONFIG.min_combined_score_for_acceptance
    ]
    proposals.sort(key=lambda item: (-item[1].combined_score, item[0].passage_index, item[1].earlier_passage.passage_index))

    claimed_later: set[uuid.UUID] = set()
    claimed_earlier: set[uuid.UUID] = set()
    accepted: dict[uuid.UUID, ScoredCandidate] = {}
    for later_passage, candidate in proposals:
        if later_passage.id in claimed_later or candidate.earlier_passage.id in claimed_earlier:
            continue
        claimed_later.add(later_passage.id)
        claimed_earlier.add(candidate.earlier_passage.id)
        accepted[later_passage.id] = candidate

    unmatched_later = [p for p in selection.later_passages if p.id not in claimed_later]
    unmatched_earlier = [p for p in selection.earlier_passages if p.id not in claimed_earlier]

    split_flags, merge_flags = detect_split_merge(
        accepted=accepted,
        candidates_by_later_id=candidates_by_later_id,
        unmatched_later=unmatched_later,
        unmatched_earlier=unmatched_earlier,
        later_by_id=later_by_id,
    )

    counts: dict[str, int] = {}

    def _record(status: AlignmentStatus) -> None:
        key = status.value.lower()
        counts[key] = counts.get(key, 0) + 1

    for later_id, candidate in accepted.items():
        later_passage = later_by_id[later_id]
        own_candidates = candidates_by_later_id[later_id]
        accepted_idx = next(i for i, c in enumerate(own_candidates) if c.earlier_passage.id == candidate.earlier_passage.id)
        best_second_margin = (
            candidate.combined_score - own_candidates[accepted_idx + 1].combined_score
            if accepted_idx + 1 < len(own_candidates)
            else None
        )

        composite = lexical_composite(candidate.lexical_features)
        status = classify_alignment(
            semantic_similarity=candidate.semantic_similarity,
            lexical_composite=composite,
            length_ratio=candidate.lexical_features.length_ratio,
        )
        disagreement = detect_disagreement(semantic_similarity=candidate.semantic_similarity, lexical_composite=composite)
        confidence_assessment = assess_confidence(
            best_second_margin=best_second_margin,
            disagreement=disagreement,
            split_merge_flag=None,
            earlier_extraction_quality=earlier_quality,
            later_extraction_quality=later_quality,
            is_transition=pair.is_transition,
            gap_months=pair.gap_months,
        )

        session.add(
            PassageAlignment(
                alignment_run_id=run.id,
                report_pair_id=pair.id,
                earlier_passage_id=candidate.earlier_passage.id,
                later_passage_id=later_id,
                alignment_status=status,
                alignment_type=AlignmentType.ONE_TO_ONE,
                semantic_similarity=candidate.semantic_similarity,
                lexical_cosine_similarity=candidate.lexical_features.lexical_cosine_similarity,
                jaccard_similarity=candidate.lexical_features.jaccard_similarity,
                edit_similarity=candidate.lexical_features.edit_similarity,
                heading_similarity=candidate.lexical_features.heading_similarity,
                length_ratio=candidate.lexical_features.length_ratio,
                position_difference=candidate.position_difference,
                combined_score=candidate.combined_score,
                candidate_rank=accepted_idx + 1,
                confidence=confidence_assessment.confidence,
                best_second_margin=best_second_margin,
                review_reason=confidence_assessment.review_reason,
                primary_alignment=True,
            )
        )
        _record(status)

    for later_passage in unmatched_later:
        split_note = split_flags.get(later_passage.id)
        status = AlignmentStatus.AMBIGUOUS if split_note else AlignmentStatus.NEW
        confidence_assessment = assess_confidence(
            best_second_margin=None,
            disagreement=None,
            split_merge_flag=split_note,
            earlier_extraction_quality=earlier_quality,
            later_extraction_quality=later_quality,
            is_transition=pair.is_transition,
            gap_months=pair.gap_months,
        )
        session.add(
            PassageAlignment(
                alignment_run_id=run.id,
                report_pair_id=pair.id,
                earlier_passage_id=None,
                later_passage_id=later_passage.id,
                alignment_status=status,
                alignment_type=AlignmentType.UNMATCHED_LATER,
                confidence=confidence_assessment.confidence,
                review_reason=confidence_assessment.review_reason,
                primary_alignment=True,
            )
        )
        _record(status)

    for earlier_passage in unmatched_earlier:
        merge_note = merge_flags.get(earlier_passage.id)
        status = AlignmentStatus.AMBIGUOUS if merge_note else AlignmentStatus.REMOVED
        confidence_assessment = assess_confidence(
            best_second_margin=None,
            disagreement=None,
            split_merge_flag=merge_note,
            earlier_extraction_quality=earlier_quality,
            later_extraction_quality=later_quality,
            is_transition=pair.is_transition,
            gap_months=pair.gap_months,
        )
        session.add(
            PassageAlignment(
                alignment_run_id=run.id,
                report_pair_id=pair.id,
                earlier_passage_id=earlier_passage.id,
                later_passage_id=None,
                alignment_status=status,
                alignment_type=AlignmentType.UNMATCHED_EARLIER,
                confidence=confidence_assessment.confidence,
                review_reason=confidence_assessment.review_reason,
                primary_alignment=True,
            )
        )
        _record(status)

    run.matched_count = len(accepted)
    run.unchanged_count = counts.get("unchanged", 0)
    run.lightly_modified_count = counts.get("lightly_modified", 0)
    run.substantially_modified_count = counts.get("substantially_modified", 0)
    run.new_count = counts.get("new", 0)
    run.removed_count = counts.get("removed", 0)
    run.ambiguous_count = counts.get("ambiguous", 0)
    run.completed_at = datetime.now(UTC)

    warnings: list[str] = []
    if earlier_quality == ExtractionQuality.NEEDS_REVIEW or later_quality == ExtractionQuality.NEEDS_REVIEW:
        warnings.append("source extraction quality NEEDS_REVIEW on at least one side")
    if pair.is_transition:
        warnings.append("transition-period pair")
    if pair.gap_months > ALIGNMENT_CONFIG.irregular_gap_months_threshold:
        warnings.append(f"irregular reporting gap ({pair.gap_months} months)")
    if run.ambiguous_count:
        warnings.append(f"{run.ambiguous_count} ambiguous alignment(s)")

    run.review_reason = "; ".join(warnings) if warnings else None
    run.status = AlignmentRunStatus.COMPLETED if not warnings else AlignmentRunStatus.COMPLETED_WITH_WARNINGS


@dataclass
class BatchAlignmentOutcome:
    completed: list[uuid.UUID] = field(default_factory=list)
    completed_with_warnings: list[uuid.UUID] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)
    ineligible: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def align_eligible_pairs(session: Session, *, limit: int | None = None, force: bool = False) -> BatchAlignmentOutcome:
    """Align every ReportPair, continuing past individual pair failures.

    Includes irregular-gap and transition pairs -- eligibility depends only
    on segmentation/embedding availability, decided per pair inside
    `align_pair`, never on document-level similarity quality.
    """
    outcome = BatchAlignmentOutcome()

    pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id, ReportPair.created_at)).all()
    if limit is not None:
        pairs = pairs[:limit]

    for pair in pairs:
        try:
            result = align_pair(session, pair, force=force)
        except Exception:
            logger.exception("unexpected orchestration error aligning pair %s", pair.id)
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

        if run.status == AlignmentRunStatus.FAILED:
            outcome.failed.append((pair.id, run.error_message or "unknown error"))
        elif run.status == AlignmentRunStatus.COMPLETED:
            outcome.completed.append(pair.id)
        elif run.status == AlignmentRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(pair.id)

    return outcome

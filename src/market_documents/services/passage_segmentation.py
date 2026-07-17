"""Passage segmentation: deterministic structural algorithm, provenance
diagnostics, and run orchestration.

Mirrors `services/extraction.py`: this module owns the configuration
fingerprint that drives idempotent skipping, and the query-time rule for
selecting a NarrativeDocument's current successful segmentation. The pure
algorithm (`segment_blocks`) and the provenance diagnostics
(`check_provenance`) take no database session and are independently unit
testable; only the orchestration functions at the bottom touch the ORM.
"""

import hashlib
import logging
import unicodedata
import uuid
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import MarketDocumentsError
from market_documents.models.enums import BlockType, ExtractionQuality, PassageSegmentationRunStatus, PassageType
from market_documents.models.extraction import ExtractionRun, NarrativeDocument, Page, TextBlock
from market_documents.models.passage import Passage, PassageSegmentationRun, PassageSourceBlock
from market_documents.models.report import Report
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.passage_config import (
    ALGORITHM_VERSION,
    PASSAGE_CONFIG,
    PassageConfig,
    compute_configuration_hash,
)
from market_documents.services.similarity_tokenization import tokenize

logger = logging.getLogger(__name__)


class SegmentationProvenanceError(MarketDocumentsError):
    """A segmentation run's output cannot be reconciled with its source blocks."""


# --------------------------------------------------------------------------
# Pure data structures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class SegmentableBlock:
    """A minimal, ORM-free view of one TextBlock, for the pure algorithm."""

    id: uuid.UUID
    page_number: int
    reading_order: int
    block_type: BlockType
    text: str
    excluded_from_narrative: bool
    exclusion_reason: str | None


@dataclass(frozen=True)
class SegmentedPassage:
    passage_index: int
    raw_text: str
    normalized_text: str
    content_hash: str
    first_page_number: int
    last_page_number: int
    word_count: int
    token_count: int
    character_count: int
    heading_text: str | None
    passage_type: PassageType
    excluded_from_alignment: bool
    exclusion_reason: str | None
    source_block_ids: tuple[uuid.UUID, ...]


def _normalize(text: str) -> str:
    """Same NFKC + lowercase normalization as the M3 tokenizer, without the
    final token-extraction step -- used for passage content hashing/dedup,
    not for token counting."""
    return unicodedata.normalize("NFKC", text).lower()


def _digit_ratio(text: str) -> float:
    return sum(ch.isdigit() for ch in text) / len(text) if text else 0.0


def _find_table_adjacent_ids(all_blocks: list[SegmentableBlock]) -> set[uuid.UUID]:
    """IDs of the nearest kept blocks immediately bordering an excluded
    TABLE_LIKE block, so those passages can be tagged TABLE_CONTEXT."""
    adjacent: set[uuid.UUID] = set()
    n = len(all_blocks)
    for i, block in enumerate(all_blocks):
        if block.block_type != BlockType.TABLE_LIKE:
            continue
        j = i - 1
        while j >= 0 and all_blocks[j].excluded_from_narrative:
            j -= 1
        if j >= 0:
            adjacent.add(all_blocks[j].id)
        k = i + 1
        while k < n and all_blocks[k].excluded_from_narrative:
            k += 1
        if k < n:
            adjacent.add(all_blocks[k].id)
    return adjacent


def _split_into_heading_runs(blocks: list[SegmentableBlock]) -> list[list[SegmentableBlock]]:
    """Split into runs at each HEADING_CANDIDATE boundary.

    A heading always starts a new run and is never merged with the run
    before it -- this is what "never cross a major heading boundary" means
    structurally: no later packing step ever combines blocks from two runs.
    """
    runs: list[list[SegmentableBlock]] = []
    current: list[SegmentableBlock] = []
    for block in blocks:
        if block.block_type == BlockType.HEADING_CANDIDATE and current:
            runs.append(current)
            current = [block]
        else:
            current.append(block)
    if current:
        runs.append(current)
    return runs


def _finalize_group(
    group: list[SegmentableBlock],
    heading_text: str | None,
    table_adjacent_ids: set[uuid.UUID],
    config: PassageConfig,
) -> SegmentedPassage:
    texts = [b.text.strip() for b in group]
    raw_text = "\n\n".join(texts)
    normalized_text = _normalize(raw_text)
    content_hash = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()

    first_page = min(b.page_number for b in group)
    last_page = max(b.page_number for b in group)
    word_count = len(raw_text.split())
    token_count = len(tokenize(raw_text))
    character_count = len(raw_text)

    block_types_present = {b.block_type for b in group}
    if heading_text is not None:
        passage_type = PassageType.HEADING_WITH_BODY
    elif block_types_present == {BlockType.LIST_ITEM}:
        passage_type = PassageType.LIST
    elif len(group) > 1:
        passage_type = PassageType.MULTI_PARAGRAPH
    else:
        passage_type = PassageType.PARAGRAPH

    if passage_type in (PassageType.PARAGRAPH, PassageType.MULTI_PARAGRAPH) and any(
        b.id in table_adjacent_ids for b in group
    ):
        passage_type = PassageType.TABLE_CONTEXT

    excluded = False
    reason: str | None = None
    digit_ratio = _digit_ratio(raw_text)
    if word_count >= config.numeric_density_min_words and digit_ratio >= config.numeric_density_exclusion_threshold:
        excluded = True
        reason = (
            f"numeric density {digit_ratio:.2f} exceeds threshold "
            f"({config.numeric_density_exclusion_threshold})"
        )

    return SegmentedPassage(
        passage_index=0,  # assigned by the caller once run order is final
        raw_text=raw_text,
        normalized_text=normalized_text,
        content_hash=content_hash,
        first_page_number=first_page,
        last_page_number=last_page,
        word_count=word_count,
        token_count=token_count,
        character_count=character_count,
        heading_text=heading_text,
        passage_type=passage_type,
        excluded_from_alignment=excluded,
        exclusion_reason=reason,
        source_block_ids=tuple(b.id for b in group),
    )


def _pack_run_into_passages(
    run: list[SegmentableBlock], config: PassageConfig, table_adjacent_ids: set[uuid.UUID]
) -> list[SegmentedPassage]:
    has_heading = run[0].block_type == BlockType.HEADING_CANDIDATE
    heading_text = run[0].text.strip() if has_heading else None

    groups: list[list[SegmentableBlock]] = []
    current: list[SegmentableBlock] = []
    current_words = 0
    for block in run:
        words = len(block.text.split())
        if current and current_words + words > config.max_words:
            groups.append(current)
            current = [block]
            current_words = words
        else:
            current.append(block)
            current_words += words
            if current_words >= config.target_max_words:
                groups.append(current)
                current = []
                current_words = 0
    if current:
        groups.append(current)

    # Merge a small trailing group backward within this run (never across
    # the heading boundary that starts it) if it fell under the preferred
    # minimum -- avoids leaving an orphaned tiny fragment at a run's end.
    if len(groups) > 1:
        last_words = sum(len(b.text.split()) for b in groups[-1])
        if last_words < config.min_preferred_words:
            prev_words = sum(len(b.text.split()) for b in groups[-2])
            if prev_words + last_words <= config.max_words:
                groups[-2] = groups[-2] + groups[-1]
                groups.pop()

    passages = []
    for idx, group in enumerate(groups):
        passages.append(_finalize_group(group, heading_text if idx == 0 else None, table_adjacent_ids, config))
    return passages


def segment_blocks(
    blocks: list[SegmentableBlock], config: PassageConfig = PASSAGE_CONFIG
) -> list[SegmentedPassage]:
    """Deterministically segment one report's ordered TextBlocks into passages.

    Structural algorithm (see passage_config.py docstring for size targets):
    1. Sort by (page_number, reading_order); drop excluded/empty blocks.
    2. Split into runs at each HEADING_CANDIDATE (a heading always starts a
       new run; passages never cross this boundary).
    3. Within a run, greedily pack blocks toward the target word range,
       splitting deterministically at the hard maximum and merging an
       undersized trailing group backward.
    4. Tag passage_type from block-type composition (heading/list/paragraph/
       multi-paragraph), and TABLE_CONTEXT when adjacent to an excluded
       table-like block.
    5. Exclude numeric-heavy passages and passages below the hard word floor
       (unless they carry a heading, which is a legitimate short section
       start) -- excluded passages are still returned, never dropped.
    """
    ordered = sorted(blocks, key=lambda b: (b.page_number, b.reading_order))
    table_adjacent_ids = _find_table_adjacent_ids(ordered)
    included = [b for b in ordered if not b.excluded_from_narrative and b.text.strip()]

    passages: list[SegmentedPassage] = []
    for run in _split_into_heading_runs(included):
        passages.extend(_pack_run_into_passages(run, config, table_adjacent_ids))

    result: list[SegmentedPassage] = []
    for index, passage in enumerate(passages):
        excluded = passage.excluded_from_alignment
        reason = passage.exclusion_reason
        if not excluded and passage.heading_text is None and passage.word_count < config.min_words_hard_floor:
            excluded = True
            reason = f"passage below minimum word floor ({passage.word_count} < {config.min_words_hard_floor})"
        result.append(
            replace(passage, passage_index=index, excluded_from_alignment=excluded, exclusion_reason=reason)
        )
    return result


# --------------------------------------------------------------------------
# Provenance diagnostics (pure)
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ProvenanceDiagnostics:
    fatal_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def check_provenance(
    all_blocks: list[SegmentableBlock], segmented: list[SegmentedPassage], narrative_word_count: int
) -> ProvenanceDiagnostics:
    """Verify segmentation output is reconcilable with its source blocks.

    Fatal (always FAILED, never silently accepted):
    - an included block omitted from every passage;
    - a block duplicated across passages (or within one passage).

    Warning-level (COMPLETED_WITH_WARNINGS):
    - source-order inversions within a passage;
    - a material total-word-count mismatch against the source NarrativeDocument
      (beyond the whitespace-join normalization documented in
      `narrative_construction.build_narrative_text`).
    """
    fatal: list[str] = []
    warnings: list[str] = []

    included_ids = {b.id for b in all_blocks if not b.excluded_from_narrative and b.text.strip()}
    seen: list[uuid.UUID] = []
    for passage in segmented:
        seen.extend(passage.source_block_ids)

    seen_set = set(seen)
    omitted = included_ids - seen_set
    if omitted:
        fatal.append(f"{len(omitted)} included source block(s) omitted from every passage")

    duplicates = {block_id for block_id in seen if seen.count(block_id) > 1}
    if duplicates:
        fatal.append(f"{len(duplicates)} source block(s) duplicated across passages")

    order_by_id = {b.id: (b.page_number, b.reading_order) for b in all_blocks}
    for passage in segmented:
        positions = [order_by_id[b_id] for b_id in passage.source_block_ids if b_id in order_by_id]
        if positions != sorted(positions):
            warnings.append(f"passage_index={passage.passage_index}: source-order inversion detected")

    segmented_word_count = sum(p.word_count for p in segmented)
    if narrative_word_count > 0:
        ratio = abs(segmented_word_count - narrative_word_count) / narrative_word_count
        if ratio > 0.02:
            warnings.append(
                f"segmented word count ({segmented_word_count}) diverges from narrative "
                f"word count ({narrative_word_count}) by {ratio:.1%}"
            )

    return ProvenanceDiagnostics(fatal_errors=fatal, warnings=warnings)


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_segmentation_run(session: Session, narrative_document_id: uuid.UUID) -> PassageSegmentationRun | None:
    """The current successful segmentation for a NarrativeDocument.

    Defined as the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS, exactly like `get_current_extraction_run`.
    """
    return session.scalars(
        select(PassageSegmentationRun)
        .where(
            PassageSegmentationRun.narrative_document_id == narrative_document_id,
            PassageSegmentationRun.status.in_(
                (PassageSegmentationRunStatus.COMPLETED, PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(PassageSegmentationRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_segmentation_runs_by_narrative_document(
    session: Session, narrative_document_ids: list[uuid.UUID]
) -> dict[uuid.UUID, PassageSegmentationRun]:
    if not narrative_document_ids:
        return {}
    candidate_runs = session.scalars(
        select(PassageSegmentationRun)
        .where(
            PassageSegmentationRun.narrative_document_id.in_(narrative_document_ids),
            PassageSegmentationRun.status.in_(
                (PassageSegmentationRunStatus.COMPLETED, PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(PassageSegmentationRun.narrative_document_id, PassageSegmentationRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, PassageSegmentationRun] = {}
    for run in candidate_runs:
        current.setdefault(run.narrative_document_id, run)
    return current


@dataclass
class SegmentationOutcome:
    report_id: uuid.UUID
    run: PassageSegmentationRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def segment_report(session: Session, report: Report, *, force: bool = False) -> SegmentationOutcome:
    """Segment one report's current successful NarrativeDocument.

    Eligibility requires a current successful ExtractionRun whose quality is
    not FAILED, a nonempty NarrativeDocument, and at least one source
    TextBlock. A report does not need a confirmed `period_end` to be
    segmented. Skips (returning the existing run) if the current successful
    segmentation already used an identical source ExtractionRun and an
    identical configuration fingerprint, and `force` was not set.
    """
    extraction_run = get_current_extraction_run(session, report.id)
    if extraction_run is None:
        return SegmentationOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason="report has no current successful extraction",
        )
    if extraction_run.extraction_quality == ExtractionQuality.FAILED:
        return SegmentationOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason="extraction quality is FAILED",
        )

    narrative = session.scalar(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id == extraction_run.id)
    )
    if narrative is None:
        return SegmentationOutcome(
            report_id=report.id, run=None, ineligible=True, ineligible_reason="no narrative document"
        )
    if narrative.word_count == 0 or not narrative.cleaned_text.strip():
        return SegmentationOutcome(
            report_id=report.id, run=None, ineligible=True, ineligible_reason="narrative document is empty"
        )

    text_blocks = session.scalars(
        select(TextBlock).where(TextBlock.extraction_run_id == extraction_run.id)
    ).all()
    if not text_blocks:
        return SegmentationOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason="no source TextBlocks available for provenance",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_segmentation_run(session, narrative.id)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.extraction_run_id == extraction_run.id
    ):
        return SegmentationOutcome(
            report_id=report.id, run=current_run, skipped=True,
            skip_reason="identical successful segmentation run already exists",
        )

    run = PassageSegmentationRun(
        narrative_document_id=narrative.id,
        extraction_run_id=extraction_run.id,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=PassageSegmentationRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_segmentation(session, report, narrative, extraction_run, text_blocks, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = PassageSegmentationRunStatus.FAILED
        run.error_message = f"segmentation failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("passage segmentation failed for %s", report.local_path)

    session.flush()
    return SegmentationOutcome(report_id=report.id, run=run)


def _run_segmentation(
    session: Session,
    report: Report,
    narrative: NarrativeDocument,
    extraction_run: ExtractionRun,
    text_blocks: list[TextBlock],
    run: PassageSegmentationRun,
) -> None:
    pages = session.scalars(select(Page).where(Page.extraction_run_id == extraction_run.id)).all()
    page_number_by_id = {p.id: p.page_number for p in pages}

    segmentable_blocks = [
        SegmentableBlock(
            id=b.id,
            page_number=page_number_by_id[b.page_id],
            reading_order=b.reading_order,
            block_type=b.block_type,
            text=b.cleaned_text or b.raw_text,
            excluded_from_narrative=b.excluded_from_narrative,
            exclusion_reason=b.exclusion_reason,
        )
        for b in text_blocks
    ]

    segmented = segment_blocks(segmentable_blocks, PASSAGE_CONFIG)
    diagnostics = check_provenance(segmentable_blocks, segmented, narrative.word_count)
    if diagnostics.fatal_errors:
        raise SegmentationProvenanceError("; ".join(diagnostics.fatal_errors))

    for sp in segmented:
        passage = Passage(
            segmentation_run_id=run.id,
            narrative_document_id=narrative.id,
            report_id=report.id,
            extraction_run_id=extraction_run.id,
            passage_index=sp.passage_index,
            raw_text=sp.raw_text,
            normalized_text=sp.normalized_text,
            content_hash=sp.content_hash,
            first_page_number=sp.first_page_number,
            last_page_number=sp.last_page_number,
            word_count=sp.word_count,
            token_count=sp.token_count,
            character_count=sp.character_count,
            heading_text=sp.heading_text,
            passage_type=sp.passage_type,
            excluded_from_alignment=sp.excluded_from_alignment,
            exclusion_reason=sp.exclusion_reason,
        )
        session.add(passage)
        session.flush()  # assign passage.id for the source-block rows below

        for order, block_id in enumerate(sp.source_block_ids):
            session.add(
                PassageSourceBlock(
                    passage_id=passage.id,
                    text_block_id=block_id,
                    segmentation_run_id=run.id,
                    source_order=order,
                )
            )

    run.passage_count = len(segmented)
    run.excluded_passage_count = sum(1 for p in segmented if p.excluded_from_alignment)
    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(diagnostics.warnings) if diagnostics.warnings else None
    run.status = (
        PassageSegmentationRunStatus.COMPLETED
        if not diagnostics.warnings
        else PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS
    )


@dataclass
class BatchSegmentationOutcome:
    completed: list[str] = field(default_factory=list)
    completed_with_warnings: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    ineligible: list[tuple[str, str]] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)


def segment_eligible_reports(
    session: Session, *, limit: int | None = None, force: bool = False
) -> BatchSegmentationOutcome:
    """Segment every report with a current successful extraction, continuing
    past individual failures. Reports without confirmed `period_end` are
    included -- segmentation eligibility never depends on metadata state.
    """
    outcome = BatchSegmentationOutcome()

    reports = session.scalars(select(Report).order_by(Report.directory_year, Report.local_path)).all()
    if limit is not None:
        reports = reports[:limit]

    for report in reports:
        try:
            result = segment_report(session, report, force=force)
        except Exception:
            logger.exception("unexpected orchestration error segmenting %s", report.local_path)
            outcome.failed.append((report.local_path, "unexpected orchestration error"))
            continue

        if result.ineligible:
            outcome.ineligible.append((report.local_path, result.ineligible_reason or "ineligible"))
            continue
        if result.skipped:
            outcome.skipped.append(report.local_path)
            continue

        run = result.run
        if run is None:
            continue

        if run.status == PassageSegmentationRunStatus.FAILED:
            outcome.failed.append((report.local_path, run.error_message or "unknown error"))
        elif run.status == PassageSegmentationRunStatus.COMPLETED:
            outcome.completed.append(report.local_path)
        elif run.status == PassageSegmentationRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(report.local_path)

    return outcome

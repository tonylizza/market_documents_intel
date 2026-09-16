"""Semantic-unit extraction: deterministic HEADED_NARRATIVE_UNIT algorithm
and run orchestration.

Track 7C.1 (docs/7c1-schedule-localization-plan.md). Mirrors
`services/passage_segmentation.py`'s split between a pure, DB-free
algorithm (`extract_unit`) and orchestration functions that touch the
`Session` at the bottom. Reads only the `TextBlock`s under a
`ScheduleInstance`'s page range -- never `Passage` or any other
passage-pipeline table.

Only `SemanticUnitType.HEADED_NARRATIVE_UNIT` is implemented, with two
boundary strategies (`NEXT_HEADING`, `ANCHOR_SENTENCE`) -- see
`semantic_unit_config.py`. A `SemanticUnit` row is created only once a
start heading has actually matched; if the end boundary cannot be
resolved, the row is still persisted with `boundary_status = UNRESOLVED`
and `end_page`/`source_text`/`word_count`/`boundary_confidence` left NULL
-- never a fabricated or partial best-guess value (see
docs/7c1-schedule-localization-plan.md Section 4.2's persistence-behavior
note).
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    BlockType,
    BoundaryConfidence,
    NormalizedSchedule,
    ScheduleLocalizationStatus,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
    SemanticUnitRunStatus,
    SemanticUnitType,
)
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.models.schedule import ScheduleInstance, ScheduleLocalizationRun
from market_documents.models.semantic_unit import SemanticUnit, SemanticUnitRun, SemanticUnitSourceBlock
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.schedule_localization import get_current_localization_run
from market_documents.services.semantic_unit_config import UnitConfig, compute_configuration_hash, unit_configs_for

logger = logging.getLogger(__name__)

# v1.0.0 = initial deterministic HEADED_NARRATIVE_UNIT extractor
# (NEXT_HEADING / ANCHOR_SENTENCE only).
# v1.0.1 = normalize typographic quotes/apostrophes to ASCII before heading
# matching, mirroring the same fix in schedule_localization.py (7C.1
# real-corpus acceptance run).
ALGORITHM_VERSION = "1.0.1"


# --------------------------------------------------------------------------
# Pure data structures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class UnitBlock:
    """A minimal, ORM-free view of one TextBlock, for the pure algorithm."""

    id: uuid.UUID
    page_number: int
    reading_order: int
    block_type: BlockType
    text: str


@dataclass(frozen=True)
class SemanticUnitExtractionResult:
    unit_key: str
    source_heading: str
    start_page: int
    boundary_strategy: SemanticUnitBoundaryStrategy
    boundary_anchor_text: str | None
    boundary_status: SemanticUnitBoundaryStatus
    boundary_confidence: BoundaryConfidence | None
    end_page: int | None
    source_text: str | None
    word_count: int | None
    extraction_note: str | None
    # Empty for UNRESOLVED. `(0, len(block.text))` for a fully-included
    # block, narrower only for the block containing an ANCHOR_SENTENCE match.
    source_block_spans: tuple[tuple[uuid.UUID, int, int], ...] = ()


_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})


def _normalize(text: str) -> str:
    return " ".join(text.strip().split()).lower().translate(_QUOTE_TRANSLATION)


def _matches_heading(block_text: str, configured_heading: str) -> bool:
    normalized_block = _normalize(block_text)
    normalized_heading = _normalize(configured_heading)
    return normalized_heading in normalized_block


def _heading_prefix_match(text: str, configured_heading: str) -> re.Match | None:
    """Match a heading rendered as a run-in prefix of a PARAGRAPH block's raw
    text (e.g. "Gross Margin The gross margin is dependent on..."), a
    pattern the real BEL corpus shows in 4 of 5 validated years -- the
    upstream block classifier types the whole run as one PARAGRAPH block
    rather than splitting a separate HEADING_CANDIDATE block, so a start
    heading that only ever matches a standalone HEADING_CANDIDATE block (as
    `_matches_heading` requires) misses it entirely. Whitespace-tolerant and
    quote-normalized like the rest of this module's matching."""
    words = configured_heading.translate(_QUOTE_TRANSLATION).split()
    if not words:
        return None
    pattern = r"^\s*" + r"\s+".join(re.escape(w) for w in words) + r"\b"
    return re.match(pattern, text.translate(_QUOTE_TRANSLATION), re.IGNORECASE)


def _unresolved(config: UnitConfig, start_block: UnitBlock, note: str) -> SemanticUnitExtractionResult:
    return SemanticUnitExtractionResult(
        unit_key=config.unit_key,
        source_heading=start_block.text.strip(),
        start_page=start_block.page_number,
        boundary_strategy=config.boundary_strategy,
        boundary_anchor_text=None,
        boundary_status=SemanticUnitBoundaryStatus.UNRESOLVED,
        boundary_confidence=None,
        end_page=None,
        source_text=None,
        word_count=None,
        extraction_note=note,
        source_block_spans=(),
    )


def extract_unit(blocks: list[UnitBlock], config: UnitConfig) -> SemanticUnitExtractionResult | None:
    """Deterministically extract one HEADED_NARRATIVE_UNIT.

    A start heading is recognized two ways: as a standalone HEADING_CANDIDATE
    block (the common case), or as a run-in prefix of a PARAGRAPH block's raw
    text -- the real BEL corpus shows the upstream block classifier fusing a
    sub-heading like "Gross Margin" onto the same block as its body text in
    most validated years, rather than segmenting it as its own heading block
    (see `_heading_prefix_match`). In the run-in case, the remainder of that
    same block (after the heading) is the first fragment of body content.

    Returns `None` -- not a row of any kind -- if `config.start_heading`
    never matches: a SemanticUnit row is only ever created once a start
    heading has actually matched (see module docstring). Once a start
    heading is found, always returns a result (RESOLVED or UNRESOLVED),
    never `None`.
    """
    ordered = sorted(blocks, key=lambda b: (b.page_number, b.reading_order))

    start_idx: int | None = None
    start_heading_text: str | None = None
    remainder_offset = 0
    for i, b in enumerate(ordered):
        if b.block_type == BlockType.HEADING_CANDIDATE and _matches_heading(b.text, config.start_heading):
            start_idx = i
            start_heading_text = b.text.strip()
            remainder_offset = len(b.text)
            break
        if b.block_type == BlockType.PARAGRAPH:
            prefix_match = _heading_prefix_match(b.text, config.start_heading)
            if prefix_match is not None:
                start_idx = i
                start_heading_text = b.text[: prefix_match.end()].strip()
                remainder_offset = prefix_match.end()
                break

    if start_idx is None:
        return None

    start_block = ordered[start_idx]
    remainder_text = start_block.text[remainder_offset:]
    later_blocks = ordered[start_idx + 1 :]

    # The body's first fragment (if any) is the run-in remainder of the
    # start block itself; `body_blocks` are the whole subsequent blocks.
    lead_fragment = (start_block, remainder_offset, remainder_text) if remainder_text.strip() else None
    body_blocks = later_blocks

    if lead_fragment is None and not body_blocks:
        return _unresolved(config, start_block, "no body content found after the matched start heading")

    if config.boundary_strategy == SemanticUnitBoundaryStrategy.NEXT_HEADING:
        end_idx = next(
            (j for j, b in enumerate(body_blocks) if b.block_type == BlockType.HEADING_CANDIDATE), None
        )
        included = body_blocks if end_idx is None else body_blocks[:end_idx]
        if lead_fragment is None and not included:
            return _unresolved(
                config, start_block, "next heading-candidate block immediately follows the start heading"
            )
        text_parts = ([lead_fragment[2].strip()] if lead_fragment else []) + [b.text.strip() for b in included]
        source_text = "\n\n".join(part for part in text_parts if part)
        spans = ([(start_block.id, remainder_offset, len(start_block.text))] if lead_fragment else []) + [
            (b.id, 0, len(b.text)) for b in included
        ]
        last_page = included[-1].page_number if included else start_block.page_number
        return SemanticUnitExtractionResult(
            unit_key=config.unit_key,
            source_heading=start_heading_text,
            start_page=start_block.page_number,
            boundary_strategy=config.boundary_strategy,
            boundary_anchor_text=None,
            boundary_status=SemanticUnitBoundaryStatus.RESOLVED,
            boundary_confidence=BoundaryConfidence.HIGH,
            end_page=last_page,
            source_text=source_text,
            word_count=len(source_text.split()),
            extraction_note=None,
            source_block_spans=tuple(spans),
        )

    # ANCHOR_SENTENCE
    assert config.anchor_pattern is not None, f"unit {config.unit_key} is ANCHOR_SENTENCE but has no anchor_pattern"

    concat = ""
    offset_map: list[tuple[UnitBlock, int, int, int]] = []  # (block, block_text_offset, concat_start, concat_end)
    if lead_fragment is not None:
        _, block_offset, text = lead_fragment
        concat += text
        offset_map.append((start_block, block_offset, 0, len(concat)))
    for b in body_blocks:
        if concat:
            concat += "\n\n"
        start_off = len(concat)
        concat += b.text
        offset_map.append((b, 0, start_off, len(concat)))

    match = config.anchor_pattern.search(concat)
    if match is None:
        return _unresolved(
            config, start_block,
            f"anchor pattern {config.anchor_pattern.pattern!r} not found in body text following the start heading",
        )

    match_end = match.end()
    included: list[UnitBlock] = []
    spans: list[tuple[uuid.UUID, int, int]] = []
    for b, block_offset, concat_start, concat_end in offset_map:
        if concat_start >= match_end:
            break
        included.append(b)
        if concat_end >= match_end:
            local_end = block_offset + (match_end - concat_start)
            spans.append((b.id, block_offset, local_end))
            break
        spans.append((b.id, block_offset, len(b.text)))

    source_text = concat[:match_end]
    return SemanticUnitExtractionResult(
        unit_key=config.unit_key,
        source_heading=start_heading_text,
        start_page=start_block.page_number,
        boundary_strategy=config.boundary_strategy,
        boundary_anchor_text=match.group(0),
        boundary_status=SemanticUnitBoundaryStatus.RESOLVED,
        boundary_confidence=BoundaryConfidence.HIGH,
        end_page=included[-1].page_number if included else start_block.page_number,
        source_text=source_text,
        word_count=len(source_text.split()),
        extraction_note=None,
        source_block_spans=tuple(spans),
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_unit_run(
    session: Session, report_id: uuid.UUID, schedule: NormalizedSchedule
) -> SemanticUnitRun | None:
    return session.scalars(
        select(SemanticUnitRun)
        .where(
            SemanticUnitRun.report_id == report_id,
            SemanticUnitRun.schedule == schedule,
            SemanticUnitRun.status.in_(
                (SemanticUnitRunStatus.COMPLETED, SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(SemanticUnitRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class UnitExtractionOutcome:
    report_id: uuid.UUID
    run: SemanticUnitRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def run_extraction(
    session: Session, report: Report, schedule: NormalizedSchedule, *, force: bool = False
) -> UnitExtractionOutcome:
    """Extract every configured HEADED_NARRATIVE_UNIT for one report's
    current successful schedule localization.

    Eligibility requires a current successful ScheduleLocalizationRun for
    (report, schedule) whose ScheduleInstance has a primary span
    (FOUND_PRIMARY_ONLY or FOUND_PRIMARY_AND_SUPPORTING), and at least one
    unit configured for this report's ticker + schedule in
    `semantic_unit_config.py`. Skips (returning the existing run) if the
    current successful extraction already used an identical source
    localization run, and `force` was not set.
    """
    localization_run = get_current_localization_run(session, report.id, schedule)
    if localization_run is None:
        return UnitExtractionOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason=f"report has no current successful {schedule.value} localization",
        )

    instance = session.scalar(
        select(ScheduleInstance).where(ScheduleInstance.schedule_localization_run_id == localization_run.id)
    )
    if instance is None or instance.status not in (
        ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY, ScheduleLocalizationStatus.FOUND_PRIMARY_AND_SUPPORTING
    ):
        return UnitExtractionOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason=f"{schedule.value} schedule instance has no primary span",
        )

    configs = unit_configs_for(report.company.ticker, schedule)
    if not configs:
        return UnitExtractionOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason=f"no HEADED_NARRATIVE_UNIT configured for {report.company.ticker}/{schedule.value}",
        )

    configuration_hash = compute_configuration_hash(configs)

    current_run = get_current_unit_run(session, report.id, schedule)
    if (
        current_run is not None
        and not force
        and current_run.schedule_localization_run_id == localization_run.id
        and current_run.configuration_hash == configuration_hash
    ):
        return UnitExtractionOutcome(
            report_id=report.id, run=current_run, skipped=True,
            skip_reason="identical successful extraction run already exists",
        )

    run = SemanticUnitRun(
        report_id=report.id,
        schedule_localization_run_id=localization_run.id,
        schedule=schedule,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=SemanticUnitRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_extraction(session, report, localization_run, instance, configs, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = SemanticUnitRunStatus.FAILED
        run.error_message = f"semantic unit extraction failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("semantic unit extraction failed for %s (%s)", report.local_path, schedule.value)

    session.flush()
    return UnitExtractionOutcome(report_id=report.id, run=run)


def _run_extraction(
    session: Session,
    report: Report,
    localization_run: ScheduleLocalizationRun,
    instance: ScheduleInstance,
    configs: tuple[UnitConfig, ...],
    run: SemanticUnitRun,
) -> None:
    extraction_run = session.get(ExtractionRun, localization_run.extraction_run_id)
    pages = session.scalars(
        select(Page).where(
            Page.extraction_run_id == extraction_run.id,
            Page.page_number >= instance.start_page,
            Page.page_number <= instance.end_page,
        )
    ).all()
    page_number_by_id = {p.id: p.page_number for p in pages}

    text_blocks = session.scalars(
        select(TextBlock).where(
            TextBlock.extraction_run_id == extraction_run.id,
            TextBlock.page_id.in_(page_number_by_id.keys()),
            TextBlock.excluded_from_narrative.is_(False),
        )
    ).all()

    unit_blocks = [
        UnitBlock(
            id=b.id, page_number=page_number_by_id[b.page_id], reading_order=b.reading_order,
            block_type=b.block_type, text=b.cleaned_text or b.raw_text,
        )
        for b in text_blocks
    ]

    notes: list[str] = []
    for config in configs:
        result = extract_unit(unit_blocks, config)
        if result is None:
            notes.append(f"{config.unit_key}: start heading {config.start_heading!r} not found -- no row created")
            continue

        unit = SemanticUnit(
            semantic_unit_run_id=run.id,
            report_id=report.id,
            schedule_instance_id=instance.id,
            unit_key=result.unit_key,
            unit_type=SemanticUnitType.HEADED_NARRATIVE_UNIT,
            source_heading=result.source_heading,
            start_page=result.start_page,
            boundary_strategy=result.boundary_strategy,
            boundary_anchor_text=result.boundary_anchor_text,
            boundary_status=result.boundary_status,
            boundary_confidence=result.boundary_confidence,
            end_page=result.end_page,
            source_text=result.source_text,
            word_count=result.word_count,
            extraction_note=result.extraction_note,
        )
        session.add(unit)
        session.flush()

        for order, (block_id, char_start, char_end) in enumerate(result.source_block_spans):
            session.add(
                SemanticUnitSourceBlock(
                    semantic_unit_id=unit.id, text_block_id=block_id,
                    block_order=order, char_start=char_start, char_end=char_end,
                )
            )

        if result.boundary_status == SemanticUnitBoundaryStatus.UNRESOLVED:
            notes.append(f"{config.unit_key}: UNRESOLVED -- {result.extraction_note}")

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = SemanticUnitRunStatus.COMPLETED if not notes else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS

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
from market_documents.services import source_adapter
from market_documents.services.canonical_extraction import get_current_canonical_run
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.schedule_localization import get_current_localization_run
from market_documents.services.semantic_unit_config import UnitConfig, compute_configuration_hash, unit_configs_for

logger = logging.getLogger(__name__)

# v1.0.0 = initial deterministic HEADED_NARRATIVE_UNIT extractor
# (NEXT_HEADING / ANCHOR_SENTENCE only).
# v1.0.1 = normalize typographic quotes/apostrophes to ASCII before heading
# matching, mirroring the same fix in schedule_localization.py (7C.1
# real-corpus acceptance run).
# v1.1.0 = Track 7D.1: `_heading_run_in_match` (formerly `_heading_prefix_match`)
# now also matches a configured heading immediately after a sentence
# boundary anywhere inside a PARAGRAPH block, not just at the block's start
# -- BEL 2020's "Gross Margin" heading is fused onto the *end* of the
# preceding section's paragraph rather than starting a fresh block
# (docs/7d1-known-recall-defect-remediation.md).
# v1.2.0 = Track 7D.2 (docs/7d2-financial-performance-unit-expansion.md):
# NEXT_HEADING's end-boundary scan now skips a heading-candidate that is a
# "<something> continued" page-continuation banner instead of treating it
# as the section's terminator -- mirroring the same generic rule
# `schedule_localization.py` already applies at the schedule level (its
# v1.0.4: "a '<heading> continued' candidate is the same section resuming,
# not a new section"). Real ACT 2021 corpus evidence
# (ACT_HEALTHCARE_SERVICES_REVIEW's real-corpus validation) showed the
# opposite classification for the exact same "CFO's review continued"
# banner text across adjacent report years -- ACT 2022 classifies it
# excluded_from_narrative (so it was never a candidate boundary there) while
# ACT 2021 classifies it as a genuine, narrative heading-candidate, which
# would otherwise truncate the unit one page early and drop a real
# continuation paragraph. Generic (matches on the trailing word "continued"
# after normalization, not any specific heading text), so it applies to any
# NEXT_HEADING unit, not just this track's new ones.
# v1.3.0 = Track 7D.2a (docs/7d2a-semantic-unit-extraction-hardening.md):
# two hardening changes.
# (1) `_matches_heading` (formerly a bare case-insensitive substring check)
# now returns (matched, exact) with the same exact/substring/word-order-
# tolerant evidence hierarchy `schedule_localization._matches_vocabulary`
# already uses, and `extract_unit`'s start-heading scan now ranks every
# match in the report (exact first, then earliest position) instead of
# simply taking the first positional match. Fixes the generic false-positive
# risk Track 7D.2 documented and deliberately left unfixed (its own
# one-correction-per-track budget was already spent): real ACT 2024 corpus
# text contains an unrelated decorative pull-quote heading-candidate
# fragment, "by prudent capital management policies", a bare substring
# match for a heading like "Capital management" that sits earlier in
# reading order than the real, exact "CAPITAL MANAGEMENT" section heading --
# the old first-match behavior let the false match win and the real section
# was never reached.
# (2) `_run_extraction` now prefers the canonical PDF source (Track 7C.1a)
# over legacy `TextBlock` when a report has a current successful
# `CanonicalExtractionRun`, mirroring `schedule_localization.py`'s own
# canonical preference (its 7C.1b) via the same `source_adapter` module --
# resolves the numeric-fragment-noise extraction-quality gap Track 7D.2
# Section 14 documented for `ACT healthcare_services_review` (legacy
# `TextBlock` did not mark several small chart-label fragments as
# `excluded_from_narrative`; the canonical/7C.1a path already classifies
# the equivalent content `NUMERIC_FRAGMENT`, excluded).
# v1.4.0 = Track 7D.3 (docs/7d3-corporate-governance-expansion.md), the
# milestone's one allowed generic parser correction: `_run_extraction`'s
# page-range query now unions the `ScheduleInstance` primary span with every
# `ScheduleInstanceSupportingSpan` page range, not just the primary. A
# `FOUND_PRIMARY_AND_SUPPORTING` instance's own `start_page`/`end_page`
# columns cover only the primary heading's own span (by design -- see
# `ScheduleInstanceSupportingSpan`'s docstring); a schedule whose "continued"
# occurrences each register as their own supporting span (BEL's
# CORPORATE_GOVERNANCE 2018/2019: primary pp.38-38/40-40, supporting spans
# extending to p.47/49) was silently searched for unit start headings only
# on the primary's one or two pages, missing every subsection heading on the
# "continued" pages entirely. Generic (reads `supporting_spans`, not any
# schedule- or heading-specific text), so it applies to every existing and
# future NEXT_HEADING/ANCHOR_SENTENCE unit, not just CORPORATE_GOVERNANCE's
# new ones.
# v1.5.0 = Track 7D.4 (docs/7d4-corpus-wide-remuneration-expansion.md), the
# milestone's one allowed generic parser/localizer correction: the v1.4.0
# fix above widened only the search range's *end* page (`max` over
# supporting-span end pages) -- it never pulled the *start* page earlier,
# so a supporting span that begins *before* the primary's own start_page was
# still silently excluded. Real bug found in ACT's real corpus: 2020's and
# 2021's REMUNERATION primary span anchors on a "REMUNERATION REPORT
# (CONTINUED)" banner (2020 p.96, 2021 p.108), while the real chapter start
# -- including the "Remuneration Committee Chairperson's report" heading --
# registers as an earlier supporting span (2020 p.94, 2021 p.107) that the
# v1.4.0 range (`[instance.start_page, widened_end]`) never reached. Now
# `range_start_page = min(instance.start_page, every supporting span's own
# start_page)`, symmetric with the existing end-page widening. Generic (same
# `supporting_spans` field, no schedule- or heading-specific text), applies
# to every existing and future NEXT_HEADING/ANCHOR_SENTENCE unit. Regression
# test: `tests/test_semantic_unit_extraction_service.py`.
# v1.6.0 = Track 7D.4a (docs/7d4a-start-heading-false-positive-hardening.md):
# start-heading false-positive hardening, generic across every schedule.
# Real-corpus investigation (querying the live ACT 2022/2023 CORPORATE_GOVERNANCE
# and ACT 2024 REMUNERATION canonical blocks directly, not just the
# documented prose summaries) found the actual mechanism behind two
# independently-documented defects (CORPORATE_GOVERNANCE `combined_assurance`,
# REMUNERATION `remuneration_governance`) is narrower than assumed: both are
# caused by `_heading_run_in_match` firing on an ordinary PARAGRAPH block
# that merely *opens* with the configured heading's words before continuing
# the same grammatical sentence -- e.g. real ACT 2024 p.121 "Remuneration
# governance to remain top of mind with a greater focus on approval
# frameworks..." and real ACT 2022/2023 "Combined assurance approach\nStrong
# Lead Independent Director..." -- rather than genuinely starting a new
# heading followed by fresh body prose (the legitimate BEL "Gross Margin The
# gross margin is dependent on..." pattern `_heading_run_in_match` exists
# for). Both false matches are exact-by-construction (the regex requires the
# exact word sequence) and sit earlier in reading order than the real,
# standalone `HEADING_CANDIDATE` heading later in the same range, so they
# won outright under the existing (exact, position) ranking -- no
# HEADING_CANDIDATE exact/substring/word-order tiering was involved in
# either real defect (the third documented case, FINANCIAL_PERFORMANCE's
# never-configured "Capital management" candidate, was already a
# HEADING_CANDIDATE substring match and was already fixed by 7D.2a's
# exact/substring tiering). `_run_in_remainder_is_prose_continuation`
# rejects a run-in match whose immediately-following text (after stripping
# leading whitespace) starts with a lowercase letter -- a genuine run-in
# heading is followed by a fresh sentence (capitalized, as in every
# validated BEL case), while ordinary prose that happens to open with the
# heading's own words continues the same clause in lowercase. A candidate
# rejected this way is treated as no match at all (not merely demoted),
# letting a later, genuine HEADING_CANDIDATE match win instead of never
# resolving. Purely a text-shape check (capitalization of one character),
# not schedule- or heading-specific, so it applies to every existing and
# future run-in match, not just the two documented defects. Regression
# tests: `tests/test_semantic_unit_extraction.py` (pure-algorithm) and
# `tests/test_semantic_unit_extraction_service.py` (DB-backed, real-corpus
# shape).
ALGORITHM_VERSION = "1.6.0"


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


def _is_continuation_heading(text: str) -> bool:
    """True for a "<something> continued" page-continuation banner --
    the same section resuming on a new page, never a new section's own
    heading. Mirrors `schedule_localization._matches_vocabulary`'s sibling
    rule at the schedule level (its v1.0.4 comment)."""
    return _normalize(text).endswith("continued")


def _matches_heading(block_text: str, configured_heading: str) -> tuple[bool, bool]:
    """Returns (matched, exact) -- mirrors
    `schedule_localization._matches_vocabulary`'s evidence hierarchy at the
    unit level: an exact normalized-text match is stronger evidence than a
    bare substring match, and a substring match is generalized further by a
    tight, order-tolerant word-window check for the same real
    PDF-extraction word-reordering artifact `_matches_vocabulary` documents.

    A bare substring check alone is a real, generic false-positive risk
    (Track 7D.2's rejected-candidate finding, fixed here in Track 7D.2a):
    real ACT 2024 corpus text contains an unrelated decorative pull-quote
    heading-candidate fragment, "by prudent capital management policies",
    which contains "capital management" as a bare substring and sits
    earlier in reading order than the real, exact "CAPITAL MANAGEMENT"
    section heading later in the document. Returning exactness lets the
    caller (`extract_unit`) rank every match in the document instead of
    simply taking whichever one occurs first."""
    normalized_block = _normalize(block_text)
    normalized_heading = _normalize(configured_heading)
    if normalized_block == normalized_heading:
        return True, True
    if normalized_heading in normalized_block:
        return True, False
    heading_words = normalized_heading.split()
    block_word_list = normalized_block.split()
    window_size = len(heading_words) + 1
    if len(heading_words) >= 2 and any(
        set(heading_words) <= set(block_word_list[i : i + window_size])
        for i in range(len(block_word_list))
    ):
        return True, False
    return False, False


def _heading_run_in_match(text: str, configured_heading: str) -> re.Match | None:
    """Match a heading rendered as a run-in inside a PARAGRAPH block's raw
    text, either at the block's start (e.g. "Gross Margin The gross margin
    is dependent on...", the pattern the real BEL corpus shows in 4 of 5
    validated years) or mid-block, immediately after a sentence boundary
    (e.g. BEL 2020's "...for parts and machines supplied. Gross Margin The
    gross margin is dependent on...", where the upstream block classifier
    fuses the heading onto the *end* of the preceding section's own
    paragraph rather than starting a fresh block with it). In either case
    the upstream block classifier typed the whole run as one PARAGRAPH block
    rather than splitting a separate HEADING_CANDIDATE block, so a start
    heading that only ever matches a standalone HEADING_CANDIDATE block (as
    `_matches_heading` requires) misses it entirely.

    Anchoring the mid-block case to a sentence boundary -- immediately after
    a preceding '.', '!' or '?' plus whitespace, never just anywhere in the
    block -- is what keeps this from firing on an ordinary occurrence of the
    heading's words in the middle of unrelated body prose: real prose
    referring to the same concept mid-sentence (e.g. "...remains driven by
    gross margin trends across...") is never immediately preceded by
    sentence-ending punctuation. Whitespace-tolerant and quote-normalized
    like the rest of this module's matching. Returns the heading itself as
    capture group 1, so callers can recover its exact start/end offsets
    within the block regardless of which case matched."""
    words = configured_heading.translate(_QUOTE_TRANSLATION).split()
    if not words:
        return None
    heading_pattern = r"\s+".join(re.escape(w) for w in words) + r"\b"
    pattern = r"(?:^\s*|(?<=[.!?])\s+)(" + heading_pattern + r")"
    return re.search(pattern, text.translate(_QUOTE_TRANSLATION), re.IGNORECASE)


def _run_in_remainder_is_prose_continuation(text: str, match: re.Match) -> bool:
    """Track 7D.4a: True if the text immediately following a run-in heading
    match reads as a grammatical continuation of the *same* sentence, not
    the start of fresh body prose -- the generic signal that distinguishes
    real ACT corpus false positives (REMUNERATION 2024 p.121: "Remuneration
    governance to remain top of mind with a greater focus..."; CORPORATE_GOVERNANCE
    2022/2023: "Combined assurance approach\nStrong Lead Independent
    Director...") from every validated genuine run-in heading (BEL: "Gross
    Margin The gross margin is dependent on...", always followed by a fresh,
    capitalized sentence).

    Checks the capitalization of the first letter after the match -- no
    specific wording -- so it generalizes to any configured heading. A
    lowercase continuation is excused, however, when a line break separates
    it from the match: real ACT 2019 corpus text shows a genuine heading
    wrapping across a line break before its own year suffix ("Changes to
    the remuneration and related policies \nfor the 2019 financial year",
    the configured heading being only "Changes to the remuneration and
    related policies"), immediately followed on its own next line by the
    real, capitalized body paragraph -- a line break there is either the
    same heading continuing (as in this case) or a genuine paragraph break,
    never evidence that the match is embedded mid-sentence in ordinary
    prose. Both real false positives above have their lowercase
    continuation on the *same* line as the match (no line break), which is
    what actually distinguishes them from this legitimate case. An empty
    remainder (heading matched at the very end of the block) is never a
    continuation."""
    remainder = text[match.end() :]
    stripped = remainder.lstrip()
    if not stripped:
        return False
    leading_whitespace = remainder[: len(remainder) - len(stripped)]
    if "\n" in leading_whitespace:
        return False
    first_char = stripped[0]
    return first_char.isalpha() and first_char.islower()


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
    block (the common case), or as a run-in inside a PARAGRAPH block's raw
    text, at the block's start or mid-block after a sentence boundary -- the
    real BEL corpus shows the upstream block classifier fusing a sub-heading
    like "Gross Margin" onto the same block as its body text (most validated
    years at the block's start; 2020 mid-block, fused onto the end of the
    *preceding* section's own paragraph) rather than segmenting it as its
    own heading block (see `_heading_run_in_match`). In the run-in case, the
    remainder of that same block (after the heading) is the first fragment
    of body content.

    Returns `None` -- not a row of any kind -- if `config.start_heading`
    never matches: a SemanticUnit row is only ever created once a start
    heading has actually matched (see module docstring). Once a start
    heading is found, always returns a result (RESOLVED or UNRESOLVED),
    never `None`.

    Track 7D.2a: every candidate match in the document is collected and
    ranked (an exact match first, then earliest position), not just the
    first one encountered -- a coincidental bare-substring match can
    precede the real heading in reading order (see `_matches_heading`), and
    picking the first positional match let that false match win. A run-in
    match (`_heading_run_in_match`) is exact by construction (its regex
    requires the heading's exact word sequence), so it ranks the same as a
    standalone exact match.
    """
    ordered = sorted(blocks, key=lambda b: (b.page_number, b.reading_order))

    candidates: list[tuple[int, bool, str, int]] = []
    for i, b in enumerate(ordered):
        if b.block_type == BlockType.HEADING_CANDIDATE:
            matched, exact = _matches_heading(b.text, config.start_heading)
            if matched:
                candidates.append((i, exact, b.text.strip(), len(b.text)))
        elif b.block_type == BlockType.PARAGRAPH:
            run_in_match = _heading_run_in_match(b.text, config.start_heading)
            if run_in_match is not None and not _run_in_remainder_is_prose_continuation(b.text, run_in_match):
                candidates.append((i, True, run_in_match.group(1).strip(), run_in_match.end(1)))

    if not candidates:
        return None

    candidates.sort(key=lambda c: (0 if c[1] else 1, c[0]))
    start_idx, _, start_heading_text, remainder_offset = candidates[0]

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
            (
                j
                for j, b in enumerate(body_blocks)
                if b.block_type == BlockType.HEADING_CANDIDATE and not _is_continuation_heading(b.text)
            ),
            None,
        )
        included = body_blocks if end_idx is None else body_blocks[:end_idx]
        # A continuation banner skipped above as a non-terminator still
        # falls inside `included` by position -- drop it from the actual
        # unit content, it is a running page header, not unit prose.
        included = [
            b for b in included if not (b.block_type == BlockType.HEADING_CANDIDATE and _is_continuation_heading(b.text))
        ]
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
    # Track 7D.2a: prefer the canonical source (Track 7C.1a) when this
    # report has a current successful CanonicalExtractionRun, mirroring
    # `schedule_localization._run_localization`'s own canonical preference
    # (its 7C.1b) -- canonical classification already marks small numeric
    # chart-label fragments `excluded_from_narrative` where legacy TextBlock
    # extraction did not (Track 7D.2 Section 14's documented gap for `ACT
    # healthcare_services_review`). Falls back to legacy TextBlock,
    # unchanged, for a report with no canonical extraction yet.
    # Track 7D.3's one generic parser correction: a FOUND_PRIMARY_AND_SUPPORTING
    # instance's own start_page/end_page cover only the primary heading's
    # span, never the supporting spans (see ScheduleInstanceSupportingSpan's
    # docstring) -- widen the search range to their union so a unit heading
    # on a "continued" supporting-span page is not silently missed.
    range_start_page = instance.start_page
    range_end_page = instance.end_page
    if range_start_page is not None and range_end_page is not None:
        for span in instance.supporting_spans:
            range_start_page = min(range_start_page, span.start_page)
            range_end_page = max(range_end_page, span.end_page)

    canonical_run = get_current_canonical_run(session, report.id)
    using_canonical = canonical_run is not None
    if using_canonical:
        source_pages = source_adapter.load_source_pages(session, canonical_run.id)
        classified = source_adapter.classify_source_pages(source_pages)
        unit_blocks = source_adapter.build_unit_blocks(
            classified, start_page=range_start_page, end_page=range_end_page
        )
    else:
        extraction_run = session.get(ExtractionRun, localization_run.extraction_run_id)
        pages = session.scalars(
            select(Page).where(
                Page.extraction_run_id == extraction_run.id,
                Page.page_number >= range_start_page,
                Page.page_number <= range_end_page,
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
                    semantic_unit_id=unit.id,
                    canonical_block_id=block_id if using_canonical else None,
                    text_block_id=None if using_canonical else block_id,
                    block_order=order, char_start=char_start, char_end=char_end,
                )
            )

        if result.boundary_status == SemanticUnitBoundaryStatus.UNRESOLVED:
            notes.append(f"{config.unit_key}: UNRESOLVED -- {result.extraction_note}")

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = SemanticUnitRunStatus.COMPLETED if not notes else SemanticUnitRunStatus.COMPLETED_WITH_WARNINGS

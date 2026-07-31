"""Pure, database-free data shapes for the Milestone 7B.1d Q&A
retrieval-chunk experiment. Mirrors `publishing/labels.py`'s convention: no
function in this package's `chunk_strategies`/`token_budget` modules ever
opens a session -- `build_chunks.py` is the only module allowed to query or
write to the app database."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

ROLE_PREVIOUS = "PREVIOUS"
ROLE_ANCHOR = "ANCHOR"
ROLE_NEXT = "NEXT"
ROLE_EARLIER_SIDE = "EARLIER_SIDE"
ROLE_LATER_SIDE = "LATER_SIDE"
ROLE_HEADING_CONTEXT = "HEADING_CONTEXT"
ROLE_TOKEN_MEMBER = "TOKEN_MEMBER"


@dataclass(frozen=True)
class PassageRow:
    """One `app.current_passages` row, ordered within its report by
    `passage_index` -- the app-layer equivalent of the research layer's
    `Passage.passage_index` (see `services/passage_segmentation.py`)."""

    id: uuid.UUID
    report_id: uuid.UUID
    company_id: uuid.UUID
    passage_index: int
    heading: str | None
    text: str
    word_count: int
    first_page_number: int
    last_page_number: int


@dataclass(frozen=True)
class ComparisonRow:
    """One `app.current_passage_comparisons` row with its parent
    `report_comparisons` period ends denormalized in, since only
    comparison-pair chunk construction needs them."""

    id: uuid.UUID
    report_comparison_id: uuid.UUID
    company_id: uuid.UUID
    earlier_passage_id: uuid.UUID | None
    later_passage_id: uuid.UUID | None
    alignment_status: str
    earlier_period_end: date | None
    later_period_end: date | None


@dataclass(frozen=True)
class ChunkMember:
    passage_id: uuid.UUID
    role: str
    passage_order: int


@dataclass(frozen=True)
class ComparisonContext:
    passage_comparison_id: uuid.UUID
    report_comparison_id: uuid.UUID
    report_side: str
    alignment_status: str
    earlier_period_end: date | None
    later_period_end: date | None


@dataclass
class ChunkCandidate:
    """Mutable during construction/token-budget enforcement; frozen in
    intent once `build_chunks.py` hands it to the embedding step."""

    strategy: str
    report_id: uuid.UUID
    company_id: uuid.UUID
    anchor_passage_id: uuid.UUID
    text: str
    members: tuple[ChunkMember, ...]
    page_start: int
    page_end: int
    truncation_policy: str = "none"
    comparison_contexts: tuple[ComparisonContext, ...] = ()

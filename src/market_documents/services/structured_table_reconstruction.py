"""Structured-table reconstruction: deterministic row/column/cell/footnote
recovery from `CanonicalBlock` text for the two validated ACT table
families (Track 7C.4, docs/7c4-structured-table-comparison.md).

Implements the row-block methodology validated in
docs/experiments/annual-report-structured-table-comparison.md Section 3:
PyMuPDF's `get_text("blocks")` (the same primitive `CanonicalBlock.raw_text`
already captures) groups each table row into one block, in native
emission/reading order, with the row label followed by its cell values in
strict left-to-right printed order -- so row/column association is a
text/regex parse, not a geometric clustering pass. Never globally
re-sorts blocks (mirrors `pdf_source.py`'s own discipline); block-order
consumption is native, with one narrow, source-observed exception (see
`_within_table_region` below) needed to exclude a same-page, unrelated
footnote that PyMuPDF happens to emit out of visual order.

Reads only `CanonicalBlock` (via the caller-supplied `TableSourceBlock`
view) -- never `SemanticUnit`, `Passage`, or `TextBlock`.
"""

import hashlib
import json
import logging
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    AlignmentConfidence,
    StructuredCellStatus,
    StructuredRowIdentityType,
    StructuredTableExtractionRunStatus,
    StructuredTableReconstructionStatus,
    StructuredTableShape,
)
from market_documents.models.pdf_source import CanonicalBlock, CanonicalPage
from market_documents.models.report import Report
from market_documents.models.structured_table import (
    StructuredTable,
    StructuredTableCell,
    StructuredTableColumn,
    StructuredTableExtractionRun,
    StructuredTableFootnote,
    StructuredTableRow,
)
from market_documents.services.canonical_extraction import get_current_canonical_run
from market_documents.services.structured_table_config import (
    TABLE_FAMILY_CONFIGS,
    TableFamilyConfig,
    normalize_apostrophes,
    table_family_config_for_key,
)

logger = logging.getLogger(__name__)

# v1.0.0 = initial deterministic row-block parser for
# ned_remuneration_policy_table / total_remuneration_outcomes, corrected
# against real ACT CanonicalBlock output (docs/7c4-...md Section 3/9's
# real-corpus validation pass).
ALGORITHM_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Pure, ORM-free source view
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class TableSourceBlock:
    """ORM-free view of one `CanonicalBlock`, in native page/block order."""

    id: uuid.UUID
    page_number: int
    block_order: int
    y0: float
    text: str


@dataclass(frozen=True)
class CellReconstruction:
    column_index: int
    raw_value: str | None
    cell_status: StructuredCellStatus
    parsed_numeric_value: float | None
    footnote_marker: str | None


@dataclass(frozen=True)
class RowReconstruction:
    position: int
    source_label: str
    normalized_identity: str
    category_label: str | None
    row_marker: str | None
    source_block_id: uuid.UUID
    page_number: int
    cells: tuple[CellReconstruction, ...]


@dataclass(frozen=True)
class FootnoteReconstruction:
    marker: str
    text: str
    page_number: int
    source_block_id: uuid.UUID


@dataclass(frozen=True)
class TableReconstructionResult:
    source_heading: str
    start_page: int
    end_page: int
    heading_block_id: uuid.UUID
    rows: tuple[RowReconstruction, ...]
    footnotes: tuple[FootnoteReconstruction, ...]
    reconstruction_status: StructuredTableReconstructionStatus
    reconstruction_confidence: AlignmentConfidence
    extraction_note: str | None


# --------------------------------------------------------------------------
# Tokenization
# --------------------------------------------------------------------------

# South-African thousand-space-grouped number, optionally decimal/percent;
# an explicit nil dash; or the literal "Waived fee"/"N/A" text values --
# the raw-string forms the source PDF itself uses to distinguish a numeric
# value from a nil/waived/not-applicable one (docs/experiments/...
# comparison.md Section 3; "N/A" confirmed directly in the real 2024 ACT
# NED table's newly-added "Special ad hoc" row, which has no current-year
# fee yet).
_TOKEN_RE = re.compile(r"–|Waived fee|N/A|\d{1,3}(?: \d{3})*(?:\.\d+)?%?")
# A line consisting only of value-shaped characters (digits, thousand
# spaces, '.', '%', dash) or the literal "Waived fee"/"N/A" -- used to
# separate row-label lines from cell-value lines without ever matching a
# digit that happens to be embedded inside a label (e.g. a footnote marker
# glued to a name, or a year mentioned inside footnote prose).
_VALUE_LINE_RE = re.compile(r"^(?:[\d\s%.,–]|Waived fee|N/A)+$")
# A footnote-marker suffix directly glued (no space) to a label or a value
# -- one or two digits, or one/two asterisks.
_TRAILING_MARKER_RE = re.compile(r"^(?P<body>.+?)(?P<marker>\*{1,2}|\d{1,2})$")
# A line starting with a footnote marker -- either the marker alone (the
# glyph emitted as its own PyMuPDF line, footnote text following on
# subsequent lines; the real ACT corpus shows one block can carry more
# than one footnote this way, e.g. two footnotes concatenated in a single
# block on the 2020 total_remuneration_outcomes page) or the marker with
# its text inline on the same line (the real 2024 total_remuneration_outcomes
# page's single-line footnote).
_FOOTNOTE_MARKER_START_RE = re.compile(
    r"^(?P<marker>\*{1,2}|\d{1,2})(?:[\s\t\x07]+(?P<inline>\S.*))?[\s\t\x07]*$"
)
# Maximum vertical (PDF points) distance below the last row a footnote
# candidate may sit -- see its use in `reconstruct_table` for the real
# corpus case this bound resolves.
_FOOTNOTE_MAX_Y_GAP = 200.0


def _normalize(text: str) -> str:
    return " ".join(normalize_apostrophes(text).strip().split()).lower()


def _clean_line(line: str) -> str:
    return unicodedata.normalize("NFKC", line).strip()


def _parse_numeric(raw: str) -> float | None:
    stripped = raw.strip().rstrip("%").replace(" ", "")
    try:
        return float(stripped)
    except ValueError:
        return None


def _classify_value(raw: str) -> tuple[StructuredCellStatus, float | None]:
    if raw == "–":
        return StructuredCellStatus.NIL_DASH, None
    if raw == "N/A":
        return StructuredCellStatus.NOT_APPLICABLE, None
    if raw == "Waived fee":
        return StructuredCellStatus.TEXT_VALUE, None
    numeric = _parse_numeric(raw)
    if numeric is None:
        return StructuredCellStatus.TEXT_VALUE, None
    if numeric == 0.0:
        return StructuredCellStatus.ZERO, 0.0
    return StructuredCellStatus.NUMERIC, numeric


def _strip_trailing_marker(text: str) -> tuple[str, str | None]:
    match = _TRAILING_MARKER_RE.match(text)
    if match is None:
        return text, None
    body = match.group("body").strip()
    if not body:
        return text, None
    return body, match.group("marker")


def _tokenize_value_line(line: str) -> list[tuple[str, str | None]]:
    """Extract cell values from one value-shaped line, splitting glued
    multi-value lines (e.g. "2 400 000 10 209 360", two space-separated
    numbers on one PDF line) and detecting a footnote-marker digit glued
    directly onto a number with no space (e.g. "1 148 9041" ->
    ("1 148 904", "1"))."""
    matches = list(_TOKEN_RE.finditer(line))
    tokens: list[tuple[str, str | None]] = []
    i = 0
    while i < len(matches):
        m = matches[i]
        value = m.group()
        marker: str | None = None
        if i + 1 < len(matches):
            nxt = matches[i + 1]
            if nxt.start() == m.end() and len(nxt.group()) <= 2 and nxt.group().isdigit():
                marker = nxt.group()
                i += 1  # consume the merged marker match
        tokens.append((value, marker))
        i += 1
    return tokens


# --------------------------------------------------------------------------
# Row/category segmentation within one block
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class _RowSegment:
    label_line: str
    value_tokens: list[tuple[str, str | None]]
    # None for a genuine row segment; the accumulated category text (joined
    # from one or more consecutive zero-value label lines -- a category
    # heading that wraps onto a second PDF line, e.g. "Audit and Risk
    # Committee  \n(per meeting)", is a real, observed case, not two
    # separate categories) when this segment carries no values of its own.
    category_text: str | None = None


def _segment_block(text: str) -> tuple[list[_RowSegment], str | None]:
    """Split one block's text into row segments. A run of one or more
    consecutive label lines with zero following value lines is one
    category (its text is their join, since a category heading can wrap
    across PDF lines, e.g. "Audit and Risk Committee  \\n(per meeting)");
    the next label line that *does* have following value lines is a row,
    tagged with that accumulated category text. Also returns any
    category text left pending at the end of the block (no row followed
    it in this block) so the caller can carry it forward to the next
    block."""
    lines = [_clean_line(line) for line in text.split("\n")]
    lines = [line for line in lines if line]

    segments: list[_RowSegment] = []
    pending_category_parts: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _VALUE_LINE_RE.fullmatch(line):
            # A value line with no preceding label in this block -- not
            # expected for a well-formed row block; skip defensively
            # rather than fabricate a row.
            i += 1
            continue
        label_line = line
        i += 1
        tokens: list[tuple[str, str | None]] = []
        while i < len(lines) and _VALUE_LINE_RE.fullmatch(lines[i]):
            tokens.extend(_tokenize_value_line(lines[i]))
            i += 1
        if not tokens:
            pending_category_parts.append(label_line)
            continue
        category_text = " ".join(pending_category_parts) if pending_category_parts else None
        pending_category_parts = []
        segments.append(_RowSegment(label_line=label_line, value_tokens=tokens, category_text=category_text))

    trailing_category = " ".join(pending_category_parts) if pending_category_parts else None
    return segments, trailing_category


def _build_cells(tokens: list[tuple[str, str | None]], config: TableFamilyConfig) -> tuple[CellReconstruction, ...]:
    cells: list[CellReconstruction] = []
    for idx in range(config.expected_column_count):
        if idx < len(tokens):
            raw, marker = tokens[idx]
            status, numeric = _classify_value(raw)
            cells.append(
                CellReconstruction(
                    column_index=idx, raw_value=raw, cell_status=status,
                    parsed_numeric_value=numeric, footnote_marker=marker,
                )
            )
        else:
            cells.append(
                CellReconstruction(
                    column_index=idx, raw_value=None, cell_status=StructuredCellStatus.MISSING,
                    parsed_numeric_value=None, footnote_marker=None,
                )
            )
    return tuple(cells)


def _looks_like_footnote_block(text: str) -> bool:
    lines = [line.strip("\r") for line in text.split("\n") if line.strip()]
    return bool(lines) and bool(_FOOTNOTE_MARKER_START_RE.match(lines[0]))


def _parse_footnotes_in_block(text: str) -> list[tuple[str, str]]:
    """Split one block into one or more (marker, text) footnotes -- a
    block can carry more than one footnote, and a footnote's text can
    either follow its marker inline on the same line or on subsequent
    lines (see `_FOOTNOTE_MARKER_START_RE` docstring)."""
    results: list[tuple[str, str]] = []
    current_marker: str | None = None
    current_parts: list[str] = []
    for raw_line in text.split("\n"):
        # \x07 (BEL) shows up as PDF rendering noise around a footnote
        # marker in the real ACT corpus (a broken bullet/tab-stop glyph,
        # not a whitespace character by Python's own `str.strip()`/`\s`
        # semantics) -- strip it explicitly so it never leaks into
        # persisted footnote text.
        line = raw_line.strip("\r").replace("\x07", "")
        marker_match = _FOOTNOTE_MARKER_START_RE.match(line)
        if marker_match:
            if current_marker is not None and current_parts:
                results.append((current_marker, " ".join(" ".join(current_parts).split())))
            current_marker = marker_match.group("marker")
            current_parts = []
            inline = marker_match.group("inline")
            if inline:
                current_parts.append(inline.strip())
        else:
            cleaned = line.strip()
            if cleaned:
                current_parts.append(cleaned)
    if current_marker is not None and current_parts:
        results.append((current_marker, " ".join(" ".join(current_parts).split())))
    return results


_TRAILING_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\*?\s*$")
# "Chairperson" <-> "Chairman" is a title-convention change, not a role
# change, confirmed directly across the real ACT NED table corpus (e.g.
# Audit and Risk Committee uses "Chairperson" 2020-2022, "Chairman"
# 2023-2024, for what is otherwise the same committee seat) -- the
# research doc's own row-alignment table treats these as one role
# (docs/experiments/annual-report-structured-table-comparison.md Section
# 7.1's "Chairperson/Chairman" notation).
_CHAIR_TITLE_VARIANTS = {"chairperson", "chairman"}
# A committee/category renamed cosmetically across the real ACT corpus --
# "Subsidiary board" -> "Subsidiary board/committee" starting 2024, the
# same committee per the research doc's own acknowledgment
# (docs/experiments/annual-report-structured-table-comparison.md Section
# 7.1: "2024 category renamed 'Subsidiary board/committee,' same role").
# Keyed/valued by the post-paren-strip, lowercased form.
_CATEGORY_ALIASES = {"subsidiary board/committee": "subsidiary board"}


def _canonical_role_category(category_label: str) -> str:
    """Strip a leading footnote-marker asterisk (a real, observed case:
    the 2023 ACT NED table glues its ICT Steering Committee footnote
    marker to the *front* of the category text, unlike every other
    footnoted category/row in this corpus, which glues it to the role
    label) and a trailing parenthetical fee-basis qualifier (e.g. "(per
    meeting)" vs "(per annum)", "(annualised retainer fee)" vs
    "(annualised retainer fee*)") -- a real, observed cosmetic drift
    across the ACT NED table corpus for the same committee. Then applies
    `_CATEGORY_ALIASES` for the one further known cosmetic rename."""
    stripped = category_label.lstrip("*").strip()
    normalized = _normalize(_TRAILING_PARENTHETICAL_RE.sub("", stripped))
    return _CATEGORY_ALIASES.get(normalized, normalized)


def _canonical_role(source_label: str) -> str:
    normalized = _normalize(source_label)
    return "chair" if normalized in _CHAIR_TITLE_VARIANTS else normalized


def _row_identity(config, category_label: str | None, source_label: str) -> str:
    if config.row_identity_type == StructuredRowIdentityType.ROLE:
        # Category disambiguates which committee a role belongs to (two
        # different committees both have a "Member" row) -- essential here.
        role = _canonical_role(source_label)
        if category_label:
            return f"{_canonical_role_category(category_label)}::{role}"
        return role
    # PERSON identity: a name is unique on its own, and category is not
    # load-bearing for identity here (brief Section 9: person-based, not
    # category-qualified) -- deliberately never included. A real corpus
    # case confirms this matters beyond tidiness: the 2023 ACT
    # total_remuneration_outcomes page's column-header fragments ("STI and
    # Retention Awards" / "LTI") sit close enough to the row-data blocks
    # that this parser's cross-block category-carry state picks up
    # "Awards LTI" as a spurious category just before the real data rows,
    # which would silently break every person's cross-year row match if
    # category were part of the identity.
    return _normalize(source_label)


def _within_table_region(block: TableSourceBlock, heading: TableSourceBlock) -> bool:
    """Guards against two real, observed hazards.

    (1) PyMuPDF's native block emission order is not strictly top-to-bottom
    (7C.1a's own docstring notes this for multi-column layouts; this corpus
    shows it can also happen on a single-column page when two unrelated
    tables/footnotes share one page). On the real ACT 2020 NED-table page,
    an unrelated footnote for a different table is emitted *after* this
    table's own footnote despite being positioned well above this table's
    heading -- excluded by requiring same-page candidates to sit at or
    below the heading.

    (2) Every one of the 10 validated ACT table-years fits on a single
    page (docs/experiments/annual-report-structured-table-comparison.md
    Section 2) -- a next-page block is therefore never this table's own
    content. Crossing a page boundary is out of scope for this milestone
    (docs/7c4-...md caveats: a page-break-spanning row is untested).

    (3) ACT's own running header/footer ("AFROCENTRIC GROUP ...",
    "... INTEGRATED REPORT ...", each paired with a bare page number) sits
    on the *same* page as the heading, below all real content, so (1)/(2)
    alone do not exclude it -- observed directly reading as a spurious
    one-value row ("AFROCENTRIC GROUP" :: "98"). Excluded by literal
    substring match; this is intentionally ACT-specific, per the
    milestone's own "family-configured, not universal" scope."""
    if block.page_number != heading.page_number or block.y0 < heading.y0:
        return False
    normalized = _normalize(block.text)
    return "afrocentric group" not in normalized and "integrated report" not in normalized


def reconstruct_table(
    blocks: list[TableSourceBlock], config: TableFamilyConfig
) -> TableReconstructionResult | None:
    """Deterministically reconstruct one structured table.

    Returns `None` -- no row created -- if `config.heading_pattern` never
    matches any block, mirroring `semantic_unit_extraction.extract_unit`'s
    "no match, no row" discipline.
    """
    ordered = sorted(blocks, key=lambda b: (b.page_number, b.block_order))

    heading_block: TableSourceBlock | None = None
    for b in ordered:
        if config.heading_pattern.search(normalize_apostrophes(b.text)):
            heading_block = b
            break
    if heading_block is None:
        return None

    rows: list[RowReconstruction] = []
    footnotes: list[FootnoteReconstruction] = []
    category_label: str | None = None
    terminal_reached = False
    notes: list[str] = []

    # Region-filtered by `_within_table_region` (same page, y0 >=
    # heading's y0), but still ordered by native `block_order`, never y0:
    # a real, observed hazard on the 2024 ACT total_remuneration_outcomes
    # page (a wide/landscape table layout) emits the row-data blocks
    # *before* the heading block in native PyMuPDF order despite them
    # being visually below it -- `block_order > heading.block_order` would
    # wrongly exclude them, but they are still *internally* self-consistent
    # in native order, so simply widening the filter (rather than
    # resorting by y0) is enough. y0-sorting was tried and reverted: it
    # breaks a different real page (2024's NED table, a genuine two-column
    # layout where a category-label block's y0 can be a point or two
    # *greater* than its own row-data block's y0, interleaving unrelated
    # column-header fragments between them) -- exactly the multi-column
    # corruption 7C.1a's own docstring warns a y-sort causes.
    candidates = sorted(
        (b for b in ordered if b.id != heading_block.id and _within_table_region(b, heading_block)),
        key=lambda b: b.block_order,
    )

    last_row_y0: float | None = None

    for block in candidates:
        # Footnotes are collected in a separate pass below -- skip a
        # footnote-looking block here without stopping row scanning (a
        # footnote can be separated from its row/terminal-row block by
        # unrelated prose, e.g. the real 2024 ACT total_remuneration_outcomes
        # page interposes an "STI performance outcomes" narrative section
        # between the TOTAL row and its own footnote).
        if _looks_like_footnote_block(block.text):
            continue

        if terminal_reached:
            break

        segments, trailing_category = _segment_block(block.text)
        for segment in segments:
            if segment.category_text is not None:
                category_label = segment.category_text

            label, row_marker = _strip_trailing_marker(segment.label_line)
            if not any(c.isalpha() for c in label):
                # Not a genuine row label -- every real row label in both
                # configured families is a role or person name (always
                # contains letters). A purely-numeric "label" is a
                # misfired column-header fragment (real corpus case: the
                # 2024 ACT total_remuneration_outcomes page's "2024*
                # \n2023\n2024\n..." year-header block, positioned inside
                # this table's own region, glued together like a row by
                # this parser's own label+values heuristic). Skip it
                # without creating a spurious row.
                notes.append(
                    f"segment on page {block.page_number} with non-alphabetic label {segment.label_line!r} "
                    f"skipped -- not a genuine row"
                )
                continue

            cells = _build_cells(segment.value_tokens, config)
            if len(segment.value_tokens) > config.expected_column_count:
                notes.append(
                    f"row {label!r} on page {block.page_number} has {len(segment.value_tokens)} values, "
                    f"expected {config.expected_column_count} -- extra values dropped"
                )
            rows.append(
                RowReconstruction(
                    position=len(rows), source_label=label,
                    normalized_identity=_row_identity(config, category_label, label),
                    category_label=category_label, row_marker=row_marker,
                    source_block_id=block.id, page_number=block.page_number, cells=cells,
                )
            )
            if config.terminal_row_label is not None and label.strip().upper() == config.terminal_row_label:
                terminal_reached = True
                break

        if segments:
            last_row_y0 = block.y0

        if trailing_category is not None:
            category_label = trailing_category

        if not segments and trailing_category is None:
            # Neither a row nor a recognizable category label, and not a
            # footnote (skipped above) -- this block is outside the table.
            if not rows:
                continue
            break

    if rows and last_row_y0 is not None:
        # Separate pass, independent of where row scanning stopped (see
        # the loop above's comment on the 2024 ACT interposed-prose case).
        # Bounded to blocks within _FOOTNOTE_MAX_Y_GAP of the last row: a
        # real footnote is always close to its table (the real 2024 ACT
        # total_remuneration_outcomes footnote sits ~130pt below its TOTAL
        # row, across a short "STI performance outcomes" preamble) --
        # unbounded scanning produces a false positive on the real 2023
        # page, where an unrelated later "Management strategic incentive
        # scheme" scorecard table (~365pt further down the same page)
        # contains a "3\nout of 5\n..." line that itself looks like a
        # footnote-marker start.
        for block in candidates:
            if not _looks_like_footnote_block(block.text):
                continue
            if block.y0 - last_row_y0 > _FOOTNOTE_MAX_Y_GAP:
                continue
            for marker, footnote_text in _parse_footnotes_in_block(block.text):
                footnotes.append(
                    FootnoteReconstruction(
                        marker=marker, text=footnote_text, page_number=block.page_number, source_block_id=block.id,
                    )
                )

    if not rows:
        return TableReconstructionResult(
            source_heading=heading_block.text.strip(), start_page=heading_block.page_number,
            end_page=heading_block.page_number, heading_block_id=heading_block.id, rows=(), footnotes=(),
            reconstruction_status=StructuredTableReconstructionStatus.MAJOR_LAYOUT_RECONSTRUCTION_NEEDED,
            reconstruction_confidence=AlignmentConfidence.NEEDS_REVIEW,
            extraction_note="heading matched but no row blocks were recognized after it",
        )

    end_page = max([r.page_number for r in rows] + [f.page_number for f in footnotes])
    status = (
        StructuredTableReconstructionStatus.CLEAN if not notes
        else StructuredTableReconstructionStatus.MINOR_CORRECTION_NEEDED
    )
    confidence = AlignmentConfidence.HIGH if not notes else AlignmentConfidence.MEDIUM
    return TableReconstructionResult(
        source_heading=heading_block.text.strip(), start_page=heading_block.page_number, end_page=end_page,
        heading_block_id=heading_block.id, rows=tuple(rows), footnotes=tuple(footnotes),
        reconstruction_status=status, reconstruction_confidence=confidence,
        extraction_note="; ".join(notes) if notes else None,
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def compute_configuration_hash(configs: tuple[TableFamilyConfig, ...] = TABLE_FAMILY_CONFIGS) -> str:
    from market_documents.services.structured_table_config import compute_configuration_hash as _config_hash

    payload = {"algorithm_version": ALGORITHM_VERSION, "config_hash": _config_hash(configs)}
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_current_extraction_run(
    session: Session, report_id: uuid.UUID, table_family_key: str
) -> StructuredTableExtractionRun | None:
    return session.scalars(
        select(StructuredTableExtractionRun)
        .where(
            StructuredTableExtractionRun.report_id == report_id,
            StructuredTableExtractionRun.table_family_key == table_family_key,
            StructuredTableExtractionRun.status.in_(
                (StructuredTableExtractionRunStatus.COMPLETED, StructuredTableExtractionRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(StructuredTableExtractionRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class TableExtractionOutcome:
    report_id: uuid.UUID
    table_family_key: str
    run: StructuredTableExtractionRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def run_table_reconstruction(
    session: Session, report: Report, table_family_key: str, *, force: bool = False
) -> TableExtractionOutcome:
    """Reconstruct one configured table family for one report's current
    successful canonical extraction.

    Eligibility requires a current successful `CanonicalExtractionRun` and a
    `TableFamilyConfig` for (report.company.ticker, table_family_key).
    Deliberately does **not** depend on schedule localization: REMUNERATION
    is not configured in `schedule_config.py` (only FINANCIAL_PERFORMANCE
    is, per 7C.1's own scope), and this milestone must not reopen that
    mechanism. `TableFamilyConfig.heading_pattern` is itself the
    localization step, scanned across the report's whole canonical
    document (see `structured_table.StructuredTableExtractionRun`'s
    docstring). Skips (returning the existing run) if the current
    successful extraction already used an identical source canonical run
    and configuration, unless `force`.
    """
    config = table_family_config_for_key(table_family_key)
    if config is None or config.ticker != report.company.ticker:
        return TableExtractionOutcome(
            report_id=report.id, table_family_key=table_family_key, run=None, ineligible=True,
            ineligible_reason=f"no TableFamilyConfig for ({report.company.ticker!r}, {table_family_key!r})",
        )

    canonical_run = get_current_canonical_run(session, report.id)
    if canonical_run is None:
        return TableExtractionOutcome(
            report_id=report.id, table_family_key=table_family_key, run=None, ineligible=True,
            ineligible_reason="report has no current successful canonical extraction run",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_extraction_run(session, report.id, table_family_key)
    if (
        current_run is not None and not force
        and current_run.canonical_run_id == canonical_run.id
        and current_run.configuration_hash == configuration_hash
    ):
        return TableExtractionOutcome(
            report_id=report.id, table_family_key=table_family_key, run=current_run, skipped=True,
            skip_reason="identical successful extraction run already exists",
        )

    run = StructuredTableExtractionRun(
        report_id=report.id, canonical_run_id=canonical_run.id,
        table_family_key=table_family_key, algorithm_version=ALGORITHM_VERSION, configuration_hash=configuration_hash,
        status=StructuredTableExtractionRunStatus.RUNNING, started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_table_reconstruction(session, report, config, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = StructuredTableExtractionRunStatus.FAILED
        run.error_message = f"structured table reconstruction failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception(
            "structured table reconstruction failed for %s (%s)", report.local_path, table_family_key
        )

    session.flush()
    return TableExtractionOutcome(report_id=report.id, table_family_key=table_family_key, run=run)


def _run_table_reconstruction(
    session: Session, report: Report, config: TableFamilyConfig, run: StructuredTableExtractionRun,
) -> None:
    page_rows = session.execute(
        select(CanonicalPage.id, CanonicalPage.page_number).where(
            CanonicalPage.canonical_run_id == run.canonical_run_id,
        )
    ).all()
    page_number_by_id = {row.id: row.page_number for row in page_rows}

    canonical_blocks = session.scalars(
        select(CanonicalBlock).where(CanonicalBlock.page_id.in_(page_number_by_id.keys()))
    ).all()
    source_blocks = [
        TableSourceBlock(
            id=b.id, page_number=page_number_by_id[b.page_id], block_order=b.block_order, y0=b.y0, text=b.raw_text,
        )
        for b in canonical_blocks
    ]

    result = reconstruct_table(source_blocks, config)
    notes: list[str] = []
    if result is None:
        notes.append(f"{config.table_family_key}: heading pattern {config.heading_pattern.pattern!r} not found -- no table created")
    else:
        table = StructuredTable(
            structured_table_extraction_run_id=run.id, report_id=report.id, table_family_key=config.table_family_key,
            schedule=config.schedule, source_heading=result.source_heading, start_page=result.start_page,
            end_page=result.end_page, table_shape=StructuredTableShape.RECTANGULAR_MATRIX,
            row_identity_type=config.row_identity_type, analytical_mode=config.analytical_mode,
            unit_of_measure=None, reconstruction_status=result.reconstruction_status,
            reconstruction_confidence=result.reconstruction_confidence, extraction_note=result.extraction_note,
        )
        session.add(table)
        session.flush()

        columns: list[StructuredTableColumn] = []
        for position, entry in enumerate(config.column_schema):
            year_ref = report.directory_year + entry.year_offset if entry.year_offset is not None else None
            column = StructuredTableColumn(
                structured_table_id=table.id, position=position, source_label=None,
                normalized_key=entry.normalized_key, group_label=entry.group_label, year_ref=year_ref,
                unit_or_currency=entry.unit_or_currency, is_restated=entry.is_restated, source_block_id=None,
            )
            session.add(column)
            columns.append(column)
        session.flush()

        row_id_by_position: dict[int, uuid.UUID] = {}
        for row_result in result.rows:
            row = StructuredTableRow(
                structured_table_id=table.id, position=row_result.position, source_label=row_result.source_label,
                normalized_identity=row_result.normalized_identity, category_label=row_result.category_label,
                row_marker=row_result.row_marker, source_block_id=row_result.source_block_id,
            )
            session.add(row)
            session.flush()
            row_id_by_position[row_result.position] = row.id

            for cell_result in row_result.cells:
                session.add(
                    StructuredTableCell(
                        structured_table_row_id=row.id, structured_table_column_id=columns[cell_result.column_index].id,
                        raw_value=cell_result.raw_value, parsed_numeric_value=cell_result.parsed_numeric_value,
                        cell_status=cell_result.cell_status, currency_or_unit=None,
                        footnote_marker=cell_result.footnote_marker,
                    )
                )

        for footnote_result in result.footnotes:
            session.add(
                StructuredTableFootnote(
                    structured_table_id=table.id, marker=footnote_result.marker, text=footnote_result.text,
                    page=footnote_result.page_number, source_block_id=footnote_result.source_block_id,
                )
            )

        if result.reconstruction_status != StructuredTableReconstructionStatus.CLEAN:
            notes.append(f"{config.table_family_key}: {result.reconstruction_status.value} -- {result.extraction_note}")

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = (
        StructuredTableExtractionRunStatus.COMPLETED if not notes
        else StructuredTableExtractionRunStatus.COMPLETED_WITH_WARNINGS
    )

"""Cross-year structured-table alignment and value-diff: deterministic row/
column correspondence matching and explicit value-change events (Track
7C.4, docs/7c4-structured-table-comparison.md).

Answers "which row/column in the later report's reconstructed table
corresponds to which row/column in the earlier report's" and, for
comparable aligned cells, "how did the value change" -- never re-derives
reconstruction (7C.4's own `structured_table_reconstruction` module) and
never merges two genuinely different row identities (a departure + a new
hire are always REMOVED + ADDED, per docs/7c4-...md Section 13).
"""

import hashlib
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    AlignmentConfidence,
    StructuredCellStatus,
    StructuredColumnAlignmentStatus,
    StructuredComparabilityStatus,
    StructuredRowAlignmentStatus,
    StructuredTableAlignmentRunStatus,
    StructuredValueChangeEventType,
)
from market_documents.models.report_pair import ReportPair
from market_documents.models.structured_table import (
    StructuredColumnAlignment,
    StructuredRowAlignment,
    StructuredTable,
    StructuredTableAlignmentRun,
    StructuredTableCell,
    StructuredTableColumn,
    StructuredTableExtractionRun,
    StructuredTableRow,
    StructuredValueChangeEvent,
)
from market_documents.services.structured_table_config import (
    TABLE_FAMILY_CONFIGS,
    TableFamilyConfig,
    compute_configuration_hash as _table_config_hash,
    schema_change_for,
    table_family_config_for_key,
)
from market_documents.services.structured_table_reconstruction import get_current_extraction_run

logger = logging.getLogger(__name__)

# v1.0.0 = initial deterministic row/column alignment (exact normalized
# identity match; no succession inference) and value-diff.
ALGORITHM_VERSION = "1.0.0"


# --------------------------------------------------------------------------
# Pure data structures and algorithm
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class RowCandidate:
    id: uuid.UUID
    position: int
    normalized_identity: str
    cell_statuses: tuple[StructuredCellStatus, ...]  # one per column position, for COMPARATIVE_ONLY detection


@dataclass(frozen=True)
class ColumnCandidate:
    id: uuid.UUID
    position: int
    normalized_key: str
    # `normalized_key` alone is not unique within a table for families
    # whose schema repeats one metric across a current-year and a prior-
    # year-restated column (e.g. total_remuneration_outcomes' base_pay
    # appears twice, year_offset 0 and -1) -- alignment identity must be
    # the pair, or the current/restated columns collide in a plain
    # key->column dict and half of them are silently dropped.
    is_restated: bool

    @property
    def alignment_key(self) -> tuple[str, bool]:
        return (self.normalized_key, self.is_restated)


@dataclass(frozen=True)
class RowAlignmentDecision:
    earlier_row_id: uuid.UUID | None
    later_row_id: uuid.UUID | None
    status: StructuredRowAlignmentStatus
    confidence: AlignmentConfidence
    evidence: str


@dataclass(frozen=True)
class ColumnAlignmentDecision:
    earlier_column_id: uuid.UUID | None
    later_column_id: uuid.UUID | None
    status: StructuredColumnAlignmentStatus
    comparability_status: StructuredComparabilityStatus
    confidence: AlignmentConfidence
    evidence: str


def _all_missing(statuses: tuple[StructuredCellStatus, ...]) -> bool:
    return all(s in (StructuredCellStatus.MISSING, StructuredCellStatus.NIL_DASH) for s in statuses) if statuses else False


def align_rows(earlier: list[RowCandidate], later: list[RowCandidate]) -> list[RowAlignmentDecision]:
    """Exact match on `normalized_identity` -- a departed individual and a
    newly-added individual are always two separate ADDED/REMOVED edges,
    never merged into one comparison subject (no succession inference in
    this milestone, per docs/7c4-...md Section 13)."""
    earlier_by_identity = {r.normalized_identity: r for r in earlier}
    later_by_identity = {r.normalized_identity: r for r in later}

    decisions: list[RowAlignmentDecision] = []
    for identity, e_row in earlier_by_identity.items():
        l_row = later_by_identity.get(identity)
        if l_row is None:
            decisions.append(
                RowAlignmentDecision(
                    earlier_row_id=e_row.id, later_row_id=None, status=StructuredRowAlignmentStatus.REMOVED,
                    confidence=AlignmentConfidence.HIGH,
                    evidence=f"row {identity!r} present in earlier table, absent from later table",
                )
            )
            continue

        # Present both sides -- distinguish a genuine ongoing match from
        # the transition-year "current-side nil, other-side real values"
        # pattern (docs/7c4-...md Section 9/13).
        if _all_missing(l_row.cell_statuses) and not _all_missing(e_row.cell_statuses):
            decisions.append(
                RowAlignmentDecision(
                    earlier_row_id=e_row.id, later_row_id=l_row.id, status=StructuredRowAlignmentStatus.COMPARATIVE_ONLY,
                    confidence=AlignmentConfidence.HIGH,
                    evidence=f"row {identity!r} has no current-side values in the later table but real earlier-side values",
                )
            )
        else:
            decisions.append(
                RowAlignmentDecision(
                    earlier_row_id=e_row.id, later_row_id=l_row.id, status=StructuredRowAlignmentStatus.MATCHED,
                    confidence=AlignmentConfidence.HIGH, evidence=f"row {identity!r} present in both tables",
                )
            )

    for identity, l_row in later_by_identity.items():
        if identity not in earlier_by_identity:
            decisions.append(
                RowAlignmentDecision(
                    earlier_row_id=None, later_row_id=l_row.id, status=StructuredRowAlignmentStatus.ADDED,
                    confidence=AlignmentConfidence.HIGH,
                    evidence=f"row {identity!r} present in later table, absent from earlier table",
                )
            )

    return decisions


def align_columns(
    earlier: list[ColumnCandidate], later: list[ColumnCandidate], config: TableFamilyConfig,
    earlier_year: int, later_year: int,
) -> list[ColumnAlignmentDecision]:
    """Match on `normalized_key` -- constant across years by construction
    (the reconstruction step assigns semantic keys from the family's fixed
    `column_schema`, not parsed from drifting printed labels). Comparability
    defaults to DIRECTLY_COMPARABLE unless the config declares a known,
    source-confirmed schema change for this transition (never inferred --
    docs/7c4-...md Section 8/14)."""
    earlier_by_key = {c.alignment_key: c for c in earlier}
    later_by_key = {c.alignment_key: c for c in later}

    decisions: list[ColumnAlignmentDecision] = []
    for key, e_col in earlier_by_key.items():
        l_col = later_by_key.get(key)
        if l_col is None:
            decisions.append(
                ColumnAlignmentDecision(
                    earlier_column_id=e_col.id, later_column_id=None, status=StructuredColumnAlignmentStatus.REMOVED,
                    comparability_status=StructuredComparabilityStatus.NOT_COMPARABLE, confidence=AlignmentConfidence.HIGH,
                    evidence=f"column {key!r} present in earlier table, absent from later table",
                )
            )
            continue

        change = schema_change_for(config, key[0], earlier_year, later_year)
        if change is not None:
            decisions.append(
                ColumnAlignmentDecision(
                    earlier_column_id=e_col.id, later_column_id=l_col.id, status=StructuredColumnAlignmentStatus.MATCHED,
                    comparability_status=StructuredComparabilityStatus.PARTIALLY_COMPARABLE_SCHEMA_CHANGED,
                    confidence=AlignmentConfidence.HIGH, evidence=change.reason,
                )
            )
        else:
            decisions.append(
                ColumnAlignmentDecision(
                    earlier_column_id=e_col.id, later_column_id=l_col.id, status=StructuredColumnAlignmentStatus.MATCHED,
                    comparability_status=StructuredComparabilityStatus.DIRECTLY_COMPARABLE,
                    confidence=AlignmentConfidence.HIGH, evidence=f"column {key!r} stable in both tables",
                )
            )

    for key, l_col in later_by_key.items():
        if key not in earlier_by_key:
            decisions.append(
                ColumnAlignmentDecision(
                    earlier_column_id=None, later_column_id=l_col.id, status=StructuredColumnAlignmentStatus.ADDED,
                    comparability_status=StructuredComparabilityStatus.NOT_COMPARABLE, confidence=AlignmentConfidence.HIGH,
                    evidence=f"column {key!r} present in later table, absent from earlier table",
                )
            )

    return decisions


@dataclass(frozen=True)
class CellView:
    id: uuid.UUID
    raw_value: str | None
    cell_status: StructuredCellStatus
    parsed_numeric_value: float | None


def classify_value_change(
    earlier: CellView | None, later: CellView | None, row_status: StructuredRowAlignmentStatus,
    comparability: StructuredComparabilityStatus,
) -> tuple[StructuredValueChangeEventType, float | None, float | None]:
    """Classify one aligned (row, column) cell pair. Returns
    (event_type, absolute_change, pct_change) -- both change fields NULL
    whenever undefined (brief Section 15): non-numeric either side, zero
    denominator, or a non-comparable schema/row state."""
    if row_status == StructuredRowAlignmentStatus.COMPARATIVE_ONLY:
        return StructuredValueChangeEventType.COMPARATIVE_ONLY, None, None
    if row_status == StructuredRowAlignmentStatus.PARTIAL_YEAR:
        return StructuredValueChangeEventType.PARTIAL_YEAR, None, None
    if comparability == StructuredComparabilityStatus.PARTIALLY_COMPARABLE_SCHEMA_CHANGED:
        return StructuredValueChangeEventType.SCHEMA_CHANGED, None, None
    if comparability == StructuredComparabilityStatus.NOT_COMPARABLE or earlier is None or later is None:
        return StructuredValueChangeEventType.VALUE_NOT_COMPARABLE, None, None

    e_status, l_status = earlier.cell_status, later.cell_status
    e_num, l_num = earlier.parsed_numeric_value, later.parsed_numeric_value

    if e_status == StructuredCellStatus.MISSING and l_status != StructuredCellStatus.MISSING:
        return StructuredValueChangeEventType.MISSING_TO_VALUE, None, None
    if e_status != StructuredCellStatus.MISSING and l_status == StructuredCellStatus.MISSING:
        return StructuredValueChangeEventType.VALUE_TO_MISSING, None, None
    if e_status == StructuredCellStatus.NIL_DASH and l_status not in (StructuredCellStatus.NIL_DASH, StructuredCellStatus.MISSING):
        return StructuredValueChangeEventType.NIL_TO_VALUE, None, None
    if e_status not in (StructuredCellStatus.NIL_DASH, StructuredCellStatus.MISSING) and l_status == StructuredCellStatus.NIL_DASH:
        return StructuredValueChangeEventType.VALUE_TO_NIL, None, None
    if e_status == StructuredCellStatus.ZERO and l_status == StructuredCellStatus.NUMERIC:
        return StructuredValueChangeEventType.ZERO_TO_VALUE, None, None
    if e_status == StructuredCellStatus.NUMERIC and l_status == StructuredCellStatus.ZERO:
        return StructuredValueChangeEventType.VALUE_TO_ZERO, None, None

    if e_status == StructuredCellStatus.NUMERIC and l_status == StructuredCellStatus.NUMERIC:
        absolute = l_num - e_num
        pct = (absolute / e_num) if e_num not in (None, 0.0) else None
        if absolute == 0:
            return StructuredValueChangeEventType.VALUE_UNCHANGED, 0.0, (0.0 if pct is not None else None)
        event = StructuredValueChangeEventType.VALUE_INCREASED if absolute > 0 else StructuredValueChangeEventType.VALUE_DECREASED
        return event, absolute, pct

    if e_status == l_status:
        return StructuredValueChangeEventType.VALUE_UNCHANGED, None, None

    return StructuredValueChangeEventType.VALUE_NOT_COMPARABLE, None, None


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def compute_configuration_hash() -> str:
    payload = {"algorithm_version": ALGORITHM_VERSION, "table_config_hash": _table_config_hash(TABLE_FAMILY_CONFIGS)}
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_current_alignment_run(
    session: Session, report_pair_id: uuid.UUID, table_family_key: str
) -> StructuredTableAlignmentRun | None:
    return session.scalars(
        select(StructuredTableAlignmentRun)
        .where(
            StructuredTableAlignmentRun.report_pair_id == report_pair_id,
            StructuredTableAlignmentRun.table_family_key == table_family_key,
            StructuredTableAlignmentRun.status.in_(
                (StructuredTableAlignmentRunStatus.COMPLETED, StructuredTableAlignmentRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(StructuredTableAlignmentRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class TableAlignmentOutcome:
    report_pair_id: uuid.UUID
    table_family_key: str
    run: StructuredTableAlignmentRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def run_table_comparison(
    session: Session, report_pair: ReportPair, table_family_key: str, *, force: bool = False
) -> TableAlignmentOutcome:
    """Align one table family's rows/columns across one adjacent-year
    `ReportPair` and persist value-change events.

    Eligibility requires a current successful `StructuredTableExtractionRun`
    for both the earlier and later report that produced a `StructuredTable`
    row (extraction can succeed with zero tables if the heading never
    matched -- that is not eligible for comparison).
    """
    config = table_family_config_for_key(table_family_key)
    if config is None:
        return TableAlignmentOutcome(
            report_pair_id=report_pair.id, table_family_key=table_family_key, run=None, ineligible=True,
            ineligible_reason=f"no TableFamilyConfig for {table_family_key!r}",
        )

    earlier_extraction = get_current_extraction_run(session, report_pair.earlier_report_id, table_family_key)
    later_extraction = get_current_extraction_run(session, report_pair.later_report_id, table_family_key)
    if earlier_extraction is None or later_extraction is None:
        return TableAlignmentOutcome(
            report_pair_id=report_pair.id, table_family_key=table_family_key, run=None, ineligible=True,
            ineligible_reason=f"no current successful {table_family_key} extraction run on both sides",
        )

    earlier_table = session.scalar(
        select(StructuredTable).where(StructuredTable.structured_table_extraction_run_id == earlier_extraction.id)
    )
    later_table = session.scalar(
        select(StructuredTable).where(StructuredTable.structured_table_extraction_run_id == later_extraction.id)
    )
    if earlier_table is None or later_table is None:
        return TableAlignmentOutcome(
            report_pair_id=report_pair.id, table_family_key=table_family_key, run=None, ineligible=True,
            ineligible_reason=f"{table_family_key} was not reconstructed (heading not found) on one or both sides",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_alignment_run(session, report_pair.id, table_family_key)
    if (
        current_run is not None and not force
        and current_run.earlier_structured_table_extraction_run_id == earlier_extraction.id
        and current_run.later_structured_table_extraction_run_id == later_extraction.id
        and current_run.configuration_hash == configuration_hash
    ):
        return TableAlignmentOutcome(
            report_pair_id=report_pair.id, table_family_key=table_family_key, run=current_run, skipped=True,
            skip_reason="identical successful alignment run already exists",
        )

    run = StructuredTableAlignmentRun(
        report_pair_id=report_pair.id, table_family_key=table_family_key,
        earlier_structured_table_extraction_run_id=earlier_extraction.id,
        later_structured_table_extraction_run_id=later_extraction.id,
        algorithm_version=ALGORITHM_VERSION, configuration_hash=configuration_hash,
        status=StructuredTableAlignmentRunStatus.RUNNING, started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_table_comparison(session, report_pair, earlier_table, later_table, config, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = StructuredTableAlignmentRunStatus.FAILED
        run.error_message = f"structured table comparison failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("structured table comparison failed for pair=%s family=%s", report_pair.id, table_family_key)

    session.flush()
    return TableAlignmentOutcome(report_pair_id=report_pair.id, table_family_key=table_family_key, run=run)


def _run_table_comparison(
    session: Session, report_pair: ReportPair, earlier_table: StructuredTable, later_table: StructuredTable,
    config: TableFamilyConfig, run: StructuredTableAlignmentRun,
) -> None:
    earlier_rows_orm = session.scalars(
        select(StructuredTableRow).where(StructuredTableRow.structured_table_id == earlier_table.id)
    ).all()
    later_rows_orm = session.scalars(
        select(StructuredTableRow).where(StructuredTableRow.structured_table_id == later_table.id)
    ).all()
    earlier_columns_orm = session.scalars(
        select(StructuredTableColumn).where(StructuredTableColumn.structured_table_id == earlier_table.id)
    ).all()
    later_columns_orm = session.scalars(
        select(StructuredTableColumn).where(StructuredTableColumn.structured_table_id == later_table.id)
    ).all()
    all_cells = session.scalars(
        select(StructuredTableCell).where(
            StructuredTableCell.structured_table_row_id.in_(
                [r.id for r in earlier_rows_orm] + [r.id for r in later_rows_orm]
            )
        )
    ).all()
    cells_by_row: dict[uuid.UUID, dict[uuid.UUID, StructuredTableCell]] = {}
    for cell in all_cells:
        cells_by_row.setdefault(cell.structured_table_row_id, {})[cell.structured_table_column_id] = cell

    def _row_candidate(row: StructuredTableRow) -> RowCandidate:
        row_cells = cells_by_row.get(row.id, {})
        # Only non-restated (current-year) columns drive the
        # MATCHED-vs-COMPARATIVE_ONLY distinction: a row whose *restated*
        # (prior-year comparative) columns still carry real figures would
        # otherwise never look "all missing," even in the exact
        # departure-in-progress case this distinction exists to catch
        # (real corpus: W Britz/S Mmakau's 2023 total_remuneration_outcomes
        # row -- every current-year cell is a dash, but the restated
        # columns still show real 2022 figures).
        table_columns = earlier_columns_orm if row.structured_table_id == earlier_table.id else later_columns_orm
        statuses = tuple(
            row_cells[c.id].cell_status if c.id in row_cells else StructuredCellStatus.MISSING
            for c in sorted(table_columns, key=lambda c: c.position)
            if not c.is_restated
        )
        return RowCandidate(id=row.id, position=row.position, normalized_identity=row.normalized_identity, cell_statuses=statuses)

    earlier_rows = [_row_candidate(r) for r in earlier_rows_orm]
    later_rows = [_row_candidate(r) for r in later_rows_orm]
    row_decisions = align_rows(earlier_rows, later_rows)

    earlier_columns = [
        ColumnCandidate(id=c.id, position=c.position, normalized_key=c.normalized_key, is_restated=c.is_restated)
        for c in earlier_columns_orm
    ]
    later_columns = [
        ColumnCandidate(id=c.id, position=c.position, normalized_key=c.normalized_key, is_restated=c.is_restated)
        for c in later_columns_orm
    ]
    column_decisions = align_columns(earlier_columns, later_columns, config, report_pair.earlier_report.directory_year, report_pair.later_report.directory_year)

    row_alignment_by_earlier: dict[uuid.UUID, StructuredRowAlignment] = {}
    row_alignment_by_later: dict[uuid.UUID, StructuredRowAlignment] = {}
    for decision in row_decisions:
        row_alignment = StructuredRowAlignment(
            alignment_run_id=run.id, earlier_structured_table_row_id=decision.earlier_row_id,
            later_structured_table_row_id=decision.later_row_id, status=decision.status,
            confidence=decision.confidence, evidence=decision.evidence,
        )
        session.add(row_alignment)
        session.flush()
        if decision.earlier_row_id:
            row_alignment_by_earlier[decision.earlier_row_id] = row_alignment
        if decision.later_row_id:
            row_alignment_by_later[decision.later_row_id] = row_alignment

    column_alignments: list[tuple[ColumnAlignmentDecision, StructuredColumnAlignment]] = []
    for decision in column_decisions:
        column_alignment = StructuredColumnAlignment(
            alignment_run_id=run.id, earlier_structured_table_column_id=decision.earlier_column_id,
            later_structured_table_column_id=decision.later_column_id, status=decision.status,
            comparability_status=decision.comparability_status, confidence=decision.confidence, evidence=decision.evidence,
        )
        session.add(column_alignment)
        session.flush()
        column_alignments.append((decision, column_alignment))

    notes: list[str] = []
    for row_decision in row_decisions:
        if row_decision.status not in (
            StructuredRowAlignmentStatus.MATCHED, StructuredRowAlignmentStatus.COMPARATIVE_ONLY,
            StructuredRowAlignmentStatus.PARTIAL_YEAR,
        ):
            continue  # ADDED/REMOVED rows have nothing to compare
        row_alignment = row_alignment_by_earlier.get(row_decision.earlier_row_id) if row_decision.earlier_row_id else None
        if row_alignment is None:
            row_alignment = row_alignment_by_later.get(row_decision.later_row_id)

        for col_decision, column_alignment in column_alignments:
            if col_decision.status != StructuredColumnAlignmentStatus.MATCHED:
                continue  # ADDED/REMOVED columns have nothing to compare

            earlier_cell_orm = (
                cells_by_row.get(row_decision.earlier_row_id, {}).get(col_decision.earlier_column_id)
                if row_decision.earlier_row_id else None
            )
            later_cell_orm = (
                cells_by_row.get(row_decision.later_row_id, {}).get(col_decision.later_column_id)
                if row_decision.later_row_id else None
            )
            earlier_view = (
                CellView(earlier_cell_orm.id, earlier_cell_orm.raw_value, earlier_cell_orm.cell_status, earlier_cell_orm.parsed_numeric_value)
                if earlier_cell_orm else None
            )
            later_view = (
                CellView(later_cell_orm.id, later_cell_orm.raw_value, later_cell_orm.cell_status, later_cell_orm.parsed_numeric_value)
                if later_cell_orm else None
            )

            event_type, absolute, pct = classify_value_change(
                earlier_view, later_view, row_decision.status, col_decision.comparability_status
            )
            session.add(
                StructuredValueChangeEvent(
                    alignment_run_id=run.id, row_alignment_id=row_alignment.id, column_alignment_id=column_alignment.id,
                    earlier_structured_table_cell_id=earlier_view.id if earlier_view else None,
                    later_structured_table_cell_id=later_view.id if later_view else None,
                    event_type=event_type,
                    earlier_raw_value=earlier_view.raw_value if earlier_view else None,
                    later_raw_value=later_view.raw_value if later_view else None,
                    earlier_numeric=earlier_view.parsed_numeric_value if earlier_view else None,
                    later_numeric=later_view.parsed_numeric_value if later_view else None,
                    absolute_change=absolute, pct_change=pct,
                )
            )

    run.completed_at = datetime.now(UTC)
    run.review_reason = "; ".join(notes) if notes else None
    run.status = (
        StructuredTableAlignmentRunStatus.COMPLETED if not notes
        else StructuredTableAlignmentRunStatus.COMPLETED_WITH_WARNINGS
    )

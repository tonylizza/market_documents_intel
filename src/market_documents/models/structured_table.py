import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalMode,
    NormalizedSchedule,
    StructuredCellStatus,
    StructuredColumnAlignmentStatus,
    StructuredComparabilityStatus,
    StructuredRowAlignmentStatus,
    StructuredRowIdentityType,
    StructuredTableAlignmentRunStatus,
    StructuredTableExtractionRunStatus,
    StructuredTableReconstructionStatus,
    StructuredTableShape,
    StructuredValueChangeEventType,
)

# --------------------------------------------------------------------------
# Reconstruction: CanonicalBlock -> StructuredTable -> rows/columns/cells/footnotes
# --------------------------------------------------------------------------


class StructuredTableExtractionRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at reconstructing every configured structured table for
    one report (Track 7C.4, docs/7c4-structured-table-comparison.md).

    Pins the source `CanonicalExtractionRun`, mirroring every prior track's
    "pin the upstream run" convention. Deliberately does **not** depend on
    a `ScheduleLocalizationRun`: REMUNERATION was never localized by 7C.1
    (only FINANCIAL_PERFORMANCE is configured there), and adding a
    REMUNERATION entry to `schedule_config.py` would mean reopening 7C.1's
    localization mechanism, which the milestone explicitly forbids. Each
    `TableFamilyConfig.heading_pattern` is itself a precise, family-scoped
    locator -- it plays the localization role directly, scoped to the
    report's whole canonical document rather than a pre-localized page
    range. "Current successful" is a query-time rule (see
    `services.structured_table_reconstruction.get_current_extraction_run`),
    never a stored flag.
    """

    __tablename__ = "structured_table_extraction_runs"
    __table_args__ = (
        Index("ix_structured_table_extraction_runs_report_family_status", "report_id", "table_family_key", "status"),
        Index("ix_structured_table_extraction_runs_report_completed_at", "report_id", "completed_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    canonical_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    table_family_key: Mapped[str] = mapped_column(String(128), nullable=False)

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[StructuredTableExtractionRunStatus] = mapped_column(
        SAEnum(StructuredTableExtractionRunStatus, name="structured_table_extraction_run_status"),
        nullable=False, default=StructuredTableExtractionRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["Report"] = relationship()  # noqa: F821
    canonical_run: Mapped["CanonicalExtractionRun"] = relationship()  # noqa: F821
    tables: Mapped[list["StructuredTable"]] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan"
    )


class StructuredTable(UUIDPkMixin, TimestampMixin, Base):
    """One reconstructed structured table instance for one report/table
    family, produced by one `StructuredTableExtractionRun`."""

    __tablename__ = "structured_tables"
    __table_args__ = (
        UniqueConstraint("structured_table_extraction_run_id", "table_family_key", name="uq_structured_tables_run_family"),
        Index("ix_structured_tables_report_family", "report_id", "table_family_key"),
    )

    structured_table_extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    table_family_key: Mapped[str] = mapped_column(String(128), nullable=False)
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule", create_type=False), nullable=False
    )

    source_heading: Mapped[str] = mapped_column(Text, nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)
    table_shape: Mapped[StructuredTableShape] = mapped_column(
        SAEnum(StructuredTableShape, name="structured_table_shape"), nullable=False
    )
    row_identity_type: Mapped[StructuredRowIdentityType] = mapped_column(
        SAEnum(StructuredRowIdentityType, name="structured_row_identity_type"), nullable=False
    )
    analytical_mode: Mapped[AnalyticalMode] = mapped_column(
        SAEnum(AnalyticalMode, name="analytical_mode", create_type=False), nullable=False
    )
    unit_of_measure: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reconstruction_status: Mapped[StructuredTableReconstructionStatus] = mapped_column(
        SAEnum(StructuredTableReconstructionStatus, name="structured_table_reconstruction_status"), nullable=False
    )
    reconstruction_confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    extraction_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    extraction_run: Mapped["StructuredTableExtractionRun"] = relationship(back_populates="tables")
    report: Mapped["Report"] = relationship()  # noqa: F821
    columns: Mapped[list["StructuredTableColumn"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="StructuredTableColumn.position"
    )
    rows: Mapped[list["StructuredTableRow"]] = relationship(
        back_populates="table", cascade="all, delete-orphan", order_by="StructuredTableRow.position"
    )
    footnotes: Mapped[list["StructuredTableFootnote"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )


class StructuredTableColumn(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_table_columns"
    __table_args__ = (
        UniqueConstraint("structured_table_id", "position", name="uq_structured_table_columns_table_position"),
    )

    structured_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_tables.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_key: Mapped[str] = mapped_column(String(128), nullable=False)
    group_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    year_ref: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unit_or_currency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    is_restated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_block_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_blocks.id", ondelete="SET NULL"), nullable=True
    )

    table: Mapped["StructuredTable"] = relationship(back_populates="columns")


class StructuredTableRow(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_table_rows"
    __table_args__ = (
        UniqueConstraint("structured_table_id", "position", name="uq_structured_table_rows_table_position"),
    )

    structured_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_tables.id", ondelete="CASCADE"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    source_label: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_identity: Mapped[str] = mapped_column(String(256), nullable=False)
    category_label: Mapped[str | None] = mapped_column(Text, nullable=True)
    row_marker: Mapped[str | None] = mapped_column(String(8), nullable=True)
    source_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_blocks.id", ondelete="CASCADE"), nullable=False
    )

    table: Mapped["StructuredTable"] = relationship(back_populates="rows")
    cells: Mapped[list["StructuredTableCell"]] = relationship(
        back_populates="row", cascade="all, delete-orphan", order_by="StructuredTableCell.structured_table_column_id"
    )


class StructuredTableCell(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_table_cells"
    __table_args__ = (
        UniqueConstraint("structured_table_row_id", "structured_table_column_id", name="uq_structured_table_cells_row_column"),
    )

    structured_table_row_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_rows.id", ondelete="CASCADE"), nullable=False
    )
    structured_table_column_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_columns.id", ondelete="CASCADE"), nullable=False
    )
    raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    parsed_numeric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    cell_status: Mapped[StructuredCellStatus] = mapped_column(
        SAEnum(StructuredCellStatus, name="structured_cell_status"), nullable=False
    )
    currency_or_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    footnote_marker: Mapped[str | None] = mapped_column(String(8), nullable=True)

    row: Mapped["StructuredTableRow"] = relationship(back_populates="cells")
    column: Mapped["StructuredTableColumn"] = relationship()


class StructuredTableFootnote(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_table_footnotes"

    structured_table_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_tables.id", ondelete="CASCADE"), nullable=False
    )
    marker: Mapped[str] = mapped_column(String(8), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    page: Mapped[int] = mapped_column(Integer, nullable=False)
    source_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_blocks.id", ondelete="CASCADE"), nullable=False
    )
    # Scoped association, per docs/7c4-...md Section 11 -- unscoped
    # (all three NULL) means table-level.
    row_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_rows.id", ondelete="SET NULL"), nullable=True
    )
    column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_columns.id", ondelete="SET NULL"), nullable=True
    )
    cell_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_cells.id", ondelete="SET NULL"), nullable=True
    )

    table: Mapped["StructuredTable"] = relationship(back_populates="footnotes")


# --------------------------------------------------------------------------
# Comparison: cross-year row/column alignment + value-change events
# --------------------------------------------------------------------------


class StructuredTableAlignmentRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at aligning one table family's two adjacent-year
    `StructuredTable` reconstructions and computing value-change events.

    Pins both source `StructuredTableExtractionRun`s, mirroring
    `SemanticUnitAlignmentRun`'s own pinning convention.
    """

    __tablename__ = "structured_table_alignment_runs"
    __table_args__ = (
        Index("ix_structured_table_alignment_runs_pair_family_status", "report_pair_id", "table_family_key", "status"),
        Index("ix_structured_table_alignment_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    table_family_key: Mapped[str] = mapped_column(String(128), nullable=False)
    earlier_structured_table_extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    later_structured_table_extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[StructuredTableAlignmentRunStatus] = mapped_column(
        SAEnum(StructuredTableAlignmentRunStatus, name="structured_table_alignment_run_status"),
        nullable=False, default=StructuredTableAlignmentRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    row_alignments: Mapped[list["StructuredRowAlignment"]] = relationship(
        back_populates="alignment_run", cascade="all, delete-orphan"
    )
    column_alignments: Mapped[list["StructuredColumnAlignment"]] = relationship(
        back_populates="alignment_run", cascade="all, delete-orphan"
    )
    value_change_events: Mapped[list["StructuredValueChangeEvent"]] = relationship(
        back_populates="alignment_run", cascade="all, delete-orphan"
    )


class StructuredRowAlignment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_row_alignments"
    __table_args__ = (
        Index("ix_structured_row_alignments_run", "alignment_run_id"),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_structured_table_row_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_rows.id", ondelete="CASCADE"), nullable=True
    )
    later_structured_table_row_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_rows.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[StructuredRowAlignmentStatus] = mapped_column(
        SAEnum(StructuredRowAlignmentStatus, name="structured_row_alignment_status"), nullable=False
    )
    confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)

    alignment_run: Mapped["StructuredTableAlignmentRun"] = relationship(back_populates="row_alignments")
    earlier_row: Mapped["StructuredTableRow | None"] = relationship(foreign_keys=[earlier_structured_table_row_id])
    later_row: Mapped["StructuredTableRow | None"] = relationship(foreign_keys=[later_structured_table_row_id])


class StructuredColumnAlignment(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_column_alignments"
    __table_args__ = (
        Index("ix_structured_column_alignments_run", "alignment_run_id"),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_structured_table_column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_columns.id", ondelete="CASCADE"), nullable=True
    )
    later_structured_table_column_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_columns.id", ondelete="CASCADE"), nullable=True
    )
    status: Mapped[StructuredColumnAlignmentStatus] = mapped_column(
        SAEnum(StructuredColumnAlignmentStatus, name="structured_column_alignment_status"), nullable=False
    )
    comparability_status: Mapped[StructuredComparabilityStatus] = mapped_column(
        SAEnum(StructuredComparabilityStatus, name="structured_comparability_status"), nullable=False
    )
    confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)

    alignment_run: Mapped["StructuredTableAlignmentRun"] = relationship(back_populates="column_alignments")
    earlier_column: Mapped["StructuredTableColumn | None"] = relationship(foreign_keys=[earlier_structured_table_column_id])
    later_column: Mapped["StructuredTableColumn | None"] = relationship(foreign_keys=[later_structured_table_column_id])


class StructuredValueChangeEvent(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "structured_value_change_events"
    __table_args__ = (
        Index("ix_structured_value_change_events_run", "alignment_run_id"),
        Index("ix_structured_value_change_events_row_alignment", "row_alignment_id"),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    row_alignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_row_alignments.id", ondelete="CASCADE"), nullable=False
    )
    column_alignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_column_alignments.id", ondelete="CASCADE"), nullable=False
    )
    earlier_structured_table_cell_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_cells.id", ondelete="CASCADE"), nullable=True
    )
    later_structured_table_cell_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("structured_table_cells.id", ondelete="CASCADE"), nullable=True
    )
    event_type: Mapped[StructuredValueChangeEventType] = mapped_column(
        SAEnum(StructuredValueChangeEventType, name="structured_value_change_event_type"), nullable=False
    )
    earlier_raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    later_raw_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    earlier_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    later_numeric: Mapped[float | None] = mapped_column(Float, nullable=True)
    absolute_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    pct_change: Mapped[float | None] = mapped_column(Float, nullable=True)

    alignment_run: Mapped["StructuredTableAlignmentRun"] = relationship(back_populates="value_change_events")
    row_alignment: Mapped["StructuredRowAlignment"] = relationship()
    column_alignment: Mapped["StructuredColumnAlignment"] = relationship()

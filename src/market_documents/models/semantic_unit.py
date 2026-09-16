import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    BoundaryConfidence,
    NormalizedSchedule,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
    SemanticUnitRunStatus,
    SemanticUnitType,
)


class SemanticUnitRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at extracting semantic units of one schedule from one
    Report's localized schedule instance(s).

    Mirrors `PassageSegmentationRun`: "current successful" is a query-time
    rule (see `services.semantic_unit_extraction.get_current_extraction_run`),
    never a stored flag. Pins the source `ScheduleLocalizationRun` so a
    result stays reproducible even after re-localization.
    """

    __tablename__ = "semantic_unit_runs"
    __table_args__ = (
        Index("ix_semantic_unit_runs_report_schedule_status", "report_id", "schedule", "status"),
        Index("ix_semantic_unit_runs_report_completed_at", "report_id", "completed_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    schedule_localization_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_localization_runs.id", ondelete="CASCADE"), nullable=False
    )
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule", create_type=False), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[SemanticUnitRunStatus] = mapped_column(
        SAEnum(SemanticUnitRunStatus, name="semantic_unit_run_status"),
        nullable=False,
        default=SemanticUnitRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs
    # (e.g. one or more UNRESOLVED units), mirroring
    # `PassageSegmentationRun.review_reason` -- error_message is reserved
    # for FAILED runs that never produced any SemanticUnit rows at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["Report"] = relationship()  # noqa: F821
    schedule_localization_run: Mapped["ScheduleLocalizationRun"] = relationship()  # noqa: F821
    units: Mapped[list["SemanticUnit"]] = relationship(
        back_populates="semantic_unit_run", cascade="all, delete-orphan"
    )


class SemanticUnit(UUIDPkMixin, TimestampMixin, Base):
    """One source-grounded, reconstructed structural unit of narrative text,
    produced by one successful SemanticUnitRun.

    Deliberately named `SemanticUnit`, not `AnalyticalUnit`: this row
    carries no comparison-type classification and is not yet an
    analytical/comparison-ready object. The research explicitly
    distinguishes a *structural semantic unit* (this row: known boundaries,
    known provenance, source-faithful text) from an *analytical comparison
    unit* (the same content once classified with a comparison type and
    ready for cross-year comparison) -- that classification is a
    downstream, not-yet-built concept (7C.3), and is not collapsed into
    this schema.

    `source_heading`/`start_page` are always populated: a row is only
    created once a start heading has actually matched within a
    ScheduleInstance. `end_page`/`source_text`/`word_count`/
    `boundary_confidence` are populated only when `boundary_status ==
    RESOLVED` -- when UNRESOLVED, they are NULL, never a fabricated or
    partial best-guess value. See `boundary_status`'s docstring on
    `SemanticUnitBoundaryStatus` and
    docs/7c1-schedule-localization-plan.md Section 4.2.
    """

    __tablename__ = "semantic_units"
    __table_args__ = (
        UniqueConstraint(
            "semantic_unit_run_id", "schedule_instance_id", "unit_key",
            name="uq_semantic_units_run_instance_unit_key",
        ),
        Index("ix_semantic_units_report_unit_key", "report_id", "unit_key"),
        Index("ix_semantic_units_report_boundary_status", "report_id", "boundary_status"),
    )

    semantic_unit_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    schedule_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_instances.id", ondelete="CASCADE"), nullable=False
    )

    # Stable, hand-defined slug from `semantic_unit_config.py`, e.g.
    # "gross_margin" -- company+schedule-scoped, NOT required to match
    # across companies (BEL and ACT may legitimately use different keys for
    # the same unit_type; see docs/7c1-schedule-localization-plan.md
    # Section 6.1).
    unit_key: Mapped[str] = mapped_column(String(128), nullable=False)
    unit_type: Mapped[SemanticUnitType] = mapped_column(
        SAEnum(SemanticUnitType, name="semantic_unit_type"), nullable=False
    )

    source_heading: Mapped[str] = mapped_column(String(512), nullable=False)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)

    boundary_strategy: Mapped[SemanticUnitBoundaryStrategy] = mapped_column(
        SAEnum(SemanticUnitBoundaryStrategy, name="semantic_unit_boundary_strategy"), nullable=False
    )
    boundary_anchor_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    boundary_status: Mapped[SemanticUnitBoundaryStatus] = mapped_column(
        SAEnum(SemanticUnitBoundaryStatus, name="semantic_unit_boundary_status"), nullable=False
    )
    boundary_confidence: Mapped[BoundaryConfidence | None] = mapped_column(
        SAEnum(BoundaryConfidence, name="boundary_confidence", create_type=False), nullable=True
    )

    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Populated for a RESOLVED unit that needed a boundary correction (audit
    # trail of *what* was fixed), and always populated for an UNRESOLVED
    # unit (audit trail of *why* resolution failed) -- never left blank in
    # the failure case, per docs/7c1-schedule-localization-plan.md's
    # persistence-behavior note.
    extraction_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    semantic_unit_run: Mapped["SemanticUnitRun"] = relationship(back_populates="units")
    report: Mapped["Report"] = relationship()  # noqa: F821
    schedule_instance: Mapped["ScheduleInstance"] = relationship()  # noqa: F821
    source_blocks: Mapped[list["SemanticUnitSourceBlock"]] = relationship(
        back_populates="semantic_unit",
        cascade="all, delete-orphan",
        order_by="SemanticUnitSourceBlock.block_order",
    )


class SemanticUnitSourceBlock(UUIDPkMixin, Base):
    """Ordered association between a SemanticUnit and a character span of
    one of its source TextBlocks -- answers "exactly which source block
    text produced this semantic unit?" Mirrors `PassageSourceBlock`.

    Empty for an UNRESOLVED unit (no trustworthy span was ever
    reconstructed). `(0, len(text_block.text))` for a fully-included block;
    a narrower span only for the block containing an `ANCHOR_SENTENCE`
    boundary.
    """

    __tablename__ = "semantic_unit_source_blocks"
    __table_args__ = (
        UniqueConstraint(
            "semantic_unit_id", "block_order", name="uq_semantic_unit_source_blocks_unit_order"
        ),
        Index("ix_semantic_unit_source_blocks_unit_id", "semantic_unit_id"),
        Index("ix_semantic_unit_source_blocks_text_block_id", "text_block_id"),
    )

    semantic_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_units.id", ondelete="CASCADE"), nullable=False
    )
    text_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("text_blocks.id", ondelete="CASCADE"), nullable=False
    )
    block_order: Mapped[int] = mapped_column(Integer, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    semantic_unit: Mapped["SemanticUnit"] = relationship(back_populates="source_blocks")
    text_block: Mapped["TextBlock"] = relationship()  # noqa: F821

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    AlignmentConfidence,
    NormalizedSchedule,
    SemanticUnitAlignmentRunStatus,
    SemanticUnitAlignmentStatus,
)


class SemanticUnitAlignmentRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at aligning SemanticUnit records between the two sides of
    an adjacent-year ReportPair, for one schedule.

    Track 7C.2 (docs/7c2-semantic-unit-alignment.md): reads only the
    persisted SemanticUnit output of one current successful SemanticUnitRun
    on each side -- never re-localizes schedules, re-extracts units, or
    touches Passage/PassageAlignment/legacy TextBlock. Pins both source
    SemanticUnitRuns so a result stays reproducible even after either side
    is re-extracted. Mirrors `AlignmentRun`/`SemanticUnitRun`: a
    (report_pair, schedule) pair may have many runs over time; "current
    successful" is a query-time rule (see `get_current_alignment_run`),
    never a stored flag.

    A row is only ever created once both sides have a current successful
    SemanticUnitRun for `schedule` -- if either side has none at all, the
    orchestration reports that pair as ineligible without creating a run
    (see `services.semantic_unit_alignment.run_alignment`).
    """

    __tablename__ = "semantic_unit_alignment_runs"
    __table_args__ = (
        Index("ix_semantic_unit_alignment_runs_pair_schedule_status", "report_pair_id", "schedule", "status"),
        Index("ix_semantic_unit_alignment_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_semantic_unit_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_runs.id", ondelete="CASCADE"), nullable=False
    )
    later_semantic_unit_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_runs.id", ondelete="CASCADE"), nullable=False
    )
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule", create_type=False), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[SemanticUnitAlignmentRunStatus] = mapped_column(
        SAEnum(SemanticUnitAlignmentRunStatus, name="semantic_unit_alignment_run_status"),
        nullable=False,
        default=SemanticUnitAlignmentRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs
    # (one or more UNRESOLVED_UPSTREAM/AMBIGUOUS results) -- error_message
    # is reserved for FAILED runs that never produced any alignment row.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    earlier_semantic_unit_run: Mapped["SemanticUnitRun"] = relationship(  # noqa: F821
        foreign_keys=[earlier_semantic_unit_run_id]
    )
    later_semantic_unit_run: Mapped["SemanticUnitRun"] = relationship(  # noqa: F821
        foreign_keys=[later_semantic_unit_run_id]
    )
    alignments: Mapped[list["SemanticUnitAlignment"]] = relationship(
        back_populates="alignment_run", cascade="all, delete-orphan"
    )


class SemanticUnitAlignment(UUIDPkMixin, TimestampMixin, Base):
    """One accepted cross-year correspondence (or non-correspondence)
    between two SemanticUnit records, produced by one
    SemanticUnitAlignmentRun.

    `earlier_semantic_unit_id`/`later_semantic_unit_id` are individually
    nullable: ADDED has no earlier match, REMOVED has no later match,
    matching the `PassageAlignment` convention. Carries no comparison or
    change-magnitude metric of any kind -- this row answers only "which
    unit corresponds to which," never "how much did it change" (7C.3).

    `confidence` reuses `AlignmentConfidence` (HIGH/MEDIUM/LOW/NEEDS_REVIEW)
    rather than a new enum: it is already a generic four-level scale with
    no Passage-specific meaning, and a duplicate enum with identical
    members would add a parallel type for no behavioral reason.
    """

    __tablename__ = "semantic_unit_alignments"
    __table_args__ = (
        Index("ix_semantic_unit_alignments_run_id", "alignment_run_id"),
        Index("ix_semantic_unit_alignments_report_pair_id", "report_pair_id"),
        Index("ix_semantic_unit_alignments_status", "alignment_run_id", "status"),
        # SPLIT/MERGED are explicitly out of scope for 7C.2 -- these partial
        # unique indexes enforce that within one run, one earlier unit never
        # silently aligns to multiple later units (and vice versa); a bug
        # that would produce such a case must fail loudly instead.
        Index(
            "uq_semantic_unit_alignments_run_later",
            "alignment_run_id", "later_semantic_unit_id",
            unique=True,
            postgresql_where=text("later_semantic_unit_id IS NOT NULL"),
        ),
        Index(
            "uq_semantic_unit_alignments_run_earlier",
            "alignment_run_id", "earlier_semantic_unit_id",
            unique=True,
            postgresql_where=text("earlier_semantic_unit_id IS NOT NULL"),
        ),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_semantic_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_units.id", ondelete="CASCADE"), nullable=True
    )
    later_semantic_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_units.id", ondelete="CASCADE"), nullable=True
    )

    status: Mapped[SemanticUnitAlignmentStatus] = mapped_column(
        SAEnum(SemanticUnitAlignmentStatus, name="semantic_unit_alignment_status"), nullable=False
    )
    confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)

    alignment_run: Mapped["SemanticUnitAlignmentRun"] = relationship(back_populates="alignments")
    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    earlier_semantic_unit: Mapped["SemanticUnit | None"] = relationship(  # noqa: F821
        foreign_keys=[earlier_semantic_unit_id]
    )
    later_semantic_unit: Mapped["SemanticUnit | None"] = relationship(  # noqa: F821
        foreign_keys=[later_semantic_unit_id]
    )

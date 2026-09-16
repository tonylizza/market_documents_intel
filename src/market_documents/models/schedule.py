import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    BoundaryConfidence,
    NormalizedSchedule,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
)


class ScheduleLocalizationRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at localizing one normalized schedule for one Report.

    Mirrors `ExtractionRun`/`PassageSegmentationRun`: a (report, schedule)
    pair may have many runs over time; the "current successful" run is a
    query-time rule (see `services.schedule_localization.get_current_localization_run`),
    never a stored flag. `schedule` is stored on the run itself, not
    inferred from child `ScheduleInstance` rows, because the run is scoped
    per (report, schedule) -- a FAILED run that produced zero instances
    still needs its own schedule identity to be queryable and to drive
    idempotent-skip logic for that schedule specifically.

    Part of Track 7C.1 (docs/7c1-schedule-localization-plan.md): a parallel
    replacement track, independent of the existing passage pipeline.
    """

    __tablename__ = "schedule_localization_runs"
    __table_args__ = (
        Index("ix_schedule_localization_runs_report_schedule_status", "report_id", "schedule", "status"),
        Index("ix_schedule_localization_runs_report_completed_at", "report_id", "completed_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[ScheduleLocalizationRunStatus] = mapped_column(
        SAEnum(ScheduleLocalizationRunStatus, name="schedule_localization_run_status"),
        nullable=False,
        default=ScheduleLocalizationRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs,
    # mirroring `ExtractionRun.review_reason` -- error_message is reserved
    # for FAILED runs that never produced a ScheduleInstance at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped["Report"] = relationship()  # noqa: F821
    extraction_run: Mapped["ExtractionRun"] = relationship()  # noqa: F821
    instances: Mapped[list["ScheduleInstance"]] = relationship(
        back_populates="localization_run", cascade="all, delete-orphan"
    )


class ScheduleInstance(UUIDPkMixin, Base):
    """One localized schedule occurrence for one Report, produced by one
    successful ScheduleLocalizationRun.

    `heading_text`/`start_page`/`end_page` are null when `status` is
    NOT_FOUND or DISTRIBUTED_NO_CLEAR_PRIMARY -- no primary span exists to
    record in either case.
    """

    __tablename__ = "schedule_instances"
    __table_args__ = (
        UniqueConstraint(
            "schedule_localization_run_id", "schedule", name="uq_schedule_instances_run_schedule"
        ),
        Index("ix_schedule_instances_report_schedule", "report_id", "schedule"),
    )

    schedule_localization_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_localization_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule", create_type=False), nullable=False
    )

    status: Mapped[ScheduleLocalizationStatus] = mapped_column(
        SAEnum(ScheduleLocalizationStatus, name="schedule_localization_status"), nullable=False
    )
    heading_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    start_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_page: Mapped[int | None] = mapped_column(Integer, nullable=True)
    boundary_confidence: Mapped[BoundaryConfidence | None] = mapped_column(
        SAEnum(BoundaryConfidence, name="boundary_confidence"), nullable=True
    )
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reasoning_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    localization_run: Mapped["ScheduleLocalizationRun"] = relationship(back_populates="instances")
    report: Mapped["Report"] = relationship()  # noqa: F821
    supporting_spans: Mapped[list["ScheduleInstanceSupportingSpan"]] = relationship(
        back_populates="schedule_instance", cascade="all, delete-orphan"
    )


class ScheduleInstanceSupportingSpan(UUIDPkMixin, Base):
    """Zero or more supporting page ranges for a ScheduleInstance whose
    material content is not fully contained in its primary span -- e.g.
    BEL's FINANCIAL_PERFORMANCE schedule has a "Financial" subsection
    inside the joint chairman/CEO report supporting the Finance director's
    report primary (see annual-report-schedule-localization.md 3.3)."""

    __tablename__ = "schedule_instance_supporting_spans"
    __table_args__ = (Index("ix_schedule_instance_supporting_spans_instance_id", "schedule_instance_id"),)

    schedule_instance_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("schedule_instances.id", ondelete="CASCADE"), nullable=False
    )
    heading_text: Mapped[str | None] = mapped_column(String(512), nullable=True)
    start_page: Mapped[int] = mapped_column(Integer, nullable=False)
    end_page: Mapped[int] = mapped_column(Integer, nullable=False)

    schedule_instance: Mapped["ScheduleInstance"] = relationship(back_populates="supporting_spans")

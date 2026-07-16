import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import DiffMode, SimilarityResultQuality, SimilarityRunStatus


class SimilarityRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at scoring a ReportPair's document-level change.

    A pair may have many runs over time; the "current" result is not a
    stored flag but a query-time rule (see
    `services.similarity.get_current_similarity_run`): the most recently
    completed run with status COMPLETED or COMPLETED_WITH_WARNINGS. FAILED
    and in-progress runs are never eligible, so a failed rerun can never
    silently replace prior successful output. `earlier_narrative_document_id`
    and `later_narrative_document_id` pin the exact inputs used, so a result
    stays reproducible even after either report is re-extracted.
    """

    __tablename__ = "similarity_runs"
    __table_args__ = (
        Index("ix_similarity_runs_pair_status", "report_pair_id", "status"),
        Index("ix_similarity_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_narrative_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_documents.id", ondelete="CASCADE"), nullable=False
    )
    later_narrative_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_documents.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[SimilarityRunStatus] = mapped_column(
        SAEnum(SimilarityRunStatus, name="similarity_run_status"),
        nullable=False,
        default=SimilarityRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    earlier_narrative_document: Mapped["NarrativeDocument"] = relationship(  # noqa: F821
        foreign_keys=[earlier_narrative_document_id]
    )
    later_narrative_document: Mapped["NarrativeDocument"] = relationship(  # noqa: F821
        foreign_keys=[later_narrative_document_id]
    )
    document_similarity: Mapped["DocumentSimilarity | None"] = relationship(
        back_populates="similarity_run", cascade="all, delete-orphan", uselist=False
    )


class DocumentSimilarity(UUIDPkMixin, TimestampMixin, Base):
    """Metric results for one successful SimilarityRun.

    One-to-one with a SimilarityRun that COMPLETED (with or without
    warnings) -- a FAILED run never gets one, so a partial or fabricated
    result can never exist. `report_pair_id`/`earlier_report_id`/
    `later_report_id` are denormalized from the run for audit and ranking
    queries that shouldn't have to join through `similarity_runs`.

    Every metric is stored independently and is `None` when it could not be
    computed (e.g. an empty token set) -- a `None` here always means
    "explicitly undefined", never a fabricated 0 or 1.
    """

    __tablename__ = "document_similarities"
    __table_args__ = (
        Index("ix_document_similarities_report_pair_id", "report_pair_id"),
        Index("ix_document_similarities_earlier_report_id", "earlier_report_id"),
        Index("ix_document_similarities_later_report_id", "later_report_id"),
    )

    similarity_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("similarity_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    later_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )

    lexical_cosine_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    jaccard_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    diff_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    diff_mode: Mapped[DiffMode | None] = mapped_column(
        SAEnum(DiffMode, name="diff_mode"), nullable=True
    )
    diff_duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    edit_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    earlier_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    later_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_change: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_change_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    earlier_character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    later_character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count_change: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count_change_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)

    quality_status: Mapped[SimilarityResultQuality] = mapped_column(
        SAEnum(SimilarityResultQuality, name="similarity_result_quality"), nullable=False
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    primary_analysis_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    primary_analysis_exclusion_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    similarity_run: Mapped["SimilarityRun"] = relationship(back_populates="document_similarity")

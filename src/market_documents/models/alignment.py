import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import AlignmentConfidence, AlignmentRunStatus, AlignmentStatus, AlignmentType


class AlignmentRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at aligning passages between the two sides of a ReportPair.

    Pins the exact segmentation and embedding runs used on each side, so a
    result stays reproducible even after either report is re-segmented or
    re-embedded. Mirrors `SimilarityRun`: a pair may have many alignment
    runs over time; "current successful" is a query-time rule.

    `unchanged_count`/`lightly_modified_count`/`substantially_modified_count`
    extend the milestone's suggested field list (which named only
    matched/new/removed/ambiguous) because the required CLI status and audit
    views break matches down by classification, and these are cheap
    denormalized rollups of `PassageAlignment.alignment_status` computed once
    at run completion.
    """

    __tablename__ = "alignment_runs"
    __table_args__ = (
        Index("ix_alignment_runs_pair_status", "report_pair_id", "status"),
        Index("ix_alignment_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_segmentation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_segmentation_runs.id", ondelete="CASCADE"), nullable=False
    )
    later_segmentation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_segmentation_runs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_embedding_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embedding_runs.id", ondelete="CASCADE"), nullable=False
    )
    later_embedding_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embedding_runs.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[AlignmentRunStatus] = mapped_column(
        SAEnum(AlignmentRunStatus, name="alignment_run_status"),
        nullable=False,
        default=AlignmentRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs
    # (e.g. NEEDS_REVIEW source extraction, irregular gap, transition pair)
    # mirroring `ExtractionRun.review_reason` -- error_message is reserved
    # for FAILED runs that never produced alignments at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    matched_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    unchanged_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lightly_modified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    substantially_modified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    new_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    removed_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ambiguous_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    earlier_segmentation_run: Mapped["PassageSegmentationRun"] = relationship(  # noqa: F821
        foreign_keys=[earlier_segmentation_run_id]
    )
    later_segmentation_run: Mapped["PassageSegmentationRun"] = relationship(  # noqa: F821
        foreign_keys=[later_segmentation_run_id]
    )
    earlier_embedding_run: Mapped["EmbeddingRun"] = relationship(  # noqa: F821
        foreign_keys=[earlier_embedding_run_id]
    )
    later_embedding_run: Mapped["EmbeddingRun"] = relationship(  # noqa: F821
        foreign_keys=[later_embedding_run_id]
    )
    alignments: Mapped[list["PassageAlignment"]] = relationship(
        back_populates="alignment_run", cascade="all, delete-orphan"
    )


class PassageAlignment(UUIDPkMixin, TimestampMixin, Base):
    """One accepted correspondence (or non-correspondence) between passages.

    `earlier_passage_id`/`later_passage_id` are individually nullable: a NEW
    passage has no earlier match, a REMOVED passage has no later match. Every
    component score is stored independently and is `None` when not
    applicable -- never a fabricated 0 or 1, matching the M3
    `DocumentSimilarity` convention. `primary_alignment` is reserved for a
    future constrained split/merge implementation where one earlier or later
    passage could legitimately appear in more than one accepted row; in this
    milestone's one-to-one-only alignment, every persisted row is primary.
    """

    __tablename__ = "passage_alignments"
    __table_args__ = (
        Index("ix_passage_alignments_run_id", "alignment_run_id"),
        Index("ix_passage_alignments_report_pair_id", "report_pair_id"),
        Index("ix_passage_alignments_status", "alignment_run_id", "alignment_status"),
        Index("ix_passage_alignments_confidence", "alignment_run_id", "confidence"),
        Index(
            "uq_passage_alignments_run_later_primary",
            "alignment_run_id",
            "later_passage_id",
            unique=True,
            postgresql_where=text("later_passage_id IS NOT NULL AND primary_alignment"),
        ),
        Index(
            "uq_passage_alignments_run_earlier_primary",
            "alignment_run_id",
            "earlier_passage_id",
            unique=True,
            postgresql_where=text("earlier_passage_id IS NOT NULL AND primary_alignment"),
        ),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    earlier_passage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="CASCADE"), nullable=True
    )
    later_passage_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="CASCADE"), nullable=True
    )

    alignment_status: Mapped[AlignmentStatus] = mapped_column(
        SAEnum(AlignmentStatus, name="alignment_status"), nullable=False
    )
    alignment_type: Mapped[AlignmentType] = mapped_column(
        SAEnum(AlignmentType, name="alignment_type"), nullable=False
    )

    semantic_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    lexical_cosine_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    jaccard_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    edit_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    length_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    position_difference: Mapped[float | None] = mapped_column(Float, nullable=True)
    combined_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    candidate_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)

    confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence"), nullable=False
    )
    best_second_margin: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    primary_alignment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    alignment_run: Mapped["AlignmentRun"] = relationship(back_populates="alignments")
    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    earlier_passage: Mapped["Passage | None"] = relationship(  # noqa: F821
        foreign_keys=[earlier_passage_id]
    )
    later_passage: Mapped["Passage | None"] = relationship(  # noqa: F821
        foreign_keys=[later_passage_id]
    )

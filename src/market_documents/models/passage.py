import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import PassageSegmentationRunStatus, PassageType


class PassageSegmentationRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at segmenting a NarrativeDocument's source blocks into passages.

    Mirrors `ExtractionRun`/`SimilarityRun`: a NarrativeDocument may have many
    runs over time; the "current successful segmentation" is a query-time
    rule (see `services.passage_segmentation.get_current_segmentation_run`),
    never a stored flag. FAILED and in-progress runs are never eligible, so a
    failed rerun can never silently replace prior successful passages.
    """

    __tablename__ = "passage_segmentation_runs"
    __table_args__ = (
        Index("ix_passage_segmentation_runs_narrative_doc_status", "narrative_document_id", "status"),
        Index(
            "ix_passage_segmentation_runs_narrative_doc_completed_at",
            "narrative_document_id",
            "completed_at",
        ),
    )

    narrative_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_documents.id", ondelete="CASCADE"), nullable=False
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[PassageSegmentationRunStatus] = mapped_column(
        SAEnum(PassageSegmentationRunStatus, name="passage_segmentation_run_status"),
        nullable=False,
        default=PassageSegmentationRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs to
    # record *why* (provenance diagnostics, etc), mirroring
    # `ExtractionRun.review_reason` -- error_message is reserved for FAILED
    # runs that never produced passages at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    passage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    excluded_passage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    narrative_document: Mapped["NarrativeDocument"] = relationship()  # noqa: F821
    extraction_run: Mapped["ExtractionRun"] = relationship()  # noqa: F821
    passages: Mapped[list["Passage"]] = relationship(
        back_populates="segmentation_run", cascade="all, delete-orphan"
    )


class Passage(UUIDPkMixin, TimestampMixin, Base):
    """One segmented passage of narrative text, scoped to a single segmentation run.

    `content_hash` is over `normalized_text` (same NFKC+lowercase normalization
    as the M3 tokenizer) so identical passage text always hashes identically
    regardless of position -- logical identity for reproducibility purposes is
    `(segmentation_run_id, passage_index)` plus this hash, never the hash
    alone, since repeated boilerplate text must remain distinguishable by
    position.
    """

    __tablename__ = "passages"
    __table_args__ = (
        UniqueConstraint(
            "segmentation_run_id", "passage_index", name="uq_passages_run_passage_index"
        ),
        Index("ix_passages_report_id", "report_id"),
        Index("ix_passages_narrative_document_id", "narrative_document_id"),
        Index("ix_passages_segmentation_run_excluded", "segmentation_run_id", "excluded_from_alignment"),
    )

    segmentation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_segmentation_runs.id", ondelete="CASCADE"), nullable=False
    )
    narrative_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("narrative_documents.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )

    passage_index: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    first_page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    last_page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    character_count: Mapped[int] = mapped_column(Integer, nullable=False)

    heading_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    passage_type: Mapped[PassageType] = mapped_column(
        SAEnum(PassageType, name="passage_type"), nullable=False
    )

    excluded_from_alignment: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    segmentation_run: Mapped["PassageSegmentationRun"] = relationship(back_populates="passages")
    source_blocks: Mapped[list["PassageSourceBlock"]] = relationship(
        back_populates="passage",
        cascade="all, delete-orphan",
        order_by="PassageSourceBlock.source_order",
    )


class PassageSourceBlock(UUIDPkMixin, Base):
    """Ordered association between a Passage and one of its source TextBlocks.

    `segmentation_run_id` is denormalized from the parent Passage so "a
    TextBlock belongs to at most one Passage per segmentation run" can be a
    plain database uniqueness constraint rather than a join-based check.
    """

    __tablename__ = "passage_source_blocks"
    __table_args__ = (
        UniqueConstraint(
            "segmentation_run_id", "text_block_id", name="uq_passage_source_blocks_run_text_block"
        ),
        UniqueConstraint("passage_id", "source_order", name="uq_passage_source_blocks_passage_order"),
        Index("ix_passage_source_blocks_passage_id", "passage_id"),
        Index("ix_passage_source_blocks_text_block_id", "text_block_id"),
    )

    passage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    text_block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("text_blocks.id", ondelete="CASCADE"), nullable=False
    )
    segmentation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_segmentation_runs.id", ondelete="CASCADE"), nullable=False
    )
    source_order: Mapped[int] = mapped_column(Integer, nullable=False)

    passage: Mapped["Passage"] = relationship(back_populates="source_blocks")
    text_block: Mapped["TextBlock"] = relationship()  # noqa: F821

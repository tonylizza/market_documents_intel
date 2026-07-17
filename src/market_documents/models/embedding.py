import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import EmbeddingRunStatus

# The pgvector column is fixed at this dimension because the single approved
# embedding model (BAAI/bge-small-en-v1.5, see services/embedding_config.py)
# produces 384-dimensional vectors. A future model with a different
# dimension requires a new migration; EmbeddingRun.embedding_dimension is
# still stored and validated at insert time rather than trusted blindly.
EMBEDDING_DIMENSION = 384


class EmbeddingRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at embedding all eligible Passages of a segmentation run.

    Mirrors `PassageSegmentationRun`: a segmentation run may have many
    embedding runs over time (e.g. after a model revision change); "current
    successful" is a query-time rule, never a stored flag.
    """

    __tablename__ = "embedding_runs"
    __table_args__ = (
        Index("ix_embedding_runs_segmentation_run_status", "segmentation_run_id", "status"),
        Index("ix_embedding_runs_segmentation_run_completed_at", "segmentation_run_id", "completed_at"),
    )

    segmentation_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_segmentation_runs.id", ondelete="CASCADE"), nullable=False
    )

    model_name: Mapped[str] = mapped_column(String(255), nullable=False)
    model_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    tokenizer_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tokenizer_revision: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(Integer, nullable=False)
    pooling_strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    normalization_method: Mapped[str] = mapped_column(String(32), nullable=False)
    maximum_model_tokens: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[EmbeddingRunStatus] = mapped_column(
        SAEnum(EmbeddingRunStatus, name="embedding_run_status"),
        nullable=False,
        default=EmbeddingRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs
    # (e.g. some passages skipped/truncated) mirroring
    # `ExtractionRun.review_reason` -- error_message is reserved for FAILED
    # runs that never produced embeddings at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    embedded_passage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skipped_passage_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    segmentation_run: Mapped["PassageSegmentationRun"] = relationship()  # noqa: F821
    passage_embeddings: Mapped[list["PassageEmbedding"]] = relationship(
        back_populates="embedding_run", cascade="all, delete-orphan"
    )


class PassageEmbedding(UUIDPkMixin, Base):
    """One dense vector for one Passage, produced by one EmbeddingRun."""

    __tablename__ = "passage_embeddings"
    __table_args__ = (
        UniqueConstraint("embedding_run_id", "passage_id", name="uq_passage_embeddings_run_passage"),
        Index("ix_passage_embeddings_passage_id", "passage_id"),
    )

    embedding_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("embedding_runs.id", ondelete="CASCADE"), nullable=False
    )
    passage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )

    embedding: Mapped[list[float]] = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=False)
    input_token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    truncated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    embedding_run: Mapped["EmbeddingRun"] = relationship(back_populates="passage_embeddings")
    passage: Mapped["Passage"] = relationship()  # noqa: F821

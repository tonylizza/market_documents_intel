import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import BlockType, ExtractionQuality, ExtractionStatus


class ExtractionRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at extracting a report's text.

    A report may have many runs over time; the "current successful
    extraction" is not a stored flag but a query-time rule (see
    `services.extraction.get_current_extraction_run`): the most recently
    completed run with status COMPLETED or COMPLETED_WITH_WARNINGS. FAILED
    and in-progress runs are never eligible, so a failed rerun can never
    silently replace prior successful output.
    """

    __tablename__ = "extraction_runs"
    __table_args__ = (
        Index("ix_extraction_runs_report_status", "report_id", "status"),
        Index("ix_extraction_runs_report_completed_at", "report_id", "completed_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )

    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[ExtractionStatus] = mapped_column(
        SAEnum(ExtractionStatus, name="extraction_status"),
        nullable=False,
        default=ExtractionStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    expected_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usable_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    low_text_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    image_only_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    extraction_quality: Mapped[ExtractionQuality | None] = mapped_column(
        SAEnum(ExtractionQuality, name="extraction_quality"), nullable=True
    )
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_pdf_handled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    report: Mapped["Report"] = relationship()  # noqa: F821
    pages: Mapped[list["Page"]] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan"
    )
    text_blocks: Mapped[list["TextBlock"]] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan"
    )
    narrative_document: Mapped["NarrativeDocument | None"] = relationship(
        back_populates="extraction_run", cascade="all, delete-orphan", uselist=False
    )


class Page(UUIDPkMixin, TimestampMixin, Base):
    """One page's native text and diagnostics, scoped to a single extraction run."""

    __tablename__ = "pages"
    __table_args__ = (
        UniqueConstraint("extraction_run_id", "page_number", name="uq_pages_run_page_number"),
        Index("ix_pages_report_page_number", "report_id", "page_number"),
    )

    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    character_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    block_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    image_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    native_text_available: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    suspected_image_only: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    extraction_quality: Mapped[ExtractionQuality] = mapped_column(
        SAEnum(ExtractionQuality, name="extraction_quality"), nullable=False
    )

    extraction_run: Mapped["ExtractionRun"] = relationship(back_populates="pages")
    text_blocks: Mapped[list["TextBlock"]] = relationship(
        back_populates="page", cascade="all, delete-orphan"
    )


class TextBlock(UUIDPkMixin, TimestampMixin, Base):
    """One extractor-reported block on a page, scoped to a single extraction run.

    `block_index` is the raw position in the extractor's block list for the
    page (including any image blocks that were skipped, so it may have
    gaps). `reading_order` is the contiguous 0..N-1 position among the text
    blocks actually kept for the page. Both are stored so future reordering
    logic has somewhere to write its output without a schema change, but M2
    does not reorder -- it trusts the extractor's own block order.
    """

    __tablename__ = "text_blocks"
    __table_args__ = (
        UniqueConstraint(
            "extraction_run_id", "page_id", "block_index", name="uq_text_blocks_run_page_block_index"
        ),
        Index("ix_text_blocks_page_reading_order", "page_id", "reading_order"),
        Index("ix_text_blocks_report_id", "report_id"),
    )

    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("pages.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )

    block_index: Mapped[int] = mapped_column(Integer, nullable=False)
    reading_order: Mapped[int] = mapped_column(Integer, nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    cleaned_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    block_type: Mapped[BlockType] = mapped_column(
        SAEnum(BlockType, name="block_type"), nullable=False, default=BlockType.UNKNOWN
    )

    x0: Mapped[float | None] = mapped_column(Float, nullable=True)
    y0: Mapped[float | None] = mapped_column(Float, nullable=True)
    x1: Mapped[float | None] = mapped_column(Float, nullable=True)
    y1: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_bold: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    is_repeated_header: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_repeated_footer: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    excluded_from_narrative: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    extraction_run: Mapped["ExtractionRun"] = relationship(back_populates="text_blocks")
    page: Mapped["Page"] = relationship(back_populates="text_blocks")


class NarrativeDocument(UUIDPkMixin, Base):
    """Deterministic report-level narrative text derived from Page/TextBlock rows.

    One-to-one with a successful ExtractionRun. This is a cache of a
    derivation, not a second source of truth -- it must always be
    regenerable from the run's Page and TextBlock records.
    """

    __tablename__ = "narrative_documents"
    __table_args__ = (Index("ix_narrative_documents_report_id", "report_id"),)

    extraction_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("extraction_runs.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )

    cleaned_text: Mapped[str] = mapped_column(Text, nullable=False)
    word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    extraction_run: Mapped["ExtractionRun"] = relationship(back_populates="narrative_document")

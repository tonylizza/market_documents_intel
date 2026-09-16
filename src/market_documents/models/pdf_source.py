import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import CanonicalExtractionStatus


class CanonicalExtractionRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at building the canonical, source-faithful PDF
    representation for a Report (Track 7C.1a).

    Mirrors `ExtractionRun`: a report may have many runs over time; the
    "current successful" run is a query-time rule (see
    `services.pdf_source_extraction.get_current_canonical_run`), never a
    stored flag. Entirely independent of `ExtractionRun`/`Page`/`TextBlock`
    -- reads only the raw PDF via `Report.local_path`, never the legacy
    extraction tables, so the legacy pipeline stays untouched (see
    docs/7c1a-canonical-source-representation.md).
    """

    __tablename__ = "canonical_extraction_runs"
    __table_args__ = (
        Index("ix_canonical_extraction_runs_report_status", "report_id", "status"),
        Index("ix_canonical_extraction_runs_report_completed_at", "report_id", "completed_at"),
    )

    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )

    extractor_name: Mapped[str] = mapped_column(String(64), nullable=False)
    extractor_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[CanonicalExtractionStatus] = mapped_column(
        SAEnum(CanonicalExtractionStatus, name="canonical_extraction_status"),
        nullable=False,
        default=CanonicalExtractionStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    expected_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    report: Mapped["Report"] = relationship()  # noqa: F821
    pages: Mapped[list["CanonicalPage"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )


class CanonicalPage(UUIDPkMixin, Base):
    """One page of a report's raw PDF, scoped to a single CanonicalExtractionRun.

    Carries only page-level geometry -- no text of its own. Page text is
    always reconstructable from its `CanonicalBlock`/`CanonicalLine`/
    `CanonicalSpan` children, never duplicated here.
    """

    __tablename__ = "canonical_pages"
    __table_args__ = (
        UniqueConstraint("canonical_run_id", "page_number", name="uq_canonical_pages_run_page_number"),
        Index("ix_canonical_pages_report_page_number", "report_id", "page_number"),
    )

    canonical_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_extraction_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)

    width: Mapped[float] = mapped_column(Float, nullable=False)
    height: Mapped[float] = mapped_column(Float, nullable=False)

    run: Mapped["CanonicalExtractionRun"] = relationship(back_populates="pages")
    blocks: Mapped[list["CanonicalBlock"]] = relationship(
        back_populates="page", cascade="all, delete-orphan", order_by="CanonicalBlock.block_order"
    )


class CanonicalBlock(UUIDPkMixin, Base):
    """One PyMuPDF `get_text("dict")` block, in native emission order.

    `block_order` is the raw, unsorted position PyMuPDF reported for this
    block on its page -- deliberately never re-sorted by y-coordinate at
    this layer (the extraction-representation bakeoff found that a global
    y-sort corrupts multi-column layouts; see
    docs/experiments/annual-report-extraction-representation-bakeoff.md).
    `native_type` is PyMuPDF's own block "type" (0 = text, 1 = image);
    image blocks are persisted for bbox/order completeness but have no
    `CanonicalLine`/`CanonicalSpan` children. `raw_text` is the verbatim
    concatenation of this block's lines/spans -- a convenience read, never
    the source of truth (that is always the span rows).
    """

    __tablename__ = "canonical_blocks"
    __table_args__ = (
        UniqueConstraint("page_id", "block_order", name="uq_canonical_blocks_page_block_order"),
        Index("ix_canonical_blocks_page_block_order", "page_id", "block_order"),
    )

    page_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_pages.id", ondelete="CASCADE"), nullable=False
    )
    block_order: Mapped[int] = mapped_column(Integer, nullable=False)
    native_type: Mapped[int] = mapped_column(Integer, nullable=False)

    x0: Mapped[float] = mapped_column(Float, nullable=False)
    y0: Mapped[float] = mapped_column(Float, nullable=False)
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)

    raw_text: Mapped[str] = mapped_column(Text, nullable=False, default="")

    page: Mapped["CanonicalPage"] = relationship(back_populates="blocks")
    lines: Mapped[list["CanonicalLine"]] = relationship(
        back_populates="block", cascade="all, delete-orphan", order_by="CanonicalLine.line_order"
    )


class CanonicalLine(UUIDPkMixin, Base):
    """One line within a `CanonicalBlock`, in native PyMuPDF order."""

    __tablename__ = "canonical_lines"
    __table_args__ = (
        UniqueConstraint("block_id", "line_order", name="uq_canonical_lines_block_line_order"),
        Index("ix_canonical_lines_block_line_order", "block_id", "line_order"),
    )

    block_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_blocks.id", ondelete="CASCADE"), nullable=False
    )
    line_order: Mapped[int] = mapped_column(Integer, nullable=False)

    x0: Mapped[float] = mapped_column(Float, nullable=False)
    y0: Mapped[float] = mapped_column(Float, nullable=False)
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)

    block: Mapped["CanonicalBlock"] = relationship(back_populates="lines")
    spans: Mapped[list["CanonicalSpan"]] = relationship(
        back_populates="line", cascade="all, delete-orphan", order_by="CanonicalSpan.span_order"
    )


class CanonicalSpan(UUIDPkMixin, Base):
    """One PyMuPDF span -- the finest-grained unit of text this layer
    captures, with its exact text and whatever font/style metadata PyMuPDF
    reports at negligible extra cost. Nothing is normalized, cleaned, or
    filtered: an empty or whitespace-only span is still persisted verbatim,
    since interpretation belongs downstream (see module docstring on
    `models.enums.CanonicalExtractionStatus`).
    """

    __tablename__ = "canonical_spans"
    __table_args__ = (
        UniqueConstraint("line_id", "span_order", name="uq_canonical_spans_line_span_order"),
        Index("ix_canonical_spans_line_span_order", "line_id", "span_order"),
    )

    line_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("canonical_lines.id", ondelete="CASCADE"), nullable=False
    )
    span_order: Mapped[int] = mapped_column(Integer, nullable=False)

    text: Mapped[str] = mapped_column(Text, nullable=False)

    x0: Mapped[float] = mapped_column(Float, nullable=False)
    y0: Mapped[float] = mapped_column(Float, nullable=False)
    x1: Mapped[float] = mapped_column(Float, nullable=False)
    y1: Mapped[float] = mapped_column(Float, nullable=False)

    font_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    font_size: Mapped[float | None] = mapped_column(Float, nullable=True)
    font_flags: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_bold: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    color: Mapped[int | None] = mapped_column(Integer, nullable=True)

    line: Mapped["CanonicalLine"] = relationship(back_populates="spans")

import uuid
from datetime import date

from sqlalchemy import Boolean, Date, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import MetadataSource, MetadataStatus


class Report(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index(
            "uq_reports_company_period_end",
            "company_id",
            "period_end",
            unique=True,
            postgresql_where=text("period_end IS NOT NULL"),
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )

    # File identity
    local_path: Mapped[str] = mapped_column(String(1024), unique=True, nullable=False)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Provisional / validated metadata
    directory_year: Mapped[int] = mapped_column(Integer, nullable=False)
    fiscal_label: Mapped[str | None] = mapped_column(String(64), nullable=True)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    reporting_months: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    metadata_status: Mapped[MetadataStatus] = mapped_column(
        SAEnum(MetadataStatus, name="metadata_status"),
        nullable=False,
        default=MetadataStatus.DISCOVERED,
    )
    metadata_source: Mapped[MetadataSource] = mapped_column(
        SAEnum(MetadataSource, name="metadata_source"),
        nullable=False,
        default=MetadataSource.DIRECTORY,
    )
    transition_report: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    validation_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    company: Mapped["Company"] = relationship(back_populates="reports")  # noqa: F821

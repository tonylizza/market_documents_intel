import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin


class ReportPair(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "report_pairs"
    __table_args__ = (
        UniqueConstraint(
            "earlier_report_id", "later_report_id", name="uq_report_pairs_earlier_later"
        ),
    )

    company_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("companies.id", ondelete="CASCADE"), nullable=False
    )
    earlier_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    later_report_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False
    )
    gap_months: Mapped[int] = mapped_column(Integer, nullable=False)
    is_transition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    company: Mapped["Company"] = relationship()  # noqa: F821
    earlier_report: Mapped["Report"] = relationship(foreign_keys=[earlier_report_id])  # noqa: F821
    later_report: Mapped["Report"] = relationship(foreign_keys=[later_report_id])  # noqa: F821

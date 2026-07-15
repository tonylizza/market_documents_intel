from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin


class Company(UUIDPkMixin, TimestampMixin, Base):
    __tablename__ = "companies"

    ticker: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    company_name: Mapped[str] = mapped_column(String(255), nullable=False)
    sector: Mapped[str | None] = mapped_column(String(128), nullable=True)

    reports: Mapped[list["Report"]] = relationship(  # noqa: F821
        back_populates="company", cascade="all, delete-orphan"
    )

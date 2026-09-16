import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    AlignmentConfidence,
    AnalyticalDecisionRunStatus,
    AnalyticalMode,
    NormalizedSchedule,
)


class AnalyticalDecisionRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at routing every `SemanticUnitAlignment` produced by one
    `SemanticUnitAlignmentRun` to an analytical comparison mode (Track 7C.3,
    docs/7c3-analytical-eligibility-and-lexical-comparison.md).

    Pins the source `SemanticUnitAlignmentRun` so a result stays
    reproducible even after realignment, mirroring
    `SemanticUnitAlignmentRun` pinning its source `SemanticUnitRun`s.
    "Current successful" is a query-time rule (see
    `services.analytical_eligibility.get_current_decision_run`), never a
    stored flag.
    """

    __tablename__ = "analytical_decision_runs"
    __table_args__ = (
        Index("ix_analytical_decision_runs_pair_schedule_status", "report_pair_id", "schedule", "status"),
        Index("ix_analytical_decision_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    schedule: Mapped[NormalizedSchedule] = mapped_column(
        SAEnum(NormalizedSchedule, name="normalized_schedule", create_type=False), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[AnalyticalDecisionRunStatus] = mapped_column(
        SAEnum(AnalyticalDecisionRunStatus, name="analytical_decision_run_status"),
        nullable=False,
        default=AnalyticalDecisionRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs
    # (one or more NOT_ELIGIBLE decisions) -- error_message is reserved for
    # FAILED runs that never produced any decision row.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    alignment_run: Mapped["SemanticUnitAlignmentRun"] = relationship()  # noqa: F821
    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    decisions: Mapped[list["AnalyticalDecision"]] = relationship(
        back_populates="decision_run", cascade="all, delete-orphan"
    )


class AnalyticalDecision(UUIDPkMixin, TimestampMixin, Base):
    """One routing outcome for one `SemanticUnitAlignment`, produced by one
    `AnalyticalDecisionRun`.

    Answers "how should this aligned unit be compared" -- never "how much
    did it change" (that is `LexicalUnitComparison`, and only exists for
    `analytical_mode == LEXICAL_ONLY`). A `SemanticUnitAlignment` with
    status UNRESOLVED_UPSTREAM or AMBIGUOUS never gets a row here at all:
    those states are not trustworthy enough to license any analytical
    claim, substantive-absence or otherwise. See
    docs/7c3-analytical-eligibility-and-lexical-comparison.md.
    """

    __tablename__ = "analytical_decisions"
    __table_args__ = (
        UniqueConstraint(
            "decision_run_id", "semantic_unit_alignment_id", name="uq_analytical_decisions_run_alignment"
        ),
        Index("ix_analytical_decisions_run_id", "decision_run_id"),
        Index("ix_analytical_decisions_alignment_id", "semantic_unit_alignment_id"),
        Index("ix_analytical_decisions_mode", "decision_run_id", "analytical_mode"),
    )

    decision_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analytical_decision_runs.id", ondelete="CASCADE"), nullable=False
    )
    semantic_unit_alignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_alignments.id", ondelete="CASCADE"), nullable=False
    )

    analytical_mode: Mapped[AnalyticalMode] = mapped_column(
        SAEnum(AnalyticalMode, name="analytical_mode"), nullable=False
    )
    # Reuses `AlignmentConfidence` (HIGH/MEDIUM/LOW/NEEDS_REVIEW), same
    # reasoning as `SemanticUnitAlignment.confidence`: a generic four-level
    # scale with no comparison-specific meaning, so a duplicate enum would
    # add a parallel type for no behavioral reason.
    confidence: Mapped[AlignmentConfidence] = mapped_column(
        SAEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    # Populated only for NOT_ELIGIBLE (no eligibility config found) -- an
    # explicit prompt for a human to add or correct configuration, never a
    # guess at what the config should have been.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    decision_run: Mapped["AnalyticalDecisionRun"] = relationship(back_populates="decisions")
    semantic_unit_alignment: Mapped["SemanticUnitAlignment"] = relationship()  # noqa: F821
    lexical_comparison: Mapped["LexicalUnitComparison | None"] = relationship(
        back_populates="analytical_decision", cascade="all, delete-orphan", uselist=False
    )


class LexicalUnitComparison(UUIDPkMixin, TimestampMixin, Base):
    """Raw, interpretable lexical-change metrics for one `LEXICAL_ONLY`
    `AnalyticalDecision`.

    Reuses the exact metric functions validated in
    `services.similarity_metrics`/`services.similarity_tokenization` --
    no new metric math, no composite score, no threshold, no materiality
    label. Every similarity field is nullable and left `NULL` (never a
    fabricated 0.0) when the underlying metric is mathematically
    undefined for these inputs. See
    docs/7c3-analytical-eligibility-and-lexical-comparison.md.
    """

    __tablename__ = "lexical_unit_comparisons"
    __table_args__ = (
        UniqueConstraint("analytical_decision_id", name="uq_lexical_unit_comparisons_decision"),
        Index("ix_lexical_unit_comparisons_alignment_id", "semantic_unit_alignment_id"),
    )

    analytical_decision_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("analytical_decisions.id", ondelete="CASCADE"), nullable=False
    )
    semantic_unit_alignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semantic_unit_alignments.id", ondelete="CASCADE"), nullable=False
    )

    tfidf_cosine: Mapped[float | None] = mapped_column(Float, nullable=True)
    unigram_jaccard: Mapped[float | None] = mapped_column(Float, nullable=True)
    bigram_jaccard: Mapped[float | None] = mapped_column(Float, nullable=True)
    edit_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    sequence_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)

    earlier_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    later_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_change: Mapped[int] = mapped_column(Integer, nullable=False)
    word_count_change_pct: Mapped[float | None] = mapped_column(Float, nullable=True)

    analytical_decision: Mapped["AnalyticalDecision"] = relationship(back_populates="lexical_comparison")
    semantic_unit_alignment: Mapped["SemanticUnitAlignment"] = relationship()  # noqa: F821

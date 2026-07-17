import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import FeatureQuality, FeatureRunStatus, SimilarityResultQuality


class FeatureRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at computing disclosure-change features for a ReportPair.

    Mirrors `SimilarityRun`/`AlignmentRun`: a pair may have many feature runs
    over time; the "current" result is a query-time rule (see
    `services.feature_extraction.get_current_feature_run`), never a stored
    flag. `similarity_run_id`/`alignment_run_id` pin the exact upstream runs
    used, so a result stays reproducible even after either is recomputed --
    identical pinned run IDs plus an identical configuration hash is what
    idempotent skipping checks against.
    """

    __tablename__ = "feature_runs"
    __table_args__ = (
        Index("ix_feature_runs_pair_status", "report_pair_id", "status"),
        Index("ix_feature_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    similarity_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("similarity_runs.id", ondelete="CASCADE"), nullable=False
    )
    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alignment_runs.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    feature_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[FeatureRunStatus] = mapped_column(
        SAEnum(FeatureRunStatus, name="feature_run_status"),
        nullable=False,
        default=FeatureRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Distinct from `error_message`: set on COMPLETED_WITH_WARNINGS runs,
    # mirroring `AlignmentRun.review_reason` -- error_message is reserved for
    # FAILED runs that never produced a ReportPairFeatures row at all.
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    similarity_run: Mapped["SimilarityRun"] = relationship()  # noqa: F821
    alignment_run: Mapped["AlignmentRun"] = relationship()  # noqa: F821
    report_pair_features: Mapped["ReportPairFeatures | None"] = relationship(
        back_populates="feature_run", cascade="all, delete-orphan", uselist=False
    )


class ReportPairFeatures(UUIDPkMixin, TimestampMixin, Base):
    """Disclosure-change features and derived signal for one successful FeatureRun.

    One-to-one with a FeatureRun that COMPLETED (with or without warnings) --
    a FAILED run never gets one, matching the `DocumentSimilarity`/
    `PassageAlignment` convention. Every raw and derived value is stored
    independently and is `None` when it could not be computed -- never a
    fabricated 0. "All-passage" fields aggregate every primary alignment row
    regardless of size; "eligible_*" fields exclude low-information passages
    per `FeatureConfig` -- both are always populated so neither silently
    stands in for the other.
    """

    __tablename__ = "report_pair_features"
    __table_args__ = (
        Index("ix_report_pair_features_report_pair_id", "report_pair_id"),
        Index("ix_report_pair_features_quality", "feature_quality"),
        Index("ix_report_pair_features_primary_eligible", "primary_eligible"),
    )

    feature_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_runs.id", ondelete="CASCADE"), nullable=False, unique=True
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

    # --- Document-level inputs (raw, from DocumentSimilarity) ---
    document_cosine_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_bigram_jaccard: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_edit_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_diff_similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_word_change_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_metric_disagreement_spread: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Reuses the `similarity_result_quality` PostgreSQL enum type created by
    # M3's migration -- `create_type=False` prevents SQLAlchemy from trying
    # (and failing) to CREATE TYPE it again for this table.
    document_quality: Mapped[SimilarityResultQuality | None] = mapped_column(
        PGEnum(SimilarityResultQuality, name="similarity_result_quality", create_type=False), nullable=True
    )
    document_primary_eligible: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Document-level change transforms (spec item G) ---
    document_cosine_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_bigram_jaccard_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_edit_similarity_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_diff_similarity_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    document_word_change_ratio_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Passage population (all-passage, raw, from segmentation) ---
    earlier_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    later_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    aligned_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    lightly_modified_count: Mapped[int] = mapped_column(Integer, nullable=False)
    substantially_modified_count: Mapped[int] = mapped_column(Integer, nullable=False)
    new_count: Mapped[int] = mapped_column(Integer, nullable=False)
    removed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    ambiguous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    high_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    medium_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    low_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    needs_review_confidence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_embedding_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    skipped_embedding_count_later: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Length-aware totals (all-passage, raw) ---
    earlier_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    later_word_count: Mapped[int] = mapped_column(Integer, nullable=False)
    unchanged_words: Mapped[float] = mapped_column(Float, nullable=False)
    lightly_modified_words: Mapped[float] = mapped_column(Float, nullable=False)
    substantially_modified_words: Mapped[float] = mapped_column(Float, nullable=False)
    new_words: Mapped[float] = mapped_column(Float, nullable=False)
    removed_words: Mapped[float] = mapped_column(Float, nullable=False)
    ambiguous_words: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Feature-eligible population (low-information passages excluded per FeatureConfig) ---
    eligible_earlier_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_later_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_aligned_passage_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_unchanged_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_lightly_modified_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_substantially_modified_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_new_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_removed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_ambiguous_count: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_unchanged_words: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_lightly_modified_words: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_substantially_modified_words: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_new_words: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_removed_words: Mapped[float] = mapped_column(Float, nullable=False)
    eligible_ambiguous_words: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Excluded low-information / heading-fragment diagnostics ---
    excluded_low_information_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_low_information_words: Mapped[float] = mapped_column(Float, nullable=False)
    excluded_heading_fragment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_heading_fragment_words: Mapped[float] = mapped_column(Float, nullable=False)
    heading_fragment_share_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    heading_fragment_share_later: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Derived rates (feature-eligible population) ---
    unchanged_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    lightly_modified_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    substantially_modified_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    removed_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    ambiguous_rate_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    unchanged_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    lightly_modified_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    substantially_modified_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    new_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    removed_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    ambiguous_rate_words: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Quality and coverage ---
    alignment_coverage_count: Mapped[float | None] = mapped_column(Float, nullable=True)
    alignment_coverage_words: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedded_coverage_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    embedded_coverage_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    high_confidence_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_required_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    irregular_gap: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reporting_gap_months: Mapped[int] = mapped_column(Integer, nullable=False)
    transition_report: Mapped[bool] = mapped_column(Boolean, nullable=False)

    feature_quality: Mapped[FeatureQuality] = mapped_column(
        SAEnum(FeatureQuality, name="feature_quality"), nullable=False
    )
    primary_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    exclusion_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    warning_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Composite disclosure-change score ---
    disclosure_change_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_version: Mapped[str] = mapped_column(String(64), nullable=False)
    score_unchanged_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_lightly_modified_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_substantially_modified_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_new_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_removed_component: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_ambiguous_component: Mapped[float | None] = mapped_column(Float, nullable=True)

    feature_run: Mapped["FeatureRun"] = relationship(back_populates="report_pair_features")

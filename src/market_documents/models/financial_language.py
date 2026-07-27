import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from market_documents.db.base import Base, TimestampMixin, UUIDPkMixin
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentStatus,
    LanguageSignalQuality,
    LanguageSignalRunStatus,
    PassageType,
    ReportSide,
)


class FinancialLanguageDictionary(UUIDPkMixin, TimestampMixin, Base):
    """One imported term dictionary (e.g. Loughran-McDonald, or this
    project's own custom domain taxonomy).

    `source_hash` is a SHA-256 of the exact file supplied at import time --
    the licensed Loughran-McDonald CSV is never committed to the repository
    (mirrors "raw PDFs remain outside Docker images"); `source_path` records
    where it was imported from purely for lineage, not as a live reference.
    `term_count` is a cheap denormalized rollup, computed once at import,
    mirroring `AlignmentRun`'s status-count rollups.
    """

    __tablename__ = "financial_language_dictionaries"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_financial_language_dictionaries_name_version"),)

    name: Mapped[str] = mapped_column(String(128), nullable=False)
    version: Mapped[str] = mapped_column(String(64), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_notes: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    term_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    terms: Mapped[list["FinancialLanguageTerm"]] = relationship(
        back_populates="dictionary", cascade="all, delete-orphan"
    )


class FinancialLanguageTerm(UUIDPkMixin, Base):
    """One (term, category) row. A normalized term may legitimately appear in
    more than one category (e.g. a Loughran-McDonald word tagged both
    `strong_modal` and `positive`) -- each combination is its own row, never
    collapsed into a multi-valued column.

    `normalized_term` is the tokenizer-normalized form (NFKC + lowercase,
    same pipeline as `similarity_tokenization.tokenize`) used at match time;
    `term` preserves the original source spelling for display/audit.
    `phrase_token_count` is precomputed so phrase matching can sort
    longest-first without re-splitting every term on every passage.
    """

    __tablename__ = "financial_language_terms"
    __table_args__ = (
        UniqueConstraint(
            "dictionary_id", "normalized_term", "category", name="uq_financial_language_terms_dict_term_category"
        ),
        Index("ix_financial_language_terms_dictionary_id", "dictionary_id"),
        Index("ix_financial_language_terms_normalized_term", "normalized_term"),
        Index("ix_financial_language_terms_category", "category"),
    )

    dictionary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_language_dictionaries.id", ondelete="CASCADE"), nullable=False
    )
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_term: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str | None] = mapped_column(String(64), nullable=True)
    polarity: Mapped[str | None] = mapped_column(String(16), nullable=True)
    weight: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    is_phrase: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    phrase_token_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    dictionary: Mapped["FinancialLanguageDictionary"] = relationship(back_populates="terms")


class LanguageSignalRun(UUIDPkMixin, TimestampMixin, Base):
    """One attempt at computing financial-language signals for a ReportPair.

    Directly parallels `FeatureRun`: pins the exact upstream `FeatureRun` and
    `AlignmentRun` used (so a result stays reproducible even after either is
    recomputed), plus the dictionary used. "Current" is a query-time rule
    (see `services.financial_language_signals.get_current_language_signal_run`),
    never a stored flag. `error_message` (not the milestone brief's
    `failure_reason`) matches `FeatureRun`/`AlignmentRun` naming: reserved for
    FAILED runs that produced no `ReportPairLanguageFeatures` row at all;
    `review_reason` is for COMPLETED_WITH_WARNINGS runs.
    """

    __tablename__ = "language_signal_runs"
    __table_args__ = (
        Index("ix_language_signal_runs_pair_status", "report_pair_id", "status"),
        Index("ix_language_signal_runs_pair_completed_at", "report_pair_id", "completed_at"),
    )

    report_pair_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("report_pairs.id", ondelete="CASCADE"), nullable=False
    )
    feature_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("feature_runs.id", ondelete="CASCADE"), nullable=False
    )
    alignment_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("alignment_runs.id", ondelete="CASCADE"), nullable=False
    )
    dictionary_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("financial_language_dictionaries.id", ondelete="CASCADE"), nullable=False
    )

    algorithm_version: Mapped[str] = mapped_column(String(64), nullable=False)
    signal_version: Mapped[str] = mapped_column(String(64), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    status: Mapped[LanguageSignalRunStatus] = mapped_column(
        SAEnum(LanguageSignalRunStatus, name="language_signal_run_status"),
        nullable=False,
        default=LanguageSignalRunStatus.PENDING,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    report_pair: Mapped["ReportPair"] = relationship()  # noqa: F821
    feature_run: Mapped["FeatureRun"] = relationship()  # noqa: F821
    alignment_run: Mapped["AlignmentRun"] = relationship()  # noqa: F821
    dictionary: Mapped["FinancialLanguageDictionary"] = relationship()
    passage_signals: Mapped[list["PassageLanguageSignal"]] = relationship(
        back_populates="language_signal_run", cascade="all, delete-orphan"
    )
    pair_features: Mapped["ReportPairLanguageFeatures | None"] = relationship(
        back_populates="language_signal_run", cascade="all, delete-orphan", uselist=False
    )


class PassageLanguageSignal(UUIDPkMixin, TimestampMixin, Base):
    """Dictionary/taxonomy hit counts for one passage-side of one accepted
    `PassageAlignment` row, scoped to a single `LanguageSignalRun`.

    One row per (run, alignment row, side) that has a passage on that side --
    a NEW row has only a `LATER` signal, a REMOVED row only an `EARLIER`
    signal, matched/AMBIGUOUS rows can have one row per present side.
    `structured_content_category` snapshots `structured_content_audit.
    classify_passage`'s result at build time (see
    `financial_language_config.STRUCTURED_CONTENT_RULE_VERSION`, which is
    folded into `LanguageSignalRun.configuration_hash` precisely so a later
    audit-rule change forces a fresh run rather than a stale snapshot).
    Every count is raw (never negation-adjusted) except `negated_hit_count`,
    which is tracked independently -- no category is ever auto-reversed.
    """

    __tablename__ = "passage_language_signals"
    __table_args__ = (
        UniqueConstraint(
            "language_signal_run_id", "passage_alignment_id", "report_side",
            name="uq_passage_language_signals_run_alignment_side",
        ),
        Index("ix_passage_language_signals_run_id", "language_signal_run_id"),
        Index("ix_passage_language_signals_passage_id", "passage_id"),
        Index("ix_passage_language_signals_alignment_status", "language_signal_run_id", "alignment_status"),
    )

    language_signal_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("language_signal_runs.id", ondelete="CASCADE"), nullable=False
    )
    passage_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passages.id", ondelete="CASCADE"), nullable=False
    )
    passage_alignment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_alignments.id", ondelete="CASCADE"), nullable=False
    )
    report_side: Mapped[ReportSide] = mapped_column(SAEnum(ReportSide, name="report_side"), nullable=False)

    alignment_status: Mapped[AlignmentStatus] = mapped_column(
        PGEnum(AlignmentStatus, name="alignment_status", create_type=False), nullable=False
    )
    confidence: Mapped[AlignmentConfidence] = mapped_column(
        PGEnum(AlignmentConfidence, name="alignment_confidence", create_type=False), nullable=False
    )
    passage_type: Mapped[PassageType] = mapped_column(
        PGEnum(PassageType, name="passage_type", create_type=False), nullable=False
    )
    passage_word_count: Mapped[int] = mapped_column(Integer, nullable=False)

    structured_content_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    primary_narrative_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    feature_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)

    positive_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negative_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uncertainty_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    litigious_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    constraining_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    strong_modal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    weak_modal_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negated_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_dictionary_hits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    category_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    language_signal_run: Mapped["LanguageSignalRun"] = relationship(back_populates="passage_signals")
    passage: Mapped["Passage"] = relationship()  # noqa: F821
    passage_alignment: Mapped["PassageAlignment"] = relationship()  # noqa: F821
    category_hits: Mapped[list["PassageLanguageCategoryHit"]] = relationship(
        back_populates="passage_language_signal", cascade="all, delete-orphan"
    )


class PassageLanguageCategoryHit(UUIDPkMixin, Base):
    """Sparse per-(category, subcategory) hit counts from the custom domain
    taxonomy (risk / financial condition / governance / strategy) for one
    `PassageLanguageSignal`.

    Kept as a normalized child table rather than the 42-subcategory-wide
    sparse row that a fully typed-column design would require, and rather
    than JSON, since query/aggregation ergonomics matter more here than for
    a one-off audit blob -- most passages have zero rows here (no custom-
    taxonomy hit), so total volume stays a small fraction of the passage
    count, unlike the estimated `PassageLanguageTermMatch` volume this
    project deliberately did not persist as a table.
    """

    __tablename__ = "passage_language_category_hits"
    __table_args__ = (
        UniqueConstraint(
            "passage_language_signal_id", "category", "subcategory",
            name="uq_passage_language_category_hits_signal_category",
        ),
        Index("ix_passage_language_category_hits_signal_id", "passage_language_signal_id"),
    )

    passage_language_signal_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("passage_language_signals.id", ondelete="CASCADE"), nullable=False
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    subcategory: Mapped[str] = mapped_column(String(64), nullable=False)
    hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    negated_hit_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    passage_language_signal: Mapped["PassageLanguageSignal"] = relationship(back_populates="category_hits")


class ReportPairLanguageFeatures(UUIDPkMixin, TimestampMixin, Base):
    """Pair-level financial-language change signal for one successful
    `LanguageSignalRun` -- one-to-one, same convention as `ReportPairFeatures`
    (never created for a FAILED run).

    Every population's counts/words are stored independently (all_passages,
    primary_narrative, plus the list/table-context/currency-exposure/
    uncertain sensitivity variants) so comparisons never require rerunning
    anything. Core-category rates are per-1,000-analyzed-words; `None` (never
    a fabricated `0.0`) when the population's word count is zero.
    """

    __tablename__ = "report_pair_language_features"
    __table_args__ = (
        Index("ix_report_pair_language_features_report_pair_id", "report_pair_id"),
        Index("ix_report_pair_language_features_quality", "language_signal_quality"),
        Index("ix_report_pair_language_features_primary_eligible", "primary_eligible"),
    )

    language_signal_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("language_signal_runs.id", ondelete="CASCADE"), nullable=False, unique=True
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

    # --- Population counts/words (spec item: "Population counts") ---
    all_passages_earlier_count: Mapped[int] = mapped_column(Integer, nullable=False)
    all_passages_later_count: Mapped[int] = mapped_column(Integer, nullable=False)
    all_passages_earlier_words: Mapped[int] = mapped_column(Integer, nullable=False)
    all_passages_later_words: Mapped[int] = mapped_column(Integer, nullable=False)

    primary_narrative_earlier_count: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_narrative_later_count: Mapped[int] = mapped_column(Integer, nullable=False)
    primary_narrative_earlier_words: Mapped[float] = mapped_column(Float, nullable=False)
    primary_narrative_later_words: Mapped[float] = mapped_column(Float, nullable=False)

    excluded_structured_content_count: Mapped[int] = mapped_column(Integer, nullable=False)
    excluded_structured_content_words: Mapped[float] = mapped_column(Float, nullable=False)

    list_content_count: Mapped[int] = mapped_column(Integer, nullable=False)
    list_content_words: Mapped[float] = mapped_column(Float, nullable=False)
    table_context_count: Mapped[int] = mapped_column(Integer, nullable=False)
    table_context_words: Mapped[float] = mapped_column(Float, nullable=False)
    currency_exposure_mixed_count: Mapped[int] = mapped_column(Integer, nullable=False)
    currency_exposure_mixed_words: Mapped[float] = mapped_column(Float, nullable=False)
    uncertain_count: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertain_words: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Sensitivity-variant primary-narrative words (spec: population variants) ---
    primary_narrative_words_excluding_lists: Mapped[float] = mapped_column(Float, nullable=False)
    primary_narrative_words_excluding_table_context: Mapped[float] = mapped_column(Float, nullable=False)
    primary_narrative_words_excluding_currency_exposure_mixed: Mapped[float] = mapped_column(Float, nullable=False)
    primary_narrative_words_excluding_uncertain: Mapped[float] = mapped_column(Float, nullable=False)

    # --- Core-category earlier/later counts and per-1,000-word rates ---
    positive_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    negative_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    uncertainty_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    litigious_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    litigious_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    litigious_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    litigious_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    litigious_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    litigious_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    constraining_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    constraining_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    constraining_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    constraining_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    constraining_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    constraining_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    strong_modal_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    strong_modal_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    strong_modal_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    strong_modal_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    strong_modal_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    strong_modal_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    weak_modal_count_earlier: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_modal_count_later: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_modal_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    weak_modal_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    weak_modal_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    weak_modal_rate_change_abs: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Passage-status-specific hits (NEW/REMOVED/SUBSTANTIALLY_MODIFIED/AMBIGUOUS) ---
    positive_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    positive_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    negative_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    uncertainty_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    litigious_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    litigious_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    litigious_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    constraining_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    constraining_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    constraining_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    strong_modal_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    strong_modal_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    strong_modal_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_modal_hits_new: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_modal_hits_removed: Mapped[int] = mapped_column(Integer, nullable=False)
    weak_modal_hits_ambiguous: Mapped[int] = mapped_column(Integer, nullable=False)

    substantially_modified_positive_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    substantially_modified_negative_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    substantially_modified_uncertainty_rate_change: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Confidence-filtered populations ---
    high_confidence_dictionary_hits: Mapped[int] = mapped_column(Integer, nullable=False)
    high_and_medium_confidence_dictionary_hits: Mapped[int] = mapped_column(Integer, nullable=False)

    # --- Derived measures ---
    net_tone_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_tone_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    net_tone_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertainty_intensity_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_language_introduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    negative_language_removal: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_language_introduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    positive_language_removal: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_language_introduction: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_language_removal: Mapped[float | None] = mapped_column(Float, nullable=True)
    forward_looking_caution_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    governance_language_change: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_condition_language_change: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Custom-taxonomy earlier/later/change (combined across subcategories) ---
    risk_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_condition_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    financial_condition_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    governance_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    governance_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    strategy_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Quality and coverage ---
    analyzed_word_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    primary_narrative_coverage: Mapped[float | None] = mapped_column(Float, nullable=True)
    dictionary_match_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Per-side dictionary coverage (Milestone 6 recalibration) -- previously
    # computed only transiently inside quality assessment; now persisted so
    # `report_side_signal_quality`'s dictionary-coverage banding
    # (`financial_language_config.dictionary_match_rate_anomalous_threshold`
    # / `_borderline_threshold`) is auditable without rebuilding.
    dictionary_match_rate_earlier: Mapped[float | None] = mapped_column(Float, nullable=True)
    dictionary_match_rate_later: Mapped[float | None] = mapped_column(Float, nullable=True)
    list_content_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    uncertain_content_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Share (by word) of the *alignment-eligible* population classified
    # AMBIGUOUS -- an `alignment_change_signal_quality` input only.
    # AMBIGUOUS rows are still included in report-side earlier/later totals
    # (see `ambiguous_words_in_report_side` below); this field never gates
    # `report_side_signal_quality`.
    ambiguous_alignment_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Share (by word) of aligned rows at LOW/NEEDS_REVIEW confidence.
    # Retained as a descriptive/audit field only -- Milestone 6
    # recalibration replaced its use as an `alignment_change_signal_quality`
    # gate with the more precise `collision_flagged_word_share` /
    # `ambiguous_alignment_share` decomposition (most of this corpus's
    # NEEDS_REVIEW confidence is collision-driven non-uniqueness, not a
    # demonstrated mismatch -- see Milestone 6 calibration audit).
    low_confidence_share: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Alignment-change-specific coverage (Milestone 6 recalibration) ---
    # Share (by word, alignment-eligible population) whose accepted
    # correspondence was flagged non-unique by candidate-collision detection
    # (see `financial_language_metrics.classify_collision`) -- collision is
    # never automatically treated as a wrong match, only as reduced
    # attribution confidence.
    collision_flagged_word_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Share (by word) with no alignment counterpart at all (NEW + REMOVED) --
    # informational: high turnover is a legitimate report characteristic,
    # not evidence of a bad match.
    unmatched_word_share: Mapped[float | None] = mapped_column(Float, nullable=True)
    # The five persisted alignment-change analytical populations (spec:
    # "Provide and persist at least" all five). `_excl_ambiguous` is the
    # selected default (see `financial_language_quality` module docstring
    # for why HIGH/MEDIUM-only is deliberately *not* the default).
    alignment_change_analyzed_words_all: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alignment_change_analyzed_words_excl_ambiguous: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alignment_change_analyzed_words_hml: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alignment_change_analyzed_words_hm: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    alignment_change_analyzed_words_h: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # Words from AMBIGUOUS-status rows included in the report-side
    # earlier/later totals above -- an audit count only (spec: "Preserve an
    # audit count showing how many words came from AMBIGUOUS alignment
    # rows"). Report-side totals include these rows by design: a passage's
    # own text and dictionary hits are valid regardless of whether a unique
    # counterpart could be proven on the other side.
    ambiguous_words_in_report_side: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # --- Independent quality/eligibility (Milestone 6 recalibration) ---
    # Confidence in report-level lexical measurements (category rates, net
    # tone, custom-taxonomy rates) -- never depends on alignment confidence,
    # candidate collisions, or one-to-one match uniqueness. See
    # `financial_language_quality.assess_report_side_quality`.
    report_side_signal_quality: Mapped[LanguageSignalQuality] = mapped_column(
        SAEnum(LanguageSignalQuality, name="language_signal_quality"), nullable=False
    )
    report_side_primary_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    report_side_warning_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_side_exclusion_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Confidence in exact passage-to-passage attribution (NEW/REMOVED
    # attribution, SUBSTANTIALLY_MODIFIED before/after deltas) -- depends on
    # alignment confidence, ambiguity, and collision share. See
    # `financial_language_quality.assess_alignment_change_quality`.
    alignment_change_signal_quality: Mapped[LanguageSignalQuality] = mapped_column(
        SAEnum(LanguageSignalQuality, name="language_signal_quality"), nullable=False
    )
    alignment_change_primary_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    alignment_change_warning_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    alignment_change_exclusion_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Deprecated composite fields (backward compatibility only) ---
    # `language_signal_quality` = the stricter (more conservative) of
    # `report_side_signal_quality`/`alignment_change_signal_quality`;
    # `primary_eligible` = `report_side_primary_eligible AND
    # alignment_change_primary_eligible`; `warning_reasons`/
    # `exclusion_reasons` = both layers' reasons concatenated, each prefixed
    # `[report-side]`/`[alignment-change]`. New code should read the
    # independent `report_side_*`/`alignment_change_*` fields directly --
    # these four exist only so pre-recalibration consumers (CLI, exports)
    # keep working against a defined, non-ambiguous value, never a silently
    # different meaning of the same column name.
    language_signal_quality: Mapped[LanguageSignalQuality] = mapped_column(
        SAEnum(LanguageSignalQuality, name="language_signal_quality"), nullable=False
    )
    primary_eligible: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    warning_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)
    exclusion_reasons: Mapped[str | None] = mapped_column(Text, nullable=True)

    language_signal_run: Mapped["LanguageSignalRun"] = relationship(back_populates="pair_features")

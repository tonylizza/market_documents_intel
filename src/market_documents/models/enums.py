import enum


class MetadataStatus(str, enum.Enum):
    DISCOVERED = "DISCOVERED"
    INSPECTED = "INSPECTED"
    VALIDATED = "VALIDATED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    REJECTED = "REJECTED"


class MetadataSource(str, enum.Enum):
    DIRECTORY = "DIRECTORY"
    FILENAME = "FILENAME"
    PDF = "PDF"
    MANUAL = "MANUAL"


class ExtractionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class ExtractionQuality(str, enum.Enum):
    GOOD = "GOOD"
    USABLE = "USABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class SimilarityRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class SimilarityResultQuality(str, enum.Enum):
    GOOD = "GOOD"
    USABLE = "USABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class DiffMode(str, enum.Enum):
    """Which SequenceMatcher configuration (if any) produced diff_similarity.

    FULL_AUTOJUNK is preserved as a named, config-selectable mode even
    though the current policy never chooses it automatically (benchmarking
    on real report text showed autojunk=True can shift the score by up to
    0.15 -- too unpredictable to use as a silent fallback). SKIPPED_TOKEN_LIMIT
    means diff_similarity is None because at least one document exceeded
    `SimilarityConfig.diff_token_threshold`, not because of a calculation
    failure.
    """

    FULL_NO_AUTOJUNK = "FULL_NO_AUTOJUNK"
    FULL_AUTOJUNK = "FULL_AUTOJUNK"
    SKIPPED_TOKEN_LIMIT = "SKIPPED_TOKEN_LIMIT"


class BlockType(str, enum.Enum):
    PARAGRAPH = "PARAGRAPH"
    HEADING_CANDIDATE = "HEADING_CANDIDATE"
    LIST_ITEM = "LIST_ITEM"
    TABLE_LIKE = "TABLE_LIKE"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    NUMERIC_FRAGMENT = "NUMERIC_FRAGMENT"
    DECORATIVE_OR_FRAGMENT = "DECORATIVE_OR_FRAGMENT"
    OVERLAPPING_TEXT_ARTIFACT = "OVERLAPPING_TEXT_ARTIFACT"
    TABLE_HEADER_FRAGMENT = "TABLE_HEADER_FRAGMENT"
    UNKNOWN = "UNKNOWN"


class PassageSegmentationRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class EmbeddingRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class AlignmentRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class PassageType(str, enum.Enum):
    HEADING_WITH_BODY = "HEADING_WITH_BODY"
    PARAGRAPH = "PARAGRAPH"
    MULTI_PARAGRAPH = "MULTI_PARAGRAPH"
    LIST = "LIST"
    TABLE_CONTEXT = "TABLE_CONTEXT"
    OTHER = "OTHER"


class AlignmentStatus(str, enum.Enum):
    UNCHANGED = "UNCHANGED"
    LIGHTLY_MODIFIED = "LIGHTLY_MODIFIED"
    SUBSTANTIALLY_MODIFIED = "SUBSTANTIALLY_MODIFIED"
    NEW = "NEW"
    REMOVED = "REMOVED"
    AMBIGUOUS = "AMBIGUOUS"


class AlignmentType(str, enum.Enum):
    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_TWO = "ONE_TO_TWO"
    TWO_TO_ONE = "TWO_TO_ONE"
    UNMATCHED_EARLIER = "UNMATCHED_EARLIER"
    UNMATCHED_LATER = "UNMATCHED_LATER"


class AlignmentConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    NEEDS_REVIEW = "NEEDS_REVIEW"


class AlignmentMatchSource(str, enum.Enum):
    """Provenance of one PassageAlignment correspondence.

    PRIMARY covers every row produced by the primary semantic/lexical
    matcher (the only source before Milestone 2). The two
    EXACT_HASH_RECONCILIATION_* values distinguish a correspondence the
    primary matcher failed to make but a deterministic post-pass recovered
    from exact `content_hash` equality among already-unmatched REMOVED/NEW
    passages -- UNIQUE when exactly one unmatched passage existed on each
    side for that hash, DUPLICATE_CLUSTER when position/anchor evidence was
    needed to choose among several identical occurrences. See
    services/alignment_reconciliation.py and
    docs/exact-hash-reconciliation-experiment.md.
    """

    PRIMARY = "PRIMARY"
    EXACT_HASH_RECONCILIATION_UNIQUE = "EXACT_HASH_RECONCILIATION_UNIQUE"
    EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER = "EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER"


class FeatureRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class FeatureQuality(str, enum.Enum):
    GOOD = "GOOD"
    USABLE = "USABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class LanguageSignalRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class LanguageSignalQuality(str, enum.Enum):
    GOOD = "GOOD"
    USABLE = "USABLE"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    FAILED = "FAILED"


class ReportSide(str, enum.Enum):
    EARLIER = "EARLIER"
    LATER = "LATER"


# --------------------------------------------------------------------------
# Track 7C.1: schedule localization + headed narrative semantic units.
#
# Parallel replacement track (see docs/7c1-schedule-localization-plan.md):
# built entirely alongside the existing passage-segmentation/alignment/
# feature pipeline above, reusing only Report/ExtractionRun/Page/TextBlock
# read-only. 7C.1 implements exactly one schedule (FINANCIAL_PERFORMANCE)
# and one semantic-unit type (HEADED_NARRATIVE_UNIT); it stops at
# source-faithful reconstruction and provenance -- no cross-year alignment,
# no comparison of any kind. NormalizedSchedule names the full validated
# ten-schedule taxonomy for future convenience, but `schedule_localization.
# localize_schedule` rejects any value other than FINANCIAL_PERFORMANCE
# explicitly (NotImplementedError), not silently.
# --------------------------------------------------------------------------


class NormalizedSchedule(str, enum.Enum):
    CEO_REVIEW = "CEO_REVIEW"
    CHAIR_REVIEW = "CHAIR_REVIEW"
    FINANCIAL_PERFORMANCE = "FINANCIAL_PERFORMANCE"
    MATERIAL_RISKS = "MATERIAL_RISKS"
    STRATEGY = "STRATEGY"
    OUTLOOK = "OUTLOOK"
    CORPORATE_GOVERNANCE = "CORPORATE_GOVERNANCE"
    REMUNERATION = "REMUNERATION"
    LEGAL_REGULATORY = "LEGAL_REGULATORY"
    MATERIAL_MATTERS_OPERATING_ENVIRONMENT = "MATERIAL_MATTERS_OPERATING_ENVIRONMENT"


class ScheduleLocalizationRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class ScheduleLocalizationStatus(str, enum.Enum):
    FOUND_PRIMARY_ONLY = "FOUND_PRIMARY_ONLY"
    FOUND_PRIMARY_AND_SUPPORTING = "FOUND_PRIMARY_AND_SUPPORTING"
    DISTRIBUTED_NO_CLEAR_PRIMARY = "DISTRIBUTED_NO_CLEAR_PRIMARY"
    NOT_FOUND = "NOT_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class BoundaryConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class SemanticUnitRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class SemanticUnitType(str, enum.Enum):
    """Only HEADED_NARRATIVE_UNIT is implemented in 7C.1 -- one member
    because that's all this milestone needs, not the start of a broad
    ontology."""

    HEADED_NARRATIVE_UNIT = "HEADED_NARRATIVE_UNIT"


class SemanticUnitBoundaryStrategy(str, enum.Enum):
    NEXT_HEADING = "NEXT_HEADING"
    ANCHOR_SENTENCE = "ANCHOR_SENTENCE"


class SemanticUnitBoundaryStatus(str, enum.Enum):
    """Whether an end boundary was actually resolved -- kept independent of
    *how confidently* it was resolved (see `BoundaryConfidence`, reused by
    `SemanticUnit.boundary_confidence`). A unit with UNRESOLVED here always
    has `end_page`/`source_text`/`boundary_confidence` set to NULL; nothing
    is ever fabricated or partially guessed to fill those columns."""

    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"


# --------------------------------------------------------------------------
# Track 7C.1a: canonical PDF source representation.
#
# A source-faithful, block/line/span-granular capture of one report's raw
# PDF, built directly from PyMuPDF's own `get_text("dict")` output and
# persisted alongside (never in place of) the legacy Page/TextBlock layer
# (see `services.extraction`). Exists specifically because the 7C.1
# real-corpus acceptance run (docs/implementation/track-7c1-acceptance.md
# Sections 2.4 and 4.3) found the legacy TextBlock layer to be lossy (BEL
# 2020's Gross Margin paragraph is entirely absent from persisted
# TextBlock rows despite being present in the raw PDF) and under-structured
# (ACT's CFO-review sub-headings cannot be distinguished from schedule
# boundaries without font/hierarchy signal TextBlock never captured). No
# classification, cleaning, or heuristic interpretation happens at this
# layer -- see `models.pdf_source` and `services.pdf_source_extraction`.
# --------------------------------------------------------------------------


class CanonicalExtractionStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


# --------------------------------------------------------------------------
# Track 7C.2: cross-year semantic-unit alignment.
#
# Determines correspondence between persisted SemanticUnit records across
# an adjacent-year ReportPair -- never how much a matched pair's text
# changed (that is 7C.3). Reads only SemanticUnit/SemanticUnitRun; never
# Passage, PassageAlignment, or legacy TextBlock. See
# docs/7c2-semantic-unit-alignment.md.
# --------------------------------------------------------------------------


class SemanticUnitAlignmentRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class SemanticUnitAlignmentStatus(str, enum.Enum):
    """Cross-year correspondence outcome for one semantic unit.

    UNRESOLVED_UPSTREAM covers every case where a unit's status on either
    side is not trustworthy enough to call a genuine disclosure event: a
    boundary that exists but never resolved, or a unit_key with no row at
    all in a run that itself completed with warnings. ADDED/REMOVED are
    reserved for the case where the *other* side's SemanticUnitRun
    completed with zero warnings -- proof every unit configured for that
    run was cleanly accounted for -- so a missing counterpart there is
    confirmed absence, not an extraction limitation. AMBIGUOUS is for more
    than one plausible normalized-heading candidate on either side; never
    guessed.

    RENAMED is declared but not currently emitted:
    `services.semantic_unit_alignment.align_units` only matches a
    different unit_key across years via normalized-heading equality, and a
    heading that survives that normalization is indistinguishable from
    cosmetic formatting noise -- calling it a genuine rename would need
    evidence this deterministic cascade doesn't have. Reserved for a future
    milestone with real evidence to justify it.
    """

    MATCHED = "MATCHED"
    RENAMED = "RENAMED"
    ADDED = "ADDED"
    REMOVED = "REMOVED"
    UNRESOLVED_UPSTREAM = "UNRESOLVED_UPSTREAM"
    AMBIGUOUS = "AMBIGUOUS"


# --------------------------------------------------------------------------
# Track 7C.3: analytical eligibility routing + lexical comparison.
#
# Determines how a MATCHED/RENAMED SemanticUnitAlignment should be compared
# -- and, for LEXICAL_ONLY only, computes the validated lexical metrics.
# ADDED/REMOVED/STRUCTURED_COMPARISON_PREFERRED/LEXICAL_WITH_NUMERIC_CONTEXT
# are represented as routing outcomes only; no comparison engine exists yet
# for them. UNRESOLVED_UPSTREAM/AMBIGUOUS alignments never reach a decision
# at all -- see docs/7c3-analytical-eligibility-and-lexical-comparison.md.
# --------------------------------------------------------------------------


class AnalyticalDecisionRunStatus(str, enum.Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    FAILED = "FAILED"


class AnalyticalMode(str, enum.Enum):
    """Comparison routing outcome for one aligned semantic unit, per the
    comparison-type taxonomy validated in
    docs/experiments/annual-report-analytical-unit-eligibility.md. Only
    LEXICAL_ONLY is executed by `services.lexical_unit_comparison` in
    7C.3 -- the others are declared routing outcomes with no comparison
    engine behind them yet.
    """

    LEXICAL_ONLY = "LEXICAL_ONLY"
    LEXICAL_WITH_NUMERIC_CONTEXT = "LEXICAL_WITH_NUMERIC_CONTEXT"
    STRUCTURED_COMPARISON_PREFERRED = "STRUCTURED_COMPARISON_PREFERRED"
    PRESENCE_STATUS_ONLY = "PRESENCE_STATUS_ONLY"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"

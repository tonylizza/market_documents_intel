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

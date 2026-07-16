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

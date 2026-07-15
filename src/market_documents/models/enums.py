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

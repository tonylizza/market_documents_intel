class MarketDocumentsError(Exception):
    """Base class for domain-specific errors."""


class PdfDecryptionError(MarketDocumentsError):
    """The PDF is encrypted and could not be opened without a user-supplied secret."""


class PdfExtractionError(MarketDocumentsError):
    """The PDF could not be opened or read, for reasons other than encryption."""


class PairNotEligibleError(MarketDocumentsError):
    """A ReportPair cannot currently be scored (missing or empty narrative, failed extraction quality)."""


class AlignmentNotEligibleError(MarketDocumentsError):
    """A ReportPair cannot currently be passage-aligned (missing/incompatible segmentation or embedding runs)."""

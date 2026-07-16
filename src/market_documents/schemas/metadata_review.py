"""Pydantic schemas for the human-reviewable metadata-remediation workflow.

The export CSV (`services.metadata_review.MetadataReviewExportRow`, a plain
dataclass -- no validation needed for output we generate ourselves) and this
reviewed import row are deliberately separate types: export carries
detection evidence a human reads, import carries only what a human decided,
plus enough validation to catch mistakes before they ever reach the
database. `ReviewerStatus` and `DetectionConfidence` are schema-layer
concepts only -- neither is a persisted Postgres enum, since a report's
reviewed status lives in the CSV artifact, not the database (see
`services/metadata_review.py` for why).
"""

import enum
import uuid
from datetime import date

from pydantic import BaseModel, model_validator

REPORTING_MONTHS_TOLERANCE = 1


class ReviewerStatus(str, enum.Enum):
    UNREVIEWED = "UNREVIEWED"
    CONFIRMED = "CONFIRMED"
    CORRECTED = "CORRECTED"
    REJECTED = "REJECTED"
    NEEDS_FURTHER_REVIEW = "NEEDS_FURTHER_REVIEW"


class DetectionConfidence(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    NONE = "NONE"


APPLICABLE_REVIEWER_STATUSES = (ReviewerStatus.CONFIRMED, ReviewerStatus.CORRECTED)


def _month_span(start: date, end: date) -> int:
    return (end.year - start.year) * 12 + (end.month - start.month)


class MetadataReviewImportRow(BaseModel):
    """One row of the human-reviewed CSV consumed by `reports metadata-review-import`.

    Only CONFIRMED/CORRECTED rows are ever applied by the import service;
    UNREVIEWED, REJECTED, and NEEDS_FURTHER_REVIEW rows pass schema
    validation (they are still well-formed CSV data) but are skipped by the
    service layer, never written to the database.
    """

    report_id: uuid.UUID
    reviewer_status: ReviewerStatus
    proposed_period_start: date | None = None
    proposed_period_end: date | None = None
    proposed_publication_date: date | None = None
    proposed_reporting_months: int | None = None
    proposed_transition_report: bool = False
    reviewer_notes: str | None = None

    @model_validator(mode="after")
    def _validate_confirmed_or_corrected(self) -> "MetadataReviewImportRow":
        if self.reviewer_status not in APPLICABLE_REVIEWER_STATUSES:
            return self

        if self.proposed_period_end is None:
            raise ValueError(
                f"proposed_period_end is required when reviewer_status is {self.reviewer_status.value}"
            )

        if self.proposed_period_start is not None and self.proposed_period_start > self.proposed_period_end:
            raise ValueError("proposed_period_start must not be after proposed_period_end")

        if self.proposed_reporting_months is not None and self.proposed_period_start is not None:
            actual_months = _month_span(self.proposed_period_start, self.proposed_period_end)
            if abs(actual_months - self.proposed_reporting_months) > REPORTING_MONTHS_TOLERANCE:
                raise ValueError(
                    f"proposed_reporting_months ({self.proposed_reporting_months}) is inconsistent "
                    f"with the proposed period interval (~{actual_months} months, "
                    f"tolerance {REPORTING_MONTHS_TOLERANCE})"
                )

        return self

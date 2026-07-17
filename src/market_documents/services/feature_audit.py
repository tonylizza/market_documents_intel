"""Corpus-level disclosure-change feature audit rows.

Mirrors `alignment_audit.py`/`similarity_audit.py`: every field is optional
and simply blank when the corresponding data doesn't exist yet (pairs not
yet feature-built, failed latest runs). Produces the audit CSVs required by
Milestone 5: `feature_run_audit.csv`, `report_pair_feature_review.csv`,
`feature_component_summary.csv`, `excluded_passages_summary.csv`, and
`irregular_gap_pairs.csv`.
"""

import csv
import statistics
from dataclasses import dataclass, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.report_pair import ReportPair
from market_documents.services.feature_config import FEATURE_CONFIG
from market_documents.services.feature_extraction import (
    get_current_feature_runs_by_pair,
    get_current_report_pair_features_by_pair,
)


def _write_csv(rows: list, row_type: type, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(row_type)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# feature_run_audit.csv / report_pair_feature_review.csv / irregular_gap_pairs.csv
# --------------------------------------------------------------------------


@dataclass
class FeatureRunAuditRow:
    ticker: str
    report_pair_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    gap_months: int
    is_transition: bool
    irregular_gap: bool | None
    status: str | None
    feature_quality: str | None
    primary_eligible: bool | None
    disclosure_change_score: float | None
    alignment_coverage_words: float | None
    embedded_coverage_earlier: float | None
    embedded_coverage_later: float | None
    ambiguous_rate_words: float | None
    excluded_low_information_count: int | None
    excluded_low_information_words: float | None
    algorithm_version: str | None
    feature_version: str | None
    configuration_hash: str | None
    warning_reasons: str | None
    exclusion_reasons: str | None


def build_feature_run_audit_rows(session: Session) -> list[FeatureRunAuditRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(
            joinedload(ReportPair.company),
            joinedload(ReportPair.earlier_report),
            joinedload(ReportPair.later_report),
        )
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()

    pair_ids = [p.id for p in pairs]
    current_runs = get_current_feature_runs_by_pair(session, pair_ids)
    features_by_pair = get_current_report_pair_features_by_pair(session, pair_ids)

    rows: list[FeatureRunAuditRow] = []
    for pair in pairs:
        run = current_runs.get(pair.id)
        feat = features_by_pair.get(pair.id)
        rows.append(
            FeatureRunAuditRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                earlier_period_end=(
                    pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None
                ),
                later_period_end=(
                    pair.later_report.period_end.isoformat() if pair.later_report.period_end else None
                ),
                gap_months=pair.gap_months,
                is_transition=pair.is_transition,
                irregular_gap=feat.irregular_gap if feat else None,
                status=run.status.value if run else None,
                feature_quality=feat.feature_quality.value if feat else None,
                primary_eligible=feat.primary_eligible if feat else None,
                disclosure_change_score=feat.disclosure_change_score if feat else None,
                alignment_coverage_words=feat.alignment_coverage_words if feat else None,
                embedded_coverage_earlier=feat.embedded_coverage_earlier if feat else None,
                embedded_coverage_later=feat.embedded_coverage_later if feat else None,
                ambiguous_rate_words=feat.ambiguous_rate_words if feat else None,
                excluded_low_information_count=feat.excluded_low_information_count if feat else None,
                excluded_low_information_words=feat.excluded_low_information_words if feat else None,
                algorithm_version=run.algorithm_version if run else None,
                feature_version=run.feature_version if run else None,
                configuration_hash=run.configuration_hash if run else None,
                warning_reasons=run.review_reason if run else None,
                exclusion_reasons=feat.exclusion_reasons if feat else None,
            )
        )
    return rows


def write_feature_run_audit_csv(rows: list[FeatureRunAuditRow], output_path: Path) -> None:
    _write_csv(rows, FeatureRunAuditRow, output_path)


def build_feature_review_rows(session: Session) -> list[FeatureRunAuditRow]:
    """Pairs needing manual attention: not yet built, mechanically failed or
    warned, NEEDS_REVIEW/FAILED quality, or excluded from primary ranking."""
    rows = build_feature_run_audit_rows(session)
    return [
        row
        for row in rows
        if row.status is None
        or row.status in ("FAILED", "COMPLETED_WITH_WARNINGS")
        or row.feature_quality in ("NEEDS_REVIEW", "FAILED")
        or row.primary_eligible is False
    ]


def write_feature_review_csv(rows: list[FeatureRunAuditRow], output_path: Path) -> None:
    _write_csv(rows, FeatureRunAuditRow, output_path)


def build_irregular_gap_rows(session: Session) -> list[FeatureRunAuditRow]:
    """Pairs whose reporting gap falls outside the configured primary
    annual window -- computed directly from `ReportPair.gap_months` so it
    is available even before features are built."""
    rows = build_feature_run_audit_rows(session)
    return [
        row
        for row in rows
        if row.gap_months < FEATURE_CONFIG.primary_gap_months_min
        or row.gap_months > FEATURE_CONFIG.primary_gap_months_max
    ]


def write_irregular_gap_csv(rows: list[FeatureRunAuditRow], output_path: Path) -> None:
    _write_csv(rows, FeatureRunAuditRow, output_path)


# --------------------------------------------------------------------------
# feature_component_summary.csv
# --------------------------------------------------------------------------


@dataclass
class ComponentSummaryRow:
    metric: str
    count: int
    minimum: float | None
    median: float | None
    maximum: float | None
    mean: float | None


_SUMMARY_METRICS = [
    "disclosure_change_score",
    "unchanged_rate_words",
    "lightly_modified_rate_words",
    "substantially_modified_rate_words",
    "new_rate_words",
    "removed_rate_words",
    "ambiguous_rate_words",
    "alignment_coverage_count",
    "alignment_coverage_words",
    "embedded_coverage_earlier",
    "embedded_coverage_later",
    "heading_fragment_share_earlier",
    "heading_fragment_share_later",
    "high_confidence_share",
    "review_required_share",
    "document_cosine_similarity",
    "document_metric_disagreement_spread",
]


def build_feature_component_summary_rows(session: Session) -> list[ComponentSummaryRow]:
    pair_ids = list(session.scalars(select(ReportPair.id)).all())
    features_by_pair = get_current_report_pair_features_by_pair(session, pair_ids)
    features = list(features_by_pair.values())

    rows: list[ComponentSummaryRow] = []
    for metric in _SUMMARY_METRICS:
        values = [v for v in (getattr(f, metric) for f in features) if v is not None]
        rows.append(
            ComponentSummaryRow(
                metric=metric,
                count=len(values),
                minimum=min(values) if values else None,
                median=statistics.median(values) if values else None,
                maximum=max(values) if values else None,
                mean=statistics.mean(values) if values else None,
            )
        )
    return rows


def write_feature_component_summary_csv(rows: list[ComponentSummaryRow], output_path: Path) -> None:
    _write_csv(rows, ComponentSummaryRow, output_path)


# --------------------------------------------------------------------------
# excluded_passages_summary.csv
# --------------------------------------------------------------------------


@dataclass
class ExcludedPassagesSummaryRow:
    ticker: str
    report_pair_id: str
    earlier_passage_count: int | None
    later_passage_count: int | None
    aligned_passage_count: int | None
    eligible_aligned_passage_count: int | None
    excluded_low_information_count: int | None
    excluded_low_information_words: float | None
    excluded_heading_fragment_count: int | None
    excluded_heading_fragment_words: float | None
    heading_fragment_share_earlier: float | None
    heading_fragment_share_later: float | None


def build_excluded_passages_summary_rows(session: Session) -> list[ExcludedPassagesSummaryRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(joinedload(ReportPair.company))
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker)
    ).all()
    pair_ids = [p.id for p in pairs]
    features_by_pair = get_current_report_pair_features_by_pair(session, pair_ids)

    rows: list[ExcludedPassagesSummaryRow] = []
    for pair in pairs:
        feat = features_by_pair.get(pair.id)
        rows.append(
            ExcludedPassagesSummaryRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                earlier_passage_count=feat.earlier_passage_count if feat else None,
                later_passage_count=feat.later_passage_count if feat else None,
                aligned_passage_count=feat.aligned_passage_count if feat else None,
                eligible_aligned_passage_count=feat.eligible_aligned_passage_count if feat else None,
                excluded_low_information_count=feat.excluded_low_information_count if feat else None,
                excluded_low_information_words=feat.excluded_low_information_words if feat else None,
                excluded_heading_fragment_count=feat.excluded_heading_fragment_count if feat else None,
                excluded_heading_fragment_words=feat.excluded_heading_fragment_words if feat else None,
                heading_fragment_share_earlier=feat.heading_fragment_share_earlier if feat else None,
                heading_fragment_share_later=feat.heading_fragment_share_later if feat else None,
            )
        )
    return rows


def write_excluded_passages_summary_csv(rows: list[ExcludedPassagesSummaryRow], output_path: Path) -> None:
    _write_csv(rows, ExcludedPassagesSummaryRow, output_path)

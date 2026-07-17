"""Deterministic manual-review sampling across all current disclosure-change
feature results.

Mirrors `review_sample.py` (M4) at ReportPair granularity instead of
alignment-row granularity: each category is sampled independently using the
same seeded shuffle-then-take approach, so the same corpus state always
produces the same sample. Two categories (lowest/highest disclosure-change
score) are rank-based rather than predicate-based and are handled
separately.
"""

import csv
import random
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.company import Company
from market_documents.models.feature import ReportPairFeatures
from market_documents.models.report_pair import ReportPair
from market_documents.services.feature_extraction import get_current_report_pair_features_by_pair

DEFAULT_SEED = 42
DEFAULT_PER_CATEGORY = 3

_DOMINANT_FIELDS = {
    "unchanged": "unchanged_rate_words",
    "lightly_modified": "lightly_modified_rate_words",
    "substantially_modified": "substantially_modified_rate_words",
    "new": "new_rate_words",
    "removed": "removed_rate_words",
    "ambiguous": "ambiguous_rate_words",
}


@dataclass
class FeatureReviewSampleRow:
    category: str
    ticker: str
    report_pair_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    gap_months: int
    is_transition: bool
    irregular_gap: bool
    feature_quality: str
    primary_eligible: bool
    disclosure_change_score: float | None
    unchanged_rate_words: float | None
    lightly_modified_rate_words: float | None
    substantially_modified_rate_words: float | None
    new_rate_words: float | None
    removed_rate_words: float | None
    ambiguous_rate_words: float | None
    high_confidence_share: float | None
    review_required_share: float | None
    heading_fragment_share_earlier: float | None
    heading_fragment_share_later: float | None
    embedded_coverage_earlier: float | None
    embedded_coverage_later: float | None
    document_metric_disagreement_spread: float | None
    warning_reasons: str | None
    exclusion_reasons: str | None


def _dominant_category(feat: ReportPairFeatures) -> str | None:
    values = {name: getattr(feat, field_name) for name, field_name in _DOMINANT_FIELDS.items()}
    values = {name: v for name, v in values.items() if v is not None}
    if not values:
        return None
    return max(values, key=lambda name: values[name])


def _category_predicates() -> dict[str, Callable[[ReportPairFeatures, ReportPair], bool]]:
    return {
        "dominant_unchanged": lambda f, p: _dominant_category(f) == "unchanged",
        "dominant_lightly_modified": lambda f, p: _dominant_category(f) == "lightly_modified",
        "dominant_substantially_modified": lambda f, p: _dominant_category(f) == "substantially_modified",
        "dominant_new": lambda f, p: _dominant_category(f) == "new",
        "dominant_removed": lambda f, p: _dominant_category(f) == "removed",
        "dominant_ambiguous": lambda f, p: _dominant_category(f) == "ambiguous",
        "high_confidence": lambda f, p: (f.high_confidence_share or 0.0) >= 0.75,
        "low_confidence": lambda f, p: (f.review_required_share or 0.0) >= 0.25,
        "ambiguous_present": lambda f, p: f.ambiguous_count > 0,
        "high_heading_fragment_share": lambda f, p: (
            max(f.heading_fragment_share_earlier or 0.0, f.heading_fragment_share_later or 0.0) >= 0.25
        ),
        "low_embedding_coverage": lambda f, p: (
            min(
                f.embedded_coverage_earlier if f.embedded_coverage_earlier is not None else 1.0,
                f.embedded_coverage_later if f.embedded_coverage_later is not None else 1.0,
            )
            < 0.80
        ),
        "irregular_gap": lambda f, p: f.irregular_gap,
        "document_metric_disagreement": lambda f, p: (f.document_metric_disagreement_spread or 0.0) > 0.4,
    }


def _build_row(category: str, pair: ReportPair, feat: ReportPairFeatures) -> FeatureReviewSampleRow:
    return FeatureReviewSampleRow(
        category=category,
        ticker=pair.company.ticker,
        report_pair_id=str(pair.id),
        earlier_period_end=pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None,
        later_period_end=pair.later_report.period_end.isoformat() if pair.later_report.period_end else None,
        gap_months=pair.gap_months,
        is_transition=pair.is_transition,
        irregular_gap=feat.irregular_gap,
        feature_quality=feat.feature_quality.value,
        primary_eligible=feat.primary_eligible,
        disclosure_change_score=feat.disclosure_change_score,
        unchanged_rate_words=feat.unchanged_rate_words,
        lightly_modified_rate_words=feat.lightly_modified_rate_words,
        substantially_modified_rate_words=feat.substantially_modified_rate_words,
        new_rate_words=feat.new_rate_words,
        removed_rate_words=feat.removed_rate_words,
        ambiguous_rate_words=feat.ambiguous_rate_words,
        high_confidence_share=feat.high_confidence_share,
        review_required_share=feat.review_required_share,
        heading_fragment_share_earlier=feat.heading_fragment_share_earlier,
        heading_fragment_share_later=feat.heading_fragment_share_later,
        embedded_coverage_earlier=feat.embedded_coverage_earlier,
        embedded_coverage_later=feat.embedded_coverage_later,
        document_metric_disagreement_spread=feat.document_metric_disagreement_spread,
        warning_reasons=feat.warning_reasons,
        exclusion_reasons=feat.exclusion_reasons,
    )


def build_feature_review_sample(
    session: Session, *, seed: int = DEFAULT_SEED, per_category: int = DEFAULT_PER_CATEGORY
) -> list[FeatureReviewSampleRow]:
    """Deterministic, seeded sample of feature results for manual review.

    Each category is sampled independently (a pair can appear in more than
    one category). Uses a plain `random.Random(seed)` shuffle-then-take, so
    the same corpus state always produces the same sample.
    """
    pairs = session.scalars(
        select(ReportPair)
        .options(
            joinedload(ReportPair.company),
            joinedload(ReportPair.earlier_report),
            joinedload(ReportPair.later_report),
        )
        .join(Company, ReportPair.company_id == Company.id)
    ).all()
    pairs_by_id = {p.id: p for p in pairs}
    features_by_pair = get_current_report_pair_features_by_pair(session, list(pairs_by_id))

    if not features_by_pair:
        return []

    rows: list[FeatureReviewSampleRow] = []

    scored = sorted(
        ((pid, f) for pid, f in features_by_pair.items() if f.disclosure_change_score is not None),
        key=lambda item: (item[1].disclosure_change_score, str(item[0])),
    )
    for pid, feat in scored[:per_category]:
        rows.append(_build_row("low_disclosure_change_score", pairs_by_id[pid], feat))
    for pid, feat in scored[-per_category:]:
        rows.append(_build_row("high_disclosure_change_score", pairs_by_id[pid], feat))

    rng = random.Random(seed)
    predicates = _category_predicates()
    for category, predicate in predicates.items():
        matches = [(pid, feat) for pid, feat in features_by_pair.items() if predicate(feat, pairs_by_id[pid])]
        matches_sorted = sorted(matches, key=lambda item: str(item[0]))  # stable order before seeded shuffle
        rng.shuffle(matches_sorted)
        for pid, feat in matches_sorted[:per_category]:
            rows.append(_build_row(category, pairs_by_id[pid], feat))

    return rows


def write_feature_review_sample_csv(rows: list[FeatureReviewSampleRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(FeatureReviewSampleRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))

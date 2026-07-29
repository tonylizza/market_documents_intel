"""Milestone 7A.1 follow-up: "review-qualified disclosure-change
publication". Covers the requirement that a NEEDS_REVIEW-quality
`disclosure_change_score` is still published (with its own quality made
explicit) rather than silently withheld, while remaining excluded from
primary discovery rankings.

Builds a real pair via `_feature_fixtures.build_ready_pair` + a real
`build_features` call (so the pinned lineage and score computation are
genuine), then directly overrides the persisted `ReportPairFeatures.
feature_quality`/`primary_eligible` fields to exercise each quality tier --
`assess_feature_quality` itself is already covered by the Milestone 3/6
test suite; this module tests only how the publisher *responds* to a given
quality value.
"""

import sys
import uuid
from pathlib import Path

import pytest
from sqlalchemy import select, inspect

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from _feature_fixtures import build_ready_pair  # noqa: E402

from market_documents.models.enums import FeatureQuality
from market_documents.publishing import labels
from market_documents.publishing.models import (
    DiscoveryItem,
    Publication,
    PublicationStatus,
    ReportComparison,
)
from market_documents.publishing.publisher import PublicationBuilder
from market_documents.services.feature_extraction import build_features, get_current_report_pair_features

# A materially different later_text (vs. the default matched-passage text)
# so `disclosure_change_score` clears the discovery/finding materiality
# epsilon -- `build_ready_pair`'s default earlier_text==later_text produces
# an UNCHANGED pair with a near-zero score, which would fail discovery
# eligibility on materiality grounds alone, independent of quality/primary_
# eligible gating.
_CHANGED_LATER_TEXT = " ".join(f"newmaterial{i}" for i in range(250))


def _build_pair_with_quality(
    db_session, ticker: str, *, quality: FeatureQuality, primary_eligible: bool, later_text: str | None = None
):
    pair, _alignment_outcome, _similarity_outcome = build_ready_pair(
        db_session, ticker=ticker, later_text=later_text or _CHANGED_LATER_TEXT
    )
    build_features(db_session, pair)
    db_session.flush()

    features = get_current_report_pair_features(db_session, pair.id)
    features.feature_quality = quality
    features.primary_eligible = primary_eligible
    db_session.flush()
    return pair, features


def _comparison_for(app_db_session, publication_id, source_report_pair_id) -> ReportComparison:
    return app_db_session.scalar(
        select(ReportComparison).where(
            ReportComparison.publication_id == publication_id,
            ReportComparison.source_report_pair_id == source_report_pair_id,
        )
    )


# ---------------------------------------------------------------------------
# Pure-logic unit tests (no DB)
# ---------------------------------------------------------------------------


def test_score_displayed_true_for_needs_review_with_score():
    assert labels.disclosure_change_score_displayed("NEEDS_REVIEW", 0.5) is True


def test_score_displayed_true_for_good_and_usable():
    assert labels.disclosure_change_score_displayed("GOOD", 0.5) is True
    assert labels.disclosure_change_score_displayed("USABLE", 0.5) is True


def test_score_displayed_false_when_quality_failed():
    assert labels.disclosure_change_score_displayed("FAILED", 0.9) is False


def test_score_displayed_false_when_score_is_none():
    assert labels.disclosure_change_score_displayed("GOOD", None) is False
    assert labels.disclosure_change_score_displayed("NEEDS_REVIEW", None) is False


def test_needs_review_still_maps_to_a_plain_language_label():
    assert labels.quality_label("NEEDS_REVIEW", "generic") == "Review recommended"
    assert labels.quality_label("FAILED", "generic") == "Unavailable"
    assert labels.quality_label("GOOD", "generic") == "Analysis ready"
    assert labels.quality_label("USABLE", "generic") == "Ready with caution"


# ---------------------------------------------------------------------------
# Integration tests against a real built publication
# ---------------------------------------------------------------------------


def test_needs_review_score_is_visible_and_correctly_labeled(db_session, app_db_session):
    pair, features = _build_pair_with_quality(
        db_session, ticker="DCQ1", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    raw_score = features.disclosure_change_score
    assert raw_score is not None  # sanity: fixture actually produced a score

    publication = PublicationBuilder(publication_version="test-dcq-1").build(db_session, app_db_session)
    assert publication.status == PublicationStatus.READY.value, publication.failure_reason

    comp = _comparison_for(app_db_session, publication.id, pair.id)
    assert comp.disclosure_change_score == raw_score
    assert comp.disclosure_change_label is not None
    assert comp.disclosure_change_quality == "NEEDS_REVIEW"
    assert comp.disclosure_change_quality_label == "Review recommended"


def test_needs_review_primary_eligible_remains_false(db_session, app_db_session):
    pair, _features = _build_pair_with_quality(
        db_session, ticker="DCQ2", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    publication = PublicationBuilder(publication_version="test-dcq-2").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)
    assert comp.disclosure_change_primary_eligible is False


def test_non_primary_score_excluded_from_discovery_ranking(db_session, app_db_session):
    pair, _features = _build_pair_with_quality(
        db_session, ticker="DCQ3", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    publication = PublicationBuilder(publication_version="test-dcq-3").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)

    feature_gated_items = list(
        app_db_session.scalars(
            select(DiscoveryItem).where(
                DiscoveryItem.publication_id == publication.id,
                DiscoveryItem.report_comparison_id == comp.id,
                DiscoveryItem.discovery_type.in_(("largest_overall_change", "largest_new_disclosure_share")),
            )
        )
    )
    assert feature_gated_items == []


def test_good_quality_score_is_primary_eligible_and_labeled(db_session, app_db_session):
    pair, _features = _build_pair_with_quality(
        db_session, ticker="DCQ4", quality=FeatureQuality.GOOD, primary_eligible=True
    )
    publication = PublicationBuilder(publication_version="test-dcq-4").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)

    assert comp.disclosure_change_score is not None
    assert comp.disclosure_change_quality == "GOOD"
    assert comp.disclosure_change_quality_label == "Analysis ready"
    assert comp.disclosure_change_primary_eligible is True
    assert comp.disclosure_change_label is not None


def test_good_quality_primary_eligible_score_is_discovery_eligible(db_session, app_db_session):
    # `build_ready_pair`'s scoring engine can legitimately net a full
    # passage swap to a low/zero disclosure_change_score (turnover
    # components can cancel), which would fail this test on materiality
    # grounds alone -- override the persisted score directly, the same
    # technique already used above for quality/primary_eligible, so this
    # test isolates the publisher's discovery-ranking behavior rather than
    # depending on the M3 scoring engine's internals.
    pair, features = _build_pair_with_quality(
        db_session, ticker="DCQ5", quality=FeatureQuality.GOOD, primary_eligible=True
    )
    features.disclosure_change_score = 0.85
    db_session.flush()

    publication = PublicationBuilder(publication_version="test-dcq-5").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)

    items = list(
        app_db_session.scalars(
            select(DiscoveryItem).where(
                DiscoveryItem.publication_id == publication.id,
                DiscoveryItem.report_comparison_id == comp.id,
                DiscoveryItem.discovery_type == "largest_overall_change",
            )
        )
    )
    assert len(items) >= 1


def test_null_score_publishes_all_related_fields_as_none(db_session, app_db_session):
    pair, features = _build_pair_with_quality(
        db_session, ticker="DCQ6", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    features.disclosure_change_score = None
    db_session.flush()

    publication = PublicationBuilder(publication_version="test-dcq-6").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)

    assert comp.disclosure_change_score is None
    assert comp.disclosure_change_label is None
    assert comp.disclosure_change_percentile is None
    # Quality/eligibility are independent of score availability -- still recorded.
    assert comp.disclosure_change_quality == "NEEDS_REVIEW"
    assert comp.disclosure_change_primary_eligible is False


def test_failed_quality_suppresses_score_even_if_raw_value_present(db_session, app_db_session):
    pair, features = _build_pair_with_quality(
        db_session, ticker="DCQ7", quality=FeatureQuality.FAILED, primary_eligible=False
    )
    assert features.disclosure_change_score is not None  # raw value genuinely present upstream

    publication = PublicationBuilder(publication_version="test-dcq-7").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)

    assert comp.disclosure_change_score is None
    assert comp.disclosure_change_label is None
    assert comp.disclosure_change_quality == "FAILED"
    assert comp.disclosure_change_quality_label == "Unavailable"


def test_no_finding_invented_when_score_null(db_session, app_db_session):
    pair, features = _build_pair_with_quality(
        db_session, ticker="DCQ8", quality=FeatureQuality.GOOD, primary_eligible=True
    )
    features.disclosure_change_score = None
    db_session.flush()

    publication = PublicationBuilder(publication_version="test-dcq-8").build(db_session, app_db_session)
    comp = _comparison_for(app_db_session, publication.id, pair.id)
    assert comp.primary_finding_key != "largest_overall_change"


def test_deterministic_label_reproducible_across_rebuild(db_session, app_db_session):
    pair, _features = _build_pair_with_quality(
        db_session, ticker="DCQ9", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    version = "test-dcq-9-deterministic"
    first = PublicationBuilder(publication_version=version).build(db_session, app_db_session)
    comp_first = _comparison_for(app_db_session, first.id, pair.id)
    label_first, pct_first = comp_first.disclosure_change_label, comp_first.disclosure_change_percentile

    app_db_session.delete(app_db_session.get(Publication, first.id))
    app_db_session.flush()

    second = PublicationBuilder(publication_version=version).build(db_session, app_db_session)
    comp_second = _comparison_for(app_db_session, second.id, pair.id)

    assert comp_second.disclosure_change_label == label_first
    assert comp_second.disclosure_change_percentile == pct_first


def test_active_view_exposes_disclosure_change_quality_columns(app_engine):
    inspector = inspect(app_engine)
    columns = {c["name"] for c in inspector.get_columns("current_report_comparisons", schema="app")}
    assert {
        "disclosure_change_quality",
        "disclosure_change_quality_label",
        "disclosure_change_primary_eligible",
        "disclosure_change_warning",
    } <= columns


def test_historical_publication_preserved_after_new_build(db_session, app_db_session):
    pair_old, _features_old = _build_pair_with_quality(
        db_session, ticker="DCQOLD", quality=FeatureQuality.GOOD, primary_eligible=True
    )
    old_publication = PublicationBuilder(publication_version="test-dcq-historical-old").build(
        db_session, app_db_session
    )
    old_comparison_count = old_publication.comparison_count
    assert old_comparison_count == 1

    pair_new, _features_new = _build_pair_with_quality(
        db_session, ticker="DCQNEW", quality=FeatureQuality.NEEDS_REVIEW, primary_eligible=False
    )
    PublicationBuilder(publication_version="test-dcq-historical-new").build(db_session, app_db_session)

    # The old publication's own row is untouched by building a new one.
    refreshed_old = app_db_session.get(Publication, old_publication.id)
    assert refreshed_old is not None
    assert refreshed_old.comparison_count == old_comparison_count
    old_comp = _comparison_for(app_db_session, refreshed_old.id, pair_old.id)
    assert old_comp is not None
    assert old_comp.disclosure_change_quality == "GOOD"

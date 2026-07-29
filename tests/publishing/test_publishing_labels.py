import uuid

from market_documents.models.enums import (
    ExtractionQuality,
    FeatureQuality,
    LanguageSignalQuality,
    SimilarityResultQuality,
)
from market_documents.publishing import labels


def test_derive_id_deterministic_for_same_version():
    a = labels.derive_id("2026-07-27.1", "companies", "source-id-1")
    b = labels.derive_id("2026-07-27.1", "companies", "source-id-1")
    assert a == b
    assert isinstance(a, uuid.UUID)


def test_derive_id_differs_by_publication_version():
    a = labels.derive_id("2026-07-27.1", "companies", "source-id-1")
    b = labels.derive_id("2026-07-27.2", "companies", "source-id-1")
    assert a != b


def test_derive_id_differs_by_table():
    a = labels.derive_id("v1", "companies", "same-id")
    b = labels.derive_id("v1", "reports", "same-id")
    assert a != b


def test_derive_id_differs_by_source_id():
    a = labels.derive_id("v1", "companies", "id-1")
    b = labels.derive_id("v1", "companies", "id-2")
    assert a != b


def test_derive_id_sensitive_to_extra_discriminator_parts():
    a = labels.derive_id("v1", "language_metrics", "pair-1", "report_side", "positive")
    b = labels.derive_id("v1", "language_metrics", "pair-1", "alignment_change", "positive")
    assert a != b


def test_every_quality_enum_value_maps_to_a_report_side_label():
    for member in (ExtractionQuality, SimilarityResultQuality, FeatureQuality, LanguageSignalQuality):
        for value in member:
            assert labels.quality_label(value.value, "report_side") is not None, value


def test_every_quality_enum_value_maps_to_an_alignment_change_label():
    for member in (ExtractionQuality, SimilarityResultQuality, FeatureQuality, LanguageSignalQuality):
        for value in member:
            assert labels.quality_label(value.value, "alignment_change") is not None, value


def test_quality_label_none_passthrough():
    assert labels.quality_label(None, "report_side") is None


def test_publication_excluded_categories_is_narrower_than_primary_narrative_excluded():
    from market_documents.services.financial_language_metrics import PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES

    assert labels.PUBLICATION_EXCLUDED_CATEGORIES < PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES
    assert labels.PUBLICATION_EXCLUDED_CATEGORIES == {"short_fragment_invalid", "broken_fragment_sequence"}


def test_compute_percentile_bands_empty_values_returns_empty():
    assert labels.compute_percentile_bands("some_metric", []) == []


def test_compute_percentile_bands_single_value():
    bands = labels.compute_percentile_bands("some_metric", [2.0])
    assert len(bands) == 4
    assert bands[0].display_order == 0
    assert bands[-1].maximum_value == float("inf")


def test_label_for_signed_metric_none_value():
    bands = labels.compute_percentile_bands("m", [1.0, 2.0, 3.0])
    assert labels.label_for_signed_metric(None, bands) is None


def test_label_for_signed_metric_no_bands():
    assert labels.label_for_signed_metric(1.0, []) is None


def test_label_for_signed_metric_zero_is_no_change():
    bands = labels.compute_percentile_bands("m", [1.0, 2.0, 3.0])
    assert labels.label_for_signed_metric(0.0, bands) == "No change"


def test_label_for_signed_metric_direction_words():
    bands = labels.compute_percentile_bands("m", [1.0, 2.0, 3.0, 4.0, 5.0])
    assert "increase" in labels.label_for_signed_metric(5.0, bands)
    assert "decrease" in labels.label_for_signed_metric(-5.0, bands)


def test_label_for_unsigned_metric_no_direction_word():
    bands = labels.compute_percentile_bands("m", [0.1, 0.2, 0.3])
    label = labels.label_for_unsigned_metric(0.3, bands)
    assert label is not None
    assert "increase" not in label and "decrease" not in label
    assert label.endswith("change")


def test_confidence_label_known_values():
    assert labels.confidence_label("HIGH") == "High confidence"
    assert labels.confidence_label("NEEDS_REVIEW") == "Needs review"


def test_confidence_label_none():
    assert labels.confidence_label(None) is None

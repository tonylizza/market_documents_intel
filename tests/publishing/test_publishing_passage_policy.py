"""Passage publication policy: exactly `short_fragment_invalid` and
`broken_fragment_sequence` are excluded from publication; every other
`structured_content_audit` category (including `legitimate_short_
abbreviation`, which looks similar but has a coherent body) is published.

Reuses the same known-good `PassageAuditInput` examples as
`tests/test_structured_content_audit.py` rather than inventing new
(potentially fragile) text fixtures, since those already exercise the
exact classification rules this policy depends on.
"""

from market_documents.models.enums import PassageType
from market_documents.publishing.labels import PUBLICATION_EXCLUDED_CATEGORIES
from market_documents.services import structured_content_audit as sca
from market_documents.services.financial_language_metrics import PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES


def _classify(**kwargs) -> sca.Classification:
    defaults = dict(passage_id=None, block_types=())
    defaults.update(kwargs)
    return sca.classify_passage(sca.PassageAuditInput(**defaults))


def test_short_fragment_invalid_is_excluded_from_publication():
    result = _classify(
        raw_text="rs", heading_text="rs", word_count=1, passage_type=PassageType.HEADING_WITH_BODY
    )
    assert result.category == sca.SHORT_FRAGMENT_INVALID
    assert result.category in PUBLICATION_EXCLUDED_CATEGORIES


def test_broken_fragment_sequence_is_excluded_from_publication():
    text = "al\n\nRe\n\ngu\n\nlat\n\nors\n\nIn\n\ndu\n\nstr\n\ny b\n\nod\n\nies\n\nov\n\ner\n\nnm\n\nen\n\nEmployees"
    result = _classify(
        raw_text=text, heading_text="al", word_count=len(text.split()), passage_type=PassageType.HEADING_WITH_BODY
    )
    assert result.category == sca.BROKEN_FRAGMENT_SEQUENCE
    assert result.category in PUBLICATION_EXCLUDED_CATEGORIES


def test_legitimate_short_abbreviation_is_published_despite_short_heading():
    text = (
        "NC\n\nUsing natural resources is a key trade-off for generating value across the other capitals. "
        "We are continuously focusing on how we can minimise our impact."
    )
    result = _classify(
        raw_text=text, heading_text="NC", word_count=len(text.split()), passage_type=PassageType.HEADING_WITH_BODY
    )
    assert result.category == sca.LEGITIMATE_SHORT_ABBREVIATION
    assert result.category not in PUBLICATION_EXCLUDED_CATEGORIES
    # This category IS excluded from *feature/signal* eligibility scope --
    # confirms the two policies are genuinely independent, not aliases.
    assert result.category not in PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES


def test_financial_table_rendered_as_prose_is_published_but_feature_ineligible():
    # This category is feature-ineligible (in PRIMARY_NARRATIVE_EXCLUDED_
    # CATEGORIES) but still real, readable content -- must remain published.
    assert "financial_table_rendered_as_prose" in PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES
    assert "financial_table_rendered_as_prose" not in PUBLICATION_EXCLUDED_CATEGORIES


def test_publication_excluded_categories_are_a_strict_subset_of_feature_excluded():
    assert PUBLICATION_EXCLUDED_CATEGORIES < PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES
    assert len(PUBLICATION_EXCLUDED_CATEGORIES) == 2

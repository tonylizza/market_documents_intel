"""Pure unit tests for services/alignment_reconciliation.py.

No DB session needed: Passage objects are constructed directly (with an
explicit `id`, since the UUIDPkMixin default is only applied on flush) and
the module under test never touches the database.
"""

import uuid

import pytest

from market_documents.models.enums import AlignmentConfidence, AlignmentMatchSource, PassageType
from market_documents.models.passage import Passage
from market_documents.services.alignment_reconciliation import (
    _match_duplicate_cluster,
    _predicted_later_position,
    reconcile_exact_hash_duplicates,
)


def _passage(*, index: int, text: str, content_hash: str, heading: str | None = None) -> Passage:
    return Passage(
        id=uuid.uuid4(),
        passage_index=index,
        raw_text=text,
        normalized_text=text.lower(),
        content_hash=content_hash,
        first_page_number=1,
        last_page_number=1,
        word_count=len(text.split()),
        token_count=len(text.split()),
        character_count=len(text),
        heading_text=heading,
        passage_type=PassageType.HEADING_WITH_BODY if heading else PassageType.PARAGRAPH,
        excluded_from_alignment=False,
    )


HASH_A = "hash-a"
HASH_B = "hash-b"


# ---------------------------------------------------------------------------
# Tier 1: unique 1:1
# ---------------------------------------------------------------------------


def test_unique_1to1_reconciled():
    e = _passage(index=5, text="USD", content_hash=HASH_A)
    l = _passage(index=7, text="USD", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e], unmatched_later=[l], accepted_anchors=[], earlier_total=10, later_total=10
    )

    assert len(result) == 1
    pair = result[0]
    assert pair.earlier_passage is e
    assert pair.later_passage is l
    assert pair.match_source == AlignmentMatchSource.EXACT_HASH_RECONCILIATION_UNIQUE
    assert pair.confidence == AlignmentConfidence.HIGH


def test_different_hashes_never_reconciled():
    e = _passage(index=5, text="USD", content_hash=HASH_A)
    l = _passage(index=7, text="EUR", content_hash=HASH_B)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e], unmatched_later=[l], accepted_anchors=[], earlier_total=10, later_total=10
    )

    assert result == []


def test_no_reconciliation_when_pools_empty():
    assert reconcile_exact_hash_duplicates(
        unmatched_earlier=[], unmatched_later=[], accepted_anchors=[], earlier_total=0, later_total=0
    ) == []


# ---------------------------------------------------------------------------
# Tier 2: duplicate clusters
# ---------------------------------------------------------------------------


def test_2to2_stable_cluster_with_anchors():
    # Anchor A: earlier 0 <-> later 0. Anchor B: earlier 5 <-> later 5.
    # Two identical "X" passages sit between the anchors on both sides, in
    # the same relative order -- expect a stable local pairing.
    e1 = _passage(index=1, text="X", content_hash=HASH_A)
    e2 = _passage(index=2, text="X", content_hash=HASH_A)
    l1 = _passage(index=1, text="X", content_hash=HASH_A)
    l2 = _passage(index=2, text="X", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e1, e2],
        unmatched_later=[l1, l2],
        accepted_anchors=[(0, 0), (5, 5)],
        earlier_total=6,
        later_total=6,
    )

    pairs = {(r.earlier_passage.passage_index, r.later_passage.passage_index) for r in result}
    assert pairs == {(1, 1), (2, 2)}
    assert all(r.match_source == AlignmentMatchSource.EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER for r in result)
    assert all(r.confidence == AlignmentConfidence.MEDIUM for r in result)


def test_3to2_earlier_surplus_leaves_one_residual():
    e1 = _passage(index=1, text="X", content_hash=HASH_A)
    e2 = _passage(index=2, text="X", content_hash=HASH_A)
    e3 = _passage(index=3, text="X", content_hash=HASH_A)
    l1 = _passage(index=1, text="X", content_hash=HASH_A)
    l2 = _passage(index=2, text="X", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e1, e2, e3],
        unmatched_later=[l1, l2],
        accepted_anchors=[(0, 0), (4, 4)],
        earlier_total=5,
        later_total=5,
    )

    assert len(result) == 2
    matched_earlier_indices = {r.earlier_passage.passage_index for r in result}
    # Nearest-position matching should prefer 1<->1 and 2<->2, leaving
    # earlier index 3 (farthest from any later occurrence) unmatched.
    assert matched_earlier_indices == {1, 2}


def test_2to3_later_surplus_leaves_one_residual():
    e1 = _passage(index=1, text="X", content_hash=HASH_A)
    e2 = _passage(index=2, text="X", content_hash=HASH_A)
    l1 = _passage(index=1, text="X", content_hash=HASH_A)
    l2 = _passage(index=2, text="X", content_hash=HASH_A)
    l3 = _passage(index=3, text="X", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e1, e2],
        unmatched_later=[l1, l2, l3],
        accepted_anchors=[(0, 0), (4, 4)],
        earlier_total=5,
        later_total=5,
    )

    assert len(result) == 2
    matched_later_indices = {r.later_passage.passage_index for r in result}
    assert matched_later_indices == {1, 2}


def test_global_shift_anchor_aware_beats_raw_index():
    # A large section is inserted before the cluster in the later report,
    # shifting raw passage_index by +100 without changing local structure.
    # Anchor-aware interpolation should still pair correctly; raw absolute
    # index matching would not.
    e1 = _passage(index=10, text="X", content_hash=HASH_A)
    e2 = _passage(index=11, text="X", content_hash=HASH_A)
    l1 = _passage(index=110, text="X", content_hash=HASH_A)
    l2 = _passage(index=111, text="X", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e1, e2],
        unmatched_later=[l1, l2],
        accepted_anchors=[(9, 109), (12, 112)],
        earlier_total=20,
        later_total=120,
    )

    pairs = {(r.earlier_passage.passage_index, r.later_passage.passage_index) for r in result}
    assert pairs == {(10, 110), (11, 111)}


def test_no_anchor_fallback_uses_relative_position():
    # No accepted primary matches at all -- falls back to normalized
    # relative document position, which reduces to ordinal correspondence
    # for an evenly spaced cluster.
    e1 = _passage(index=2, text="X", content_hash=HASH_A)
    e2 = _passage(index=8, text="X", content_hash=HASH_A)
    l1 = _passage(index=3, text="X", content_hash=HASH_A)
    l2 = _passage(index=9, text="X", content_hash=HASH_A)

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=[e1, e2],
        unmatched_later=[l1, l2],
        accepted_anchors=[],
        earlier_total=10,
        later_total=10,
    )

    pairs = {(r.earlier_passage.passage_index, r.later_passage.passage_index) for r in result}
    assert pairs == {(2, 3), (8, 9)}
    assert "relative-position fallback" in result[0].review_reason


def test_deterministic_tie_break_smallest_earlier_then_later_index():
    # e1 and e2 are equidistant from l1 (predicted position identical, no
    # anchors, symmetric indices) -- the documented tie-break is smallest
    # position_diff, then smallest earlier passage_index, then smallest
    # later passage_index. Construct an exact tie between two candidate
    # pairs and confirm the lower-index pair wins deterministically.
    e1 = _passage(index=1, text="X", content_hash=HASH_A)
    e2 = _passage(index=3, text="X", content_hash=HASH_A)
    l1 = _passage(index=2, text="X", content_hash=HASH_A)

    result = _match_duplicate_cluster(
        [e1, e2], [l1], anchors=[], earlier_total=4, later_total=4
    )

    assert len(result) == 1
    # Both e1 (|1-2|=1 under ratio*3=1.5... ) -- use the explicit predicted
    # position to reason about the tie instead of raw index heuristics.
    predicted_e1 = _predicted_later_position(1, [], 4, 4)
    predicted_e2 = _predicted_later_position(3, [], 4, 4)
    diff_e1 = abs(predicted_e1 - 2)
    diff_e2 = abs(predicted_e2 - 2)
    winner = e1 if diff_e1 <= diff_e2 else e2
    assert result[0].earlier_passage is winner


def test_residual_never_forces_equal_counts():
    # 4 earlier, 2 later -- exactly 2 pairs, 2 earlier residuals, real
    # count imbalance preserved rather than papered over.
    earlier = [_passage(index=i, text="X", content_hash=HASH_A) for i in range(1, 5)]
    later = [_passage(index=i, text="X", content_hash=HASH_A) for i in range(1, 3)]

    result = reconcile_exact_hash_duplicates(
        unmatched_earlier=earlier, unmatched_later=later, accepted_anchors=[], earlier_total=6, later_total=4
    )

    assert len(result) == 2
    assert "residual 2 earlier / 0 later unmatched" in result[0].review_reason


# ---------------------------------------------------------------------------
# _predicted_later_position edge cases
# ---------------------------------------------------------------------------


def test_predicted_position_interpolates_between_anchors():
    # Anchor A: earlier 0 <-> later 0. Anchor B: earlier 10 <-> later 20.
    # Earlier index 5 (midpoint) should predict later position 10.
    predicted = _predicted_later_position(5, [(0, 0), (10, 20)], earlier_total=11, later_total=21)
    assert predicted == pytest.approx(10.0)


def test_predicted_position_extrapolates_from_single_prior_anchor():
    predicted = _predicted_later_position(12, [(10, 20)], earlier_total=20, later_total=30)
    assert predicted == pytest.approx(22.0)


def test_predicted_position_extrapolates_from_single_following_anchor():
    predicted = _predicted_later_position(8, [(10, 20)], earlier_total=20, later_total=30)
    assert predicted == pytest.approx(18.0)

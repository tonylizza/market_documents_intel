"""Post-pass reconciliation of already-unmatched REMOVED/NEW passages that
share an exact `content_hash` (Milestone 2). See
docs/exact-hash-reconciliation-experiment.md for the full experiment and
docs/table-fragment-hardening-experiment.md section 13 for why this is the
narrowly-scoped follow-up to Milestone 1's table-fragment hardening.

Runs strictly after the primary matcher (`passage_alignment.py`), split/merge
detection, and collision detection have all finalized their output -- never
alters an accepted primary match, never considers a passage split/merge
detection already flagged AMBIGUOUS, and never uses anything but exact
`content_hash` identity as an acceptance signal. Position/anchor evidence
(`accepted_anchors`, derived from the primary matcher's own accepted
correspondences) is used only to choose *which* identical duplicate
occurrence pairs with which when a hash has more than one unmatched
occurrence on either side -- it can never override an exact-hash mismatch,
and it can never force counts to balance: leftover occurrences on the larger
side stay unmatched, since that imbalance may itself be a real disclosure
change (e.g. a removed table column).
"""

import bisect
from collections import defaultdict
from dataclasses import dataclass

from market_documents.models.enums import AlignmentConfidence, AlignmentMatchSource
from market_documents.models.passage import Passage


@dataclass(frozen=True)
class ReconciledPair:
    earlier_passage: Passage
    later_passage: Passage
    match_source: AlignmentMatchSource
    confidence: AlignmentConfidence
    review_reason: str


def reconcile_exact_hash_duplicates(
    *,
    unmatched_earlier: list[Passage],
    unmatched_later: list[Passage],
    accepted_anchors: list[tuple[int, int]],
    earlier_total: int,
    later_total: int,
) -> list[ReconciledPair]:
    """Reconcile unmatched passages that share an exact `content_hash`.

    `unmatched_earlier`/`unmatched_later` must already exclude anything the
    caller has flagged as a likely split/merge (AMBIGUOUS) -- this function
    treats every passage it receives as eligible.

    `accepted_anchors` must be `(earlier_passage_index, later_passage_index)`
    pairs from the primary matcher's own accepted correspondences -- used
    only for duplicate-cluster position evidence (see
    `_predicted_later_position`), never as an acceptance gate. Order is
    irrelevant; this function sorts them itself.

    Hashes are processed in sorted order purely so output ordering is
    deterministic and reproducible across runs; hash groups are disjoint
    partitions of the input, so processing order cannot affect which pairs
    are chosen.
    """
    earlier_by_hash: dict[str, list[Passage]] = defaultdict(list)
    for p in unmatched_earlier:
        earlier_by_hash[p.content_hash].append(p)
    later_by_hash: dict[str, list[Passage]] = defaultdict(list)
    for p in unmatched_later:
        later_by_hash[p.content_hash].append(p)

    anchors = sorted(accepted_anchors)

    reconciled: list[ReconciledPair] = []
    for content_hash in sorted(set(earlier_by_hash) & set(later_by_hash)):
        earlier_group = sorted(earlier_by_hash[content_hash], key=lambda p: p.passage_index)
        later_group = sorted(later_by_hash[content_hash], key=lambda p: p.passage_index)

        if len(earlier_group) == 1 and len(later_group) == 1:
            reconciled.append(
                ReconciledPair(
                    earlier_passage=earlier_group[0],
                    later_passage=later_group[0],
                    match_source=AlignmentMatchSource.EXACT_HASH_RECONCILIATION_UNIQUE,
                    confidence=AlignmentConfidence.HIGH,
                    review_reason=(
                        "exact_hash_reconciliation_unique: unique exact-hash correspondence "
                        "(1 unmatched earlier, 1 unmatched later) recovered after primary "
                        "alignment left both unmatched"
                    ),
                )
            )
            continue

        reconciled.extend(
            _match_duplicate_cluster(
                earlier_group, later_group, anchors=anchors, earlier_total=earlier_total, later_total=later_total
            )
        )

    return reconciled


def _predicted_later_position(
    earlier_index: int, anchors: list[tuple[int, int]], earlier_total: int, later_total: int
) -> float:
    """Predict where `earlier_index` should land in the later report.

    Three preference levels, expressed as one interpolation rather than
    separate code paths (spec section 8):

    1. If accepted primary matches bracket `earlier_index` on both sides,
       linearly interpolate between those anchors' later_index values --
       local position relative to nearby accepted alignments.
    2. If only one side has an anchor (start/end of document), extrapolate
       using that anchor's earlier-to-later offset.
    3. If there are no accepted anchors at all, fall back to normalized
       relative document position -- which reduces to ordinal
       correspondence for an evenly-spaced duplicate cluster.
    """
    if anchors:
        earlier_indices = [a[0] for a in anchors]
        pos = bisect.bisect_left(earlier_indices, earlier_index)
        prev_anchor = anchors[pos - 1] if pos > 0 else None
        next_anchor = anchors[pos] if pos < len(anchors) else None

        if prev_anchor and next_anchor:
            e_prev, l_prev = prev_anchor
            e_next, l_next = next_anchor
            fraction = (earlier_index - e_prev) / (e_next - e_prev)
            return l_prev + fraction * (l_next - l_prev)
        if prev_anchor:
            e_prev, l_prev = prev_anchor
            return l_prev + (earlier_index - e_prev)
        if next_anchor:
            e_next, l_next = next_anchor
            return l_next - (e_next - earlier_index)

    ratio = earlier_index / (earlier_total - 1) if earlier_total > 1 else 0.0
    return ratio * (later_total - 1) if later_total > 1 else 0.0


def _match_duplicate_cluster(
    earlier_group: list[Passage],
    later_group: list[Passage],
    *,
    anchors: list[tuple[int, int]],
    earlier_total: int,
    later_total: int,
) -> list[ReconciledPair]:
    """Deterministically pair identical duplicate occurrences.

    Every candidate `(earlier, later)` pair in the cluster is scored by
    `|predicted_later_position(earlier) - later.passage_index|`, then all
    candidates are sorted by `(position_diff, earlier.passage_index,
    later.passage_index)` and greedily claimed in that order -- this single
    global sort is both the matching algorithm and the deterministic
    tie-break rule (spec section 10). Leftover occurrences on the larger
    side are never forced to pair; they remain unmatched, preserving a real
    count imbalance rather than papering over it.
    """
    predicted = {p.id: _predicted_later_position(p.passage_index, anchors, earlier_total, later_total) for p in earlier_group}

    candidates: list[tuple[float, int, int, Passage, Passage]] = []
    for earlier in earlier_group:
        for later in later_group:
            diff = abs(predicted[earlier.id] - later.passage_index)
            candidates.append((diff, earlier.passage_index, later.passage_index, earlier, later))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))

    claimed_earlier: set = set()
    claimed_later: set = set()
    pairs: list[tuple[Passage, Passage]] = []
    for _, _, _, earlier, later in candidates:
        if earlier.id in claimed_earlier or later.id in claimed_later:
            continue
        claimed_earlier.add(earlier.id)
        claimed_later.add(later.id)
        pairs.append((earlier, later))

    residual_earlier = len(earlier_group) - len(pairs)
    residual_later = len(later_group) - len(pairs)
    evidence = "anchor-interpolated" if anchors else "relative-position fallback (no accepted anchors)"
    note = (
        f"exact_hash_reconciliation_duplicate_cluster: {len(earlier_group)} earlier / "
        f"{len(later_group)} later occurrences; {evidence} position evidence; "
        f"residual {residual_earlier} earlier / {residual_later} later unmatched"
    )

    return [
        ReconciledPair(
            earlier_passage=earlier,
            later_passage=later,
            match_source=AlignmentMatchSource.EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER,
            confidence=AlignmentConfidence.MEDIUM,
            review_reason=note,
        )
        for earlier, later in pairs
    ]


def embedding_cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float | None:
    """Plain-Python cosine similarity between two embedding vectors.

    Diagnostic only -- reconciliation acceptance never depends on this (spec
    section 11). Used solely to populate `PassageAlignment.semantic_similarity`
    on reconciled rows for comparability with primary-matcher rows, since
    reconciled pairs never went through `get_semantic_candidates`.
    """
    dot = sum(a * b for a, b in zip(vector_a, vector_b, strict=True))
    norm_a = sum(a * a for a in vector_a) ** 0.5
    norm_b = sum(b * b for b in vector_b) ** 0.5
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    return dot / (norm_a * norm_b)

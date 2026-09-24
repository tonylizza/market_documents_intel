"""Pure, independently testable financial-language-signal aggregation and
formulas.

Mirrors `feature_metrics.py`: no database access -- every function takes
plain values or the small `SignalRowInput` dataclass and returns plain
values, so population membership, rate computation, and derived-measure
formulas can be unit tested without PostgreSQL. Database wiring (pulling
`PassageLanguageSignal`/`PassageLanguageCategoryHit` rows into
`SignalRowInput`) lives in `financial_language_signals.py`.
"""

import math
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, ReportSide
from market_documents.services.financial_language_config import CORE_CATEGORIES, CUSTOM_TAXONOMY_CATEGORIES

# Structured-content categories excluded from `primary_narrative` (spec:
# "Exclude ... financial_table_rendered_as_prose"). `currency_exposure_
# table_mixed`, `uncertain`, `list_content`, and `table_context` are
# deliberately retained by default -- only available as separate sensitivity
# variants (see `SENSITIVITY_EXCLUDED_CATEGORIES`).
PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES = frozenset(
    {
        "short_fragment_invalid",
        "broken_fragment_sequence",
        "numeric_or_table_like_source",
        "contents_or_index_like",
        "caption_or_label_like",
        "financial_table_rendered_as_prose",
    }
)


@dataclass(frozen=True)
class SignalRowInput:
    """Plain-value projection of one `PassageLanguageSignal` row (plus its
    `PassageLanguageCategoryHit` children, pre-aggregated by category).

    `collision_flag`/`split_merge_flag` are derived at build time from the
    pinned `PassageAlignment` row (`review_reason` text / `alignment_type`)
    -- never a new column on `PassageAlignment` or `PassageLanguageSignal`
    itself (Milestone 6 recalibration explicitly does not touch alignment
    schema). They exist so alignment-*change* quality can distinguish
    "non-unique but plausible" (collision) from genuine non-correspondence
    (`AlignmentStatus.AMBIGUOUS`) -- see `classify_collision`.
    """

    report_side: ReportSide
    alignment_status: AlignmentStatus
    confidence: AlignmentConfidence
    passage_word_count: int
    structured_content_category: str | None
    feature_eligible: bool
    positive_count: int
    negative_count: int
    uncertainty_count: int
    litigious_count: int
    constraining_count: int
    strong_modal_count: int
    weak_modal_count: int
    total_dictionary_hits: int
    custom_category_hits: dict[str, int] = field(default_factory=dict)
    # Track 7F.4: subcategory-level custom-taxonomy hits, keyed
    # (category, subcategory) -- populated from the exact same
    # `match_passage` result as `custom_category_hits` above (no second
    # hit-counting path), retained here only because the M6b topic-mix
    # formula needs subcategory granularity that `custom_category_hits`
    # collapses away.
    custom_subcategory_hits: dict[tuple[str, str], int] = field(default_factory=dict)
    collision_flag: bool = False
    split_merge_flag: bool = False
    # Track 7F.9: the pinned `PassageAlignment` row this signal row belongs
    # to -- the alignment unit that `topic_unit_deltas` groups hits by for
    # the supporting (never eligibility-affecting) change-consistency
    # diagnostics. `None` only in unit tests that don't exercise them.
    passage_alignment_id: uuid.UUID | None = None

    def core_count(self, category: str) -> int:
        return getattr(self, f"{category}_count")


# Substrings of `PassageAlignment.review_reason` written by
# `detect_candidate_collisions` (passage_alignment.py) -- neither message
# contains the literal word "collision", so matching must target the actual
# wording ("...likely duplicated/boilerplate content, match may be
# arbitrary" / "...cannot be disambiguated from content alone").
_COLLISION_REASON_MARKERS = ("duplicat", "boilerplate", "disambiguat", "arbitrary")


def classify_collision(review_reason: str | None) -> bool:
    """Whether `review_reason` was written by candidate-collision detection
    (multi-claimant or exact-duplicate earlier passage) rather than some
    other NEEDS_REVIEW trigger (disagreement, extraction quality, transition
    period, irregular gap). A collision means the correspondence is
    *non-unique*, not that it is wrong -- see module docstring."""
    if not review_reason:
        return False
    reason = review_reason.lower()
    return any(marker in reason for marker in _COLLISION_REASON_MARKERS)


def is_primary_narrative_eligible(row: SignalRowInput) -> bool:
    return row.structured_content_category not in PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES


def safe_ratio(numerator: float, denominator: float) -> float | None:
    """`numerator / denominator`, or `None` (never a fabricated 0.0) when the
    denominator is zero or negative."""
    return numerator / denominator if denominator > 0 else None


def rate_per_1000_words(count: float, words: float, denominator: int = 1000) -> float | None:
    return safe_ratio(count * denominator, words)


def rate_change(later: float | None, earlier: float | None) -> float | None:
    if later is None or earlier is None:
        return None
    return later - earlier


@dataclass(frozen=True)
class SidePopulation:
    count: int
    words: float
    category_totals: dict[str, int]
    custom_category_totals: dict[str, int]
    dictionary_hit_total: int


def aggregate_side(rows: list[SignalRowInput], side: ReportSide) -> SidePopulation:
    """Totals for one report side across the given (already population-
    filtered) rows -- callers pass in exactly the rows that belong to the
    population/side they want (e.g. primary_narrative + EARLIER)."""
    side_rows = [r for r in rows if r.report_side == side]
    category_totals = {c: sum(r.core_count(c) for r in side_rows) for c in CORE_CATEGORIES}
    custom_totals: dict[str, int] = {c: 0 for c in CUSTOM_TAXONOMY_CATEGORIES}
    for r in side_rows:
        for category, hits in r.custom_category_hits.items():
            custom_totals[category] = custom_totals.get(category, 0) + hits
    return SidePopulation(
        count=len(side_rows),
        words=sum(r.passage_word_count for r in side_rows),
        category_totals=category_totals,
        custom_category_totals=custom_totals,
        dictionary_hit_total=sum(r.total_dictionary_hits for r in side_rows),
    )


@dataclass(frozen=True)
class CoreCategoryChange:
    count_earlier: int
    count_later: int
    rate_earlier: float | None
    rate_later: float | None
    rate_change: float | None
    rate_change_abs: float | None


def compute_core_category_change(
    category: str, earlier: SidePopulation, later: SidePopulation
) -> CoreCategoryChange:
    rate_e = rate_per_1000_words(earlier.category_totals[category], earlier.words)
    rate_l = rate_per_1000_words(later.category_totals[category], later.words)
    change = rate_change(rate_l, rate_e)
    return CoreCategoryChange(
        count_earlier=earlier.category_totals[category],
        count_later=later.category_totals[category],
        rate_earlier=rate_e,
        rate_later=rate_l,
        rate_change=change,
        rate_change_abs=abs(change) if change is not None else None,
    )


def net_tone(positive_rate: float | None, negative_rate: float | None) -> float | None:
    if positive_rate is None or negative_rate is None:
        return None
    return positive_rate - negative_rate


@dataclass(frozen=True)
class StatusHits:
    """Category hits restricted to rows of one `AlignmentStatus`, summed
    across all seven core categories plus each custom-taxonomy category --
    used for the NEW/REMOVED/AMBIGUOUS breakdowns and the introduction/
    removal derived measures."""

    core: dict[str, int]
    custom: dict[str, int]
    words: float


def hits_for_status(rows: list[SignalRowInput], status: AlignmentStatus) -> StatusHits:
    matching = [r for r in rows if r.alignment_status == status]
    core = {c: sum(r.core_count(c) for r in matching) for c in CORE_CATEGORIES}
    custom: dict[str, int] = {c: 0 for c in CUSTOM_TAXONOMY_CATEGORIES}
    for r in matching:
        for category, hits in r.custom_category_hits.items():
            custom[category] = custom.get(category, 0) + hits
    return StatusHits(core=core, custom=custom, words=sum(r.passage_word_count for r in matching))


def introduction_or_removal_rate(status_hits: StatusHits, category: str) -> float | None:
    """Word-normalized rate of a category's hits within a single-sided
    population (NEW uses only later-side rows, REMOVED only earlier-side
    rows -- the caller passes rows already filtered to that side).
    Direction is always explicit: this never interprets an absent category
    on the removed side as evidence of the opposite category."""
    return rate_per_1000_words(status_hits.core.get(category, status_hits.custom.get(category, 0)), status_hits.words)


def forward_looking_caution_rate(side: SidePopulation) -> float | None:
    """uncertainty + weak_modal combined rate -- both indicate hedged,
    non-committal forward-looking language; kept as an explicit, documented
    combination rather than either category's rate alone."""
    uncertainty = rate_per_1000_words(side.category_totals["uncertainty"], side.words)
    weak_modal = rate_per_1000_words(side.category_totals["weak_modal"], side.words)
    if uncertainty is None or weak_modal is None:
        return None
    return uncertainty + weak_modal


def custom_category_rate(side: SidePopulation, category: str) -> float | None:
    return rate_per_1000_words(side.custom_category_totals.get(category, 0), side.words)


def dictionary_match_rate(side: SidePopulation) -> float | None:
    """Share of this population's words attributable to *some* dictionary
    hit (core or custom-taxonomy) -- a coverage/quality signal, distinct
    from any single category's per-1,000-word rate."""
    return safe_ratio(side.dictionary_hit_total, side.words)


def dictionary_hits_by_confidence(rows: list[SignalRowInput], confidences: tuple[AlignmentConfidence, ...]) -> int:
    """Total dictionary hits (core + custom) across rows whose alignment
    confidence is in `confidences` -- used for the high-confidence and
    high-and-medium-confidence populations."""
    return sum(r.total_dictionary_hits for r in rows if r.confidence in confidences)


# --------------------------------------------------------------------------
# Track 7F.4 -- M3 (financial-condition hit-share change) and M6b
# (financial-condition topic-mix change). See docs/financial-condition-
# ranking-calibration-7f3.md for the methodology decision
# (ADOPT_M3_WITH_THRESHOLD, |M3| >= 0.04; M6b is supporting detail only).
# --------------------------------------------------------------------------


def custom_taxonomy_hit_share(side: SidePopulation, category: str) -> float | None:
    """M3's per-side input: `category`'s share of this side's total
    custom-taxonomy hits (risk + financial_condition + governance +
    strategy combined). Reuses `SidePopulation.custom_category_totals` --
    already computed by `aggregate_side` -- so this is not a second hit-
    counting path. `None` (never a fabricated 0.0) when the side has zero
    custom-taxonomy hits at all."""
    total = sum(side.custom_category_totals.values())
    return safe_ratio(side.custom_category_totals.get(category, 0), total)


def custom_subcategory_totals(rows: list[SignalRowInput], side: ReportSide, category: str) -> dict[str, int]:
    """Subcategory hit totals for one custom-taxonomy `category`, restricted
    to `side`, summed from `SignalRowInput.custom_subcategory_hits` -- the
    same matched data `custom_category_hits` is built from, just not
    collapsed to category level. Scoped to a single category (not a generic
    all-category breakdown) since only `financial_condition`'s M6b needs
    subcategory granularity."""
    totals: dict[str, int] = {}
    for row in rows:
        if row.report_side != side:
            continue
        for (hit_category, subcategory), hits in row.custom_subcategory_hits.items():
            if hit_category != category:
                continue
            totals[subcategory] = totals.get(subcategory, 0) + hits
    return totals


def subcategory_share_vector(totals: dict[str, int], subcategories: tuple[str, ...]) -> tuple[float, ...]:
    """Ordered share vector over `subcategories`: each entry is that
    subcategory's share of `totals`'s combined hit count. All-zero (not
    `None`) when the category has zero hits -- `cosine_distance` is what
    turns an all-zero vector into `None`, not this helper."""
    category_total = sum(totals.values())
    if category_total <= 0:
        return tuple(0.0 for _ in subcategories)
    return tuple(totals.get(sub, 0) / category_total for sub in subcategories)


def cosine_distance(a: tuple[float, ...], b: tuple[float, ...]) -> float | None:
    """`1 - cosine_similarity(a, b)`. Explicit zero-vector rule: if either
    vector's L2 norm is 0 (the category had zero hits on that side), cosine
    similarity is undefined -- return `None`, never a fabricated 0.0 (no
    change) or 1.0 (maximal distance)."""
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0.0 or norm_b == 0.0:
        return None
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    similarity = dot / (norm_a * norm_b)
    return 1.0 - similarity


# --------------------------------------------------------------------------
# Track 7F.9 -- unified Discover topic-change metric (C_min conjunction) and
# its supporting alignment-unit diagnostics. Methodology frozen in
# docs/discover-metrics-methodology-consolidation-7f8.md and
# docs/topic-conjunction-evidence-challenge-7f8a.md; implementation notes in
# docs/discover-metrics-unified-implementation-7f9.md.
# --------------------------------------------------------------------------


def pair_mean_count_change(
    hits_earlier: int, hits_later: int, words_earlier: float, words_later: float, denominator: int = 1000
) -> float | None:
    """Count leg `D = 1000 * (h2 - h1) / ((w1 + w2) / 2)`: the change in a
    category's hit count per 1,000 pair-average words. `None` (never a
    fabricated 0.0) when the pair-average word count is not positive."""
    mean_words = (words_earlier + words_later) / 2
    if mean_words <= 0:
        return None
    return denominator * (hits_later - hits_earlier) / mean_words


def density_change(
    hits_earlier: int, hits_later: int, words_earlier: float, words_later: float, denominator: int = 1000
) -> float | None:
    """Density leg `M1 = 1000 * (h2/w2 - h1/w1)`, computed in exactly this
    operation order so it reproduces the 7F.8/7F.8a research value bit for
    bit. `None` when either side has no words."""
    if words_earlier <= 0 or words_later <= 0:
        return None
    return denominator * (hits_later / words_later - hits_earlier / words_earlier)


def topic_change_conjunction(count_change: float | None, density: float | None) -> float | None:
    """`C_min`: `sign(D) * min(|D|, |M1|)` when the count leg and the density
    leg share a strictly common direction; `0.0` when either leg is zero or
    they disagree in sign. `None` only when a leg is itself undefined."""
    if count_change is None or density is None:
        return None
    if count_change * density <= 0:
        return 0.0
    return math.copysign(min(abs(count_change), abs(density)), count_change)


def change_consistency_ratio(unit_deltas: list[int]) -> float:
    """Signed `net / gross` over per-alignment-unit hit deltas, in [-1, 1]:
    +1/-1 when every changed unit moved the same way, near 0 under heavy
    offsetting churn. `0.0` when no unit changed. Supporting diagnostic only
    -- never an eligibility condition (7F.8a frozen decision)."""
    gross = sum(abs(d) for d in unit_deltas)
    return sum(unit_deltas) / gross if gross > 0 else 0.0


def largest_passage_share(unit_deltas: list[int]) -> float:
    """`max(|unit_delta|) / gross`: how much of the pair's total hit churn a
    single alignment unit accounts for. `0.0` when no unit changed.
    Supporting diagnostic only."""
    gross = sum(abs(d) for d in unit_deltas)
    return max(abs(d) for d in unit_deltas) / gross if gross > 0 else 0.0


def topic_unit_deltas(rows: list[SignalRowInput], hits_of: Callable[[SignalRowInput], int]) -> list[int]:
    """Later-minus-earlier hit delta per alignment unit (rows grouped by
    `passage_alignment_id`), over the rows the caller passes -- always the
    same `feature_eligible_primary` population the pair metrics use. Units
    whose delta is zero are omitted."""
    units: dict[uuid.UUID | None, list[int]] = {}
    for row in rows:
        unit = units.setdefault(row.passage_alignment_id, [0, 0])
        unit[0 if row.report_side == ReportSide.EARLIER else 1] += hits_of(row)
    return [later - earlier for earlier, later in units.values() if later != earlier]


@dataclass(frozen=True)
class TopicChangeDiagnostics:
    """Supporting-only decomposition of a pair's category hit change across
    alignment units. `supporting_hits`/`opposing_hits` are expressed relative
    to the direction of the pair's net count change `h2 - h1` -- which is the
    finding's direction whenever the topic change is nonzero (C_min always
    carries sign(D)). Both are 0 when the net change is exactly 0."""

    supporting_hits: int
    opposing_hits: int
    change_consistency_ratio: float
    largest_passage_share: float


def topic_change_diagnostics(unit_deltas: list[int]) -> TopicChangeDiagnostics:
    net = sum(unit_deltas)
    direction = (net > 0) - (net < 0)
    return TopicChangeDiagnostics(
        supporting_hits=sum(abs(d) for d in unit_deltas if d * direction > 0),
        opposing_hits=sum(abs(d) for d in unit_deltas if d * direction < 0),
        change_consistency_ratio=change_consistency_ratio(unit_deltas),
        largest_passage_share=largest_passage_share(unit_deltas),
    )


@dataclass(frozen=True)
class TopicChange:
    hits_earlier: int
    hits_later: int
    count_change_per_1000: float | None
    density_change: float | None
    topic_change: float | None
    diagnostics: TopicChangeDiagnostics


def compute_topic_change(
    rows: list[SignalRowInput],
    hits_of: Callable[[SignalRowInput], int],
    words_earlier: float,
    words_later: float,
) -> TopicChange:
    """One category's full 7F.9 topic-change record over `rows` (the
    `feature_eligible_primary` population): raw hits each side, the count and
    density legs, their C_min conjunction, and the alignment-unit
    diagnostics."""
    h1 = sum(hits_of(r) for r in rows if r.report_side == ReportSide.EARLIER)
    h2 = sum(hits_of(r) for r in rows if r.report_side == ReportSide.LATER)
    d = pair_mean_count_change(h1, h2, words_earlier, words_later)
    m1 = density_change(h1, h2, words_earlier, words_later)
    return TopicChange(
        hits_earlier=h1,
        hits_later=h2,
        count_change_per_1000=d,
        density_change=m1,
        topic_change=topic_change_conjunction(d, m1),
        diagnostics=topic_change_diagnostics(topic_unit_deltas(rows, hits_of)),
    )

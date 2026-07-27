"""Pure, independently testable financial-language-signal aggregation and
formulas.

Mirrors `feature_metrics.py`: no database access -- every function takes
plain values or the small `SignalRowInput` dataclass and returns plain
values, so population membership, rate computation, and derived-measure
formulas can be unit tested without PostgreSQL. Database wiring (pulling
`PassageLanguageSignal`/`PassageLanguageCategoryHit` rows into
`SignalRowInput`) lives in `financial_language_signals.py`.
"""

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
    collision_flag: bool = False
    split_merge_flag: bool = False

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

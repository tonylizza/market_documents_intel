"""Pure, independently testable disclosure-change feature calculations.

No database access -- every function here takes plain values or the small
`AlignmentRowInput` dataclass and returns plain values, so aggregation,
weighting, and scoring logic can be unit tested without PostgreSQL. Database
wiring (pulling `PassageAlignment`/`Passage` rows into `AlignmentRowInput`)
lives in `feature_extraction.py`.

Word-weighting rule (spec item B): for a matched row (UNCHANGED/
LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED) the weight is
`mean(earlier_word_count, later_word_count)` -- symmetric, so the score
never rewards whichever side happens to be longer. NEW uses the later
passage's word count, REMOVED uses the earlier passage's word count.
AMBIGUOUS rows (including split/merge-flagged ones) have exactly one
present side per row -- `PassageAlignment`'s partial unique indexes
guarantee a passage is primary in at most one row, so summing each row's
single-side weight can never double-count a passage across a split/merge
group.
"""

from dataclasses import dataclass

from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, PassageType
from market_documents.services.feature_config import FEATURE_CONFIG, FeatureConfig

MATCHED_STATUSES = (
    AlignmentStatus.UNCHANGED,
    AlignmentStatus.LIGHTLY_MODIFIED,
    AlignmentStatus.SUBSTANTIALLY_MODIFIED,
)


@dataclass(frozen=True)
class AlignmentRowInput:
    """Plain-value projection of one primary `PassageAlignment` row.

    `earlier_word_count`/`later_word_count` are `None` exactly when the
    corresponding passage doesn't exist for this row (NEW has no earlier
    side, REMOVED has no later side, AMBIGUOUS has exactly one side).
    """

    alignment_status: AlignmentStatus
    confidence: AlignmentConfidence
    earlier_word_count: int | None
    later_word_count: int | None
    earlier_passage_type: PassageType | None
    later_passage_type: PassageType | None


def is_low_information(word_count: int, config: FeatureConfig = FEATURE_CONFIG) -> bool:
    """A passage below the feature-local word floor, regardless of type.

    Deliberately distinct from `PassageConfig.min_words_hard_floor` (15),
    which already excludes unusably tiny passages from alignment entirely --
    this catches the M4-documented artifact of passages that clear that
    floor but are still too short to carry independent disclosure-change
    signal (e.g. a heading plus one short sentence).
    """
    return word_count < config.minimum_feature_passage_words


def is_heading_fragment(
    word_count: int, passage_type: PassageType, config: FeatureConfig = FEATURE_CONFIG
) -> bool:
    """A low-information passage that is specifically heading-derived."""
    return passage_type == PassageType.HEADING_WITH_BODY and is_low_information(word_count, config)


def passage_excluded_from_features(
    word_count: int | None, passage_type: PassageType | None, config: FeatureConfig
) -> bool:
    """Whether one side of a row is excluded from the feature-eligible population.

    A side that doesn't exist for this row (`word_count is None`) is never
    itself a reason to exclude the row.
    """
    if word_count is None:
        return False
    if not is_low_information(word_count, config):
        return False
    if config.include_low_information_passages:
        return False
    if passage_type == PassageType.HEADING_WITH_BODY and config.include_heading_only_passages:
        return False
    return True


def is_row_eligible(row: AlignmentRowInput, config: FeatureConfig = FEATURE_CONFIG) -> bool:
    """A row is feature-eligible only if every side it has clears the low-information rule."""
    return not (
        passage_excluded_from_features(row.earlier_word_count, row.earlier_passage_type, config)
        or passage_excluded_from_features(row.later_word_count, row.later_passage_type, config)
    )


def row_word_weight(row: AlignmentRowInput) -> float:
    """The word weight one row contributes to its outcome category's total."""
    if row.alignment_status == AlignmentStatus.NEW:
        return float(row.later_word_count or 0)
    if row.alignment_status == AlignmentStatus.REMOVED:
        return float(row.earlier_word_count or 0)
    if row.alignment_status == AlignmentStatus.AMBIGUOUS:
        present = row.earlier_word_count if row.earlier_word_count is not None else row.later_word_count
        return float(present or 0)
    # Matched tiers: both sides present.
    values = [v for v in (row.earlier_word_count, row.later_word_count) if v is not None]
    return sum(values) / len(values) if values else 0.0


@dataclass(frozen=True)
class OutcomeAggregate:
    counts: dict[AlignmentStatus, int]
    words: dict[AlignmentStatus, float]


def aggregate_outcomes(
    rows: list[AlignmentRowInput], *, eligible_only: bool, config: FeatureConfig = FEATURE_CONFIG
) -> OutcomeAggregate:
    """Raw (`eligible_only=False`) or feature-eligible (`eligible_only=True`) outcome totals.

    Both variants are always computed by the caller from the same `rows`
    list -- this function never decides which one is "the" result.
    """
    counts: dict[AlignmentStatus, int] = {status: 0 for status in AlignmentStatus}
    words: dict[AlignmentStatus, float] = {status: 0.0 for status in AlignmentStatus}
    for row in rows:
        if eligible_only and not is_row_eligible(row, config):
            continue
        counts[row.alignment_status] += 1
        words[row.alignment_status] += row_word_weight(row)
    return OutcomeAggregate(counts=counts, words=words)


def safe_ratio(numerator: float, denominator: float) -> float | None:
    """`numerator / denominator`, or `None` (never a fabricated 0.0) when the
    denominator is zero."""
    return numerator / denominator if denominator else None


def count_rates(aggregate: OutcomeAggregate) -> dict[AlignmentStatus, float | None]:
    total = sum(aggregate.counts.values())
    return {status: safe_ratio(count, total) for status, count in aggregate.counts.items()}


def word_rates(aggregate: OutcomeAggregate) -> dict[AlignmentStatus, float | None]:
    total = sum(aggregate.words.values())
    return {status: safe_ratio(words, total) for status, words in aggregate.words.items()}


@dataclass(frozen=True)
class ScoreComponents:
    unchanged: float | None
    lightly_modified: float | None
    substantially_modified: float | None
    new: float | None
    removed: float | None
    ambiguous: float | None

    @property
    def total(self) -> float | None:
        values = (self.unchanged, self.lightly_modified, self.substantially_modified, self.new, self.removed, self.ambiguous)
        if any(v is None for v in values):
            return None
        # Guard against float-summation drift pushing a value marginally
        # outside [0, 1], mirroring similarity_metrics._clamp_unit.
        return max(0.0, min(1.0, sum(values)))


def row_exclusion_kind(row: AlignmentRowInput, config: FeatureConfig = FEATURE_CONFIG) -> str | None:
    """`None` if the row is feature-eligible; otherwise `"heading_fragment"`
    when every excluding side is HEADING_WITH_BODY-typed, else `"low_information"`.

    A row with a mix (one excluding side a heading fragment, the other a
    plain short passage) is conservatively classified `"low_information"`,
    since it is not purely a heading-fragment artifact.
    """
    excluded_sides_are_heading: list[bool] = []
    for word_count, passage_type in (
        (row.earlier_word_count, row.earlier_passage_type),
        (row.later_word_count, row.later_passage_type),
    ):
        if passage_excluded_from_features(word_count, passage_type, config):
            excluded_sides_are_heading.append(passage_type == PassageType.HEADING_WITH_BODY)
    if not excluded_sides_are_heading:
        return None
    return "heading_fragment" if all(excluded_sides_are_heading) else "low_information"


@dataclass(frozen=True)
class AlignmentCoverage:
    coverage_count: float | None
    coverage_words: float | None


def compute_alignment_coverage(
    rows: list[AlignmentRowInput],
    *,
    earlier_total_count: int,
    later_total_count: int,
    earlier_total_words: int,
    later_total_words: int,
) -> AlignmentCoverage:
    """Share of the raw segmentation population represented by a primary
    alignment row, counted per side (a matched row represents one earlier
    passage *and* one later passage, not one unit)."""
    earlier_covered_count = sum(1 for r in rows if r.earlier_word_count is not None)
    later_covered_count = sum(1 for r in rows if r.later_word_count is not None)
    earlier_covered_words = sum(r.earlier_word_count for r in rows if r.earlier_word_count is not None)
    later_covered_words = sum(r.later_word_count for r in rows if r.later_word_count is not None)
    return AlignmentCoverage(
        coverage_count=safe_ratio(
            earlier_covered_count + later_covered_count, earlier_total_count + later_total_count
        ),
        coverage_words=safe_ratio(
            earlier_covered_words + later_covered_words, earlier_total_words + later_total_words
        ),
    )


@dataclass(frozen=True)
class DocumentChangeTransforms:
    cosine_change: float | None
    bigram_jaccard_change: float | None
    edit_similarity_change: float | None
    diff_similarity_change: float | None
    word_change_ratio_abs: float | None
    metric_disagreement_spread: float | None


def compute_document_change_transforms(
    *,
    cosine: float | None,
    bigram_jaccard: float | None,
    edit_similarity: float | None,
    diff_similarity: float | None,
    word_change_ratio: float | None,
) -> DocumentChangeTransforms:
    """Interpretable "amount of change" transforms of the M3 similarity
    metrics (spec item G), plus the metric-disagreement spread recomputed
    from the same raw values -- kept as separate, explicitly named columns
    rather than averaged into the raw metrics."""

    def invert(value: float | None) -> float | None:
        return 1.0 - value if value is not None else None

    values = [v for v in (cosine, bigram_jaccard, diff_similarity, edit_similarity) if v is not None]
    spread = max(values) - min(values) if len(values) >= 2 else None
    return DocumentChangeTransforms(
        cosine_change=invert(cosine),
        bigram_jaccard_change=invert(bigram_jaccard),
        edit_similarity_change=invert(edit_similarity),
        diff_similarity_change=invert(diff_similarity),
        word_change_ratio_abs=abs(word_change_ratio) if word_change_ratio is not None else None,
        metric_disagreement_spread=spread,
    )


def compute_score_components(
    eligible_word_rates: dict[AlignmentStatus, float | None], config: FeatureConfig = FEATURE_CONFIG
) -> ScoreComponents:
    """Word-weighted-rate x weight for each outcome category.

    `unchanged_weight` defaults to 0.0 (present in the rate denominator,
    contributes nothing to the numerator) but is still computed and stored
    explicitly rather than omitted, so the full formula stays inspectable.
    """

    def component(status: AlignmentStatus, weight: float) -> float | None:
        rate = eligible_word_rates.get(status)
        return rate * weight if rate is not None else None

    return ScoreComponents(
        unchanged=component(AlignmentStatus.UNCHANGED, config.unchanged_weight),
        lightly_modified=component(AlignmentStatus.LIGHTLY_MODIFIED, config.lightly_modified_weight),
        substantially_modified=component(AlignmentStatus.SUBSTANTIALLY_MODIFIED, config.substantially_modified_weight),
        new=component(AlignmentStatus.NEW, config.new_weight),
        removed=component(AlignmentStatus.REMOVED, config.removed_weight),
        ambiguous=component(AlignmentStatus.AMBIGUOUS, config.ambiguous_weight),
    )

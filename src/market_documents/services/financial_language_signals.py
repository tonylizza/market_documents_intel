"""Financial-language-signal orchestration: run lifecycle, idempotency, and
persistence.

Directly parallels `services/feature_extraction.py`: this module owns the
configuration fingerprint that drives idempotent skipping, and the
query-time rule for selecting a ReportPair's current successful language-
signal result. Matching/aggregation logic is delegated to
`financial_language_tokenization` (tokenize/match/negate) and
`financial_language_metrics` (aggregate/rate); quality assessment to
`financial_language_quality`. This module only selects sources, wires
everything together, and persists the result -- exactly the `FeatureRun`
convention: a pair may have many `LanguageSignalRun`s over time, "current
successful" is a query-time rule, and a FAILED run never produces a
`ReportPairLanguageFeatures` row.
"""

import logging
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.exceptions import LanguageSignalNotEligibleError
from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.enums import (
    AlignmentConfidence,
    AlignmentStatus,
    AlignmentType,
    BlockType,
    LanguageSignalQuality,
    LanguageSignalRunStatus,
    ReportSide,
)
from market_documents.models.extraction import TextBlock
from market_documents.models.feature import ReportPairFeatures
from market_documents.models.financial_language import (
    FinancialLanguageDictionary,
    FinancialLanguageTerm,
    LanguageSignalRun,
    PassageLanguageCategoryHit,
    PassageLanguageSignal,
    ReportPairLanguageFeatures,
)
from market_documents.models.passage import Passage, PassageSourceBlock
from market_documents.models.report_pair import ReportPair
from market_documents.services.feature_config import FEATURE_CONFIG
from market_documents.services.feature_extraction import get_current_feature_run, get_current_report_pair_features
from market_documents.services.feature_metrics import passage_excluded_from_features
from market_documents.services.financial_language_config import (
    ALGORITHM_VERSION,
    CORE_CATEGORIES,
    CUSTOM_TAXONOMY_CATEGORIES,
    FINANCIAL_LANGUAGE_CONFIG,
    SIGNAL_VERSION,
    DictionaryFingerprint,
    FinancialLanguageConfig,
    compute_configuration_hash,
)
from market_documents.services.financial_language_metrics import (
    PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES,
    SidePopulation,
    SignalRowInput,
    aggregate_side,
    classify_collision,
    compute_core_category_change,
    custom_category_rate,
    dictionary_hits_by_confidence,
    dictionary_match_rate,
    forward_looking_caution_rate,
    hits_for_status,
    introduction_or_removal_rate,
    is_primary_narrative_eligible,
    net_tone,
    rate_change,
    safe_ratio,
)
from market_documents.services.financial_language_quality import (
    AlignmentChangeQualityInputs,
    ReportSideQualityInputs,
    assess_alignment_change_quality,
    assess_report_side_quality,
    combine_quality_for_deprecated_composite,
)
from market_documents.services.financial_language_tokenization import (
    match_phrases_and_unigrams,
    negated_token_positions,
    tokenize_sentences,
)
from market_documents.services.structured_content_audit import Classification, PassageAuditInput, classify_passage

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Dictionary and term-index resolution
# --------------------------------------------------------------------------


def get_current_dictionaries(session: Session) -> list[FinancialLanguageDictionary]:
    """One dictionary per distinct `name`: the most recently imported
    version. Dictionaries have no run-lifecycle status (they are reference
    data, not a computed result), so "current" is simply the latest import
    per name."""
    all_dicts = session.scalars(
        select(FinancialLanguageDictionary).order_by(
            FinancialLanguageDictionary.name, FinancialLanguageDictionary.created_at.desc()
        )
    ).all()
    current: dict[str, FinancialLanguageDictionary] = {}
    for dictionary in all_dicts:
        current.setdefault(dictionary.name, dictionary)
    return list(current.values())


@dataclass(frozen=True)
class TermRecord:
    category: str
    subcategory: str | None
    weight: float


@dataclass(frozen=True)
class TermIndex:
    records_by_key: dict[tuple[str, ...], list[TermRecord]]
    keys_by_length: dict[int, set[tuple[str, ...]]]


def build_term_index(session: Session, dictionary_ids: list[uuid.UUID]) -> TermIndex:
    if not dictionary_ids:
        return TermIndex({}, {})
    terms = session.scalars(
        select(FinancialLanguageTerm).where(FinancialLanguageTerm.dictionary_id.in_(dictionary_ids))
    ).all()
    records_by_key: dict[tuple[str, ...], list[TermRecord]] = defaultdict(list)
    for term in terms:
        key = tuple(term.normalized_term.split())
        records_by_key[key].append(TermRecord(category=term.category, subcategory=term.subcategory, weight=term.weight))
    keys_by_length: dict[int, set[tuple[str, ...]]] = defaultdict(set)
    for key in records_by_key:
        keys_by_length[len(key)].add(key)
    return TermIndex(dict(records_by_key), dict(keys_by_length))


# --------------------------------------------------------------------------
# Passage-level matching
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PassageMatchResult:
    core_counts: dict[str, int]
    negated_hit_count: int
    total_dictionary_hits: int
    custom_hits: dict[tuple[str, str], int]
    custom_hits_negated: dict[tuple[str, str], int]


def match_passage(raw_text: str, index: TermIndex, config: FinancialLanguageConfig) -> PassageMatchResult:
    """Tokenize `raw_text` sentence-by-sentence, match phrases/unigrams
    (longest-phrase-first, hyphen-optional) against the dictionary term
    index, and score negation within each sentence independently -- negation
    scope never crosses a sentence boundary (see `tokenize_sentences`)."""
    core_counts = {c: 0 for c in CORE_CATEGORIES}
    custom_hits: dict[tuple[str, str], int] = defaultdict(int)
    custom_hits_negated: dict[tuple[str, str], int] = defaultdict(int)
    negated_total = 0
    total = 0

    boundary_conjunctions = frozenset(config.negation_boundary_conjunctions)
    for tokens in tokenize_sentences(raw_text):
        if not tokens:
            continue
        negated_positions = negated_token_positions(tokens, window=config.negation_window, boundary_conjunctions=boundary_conjunctions)
        for key, start, span in match_phrases_and_unigrams(tokens, index.keys_by_length):
            records = index.records_by_key.get(key, ())
            if not records:
                continue
            is_negated = any(pos in negated_positions for pos in range(start, start + span))
            for record in records:
                total += 1
                if is_negated:
                    negated_total += 1
                if record.category in CORE_CATEGORIES:
                    core_counts[record.category] += 1
                else:
                    hit_key = (record.category, record.subcategory or "")
                    custom_hits[hit_key] += 1
                    if is_negated:
                        custom_hits_negated[hit_key] += 1

    return PassageMatchResult(
        core_counts=core_counts,
        negated_hit_count=negated_total,
        total_dictionary_hits=total,
        custom_hits=dict(custom_hits),
        custom_hits_negated=dict(custom_hits_negated),
    )


# --------------------------------------------------------------------------
# Structured-content classification (local re-derivation, see module
# docstring in structured_content_audit.py for the classification rules
# themselves -- reused directly, not reimplemented).
# --------------------------------------------------------------------------


def _block_types_by_passage(session: Session, passage_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[BlockType]]:
    if not passage_ids:
        return {}
    rows = session.execute(
        select(PassageSourceBlock.passage_id, TextBlock.block_type)
        .join(TextBlock, PassageSourceBlock.text_block_id == TextBlock.id)
        .where(PassageSourceBlock.passage_id.in_(passage_ids))
    ).all()
    out: dict[uuid.UUID, list[BlockType]] = defaultdict(list)
    for passage_id, block_type in rows:
        out[passage_id].append(block_type)
    return out


def classify_passages(session: Session, passages: list[Passage]) -> dict[uuid.UUID, Classification]:
    passage_ids = [p.id for p in passages]
    block_types_by_passage = _block_types_by_passage(session, passage_ids)
    out: dict[uuid.UUID, Classification] = {}
    for passage in passages:
        ctx = PassageAuditInput(
            passage_id=passage.id,
            raw_text=passage.raw_text,
            heading_text=passage.heading_text,
            word_count=passage.word_count,
            passage_type=passage.passage_type,
            block_types=tuple(block_types_by_passage.get(passage.id, [])),
        )
        classification = classify_passage(ctx)
        out[passage.id] = classification if classification is not None else Classification(None, "", None, False)
    return out


# --------------------------------------------------------------------------
# Current-result query-time rules
# --------------------------------------------------------------------------


def get_current_language_signal_run(session: Session, report_pair_id: uuid.UUID) -> LanguageSignalRun | None:
    return session.scalars(
        select(LanguageSignalRun)
        .where(
            LanguageSignalRun.report_pair_id == report_pair_id,
            LanguageSignalRun.status.in_(
                (LanguageSignalRunStatus.COMPLETED, LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(LanguageSignalRun.completed_at.desc())
        .limit(1)
    ).first()


def get_current_language_signal_runs_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, LanguageSignalRun]:
    if not report_pair_ids:
        return {}
    candidates = session.scalars(
        select(LanguageSignalRun)
        .where(
            LanguageSignalRun.report_pair_id.in_(report_pair_ids),
            LanguageSignalRun.status.in_(
                (LanguageSignalRunStatus.COMPLETED, LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(LanguageSignalRun.report_pair_id, LanguageSignalRun.completed_at.desc())
    ).all()
    current: dict[uuid.UUID, LanguageSignalRun] = {}
    for run in candidates:
        current.setdefault(run.report_pair_id, run)
    return current


def get_current_pair_language_features(session: Session, report_pair_id: uuid.UUID) -> ReportPairLanguageFeatures | None:
    current_run = get_current_language_signal_run(session, report_pair_id)
    if current_run is None:
        return None
    return session.scalar(
        select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id == current_run.id)
    )


def get_current_pair_language_features_by_pair(
    session: Session, report_pair_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ReportPairLanguageFeatures]:
    current_runs = get_current_language_signal_runs_by_pair(session, report_pair_ids)
    if not current_runs:
        return {}
    run_ids = [run.id for run in current_runs.values()]
    rows = session.scalars(
        select(ReportPairLanguageFeatures).where(ReportPairLanguageFeatures.language_signal_run_id.in_(run_ids))
    ).all()
    by_run_id = {r.language_signal_run_id: r for r in rows}
    return {pair_id: by_run_id[run.id] for pair_id, run in current_runs.items() if run.id in by_run_id}


# --------------------------------------------------------------------------
# Source selection
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LanguageSignalSourceSelection:
    feature_run_id: uuid.UUID
    feature: ReportPairFeatures
    alignment_run: AlignmentRun
    dictionaries: tuple[FinancialLanguageDictionary, ...]


def select_language_signal_source(session: Session, pair: ReportPair) -> LanguageSignalSourceSelection:
    """Raises `LanguageSignalNotEligibleError` when signals cannot currently
    be built: the pair lacks a current successful `FeatureRun`/
    `ReportPairFeatures`, or no financial-language dictionary has been
    imported yet. Never creates or infers either -- both must already exist.
    The alignment run used is the *exact* one pinned by the feature run
    (`feature_run.alignment_run_id`), not independently re-resolved as
    "current" -- this guarantees the language signal and the disclosure-
    change features it is compared against always describe the same
    alignment.
    """
    feature_run = get_current_feature_run(session, pair.id)
    if feature_run is None:
        raise LanguageSignalNotEligibleError("pair has no current successful feature run")
    feature = get_current_report_pair_features(session, pair.id)
    if feature is None:
        raise LanguageSignalNotEligibleError("pair has no current ReportPairFeatures result")

    alignment_run = session.get(AlignmentRun, feature_run.alignment_run_id)
    if alignment_run is None:
        raise LanguageSignalNotEligibleError("feature run's pinned alignment run no longer exists")

    dictionaries = tuple(get_current_dictionaries(session))
    if not dictionaries:
        raise LanguageSignalNotEligibleError("no financial-language dictionary has been imported yet")

    return LanguageSignalSourceSelection(
        feature_run_id=feature_run.id, feature=feature, alignment_run=alignment_run, dictionaries=dictionaries
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


@dataclass
class BuildOutcome:
    report_pair_id: uuid.UUID
    run: LanguageSignalRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def build_language_signals(session: Session, pair: ReportPair, *, force: bool = False) -> BuildOutcome:
    """Build financial-language signals for one ReportPair, creating a new
    `LanguageSignalRun`. Skips (returning the existing run) if the current
    successful run already used an identical pinned feature/alignment run
    and an identical configuration fingerprint, and `force` was not set.
    Never mutates or replaces a prior run's rows."""
    try:
        selection = select_language_signal_source(session, pair)
    except LanguageSignalNotEligibleError as exc:
        return BuildOutcome(report_pair_id=pair.id, run=None, ineligible=True, ineligible_reason=str(exc))

    fingerprints = tuple(
        DictionaryFingerprint(name=d.name, version=d.version, source_hash=d.source_hash) for d in selection.dictionaries
    )
    configuration_hash = compute_configuration_hash(fingerprints)
    # One `LanguageSignalRun.dictionary_id` FK is required by the schema;
    # dictionaries actually used are fully identified by the configuration
    # hash (which folds in every dictionary's name/version/hash), so the FK
    # simply pins the primary (first, alphabetically by name) dictionary for
    # convenient joins -- never the sole source of dictionary lineage.
    primary_dictionary = min(selection.dictionaries, key=lambda d: d.name)

    current_run = get_current_language_signal_run(session, pair.id)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.feature_run_id == selection.feature_run_id
        and current_run.alignment_run_id == selection.alignment_run.id
    ):
        return BuildOutcome(
            report_pair_id=pair.id,
            run=current_run,
            skipped=True,
            skip_reason="identical successful language-signal run already exists",
        )

    run = LanguageSignalRun(
        report_pair_id=pair.id,
        feature_run_id=selection.feature_run_id,
        alignment_run_id=selection.alignment_run.id,
        dictionary_id=primary_dictionary.id,
        algorithm_version=ALGORITHM_VERSION,
        signal_version=SIGNAL_VERSION,
        configuration_hash=configuration_hash,
        status=LanguageSignalRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_signal_build(session, pair, run, selection)
    except Exception as exc:  # never leave a run silently half-written
        run.status = LanguageSignalRunStatus.FAILED
        run.error_message = f"language-signal build failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("language-signal build failed for pair %s", pair.id)

    session.flush()
    return BuildOutcome(report_pair_id=pair.id, run=run)


def _run_signal_build(
    session: Session, pair: ReportPair, run: LanguageSignalRun, selection: LanguageSignalSourceSelection
) -> None:
    config = FINANCIAL_LANGUAGE_CONFIG
    alignment_run = selection.alignment_run
    feat = selection.feature

    alignment_rows = session.scalars(
        select(PassageAlignment).where(
            PassageAlignment.alignment_run_id == alignment_run.id, PassageAlignment.primary_alignment.is_(True)
        )
    ).all()

    passage_ids = {r.earlier_passage_id for r in alignment_rows if r.earlier_passage_id} | {
        r.later_passage_id for r in alignment_rows if r.later_passage_id
    }
    passages = session.scalars(select(Passage).where(Passage.id.in_(passage_ids))).all() if passage_ids else []
    passages_by_id = {p.id: p for p in passages}
    classifications_by_id = classify_passages(session, passages)

    dictionary_ids = [d.id for d in selection.dictionaries]
    term_index = build_term_index(session, dictionary_ids)

    match_cache: dict[uuid.UUID, PassageMatchResult] = {}

    def match_for(passage: Passage) -> PassageMatchResult:
        cached = match_cache.get(passage.id)
        if cached is None:
            cached = match_passage(passage.raw_text, term_index, config)
            match_cache[passage.id] = cached
        return cached

    signal_rows: list[SignalRowInput] = []

    for alignment_row in alignment_rows:
        for side, passage_id in (
            (ReportSide.EARLIER, alignment_row.earlier_passage_id),
            (ReportSide.LATER, alignment_row.later_passage_id),
        ):
            if passage_id is None:
                continue
            passage = passages_by_id.get(passage_id)
            if passage is None:
                continue
            classification = classifications_by_id.get(passage_id) or Classification(None, "", None, False)
            match_result = match_for(passage)
            feature_eligible = not passage_excluded_from_features(passage.word_count, passage.passage_type, FEATURE_CONFIG)
            primary_eligible = classification.category not in PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES
            # Derived from the pinned PassageAlignment row only -- never a
            # new column on PassageAlignment/PassageLanguageSignal itself
            # (Milestone 6 recalibration does not touch alignment schema).
            collision_flag = classify_collision(alignment_row.review_reason)
            split_merge_flag = alignment_row.alignment_type in (AlignmentType.ONE_TO_TWO, AlignmentType.TWO_TO_ONE)

            signal = PassageLanguageSignal(
                language_signal_run_id=run.id,
                passage_id=passage.id,
                passage_alignment_id=alignment_row.id,
                report_side=side,
                alignment_status=alignment_row.alignment_status,
                confidence=alignment_row.confidence,
                passage_type=passage.passage_type,
                passage_word_count=passage.word_count,
                structured_content_category=classification.category,
                primary_narrative_eligible=primary_eligible,
                feature_eligible=feature_eligible,
                positive_count=match_result.core_counts["positive"],
                negative_count=match_result.core_counts["negative"],
                uncertainty_count=match_result.core_counts["uncertainty"],
                litigious_count=match_result.core_counts["litigious"],
                constraining_count=match_result.core_counts["constraining"],
                strong_modal_count=match_result.core_counts["strong_modal"],
                weak_modal_count=match_result.core_counts["weak_modal"],
                negated_hit_count=match_result.negated_hit_count,
                total_dictionary_hits=match_result.total_dictionary_hits,
                category_hit_count=sum(match_result.custom_hits.values()),
            )
            session.add(signal)
            session.flush()

            custom_totals_by_category: dict[str, int] = defaultdict(int)
            for (category, subcategory), hit_count in match_result.custom_hits.items():
                negated = match_result.custom_hits_negated.get((category, subcategory), 0)
                session.add(
                    PassageLanguageCategoryHit(
                        passage_language_signal_id=signal.id,
                        category=category,
                        subcategory=subcategory,
                        hit_count=hit_count,
                        negated_hit_count=negated,
                    )
                )
                custom_totals_by_category[category] += hit_count

            signal_rows.append(
                SignalRowInput(
                    report_side=side,
                    alignment_status=alignment_row.alignment_status,
                    confidence=alignment_row.confidence,
                    passage_word_count=passage.word_count,
                    structured_content_category=classification.category,
                    feature_eligible=feature_eligible,
                    positive_count=match_result.core_counts["positive"],
                    negative_count=match_result.core_counts["negative"],
                    uncertainty_count=match_result.core_counts["uncertainty"],
                    litigious_count=match_result.core_counts["litigious"],
                    constraining_count=match_result.core_counts["constraining"],
                    strong_modal_count=match_result.core_counts["strong_modal"],
                    weak_modal_count=match_result.core_counts["weak_modal"],
                    total_dictionary_hits=match_result.total_dictionary_hits,
                    custom_category_hits=dict(custom_totals_by_category),
                    collision_flag=collision_flag,
                    split_merge_flag=split_merge_flag,
                )
            )

    pair_features = _aggregate_pair_features(pair, run, alignment_run, feat, signal_rows, config)
    session.add(pair_features)

    run.completed_at = datetime.now(UTC)
    run.review_reason = pair_features.warning_reasons
    run.status = (
        LanguageSignalRunStatus.COMPLETED
        if pair_features.language_signal_quality == LanguageSignalQuality.GOOD
        else LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS
    )


def _filtered(rows: list[SignalRowInput], predicate) -> list[SignalRowInput]:
    return [r for r in rows if predicate(r)]


def _words(rows: list[SignalRowInput], side: ReportSide) -> float:
    return sum(r.passage_word_count for r in rows if r.report_side == side)


def _count(rows: list[SignalRowInput], side: ReportSide) -> int:
    return sum(1 for r in rows if r.report_side == side)


def _aggregate_pair_features(
    pair: ReportPair,
    run: LanguageSignalRun,
    alignment_run: AlignmentRun,
    feat: ReportPairFeatures,
    rows: list[SignalRowInput],
    config: FinancialLanguageConfig,
) -> ReportPairLanguageFeatures:
    all_passages = rows
    primary_narrative = _filtered(rows, is_primary_narrative_eligible)
    feature_eligible_primary = _filtered(primary_narrative, lambda r: r.feature_eligible)

    excluded_structured = _filtered(rows, lambda r: not is_primary_narrative_eligible(r))
    list_rows = _filtered(rows, lambda r: r.structured_content_category == "list_content")
    table_context_rows = _filtered(rows, lambda r: r.structured_content_category == "table_context")
    currency_rows = _filtered(rows, lambda r: r.structured_content_category == "currency_exposure_table_mixed")
    uncertain_rows = _filtered(rows, lambda r: r.structured_content_category == "uncertain")

    primary_excl_lists = _filtered(feature_eligible_primary, lambda r: r.structured_content_category != "list_content")
    primary_excl_table_context = _filtered(
        feature_eligible_primary, lambda r: r.structured_content_category != "table_context"
    )
    primary_excl_currency = _filtered(
        feature_eligible_primary, lambda r: r.structured_content_category != "currency_exposure_table_mixed"
    )
    primary_excl_uncertain = _filtered(feature_eligible_primary, lambda r: r.structured_content_category != "uncertain")

    earlier_side = aggregate_side(feature_eligible_primary, ReportSide.EARLIER)
    later_side = aggregate_side(feature_eligible_primary, ReportSide.LATER)

    core_changes = {c: compute_core_category_change(c, earlier_side, later_side) for c in CORE_CATEGORIES}

    status_hits = {status: hits_for_status(feature_eligible_primary, status) for status in AlignmentStatus}
    new_hits = status_hits[AlignmentStatus.NEW]
    removed_hits = status_hits[AlignmentStatus.REMOVED]
    ambiguous_hits = status_hits[AlignmentStatus.AMBIGUOUS]

    substantially_modified_rows = _filtered(
        feature_eligible_primary, lambda r: r.alignment_status == AlignmentStatus.SUBSTANTIALLY_MODIFIED
    )
    sm_earlier = aggregate_side(substantially_modified_rows, ReportSide.EARLIER)
    sm_later = aggregate_side(substantially_modified_rows, ReportSide.LATER)

    net_tone_e = net_tone(core_changes["positive"].rate_earlier, core_changes["negative"].rate_earlier)
    net_tone_l = net_tone(core_changes["positive"].rate_later, core_changes["negative"].rate_later)

    all_earlier_words = _words(all_passages, ReportSide.EARLIER)
    all_later_words = _words(all_passages, ReportSide.LATER)
    primary_earlier_words = _words(primary_narrative, ReportSide.EARLIER)
    primary_later_words = _words(primary_narrative, ReportSide.LATER)

    ambiguous_words_total = sum(r.passage_word_count for r in feature_eligible_primary if r.alignment_status == AlignmentStatus.AMBIGUOUS)
    total_eligible_words = sum(r.passage_word_count for r in feature_eligible_primary)
    unmatched_words_total = sum(
        r.passage_word_count
        for r in feature_eligible_primary
        if r.alignment_status in (AlignmentStatus.NEW, AlignmentStatus.REMOVED)
    )
    collision_words_total = sum(r.passage_word_count for r in feature_eligible_primary if r.collision_flag)

    dict_match_rate_earlier = dictionary_match_rate(earlier_side)
    dict_match_rate_later = dictionary_match_rate(later_side)

    report_side_assessment = assess_report_side_quality(
        ReportSideQualityInputs(
            is_transition=pair.is_transition,
            irregular_gap=feat.irregular_gap,
            primary_narrative_word_coverage_earlier=safe_ratio(primary_earlier_words, all_earlier_words),
            primary_narrative_word_coverage_later=safe_ratio(primary_later_words, all_later_words),
            dictionary_match_rate_earlier=dict_match_rate_earlier,
            dictionary_match_rate_later=dict_match_rate_later,
        ),
        config,
    )

    alignment_change_assessment = assess_alignment_change_quality(
        AlignmentChangeQualityInputs(
            alignment_run_status=alignment_run.status,
            alignment_review_reason=alignment_run.review_reason,
            feature_quality=feat.feature_quality,
            is_transition=pair.is_transition,
            irregular_gap=feat.irregular_gap,
            ambiguous_word_share=safe_ratio(ambiguous_words_total, total_eligible_words),
            collision_flagged_word_share=safe_ratio(collision_words_total, total_eligible_words),
            unmatched_word_share=safe_ratio(unmatched_words_total, total_eligible_words),
        ),
        config,
    )

    composite_assessment = combine_quality_for_deprecated_composite(report_side_assessment, alignment_change_assessment)

    # Five persisted alignment-change analytical populations (spec:
    # "Provide and persist at least" all five) -- word coverage under each
    # restriction, for transparency/audit. The *default* population for
    # NEW/REMOVED/SUBSTANTIALLY_MODIFIED attribution is population 1 (all
    # valid alignment rows, i.e. `feature_eligible_primary` itself, same as
    # report-side): the Milestone 6 calibration sensitivity audit found
    # HIGH/MEDIUM/LOW/HIGH-MEDIUM/HIGH-only restrictions retain only
    # ~27-30% of words and materially destabilize results (median net-tone
    # delta ~2.0, max ~7.6), while excluding only genuinely AMBIGUOUS rows
    # retains ~96% of words with a much smaller effect (median ~0.29) --
    # HIGH/MEDIUM-only is deliberately NOT the default merely because it
    # sounds stricter (see financial_language_quality module docstring).
    # NEW/REMOVED/SUBSTANTIALLY_MODIFIED counts below are unaffected by
    # which of these five populations is "selected" in practice (those
    # alignment statuses are already disjoint from AMBIGUOUS), so no
    # separate per-population NEW/REMOVED breakdown is persisted -- only
    # the word-coverage each population would retain, for transparency.
    alignment_eligible_excl_ambiguous = _filtered(
        feature_eligible_primary, lambda r: r.alignment_status != AlignmentStatus.AMBIGUOUS
    )
    alignment_eligible_hml = _filtered(feature_eligible_primary, lambda r: r.confidence != AlignmentConfidence.NEEDS_REVIEW)
    alignment_eligible_hm = _filtered(
        feature_eligible_primary, lambda r: r.confidence in (AlignmentConfidence.HIGH, AlignmentConfidence.MEDIUM)
    )
    alignment_eligible_h = _filtered(feature_eligible_primary, lambda r: r.confidence == AlignmentConfidence.HIGH)

    def _side_words(rows_: list[SignalRowInput], side: ReportSide) -> float:
        return sum(r.passage_word_count for r in rows_ if r.report_side == side)

    return ReportPairLanguageFeatures(
        language_signal_run_id=run.id,
        report_pair_id=pair.id,
        earlier_report_id=pair.earlier_report_id,
        later_report_id=pair.later_report_id,
        all_passages_earlier_count=_count(all_passages, ReportSide.EARLIER),
        all_passages_later_count=_count(all_passages, ReportSide.LATER),
        all_passages_earlier_words=int(all_earlier_words),
        all_passages_later_words=int(all_later_words),
        primary_narrative_earlier_count=_count(primary_narrative, ReportSide.EARLIER),
        primary_narrative_later_count=_count(primary_narrative, ReportSide.LATER),
        primary_narrative_earlier_words=primary_earlier_words,
        primary_narrative_later_words=primary_later_words,
        excluded_structured_content_count=len(excluded_structured),
        excluded_structured_content_words=sum(r.passage_word_count for r in excluded_structured),
        list_content_count=len(list_rows),
        list_content_words=sum(r.passage_word_count for r in list_rows),
        table_context_count=len(table_context_rows),
        table_context_words=sum(r.passage_word_count for r in table_context_rows),
        currency_exposure_mixed_count=len(currency_rows),
        currency_exposure_mixed_words=sum(r.passage_word_count for r in currency_rows),
        uncertain_count=len(uncertain_rows),
        uncertain_words=sum(r.passage_word_count for r in uncertain_rows),
        primary_narrative_words_excluding_lists=sum(r.passage_word_count for r in primary_excl_lists),
        primary_narrative_words_excluding_table_context=sum(r.passage_word_count for r in primary_excl_table_context),
        primary_narrative_words_excluding_currency_exposure_mixed=sum(r.passage_word_count for r in primary_excl_currency),
        primary_narrative_words_excluding_uncertain=sum(r.passage_word_count for r in primary_excl_uncertain),
        positive_count_earlier=core_changes["positive"].count_earlier,
        positive_count_later=core_changes["positive"].count_later,
        positive_rate_earlier=core_changes["positive"].rate_earlier,
        positive_rate_later=core_changes["positive"].rate_later,
        positive_rate_change=core_changes["positive"].rate_change,
        positive_rate_change_abs=core_changes["positive"].rate_change_abs,
        negative_count_earlier=core_changes["negative"].count_earlier,
        negative_count_later=core_changes["negative"].count_later,
        negative_rate_earlier=core_changes["negative"].rate_earlier,
        negative_rate_later=core_changes["negative"].rate_later,
        negative_rate_change=core_changes["negative"].rate_change,
        negative_rate_change_abs=core_changes["negative"].rate_change_abs,
        uncertainty_count_earlier=core_changes["uncertainty"].count_earlier,
        uncertainty_count_later=core_changes["uncertainty"].count_later,
        uncertainty_rate_earlier=core_changes["uncertainty"].rate_earlier,
        uncertainty_rate_later=core_changes["uncertainty"].rate_later,
        uncertainty_rate_change=core_changes["uncertainty"].rate_change,
        uncertainty_rate_change_abs=core_changes["uncertainty"].rate_change_abs,
        litigious_count_earlier=core_changes["litigious"].count_earlier,
        litigious_count_later=core_changes["litigious"].count_later,
        litigious_rate_earlier=core_changes["litigious"].rate_earlier,
        litigious_rate_later=core_changes["litigious"].rate_later,
        litigious_rate_change=core_changes["litigious"].rate_change,
        litigious_rate_change_abs=core_changes["litigious"].rate_change_abs,
        constraining_count_earlier=core_changes["constraining"].count_earlier,
        constraining_count_later=core_changes["constraining"].count_later,
        constraining_rate_earlier=core_changes["constraining"].rate_earlier,
        constraining_rate_later=core_changes["constraining"].rate_later,
        constraining_rate_change=core_changes["constraining"].rate_change,
        constraining_rate_change_abs=core_changes["constraining"].rate_change_abs,
        strong_modal_count_earlier=core_changes["strong_modal"].count_earlier,
        strong_modal_count_later=core_changes["strong_modal"].count_later,
        strong_modal_rate_earlier=core_changes["strong_modal"].rate_earlier,
        strong_modal_rate_later=core_changes["strong_modal"].rate_later,
        strong_modal_rate_change=core_changes["strong_modal"].rate_change,
        strong_modal_rate_change_abs=core_changes["strong_modal"].rate_change_abs,
        weak_modal_count_earlier=core_changes["weak_modal"].count_earlier,
        weak_modal_count_later=core_changes["weak_modal"].count_later,
        weak_modal_rate_earlier=core_changes["weak_modal"].rate_earlier,
        weak_modal_rate_later=core_changes["weak_modal"].rate_later,
        weak_modal_rate_change=core_changes["weak_modal"].rate_change,
        weak_modal_rate_change_abs=core_changes["weak_modal"].rate_change_abs,
        positive_hits_new=new_hits.core["positive"],
        positive_hits_removed=removed_hits.core["positive"],
        positive_hits_ambiguous=ambiguous_hits.core["positive"],
        negative_hits_new=new_hits.core["negative"],
        negative_hits_removed=removed_hits.core["negative"],
        negative_hits_ambiguous=ambiguous_hits.core["negative"],
        uncertainty_hits_new=new_hits.core["uncertainty"],
        uncertainty_hits_removed=removed_hits.core["uncertainty"],
        uncertainty_hits_ambiguous=ambiguous_hits.core["uncertainty"],
        litigious_hits_new=new_hits.core["litigious"],
        litigious_hits_removed=removed_hits.core["litigious"],
        litigious_hits_ambiguous=ambiguous_hits.core["litigious"],
        constraining_hits_new=new_hits.core["constraining"],
        constraining_hits_removed=removed_hits.core["constraining"],
        constraining_hits_ambiguous=ambiguous_hits.core["constraining"],
        strong_modal_hits_new=new_hits.core["strong_modal"],
        strong_modal_hits_removed=removed_hits.core["strong_modal"],
        strong_modal_hits_ambiguous=ambiguous_hits.core["strong_modal"],
        weak_modal_hits_new=new_hits.core["weak_modal"],
        weak_modal_hits_removed=removed_hits.core["weak_modal"],
        weak_modal_hits_ambiguous=ambiguous_hits.core["weak_modal"],
        substantially_modified_positive_rate_change=compute_core_category_change(
            "positive", sm_earlier, sm_later
        ).rate_change,
        substantially_modified_negative_rate_change=compute_core_category_change(
            "negative", sm_earlier, sm_later
        ).rate_change,
        substantially_modified_uncertainty_rate_change=compute_core_category_change(
            "uncertainty", sm_earlier, sm_later
        ).rate_change,
        high_confidence_dictionary_hits=dictionary_hits_by_confidence(
            feature_eligible_primary, (AlignmentConfidence.HIGH,)
        ),
        high_and_medium_confidence_dictionary_hits=dictionary_hits_by_confidence(
            feature_eligible_primary, (AlignmentConfidence.HIGH, AlignmentConfidence.MEDIUM)
        ),
        net_tone_earlier=net_tone_e,
        net_tone_later=net_tone_l,
        net_tone_change=rate_change(net_tone_l, net_tone_e),
        uncertainty_intensity_change=core_changes["uncertainty"].rate_change,
        negative_language_introduction=introduction_or_removal_rate(new_hits, "negative"),
        negative_language_removal=introduction_or_removal_rate(removed_hits, "negative"),
        positive_language_introduction=introduction_or_removal_rate(new_hits, "positive"),
        positive_language_removal=introduction_or_removal_rate(removed_hits, "positive"),
        risk_language_introduction=introduction_or_removal_rate(new_hits, "risk"),
        risk_language_removal=introduction_or_removal_rate(removed_hits, "risk"),
        forward_looking_caution_change=rate_change(
            forward_looking_caution_rate(later_side), forward_looking_caution_rate(earlier_side)
        ),
        governance_language_change=rate_change(
            custom_category_rate(later_side, "governance"), custom_category_rate(earlier_side, "governance")
        ),
        financial_condition_language_change=rate_change(
            custom_category_rate(later_side, "financial_condition"), custom_category_rate(earlier_side, "financial_condition")
        ),
        risk_rate_earlier=custom_category_rate(earlier_side, "risk"),
        risk_rate_later=custom_category_rate(later_side, "risk"),
        financial_condition_rate_earlier=custom_category_rate(earlier_side, "financial_condition"),
        financial_condition_rate_later=custom_category_rate(later_side, "financial_condition"),
        governance_rate_earlier=custom_category_rate(earlier_side, "governance"),
        governance_rate_later=custom_category_rate(later_side, "governance"),
        strategy_rate_earlier=custom_category_rate(earlier_side, "strategy"),
        strategy_rate_later=custom_category_rate(later_side, "strategy"),
        analyzed_word_coverage=safe_ratio(sum(r.passage_word_count for r in all_passages), all_earlier_words + all_later_words),
        primary_narrative_coverage=safe_ratio(primary_earlier_words + primary_later_words, all_earlier_words + all_later_words),
        dictionary_match_rate=safe_ratio(
            sum(r.total_dictionary_hits for r in feature_eligible_primary), total_eligible_words
        ),
        dictionary_match_rate_earlier=dict_match_rate_earlier,
        dictionary_match_rate_later=dict_match_rate_later,
        list_content_share=safe_ratio(sum(r.passage_word_count for r in list_rows), total_eligible_words or 1),
        uncertain_content_share=safe_ratio(sum(r.passage_word_count for r in uncertain_rows), total_eligible_words or 1),
        ambiguous_alignment_share=safe_ratio(ambiguous_words_total, total_eligible_words),
        low_confidence_share=feat.review_required_share,
        collision_flagged_word_share=safe_ratio(collision_words_total, total_eligible_words),
        unmatched_word_share=safe_ratio(unmatched_words_total, total_eligible_words),
        alignment_change_analyzed_words_all=total_eligible_words,
        alignment_change_analyzed_words_excl_ambiguous=sum(r.passage_word_count for r in alignment_eligible_excl_ambiguous),
        alignment_change_analyzed_words_hml=sum(r.passage_word_count for r in alignment_eligible_hml),
        alignment_change_analyzed_words_hm=sum(r.passage_word_count for r in alignment_eligible_hm),
        alignment_change_analyzed_words_h=sum(r.passage_word_count for r in alignment_eligible_h),
        ambiguous_words_in_report_side=ambiguous_words_total,
        report_side_signal_quality=report_side_assessment.quality,
        report_side_primary_eligible=report_side_assessment.primary_eligible,
        report_side_warning_reasons=report_side_assessment.warning_reasons,
        report_side_exclusion_reasons=report_side_assessment.exclusion_reasons,
        alignment_change_signal_quality=alignment_change_assessment.quality,
        alignment_change_primary_eligible=alignment_change_assessment.primary_eligible,
        alignment_change_warning_reasons=alignment_change_assessment.warning_reasons,
        alignment_change_exclusion_reasons=alignment_change_assessment.exclusion_reasons,
        language_signal_quality=composite_assessment.quality,
        primary_eligible=composite_assessment.primary_eligible,
        warning_reasons=composite_assessment.warning_reasons,
        exclusion_reasons=composite_assessment.exclusion_reasons,
    )


@dataclass
class BatchBuildOutcome:
    completed: list[uuid.UUID] = field(default_factory=list)
    completed_with_warnings: list[uuid.UUID] = field(default_factory=list)
    skipped: list[uuid.UUID] = field(default_factory=list)
    ineligible: list[tuple[uuid.UUID, str]] = field(default_factory=list)
    failed: list[tuple[uuid.UUID, str]] = field(default_factory=list)


def build_eligible_language_signals(
    session: Session, *, limit: int | None = None, force: bool = False
) -> BatchBuildOutcome:
    outcome = BatchBuildOutcome()
    pairs = session.scalars(select(ReportPair).order_by(ReportPair.company_id, ReportPair.created_at)).all()
    if limit is not None:
        pairs = pairs[:limit]

    for pair in pairs:
        try:
            result = build_language_signals(session, pair, force=force)
        except Exception:
            logger.exception("unexpected orchestration error building language signals for pair %s", pair.id)
            outcome.failed.append((pair.id, "unexpected orchestration error"))
            continue

        if result.ineligible:
            outcome.ineligible.append((pair.id, result.ineligible_reason or "ineligible"))
            continue
        if result.skipped:
            outcome.skipped.append(pair.id)
            continue

        run = result.run
        if run is None:
            continue
        if run.status == LanguageSignalRunStatus.FAILED:
            outcome.failed.append((pair.id, run.error_message or "unknown error"))
        elif run.status == LanguageSignalRunStatus.COMPLETED:
            outcome.completed.append(pair.id)
        elif run.status == LanguageSignalRunStatus.COMPLETED_WITH_WARNINGS:
            outcome.completed_with_warnings.append(pair.id)

    return outcome

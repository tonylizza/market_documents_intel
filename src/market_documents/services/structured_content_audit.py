"""Audit-only operationalization of "structured content" leaking into the
narrative corpus, for Milestone 6 readiness review.

No production classification named `structured_leak` exists anywhere in this
codebase -- `block_classification.py` and `passage_segmentation.py` only ever
produce `BlockType`/`PassageType`, plus the passage-level numeric-density
exclusion (`PassageConfig.numeric_density_exclusion_threshold`). This module
defines a transparent, audit-only category system on top of those existing
signals so the question "does structured/graphical content leak into the
Milestone 5 corpus, and would excluding it change the features?" can be
answered without changing any extraction, segmentation, alignment, or
feature-build behavior. Nothing here writes to the database, and nothing
here is consulted by `passage_segmentation.py`/`feature_extraction.py` --
it is a read-only report, mirroring `corpus_audit.py`/`alignment_audit.py`/
`feature_audit.py`.

Ten mutually-exclusive audit categories (first matching rule wins, in the
priority order documented in `classify_passage`):

  short_fragment_invalid       -- isolated one-word, <=2-char heading passage
  broken_fragment_sequence     -- many isolated short tokens/lines (diagram-
                                   shattered text), heading or not
  list_content                 -- PassageType.LIST or any LIST_ITEM source
                                   block, never itself treated as invalid
  table_context                -- PassageType.TABLE_CONTEXT (adjacency to an
                                   excluded table, not proof of leaked table
                                   content)
  numeric_or_table_like_source -- elevated digit ratio bordering (but under)
                                   the existing block/passage numeric
                                   exclusion thresholds
  contents_or_index_like       -- dot-leader / "Contents" / GRI-ESG-index
                                   keyword patterns
  caption_or_label_like        -- "Figure/Table/Chart/Source" prefixes, or a
                                   short heading-only label with no sentence
  legitimate_short_abbreviation -- short heading (any length) attached to
                                   coherent, sentence-punctuated body prose
  ordinary_prose_false_positive -- initially matched a leakage rule (table_
                                   context / numeric) but reads as coherent
                                   narrative prose on the deterministic
                                   coherence proxy documented below
  uncertain                    -- evidence does not cleanly support any of
                                   the above

Every category's rule is either a quoted deterministic predicate (documented
inline) or explicitly marked as a heuristic proxy standing in for human
review (`ordinary_prose_false_positive`) -- never an opaque score.
"""

import csv
import re
import statistics
import uuid
from collections import defaultdict
from dataclasses import dataclass, field, fields
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from market_documents.models.alignment import AlignmentRun, PassageAlignment
from market_documents.models.company import Company
from market_documents.models.enums import AlignmentConfidence, AlignmentStatus, BlockType, PassageType
from market_documents.models.extraction import NarrativeDocument, TextBlock
from market_documents.models.passage import Passage, PassageSegmentationRun, PassageSourceBlock
from market_documents.models.report import Report
from market_documents.models.report_pair import ReportPair
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.feature_config import FEATURE_CONFIG, FeatureConfig
from market_documents.services.feature_extraction import get_current_report_pair_features_by_pair
from market_documents.services.feature_metrics import (
    AlignmentRowInput,
    aggregate_outcomes,
    compute_alignment_coverage,
    compute_score_components,
    count_rates,
    passage_excluded_from_features,
    safe_ratio,
    word_rates,
)
from market_documents.services.feature_quality import QualityInputs, assess_feature_quality
from market_documents.services.passage_alignment import get_current_alignment_runs_by_pair
from market_documents.services.passage_segmentation import get_current_segmentation_run
from market_documents.services.similarity import get_current_document_similarities_by_pair

# --------------------------------------------------------------------------
# Category names (audit-only -- see module docstring)
# --------------------------------------------------------------------------

SHORT_FRAGMENT_INVALID = "short_fragment_invalid"
BROKEN_FRAGMENT_SEQUENCE = "broken_fragment_sequence"
LIST_CONTENT = "list_content"
TABLE_CONTEXT = "table_context"
NUMERIC_OR_TABLE_LIKE_SOURCE = "numeric_or_table_like_source"
CONTENTS_OR_INDEX_LIKE = "contents_or_index_like"
CAPTION_OR_LABEL_LIKE = "caption_or_label_like"
LEGITIMATE_SHORT_ABBREVIATION = "legitimate_short_abbreviation"
ORDINARY_PROSE_FALSE_POSITIVE = "ordinary_prose_false_positive"
UNCERTAIN = "uncertain"

EXCLUDE = "EXCLUDE"
RETAIN = "RETAIN"
REVIEW = "REVIEW"

# Categories a human should never be told to blanket-exclude, regardless of
# how they were reached -- lists and table-adjacent prose may carry genuine
# disclosure, legitimate abbreviations and false positives are real prose,
# and "uncertain" means the evidence does not support a confident exclusion.
_NEVER_EXCLUDE_CATEGORIES = frozenset(
    {LIST_CONTENT, TABLE_CONTEXT, LEGITIMATE_SHORT_ABBREVIATION, ORDINARY_PROSE_FALSE_POSITIVE, UNCERTAIN}
)

# --------------------------------------------------------------------------
# Deterministic content-pattern rules
# --------------------------------------------------------------------------

_GRI_ESG_RE = re.compile(
    r"\bGRI\b|\bSASB\b|\bTCFD\b|\bESG\s+index\b|sustainability\s+index|integrated\s+report(?:ing)?\s+index|\bIIRC\b",
    re.IGNORECASE,
)
_DOT_LEADER_RE = re.compile(r"\.{3,}\s*\d{1,4}\b")
_CONTENTS_HEADING_RE = re.compile(r"^\s*(contents|table of contents|index)\s*$", re.IGNORECASE)
_CAPTION_PREFIX_RE = re.compile(r"^\s*(figure|table|chart|graph|source)\s*[:\-\d]", re.IGNORECASE)
_SENTENCE_END_RE = re.compile(r"[.!?]")

# Elevated-but-under-threshold digit density: the block-level TABLE_LIKE cut
# is 0.30 (`ExtractionConfig.table_like_min_digit_ratio`) and the passage-
# level hard exclusion is 0.35 (`PassageConfig.numeric_density_exclusion_
# threshold`); 0.15 is deliberately inclusive of everything "bordering" those
# thresholds so the sampling/false-positive-rate check (item 8 of the audit
# brief) has real material to test against, not a pre-narrowed population.
NUMERIC_ELEVATED_THRESHOLD = 0.15

# Fraction of alphabetic body tokens at or under this length that marks a
# passage as diagram-shattered rather than real running text -- calibrated
# against the corpus's own 22 body-bearing two-character-heading passages
# (see tests/test_structured_content_audit.py for the worked examples this
# threshold was set from: "al"/"te"/"ll" bodies are >0.9; "NC"/"SC"/"IC"/
# "HC"/"FC"/"CA"/"IT" bodies are <0.2).
FRAGMENT_TOKEN_RATIO_THRESHOLD = 0.5
FRAGMENT_TOKEN_MAX_LENGTH = 3

# Coherence-proxy thresholds for `ordinary_prose_false_positive` -- a stand-in
# for human review (see module docstring), not a claim of certainty.
FALSE_POSITIVE_MIN_WORDS = 40
FALSE_POSITIVE_MAX_FRAGMENT_RATIO = 0.3
FALSE_POSITIVE_MAX_DIGIT_RATIO = 0.20


def digit_ratio(text: str) -> float:
    return sum(ch.isdigit() for ch in text) / len(text) if text else 0.0


def fragment_token_ratio(text: str) -> float:
    """Fraction of this passage's constituent blocks (rejoined with `"\\n\\n"`
    by `passage_segmentation._finalize_group`) that are themselves tiny
    (<=`FRAGMENT_TOKEN_MAX_LENGTH` alphabetic characters, ignoring internal
    whitespace) -- the signature of text that PDF extraction shattered into
    single glyphs/syllables, each glyph-run becoming its own TextBlock and
    hence its own `"\\n\\n"`-joined segment (curved or rotated diagram text;
    see `block_classification.py`'s documented root cause for the one-
    character case). Deliberately segment-based, not whitespace-token-based:
    ordinary prose is full of short *words* ("is", "a", "for", "the") that a
    naive per-word length check would misclassify as fragments, but those
    words never each occupy their own source block/segment the way shattered
    glyph-runs do. A body with no non-blank segments at all counts as fully
    fragmented (ratio 1.0), never as coherent by default."""
    segments = [s.strip() for s in text.split("\n\n") if s.strip()]
    if not segments:
        return 1.0
    fragment_count = sum(1 for s in segments if sum(ch.isalpha() for ch in s) <= FRAGMENT_TOKEN_MAX_LENGTH)
    return fragment_count / len(segments)


def has_sentence_punctuation(text: str) -> bool:
    return bool(_SENTENCE_END_RE.search(text))


def _body_after_heading(raw_text: str, heading_text: str | None) -> str:
    """`raw_text` with a leading `heading_text` line stripped, so fragment-
    ratio/sentence-punctuation checks assess the passage's body, not its
    (possibly corrupted) heading token itself."""
    if not heading_text:
        return raw_text
    stripped = raw_text.strip()
    heading_stripped = heading_text.strip()
    if stripped.startswith(heading_stripped):
        return stripped[len(heading_stripped) :]
    return raw_text


# --------------------------------------------------------------------------
# Pure classification
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class PassageAuditInput:
    """ORM-free view of one Passage plus its constituent block types, so
    `classify_passage` is independently unit-testable without a database."""

    passage_id: uuid.UUID
    raw_text: str
    heading_text: str | None
    word_count: int
    passage_type: PassageType
    block_types: tuple[BlockType, ...] = ()


@dataclass(frozen=True)
class Classification:
    category: str | None
    rule_evidence: str
    suggested_action: str | None
    is_two_char_heading: bool


def _two_char_classification(ctx: PassageAuditInput) -> Classification:
    """Classification specific to passages whose (trimmed) heading_text is
    exactly two characters -- see the module docstring's worked examples.
    Deliberately never collapses to a single blanket rule: a one-word
    fragment, a diagram-shattered multi-word body, a bullet/label-like
    diagram callout, and a corrupted-heading-but-real-body passage are all
    structurally distinguishable from the passage's own content."""
    heading = (ctx.heading_text or "").strip()

    if ctx.word_count == 1:
        is_alpha_upper = heading.isalpha() and heading.isupper()
        action = REVIEW if is_alpha_upper else EXCLUDE
        rationale = (
            f"heading_text={heading!r}, word_count=1, passage_type=HEADING_WITH_BODY -- isolated token with no "
            "body, the same failure signature as the fixed one-character DECORATIVE_OR_FRAGMENT rule in "
            "block_classification.py, just one character wider. "
            + (
                "All-uppercase: plausibly a recurring diagram/table label rather than a mid-word glyph "
                "fragment -- retained for human confirmation rather than auto-excluded."
                if is_alpha_upper
                else "Lowercase/mixed-case: matches the corpus's observed mid-word bigram-fragment pattern "
                "(e.g. 'rs', 'er', 'nt', 'te') -- no plausible legitimate reading."
            )
        )
        return Classification(SHORT_FRAGMENT_INVALID, rationale, action, True)

    body = _body_after_heading(ctx.raw_text, ctx.heading_text)
    frag_ratio = fragment_token_ratio(body)
    coherent = has_sentence_punctuation(body)

    if frag_ratio > FRAGMENT_TOKEN_RATIO_THRESHOLD:
        rationale = (
            f"heading_text={heading!r}, word_count={ctx.word_count}, body fragment-token ratio "
            f"{frag_ratio:.2f} > {FRAGMENT_TOKEN_RATIO_THRESHOLD} -- body is itself mostly one-to-three-"
            "character tokens, i.e. the same diagram-text-shattering that produced the corrupted heading "
            "extends through the whole passage; no narrative content to preserve."
        )
        return Classification(BROKEN_FRAGMENT_SEQUENCE, rationale, EXCLUDE, True)

    if coherent:
        rationale = (
            f"heading_text={heading!r}, word_count={ctx.word_count}, body fragment-token ratio {frag_ratio:.2f} "
            f"<= {FRAGMENT_TOKEN_RATIO_THRESHOLD} and contains sentence-ending punctuation -- the heading label "
            "is corrupted/truncated but the body is coherent narrative prose. Retaining the passage preserves "
            "real disclosure content; only the heading metadata is unreliable."
        )
        return Classification(LEGITIMATE_SHORT_ABBREVIATION, rationale, RETAIN, True)

    rationale = (
        f"heading_text={heading!r}, word_count={ctx.word_count}, body fragment-token ratio {frag_ratio:.2f} "
        f"<= {FRAGMENT_TOKEN_RATIO_THRESHOLD} but no sentence-ending punctuation -- reads as a list of short "
        "diagram/label callouts (e.g. strategy pillars, risk-register items, an org-chart entry), not flowing "
        "narrative prose. May carry real informational content but is not independent narrative disclosure."
    )
    return Classification(CAPTION_OR_LABEL_LIKE, rationale, REVIEW, True)


def classify_passage(ctx: PassageAuditInput) -> Classification | None:
    """Return this passage's audit classification, or `None` if it matches no
    audit category at all (the common case -- most of the corpus is
    unflagged ordinary prose and never appears in `structured_leak_passages.
    csv`). Priority order below is fixed and evaluated top to bottom; the
    first matching rule wins, so a passage is never assigned more than one
    category."""
    heading = (ctx.heading_text or "").strip()
    if heading and len(heading) == 2 and ctx.passage_type == PassageType.HEADING_WITH_BODY:
        return _two_char_classification(ctx)

    stripped = ctx.raw_text.strip()

    # A broken-fragment sequence can occur without a corrupted heading at
    # all (e.g. a paragraph-boundary passage that swallowed shattered
    # diagram text) -- checked before the more specific content-keyword
    # rules below, since a passage this corrupted cannot be meaningfully
    # read as contents/GRI/caption content either.
    frag_ratio = fragment_token_ratio(stripped)
    if ctx.word_count >= 10 and frag_ratio > FRAGMENT_TOKEN_RATIO_THRESHOLD:
        rationale = (
            f"word_count={ctx.word_count}, whole-passage fragment-token ratio {frag_ratio:.2f} > "
            f"{FRAGMENT_TOKEN_RATIO_THRESHOLD} -- mostly one-to-three-character tokens throughout, independent "
            "of any heading; consistent with diagram/curved-text shattering."
        )
        return Classification(BROKEN_FRAGMENT_SEQUENCE, rationale, EXCLUDE, False)

    if _GRI_ESG_RE.search(ctx.raw_text) or _DOT_LEADER_RE.search(ctx.raw_text) or _CONTENTS_HEADING_RE.match(stripped):
        which = (
            "GRI/ESG/TCFD/SASB/IIRC keyword"
            if _GRI_ESG_RE.search(ctx.raw_text)
            else ("dot-leader page-reference pattern" if _DOT_LEADER_RE.search(ctx.raw_text) else "'Contents'/'Index' heading-only")
        )
        return Classification(
            CONTENTS_OR_INDEX_LIKE,
            f"matched deterministic pattern: {which}.",
            EXCLUDE,
            False,
        )

    if _CAPTION_PREFIX_RE.match(stripped):
        return Classification(
            CAPTION_OR_LABEL_LIKE,
            "matched deterministic pattern: leading 'Figure/Table/Chart/Source' caption prefix.",
            EXCLUDE,
            False,
        )

    ratio = digit_ratio(ctx.raw_text)
    if ctx.word_count >= 5 and ratio >= NUMERIC_ELEVATED_THRESHOLD:
        if (
            ctx.word_count >= FALSE_POSITIVE_MIN_WORDS
            and has_sentence_punctuation(ctx.raw_text)
            and frag_ratio < FALSE_POSITIVE_MAX_FRAGMENT_RATIO
            and ratio < FALSE_POSITIVE_MAX_DIGIT_RATIO
        ):
            rationale = (
                f"digit_ratio={ratio:.2f} initially matched the numeric_or_table_like_source rule "
                f"(>= {NUMERIC_ELEVATED_THRESHOLD}), but word_count={ctx.word_count} >= "
                f"{FALSE_POSITIVE_MIN_WORDS}, contains sentence punctuation, and fragment-token ratio "
                f"{frag_ratio:.2f} < {FALSE_POSITIVE_MAX_FRAGMENT_RATIO} -- coherence-proxy override to a "
                "false positive (see module docstring: this proxy stands in for human review, not a "
                "certainty)."
            )
            return Classification(ORDINARY_PROSE_FALSE_POSITIVE, rationale, RETAIN, False)
        rationale = (
            f"digit_ratio={ratio:.2f} >= {NUMERIC_ELEVATED_THRESHOLD} (elevated, bordering but under the "
            "existing block-level TABLE_LIKE cut of 0.30 and passage-level hard-exclusion cut of 0.35) -- "
            "escaped both existing numeric-density exclusions."
        )
        return Classification(NUMERIC_OR_TABLE_LIKE_SOURCE, rationale, EXCLUDE, False)

    # Deliberately does NOT flag "any short heading with no sentence
    # punctuation" in the general population: sampling against the real
    # corpus showed that pattern matches thousands of entirely ordinary,
    # short section-title passages (e.g. "AUDIT COMMITTEE", "Grow and
    # strengthen our businesses") that are legitimate brief headings, not
    # diagram/caption leakage -- there is no reliable general-population
    # signal for this without much stronger corroborating evidence. The
    # two-character-heading-specific version of this check in
    # `_two_char_classification` stays: it is scoped to the narrow, already-
    # suspicious two-character-heading population where it was validated
    # against sampled real passages (see module docstring).

    if ctx.passage_type == PassageType.TABLE_CONTEXT:
        if (
            ctx.word_count >= FALSE_POSITIVE_MIN_WORDS
            and has_sentence_punctuation(ctx.raw_text)
            and frag_ratio < FALSE_POSITIVE_MAX_FRAGMENT_RATIO
        ):
            rationale = (
                f"passage_type=TABLE_CONTEXT (adjacent to an excluded table block) initially matched, but "
                f"word_count={ctx.word_count} >= {FALSE_POSITIVE_MIN_WORDS} with sentence punctuation and low "
                "fragment ratio -- coherence-proxy override to a false positive: adjacency to a table is not "
                "evidence this specific passage's own text is table content."
            )
            return Classification(ORDINARY_PROSE_FALSE_POSITIVE, rationale, RETAIN, False)
        return Classification(
            TABLE_CONTEXT,
            "passage_type=TABLE_CONTEXT: adjacent to an excluded TABLE_LIKE block in reading order "
            "(passage_segmentation.py's `_find_table_adjacent_ids`) -- adjacency only, not proof this "
            "passage's own text is table content.",
            None,
            False,
        )

    is_list = ctx.passage_type == PassageType.LIST or BlockType.LIST_ITEM in ctx.block_types
    if is_list:
        which = "passage_type=LIST (every source block is LIST_ITEM)" if ctx.passage_type == PassageType.LIST else (
            "at least one source block is LIST_ITEM (mixed list/prose passage)"
        )
        return Classification(
            LIST_CONTENT,
            f"{which} -- lists may carry substantive narrative disclosure and are never auto-invalidated.",
            None,
            False,
        )

    return None


# --------------------------------------------------------------------------
# ORM-facing current-run resolution
# --------------------------------------------------------------------------


def current_segmentation_run_for_report(session: Session, report: Report) -> PassageSegmentationRun | None:
    """The current passage population for one report, resolved through the
    full current-run chain (Report -> current ExtractionRun -> its
    NarrativeDocument -> current PassageSegmentationRun for that document) --
    never by taking the latest segmentation run per `narrative_document_id`
    across every historical extraction, which over-counts any report that
    has been re-extracted more than once."""
    extraction_run = get_current_extraction_run(session, report.id)
    if extraction_run is None:
        return None
    narrative = session.scalar(
        select(NarrativeDocument).where(NarrativeDocument.extraction_run_id == extraction_run.id)
    )
    if narrative is None:
        return None
    return get_current_segmentation_run(session, narrative.id)


@dataclass(frozen=True)
class CurrentReportContext:
    report: Report
    company: Company
    segmentation_run: PassageSegmentationRun


def current_report_contexts(session: Session) -> list[CurrentReportContext]:
    reports = session.scalars(
        select(Report).options(joinedload(Report.company)).join(Company).order_by(Company.ticker, Report.directory_year)
    ).all()
    contexts: list[CurrentReportContext] = []
    for report in reports:
        seg = current_segmentation_run_for_report(session, report)
        if seg is not None:
            contexts.append(CurrentReportContext(report=report, company=report.company, segmentation_run=seg))
    return contexts


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


def _source_block_ids_by_passage(session: Session, passage_ids: list[uuid.UUID]) -> dict[uuid.UUID, list[uuid.UUID]]:
    if not passage_ids:
        return {}
    rows = session.execute(
        select(PassageSourceBlock.passage_id, PassageSourceBlock.text_block_id)
        .where(PassageSourceBlock.passage_id.in_(passage_ids))
        .order_by(PassageSourceBlock.passage_id, PassageSourceBlock.source_order)
    ).all()
    out: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for passage_id, text_block_id in rows:
        out[passage_id].append(text_block_id)
    return out


def to_audit_input(passage: Passage, block_types: list[BlockType] | None = None) -> PassageAuditInput:
    return PassageAuditInput(
        passage_id=passage.id,
        raw_text=passage.raw_text,
        heading_text=passage.heading_text,
        word_count=passage.word_count,
        passage_type=passage.passage_type,
        block_types=tuple(block_types or ()),
    )


# --------------------------------------------------------------------------
# Corpus-wide audit assembly
# --------------------------------------------------------------------------


@dataclass
class PassageAuditRow:
    ticker: str
    company_name: str
    report_id: str
    directory_year: int
    period_end: str | None
    extraction_run_id: str
    segmentation_run_id: str
    passage_id: str
    passage_index: int
    first_page_number: int
    last_page_number: int
    passage_type: str
    heading_text: str | None
    word_count: int
    character_count: int
    excluded_from_alignment: bool
    feature_eligible: bool
    category: str
    rule_evidence: str
    suggested_action: str | None
    is_two_char_heading: bool
    constituent_block_types: str
    source_block_ids: str
    text_excerpt: str


def build_passage_audit_rows(
    session: Session, config: FeatureConfig = FEATURE_CONFIG
) -> tuple[list[PassageAuditRow], list[CurrentReportContext], dict[uuid.UUID, Passage], dict[uuid.UUID, Classification]]:
    """Classify every current passage in the corpus.

    Returns the flagged-row CSV population, the resolved current-report
    contexts (for company/year rollups), a passage_id -> Passage lookup, and
    a passage_id -> Classification lookup covering every current passage
    (including unflagged ones, `category is None`) so feature-sensitivity
    recomputation can reuse the same classification pass.
    """
    contexts = current_report_contexts(session)
    seg_run_ids = [c.segmentation_run.id for c in contexts]
    context_by_seg_run = {c.segmentation_run.id: c for c in contexts}

    passages = (
        session.scalars(select(Passage).where(Passage.segmentation_run_id.in_(seg_run_ids))).all()
        if seg_run_ids
        else []
    )
    passage_ids = [p.id for p in passages]
    block_types_by_passage = _block_types_by_passage(session, passage_ids)

    rows: list[PassageAuditRow] = []
    passages_by_id: dict[uuid.UUID, Passage] = {}
    classifications_by_id: dict[uuid.UUID, Classification] = {}

    flagged_ids: list[uuid.UUID] = []
    for passage in passages:
        passages_by_id[passage.id] = passage
        block_types = block_types_by_passage.get(passage.id, [])
        ctx = to_audit_input(passage, block_types)
        classification = classify_passage(ctx)
        classifications_by_id[passage.id] = classification if classification is not None else Classification(
            None, "", None, False
        )
        if classification is not None and classification.category is not None:
            flagged_ids.append(passage.id)

    source_block_ids_by_passage = _source_block_ids_by_passage(session, flagged_ids)

    for passage_id in flagged_ids:
        passage = passages_by_id[passage_id]
        classification = classifications_by_id[passage_id]
        report_ctx = context_by_seg_run[passage.segmentation_run_id]
        block_types = block_types_by_passage.get(passage_id, [])
        rows.append(
            PassageAuditRow(
                ticker=report_ctx.company.ticker,
                company_name=report_ctx.company.company_name,
                report_id=str(report_ctx.report.id),
                directory_year=report_ctx.report.directory_year,
                period_end=report_ctx.report.period_end.isoformat() if report_ctx.report.period_end else None,
                extraction_run_id=str(passage.extraction_run_id),
                segmentation_run_id=str(passage.segmentation_run_id),
                passage_id=str(passage.id),
                passage_index=passage.passage_index,
                first_page_number=passage.first_page_number,
                last_page_number=passage.last_page_number,
                passage_type=passage.passage_type.value,
                heading_text=passage.heading_text,
                word_count=passage.word_count,
                character_count=passage.character_count,
                excluded_from_alignment=passage.excluded_from_alignment,
                feature_eligible=not passage_excluded_from_features(passage.word_count, passage.passage_type, config),
                category=classification.category,
                rule_evidence=classification.rule_evidence,
                suggested_action=classification.suggested_action,
                is_two_char_heading=classification.is_two_char_heading,
                constituent_block_types="|".join(bt.value for bt in block_types),
                source_block_ids="|".join(str(bid) for bid in source_block_ids_by_passage.get(passage_id, [])),
                text_excerpt=passage.raw_text[:240].replace("\n", " "),
            )
        )

    rows.sort(key=lambda r: (r.ticker, r.directory_year, r.passage_index))
    return rows, contexts, passages_by_id, classifications_by_id


def write_passage_audit_csv(rows: list[PassageAuditRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(PassageAuditRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# structured_leak_summary_by_company.csv
# --------------------------------------------------------------------------


@dataclass
class CompanySummaryRow:
    ticker: str
    reports_current: int
    current_passages: int
    current_passage_words: int
    flagged_passages: int
    flagged_passage_words: int
    flagged_share_count: float | None
    flagged_share_words: float | None
    feature_eligible_flagged_passages: int
    feature_eligible_flagged_words: int
    short_fragment_invalid_count: int
    broken_fragment_sequence_count: int
    list_content_count: int
    table_context_count: int
    numeric_or_table_like_source_count: int
    contents_or_index_like_count: int
    caption_or_label_like_count: int
    legitimate_short_abbreviation_count: int
    ordinary_prose_false_positive_count: int
    uncertain_count: int


_CATEGORY_FIELD_MAP = {
    SHORT_FRAGMENT_INVALID: "short_fragment_invalid_count",
    BROKEN_FRAGMENT_SEQUENCE: "broken_fragment_sequence_count",
    LIST_CONTENT: "list_content_count",
    TABLE_CONTEXT: "table_context_count",
    NUMERIC_OR_TABLE_LIKE_SOURCE: "numeric_or_table_like_source_count",
    CONTENTS_OR_INDEX_LIKE: "contents_or_index_like_count",
    CAPTION_OR_LABEL_LIKE: "caption_or_label_like_count",
    LEGITIMATE_SHORT_ABBREVIATION: "legitimate_short_abbreviation_count",
    ORDINARY_PROSE_FALSE_POSITIVE: "ordinary_prose_false_positive_count",
    UNCERTAIN: "uncertain_count",
}


def build_company_summary_rows(
    rows: list[PassageAuditRow], contexts: list[CurrentReportContext], passages_by_id: dict[uuid.UUID, Passage]
) -> list[CompanySummaryRow]:
    tickers = sorted({c.company.ticker for c in contexts})
    reports_by_ticker: dict[str, int] = defaultdict(int)
    for c in contexts:
        reports_by_ticker[c.company.ticker] += 1

    current_passages_by_ticker: dict[str, int] = defaultdict(int)
    current_words_by_ticker: dict[str, int] = defaultdict(int)
    seg_run_to_ticker = {c.segmentation_run.id: c.company.ticker for c in contexts}
    for passage in passages_by_id.values():
        ticker = seg_run_to_ticker.get(passage.segmentation_run_id)
        if ticker is None:
            continue
        current_passages_by_ticker[ticker] += 1
        current_words_by_ticker[ticker] += passage.word_count

    out: list[CompanySummaryRow] = []
    for ticker in tickers:
        ticker_rows = [r for r in rows if r.ticker == ticker]
        flagged_words = sum(r.word_count for r in ticker_rows)
        eligible_rows = [r for r in ticker_rows if r.feature_eligible]
        category_counts = {field_name: 0 for field_name in _CATEGORY_FIELD_MAP.values()}
        for r in ticker_rows:
            field_name = _CATEGORY_FIELD_MAP.get(r.category)
            if field_name:
                category_counts[field_name] += 1
        out.append(
            CompanySummaryRow(
                ticker=ticker,
                reports_current=reports_by_ticker[ticker],
                current_passages=current_passages_by_ticker[ticker],
                current_passage_words=current_words_by_ticker[ticker],
                flagged_passages=len(ticker_rows),
                flagged_passage_words=flagged_words,
                flagged_share_count=safe_ratio(len(ticker_rows), current_passages_by_ticker[ticker]),
                flagged_share_words=safe_ratio(flagged_words, current_words_by_ticker[ticker]),
                feature_eligible_flagged_passages=len(eligible_rows),
                feature_eligible_flagged_words=sum(r.word_count for r in eligible_rows),
                **category_counts,
            )
        )
    return out


def write_company_summary_csv(rows: list[CompanySummaryRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(CompanySummaryRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# two_character_heading_review.csv
# --------------------------------------------------------------------------


@dataclass
class TwoCharHeadingRow:
    ticker: str
    report_id: str
    directory_year: int
    passage_id: str
    heading_text: str
    word_count: int
    body_present: bool
    first_page_number: int
    passage_type: str
    constituent_block_types: str
    text_excerpt: str
    category: str
    rule_evidence: str
    suggested_action: str


def build_two_char_heading_rows(
    contexts: list[CurrentReportContext],
    passages_by_id: dict[uuid.UUID, Passage],
    classifications_by_id: dict[uuid.UUID, Classification],
) -> list[TwoCharHeadingRow]:
    seg_run_to_context = {c.segmentation_run.id: c for c in contexts}
    out: list[TwoCharHeadingRow] = []
    for passage in passages_by_id.values():
        heading = (passage.heading_text or "").strip()
        if passage.passage_type != PassageType.HEADING_WITH_BODY or len(heading) != 2:
            continue
        classification = classifications_by_id[passage.id]
        report_ctx = seg_run_to_context[passage.segmentation_run_id]
        out.append(
            TwoCharHeadingRow(
                ticker=report_ctx.company.ticker,
                report_id=str(report_ctx.report.id),
                directory_year=report_ctx.report.directory_year,
                passage_id=str(passage.id),
                heading_text=passage.heading_text or "",
                word_count=passage.word_count,
                body_present=passage.word_count > 1,
                first_page_number=passage.first_page_number,
                passage_type=passage.passage_type.value,
                constituent_block_types="",
                text_excerpt=passage.raw_text[:240].replace("\n", " "),
                category=classification.category or UNCERTAIN,
                rule_evidence=classification.rule_evidence,
                suggested_action=classification.suggested_action or REVIEW,
            )
        )
    out.sort(key=lambda r: (r.body_present, r.ticker, r.directory_year, r.heading_text))
    return out


def write_two_char_heading_csv(rows: list[TwoCharHeadingRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(TwoCharHeadingRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# Feature-sensitivity recomputation (A / B / C), in memory only
# --------------------------------------------------------------------------


def is_two_char_heading_passage(passage: Passage) -> bool:
    heading = (passage.heading_text or "").strip()
    return passage.passage_type == PassageType.HEADING_WITH_BODY and len(heading) == 2


def excluded_in_variant_b(category: str | None, is_two_char: bool) -> bool:
    """"Clearly invalid structured or graphical leakage", excluding
    two-character-heading-specific fragments (those are variant C's
    incremental addition, so B and C's difference isolates their impact).
    Never excludes list_content, table_context, legitimate_short_
    abbreviation, ordinary_prose_false_positive, or uncertain."""
    if category is None or category in _NEVER_EXCLUDE_CATEGORIES:
        return False
    if category == SHORT_FRAGMENT_INVALID:
        return False  # inherently two-char-heading-scoped; variant C only.
    if category == BROKEN_FRAGMENT_SEQUENCE and is_two_char:
        return False  # two-char-heading-driven case; variant C only.
    return category in (BROKEN_FRAGMENT_SEQUENCE, NUMERIC_OR_TABLE_LIKE_SOURCE, CONTENTS_OR_INDEX_LIKE, CAPTION_OR_LABEL_LIKE)


def excluded_in_variant_c(category: str | None, is_two_char: bool) -> bool:
    if excluded_in_variant_b(category, is_two_char):
        return True
    if is_two_char and category in (SHORT_FRAGMENT_INVALID, BROKEN_FRAGMENT_SEQUENCE):
        return True
    return False


@dataclass(frozen=True)
class _RowContext:
    alignment_status: AlignmentStatus
    confidence: AlignmentConfidence
    earlier_passage_id: uuid.UUID | None
    later_passage_id: uuid.UUID | None
    earlier_word_count: int | None
    later_word_count: int | None
    earlier_passage_type: PassageType | None
    later_passage_type: PassageType | None

    def to_alignment_row_input(self) -> AlignmentRowInput:
        return AlignmentRowInput(
            alignment_status=self.alignment_status,
            confidence=self.confidence,
            earlier_word_count=self.earlier_word_count,
            later_word_count=self.later_word_count,
            earlier_passage_type=self.earlier_passage_type,
            later_passage_type=self.later_passage_type,
        )


def _variant_row_inputs(rows: list[_RowContext], excluded_ids: frozenset[uuid.UUID]) -> list[AlignmentRowInput]:
    """A row is dropped from a variant's population if *either* side is a
    passage excluded by that variant -- mirrors `feature_metrics.is_row_
    eligible`'s own "every side must clear the rule" convention, so
    structured-leak exclusion is applied with the same row-level philosophy
    as the existing low-information exclusion, not a different one."""
    kept = [
        r
        for r in rows
        if (r.earlier_passage_id is None or r.earlier_passage_id not in excluded_ids)
        and (r.later_passage_id is None or r.later_passage_id not in excluded_ids)
    ]
    return [r.to_alignment_row_input() for r in kept]


@dataclass(frozen=True)
class VariantMetrics:
    disclosure_change_score: float | None
    new_rate_words: float | None
    removed_rate_words: float | None
    substantially_modified_rate_words: float | None
    ambiguous_rate_words: float | None
    alignment_coverage_words: float | None
    alignment_coverage_count: float | None
    eligible_aligned_passage_count: int
    quality: str
    primary_eligible: bool
    words_considered: float


def _compute_variant_metrics(
    row_inputs: list[AlignmentRowInput],
    *,
    earlier_total_count: int,
    later_total_count: int,
    earlier_total_words: int,
    later_total_words: int,
    embedded_coverage_earlier: float | None,
    embedded_coverage_later: float | None,
    alignment_run_status,
    alignment_review_reason: str | None,
    document_quality,
    is_transition: bool,
    irregular_gap: bool,
    config: FeatureConfig,
) -> VariantMetrics:
    eligible = aggregate_outcomes(row_inputs, eligible_only=True, config=config)
    word_rate_map = word_rates(eligible)
    coverage = compute_alignment_coverage(
        row_inputs,
        earlier_total_count=earlier_total_count,
        later_total_count=later_total_count,
        earlier_total_words=earlier_total_words,
        later_total_words=later_total_words,
    )
    confidence_counts = {c: 0 for c in AlignmentConfidence}
    for r in row_inputs:
        confidence_counts[r.confidence] += 1
    total_rows = len(row_inputs)
    review_required_share = safe_ratio(
        confidence_counts[AlignmentConfidence.LOW] + confidence_counts[AlignmentConfidence.NEEDS_REVIEW], total_rows
    )

    score_components = compute_score_components(word_rate_map, config)
    disclosure_change_score = score_components.total
    coverage_sufficient = (
        coverage.coverage_words is not None
        and coverage.coverage_words >= config.minimum_alignment_coverage
        and embedded_coverage_earlier is not None
        and embedded_coverage_earlier >= config.minimum_embedding_coverage
        and embedded_coverage_later is not None
        and embedded_coverage_later >= config.minimum_embedding_coverage
    )
    if not coverage_sufficient:
        disclosure_change_score = None

    quality_inputs = QualityInputs(
        alignment_run_status=alignment_run_status,
        alignment_review_reason=alignment_review_reason,
        document_quality=document_quality,
        is_transition=is_transition,
        irregular_gap=irregular_gap,
        alignment_coverage_count=coverage.coverage_count,
        alignment_coverage_words=coverage.coverage_words,
        embedded_coverage_earlier=embedded_coverage_earlier,
        embedded_coverage_later=embedded_coverage_later,
        ambiguous_word_share=word_rate_map.get(AlignmentStatus.AMBIGUOUS),
        low_confidence_share=review_required_share,
        disclosure_change_score=disclosure_change_score,
    )
    assessment = assess_feature_quality(quality_inputs, config)

    return VariantMetrics(
        disclosure_change_score=disclosure_change_score,
        new_rate_words=word_rate_map.get(AlignmentStatus.NEW),
        removed_rate_words=word_rate_map.get(AlignmentStatus.REMOVED),
        substantially_modified_rate_words=word_rate_map.get(AlignmentStatus.SUBSTANTIALLY_MODIFIED),
        ambiguous_rate_words=word_rate_map.get(AlignmentStatus.AMBIGUOUS),
        alignment_coverage_words=coverage.coverage_words,
        alignment_coverage_count=coverage.coverage_count,
        eligible_aligned_passage_count=sum(eligible.counts.values()),
        quality=assessment.quality.value,
        primary_eligible=assessment.primary_eligible,
        words_considered=sum(eligible.words.values()),
    )


@dataclass
class FeatureSensitivityRow:
    ticker: str
    report_pair_id: str
    earlier_period_end: str | None
    later_period_end: str | None
    score_a: float | None
    score_b: float | None
    score_c: float | None
    delta_ab: float | None
    delta_ac: float | None
    new_rate_words_a: float | None
    new_rate_words_b: float | None
    new_rate_words_c: float | None
    removed_rate_words_a: float | None
    removed_rate_words_b: float | None
    removed_rate_words_c: float | None
    substantially_modified_rate_words_a: float | None
    substantially_modified_rate_words_b: float | None
    substantially_modified_rate_words_c: float | None
    ambiguous_rate_words_a: float | None
    ambiguous_rate_words_b: float | None
    ambiguous_rate_words_c: float | None
    alignment_coverage_words_a: float | None
    alignment_coverage_words_b: float | None
    alignment_coverage_words_c: float | None
    feature_quality_a: str
    feature_quality_b: str
    feature_quality_c: str
    primary_eligible_a: bool
    primary_eligible_b: bool
    primary_eligible_c: bool
    quality_changed_b: bool
    quality_changed_c: bool
    primary_eligibility_changed_b: bool
    primary_eligibility_changed_c: bool
    words_excluded_b: float
    words_excluded_c: float
    pct_eligible_words_removed_b: float | None
    pct_eligible_words_removed_c: float | None
    coverage_threshold_failed_b: bool
    coverage_threshold_failed_c: bool
    stored_disclosure_change_score: float | None


def build_feature_sensitivity_rows(
    session: Session,
    passages_by_id: dict[uuid.UUID, Passage],
    classifications_by_id: dict[uuid.UUID, Classification],
    config: FeatureConfig = FEATURE_CONFIG,
) -> list[FeatureSensitivityRow]:
    pairs = session.scalars(
        select(ReportPair)
        .options(joinedload(ReportPair.company), joinedload(ReportPair.earlier_report), joinedload(ReportPair.later_report))
        .join(Company, ReportPair.company_id == Company.id)
        .order_by(Company.ticker, ReportPair.gap_months)
    ).all()
    pair_ids = [p.id for p in pairs]
    current_alignment_runs = get_current_alignment_runs_by_pair(session, pair_ids)
    doc_similarities = get_current_document_similarities_by_pair(session, pair_ids)
    stored_features = get_current_report_pair_features_by_pair(session, pair_ids)

    out: list[FeatureSensitivityRow] = []
    for pair in pairs:
        alignment_run = current_alignment_runs.get(pair.id)
        stored = stored_features.get(pair.id)
        if alignment_run is None:
            continue

        earlier_passages = [p for p in passages_by_id.values() if p.segmentation_run_id == alignment_run.earlier_segmentation_run_id]
        later_passages = [p for p in passages_by_id.values() if p.segmentation_run_id == alignment_run.later_segmentation_run_id]
        earlier_total_count = len(earlier_passages)
        later_total_count = len(later_passages)
        earlier_total_words = sum(p.word_count for p in earlier_passages)
        later_total_words = sum(p.word_count for p in later_passages)

        alignment_rows = session.scalars(
            select(PassageAlignment).where(
                PassageAlignment.alignment_run_id == alignment_run.id,
                PassageAlignment.primary_alignment.is_(True),
            )
        ).all()

        row_contexts: list[_RowContext] = []
        for r in alignment_rows:
            earlier_p = passages_by_id.get(r.earlier_passage_id) if r.earlier_passage_id else None
            later_p = passages_by_id.get(r.later_passage_id) if r.later_passage_id else None
            row_contexts.append(
                _RowContext(
                    alignment_status=r.alignment_status,
                    confidence=r.confidence,
                    earlier_passage_id=r.earlier_passage_id,
                    later_passage_id=r.later_passage_id,
                    earlier_word_count=earlier_p.word_count if earlier_p else None,
                    later_word_count=later_p.word_count if later_p else None,
                    earlier_passage_type=earlier_p.passage_type if earlier_p else None,
                    later_passage_type=later_p.passage_type if later_p else None,
                )
            )

        excluded_b: set[uuid.UUID] = set()
        excluded_c: set[uuid.UUID] = set()
        for passage in earlier_passages + later_passages:
            classification = classifications_by_id.get(passage.id)
            category = classification.category if classification else None
            is_two_char = classification.is_two_char_heading if classification else False
            if excluded_in_variant_b(category, is_two_char):
                excluded_b.add(passage.id)
            if excluded_in_variant_c(category, is_two_char):
                excluded_c.add(passage.id)

        embedded_coverage_earlier = stored.embedded_coverage_earlier if stored else None
        embedded_coverage_later = stored.embedded_coverage_later if stored else None
        irregular_gap = not (config.primary_gap_months_min <= pair.gap_months <= config.primary_gap_months_max)
        doc_sim = doc_similarities.get(pair.id)
        document_quality = doc_sim.quality_status if doc_sim else None

        common_kwargs = dict(
            earlier_total_count=earlier_total_count,
            later_total_count=later_total_count,
            earlier_total_words=earlier_total_words,
            later_total_words=later_total_words,
            embedded_coverage_earlier=embedded_coverage_earlier,
            embedded_coverage_later=embedded_coverage_later,
            alignment_run_status=alignment_run.status,
            alignment_review_reason=alignment_run.review_reason,
            document_quality=document_quality,
            is_transition=pair.is_transition,
            irregular_gap=irregular_gap,
            config=config,
        )

        metrics_a = _compute_variant_metrics(
            _variant_row_inputs(row_contexts, frozenset()), **common_kwargs
        )
        metrics_b = _compute_variant_metrics(
            _variant_row_inputs(row_contexts, frozenset(excluded_b)), **common_kwargs
        )
        metrics_c = _compute_variant_metrics(
            _variant_row_inputs(row_contexts, frozenset(excluded_c)), **common_kwargs
        )

        words_excluded_b = metrics_a.words_considered - metrics_b.words_considered
        words_excluded_c = metrics_a.words_considered - metrics_c.words_considered

        out.append(
            FeatureSensitivityRow(
                ticker=pair.company.ticker,
                report_pair_id=str(pair.id),
                earlier_period_end=pair.earlier_report.period_end.isoformat() if pair.earlier_report.period_end else None,
                later_period_end=pair.later_report.period_end.isoformat() if pair.later_report.period_end else None,
                score_a=metrics_a.disclosure_change_score,
                score_b=metrics_b.disclosure_change_score,
                score_c=metrics_c.disclosure_change_score,
                delta_ab=(
                    metrics_b.disclosure_change_score - metrics_a.disclosure_change_score
                    if metrics_a.disclosure_change_score is not None and metrics_b.disclosure_change_score is not None
                    else None
                ),
                delta_ac=(
                    metrics_c.disclosure_change_score - metrics_a.disclosure_change_score
                    if metrics_a.disclosure_change_score is not None and metrics_c.disclosure_change_score is not None
                    else None
                ),
                new_rate_words_a=metrics_a.new_rate_words,
                new_rate_words_b=metrics_b.new_rate_words,
                new_rate_words_c=metrics_c.new_rate_words,
                removed_rate_words_a=metrics_a.removed_rate_words,
                removed_rate_words_b=metrics_b.removed_rate_words,
                removed_rate_words_c=metrics_c.removed_rate_words,
                substantially_modified_rate_words_a=metrics_a.substantially_modified_rate_words,
                substantially_modified_rate_words_b=metrics_b.substantially_modified_rate_words,
                substantially_modified_rate_words_c=metrics_c.substantially_modified_rate_words,
                ambiguous_rate_words_a=metrics_a.ambiguous_rate_words,
                ambiguous_rate_words_b=metrics_b.ambiguous_rate_words,
                ambiguous_rate_words_c=metrics_c.ambiguous_rate_words,
                alignment_coverage_words_a=metrics_a.alignment_coverage_words,
                alignment_coverage_words_b=metrics_b.alignment_coverage_words,
                alignment_coverage_words_c=metrics_c.alignment_coverage_words,
                feature_quality_a=metrics_a.quality,
                feature_quality_b=metrics_b.quality,
                feature_quality_c=metrics_c.quality,
                primary_eligible_a=metrics_a.primary_eligible,
                primary_eligible_b=metrics_b.primary_eligible,
                primary_eligible_c=metrics_c.primary_eligible,
                quality_changed_b=metrics_a.quality != metrics_b.quality,
                quality_changed_c=metrics_a.quality != metrics_c.quality,
                primary_eligibility_changed_b=metrics_a.primary_eligible != metrics_b.primary_eligible,
                primary_eligibility_changed_c=metrics_a.primary_eligible != metrics_c.primary_eligible,
                words_excluded_b=words_excluded_b,
                words_excluded_c=words_excluded_c,
                pct_eligible_words_removed_b=safe_ratio(words_excluded_b, metrics_a.words_considered),
                pct_eligible_words_removed_c=safe_ratio(words_excluded_c, metrics_a.words_considered),
                coverage_threshold_failed_b=(
                    metrics_b.alignment_coverage_words is not None
                    and metrics_b.alignment_coverage_words < config.minimum_alignment_coverage
                ),
                coverage_threshold_failed_c=(
                    metrics_c.alignment_coverage_words is not None
                    and metrics_c.alignment_coverage_words < config.minimum_alignment_coverage
                ),
                stored_disclosure_change_score=stored.disclosure_change_score if stored else None,
            )
        )
    return out


def write_feature_sensitivity_csv(rows: list[FeatureSensitivityRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(FeatureSensitivityRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# deterministic_structured_leak_review_sample.csv
# --------------------------------------------------------------------------


@dataclass
class ReviewSampleRow:
    sample_reason: str
    ticker: str
    report_id: str
    directory_year: int
    passage_id: str
    passage_index: int
    heading_text: str | None
    word_count: int
    passage_type: str
    category: str
    suggested_action: str | None
    alignment_status: str | None
    confidence: str | None
    text_excerpt: str


def build_deterministic_review_sample(
    session: Session,
    rows: list[PassageAuditRow],
    passages_by_id: dict[uuid.UUID, Passage],
    *,
    per_bucket_limit: int = 3,
) -> list[ReviewSampleRow]:
    """A fixed, reproducible sample -- deterministic sort keys only, no
    randomness -- covering every audit category, both two-character-heading
    populations, and (where available) every alignment status, so a human
    reviewer sees representative examples rather than an arbitrary head()."""
    passage_ids = [uuid.UUID(r.passage_id) for r in rows]
    alignment_by_passage: dict[uuid.UUID, PassageAlignment] = {}
    if passage_ids:
        alignment_rows = session.scalars(
            select(PassageAlignment).where(
                (PassageAlignment.earlier_passage_id.in_(passage_ids)) | (PassageAlignment.later_passage_id.in_(passage_ids))
            )
        ).all()
        for a in alignment_rows:
            if a.earlier_passage_id is not None:
                alignment_by_passage.setdefault(a.earlier_passage_id, a)
            if a.later_passage_id is not None:
                alignment_by_passage.setdefault(a.later_passage_id, a)

    def _alignment_for(row: PassageAuditRow) -> PassageAlignment | None:
        return alignment_by_passage.get(uuid.UUID(row.passage_id))

    buckets: dict[str, list[PassageAuditRow]] = defaultdict(list)
    for row in rows:
        bucket = f"category:{row.category}"
        buckets[bucket].append(row)
        if row.is_two_char_heading:
            buckets["two_char:word_count_1" if row.word_count == 1 else "two_char:body_bearing"].append(row)

    for status in AlignmentStatus:
        matching = [r for r in rows if (a := _alignment_for(r)) is not None and a.alignment_status == status]
        if matching:
            buckets[f"alignment_status:{status.value}"] = matching

    out: list[ReviewSampleRow] = []
    seen_passage_ids: set[str] = set()
    for bucket_name in sorted(buckets):
        bucket_rows = sorted(buckets[bucket_name], key=lambda r: (r.ticker, r.directory_year, r.passage_index))
        # Deterministic spread: lowest, middle, and highest word_count in
        # the bucket (falls back to however many are available) rather than
        # always the same first N rows.
        by_words = sorted(bucket_rows, key=lambda r: (r.word_count, r.ticker, r.passage_index))
        picks: list[PassageAuditRow] = []
        if by_words:
            picks.append(by_words[0])
        if len(by_words) > 2:
            picks.append(by_words[len(by_words) // 2])
        if len(by_words) > 1:
            picks.append(by_words[-1])
        for row in picks[:per_bucket_limit]:
            key = f"{bucket_name}:{row.passage_id}"
            if key in seen_passage_ids:
                continue
            seen_passage_ids.add(key)
            alignment = _alignment_for(row)
            out.append(
                ReviewSampleRow(
                    sample_reason=bucket_name,
                    ticker=row.ticker,
                    report_id=row.report_id,
                    directory_year=row.directory_year,
                    passage_id=row.passage_id,
                    passage_index=row.passage_index,
                    heading_text=row.heading_text,
                    word_count=row.word_count,
                    passage_type=row.passage_type,
                    category=row.category,
                    suggested_action=row.suggested_action,
                    alignment_status=alignment.alignment_status.value if alignment else None,
                    confidence=alignment.confidence.value if alignment else None,
                    text_excerpt=row.text_excerpt,
                )
            )
    out.sort(key=lambda r: (r.sample_reason, r.ticker, r.directory_year, r.passage_index))
    return out


def write_review_sample_csv(rows: list[ReviewSampleRow], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [f.name for f in fields(ReviewSampleRow)]
    with output_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(vars(row))


# --------------------------------------------------------------------------
# Orchestration: run everything, write all five CSVs
# --------------------------------------------------------------------------


@dataclass
class StructuredContentAuditResult:
    passage_rows: list[PassageAuditRow]
    company_summary_rows: list[CompanySummaryRow]
    two_char_heading_rows: list[TwoCharHeadingRow]
    feature_sensitivity_rows: list[FeatureSensitivityRow]
    review_sample_rows: list[ReviewSampleRow]


def run_structured_content_audit(session: Session, config: FeatureConfig = FEATURE_CONFIG) -> StructuredContentAuditResult:
    passage_rows, contexts, passages_by_id, classifications_by_id = build_passage_audit_rows(session, config)
    company_summary_rows = build_company_summary_rows(passage_rows, contexts, passages_by_id)
    two_char_heading_rows = build_two_char_heading_rows(contexts, passages_by_id, classifications_by_id)
    feature_sensitivity_rows = build_feature_sensitivity_rows(session, passages_by_id, classifications_by_id, config)
    review_sample_rows = build_deterministic_review_sample(session, passage_rows, passages_by_id)
    return StructuredContentAuditResult(
        passage_rows=passage_rows,
        company_summary_rows=company_summary_rows,
        two_char_heading_rows=two_char_heading_rows,
        feature_sensitivity_rows=feature_sensitivity_rows,
        review_sample_rows=review_sample_rows,
    )


def write_all_csvs(result: StructuredContentAuditResult, output_dir: Path) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "structured_leak_passages": output_dir / "structured_leak_passages.csv",
        "structured_leak_summary_by_company": output_dir / "structured_leak_summary_by_company.csv",
        "two_character_heading_review": output_dir / "two_character_heading_review.csv",
        "feature_sensitivity_structured_leak": output_dir / "feature_sensitivity_structured_leak.csv",
        "deterministic_structured_leak_review_sample": output_dir / "deterministic_structured_leak_review_sample.csv",
    }
    write_passage_audit_csv(result.passage_rows, paths["structured_leak_passages"])
    write_company_summary_csv(result.company_summary_rows, paths["structured_leak_summary_by_company"])
    write_two_char_heading_csv(result.two_char_heading_rows, paths["two_character_heading_review"])
    write_feature_sensitivity_csv(result.feature_sensitivity_rows, paths["feature_sensitivity_structured_leak"])
    write_review_sample_csv(result.review_sample_rows, paths["deterministic_structured_leak_review_sample"])
    return paths

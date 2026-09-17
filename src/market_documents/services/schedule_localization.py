"""Schedule localization: deterministic heading-vocabulary algorithm and run
orchestration.

Track 7C.1 (docs/7c1-schedule-localization-plan.md). Mirrors
`services/passage_segmentation.py`'s split between a pure, DB-free
algorithm (`localize_schedule`) and orchestration functions that touch the
`Session` at the bottom. Reads only `Page`/`TextBlock` -- the same source
data `passage_segmentation.py` reads -- and never touches `Passage` or any
other passage-pipeline table, keeping this track independent of the
existing passage pipeline (see the plan's Section 1).

Only `NormalizedSchedule.FINANCIAL_PERFORMANCE` is implemented.
`localize_schedule` raises `NotImplementedError` for any other schedule --
a real, visible failure, not a silent skip -- enforcing the milestone's
scope boundary in code, not just in the plan document.

Track 7C.1b (docs/7c1b-canonical-hierarchy-integration.md) adds
hierarchy-aware boundary termination: a later heading-candidate only ends a
span if `heading_structure.assess_heading_structure` finds it plausibly
top-level (see `_end_page_for`), and prefers the Track 7C.1a canonical
source (via `source_adapter`) over legacy `TextBlock` when a report has a
current successful `CanonicalExtractionRun`, since only canonical data
carries the per-span font/geometry evidence that assessment needs.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from market_documents.models.enums import (
    BlockType,
    BoundaryConfidence,
    ExtractionQuality,
    NormalizedSchedule,
    ScheduleLocalizationRunStatus,
    ScheduleLocalizationStatus,
)
from market_documents.models.extraction import ExtractionRun, Page, TextBlock
from market_documents.models.report import Report
from market_documents.models.schedule import ScheduleInstance, ScheduleInstanceSupportingSpan, ScheduleLocalizationRun
from market_documents.services import source_adapter
from market_documents.services.canonical_extraction import get_current_canonical_run
from market_documents.services.extraction import get_current_extraction_run
from market_documents.services.heading_structure import assess_heading_structure
from market_documents.services.schedule_config import SCHEDULE_CONFIG, ALGORITHM_VERSION, ScheduleConfig, compute_configuration_hash

logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------
# Pure data structures
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class HeadingBlock:
    """A minimal, ORM-free view of one HEADING_CANDIDATE TextBlock.

    `font_size`/`is_bold`/`block_width_ratio` are optional structural
    evidence (Track 7C.1b) -- `None` when the source data doesn't carry it
    (e.g. legacy TextBlock rows with no recorded font, or a report with no
    canonical extraction), in which case `heading_structure` defaults to
    the pre-7C.1b behavior instead of guessing.
    """

    id: uuid.UUID
    page_number: int
    reading_order: int
    text: str
    font_size: float | None = None
    is_bold: bool | None = None
    block_width_ratio: float | None = None


@dataclass(frozen=True)
class SpanResult:
    heading_text: str
    start_page: int
    end_page: int
    exact_match: bool


@dataclass(frozen=True)
class ScheduleLocalizationResult:
    schedule: NormalizedSchedule
    status: ScheduleLocalizationStatus
    primary: SpanResult | None
    supporting: tuple[SpanResult, ...]
    boundary_confidence: BoundaryConfidence | None
    confidence_score: float | None
    reasoning_summary: str


_QUOTE_TRANSLATION = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"'})

# A later heading-candidate's own font size must be at least this fraction
# of the schedule's own matched heading's font size to end the span (Track
# 7D.1). Real-corpus verification (docs/7d1-known-recall-defect-remediation.md)
# showed BEL's and ACT's full heading-candidate font-size populations are
# dense, near-continuous spectrums -- `heading_structure`'s whole-document
# clustering collapses almost the entire top of the range into one cluster
# regardless of its own gap-ratio setting, so it cannot reliably separate a
# genuine next top-level section from an internal subsection heading in
# these documents. Comparing a candidate directly to *this specific span's*
# own matched heading is a narrower, per-span use of the same
# relative-font-size evidence. 0.78 is calibrated against two real,
# confirmed cases: BEL 2017's "Gross margin"/"Revenue analysis" subsection
# headings (18pt under a 24pt "Finance Director's Report" heading, ratio
# 0.75 -- must be excluded) and ACT 2019's genuine next section, "Results AT
# A GLANCE" (45.08pt under a 57.58pt "Group CFO's Report" heading, ratio
# 0.783 -- must be included).
_END_BOUNDARY_FONT_RATIO = 0.78


def _normalize_heading(text: str) -> str:
    return " ".join(text.strip().split()).lower().translate(_QUOTE_TRANSLATION)


def _matches_vocabulary(heading_text: str, vocabulary: tuple[str, ...]) -> tuple[bool, bool]:
    """Returns (matched, exact) -- `exact` means the normalized heading text
    equals a vocabulary entry exactly (not merely contains it), which is
    treated as a stronger signal than a substring match.

    A heading also matches if every word of a vocabulary phrase appears
    within a small window of consecutive heading words, in any order -- real
    PDF text extraction sometimes reorders a heading's words relative to
    their visual layout, occasionally with one stray intervening word (e.g.
    real ACT 2019 corpus text extracts as "REPORT Group CFO's" for what
    reads as "Group CFO's Report" on the page), which a pure substring check
    never generalizes to no matter how the vocabulary is worded. The window
    is deliberately tight -- vocabulary word count plus one -- so this
    catches a genuine local reordering/insertion artifact without also
    matching an unrelated heading that merely happens to contain the same
    words scattered far apart (real BEL corpus false-positive risk: "FINANCIAL
    STATEMENTS AND EXTERNAL REVIEW" contains both "financial" and "review"
    but is an unrelated section, three words apart). Word-order tolerance is
    deliberately weaker evidence
    than a substring match (never `exact`), since the caller
    (`localize_schedule`) also weighs each match's structural top-level
    evidence before picking a primary span -- see its module docstring."""
    normalized = _normalize_heading(heading_text)
    heading_word_list = normalized.split()
    for candidate in vocabulary:
        normalized_candidate = _normalize_heading(candidate)
        if normalized == normalized_candidate:
            return True, True
        if normalized_candidate in normalized:
            return True, False
        candidate_words = set(normalized_candidate.split())
        window_size = len(candidate_words) + 1
        if len(candidate_words) >= 2 and any(
            candidate_words <= set(heading_word_list[i : i + window_size])
            for i in range(len(heading_word_list))
        ):
            return True, False
    return False, False


def localize_schedule(
    headings: list[HeadingBlock],
    last_page_number: int,
    schedule: NormalizedSchedule,
    config: ScheduleConfig = SCHEDULE_CONFIG,
) -> ScheduleLocalizationResult:
    """Deterministically localize one normalized schedule from a report's
    ordered HEADING_CANDIDATE blocks.

    Algorithm:
    1. Find every heading-candidate block whose text matches the schedule's
       configured vocabulary (case-insensitive, whitespace-normalized;
       exact full-text match is a stronger signal than a substring match).
    2. If none match: NOT_FOUND.
    3. If one or more match: the first (by page/reading-order) is primary;
       any further matches are supporting spans (FOUND_PRIMARY_AND_SUPPORTING).
       A span's end boundary is the page before the next heading-candidate
       block in the document (of any kind, not just vocabulary matches),
       or the report's last page if it is the final heading.

    Only FINANCIAL_PERFORMANCE is implemented -- raises NotImplementedError
    for any other schedule (see module docstring).
    """
    if schedule != NormalizedSchedule.FINANCIAL_PERFORMANCE:
        raise NotImplementedError(
            f"schedule_localization.localize_schedule: {schedule.value} is not implemented in "
            "Track 7C.1 -- only FINANCIAL_PERFORMANCE is supported. See "
            "docs/7c1-schedule-localization-plan.md Section 2 (explicit scope boundary)."
        )

    vocabulary = config.heading_vocabulary.get(schedule, ())
    ordered = sorted(headings, key=lambda h: (h.page_number, h.reading_order))

    # Track 7C.1b: every heading-candidate whose text matches the schedule's
    # vocabulary, *before* any table-of-contents filtering -- used only to
    # anchor the structural assessment below (a real section heading's own
    # font size identifies which document-relative font-size tier counts as
    # "top-level"). A stray table-of-contents row matching the same
    # vocabulary substring is normally smaller-font than the real heading,
    # so including it here is harmless: iterating tiers largest-first below
    # finds the real heading's tier first regardless.
    raw_matches: list[tuple[HeadingBlock, bool]] = []
    for heading in ordered:
        matched, exact = _matches_vocabulary(heading.text, vocabulary)
        if matched:
            raw_matches.append((heading, exact))

    if not raw_matches:
        return ScheduleLocalizationResult(
            schedule=schedule,
            status=ScheduleLocalizationStatus.NOT_FOUND,
            primary=None,
            supporting=(),
            boundary_confidence=None,
            confidence_score=None,
            reasoning_summary=(
                f"No heading-candidate block matched the {schedule.value} vocabulary "
                f"({len(vocabulary)} configured heading(s))."
            ),
        )

    anchor_font_sizes = tuple(h.font_size for h, _ in raw_matches if h.font_size is not None)

    # Document-relative structural assessment (font-size tiering anchored to
    # the schedule's own matched heading(s), table-of-contents pattern,
    # paired/grouped labels) of every heading-candidate in the document,
    # used below both to keep a table-of-contents entry from being matched
    # as the schedule's own heading and to keep an internal subsection
    # heading or chart title from ending the span just because it is *a*
    # heading-candidate.
    structural = assess_heading_structure(ordered, anchor_font_sizes=anchor_font_sizes)

    # Recurring running-section banners (e.g. BEL's "PERFORMANCE REVIEW",
    # printed at the top of every page in a whole report part) are
    # classified as HEADING_CANDIDATE by the upstream extraction pipeline
    # just like genuine section headings -- that pipeline is frozen/
    # read-only for this track (see module docstring), so this heuristic
    # compensates locally rather than touching it. A heading whose
    # normalized text recurs 3+ times anywhere in the document's
    # heading-candidates is treated as boilerplate, not a section boundary,
    # when computing a span's end page -- real section-boundary headings in
    # this corpus (e.g. "Corporate governance report") appear once.
    _BOILERPLATE_REPEAT_THRESHOLD = 3
    heading_frequency: dict[str, int] = {}
    for heading in ordered:
        key = _normalize_heading(heading.text)
        heading_frequency[key] = heading_frequency.get(key, 0) + 1
    boundary_candidates = [
        h for h in ordered
        if heading_frequency[_normalize_heading(h.text)] < _BOILERPLATE_REPEAT_THRESHOLD
        and not structural[h.id].is_toc_entry
    ]

    # A table-of-contents listing entry (e.g. "Financial review....42") is
    # itself classified HEADING_CANDIDATE and can match the schedule's
    # vocabulary just like the real section heading does -- excluded here so
    # it is never picked up as the primary/supporting match.
    matches = [(h, exact) for h, exact in raw_matches if not structural[h.id].is_toc_entry]

    if not matches:
        return ScheduleLocalizationResult(
            schedule=schedule,
            status=ScheduleLocalizationStatus.NOT_FOUND,
            primary=None,
            supporting=(),
            boundary_confidence=None,
            confidence_score=None,
            reasoning_summary=(
                f"Every heading-candidate block matching the {schedule.value} vocabulary "
                f"({len(vocabulary)} configured heading(s)) was a table-of-contents entry, not a real heading."
            ),
        )

    def _end_page_for(heading: HeadingBlock) -> int:
        # Only a heading-candidate on a *later* page can end this span -- a
        # candidate later in reading order but still on the same page (e.g.
        # a "salient features" sidebar's short numeric callouts, observed on
        # real BEL pages classified as HEADING_CANDIDATE alongside the
        # primary heading) is not a section boundary, and must not truncate
        # a genuinely multi-page schedule down to one page.
        #
        # A "<heading> continued" candidate is this same section resuming on
        # a later page (the schedule-localization research doc's own
        # documented convention -- sections are "bracketed by clear
        # 'continued' labels"), not a new section starting -- it must not
        # end the span either, even though it normalizes to a distinct,
        # non-boilerplate string.
        #
        # Track 7C.1b: a boundary candidate only ends the span if it also
        # qualifies as a top-level structural heading -- an internal
        # subsection heading (e.g. ACT's "Depreciation/amortisation") or a
        # chart title (e.g. BEL's "2019 External Revenue Analysis -
        # Geographic") is a HEADING_CANDIDATE like any other, but is not a
        # document-hierarchy section boundary, and must not truncate its
        # parent schedule.
        #
        # Track 7D.1: `is_top_level` alone isn't a reliable enough filter on
        # its own -- real BEL/ACT heading-candidate font-size populations
        # are dense spectrums that `heading_structure`'s whole-document
        # clustering can merge into one broad top cluster, spanning both the
        # schedule's own heading tier and a materially smaller subsection
        # tier beneath it (real BEL 2017 case: 24pt "Finance Director's
        # Report" and its own 18pt "Revenue analysis"/"Gross margin"
        # subsections). Additionally requiring a candidate's own font size
        # to be reasonably close to *this specific schedule heading's* font
        # size -- a per-span comparison, not the whole document's tiering --
        # is a second, independent use of the same relative-font-size
        # evidence (see `_END_BOUNDARY_FONT_RATIO`).
        heading_norm = _normalize_heading(heading.text)
        later = [
            h for h in boundary_candidates
            if h.page_number > heading.page_number
            and _normalize_heading(h.text) != f"{heading_norm} continued"
            and structural[h.id].is_top_level
            and (
                heading.font_size is None
                or h.font_size is None
                or h.font_size >= heading.font_size * _END_BOUNDARY_FONT_RATIO
            )
        ]
        if not later:
            return last_page_number
        next_page = later[0].page_number
        return max(heading.page_number, next_page - 1)

    # Track 7D.1: the primary span is the best-evidenced match, not simply
    # whichever match happens to occur on the earliest page -- a real
    # section's own genuine heading can sit *after* an unrelated,
    # coincidental substring/word-set match earlier in the document (real
    # ACT 2019 corpus case: "Consistent financial performance", an ordinary
    # sentence fragment on an early overview page, substring-matches the
    # FINANCIAL_PERFORMANCE vocabulary at 11pt and precedes the real, much
    # larger "CFO's Report" heading (57.58pt) by dozens of pages). Ranked by:
    # an exact vocabulary match first; then structural top-level assessment
    # (Track 7C.1b's document-relative font-size tiering); then, as a
    # tie-break among matches that land in the same tier, the match's own
    # font size descending; then page order as the final tie-break.
    ranked_matches = sorted(
        matches,
        key=lambda pair: (
            0 if pair[1] else 1,
            0 if structural[pair[0].id].is_top_level else 1,
            -(pair[0].font_size if pair[0].font_size is not None else float("-inf")),
            pair[0].page_number,
            pair[0].reading_order,
        ),
    )

    spans = [
        SpanResult(
            heading_text=heading.text.strip(),
            start_page=heading.page_number,
            end_page=_end_page_for(heading),
            exact_match=exact,
        )
        for heading, exact in ranked_matches
    ]

    primary = spans[0]
    supporting = tuple(spans[1:])
    status = (
        ScheduleLocalizationStatus.FOUND_PRIMARY_AND_SUPPORTING
        if supporting
        else ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    )
    boundary_confidence = BoundaryConfidence.HIGH if primary.exact_match else BoundaryConfidence.MEDIUM
    confidence_score = 0.85 if primary.exact_match else 0.6

    return ScheduleLocalizationResult(
        schedule=schedule,
        status=status,
        primary=primary,
        supporting=supporting,
        boundary_confidence=boundary_confidence,
        confidence_score=confidence_score,
        reasoning_summary=(
            f"Matched heading '{primary.heading_text}' "
            f"({'exact' if primary.exact_match else 'substring'} match) as primary "
            f"span pp.{primary.start_page}-{primary.end_page}"
            + (f"; {len(supporting)} supporting span(s) also matched." if supporting else ".")
        ),
    )


# --------------------------------------------------------------------------
# Orchestration
# --------------------------------------------------------------------------


def get_current_localization_run(
    session: Session, report_id: uuid.UUID, schedule: NormalizedSchedule
) -> ScheduleLocalizationRun | None:
    """The current successful localization run for one (report, schedule).

    Defined as the most recently completed run with status COMPLETED or
    COMPLETED_WITH_WARNINGS, exactly like `get_current_extraction_run`.
    """
    return session.scalars(
        select(ScheduleLocalizationRun)
        .where(
            ScheduleLocalizationRun.report_id == report_id,
            ScheduleLocalizationRun.schedule == schedule,
            ScheduleLocalizationRun.status.in_(
                (ScheduleLocalizationRunStatus.COMPLETED, ScheduleLocalizationRunStatus.COMPLETED_WITH_WARNINGS)
            ),
        )
        .order_by(ScheduleLocalizationRun.completed_at.desc())
        .limit(1)
    ).first()


@dataclass
class LocalizationOutcome:
    report_id: uuid.UUID
    run: ScheduleLocalizationRun | None
    skipped: bool = False
    skip_reason: str | None = None
    ineligible: bool = False
    ineligible_reason: str | None = None


def run_localization(
    session: Session, report: Report, schedule: NormalizedSchedule, *, force: bool = False
) -> LocalizationOutcome:
    """Localize one normalized schedule for one report's current successful extraction.

    Eligibility requires a current successful ExtractionRun whose quality is
    not FAILED. Skips (returning the existing run) if the current
    successful localization already used an identical source ExtractionRun
    and an identical configuration fingerprint, and `force` was not set.
    """
    extraction_run = get_current_extraction_run(session, report.id)
    if extraction_run is None:
        return LocalizationOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason="report has no current successful extraction",
        )
    if extraction_run.extraction_quality == ExtractionQuality.FAILED:
        return LocalizationOutcome(
            report_id=report.id, run=None, ineligible=True,
            ineligible_reason="extraction quality is FAILED",
        )

    configuration_hash = compute_configuration_hash()

    current_run = get_current_localization_run(session, report.id, schedule)
    if (
        current_run is not None
        and not force
        and current_run.configuration_hash == configuration_hash
        and current_run.extraction_run_id == extraction_run.id
    ):
        return LocalizationOutcome(
            report_id=report.id, run=current_run, skipped=True,
            skip_reason="identical successful localization run already exists",
        )

    run = ScheduleLocalizationRun(
        report_id=report.id,
        extraction_run_id=extraction_run.id,
        schedule=schedule,
        algorithm_version=ALGORITHM_VERSION,
        configuration_hash=configuration_hash,
        status=ScheduleLocalizationRunStatus.RUNNING,
        started_at=datetime.now(UTC),
    )
    session.add(run)
    session.flush()

    try:
        with session.begin_nested():
            _run_localization(session, report, extraction_run, schedule, run)
    except Exception as exc:  # never leave a run silently half-written
        run.status = ScheduleLocalizationRunStatus.FAILED
        run.error_message = f"schedule localization failure: {exc}"
        run.completed_at = datetime.now(UTC)
        logger.exception("schedule localization failed for %s (%s)", report.local_path, schedule.value)

    session.flush()
    return LocalizationOutcome(report_id=report.id, run=run)


def _run_localization(
    session: Session,
    report: Report,
    extraction_run: ExtractionRun,
    schedule: NormalizedSchedule,
    run: ScheduleLocalizationRun,
) -> None:
    pages = session.scalars(select(Page).where(Page.extraction_run_id == extraction_run.id)).all()
    if not pages:
        run.status = ScheduleLocalizationRunStatus.FAILED
        run.error_message = "no source Pages available"
        run.completed_at = datetime.now(UTC)
        return
    last_page_number = max(p.page_number for p in pages)

    # Track 7C.1b: prefer the canonical source (Track 7C.1a) when this
    # report has a current successful CanonicalExtractionRun -- it carries
    # the per-span font/geometry evidence `heading_structure` needs and is
    # source-faithful where legacy TextBlock rows can be lossy (see
    # docs/7c1a-canonical-source-representation.md). Falls back to legacy
    # TextBlock, unchanged, for a report with no canonical extraction yet;
    # TextBlock does carry a flattened per-block font_size/is_bold, so the
    # structural assessment still has *some* evidence in that case, just
    # less precise than canonical spans.
    canonical_run = get_current_canonical_run(session, report.id)
    if canonical_run is not None:
        source_pages = source_adapter.load_source_pages(session, canonical_run.id)
        classified = source_adapter.classify_source_pages(source_pages)
        headings = source_adapter.build_heading_blocks(classified)
        if source_pages:
            last_page_number = max(p.page_number for p in source_pages)
    else:
        text_blocks = session.scalars(
            select(TextBlock).where(
                TextBlock.extraction_run_id == extraction_run.id,
                TextBlock.block_type == BlockType.HEADING_CANDIDATE,
                TextBlock.excluded_from_narrative.is_(False),
            )
        ).all()

        headings = [
            HeadingBlock(
                id=b.id, page_number=next(p.page_number for p in pages if p.id == b.page_id),
                reading_order=b.reading_order, text=b.cleaned_text or b.raw_text,
                font_size=b.font_size, is_bold=b.is_bold,
            )
            for b in text_blocks
        ]

    result = localize_schedule(headings, last_page_number, schedule)

    instance = ScheduleInstance(
        schedule_localization_run_id=run.id,
        report_id=report.id,
        schedule=schedule,
        status=result.status,
        heading_text=result.primary.heading_text if result.primary else None,
        start_page=result.primary.start_page if result.primary else None,
        end_page=result.primary.end_page if result.primary else None,
        boundary_confidence=result.boundary_confidence,
        confidence_score=result.confidence_score,
        reasoning_summary=result.reasoning_summary,
    )
    session.add(instance)
    session.flush()

    for span in result.supporting:
        session.add(
            ScheduleInstanceSupportingSpan(
                schedule_instance_id=instance.id,
                heading_text=span.heading_text,
                start_page=span.start_page,
                end_page=span.end_page,
            )
        )

    run.completed_at = datetime.now(UTC)
    run.status = ScheduleLocalizationRunStatus.COMPLETED

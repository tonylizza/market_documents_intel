"""Structural-level assessment for HEADING_CANDIDATE blocks (Track 7C.1b).

`schedule_localization.py`'s boundary algorithm (Track 7C.1) treats every
HEADING_CANDIDATE as an equally valid schedule terminator. Real corpus
evidence (docs/7c1a-canonical-source-representation.md Section 9, ACT 2021)
shows this is wrong: a report's document hierarchy is Document -> Schedule
-> Semantic units/subsections, and an internal subsection heading (e.g.
"Depreciation/amortisation", ~11-14pt) must not terminate its parent
schedule just because it was classified as a heading-candidate the same way
a genuine top-level section heading (e.g. "CFO'S REVIEW", ~62-65pt) was.

This module answers one narrow question -- "is this heading-candidate
plausibly a top-level structural section heading in *this* document?" --
using signals relative to the document's own other heading-candidates, never
an absolute point-size threshold (ACT's ~62pt top tier and BEL's ~12-14pt
top tier are both "the top tier" for their own document). Pure and
deterministic: no DB access, no LLM/VLM.
"""

import re
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class StructuralConfidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True)
class HeadingStructuralAssessment:
    heading_id: uuid.UUID
    is_top_level: bool
    confidence: StructuralConfidence
    is_toc_entry: bool
    evidence: tuple[str, ...]


class _HeadingLike(Protocol):
    """Structural shape `assess_heading_structure` needs -- matches
    `schedule_localization.HeadingBlock` without importing it, which would
    create a circular import (that module calls back into this one)."""

    id: uuid.UUID
    page_number: int
    reading_order: int
    text: str
    font_size: float | None
    is_bold: bool | None
    block_width_ratio: float | None


# A gap between two document-relative font-size clusters: the next cluster
# down is a genuinely different tier only if its largest member is under
# this fraction of the current cluster's smallest member. Relative, not an
# absolute point size -- ACT's ~62pt/~12pt split and a hypothetical
# 14pt/10pt split are both "a gap" under this rule if the ratio holds.
#
# Track 7D.1 investigated raising this to separate a real BEL 2017 case
# (18pt subsection headings landing exactly on the old 0.75 ratio against
# their 24pt parent-section heading, so never separating) -- reverted after
# real-corpus verification showed both BEL's and ACT's full heading-candidate
# font-size populations are dense, near-continuous spectrums with no usable
# gap anywhere near the top tier (every real report-year checked collapses
# to one ~30-50-member top cluster under any ratio from 0.75-0.85), so no
# single whole-document ratio can separate the cases that motivated the
# change without merging cases that must stay separate elsewhere in the
# corpus. `schedule_localization._end_page_for` instead compares a boundary
# candidate's font size directly to the schedule's own matched heading (see
# its module docstring) -- a per-span, not whole-document, comparison.
_CLUSTER_GAP_RATIO = 0.75

# A font-size gap between the top tier and the next tier at or above this
# ratio (top-tier-min / next-tier-max) is treated as unambiguous separation
# (HIGH confidence); below it, the same top-tier classification still holds
# but with MEDIUM confidence.
_UNAMBIGUOUS_GAP_RATIO = 2.0

# A candidate top-tier font-size cluster only qualifies as the document's
# genuine top-level-heading tier if its members span at least this many
# distinct pages -- a one-off cover-page title or a single-page marketing
# insert (both observed in the real BEL corpus) can register as the
# largest font-size cluster in the whole document without being anything
# like a recurring section-heading style; a real top-level-heading tier
# recurs across multiple different pages by construction (one heading per
# section, each on its own page).
_MIN_TOP_TIER_PAGES = 2

# A table-of-contents listing shows up as several heading-candidates on the
# same page, each ending in a short run of digits (its target page number,
# with or without dot leaders) -- generic structural pattern, not any
# specific title or page number.
_TRAILING_PAGE_NUMBER_RE = re.compile(r"[.\s]{1,}\d{1,4}$")
_TOC_MIN_SIBLINGS = 3

# Two same-page heading-candidates with substantial word overlap (e.g. two
# chart titles, "2019 External Revenue Analysis - Geographic" and "2018
# External Revenue Analysis - Geographic" -- sharing every word except the
# year) look like a paired/grouped label set, not independent top-level
# sections -- genuine top-level headings don't usually appear multiply on
# one page with near-duplicate text. Word-set overlap, not a prefix match:
# a prefix check misses this real BEL pair, whose *first* word (the year)
# is exactly what differs between them.
_SHARED_WORDS_MIN_COUNT = 2
_SHARED_WORDS_MIN_RATIO = 0.5


def _cluster_font_sizes(sizes: list[float]) -> list[list[float]]:
    """Group distinct font sizes (descending) by relative gap. Returns a list
    of clusters, each a list of sizes in descending order; `clusters[0]` is
    the document's largest-font tier."""
    unique_sizes = sorted(set(sizes), reverse=True)
    if not unique_sizes:
        return []
    clusters: list[list[float]] = [[unique_sizes[0]]]
    for size in unique_sizes[1:]:
        if size < clusters[-1][-1] * _CLUSTER_GAP_RATIO:
            clusters.append([size])
        else:
            clusters[-1].append(size)
    return clusters


def _shares_words(a: str, b: str) -> bool:
    words_a, words_b = set(a.lower().split()), set(b.lower().split())
    if not words_a or not words_b:
        return False
    shared = words_a & words_b
    overlap_ratio = len(shared) / min(len(words_a), len(words_b))
    return len(shared) >= _SHARED_WORDS_MIN_COUNT and overlap_ratio >= _SHARED_WORDS_MIN_RATIO


def assess_heading_structure(
    headings: list[_HeadingLike], anchor_font_sizes: tuple[float, ...] = ()
) -> dict[uuid.UUID, HeadingStructuralAssessment]:
    """Assess every heading-candidate's structural level, relative to the
    other heading-candidates in the same document (`headings` should be the
    full ordered set for one report, not a pre-filtered subset).

    `anchor_font_sizes` are the font sizes of heading-candidates that
    already matched the target schedule's own heading vocabulary (before
    any table-of-contents filtering -- see `schedule_localization.py`,
    which computes these first). When given, the document's top-level tier
    is the font-size cluster *containing one of these anchors* -- the tier
    the report's own recognized section heading belongs to -- rather than
    simply the largest cluster in the whole document. This matters because
    the largest cluster in a real annual report is not reliably a section
    heading at all: a cover-page title or an isolated marketing insert can
    be larger than every genuine section heading, appear only once, and
    still register as "the largest tier" (real BEL corpus cases). Iterating
    clusters largest-first and taking the first one containing an anchor
    means an outlier larger than the real heading tier is skipped
    automatically, without needing to know anything about it specifically.

    Without anchors (e.g. a standalone caller with no vocabulary-match
    context), falls back to the largest cluster whose members span at least
    `_MIN_TOP_TIER_PAGES` distinct pages, as a generic (weaker) outlier
    filter.

    When no usable top tier can be identified at all, every heading
    defaults to `is_top_level=True, confidence=LOW` -- i.e. this module
    changes nothing, preserving `localize_schedule`'s pre-7C.1b behavior
    exactly, so a report with no structural evidence never regresses.
    """
    by_page: dict[int, list[_HeadingLike]] = {}
    for h in headings:
        by_page.setdefault(h.page_number, []).append(h)

    sizes = [h.font_size for h in headings if h.font_size is not None]
    clusters = _cluster_font_sizes(sizes)

    top_tier: set[float] = set()
    top_tier_confidence = StructuralConfidence.MEDIUM
    top_tier_cluster_index: int | None = None

    if anchor_font_sizes:
        anchor_set = set(anchor_font_sizes)
        for idx, cluster in enumerate(clusters):
            if anchor_set & set(cluster):
                top_tier = set(cluster)
                top_tier_cluster_index = idx
                break

    if top_tier_cluster_index is None:
        # No anchors given, or none of them matched any cluster (shouldn't
        # happen if the anchor came from `headings` itself, but a caller
        # could pass an anchor from outside this exact set) -- fall back to
        # the page-span outlier filter.
        for idx, cluster in enumerate(clusters):
            member_pages = {h.page_number for h in headings if h.font_size in cluster}
            if len(member_pages) >= _MIN_TOP_TIER_PAGES:
                top_tier = set(cluster)
                top_tier_cluster_index = idx
                break

    has_separation = top_tier_cluster_index is not None and len(top_tier) < len(set(sizes))
    if has_separation and top_tier_cluster_index + 1 < len(clusters):
        gap_ratio = clusters[top_tier_cluster_index + 1][0] / clusters[top_tier_cluster_index][-1]
        top_tier_confidence = StructuralConfidence.HIGH if gap_ratio < (1 / _UNAMBIGUOUS_GAP_RATIO) else StructuralConfidence.MEDIUM

    assessments: dict[uuid.UUID, HeadingStructuralAssessment] = {}

    for h in headings:
        page_siblings = by_page[h.page_number]
        toc_like_siblings = [s for s in page_siblings if _TRAILING_PAGE_NUMBER_RE.search(s.text.strip())]
        if len(toc_like_siblings) >= _TOC_MIN_SIBLINGS and _TRAILING_PAGE_NUMBER_RE.search(h.text.strip()):
            assessments[h.id] = HeadingStructuralAssessment(
                heading_id=h.id, is_top_level=False, confidence=StructuralConfidence.HIGH, is_toc_entry=True,
                evidence=(
                    f"page {h.page_number} carries {len(toc_like_siblings)} heading-candidates each ending "
                    "in a page-number suffix -- treated as a table-of-contents listing, not a section heading",
                ),
            )
            continue

        # A same-page sibling sharing substantial word overlap (chart-title
        # pairs, grouped labels) is strong, independent evidence on its own
        # -- applied unconditionally, *before* the font-tier check, not only
        # when font tiering happens to agree. Font-size clustering across an
        # entire annual report can be a smooth, gradual spectrum with no
        # clean gap near a real chart title's size (the real BEL 2020 case:
        # the matched heading's own tier turns out to span everything from
        # 18pt down to 8pt, swallowing an 8pt chart title along with it) --
        # relying on the font tier to also flag the sibling would silently
        # miss exactly this case.
        paired_siblings = [
            s for s in page_siblings
            if s.id != h.id and _shares_words(s.text.strip(), h.text.strip())
        ]
        if paired_siblings:
            font_agrees = h.font_size is not None and has_separation and h.font_size not in top_tier
            assessments[h.id] = HeadingStructuralAssessment(
                heading_id=h.id, is_top_level=False,
                confidence=StructuralConfidence.HIGH if font_agrees else StructuralConfidence.MEDIUM,
                is_toc_entry=False,
                evidence=(
                    f"shares {_SHARED_WORDS_MIN_COUNT}+ words with {len(paired_siblings)} other "
                    "heading-candidate(s) on the same page -- treated as a paired/grouped label, not a "
                    "section boundary",
                ),
            )
            continue

        if h.font_size is None or not has_separation:
            assessments[h.id] = HeadingStructuralAssessment(
                heading_id=h.id, is_top_level=True, confidence=StructuralConfidence.LOW, is_toc_entry=False,
                evidence=("no document-relative font-size separation available -- defaulting to top-level",),
            )
            continue

        in_top_tier = h.font_size in top_tier
        if in_top_tier:
            evidence = [
                f"font size {h.font_size}pt is in this document's largest heading-candidate size tier "
                f"{sorted(top_tier, reverse=True)}"
            ]
            if h.is_bold:
                evidence.append("bold")
            assessments[h.id] = HeadingStructuralAssessment(
                heading_id=h.id, is_top_level=True, confidence=top_tier_confidence, is_toc_entry=False,
                evidence=tuple(evidence),
            )
        else:
            assessments[h.id] = HeadingStructuralAssessment(
                heading_id=h.id, is_top_level=False, confidence=StructuralConfidence.HIGH, is_toc_entry=False,
                evidence=(
                    f"font size {h.font_size}pt is not in this document's top-level heading-candidate size tier "
                    f"{sorted(top_tier, reverse=True)}",
                ),
            )

    return assessments

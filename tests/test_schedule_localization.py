"""Pure-algorithm tests for `services.schedule_localization` (Track 7C.1).

No database access -- `localize_schedule` takes plain `HeadingBlock` values
and returns a plain `ScheduleLocalizationResult`, mirroring
`test_passage_segmentation.py`'s "Pure-algorithm fixtures (no DB)" pattern.
"""

import uuid

import pytest

from market_documents.models.enums import BoundaryConfidence, NormalizedSchedule, ScheduleLocalizationStatus
from market_documents.services import schedule_localization as sl
from market_documents.services.schedule_config import ScheduleConfig


def _heading(
    page: int, order: int, text: str, *, font_size: float | None = None, is_bold: bool | None = None
) -> sl.HeadingBlock:
    return sl.HeadingBlock(
        id=uuid.uuid4(), page_number=page, reading_order=order, text=text, font_size=font_size, is_bold=is_bold
    )


CONFIG = ScheduleConfig(
    heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Finance director's report", "CFO's review")}
)


def test_exact_match_is_found_primary_only_high_confidence():
    headings = [
        _heading(10, 0, "Corporate governance report"),
        _heading(38, 0, "Finance director's report"),
        _heading(41, 0, "Corporate governance report"),
    ]
    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=CONFIG)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.heading_text == "Finance director's report"
    assert result.primary.start_page == 38
    assert result.primary.end_page == 40  # page before the next heading-candidate block (41)
    assert result.boundary_confidence == BoundaryConfidence.HIGH
    assert result.supporting == ()


def test_substring_match_is_medium_confidence():
    headings = [_heading(16, 0, "6.5 Commentary on the 2024 Financial Results")]
    config = ScheduleConfig(
        heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Financial Results",)}
    )
    result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.boundary_confidence == BoundaryConfidence.MEDIUM


def test_no_match_is_not_found():
    headings = [_heading(10, 0, "Corporate governance report"), _heading(41, 0, "Remuneration committee report")]
    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=CONFIG)

    assert result.status == ScheduleLocalizationStatus.NOT_FOUND
    assert result.primary is None
    assert result.boundary_confidence is None


def test_last_schedule_in_document_ends_at_last_page():
    headings = [_heading(38, 0, "Finance director's report")]
    result = sl.localize_schedule(headings, last_page_number=124, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=CONFIG)

    assert result.primary.end_page == 124


def test_multiple_matches_produce_primary_and_supporting():
    headings = [
        _heading(35, 0, "Finance director's report"),  # e.g. a "Financial" subsection within a joint report
        _heading(38, 0, "Finance director's report"),
        _heading(41, 0, "Corporate governance report"),
    ]
    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=CONFIG)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_AND_SUPPORTING
    assert result.primary.start_page == 35
    assert len(result.supporting) == 1
    assert result.supporting[0].start_page == 38


def test_non_financial_performance_schedule_raises_not_implemented():
    headings = [_heading(10, 0, "Corporate governance report")]
    with pytest.raises(NotImplementedError):
        sl.localize_schedule(
            headings, last_page_number=100, schedule=NormalizedSchedule.CORPORATE_GOVERNANCE, config=CONFIG
        )


# --------------------------------------------------------------------------
# Track 7C.1b: hierarchy-aware boundary termination
# --------------------------------------------------------------------------


def test_internal_subsection_heading_does_not_terminate_parent_schedule():
    """ACT-shaped: internal CFO-review subsection headings, all in a much
    smaller font tier than the section heading itself, must not truncate
    the schedule -- it must extend through the last of them."""
    headings = [
        _heading(60, 0, "CFO'S REVIEW", font_size=62.2, is_bold=True),
        _heading(63, 0, "Depreciation/amortisation", font_size=11.4),
        _heading(64, 0, "IFRS 16 (leases) net effect", font_size=11.4),
        _heading(65, 0, "Healthcare Services Financial Performance", font_size=12.0),
        _heading(66, 0, "Capital management", font_size=12.0),
        _heading(67, 0, "In conclusion", font_size=12.0),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("CFO's review",)})

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.start_page == 60
    assert result.primary.end_page == 100  # no later top-level heading -- runs to the document's last page


def test_chart_title_does_not_terminate_parent_schedule():
    """BEL-shaped: chart-title heading-candidates sharing a text prefix on
    the same page must not truncate the schedule merely because they are
    heading-candidates."""
    headings = [
        _heading(38, 0, "Financial review", font_size=16.0, is_bold=True),
        _heading(40, 0, "2019 External Revenue Analysis - Geographic", font_size=9.0),
        _heading(40, 1, "2019 External Revenue Analysis - by product", font_size=9.0),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Financial review",)})

    result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 50


def test_next_genuine_top_level_heading_still_terminates_schedule():
    headings = [
        _heading(38, 0, "Financial review", font_size=16.0, is_bold=True),
        _heading(40, 0, "Depreciation", font_size=9.0),  # internal subsection -- must not terminate
        _heading(45, 0, "Corporate governance report", font_size=16.0, is_bold=True),  # same tier -- terminates
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Financial review",)})

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 44  # page before the next top-level heading (45)


def test_hierarchy_fix_does_not_rely_on_absolute_act_font_thresholds():
    """The same relative pattern (large section-heading tier, small
    subsection tier) must behave identically at a different absolute point
    scale than the real ACT corpus -- proving no hard-coded ACT threshold."""
    headings = [
        _heading(10, 0, "CFO's review", font_size=20.0, is_bold=True),
        _heading(12, 0, "Capital management", font_size=4.0),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("CFO's review",)})

    result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 50  # "Capital management" (small tier) does not terminate


def test_table_of_contents_entry_is_not_matched_as_primary_heading():
    headings = [
        _heading(3, 0, "Chairman's statement....................5"),
        _heading(3, 1, "Financial review....................38"),
        _heading(3, 2, "Corporate governance report....................41"),
        _heading(3, 3, "Remuneration report....................55"),
        _heading(38, 0, "Financial review", font_size=16.0, is_bold=True),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Financial review",)})

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.start_page == 38  # the real heading, not the p.3 TOC listing


# --------------------------------------------------------------------------
# Track 7D.1: word-order-tolerant matching, evidence-based primary
# selection, and per-span font-ratio boundary termination
# --------------------------------------------------------------------------


def test_word_order_scrambled_heading_matches_vocabulary():
    """Real ACT 2019 corpus text extracts a heading's words in a different
    order than they're laid out on the page ("REPORT Group CFO's" for what
    reads as "Group CFO's Report"). A pure substring check never
    generalizes to this; `_matches_vocabulary` must also match when the
    heading contains every word of a vocabulary phrase, in any order."""
    matched, exact = sl._matches_vocabulary("REPORT Group CFO's", ("CFO's report",))
    assert matched is True
    assert exact is False  # weaker evidence than a substring/exact match


def test_word_order_tolerant_matching_does_not_relax_exact_match():
    matched, exact = sl._matches_vocabulary("CFO's report", ("CFO's report",))
    assert matched is True
    assert exact is True


def test_unrelated_heading_with_only_some_words_does_not_match():
    matched, _ = sl._matches_vocabulary("Group CEO's report", ("CFO's report",))
    assert matched is False


def test_word_order_tolerance_does_not_match_words_scattered_far_apart():
    """Real BEL 2016 corpus false-positive risk: an unrelated heading
    ("FINANCIAL STATEMENTS AND EXTERNAL REVIEW", an audit-review section)
    contains both "financial" and "review" but three words apart -- must
    not match "Financial review" just because both words appear somewhere
    in the heading. Word-order tolerance is for a local
    reordering/insertion artifact, not scattered coincidental word reuse."""
    matched, _ = sl._matches_vocabulary("FINANCIAL STATEMENTS AND EXTERNAL REVIEW", ("Financial review",))
    assert matched is False


def test_primary_selection_prefers_genuine_section_over_earlier_coincidental_match():
    """ACT-2019-shaped: an ordinary early-page sentence fragment
    substring-matches the vocabulary and precedes the real, much larger
    section heading by many pages. The real heading (found only via
    word-order-tolerant matching) must still win primary selection."""
    headings = [
        _heading(13, 11, "Consistent financial performance", font_size=11.0),
        _heading(40, 2, "REPORT\nGroup CFO's", font_size=57.58),
        _heading(42, 1, "GROUP CFO'S REPORT (CONTINUED)", font_size=11.0),
        _heading(44, 1, "Results AT A GLANCE", font_size=45.08),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("CFO's report",)})

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.start_page == 40
    assert result.primary.end_page == 43  # page before "Results AT A GLANCE" (44)


def test_end_boundary_excludes_subsection_heading_close_in_font_to_parent():
    """BEL-2017-shaped: the schedule's own subsection headings (e.g. 'Gross
    margin', 'Revenue analysis') sit at 18pt under a 24pt section heading --
    a ratio (0.75) landing exactly on `heading_structure`'s own
    document-wide cluster-gap threshold, so document-wide clustering alone
    cannot tell them apart from a genuine next top-level section. The
    per-span font-ratio check must still exclude them."""
    headings = [
        _heading(24, 1, "Finance Director's Report", font_size=24.0),
        _heading(25, 3, "Revenue analysis", font_size=18.0),
        _heading(25, 4, "Gross margin", font_size=18.0),
        _heading(28, 1, "Corporate Governance Report", font_size=24.0),
    ]
    config = ScheduleConfig(
        heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Finance director's report",)}
    )

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 27  # page before the genuine next section (28), not 24


def test_end_boundary_includes_genuine_next_section_moderately_smaller_in_font():
    """ACT-2019-shaped: the genuine next top-level section is rendered at a
    moderately smaller font than the schedule's own heading (45.08pt vs
    57.58pt, ratio 0.783) -- still close enough to be the same "cover title"
    tier, and must still terminate the span."""
    headings = [
        _heading(40, 2, "Group CFO's Report", font_size=57.58),
        _heading(42, 1, "Group CFO's Report (continued)", font_size=11.0),
        _heading(43, 5, "In conclusion", font_size=11.0),
        _heading(44, 1, "Results AT A GLANCE", font_size=45.08),
    ]
    config = ScheduleConfig(heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("CFO's report",)})

    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 43  # includes "In conclusion", stops before the next real section


def test_end_boundary_font_ratio_scales_with_document_not_absolute_points():
    """The same relative pattern (a materially smaller subsection tier vs.
    the schedule heading's own tier) must behave identically at a different
    absolute point scale, proving the ratio isn't tuned to one document's
    literal font sizes."""
    headings = [
        _heading(10, 1, "Finance director's report", font_size=12.0),
        _heading(11, 1, "Gross margin", font_size=9.0),  # ratio 0.75, same as the BEL 24/18 case
        _heading(14, 1, "Corporate governance report", font_size=12.0),
    ]
    config = ScheduleConfig(
        heading_vocabulary={NormalizedSchedule.FINANCIAL_PERFORMANCE: ("Finance director's report",)}
    )

    result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=config)

    assert result.primary.end_page == 13  # subsection at page 11 does not terminate; page 14 does


def test_previously_working_schedule_unchanged_with_no_font_evidence():
    """A report with no font data at all (the exact fixture from
    `test_exact_match_is_found_primary_only_high_confidence`) must localize
    identically to before 7C.1b."""
    headings = [
        _heading(10, 0, "Corporate governance report"),
        _heading(38, 0, "Finance director's report"),
        _heading(41, 0, "Corporate governance report"),
    ]
    result = sl.localize_schedule(headings, last_page_number=100, schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE, config=CONFIG)

    assert result.primary.start_page == 38
    assert result.primary.end_page == 40

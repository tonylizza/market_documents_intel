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


def test_unimplemented_schedule_raises_not_implemented():
    """Track 7D.6 implemented CEO_REVIEW/CHAIR_REVIEW -- this now targets a
    schedule still genuinely unimplemented (mirrors Track 7D.3's/7D.4's/
    7D.5's own replacement of this test each time another schedule was
    implemented)."""
    headings = [_heading(10, 0, "Strategy")]
    with pytest.raises(NotImplementedError):
        sl.localize_schedule(
            headings, last_page_number=100, schedule=NormalizedSchedule.STRATEGY, config=CONFIG
        )


# --------------------------------------------------------------------------
# Track 7D.3: CORPORATE_GOVERNANCE schedule localization
# --------------------------------------------------------------------------

GOVERNANCE_CONFIG = ScheduleConfig(
    heading_vocabulary={NormalizedSchedule.CORPORATE_GOVERNANCE: ("Corporate governance report",)}
)


def test_corporate_governance_schedule_localizes_like_financial_performance():
    """The algorithm is schedule-agnostic; CORPORATE_GOVERNANCE must resolve
    exactly like FINANCIAL_PERFORMANCE given the same shape of evidence."""
    headings = [
        _heading(38, 0, "Finance director's report"),
        _heading(43, 0, "Corporate governance report"),
        _heading(56, 0, "Remuneration committee report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=100, schedule=NormalizedSchedule.CORPORATE_GOVERNANCE, config=GOVERNANCE_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 43
    assert result.primary.end_page == 55  # page before the next section (56)


def test_corporate_governance_continued_banner_does_not_terminate_schedule():
    """BEL-shaped: 'Corporate governance report continued' banners must
    extend the schedule, not be treated as a new section boundary."""
    headings = [
        _heading(43, 0, "Corporate governance report", font_size=16.0, is_bold=True),
        _heading(44, 0, "Corporate governance report continued", font_size=16.0, is_bold=True),
        _heading(46, 0, "Corporate governance report continued", font_size=16.0, is_bold=True),
        _heading(50, 0, "Social, ethics and transformation committee report", font_size=16.0, is_bold=True),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=100, schedule=NormalizedSchedule.CORPORATE_GOVERNANCE, config=GOVERNANCE_CONFIG
    )

    assert result.primary.start_page == 43
    assert result.primary.end_page == 49  # page before the genuine next section (50)


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


# --------------------------------------------------------------------------
# Track 7D.4: REMUNERATION schedule localization
# --------------------------------------------------------------------------

REMUNERATION_CONFIG = ScheduleConfig(
    heading_vocabulary={NormalizedSchedule.REMUNERATION: ("Remuneration report",)}
)


def test_remuneration_schedule_localizes_like_other_schedules():
    """The algorithm is schedule-agnostic; REMUNERATION must resolve exactly
    like FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE given the same shape of
    evidence."""
    headings = [
        _heading(43, 0, "Corporate governance report"),
        _heading(97, 0, "Remuneration report"),
        _heading(122, 0, "Directors' report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.REMUNERATION, config=REMUNERATION_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 97
    assert result.primary.end_page == 121  # page before the next section (122)
    assert result.boundary_confidence == BoundaryConfidence.HIGH


def test_remuneration_substring_match_does_not_win_over_exact_match():
    """Real-corpus case (SUR): 'REMUNERATION REPORTING AND ENGAGEMENT' is a
    substring match on 'Remuneration report' (a bare prefix, since
    "reporting" starts with "report") that appears *before* the genuine
    exact-match heading in reading order -- the existing exact-match-first
    primary-selection rule must still pick the real heading, not the
    coincidental substring match."""
    headings = [
        _heading(89, 0, "REMUNERATION REPORTING AND ENGAGEMENT:"),
        _heading(97, 0, "REMUNERATION REPORT"),
        _heading(122, 0, "Directors' report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.REMUNERATION, config=REMUNERATION_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_AND_SUPPORTING
    assert result.primary.start_page == 97
    assert result.primary.exact_match is True
    assert result.supporting[0].start_page == 89
    assert result.supporting[0].exact_match is False


def test_remuneration_continued_banner_does_not_terminate_schedule():
    headings = [
        _heading(97, 0, "Remuneration report"),
        _heading(102, 0, "Remuneration report continued"),
        _heading(122, 0, "Directors' report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.REMUNERATION, config=REMUNERATION_CONFIG
    )

    assert result.primary.end_page == 121


# --------------------------------------------------------------------------
# Track 7D.5: MATERIAL_RISKS schedule localization
# --------------------------------------------------------------------------

MATERIAL_RISKS_CONFIG = ScheduleConfig(
    heading_vocabulary={
        NormalizedSchedule.MATERIAL_RISKS: ("Overview of our top risks", "Material risks and opportunities")
    }
)


def test_material_risks_schedule_localizes_like_other_schedules():
    """The algorithm is schedule-agnostic; MATERIAL_RISKS must resolve
    exactly like FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE/REMUNERATION
    given the same shape of evidence."""
    headings = [
        _heading(38, 0, "Our risks"),
        _heading(39, 0, "Overview of our top risks"),
        _heading(45, 0, "Audit and risk committee report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.MATERIAL_RISKS, config=MATERIAL_RISKS_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 39
    assert result.primary.end_page == 44  # page before the next section (45)
    assert result.boundary_confidence == BoundaryConfidence.HIGH


def test_material_risks_generic_navigational_label_is_not_configured_vocabulary():
    """Real-corpus case (ACT): a value-creation-model overview page carries
    a short 'Risks and \\nopportunities' navigational cross-reference label
    in years lacking a real, bounded risk chapter. That generic phrase is
    deliberately NOT part of the configured vocabulary (see
    schedule_config.py's MATERIAL_RISKS comment) specifically so it cannot
    be matched at all -- confirmed here: a heading with only that
    navigational text produces NOT_FOUND, not a false-positive match."""
    headings = [_heading(4, 0, "Risks and \nopportunities")]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.MATERIAL_RISKS, config=MATERIAL_RISKS_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.NOT_FOUND


def test_material_risks_real_chapter_wins_over_navigational_label_when_both_present():
    """Same real-corpus shape as above, but with the genuine chapter heading
    also present later in the document (ACT 2024's real shape) -- the
    navigational label must not be configured vocabulary at all, so only
    the genuine chapter heading is ever a candidate."""
    headings = [
        _heading(8, 0, "Risks and \nopportunities"),
        _heading(40, 0, "Overview of our top risks and related opportunities"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.MATERIAL_RISKS, config=MATERIAL_RISKS_CONFIG
    )

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 40


def test_material_risks_continued_banner_does_not_terminate_schedule():
    headings = [
        _heading(39, 0, "Overview of our top risks"),
        _heading(41, 0, "Overview of our top risks continued"),
        _heading(45, 0, "Audit and risk committee report"),
    ]
    result = sl.localize_schedule(
        headings, last_page_number=150, schedule=NormalizedSchedule.MATERIAL_RISKS, config=MATERIAL_RISKS_CONFIG
    )

    assert result.primary.end_page == 44


# --------------------------------------------------------------------------
# Track 7D.6: CEO_REVIEW / CHAIR_REVIEW schedule localization
# --------------------------------------------------------------------------

CEO_CHAIR_CONFIG = ScheduleConfig(
    heading_vocabulary={
        NormalizedSchedule.CEO_REVIEW: ("CEO's review", "Group CEO's report", "Joint report by the chairman and chief executive"),
        NormalizedSchedule.CHAIR_REVIEW: ("Chairman's review", "Chairperson's report", "Joint report by the chairman and chief executive"),
    }
)


def test_ceo_review_schedule_localizes_like_other_schedules():
    """The algorithm is schedule-agnostic; CEO_REVIEW must resolve exactly
    like FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE/REMUNERATION/
    MATERIAL_RISKS given the same shape of evidence."""
    headings = [
        _heading(10, 0, "Chairperson's report"),
        _heading(28, 0, "CEO's review"),
        _heading(35, 0, "Corporate governance report"),
    ]
    result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CEO_REVIEW, config=CEO_CHAIR_CONFIG)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 28
    assert result.primary.end_page == 34
    assert result.boundary_confidence == BoundaryConfidence.HIGH


def test_chair_review_schedule_localizes_like_other_schedules():
    headings = [
        _heading(10, 0, "Chairperson's report"),
        _heading(28, 0, "CEO's review"),
    ]
    result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CHAIR_REVIEW, config=CEO_CHAIR_CONFIG)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 10
    assert result.primary.end_page == 27


def test_joint_chapter_maps_to_both_ceo_and_chair_schedules():
    """BEL's/SDL's real corpus shape: one joint chapter, one heading, no
    split -- the same source span independently localizes as the primary
    span under both CEO_REVIEW and CHAIR_REVIEW because both schedules'
    vocabularies deliberately include the same joint-chapter phrase (see
    schedule_config.py's changelog). No schema change: each call is a
    fully independent, schedule-scoped run."""
    headings = [_heading(24, 0, "Joint report by the chairman and chief executive")]

    ceo_result = sl.localize_schedule(headings, last_page_number=90, schedule=NormalizedSchedule.CEO_REVIEW, config=CEO_CHAIR_CONFIG)
    chair_result = sl.localize_schedule(headings, last_page_number=90, schedule=NormalizedSchedule.CHAIR_REVIEW, config=CEO_CHAIR_CONFIG)

    assert ceo_result.primary.start_page == chair_result.primary.start_page == 24
    assert ceo_result.primary.end_page == chair_result.primary.end_page == 90
    assert ceo_result.primary.heading_text == chair_result.primary.heading_text


def test_chair_only_issuer_has_no_ceo_review_match():
    """SBP's real corpus shape: a standalone Chairman's letter, no
    standalone CEO section at all -- CEO_REVIEW must be NOT_FOUND, not a
    fabricated/guessed match."""
    headings = [_heading(2, 0, "Chairman's letter to shareholders")]
    config = ScheduleConfig(
        heading_vocabulary={
            NormalizedSchedule.CEO_REVIEW: ("CEO's review",),
            NormalizedSchedule.CHAIR_REVIEW: ("Chairman's letter to shareholders",),
        }
    )
    ceo_result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.CEO_REVIEW, config=config)
    chair_result = sl.localize_schedule(headings, last_page_number=50, schedule=NormalizedSchedule.CHAIR_REVIEW, config=config)

    assert ceo_result.status == ScheduleLocalizationStatus.NOT_FOUND
    assert chair_result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY


def test_no_clear_section_issuer_has_neither_schedule_matched():
    """KP2's real corpus shape: no CEO/Chairman/Chairperson heading-candidate
    at all in any of its 6 real report years -- both schedules must be
    NOT_FOUND, never guessed from its "Review of Operations and Strategic
    Report" chapter."""
    headings = [_heading(5, 0, "Review of Operations and Strategic Report")]
    ceo_result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CEO_REVIEW, config=CEO_CHAIR_CONFIG)
    chair_result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CHAIR_REVIEW, config=CEO_CHAIR_CONFIG)

    assert ceo_result.status == ScheduleLocalizationStatus.NOT_FOUND
    assert chair_result.status == ScheduleLocalizationStatus.NOT_FOUND


def test_toc_entry_is_not_matched_as_ceo_chair_heading():
    """Real corpus false positive (7D.5a/7D.6 finding): page-3 table-of-
    contents lines like 'GROUP CEO'S REPORT 47' must never be matched as
    the schedule's own heading -- only the real chapter heading later in
    the document counts."""
    headings = [
        _heading(3, 0, "GROUP CEO'S REPORT 47", font_size=10.0),
        _heading(3, 1, "CHAIRPERSON'S REPORT 4", font_size=10.0),
        _heading(47, 0, "GROUP CEO'S REPORT", font_size=40.0),
        _heading(4, 0, "CHAIRPERSON'S REPORT", font_size=40.0),
    ]
    config = ScheduleConfig(
        heading_vocabulary={
            NormalizedSchedule.CEO_REVIEW: ("Group CEO's report",),
            NormalizedSchedule.CHAIR_REVIEW: ("Chairperson's report",),
        }
    )
    ceo_result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CEO_REVIEW, config=config)

    assert ceo_result.primary.start_page == 47


def test_split_heading_fragment_on_same_page_is_concatenated_and_matched():
    """Track 7D.6's one bounded generic fix: a real corpus defect where a
    section's own title is split across two consecutive same-page
    HEADING_CANDIDATE blocks by the upstream extraction pipeline (ACT
    2020's real corpus: 'CHAIRMAN'S' then 'REVIEW' as two separate blocks,
    same font, same page). Neither fragment alone matches the vocabulary,
    but their same-page concatenation does."""
    headings = [
        _heading(24, 0, "CHAIRMAN'S", font_size=62.23),
        _heading(24, 1, "REVIEW", font_size=62.23),
        _heading(25, 0, "DR ANNA MOKGOKONG", font_size=15.15),
    ]
    result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CHAIR_REVIEW, config=CEO_CHAIR_CONFIG)

    assert result.status == ScheduleLocalizationStatus.FOUND_PRIMARY_ONLY
    assert result.primary.start_page == 24
    assert result.primary.heading_text == "CHAIRMAN'S REVIEW"
    assert result.boundary_confidence == BoundaryConfidence.HIGH  # exact match once concatenated


def test_split_heading_fragments_on_different_pages_are_not_concatenated():
    """The concatenation fix is scoped to same-page fragments only -- two
    unrelated headings on different pages must never be joined into a
    false vocabulary match."""
    headings = [
        _heading(24, 0, "CHAIRMAN'S", font_size=62.23),
        _heading(25, 0, "REVIEW", font_size=62.23),
    ]
    result = sl.localize_schedule(headings, last_page_number=150, schedule=NormalizedSchedule.CHAIR_REVIEW, config=CEO_CHAIR_CONFIG)

    assert result.status == ScheduleLocalizationStatus.NOT_FOUND

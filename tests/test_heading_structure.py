"""Pure-algorithm tests for `services.heading_structure` (Track 7C.1b).

No database access -- `assess_heading_structure` takes plain `HeadingBlock`
values (the same dataclass `schedule_localization.py` uses) and returns a
plain assessment dict, mirroring `test_schedule_localization.py`'s pattern.
"""

import uuid

from market_documents.services import heading_structure as hs
from market_documents.services.schedule_localization import HeadingBlock


def _heading(page: int, order: int, text: str, *, font_size: float | None = None, is_bold: bool | None = None) -> HeadingBlock:
    return HeadingBlock(id=uuid.uuid4(), page_number=page, reading_order=order, text=text, font_size=font_size, is_bold=is_bold)


def test_large_font_tier_is_top_level_small_tier_is_not():
    # ACT-shaped: a clear ~5x gap between the section-heading tier and the
    # internal-subsection tier, but using different absolute point sizes
    # than the real corpus to prove the rule is document-relative. Two
    # section headings (on different pages) so the top tier is a genuine
    # recurring tier, not a one-off outlier -- matches real annual reports,
    # which always have more than one top-level section.
    section_a = _heading(60, 0, "CFO'S REVIEW", font_size=62.2, is_bold=True)
    section_b = _heading(90, 0, "Corporate governance report", font_size=60.0, is_bold=True)
    subsection_a = _heading(63, 0, "Depreciation/amortisation", font_size=11.4)
    subsection_b = _heading(65, 0, "In conclusion", font_size=12.0)

    assessments = hs.assess_heading_structure([section_a, section_b, subsection_a, subsection_b])

    assert assessments[section_a.id].is_top_level is True
    assert assessments[section_b.id].is_top_level is True
    assert assessments[subsection_a.id].is_top_level is False
    assert assessments[subsection_b.id].is_top_level is False


def test_top_level_classification_is_relative_not_absolute():
    """The same qualitative pattern (one large tier, one small tier, ~5x
    gap) must produce the same classification regardless of the absolute
    point sizes involved -- no hard-coded ACT-specific threshold."""
    small_scale = [
        _heading(10, 0, "Financial review", font_size=6.0),
        _heading(30, 0, "Corporate governance report", font_size=6.0),
        _heading(12, 0, "Capital management", font_size=1.2),
    ]
    large_scale = [
        _heading(10, 0, "Financial review", font_size=600.0),
        _heading(30, 0, "Corporate governance report", font_size=600.0),
        _heading(12, 0, "Capital management", font_size=120.0),
    ]

    for headings in (small_scale, large_scale):
        assessments = hs.assess_heading_structure(headings)
        assert assessments[headings[0].id].is_top_level is True
        assert assessments[headings[1].id].is_top_level is True
        assert assessments[headings[2].id].is_top_level is False


def test_anchor_font_sizes_select_the_matched_headings_tier_not_the_largest():
    """Real BEL case: the document's single largest font-size cluster can be
    a one-off outlier (a cover-page title) that isn't a section heading at
    all. When the caller supplies the matched schedule heading's own font
    size as an anchor, the outlier must be skipped in favor of the tier the
    real heading actually belongs to."""
    cover_title = _heading(1, 0, "BELL EQUIPMENT LIMITED INTEGRATED ANNUAL REPORT", font_size=38.33)
    section = _heading(36, 0, "Finance director's report", font_size=18.0, is_bold=True)
    next_section = _heading(40, 0, "Corporate governance report", font_size=18.0, is_bold=True)
    subsection = _heading(37, 0, "Some internal subsection", font_size=10.0)

    assessments = hs.assess_heading_structure(
        [cover_title, section, next_section, subsection], anchor_font_sizes=(18.0,)
    )

    assert assessments[cover_title.id].is_top_level is False
    assert assessments[section.id].is_top_level is True
    assert assessments[next_section.id].is_top_level is True


def test_paired_same_page_titles_are_not_top_level_even_without_font_separation():
    # BEL-shaped: two chart titles on the same page sharing most words,
    # with no usable font-size separation (single tier).
    chart_a = _heading(20, 0, "2019 External Revenue Analysis - Geographic", font_size=9.0)
    chart_b = _heading(20, 1, "2019 External Revenue Analysis - by product", font_size=9.0)

    assessments = hs.assess_heading_structure([chart_a, chart_b])

    assert assessments[chart_a.id].is_top_level is False
    assert assessments[chart_b.id].is_top_level is False


def test_paired_titles_differing_in_leading_word_are_still_caught():
    """Real BEL 2019 case: the two chart titles differ in their *first*
    word (the year), not a shared prefix -- a naive prefix check misses
    this; word-set overlap must not."""
    chart_2019 = _heading(37, 6, "2019 External Revenue Analysis - Geographic", font_size=10.0, is_bold=True)
    chart_2018 = _heading(37, 15, "2018 External Revenue Analysis - Geographic", font_size=10.0, is_bold=True)

    assessments = hs.assess_heading_structure([chart_2019, chart_2018])

    assert assessments[chart_2019.id].is_top_level is False
    assert assessments[chart_2018.id].is_top_level is False


def test_paired_titles_demoted_even_when_font_separation_exists_elsewhere():
    section = _heading(38, 0, "Financial review", font_size=60.0, is_bold=True)
    chart_a = _heading(40, 0, "2019 External Revenue Analysis - Geographic", font_size=9.0)
    chart_b = _heading(40, 1, "2019 External Revenue Analysis - by product", font_size=9.0)

    assessments = hs.assess_heading_structure([section, chart_a, chart_b])

    assert assessments[section.id].is_top_level is True
    assert assessments[chart_a.id].is_top_level is False
    assert assessments[chart_b.id].is_top_level is False


def test_no_font_evidence_defaults_to_top_level():
    """Regression safety: a report with no font data at all (e.g. legacy
    TextBlock rows missing font_size) must fall back to treating every
    heading-candidate as top-level -- the pre-7C.1b behavior -- rather than
    guessing."""
    a = _heading(10, 0, "Corporate governance report")
    b = _heading(38, 0, "Finance director's report")

    assessments = hs.assess_heading_structure([a, b])

    assert assessments[a.id].is_top_level is True
    assert assessments[b.id].is_top_level is True
    assert assessments[a.id].confidence == hs.StructuralConfidence.LOW


def test_table_of_contents_listing_is_flagged_and_not_top_level():
    toc_page = [
        _heading(3, 0, "Chairman's statement....................5"),
        _heading(3, 1, "CFO's review....................38"),
        _heading(3, 2, "Corporate governance report....................41"),
        _heading(3, 3, "Remuneration report....................55"),
    ]
    real_heading = _heading(38, 0, "CFO's review", font_size=60.0)

    assessments = hs.assess_heading_structure([*toc_page, real_heading])

    for entry in toc_page:
        assert assessments[entry.id].is_toc_entry is True
        assert assessments[entry.id].is_top_level is False
    assert assessments[real_heading.id].is_toc_entry is False


def test_single_heading_no_siblings_defaults_top_level():
    only = _heading(38, 0, "Finance director's report", font_size=14.0)
    assessments = hs.assess_heading_structure([only])
    assert assessments[only.id].is_top_level is True

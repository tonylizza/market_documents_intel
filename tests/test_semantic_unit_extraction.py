"""Pure-algorithm tests for `services.semantic_unit_extraction` (Track 7C.1).

No database access -- `extract_unit` takes plain `UnitBlock` values and
returns a plain `SemanticUnitExtractionResult | None`. Includes a
regression test for the exact BEL 2019 "Gross Margin" chart-interruption
defect documented in
docs/experiments/annual-report-bel-compact-validation.md Section 3: a bar
chart's axis labels/percentages sit between the narrative paragraph and the
next heading, so a naive NEXT_HEADING boundary incorrectly sweeps the chart
text into the unit while the configured ANCHOR_SENTENCE boundary correctly
excludes it.
"""

import re
import uuid

from market_documents.models.enums import (
    BlockType,
    BoundaryConfidence,
    NormalizedSchedule,
    SemanticUnitBoundaryStatus,
    SemanticUnitBoundaryStrategy,
)
from market_documents.services import semantic_unit_extraction as sue
from market_documents.services.semantic_unit_config import BEL_GROSS_MARGIN, UnitConfig

ANCHOR_PATTERN = re.compile(
    r"compared\s+with\s+[\d.,]+\s*%\s+in\s+the\s+prior\s+year\.", re.IGNORECASE
)


def _block(page: int, order: int, text: str, block_type: BlockType = BlockType.PARAGRAPH) -> sue.UnitBlock:
    return sue.UnitBlock(id=uuid.uuid4(), page_number=page, reading_order=order, block_type=block_type, text=text)


NEXT_HEADING_CONFIG = UnitConfig(
    unit_key="gross_margin",
    schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
    ticker="BEL",
    start_heading="Gross Margin",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

ANCHOR_CONFIG = UnitConfig(
    unit_key="gross_margin",
    schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
    ticker="BEL",
    start_heading="Gross Margin",
    boundary_strategy=SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE,
    anchor_pattern=ANCHOR_PATTERN,
)

PARAGRAPH_TEXT = (
    "The gross margin is dependent on the product and geographic mix of sales, market "
    "conditions and exchange rates. The gross margin for the year was 24.1% compared "
    "with 26.4% in the prior year."
)
CHART_NOISE_TEXT = "2019 External Revenue Analysis - Geographic\nNorth America 45%\nEurope 30%\nAfrica 25%"


def _bel_2019_fixture() -> list[sue.UnitBlock]:
    return [
        _block(39, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(39, 1, PARAGRAPH_TEXT),
        _block(39, 2, CHART_NOISE_TEXT),
        _block(40, 0, "Other operating income", BlockType.HEADING_CANDIDATE),
    ]


def test_next_heading_boundary_incorrectly_includes_chart_noise():
    blocks = _bel_2019_fixture()
    result = sue.extract_unit(blocks, NEXT_HEADING_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert "External Revenue Analysis" in result.source_text  # the defect this milestone fixes


def test_anchor_sentence_boundary_excludes_chart_noise():
    blocks = _bel_2019_fixture()
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.boundary_confidence == BoundaryConfidence.HIGH
    assert "External Revenue Analysis" not in result.source_text
    assert result.source_text.endswith("in the prior year.")
    assert result.end_page == 39


def test_anchor_matching_tolerates_pdf_line_wrap():
    """Reproduces the BEL 2022 case: 'prior' and 'year' split across a line."""
    wrapped_text = PARAGRAPH_TEXT.replace("prior year.", "prior \nyear.")
    blocks = [
        _block(39, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(39, 1, wrapped_text),
        _block(40, 0, "Other operating income", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED


def test_anchor_not_found_persists_unresolved_with_no_fabricated_text():
    blocks = [
        _block(39, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(39, 1, "A paragraph with no matching closing sentence at all."),
        _block(40, 0, "Other operating income", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.UNRESOLVED
    assert result.source_text is None
    assert result.end_page is None
    assert result.word_count is None
    assert result.boundary_confidence is None
    assert result.extraction_note is not None
    assert result.source_block_spans == ()


# --------------------------------------------------------------------------
# Track 7D.1: generalized ANCHOR_SENTENCE year-reference clause
# --------------------------------------------------------------------------


def test_anchor_matches_year_named_directly_instead_of_prior_year_phrase():
    """Real BEL 2017 wording names the comparison year directly ("...for
    2016.") instead of saying "in the prior year." -- the generalized
    anchor must match this without any BEL/2017/2016-specific code."""
    blocks = [
        _block(25, 0, "Gross margin", BlockType.HEADING_CANDIDATE),
        _block(
            25, 1,
            "The gross margin is dependent on the product and geographic mix of sales. The average gross "
            "margin reduced to 21,3% for 2017 compared with 23,3% for 2016. The Rand was stronger.",
        ),
        _block(26, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, BEL_GROSS_MARGIN)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_text.endswith("compared with 23,3% for 2016.")
    assert "The Rand was stronger" not in result.source_text


def test_anchor_still_matches_original_prior_year_phrasing():
    blocks = _bel_2019_fixture()
    result = sue.extract_unit(blocks, BEL_GROSS_MARGIN)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_text.endswith("in the prior year.")


def test_start_heading_not_found_returns_none():
    blocks = [
        _block(10, 0, "Corporate governance report", BlockType.HEADING_CANDIDATE),
        _block(10, 1, "Some governance text."),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is None


# --------------------------------------------------------------------------
# Track 7D.1: heading embedded mid-block (BEL 2020)
# --------------------------------------------------------------------------


def test_heading_matches_mid_block_after_sentence_boundary():
    """Real BEL 2020 corpus text: "Gross Margin" is fused onto the end of
    the *preceding* section's own paragraph ("...supplied. Gross Margin The
    gross margin is dependent...") rather than starting a fresh block."""
    blocks = [
        _block(
            39, 0,
            "support customers in difficult conditions in Zimbabwe on the basis of payment in advance in "
            "South Africa for parts and machines supplied. Gross Margin The gross margin is dependent on "
            "the product and geographic mix of sales, market conditions and exchange rates. The average "
            "gross margin for the year was 18,4% compared with 18,5% in the prior year.",
        ),
        _block(40, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_heading == "Gross Margin"
    assert "support customers" not in result.source_text
    assert result.source_text.strip().startswith("The gross margin is dependent")
    assert result.source_text.endswith("in the prior year.")


def test_standalone_heading_block_still_works():
    """The pre-existing block-start-anchored case (BEL 2018/2019/2021/2022)
    must still work after generalizing to mid-block matching."""
    blocks = [
        _block(37, 0, "Gross Margin The gross margin is dependent on the product mix. The margin was 18,7% "
               "compared with 19,7% in the prior year."),
        _block(38, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_heading == "Gross Margin"


def test_ordinary_body_prose_occurrence_of_heading_words_does_not_falsely_match():
    """An ordinary, mid-sentence mention of the heading's own words (not at
    a sentence boundary) must not be mistaken for the heading itself -- the
    generalization must not blindly split every paragraph."""
    blocks = [
        _block(
            39, 0,
            "The company's overall profitability, including its gross margin performance, was strong "
            "throughout the year despite challenging market conditions across every region.",
        ),
        _block(40, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is None


def test_next_heading_falls_back_to_end_of_provided_range_when_no_further_heading():
    blocks = [
        _block(39, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(39, 1, PARAGRAPH_TEXT),
    ]
    result = sue.extract_unit(blocks, NEXT_HEADING_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.end_page == 39


def test_next_heading_skips_continuation_banner_and_keeps_scanning():
    """Track 7D.2 real-corpus defect (ACT 2021 "Healthcare Services
    Financial Performance"): a "<heading> continued" page banner is a
    heading-candidate classified as narrative in this report year, and must
    not terminate the section -- the real content resumes on the next page
    before the true next section heading. Mirrors
    `schedule_localization.py`'s own schedule-level "continued" rule."""
    blocks = [
        _block(62, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(62, 1, "First paragraph of real content."),
        _block(62, 2, "CFO's review continued", BlockType.HEADING_CANDIDATE),
        _block(63, 0, "Second paragraph, a real continuation of the same section."),
        _block(63, 1, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, NEXT_HEADING_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.end_page == 63
    assert "First paragraph of real content." in result.source_text
    assert "Second paragraph, a real continuation of the same section." in result.source_text
    assert "continued" not in result.source_text.lower()


def test_next_heading_still_stops_at_a_genuine_non_continuation_heading():
    """Regression guard: an ordinary heading-candidate (not a "continued"
    banner) must still terminate the section exactly as before."""
    blocks = [
        _block(62, 0, "Gross Margin", BlockType.HEADING_CANDIDATE),
        _block(62, 1, "First paragraph of real content."),
        _block(62, 2, "Financial position", BlockType.HEADING_CANDIDATE),
        _block(63, 0, "Unrelated content from the next section."),
    ]
    result = sue.extract_unit(blocks, NEXT_HEADING_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.end_page == 62
    assert "Unrelated content from the next section." not in result.source_text


def test_is_continuation_heading_matches_trailing_word_only():
    assert sue._is_continuation_heading("CFO's review continued") is True
    assert sue._is_continuation_heading("Finance director's report continued") is True
    assert sue._is_continuation_heading("Continued operations") is False
    assert sue._is_continuation_heading("Financial position") is False


# --------------------------------------------------------------------------
# Track 7D.2a: exact/substring/word-order-aware start-heading matching
# --------------------------------------------------------------------------


def test_matches_heading_exact_normalized_match():
    matched, exact = sue._matches_heading("CAPITAL MANAGEMENT", "Capital management")
    assert matched is True
    assert exact is True


def test_matches_heading_substring_match_is_not_exact():
    matched, exact = sue._matches_heading("Capital management and funding", "Capital management")
    assert matched is True
    assert exact is False


def test_matches_heading_word_order_tolerant_match_is_not_exact():
    matched, exact = sue._matches_heading("REPORT Group CFO's", "Group CFO's Report")
    assert matched is True
    assert exact is False


def test_matches_heading_unrelated_text_does_not_match():
    matched, _ = sue._matches_heading("Group CEO's report", "CFO's report")
    assert matched is False


def test_start_heading_selection_prefers_exact_match_over_earlier_coincidental_substring():
    """Real ACT 2024 corpus defect (Track 7D.2's rejected-candidate finding,
    fixed here): an unrelated decorative pull-quote heading-candidate
    fragment, "by prudent capital management policies", bare-substring-
    matches the configured heading "Capital management" and sits earlier in
    reading order than the real, exact "CAPITAL MANAGEMENT" section
    heading. The pre-7D.2a first-positional-match behavior let the false
    match win and never reached the real section; ranking by exactness
    first must pick the real heading instead."""
    config = UnitConfig(
        unit_key="capital_management",
        schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
        ticker="ACT",
        start_heading="Capital management",
        boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
        anchor_pattern=None,
    )
    blocks = [
        _block(60, 0, "by prudent capital management policies", BlockType.HEADING_CANDIDATE),
        _block(60, 1, "Unrelated pull-quote page content."),
        _block(65, 0, "CAPITAL MANAGEMENT", BlockType.HEADING_CANDIDATE),
        _block(65, 1, "The real capital management narrative content."),
        _block(66, 0, "Funding", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, config)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_heading == "CAPITAL MANAGEMENT"
    assert result.start_page == 65
    assert "Unrelated pull-quote page content." not in result.source_text
    assert "The real capital management narrative content." in result.source_text


def test_start_heading_selection_still_picks_earliest_among_equal_exactness():
    """Two equally exact matches must still resolve to the earliest one, so
    existing single-match/first-occurrence behavior is unchanged."""
    config = UnitConfig(
        unit_key="capital_management",
        schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
        ticker="ACT",
        start_heading="Capital management",
        boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
        anchor_pattern=None,
    )
    blocks = [
        _block(21, 0, "Capital management", BlockType.HEADING_CANDIDATE),
        _block(21, 1, "First occurrence content."),
        _block(22, 0, "Funding", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, config)

    assert result is not None
    assert result.start_page == 21
    assert "First occurrence content." in result.source_text


# --------------------------------------------------------------------------
# Track 7D.4a: start-heading false-positive hardening
# (docs/7d4a-start-heading-false-positive-hardening.md)
# --------------------------------------------------------------------------


REMUNERATION_GOVERNANCE_CONFIG = UnitConfig(
    unit_key="remuneration_governance",
    schedule=NormalizedSchedule.REMUNERATION,
    ticker="ACT",
    start_heading="Remuneration governance",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

COMBINED_ASSURANCE_CONFIG = UnitConfig(
    unit_key="combined_assurance",
    schedule=NormalizedSchedule.CORPORATE_GOVERNANCE,
    ticker="ACT",
    start_heading="Combined assurance",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)


def test_run_in_remainder_is_prose_continuation_rejects_same_line_lowercase():
    match = re.match(r"Remuneration governance", "Remuneration governance to remain top of mind")
    assert sue._run_in_remainder_is_prose_continuation(
        "Remuneration governance to remain top of mind", match
    ) is True


def test_run_in_remainder_is_prose_continuation_accepts_capitalized_new_sentence():
    match = re.match(r"Gross Margin", "Gross Margin The gross margin is dependent on the product mix.")
    assert sue._run_in_remainder_is_prose_continuation(
        "Gross Margin The gross margin is dependent on the product mix.", match
    ) is False


def test_run_in_remainder_is_prose_continuation_excuses_line_break_before_lowercase():
    """Real ACT 2019 corpus text: a genuine heading wraps its own year
    suffix onto the next line in lowercase ("Changes to the remuneration
    and related policies \nfor the 2019 financial year") before the real,
    capitalized body paragraph starts on the line after that. A line break
    immediately after the match must not be treated as evidence of a
    same-sentence prose continuation -- only a same-line lowercase
    continuation is (see the two rejection tests above/below)."""
    text = "Changes to the remuneration and related policies \nfor the 2019 financial year\nThe committee reviewed..."
    match = re.match(r"Changes to the remuneration and related policies", text)
    assert sue._run_in_remainder_is_prose_continuation(text, match) is False


def test_start_heading_selection_rejects_run_in_match_that_is_mid_sentence_prose():
    """Real ACT 2024 REMUNERATION corpus defect: p.121 has an ordinary
    PARAGRAPH block, "Remuneration governance to remain top of mind with a
    greater focus on approval frameworks given the larger Sanlam Group
    structure AfroCentric is now part of.", which opens with the configured
    heading's exact words but continues the same sentence rather than
    starting a fresh one. `_heading_run_in_match` matched it (exact by
    construction) and it sat earlier in reading order than the real,
    standalone "Remuneration governance" HEADING_CANDIDATE later in the
    range, so the old (exact, position) ranking let it win outright and the
    real section was never reached. The prose-continuation guard must
    reject it as a candidate at all, letting the real heading resolve."""
    blocks = [
        _block(
            121, 0,
            "Remuneration governance to remain top of mind with a greater focus on approval "
            "frameworks given the larger Sanlam Group structure AfroCentric is now part of.",
        ),
        _block(122, 0, "Remuneration governance", BlockType.HEADING_CANDIDATE),
        _block(
            122, 1,
            "AfroCentric's remuneration policy, structures and processes are set within a "
            "governance framework with designated levels of authority.",
        ),
        _block(123, 0, "Remuneration model", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, REMUNERATION_GOVERNANCE_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.start_page == 122
    assert result.source_heading == "Remuneration governance"
    assert "top of mind" not in result.source_text
    assert "designated levels of authority" in result.source_text


def test_start_heading_selection_rejects_run_in_match_fused_to_unrelated_infographic():
    """Real ACT 2022/2023 CORPORATE_GOVERNANCE corpus defect: an infographic
    caption PARAGRAPH block, "Combined assurance approach\nStrong Lead
    Independent Director...", opens with the configured heading's exact
    words before continuing into unrelated board-composition content on the
    same line (no line break between "assurance" and "approach"). It sat
    earlier in reading order than the real, standalone "Combined assurance"
    HEADING_CANDIDATE section further into the range and won outright under
    the old ranking. The guard must reject it so the real section resolves."""
    blocks = [
        _block(88, 0, "Combined assurance approach\nStrong Lead Independent Director oversight."),
        _block(107, 0, "Combined assurance", BlockType.HEADING_CANDIDATE),
        _block(
            107, 1,
            "Our combined assurance framework is supported by the three lines of defence model "
            "that specifies and delegates accountability for managing risks across the Group.",
        ),
        _block(108, 0, "Risk governance", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, COMBINED_ASSURANCE_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.start_page == 107
    assert result.source_heading == "Combined assurance"
    assert "Strong Lead Independent Director" not in result.source_text
    assert "three lines of defence model" in result.source_text


def test_run_in_heading_still_works_when_no_stronger_candidate_exists():
    """A legitimate run-in match must still resolve when it is the only
    candidate at all -- the guard must not reject every run-in match
    unconditionally, only ones that read as mid-sentence prose."""
    blocks = [
        _block(37, 0, "Gross Margin The gross margin is dependent on the product mix. The margin was "
               "18,7% compared with 19,7% in the prior year."),
        _block(38, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, NEXT_HEADING_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_heading == "Gross Margin"


def test_anchor_sentence_boundary_unaffected_by_prose_continuation_guard():
    """ANCHOR_SENTENCE resolution is downstream of start-heading selection;
    once a genuine start heading is found the guard has no further effect
    on how the anchor pattern locates the end boundary."""
    blocks = [
        _block(
            39, 0,
            "Gross Margin The gross margin is dependent on the product and geographic mix of sales, market "
            "conditions and exchange rates. The average gross margin for the year was 18,4% compared with "
            "18,5% in the prior year.",
        ),
        _block(40, 0, "Financial position", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, ANCHOR_CONFIG)

    assert result is not None
    assert result.boundary_status == SemanticUnitBoundaryStatus.RESOLVED
    assert result.source_heading == "Gross Margin"
    assert result.source_text.endswith("in the prior year.")


def test_heading_variation_word_order_tolerance_still_intact():
    """Word-order-tolerant matching for a genuine heading-extraction
    artifact (not prose) must be unaffected by the run-in prose guard,
    which only ever applies to PARAGRAPH run-in candidates."""
    matched, exact = sue._matches_heading("GOVERNANCE Remuneration", "Remuneration governance")
    assert matched is True
    assert exact is False


def test_earliest_reading_order_still_wins_among_equal_evidence_quality():
    """Two genuine, equally-exact HEADING_CANDIDATE matches (no run-in
    involved) must still resolve to the earliest one in reading order."""
    blocks = [
        _block(120, 0, "Combined assurance", BlockType.HEADING_CANDIDATE),
        _block(120, 1, "First occurrence content."),
        _block(121, 0, "Risk governance", BlockType.HEADING_CANDIDATE),
    ]
    result = sue.extract_unit(blocks, COMBINED_ASSURANCE_CONFIG)

    assert result is not None
    assert result.start_page == 120
    assert "First occurrence content." in result.source_text

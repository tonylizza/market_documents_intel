"""Pure-algorithm tests for `services.semantic_unit_alignment` (Track 7C.2).

No database access -- `align_units` takes plain `UnitCandidate` values and
returns plain `AlignmentDecision` values, mirroring
`test_semantic_unit_extraction.py`'s "Pure-algorithm fixtures (no DB)"
pattern.
"""

import uuid

from market_documents.models.enums import AlignmentConfidence, SemanticUnitAlignmentStatus, SemanticUnitBoundaryStatus
from market_documents.services import semantic_unit_alignment as sua


def _resolved(unit_key: str, heading: str) -> sua.UnitCandidate:
    return sua.UnitCandidate(
        id=uuid.uuid4(), unit_key=unit_key, source_heading=heading, boundary_status=SemanticUnitBoundaryStatus.RESOLVED
    )


def _unresolved(unit_key: str, heading: str) -> sua.UnitCandidate:
    return sua.UnitCandidate(
        id=uuid.uuid4(), unit_key=unit_key, source_heading=heading,
        boundary_status=SemanticUnitBoundaryStatus.UNRESOLVED,
    )


def test_exact_unit_key_match_is_matched_high_confidence():
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later = [_resolved("gross_margin", "Gross Margin")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.MATCHED
    assert decision.confidence == AlignmentConfidence.HIGH
    assert decision.earlier_unit_id == earlier[0].id
    assert decision.later_unit_id == later[0].id
    assert "gross_margin" in decision.evidence


def test_earlier_only_with_clean_later_run_is_removed():
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later: list[sua.UnitCandidate] = []

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.REMOVED
    assert decision.confidence == AlignmentConfidence.HIGH
    assert decision.earlier_unit_id == earlier[0].id
    assert decision.later_unit_id is None


def test_later_only_with_clean_earlier_run_is_added():
    earlier: list[sua.UnitCandidate] = []
    later = [_resolved("cfo_conclusion", "In conclusion")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.ADDED
    assert decision.confidence == AlignmentConfidence.HIGH
    assert decision.later_unit_id == later[0].id
    assert decision.earlier_unit_id is None


def test_normalized_heading_variation_still_aligns():
    """Numbering prefix + punctuation + case differ, unit_key differs too --
    only the normalized heading ties them together."""
    earlier = [_resolved("results_commentary", "6.5 Commentary on the 2023 Financial Results")]
    later = [_resolved("financial_results_commentary", "commentary on the 2023 financial results.")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.MATCHED
    assert decision.confidence == AlignmentConfidence.MEDIUM
    assert decision.earlier_unit_id == earlier[0].id
    assert decision.later_unit_id == later[0].id


def test_normalized_heading_match_with_different_unit_key_is_matched_medium_confidence():
    """RENAMED is a declared but currently-unsupported status (see
    `SemanticUnitAlignmentStatus`'s docstring) -- distinguishing a genuine
    heading rename from cosmetic normalization noise would need evidence
    beyond this deterministic cascade, so a unique normalized-heading match
    is always MATCHED, just at lower confidence than an exact unit_key
    match."""
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later = [_resolved("margin_review", "Gross margin!")]  # different unit_key, normalizes equal

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    assert decisions[0].status == SemanticUnitAlignmentStatus.MATCHED
    assert decisions[0].confidence == AlignmentConfidence.MEDIUM


def test_ambiguous_multiple_candidates_are_not_guessed():
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later = [
        _resolved("margin_a", "Gross Margin"),
        _resolved("margin_b", "Gross Margin"),
    ]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.AMBIGUOUS
    assert decision.confidence == AlignmentConfidence.NEEDS_REVIEW
    assert decision.later_unit_id is None


def test_unresolved_upstream_extraction_does_not_become_false_removed():
    """The BEL 2020 gross_margin case: the later run completed WITH
    warnings and has no row at all for this unit_key -- must not be
    silently converted into a REMOVED disclosure event."""
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later: list[sua.UnitCandidate] = []

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=False)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM
    assert decision.confidence == AlignmentConfidence.NEEDS_REVIEW
    assert decision.earlier_unit_id == earlier[0].id
    assert decision.later_unit_id is None


def test_unresolved_upstream_extraction_does_not_become_false_added():
    earlier: list[sua.UnitCandidate] = []
    later = [_resolved("cfo_conclusion", "In conclusion")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=False, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM
    assert decision.later_unit_id == later[0].id
    assert decision.earlier_unit_id is None


def test_unresolved_boundary_status_row_is_unresolved_upstream_not_removed():
    """A unit whose boundary never resolved (row exists, but no source
    text) must not be treated as absent."""
    earlier = [_resolved("gross_margin", "Gross Margin")]
    later = [_unresolved("gross_margin", "Gross Margin")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    assert len(decisions) == 1
    decision = decisions[0]
    assert decision.status == SemanticUnitAlignmentStatus.UNRESOLVED_UPSTREAM
    assert decision.earlier_unit_id == earlier[0].id
    assert decision.later_unit_id == later[0].id


def test_no_units_on_either_side_produces_no_decisions():
    decisions = sua.align_units([], [], earlier_run_clean=True, later_run_clean=True)
    assert decisions == []


def test_matched_and_removed_can_coexist_in_one_run():
    """ACT-shaped: cfo_conclusion matches cleanly while a hypothetical
    second unit genuinely disappears in a cleanly-completed later run."""
    earlier = [_resolved("cfo_conclusion", "In conclusion"), _resolved("capital_management", "Capital management")]
    later = [_resolved("cfo_conclusion", "In conclusion")]

    decisions = sua.align_units(earlier, later, earlier_run_clean=True, later_run_clean=True)

    by_key = {d.earlier_unit_id: d for d in decisions}
    matched = next(d for d in decisions if d.status == SemanticUnitAlignmentStatus.MATCHED)
    removed = next(d for d in decisions if d.status == SemanticUnitAlignmentStatus.REMOVED)
    assert matched.earlier_unit_id == earlier[0].id
    assert removed.earlier_unit_id == earlier[1].id
    assert len(by_key) == 2

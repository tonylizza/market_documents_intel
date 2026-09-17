"""Per-`unit_key` boundary definitions for HEADED_NARRATIVE_UNIT extraction.

Track 7C.1 (docs/7c1-schedule-localization-plan.md). Each `UnitConfig`
names a start heading to match within a schedule instance's page range, and
a boundary strategy for finding the unit's end: `NEXT_HEADING` (the next
heading-candidate block after the start) or `ANCHOR_SENTENCE` (a stable
recurring phrase, matched with a whitespace-tolerant regex so a PDF
line-wrap mid-phrase -- e.g. BEL 2022's "...in the prior \\nyear." -- does
not break the match).

BEL and ACT are not required to use the same `unit_key` (see the plan's
Section 6.1/6.3) -- each names a genuine recurring headed narrative
subsection inside its own FINANCIAL_PERFORMANCE schedule, not a forced
cross-company equivalent concept.
"""

import hashlib
import json
import re
from dataclasses import dataclass

from market_documents.models.enums import NormalizedSchedule, SemanticUnitBoundaryStrategy

# v1.0.0 = initial two-unit configuration (BEL gross_margin, ACT results_overview).
# v1.1.0 = replaced the unverified ACT_RESULTS_OVERVIEW placeholder (its
# "Results overview" heading never appeared in the real ACT corpus) with
# ACT_CFO_CONCLUSION, verified against the actual ACT PDFs during the 7C.1
# real-corpus acceptance run (docs/implementation/track-7c1-acceptance.md).
# v1.2.0 = Track 7D.1: broadened BEL_GROSS_MARGIN's closing-anchor clause
# from the single literal "in the prior year" to a configurable set of
# generic year-reference variants (docs/7d1-known-recall-defect-remediation.md)
# -- BEL 2017's real closing sentence names the comparison year directly
# ("...for 2016.") instead of saying "the prior year", and the old pattern
# never generalized to that phrasing.
CONFIG_VERSION = "1.2.0"

# A trailing clause that names the prior-year comparison a closing sentence
# is making, in any of the generic phrasings observed across the corpus
# (recurring-year-comparison wording, not any one issuer's or year's exact
# sentence). Shared so any future ANCHOR_SENTENCE unit can reuse it instead
# of re-deriving its own variant list.
_YEAR_REFERENCE_CLAUSE = (
    r"(?:"
    r"in\s+the\s+prior\s+year"
    r"|in\s+the\s+previous\s+year"
    r"|compared\s+with\s+\d{4}"
    r"|compared\s+to\s+\d{4}"
    r"|versus\s+\d{4}"
    r"|vs\.?\s+\d{4}"
    r"|for\s+\d{4}"
    r")"
)


@dataclass(frozen=True)
class UnitConfig:
    unit_key: str
    schedule: NormalizedSchedule
    ticker: str
    start_heading: str
    boundary_strategy: SemanticUnitBoundaryStrategy
    # Whitespace-tolerant (each `\s+` matches across a PDF line-wrap),
    # case-insensitive. Required when boundary_strategy is ANCHOR_SENTENCE.
    anchor_pattern: re.Pattern | None = None


# BEL's "Gross Margin" unit inside the Finance director's report --
# directly validated in docs/experiments/annual-report-bel-compact-validation.md
# Section 3. NEXT_HEADING alone was shown to fail on the 2019 report (a bar
# chart's axis labels/percentages sit between the paragraph and the next
# heading, "Other operating income"); the recurring closing sentence
# ("...compared with X% <year-reference clause>.") is the load-bearing
# anchor. The year-reference clause itself varies by year -- most years say
# "...in the prior year.", but 2017 instead says "...for 2016.", naming the
# comparison year directly (see `_YEAR_REFERENCE_CLAUSE`) -- so the pattern
# accepts any of that shared, generic set of phrasings rather than one
# literal sentence.
BEL_GROSS_MARGIN = UnitConfig(
    unit_key="gross_margin",
    schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
    ticker="BEL",
    start_heading="Gross Margin",
    boundary_strategy=SemanticUnitBoundaryStrategy.ANCHOR_SENTENCE,
    anchor_pattern=re.compile(
        rf"compared\s+with\s+[\d.,]+\s*%\s+{_YEAR_REFERENCE_CLAUSE}\.", re.IGNORECASE
    ),
)

# ACT's headed-narrative unit inside its CFO's review, validating that the
# same HEADED_NARRATIVE_UNIT mechanism generalizes to a second issuer
# without requiring the same underlying financial concept as BEL's (plan
# Section 6.3/6.4). "In conclusion" is the CFO letter's closing subsection --
# confirmed present, verbatim, and heading-anchored in the real ACT 2019 and
# 2021 PDFs (7C.1 real-corpus acceptance run,
# docs/implementation/track-7c1-acceptance.md), each time followed by 3-4
# prose paragraphs and ending cleanly at the "Hannes Boonzaaier" signature
# heading -- no table/chart content intervenes in either year, so
# NEXT_HEADING is a safe boundary strategy here (unlike a naive NEXT_HEADING
# on BEL's Gross Margin). Not present in every ACT year (report format
# changed after the 2022 governance redesign the compact-validation
# experiment documents), which is fine: the acceptance criterion only
# requires recurrence across at least two years, not universal presence.
ACT_CFO_CONCLUSION = UnitConfig(
    unit_key="cfo_conclusion",
    schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
    ticker="ACT",
    start_heading="In conclusion",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

UNIT_CONFIGS: tuple[UnitConfig, ...] = (BEL_GROSS_MARGIN, ACT_CFO_CONCLUSION)


def unit_configs_for(ticker: str, schedule: NormalizedSchedule) -> tuple[UnitConfig, ...]:
    return tuple(c for c in UNIT_CONFIGS if c.ticker == ticker and c.schedule == schedule)


def compute_configuration_hash(configs: tuple[UnitConfig, ...] = UNIT_CONFIGS) -> str:
    """Deterministic fingerprint of the unit-definition configuration in
    effect, so adding/changing a UnitConfig forces a fresh
    `SemanticUnitRun` instead of a stale skip."""
    payload = {
        "config_version": CONFIG_VERSION,
        "units": [
            {
                "unit_key": c.unit_key,
                "schedule": c.schedule.value,
                "ticker": c.ticker,
                "start_heading": c.start_heading,
                "boundary_strategy": c.boundary_strategy.value,
                "anchor_pattern": c.anchor_pattern.pattern if c.anchor_pattern else None,
            }
            for c in configs
        ],
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

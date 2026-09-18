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
# v1.3.0 = Track 7D.2 (docs/7d2-financial-performance-unit-expansion.md):
# added ACT_HEALTHCARE_SERVICES_REVIEW ("Healthcare Services Financial
# Performance", NEXT_HEADING, resolved 2021-2023, giving two genuinely
# adjacent ReportPairs). A second candidate, ACT "Capital management", was
# evaluated and rejected -- its 2024 occurrence exposed a pre-existing
# generic false-positive substring-match defect in
# `semantic_unit_extraction._matches_heading` (an unrelated decorative
# pull-quote heading fragment earlier in the same report, "...driven by
# prudent capital management policies...", contains "capital management" as
# a bare substring and matches first), and this milestone's one-bounded-
# generic-parser-correction budget was already spent on the NEXT_HEADING
# continuation-banner gap below. Without that second fix, "Capital
# management" only safely resolves in one year (2021), failing the
# recurring-across-multiple-years selection criterion -- see the milestone
# doc's rejected-candidates section. No BEL unit added this track -- BEL's
# real corpus has no further recurring section whose narrative is bounded by
# a standalone heading-candidate after 2018 (every later subsection heading
# is fused run-in onto its own paragraph with no standalone heading
# following it before the next section, which NEXT_HEADING cannot bound
# without a bespoke ANCHOR_SENTENCE calibration per unit -- deferred, see
# the milestone doc's rejected-candidates section).
# v1.4.0 = Track 7D.3 (docs/7d3-corporate-governance-expansion.md): first
# CORPORATE_GOVERNANCE units, added to prove the existing architecture
# generalizes past FINANCIAL_PERFORMANCE. ACT_INFORMATION_SECURITY_GOVERNANCE
# ("Information and security governance", NEXT_HEADING) recurs 2016,
# 2018-2024 -- consistently a short, clean, standalone narrative subsection
# ending at a genuine next heading every year checked (2016's "GOVERNANCE
# OUTLOOK", 2022's page-banner "The Board of Directors continued", 2024's
# "TAX TRANSPARENCY"). ACT_GOVERNANCE_POLICIES_PROCESSES ("Governance
# policies, procedures and processes", NEXT_HEADING) recurs 2018-2024,
# bounded by "Ethical behaviour" every year checked. ACT_COMBINED_ASSURANCE
# ("Combined assurance", NEXT_HEADING) recurs 2018, 2020-2024, a short
# framework-introduction narrative bounded by the "FIRST/SECOND/THIRD LINE
# OF DEFENCE" diagram labels -- but see its own KNOWN DEFECT note below:
# 2022/2023 resolve to the wrong content. BEL_BOARD_COMPOSITION_DIVERSITY
# ("Board composition and diversity", NEXT_HEADING) recurs 2018-2021; unlike
# the other three, its content is a demographic composition table, not
# prose -- routed STRUCTURED_COMPARISON_PREFERRED, not LEXICAL_ONLY (see
# docs/7d3-corporate-governance-expansion.md Section 9). No new boundary
# strategy was needed for any of the four.
CONFIG_VERSION = "1.4.0"

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

# ACT's "Healthcare Services Financial Performance" subsection -- a
# recurring narrative review of the Medscheme/medical-scheme-administration
# cluster's operating performance, confirmed present in the real ACT 2021,
# 2022, and 2023 PDFs (Track 7D.2 real-corpus inventory), with the
# 2021-2022-2023 span giving two genuinely adjacent ReportPairs for
# alignment/lexical comparison (2021->2022 and 2022->2023). 2022's and 2023's
# narrative is fully captured by NEXT_HEADING (each page's trailing
# "continued"/numeric-table content is independently classified
# excluded_from_narrative, so the boundary lands cleanly on the next
# genuine heading-candidate, "Operating margin" in 2022 and "Five-year
# summary of Profit before tax" in 2023). 2021 is the one year where the
# immediately following page-banner heading-candidate ("CFO's review
# continued") is not itself excluded from narrative, which is exactly the
# generic NEXT_HEADING-vs-continuation-banner gap this track's one bounded
# parser fix addresses (see semantic_unit_extraction.py ALGORITHM_VERSION
# 1.2.0) -- without that fix, 2021 would under-recover a real continuation
# paragraph that resumes on the following page before the next genuine
# heading.
ACT_HEALTHCARE_SERVICES_REVIEW = UnitConfig(
    unit_key="healthcare_services_review",
    schedule=NormalizedSchedule.FINANCIAL_PERFORMANCE,
    ticker="ACT",
    start_heading="Healthcare Services Financial Performance",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

# Track 7D.3 (docs/7d3-corporate-governance-expansion.md): first
# CORPORATE_GOVERNANCE units. ACT's "Information and security governance"
# subsection -- confirmed present, verbatim, in the real ACT 2016, 2018,
# 2019, 2020, 2021, 2022, 2023, and 2024 PDFs (7D.3 real-corpus inventory),
# each time 3-4 short paragraphs ending cleanly at a genuine next heading
# ("GOVERNANCE OUTLOOK" in 2016, the page-banner "The Board of Directors
# continued" in 2022 -- already excluded by the existing generic
# boilerplate-repeat handling, "TAX TRANSPARENCY" in 2024). Not present in
# 2017 (that year's report restructured the whole governance section around
# a running "GOVERNANCE" page banner with no matching standalone heading --
# GENUINE_ABSENCE, not an extraction defect; see the milestone doc's
# extraction-coverage table).
ACT_INFORMATION_SECURITY_GOVERNANCE = UnitConfig(
    unit_key="information_security_governance",
    schedule=NormalizedSchedule.CORPORATE_GOVERNANCE,
    ticker="ACT",
    start_heading="Information and security governance",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

# ACT's "Governance policies, procedures and processes" subsection --
# confirmed present in the real ACT 2018-2024 PDFs, each time a compliance-
# focused narrative (group compliance universe, POPIA, ESG incidents) ending
# cleanly at the next genuine heading, "Ethical behaviour", every year
# checked (2022, 2024).
ACT_GOVERNANCE_POLICIES_PROCESSES = UnitConfig(
    unit_key="governance_policies_processes",
    schedule=NormalizedSchedule.CORPORATE_GOVERNANCE,
    ticker="ACT",
    start_heading="Governance policies, procedures and processes",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

# ACT's "Combined assurance" subsection -- confirmed present in the real ACT
# 2018, 2020-2024 PDFs, a short (2-paragraph) narrative introducing the
# three-lines-of-defence framework, ending cleanly at the "FIRST/SECOND/
# THIRD LINE OF DEFENCE" diagram-label headings in 2020, 2021, and 2024.
# KNOWN DEFECT, deliberately left unfixed (see
# docs/7d3-corporate-governance-expansion.md Sections 12/15/18): in 2022 and
# 2023, an earlier, unrelated governance-practices overview/infographic
# heading-candidate ("Combined Assurance Approach\nStrong Lead Independent
# Director...") wins the start-heading match instead of the real section --
# the same false-positive-substring-match defect class Track 7D.2 already
# documented and deliberately left unfixed for ACT "Capital management".
# This unit is therefore NOT_READY_FOR_CUTOVER despite being configured and
# resolving a boundary in every attempted year.
ACT_COMBINED_ASSURANCE = UnitConfig(
    unit_key="combined_assurance",
    schedule=NormalizedSchedule.CORPORATE_GOVERNANCE,
    ticker="ACT",
    start_heading="Combined assurance",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

# BEL's "Board composition and diversity" subsection -- confirmed present in
# the real BEL 2018-2021 PDFs. Unlike the three ACT units above, its content
# is a demographic composition table (director designation/age/gender/race),
# not narrative prose -- Track 7D.3 routes it PRESENCE_STATUS_ONLY rather
# than LEXICAL_ONLY (docs/7d3-corporate-governance-expansion.md Section 9),
# same as every other STRUCTURED_COMPARISON_PREFERRED/PRESENCE_STATUS_ONLY
# unit: extraction and boundary resolution still run, but no lexical
# comparison is computed. Included specifically to give CORPORATE_GOVERNANCE
# at least one BEL unit, proving the schedule (not just its units) localizes
# for both issuers.
BEL_BOARD_COMPOSITION_DIVERSITY = UnitConfig(
    unit_key="board_composition_diversity",
    schedule=NormalizedSchedule.CORPORATE_GOVERNANCE,
    ticker="BEL",
    start_heading="Board composition and diversity",
    boundary_strategy=SemanticUnitBoundaryStrategy.NEXT_HEADING,
    anchor_pattern=None,
)

UNIT_CONFIGS: tuple[UnitConfig, ...] = (
    BEL_GROSS_MARGIN,
    ACT_CFO_CONCLUSION,
    ACT_HEALTHCARE_SERVICES_REVIEW,
    ACT_INFORMATION_SECURITY_GOVERNANCE,
    ACT_GOVERNANCE_POLICIES_PROCESSES,
    ACT_COMBINED_ASSURANCE,
    BEL_BOARD_COMPOSITION_DIVERSITY,
)


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

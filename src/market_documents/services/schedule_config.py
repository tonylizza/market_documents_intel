"""Centralized, versioned schedule-localization configuration.

Track 7C.1 (docs/7c1-schedule-localization-plan.md): mirrors
`passage_config.py`'s pattern -- an `ALGORITHM_VERSION` plus a
`compute_configuration_hash()` fingerprint, so a change to the heading
vocabulary or matching rules forces a fresh `ScheduleLocalizationRun`
instead of silently reusing a stale one.

7C.1 implements exactly one schedule, FINANCIAL_PERFORMANCE. The heading
vocabulary below is drawn directly from
`docs/experiments/annual-report-schedule-localization.md` (BEL 2021's
"Finance director's report", ACT 2022's "CFO'S REVIEW") plus generic
variants observed across the corpus's other companies for that same
schedule, so the deterministic matcher recognizes the concept without
requiring per-company configuration. `NormalizedSchedule` names the full
ten-schedule taxonomy for future milestones; only `FINANCIAL_PERFORMANCE`
has an entry in `SCHEDULE_HEADING_VOCABULARY` today.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, field

from market_documents.models.enums import NormalizedSchedule

# v1.0.0 = initial deterministic heading-vocabulary matcher, FINANCIAL_PERFORMANCE only.
# v1.0.1 = normalize typographic quotes/apostrophes (U+2018/2019/201C/201D) to ASCII
# before matching -- real BEL/ACT PDF text uses curly apostrophes ("Finance
# director's report") while the configured vocabulary used straight ones, so every
# BEL year failed to match until this normalization was added (7C.1 real-corpus
# acceptance run, docs/implementation/track-7c1-acceptance.md).
# v1.0.2 = a span's end boundary only advances past a heading-candidate on a
# strictly later page -- a same-page trailing heading-candidate (e.g. a
# "salient features" sidebar's numeric callouts) is not a section boundary
# and must not truncate a multi-page schedule to one page (same acceptance
# run).
# v1.0.3 = ignore heading-candidates that recur 3+ times anywhere in the
# document (running section banners like BEL's "PERFORMANCE REVIEW",
# misclassified as HEADING_CANDIDATE by the frozen upstream pipeline) when
# computing a span's end boundary -- otherwise the very next page's repeated
# banner falsely ends the schedule one page early (same acceptance run).
# v1.0.4 = a "<heading> continued" candidate is the same section resuming,
# not a new section -- it must not end the span either (same acceptance
# run).
# v1.1.0 = Track 7C.1b (docs/7c1b-canonical-hierarchy-integration.md):
# hierarchy-aware boundary termination -- a later heading-candidate only
# ends a span if `heading_structure.assess_heading_structure` finds it
# plausibly top-level (document-relative font-size tiering, paired/grouped
# labels, table-of-contents pattern), so an internal subsection heading or
# chart title no longer truncates its parent schedule. Also prefers the
# Track 7C.1a canonical source over legacy TextBlock when a report has a
# current successful CanonicalExtractionRun.
# v1.2.0 = Track 7D.1 (docs/7d1-known-recall-defect-remediation.md):
# `_matches_vocabulary` also matches a heading whose words contain every
# word of a vocabulary phrase in any order (real corpus text extraction can
# reorder a heading's words relative to its visual layout), and the primary
# span is chosen by strongest evidence (exact match, then structural
# top-level assessment, then page order) instead of simply the earliest
# page a vocabulary match happens to occur on -- a real section's own
# heading can be preceded by an unrelated, coincidental substring/word-set
# match many pages earlier.
# v1.3.0 = Track 7D.3 (docs/7d3-corporate-governance-expansion.md): added
# CORPORATE_GOVERNANCE vocabulary. Both BEL ("Corporate governance report" /
# "corporate governance report") and ACT ("CORPORATE GOVERNANCE REPORT" /
# "Corporate governance review") name the schedule directly every year in
# the real corpus (2016-2022 BEL, 2016-2024 ACT) -- no new matching rule was
# needed, only new vocabulary strings.
# v1.3.1 = 7D.3's corpus-wide scope amendment: added "CORPORATE GOVERNANCE
# REPORT" is already shared with ACT/BEL and matched KP2 as-is (real corpus,
# 2020-2025); added "Governance and functions of the Board" for SBP (real
# corpus, 2023-2025). Pure vocabulary addition, no matching-logic change --
# does not draw on the milestone's one-generic-correction parser budget.
# v1.4.0 = Track 7D.4 (docs/7d4-corpus-wide-remuneration-expansion.md): added
# REMUNERATION vocabulary. "Remuneration Committee Report" covers ACT
# 2016-2017 and BEL 2016-2022; "Remuneration Report" covers ACT 2018-2024,
# SUR 2023-2025, and SDL 2024-2025 ("REMUNERATION REPORT (AUDITED)", still a
# substring match). Pure vocabulary addition -- no matching-logic change,
# does not draw on this milestone's one-generic-correction parser budget.
# v1.5.0 = Track 7D.5 (docs/7d5-corpus-wide-material-risks-expansion.md):
# added MATERIAL_RISKS vocabulary, real-corpus inventoried across all 6
# tickers (see the milestone doc's schedule-inventory section). Deliberately
# excludes "Risk management", "Enterprise Risk Management", "Audit and Risk
# Committee", and similar HOW-risk-is-governed headings -- those name risk
# oversight/governance, not the material-risk disclosure itself (the
# milestone's own Section 2 distinction), and were confirmed in the real
# corpus to belong to CORPORATE_GOVERNANCE-adjacent content, not this
# schedule. Pure vocabulary addition -- no matching-logic change, does not
# draw on this milestone's one-generic-correction parser budget.
ALGORITHM_VERSION = "1.5.0"

HEADING_VOCABULARY_VERSION = 5

# Canonical heading strings per schedule, matched case-insensitively as a
# substring of a HEADING_CANDIDATE block's text (see
# `schedule_localization.py`). Order is not significant -- every configured
# string is checked for every heading-candidate block.
SCHEDULE_HEADING_VOCABULARY: dict[NormalizedSchedule, tuple[str, ...]] = {
    NormalizedSchedule.FINANCIAL_PERFORMANCE: (
        "Finance director's report",
        "Finance Director's Report",
        "CFO's review",
        "CFO'S REVIEW",
        "CFO's report",
        "Financial performance",
        "Financial Performance",
        "Financial review",
        "Financial Review",
    ),
    # Real-corpus heading strings confirmed via docs/7d3-corporate-governance-
    # expansion.md Section 1's inventory (BEL 2016-2022, ACT 2016-2024). Both
    # issuers' "(continued)"/"CONTINUED" running banners are already handled
    # generically by the existing boilerplate-repeat and hierarchy-aware
    # boundary logic below, not by this vocabulary.
    NormalizedSchedule.CORPORATE_GOVERNANCE: (
        "Corporate governance report",
        "CORPORATE GOVERNANCE REPORT",
        "Corporate governance review",
        "CORPORATE GOVERNANCE REVIEW",
        "Governance and functions of the Board",
    ),
    # Real-corpus heading strings confirmed via docs/7d4-corpus-wide-
    # remuneration-expansion.md Section 1's inventory (ACT 2016-2024, BEL
    # 2016-2022, SUR 2023-2025, SDL 2024-2025). "Remuneration report" is a
    # substring match, not exact, so a KP2/SDL "(CONT)"/"(AUDITED)" suffix or
    # SUR's "REMUNERATION REPORTING AND ENGAGEMENT" (which literally contains
    # "remuneration report" as its own substring) still match -- the existing
    # exact-match-first primary-selection rule (v1.2.0) resolves that
    # ambiguity in every issuer checked, since the genuine standalone
    # "Remuneration report" heading is present, exact, and preferred as
    # primary wherever both occur (see the milestone doc's localization
    # section for per-issuer confirmation).
    NormalizedSchedule.REMUNERATION: (
        "Remuneration committee report",
        "REMUNERATION COMMITTEE REPORT",
        "Remuneration report",
        "REMUNERATION REPORT",
    ),
    # Real-corpus heading strings confirmed via docs/7d5-corpus-wide-
    # material-risks-expansion.md's schedule-inventory section (ACT 2016,
    # 2018, 2022-2024, BEL 2018-2022, SUR 2023-2025). Deliberately does NOT
    # include "Risk management", "Enterprise Risk Management", "Audit and
    # Risk Committee" -- those describe HOW risk is governed, not WHAT the
    # material risks are, and were confirmed in the real corpus to belong to
    # risk-governance content, not this schedule (see the milestone doc's
    # Section 2 distinction). Deliberately does NOT include the bare phrase
    # "Risks and opportunities" either -- real-corpus inspection found ACT's
    # own value-creation-model overview page (present nearly every year)
    # carries a small "RISKS AND \nOPPORTUNITIES" navigational label as one
    # of several cross-reference callouts, which exact-matched and won
    # primary over the real, much longer risk chapter in years lacking a
    # more specific "...top risks"/"...risks and opportunities" chapter
    # title (2017, 2020, 2021) -- a real, confirmed vocabulary-breadth
    # false-positive risk (see the milestone doc's Section 19 safety
    # review). Narrowing the vocabulary to the specific chapter-title
    # phrases below (never matching the generic navigational label) avoids
    # it without any matching-logic change.
    NormalizedSchedule.MATERIAL_RISKS: (
        "Material risks and opportunities",
        "MATERIAL RISKS AND OPPORTUNITIES",
        "Key risks and opportunities",
        "KEY RISKS AND OPPORTUNITIES",
        "Overview of our top risks",
        "OVERVIEW OF OUR TOP RISKS",
        "Strategic overview and risk management",
        "Social and economic risks facing South Africa",
        "SOCIAL AND ECONOMIC RISKS FACING SOUTH AFRICA",
    ),
}


@dataclass(frozen=True)
class ScheduleConfig:
    heading_vocabulary: dict[NormalizedSchedule, tuple[str, ...]] = field(
        default_factory=lambda: SCHEDULE_HEADING_VOCABULARY
    )


SCHEDULE_CONFIG = ScheduleConfig()


def compute_configuration_hash(config: ScheduleConfig = SCHEDULE_CONFIG) -> str:
    """Deterministic fingerprint of everything that can change localization output."""
    payload = {
        "algorithm_version": ALGORITHM_VERSION,
        "heading_vocabulary_version": HEADING_VOCABULARY_VERSION,
        "heading_vocabulary": {
            schedule.value: list(headings) for schedule, headings in config.heading_vocabulary.items()
        },
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

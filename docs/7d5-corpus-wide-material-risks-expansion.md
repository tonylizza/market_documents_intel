# Track 7D.5: Corpus-Wide Material Risks Expansion

## 0. Scope note

This track evaluates the normalized `MATERIAL_RISKS` schedule corpus-wide,
across every company currently in the corpus (ACT, BEL, KP2, SBP, SDL, SUR)
and every available report year, following the same corpus-wide-from-the-
start pattern Tracks 7D.3/7D.4 established. No production database change
was made; no schedule other than MATERIAL_RISKS was touched; production
remains on the existing stable publication; `cutover_config.py` was not
touched. Unlike 7D.3/7D.4, this track configured **zero** narrative
semantic units -- a deliberate, evidence-based outcome, not an oversight
(see Sections 4-8 and 21).

## 1. Corpus / company inventory

Same six issuers and report-year counts as Tracks 7D.3/7D.4's audits, no
others added:

| ticker | report years |
|---|---|
| ACT | 9 (2016-2024) |
| BEL | 7 (2016-2022) |
| KP2 | 6 (2020-2025) |
| SBP | 3 (2023-2025) |
| SDL | 2 (2024-2025) |
| SUR | 3 (2023-2025) |

Total: 30 report years.

A real-corpus heading inventory was run first, independent of any
localization code, by scanning every `HEADING_CANDIDATE` block containing
the word "risk" across all 30 report years directly against the canonical
source (or legacy TextBlock where no canonical extraction exists). This
inventory (not the localization algorithm) is what identified every
candidate vocabulary phrase below and every risk-governance phrase to
deliberately exclude.

## 2. Distinguishing Material Risks from risk governance

Confirmed in the real corpus, consistent with the milestone's own caution:
every issuer's real-corpus heading inventory contains substantial risk-
*governance* content -- "Audit and Risk Committee" (ACT, KP2, SBP, all
years), "Enterprise Risk Management"/"AfroCentric risk management" (ACT
2018, 2021-2024), "Risk and Sustainability Committee" (BEL, all years),
"Approach to risk management"/"Risk framework and the governance of risk"
(SBP, numbered subsections 10.1/10.2), "Risk committee" (SUR, all years),
"G4 Compliance and risk management" (SUR). None of this was folded into
`MATERIAL_RISKS` vocabulary or treated as a `MATERIAL_RISKS` candidate --
it describes HOW risk is governed/overseen, not WHAT the material risks
are, matching the milestone's Section 2 distinction. `SCHEDULE_HEADING_
VOCABULARY[MATERIAL_RISKS]` and its own module comment name this exclusion
explicitly, and `tests/test_material_risks_expansion.py::
test_material_risks_vocabulary_excludes_risk_governance_phrases` guards it.

No existing `CORPORATE_GOVERNANCE`/`REMUNERATION` unit was moved or
reclassified.

## 3. Schedule localization results

`schedule_localization.localize_schedule`'s scope guard was extended to
accept `NormalizedSchedule.MATERIAL_RISKS` (previously `NotImplementedError`)
-- a scope-guard change only, exactly mirroring 7D.3's/7D.4's own pattern.
Heading vocabulary added (pure config, `ALGORITHM_VERSION` 1.4.0 -> 1.5.0,
`HEADING_VOCABULARY_VERSION` 4 -> 5):

- `"Material risks and opportunities"` (ACT 2016)
- `"Key risks and opportunities"` (ACT 2018)
- `"Overview of our top risks"` (ACT 2022-2024)
- `"Strategic overview and risk management"` (BEL 2018-2022)
- `"Social and economic risks facing South Africa"` (SUR 2023-2025)

**A real vocabulary-breadth false positive was found and fixed during this
track**, entirely by narrowing the configured vocabulary (no matching-logic
change, so this does not draw on the milestone's one-bounded-generic-
correction budget): the bare phrase `"Risks and opportunities"` was
initially configured (by analogy with the confirmed genuine "Material/Key
risks and opportunities" chapter titles), but real-corpus inspection showed
ACT's own value-creation-model overview page (present most years, often as
page 4 or 8) carries a short `"RISKS AND \nOPPORTUNITIES"` navigational
cross-reference label among several similar labels (`"EXTERNAL \n
ENVIRONMENT"`, `"STAKEHOLDER \nRELATIONSHIPS"`, `"MATERIAL \nMATTERS"`) --
an exact match that won primary selection over the real, much longer risk
chapter in every year lacking its own more specific chapter title (2017,
2020, 2021), and in 2024 won primary over the real chapter even though the
real chapter's heading *also* matched as a supporting span that year.
Removing the bare phrase and keeping only the specific, real chapter-title
strings above resolved this cleanly: 2017/2020/2021 correctly became
`NOT_FOUND` (no bounded chapter exists those years -- the risk content is
dispersed across the broader "Material matters" narrative instead, not a
standalone schedule), and 2024 correctly re-anchored on the real chapter
heading. `tests/test_schedule_localization.py::
test_material_risks_generic_navigational_label_is_not_configured_vocabulary`
and `::test_material_risks_real_chapter_wins_over_navigational_label_when_
both_present` regression-test this.

| ticker | year | status | primary span | heading | notes |
|---|---|---|---|---|---|
| ACT | 2016 | RESOLVED | 49-51 | "MATERIAL RISKS AND OPPORTUNITIES" | materiality-matrix table, see Section 4 |
| ACT | 2017 | GENUINE_ABSENCE | -- | NOT_FOUND | no bounded chapter; risk content dispersed in the broader material-matters narrative |
| ACT | 2018 | RESOLVED | 46-51 | "KEY RISKS AND \nOPPORTUNITIES" | materiality-matrix table + per-risk cards |
| ACT | 2019 | GENUINE_ABSENCE | -- | NOT_FOUND | same as 2017 |
| ACT | 2020 | GENUINE_ABSENCE | -- | NOT_FOUND | same as 2017 |
| ACT | 2021 | GENUINE_ABSENCE | -- | NOT_FOUND | same as 2017 |
| ACT | 2022 | RESOLVED | 39-39 | "Overview of our top risks" | risk-card/heat-map layout |
| ACT | 2023 | RESOLVED | 39-39 | "OVERVIEW OF OUR TOP RISKS" | risk-card/heat-map layout |
| ACT | 2024 | RESOLVED | 40-40 | "Overview of our top risks and related opportunities" | risk-card layout |
| BEL | 2016 | GENUINE_ABSENCE | -- | NOT_FOUND | different report structure that year |
| BEL | 2017 | GENUINE_ABSENCE | -- | NOT_FOUND | same |
| BEL | 2018 | RESOLVED | 20-24 | "Strategic overview and risk management" | named-risk register, see Section 4 |
| BEL | 2019 | RESOLVED | 20-25 | same | same |
| BEL | 2020 | RESOLVED | 20-27 | same | same |
| BEL | 2021 | RESOLVED | 20-27 | same | same |
| BEL | 2022 | RESOLVED | 18-25 | same | same |
| KP2 | 2020-2025 | GENUINE_ABSENCE (6/6) | -- | NOT_FOUND | only Audit and Risk Committee governance content and IFRS financial-instrument-risk notes found in the real-corpus heading inventory; no standalone Material Risks chapter |
| SBP | 2023-2025 | GENUINE_ABSENCE (3/3) | -- | NOT_FOUND | only "Audit, Governance and Risk Committee" and numbered "10.1/10.2" risk-governance subsections found; consistent with SBP's numbered-subsection report structure already documented in 7D.3/7D.4 |
| SDL | 2024-2025 | GENUINE_ABSENCE (2/2) | -- | NOT_FOUND | only two isolated named-risk headings ("Tenure and title risk", "Sovereign risk") with no parent schedule heading; thin evidence (2 years), consistent with SDL's overall thin corpus in prior tracks |
| SUR | 2023 | RESOLVED | 48-48 | "Social and economic risks facing South Africa" | pure risk-landscape infographic, see Section 4 |
| SUR | 2024 | RESOLVED | 173-173 | "SOCIAL AND ECONOMIC RISKS FACING SOUTH AFRICA" | same |
| SUR | 2025 | RESOLVED | 7-7 | "1 SOCIAL AND ECONOMIC RISKS FACING SOUTH AFRICA" | same |

Schedules resolved: 16 of 30 (ACT 5/9, BEL 5/7, KP2 0/6, SBP 0/3, SDL 0/2,
SUR 3/3).

**Top-level termination behavior**: confirmed generic and schedule-agnostic
for every RESOLVED case above -- no MATERIAL_RISKS-specific termination
logic was needed anywhere, same as every prior schedule.

## 4. Risk-schedule structural inventory

Every resolved schedule's actual block content was inspected directly
against the canonical source (not inferred from heading text alone):

| ticker | classification | evidence |
|---|---|---|
| ACT | `MIXED_NARRATIVE_AND_STRUCTURED` / `CARD_OR_MATRIX_LAYOUT` | 2016/2018: a "Material matters / Why material? / Risks / Opportunities / Stakeholders / Response" materiality matrix, one row per named risk, each cell itself a `HEADING_CANDIDATE`+short paragraphs (not free narrative). 2022-2024: an "Overview of our top risks" risk-heat-map page followed by per-risk cards ("IT RISKS", "ECONOMIC/GROWTH RISKS"), each card a `Risk description / Root cause / Inherent rating / Existing controls / Previous residual rating / Current residual rating / Movement` structured block, not prose. |
| BEL | `MIXED_NARRATIVE_AND_STRUCTURED` | A "Strategic overview and risk management" chapter containing named risk topics ("Competitor risk", "Currency risk", "Political risks in the countries...", "Regulatory risk", "Human capital", "Global competitiveness") each followed by 1-2 real narrative paragraphs plus a bulleted mitigation-factor list under an "Inherent risks / Risk mitigation factors" running table header -- genuinely part-narrative, unlike ACT's pure matrix, but see Section 5's taxonomy-instability finding. |
| SUR | `OTHER` (pure infographic) | The localized page range for all three years contains **zero** non-heading text blocks in the canonical source -- the "Social and economic risks facing South Africa" content is rendered entirely as a risk-landscape graphic (repeated bare "RISK" labels, "HIGH RISK LOW RISK" axis labels, icons), with no extractable narrative text at all. |

No issuer's Material Risks content matches the `NARRATIVE_SECTIONED`
pattern that FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE/REMUNERATION units
have used successfully so far -- confirming the milestone's own warning
that "Material Risks may be structurally different from the narrative
schedules already implemented."

## 5. Candidate semantic-unit inventory

**ACT**: every candidate concept observed ("IT RISKS", "ECONOMIC/GROWTH
RISKS", "BUSINESS/REPUTATIONAL RISKS", "Concentration risk", "Strategic
execution risk", the materiality-matrix's numbered risk rows) is a
structured card/table cell, not a bounded narrative subsection --
`NEXT_HEADING` on any of these would capture only a fragment of a table row
(a risk-description paragraph immediately followed by more table-header
fragments), not real narrative. No candidate meets the "narrative, usable
boundary" bar.

**BEL**: the named-risk topics look narrative-shaped at first (a topic name
followed by real prose), but real-corpus year-over-year inspection found
their identity is **not stable**: `"Currency risk"`/`"Competitor risk"`
appear as standalone `HEADING_CANDIDATE` blocks in 2019, as run-in
`PARAGRAPH`-prefix text in 2018 and 2020 (lower-case-vs-upper-case run-in
style also changes between those two years), and are **absent entirely**
in 2021-2022, replaced by a different topic set (`"STRATEGIC ALLIANCE
PARTNERS AND KEY SUPPLIER RELATIONS RISK"`, `"BUSINESS CONTINUITY DUE TO
POWER SUPPLY"`, `"BUSINESS CONTINUITY DUE TO SUPPLY CHAIN FAILURE"`,
`"BUSINESS CONTINUITY RISK DUE TO COVID-19"`) that itself is not stable
across those two years either. This is exactly the "risk disclosures
change names, split, merge, move order, disappear because taxonomy
changed" pattern the milestone's Section 7 explicitly warns against forcing
continuity through -- no candidate here meets the "stable analytical
identity" bar the milestone requires (Section 6).

**SUR**: no candidate exists -- the localized content is a pure graphic
with zero extractable text (Section 4).

**KP2, SBP, SDL**: no schedule resolved (Section 3), so no candidate
inventory was possible.

## 6. Unit selection

**Zero units were selected**, for every issuer, per the milestone's own
Section 8 instruction: "It is acceptable for an issuer to have zero
selected units. Do not manufacture coverage." This is the honest outcome
of Sections 4-5's real-corpus structural findings, not a shortfall against
a quota. No new boundary strategy was introduced (none was needed, since
no unit was configured at all).

## 7. Rejected / deferred candidates

- ACT's materiality-matrix rows and risk cards (all years): deferred to the
  structured backlog (Section 9) -- table/card content, not narrative.
- BEL's named-risk topics: deferred, real taxonomy instability documented
  in Section 5 -- not forced into a `unit_key` that would silently paper
  over the 2021-2022 topic-set change as if it were the same analytical
  risk continuing.
- SUR's "Social and economic risks facing South Africa": deferred -- no
  extractable text exists to configure a narrative unit around at all.
- SDL's `"Tenure and title risk"`/`"Sovereign risk"`: deferred -- only 2
  years, no parent schedule heading, too thin to inventory confidently
  (same judgment 7D.3/7D.4 already applied to SDL elsewhere).

## 8. Configuration changes

**Configuration only** (`schedule_config.py` -- nothing else):
- `NormalizedSchedule.MATERIAL_RISKS` added to `schedule_localization.py`'s
  scope guard (docstring + tuple, mirroring 7D.3/7D.4's own pattern
  exactly).
- 9 new heading-vocabulary strings (5 distinct phrases, upper/title-case
  variants for readability, matching the file's existing style -- see
  Section 3).

`semantic_unit_config.py`, `analytical_eligibility.py`,
`coverage_registry.py`, and `cutover_config.py` were **not touched** --
zero narrative units means zero new entries in any of them. This is
verified by `tests/test_material_risks_expansion.py`.

## 9. Structured/card risk backlog

| ticker | table/card family | years observed | structure | existing engine compatible? | notes |
|---|---|---|---|---|---|
| ACT | Materiality matrix ("Material matters / Why material? / Risks / Opportunities / Stakeholders / Response") | 2016, 2018 | `MIXED_NARRATIVE_AND_STRUCTURED` table, one row per named risk | No | `NEW_TABLE_FAMILY_REQUIRED` -- different column shape than any existing 7C.4 table family |
| ACT | Risk cards ("Risk description / Root cause / Inherent rating / Existing controls / Previous residual rating / Current residual rating / Movement") | 2022-2024 | `RISK_REGISTER_STYLE_TABLE` per card | No | `NEW_TABLE_FAMILY_REQUIRED` -- also needs a heat-map/likelihood-impact visual encoding no existing engine reads |
| BEL | "Inherent risks / Risk mitigation factors" running table | 2018-2022 | `MIXED_NARRATIVE_AND_STRUCTURED`, topic set unstable year to year | No | `NEW_TABLE_FAMILY_REQUIRED` -- and taxonomy instability (Section 5) would block row alignment regardless of parser support |
| SUR | Risk-landscape infographic ("Our risk landscape", "HIGH RISK LOW RISK") | 2023-2025 | pure graphic, no text/table structure at all | No | `CARD_LAYOUT_NOT_SUPPORTED` -- not even a real data table, a rendered image-like layout with no underlying structured cell data in the canonical source |

No new structured-table parser was built in this milestone (explicitly out
of scope, Section 9/13 of the milestone brief).

## 10. Extraction coverage / manual source review / alignment / analytical routing / lexical comparison / longitudinal sanity check / risk-identity review

Not applicable -- zero units were configured, so no extraction, alignment,
analytical-decision, or lexical-comparison run has anything to operate on.
Confirmed directly (not merely inferred) by running the full `localize` ->
`extract` -> `align` -> `classify` CLI pipeline against the live corpus for
ACT, BEL, and SUR (the three issuers with a resolved schedule): `extract`
correctly reports `ineligible -- no HEADED_NARRATIVE_UNIT configured for
{ticker}/MATERIAL_RISKS` for every resolved year and `ineligible --
MATERIAL_RISKS schedule instance has no primary span` for every
GENUINE_ABSENCE year; `align` and `classify` correctly cascade
`ineligible` for the same reason, upstream-unavailable. No crash, no
silently-wrong output, at any stage.

## 11. False-positive safety review

Per the milestone's Section 19 instruction (given 7D.4a just hardened
start-heading false positives), the real-corpus heading inventory was
searched specifically for cases where a configured MATERIAL_RISKS heading
occurs inside ordinary prose or a navigational label rather than as a real
structural heading. One such case was found and fixed by vocabulary
narrowing alone (Section 3's navigational-label finding) -- not a new
variant of 7D.4a's PARAGRAPH run-in-matcher defect (that mechanism was not
involved here at all; this was a `HEADING_CANDIDATE`-vs-`HEADING_CANDIDATE`
exact-match ambiguity, resolved by removing the offending vocabulary
string, which needs no algorithm change). No other false-positive
mechanism was found. No second correction was made or needed.

## 12. Coverage registry

`coverage_registry.py` is unchanged -- still derived automatically from
`semantic_unit_config.UNIT_CONFIGS`, `analytical_eligibility.
UNIT_ANALYTICAL_MODES`, and `cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE`.
Since no MATERIAL_RISKS `UnitConfig` exists, the registry correctly
contains zero MATERIAL_RISKS entries, verified by
`tests/test_material_risks_expansion.py::
test_material_risks_has_no_coverage_registry_entries`.

## 13. Issuer-level coverage summary

| ticker | report years | schedule years resolved | absent/unresolved years | narrative candidates found | narrative units configured | structured/card families observed | major blockers |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 5 | 4 (2017, 2019-2021) | 2 evaluated (materiality matrix, risk cards), 0 selected | 0 | 2 (`NEW_TABLE_FAMILY_REQUIRED` both) | every real risk concept is table/card content, not narrative |
| BEL | 7 | 5 | 2 (2016-2017) | ~6-9 named-risk topics evaluated across years, 0 selected | 0 | 1 (`NEW_TABLE_FAMILY_REQUIRED`) | named-risk topic identity is unstable year to year (Section 5) |
| KP2 | 6 | 0 | 6 | 0 evaluated | 0 | none inventoried | no heading matches the configured vocabulary in any year |
| SBP | 3 | 0 | 3 | 0 evaluated | 0 | none inventoried | no heading matches the configured vocabulary in any year |
| SDL | 2 | 0 | 2 | 0 evaluated (thin evidence) | 0 | not inspected in depth | only 2 isolated named-risk headings, no parent schedule heading |
| SUR | 3 | 3 | 0 | 0 evaluated (no extractable text) | 0 | 1 (`CARD_LAYOUT_NOT_SUPPORTED`) | content is a pure infographic with no narrative text at all |

## 14. Corpus-wide acceptance matrix

Not applicable -- with zero narrative units configured, there is no
per-unit alignment/analytical/comparison/provenance/cutover-readiness row
to report. Every configured-unit-dependent section of the milestone
(Sections 11-19, 21 of the milestone brief) resolves trivially to "none
configured," documented rather than fabricated.

## 15. Configuration-driven assessment

- **Units added through configuration + validation only**: 0.
- **Units requiring the one allowed generic parser/localizer correction**:
  0 -- the one real defect found (Section 3's navigational-label false
  positive) was fixed by vocabulary narrowing alone, which does not draw on
  this budget (same distinction 7D.3/7D.4 already established between pure
  vocabulary changes and matching-logic changes).
- **Candidates blocked by taxonomy instability**: BEL's entire named-risk
  topic set (Section 5).
- **Candidates blocked by structured/card layout**: ACT's entire Material
  Risks content, both years' materiality-matrix and years' risk-card
  layout (Section 4/9); SUR's infographic (not even structured -- a pure
  graphic).
- **Candidates requiring issuer-specific parser work**: 0 identified --
  every blocker found is either a corpus-wide structural mismatch (card/
  table content vs. narrative extraction) or a corpus-wide taxonomy-
  instability judgment call, not a one-off parser quirk.
- **Candidates requiring genuinely new architecture**: effectively all of
  them, if MATERIAL_RISKS coverage is ever to be added for real -- a new
  structured-table/card parser (explicitly out of this milestone's scope)
  would be needed for ACT's and BEL's content, and no amount of
  configuration alone can make SUR's pure infographic or BEL's unstable
  risk taxonomy narrative-comparable.

**Is Material Risks expansion still primarily configuration-driven?** No --
this is the first of the five schedules evaluated across 7C.1/7D.2/7D.3/
7D.4/7D.5 where configuration-only work (vocabulary + `UnitConfig` entries)
could not produce a single usable comparison unit for any issuer. The
schedule itself localizes cleanly and configuration-only (16/30 years
resolved, one real false positive fixed by vocabulary narrowing alone), but
every issuer's actual risk-disclosure *content* requires either a new
structured-table/card parser (ACT, BEL, SUR's card family) or resolves to
content with no stable analytical identity to compare longitudinally at all
(BEL) or no extractable text whatsoever (SUR) -- capability gaps this
milestone was explicitly scoped not to close.

## 16. One-fix budget

**Zero of the one allowed generic parser/localizer/extractor correction was
used.** The one real defect found and fixed (Section 3/11) was a pure
vocabulary narrowing, not a matching-logic change, so it draws on neither
this milestone's nor any future milestone's one-fix budget.

## 17. Regression testing

`schedule_config.py`'s `ALGORITHM_VERSION`/`HEADING_VOCABULARY_VERSION`
bump changes `compute_configuration_hash()` for every schedule (the hash
covers the whole vocabulary dict), which forces a fresh
`ScheduleLocalizationRun` on next invocation for FINANCIAL_PERFORMANCE/
CORPORATE_GOVERNANCE/REMUNERATION too, rather than a stale skip -- expected
and harmless, since none of those schedules' own vocabulary entries were
touched. The full pytest suite (Section 18) is the authoritative regression
check and passed with no unexpected failures. No shared extraction/
boundary/matching code was changed at all this track (only
`schedule_config.py`'s vocabulary dict and `schedule_localization.py`'s
scope-guard tuple + docstring), so BEL `gross_margin`, ACT
`healthcare_services_review`, ACT `combined_assurance`, ACT
`remuneration_policy_changes`, and ACT `remuneration_governance` were not
at risk of any behavioral change this track, and the full suite confirms
none occurred.

## 18. Tests

Added:
- `tests/test_schedule_localization.py`: `test_unimplemented_schedule_
  raises_not_implemented` updated to target `CEO_REVIEW` (still genuinely
  unimplemented), replacing the now-stale `MATERIAL_RISKS` target, mirroring
  7D.3's/7D.4's own replacement pattern each time another schedule was
  implemented. New MATERIAL_RISKS section: schedule localizes like every
  other implemented schedule given the same evidence shape; the real
  navigational-label false positive does not occur with the deliberately
  narrowed vocabulary (both with and without the real chapter heading also
  present); a "continued" banner does not terminate the schedule.
- `tests/test_material_risks_expansion.py` (new): documents and guards the
  milestone's own zero-narrative-units outcome -- no `UnitConfig`, no
  `UNIT_ANALYTICAL_MODES` entry, no `coverage_registry` entry, and no
  `cutover_config` scope entry exists for MATERIAL_RISKS; the configured
  vocabulary excludes risk-governance phrases (Audit and Risk Committee,
  Enterprise Risk Management, combined assurance, three lines of defence,
  bare "risk management") and the generic navigational-label phrase ("risks
  and opportunities").

Targeted tests were run throughout development
(`tests/test_schedule_localization.py`,
`tests/test_material_risks_expansion.py`); the full suite was run once at
the end (Section 19's result). No publishing/frontend tests were affected,
as expected -- this track never touches published data shapes.

## 19. Fresh-database sanity result

Deferred beyond a lightweight check, per the milestone's own instruction
that this is not release hardening. The local Postgres instance (Docker
Compose) was already running with the full 6-issuer corpus loaded from
prior tracks, and this track's own CLI runs (`localize` across all six
tickers, `extract`/`align`/`classify` across ACT/BEL/SUR) exercised the
full migrations-to-publication-adjacent path against that live database
end-to-end without incident.

## 20. Caveats

- Zero MATERIAL_RISKS narrative units are configured or comparable in the
  current pipeline for any issuer -- this track adds schedule-localization
  infrastructure (a real, verified capability: 16/30 report-years now
  correctly bound a Material Risks chapter, including one real false-
  positive fix) but zero user-facing comparison capability.
  `docs/7d4-corpus-wide-remuneration-expansion.md`'s own Section 26
  checkpoint predicted MATERIAL_RISKS would carry "moderate" difficulty
  based on adjacent-schedule circumstantial evidence; this track's direct,
  real-corpus structural inventory contradicts that prediction -- the
  content itself, not the localization step, is the blocker.
- BEL's named-risk-topic identity instability (Section 5) is a real,
  confirmed finding, not a placeholder for "not yet investigated" -- a
  future track revisiting this should expect the same instability unless
  it specifically targets a different, more stable candidate concept (none
  was found in this track's inventory).
- SUR's Material Risks content is a pure infographic with zero extractable
  text in the canonical source for all three years -- this is a genuine
  content-representation limit (no OCR/VLM was attempted, per the
  milestone's explicit hard exclusion), not a localization or extraction
  defect.
- KP2/SBP/SDL's GENUINE_ABSENCE findings reflect real uncertainty about
  those issuers' report structure for this schedule specifically, not
  confirmed dead ends -- consistent with the same issuers' thin coverage
  already documented for CORPORATE_GOVERNANCE/REMUNERATION in 7D.3/7D.4.

## 21. Final verdict

**FAIL -- MATERIAL RISKS IS TOO STRUCTURALLY VARIABLE FOR CURRENT
ARCHITECTURE**

Material Risks schedule *localization* is configuration-driven and now
works corpus-wide exactly like every other implemented schedule (16 of 30
report-years resolved, one real false positive found and fixed by
vocabulary narrowing alone, zero draw on the one-generic-fix budget). But
every issuer's actual risk-disclosure *content* -- the thing a comparison
system would actually need to extract and compare -- is either a
materiality-matrix/risk-card table (ACT), a named-risk register whose topic
identity reorganizes year to year (BEL), a pure infographic with no
extractable text (SUR), or absent from the real corpus entirely (KP2, SBP,
SDL). None of the existing `NEXT_HEADING`/`ANCHOR_SENTENCE` narrative
extraction, `LEXICAL_ONLY` comparison, or existing structured-table
architecture can honestly produce a single usable, longitudinally-
comparable Material Risks unit for any issuer without either a new
structured-table/card parser or a taxonomy-normalization capability this
milestone was explicitly scoped not to build. This is the answer to the
milestone's own question -- delivered honestly rather than forced --
rather than a shortfall against a coverage quota.

- Companies audited: 6 (ACT, BEL, KP2, SBP, SDL, SUR)
- Report years audited: 30 (9+7+6+3+2+3)
- Schedules resolved: 16 of 30 (ACT 5/9, BEL 5/7, KP2 0/6, SBP 0/3, SDL
  0/2, SUR 3/3)
- Semantic units configured: 0
- READY_FOR_CUTOVER: 0
- READY_WITH_CAVEAT: 0
- NOT_READY: 0 (no unit was configured to be NOT_READY -- distinct from
  every prior schedule, which always configured at least one unit that
  later proved NOT_READY)
- Structured/card families deferred: 4 (ACT materiality matrix, ACT risk
  cards, BEL inherent-risks table, SUR risk-landscape infographic)

## 22. Next-schedule checkpoint

Evaluated corpus-wide, using this track's own real-corpus inventory plus
7D.3's/7D.4's:

- **CEO_REVIEW / CHAIR_REVIEW**: this track's incidental inventory (risk-
  heading scan touched many pages of narrative context around risk
  sections) did not surface new evidence on the previously-flagged fused-
  chairman-plus-CEO-section risk (BEL) or the general CEO/Chair heading
  question either way. Still an open scoping question from 7D.3/7D.4,
  unresolved.
- **STRATEGY / OUTLOOK**: no new evidence surfaced this track either;
  still not enough information to recommend confidently.
- **LEGAL_REGULATORY, MATERIAL_MATTERS_OPERATING_ENVIRONMENT**: not
  evaluated in this or any prior track; no evidence-based estimate
  possible without a dedicated inventory pass, same as before.
- A general observation from this track worth carrying forward: schedules
  whose real-corpus content is dominated by risk/impact/likelihood-style
  disclosure (heat maps, materiality matrices, rating tables) are
  structurally incompatible with this architecture's narrative-extraction
  assumption regardless of how cleanly their *schedule* localizes -- this
  is a useful screening question to ask early, before investing in
  heading-vocabulary work, for any future schedule candidate.

**Recommendation**: given this track's finding that MATERIAL_RISKS -- the
schedule 7D.4's own checkpoint rated as having the strongest circumstantial
evidence of any remaining schedule -- turned out to require new
architecture rather than configuration, the next schedule should be chosen
by first running the same lightweight real-corpus heading-and-content
inventory this track opened with (Section 1) for CEO_REVIEW/CHAIR_REVIEW,
STRATEGY, and OUTLOOK *before* committing to a full milestone, specifically
checking each for narrative-vs-structured content shape, rather than
assuming adjacent-schedule circumstantial evidence predicts narrative
compatibility. No single confident recommendation is made here without
that inventory.

# Track 7D.6: Corpus-Wide CEO/Chair Review Expansion

## 1. Corpus inventory

Same six issuers, same report-year counts as every prior 7D track:

| ticker | report years |
|---|---|
| ACT | 9 (2016-2024) |
| BEL | 7 (2016-2022) |
| KP2 | 6 (2020-2025) |
| SBP | 3 (2023-2025) |
| SDL | 2 (2024-2025) |
| SUR | 3 (2023-2025) |

Total: 30 report years, both new schedules (CEO_REVIEW, CHAIR_REVIEW)
evaluated against every one.

## 2. Canonical-extraction readiness by issuer

7D.5a found ACT and BEL had a completed Track 7C.1a canonical-extraction run
for every year; KP2, SBP, SDL, SUR fell back to legacy `TextBlock` for all
years. This track directly tested whether that gap mattered for CEO/Chair
boundary reliability: a first localization pass against SBP's legacy
`TextBlock` data produced a severely over-extended (bled) Chairman's-letter
span for 2023/2024 (see Section 7) because legacy rows carry no font
evidence at all, so nothing could ever satisfy the end-boundary's
relative-font-size check. That is direct, positive evidence (per the
milestone's own Section 3 instruction) that structural/font evidence is
load-bearing here, so Track 7C.1a canonical extraction was run for KP2,
SBP, SDL, and SUR (`canonical extract <TICKER>` for each) before finalizing
vocabulary and localization. All 17 report-years across the four issuers
completed successfully with no failures.

Re-running localization against the new canonical source did **not**
change SBP's/SDL's outcomes (see Section 7) -- the underlying boundary
issue there is a font-ratio heuristic limitation (Section 19), not a
canonical-extraction absence. Canonical extraction was still the right,
disciplined thing to run first: it is what makes the real cause (a
font-ratio limitation, not "no font data") legible, and every subsequent
CEO/Chair claim in this document for KP2/SBP/SDL/SUR is now made against
the same canonical, source-faithful representation ACT/BEL already had --
not against a temporary legacy-data workaround.

## 3. Schedule-heading inventory (real-corpus verified)

7D.5a's own screening pass was re-verified against the live database in
this track (not re-derived from memory), using a direct DB inspection
mirroring `schedule_localization.py`'s own heading-detection path (canonical
source preferred, legacy `TextBlock` fallback). Real per-year heading text,
confirmed:

**ACT** (wording changes almost every year -- the same vocabulary-breadth
pattern CORPORATE_GOVERNANCE/REMUNERATION/MATERIAL_RISKS already handle):

| year | CEO heading | Chair heading |
|---|---|---|
| 2016 | CHIEF EXECUTIVE OFFICER'S REPORT | CHAIRPERSON'S REPORT |
| 2017 | GROUP CEO'S REPORT | CHAIRPERSON'S REPORT |
| 2018 | GROUP CEO'S REPORT (title split across 2 blocks) | CHAIRMAN'S REPORT (title split across 2 blocks) |
| 2019 | GROUP CEO'S STRATEGIC REVIEW (title split, reordered) | CHAIRMAN'S REPORT (title split, reordered) |
| 2020 | CEO'S REVIEW (title split across 2 blocks) | CHAIRMAN'S REVIEW (title split across 2 blocks) |
| 2021 | CEO'S REVIEW | CHAIRMAN'S REVIEW (as "OUR BUSINESS IN CONTEXT CHAIRMAN'S REVIEW") |
| 2022 | CEO'S REVIEW | CHAIRMAN'S REVIEW |
| 2023 | CEO'S (title split) | CHAIRMAN'S (title split) |
| 2024 | CEO'S REVIEW | CHAIRMAN'S |

**BEL/SDL** (joint chapter, one heading, never split):
- BEL 2016: "joint report by the CHAIRMAN AND chief executive"
- BEL 2017-2022: "Joint report by the chairman and chief executive" (exact,
  every year)
- SDL 2024-2025: "CHAIRMAN AND CEO REPORT" (exact, both years; repeats
  verbatim on the immediately following page without a "(continued)"
  suffix -- see Section 19's truncation defect)

**SBP**: "CHAIRMAN'S LETTER TO SHAREHOLDERS" (exact, all 3 years). No
standalone CEO heading anywhere in SBP's real corpus -- confirmed
`GENUINE_ABSENCE`; SBP's Executive Chairman and CEO are the same person
(consistent with 7D.3's/7D.4's own prior note about SBP's family-holding-
company structure).

**SUR** (wording varies by year, separation is stable):
- 2023: "CEO's review" (p68) / "Chairman's review" (p65)
- 2024: "A Message from our CEO" (p11, recurs 4x across the byline/photo
  captions) / "Introduction from our chairman" (p8, recurs 4x similarly)
- 2025: "CEO's review" (p17) / "Chairman's review" (p14)

**KP2**: zero CEO/Chairman/Chairperson heading-candidate hits in any of its
6 real report years, confirmed again after running canonical extraction --
`GENUINE_ABSENCE`, consistent with its differently-structured "Review of
Operations and Strategic Report" lead chapter.

## 4. Navigational/TOC false-positive review

Page-3 TOC lines matching CEO/Chair vocabulary were directly confirmed in
the real corpus (e.g. ACT 2017's "GROUP CEO'S REPORT 47", ACT 2018's "Group
CEO's report 19 – 22", ACT 2022's "Chief Executive Officer's (CEO's) review
Page 46"). Every one of these was correctly excluded from primary/supporting
matching by the existing `is_toc_entry` structural check -- confirmed by
direct query against `assess_heading_structure`'s output for these exact
rows, and guarded by a new test
(`test_toc_entry_is_not_matched_as_ceo_chair_heading`). No running-header,
page-banner, or sidebar false positive was found for CEO/Chair vocabulary in
this track's inspection (unlike 7D.5a's STRATEGY/OUTLOOK findings, which
remain a standing caution for those still-deferred schedules only).

## 5. CEO/Chair normalization design

**Functional mapping**, exactly as 7D.5a recommended:

- ACT, SUR: separate CEO_REVIEW and CHAIR_REVIEW chapters, each with its own
  vocabulary entries.
- BEL, SDL: one joint chapter. Its heading strings ("Joint report by the
  chairman and chief executive", "Chairman and CEO report") are configured
  under **both** schedules' vocabulary in `schedule_config.py`.
- SBP: CHAIR_REVIEW only (no CEO vocabulary entry matches SBP's corpus at
  all).
- KP2: neither schedule has any matching vocabulary in KP2's real corpus.

## 6. Joint-span functional mapping design

**No schema or algorithm change was needed.** `ScheduleLocalizationRun` and
`ScheduleInstance` are already scoped per `(report, schedule)` --
`localize_schedule`/`run_localization` run completely independently for
CEO_REVIEW and CHAIR_REVIEW. Because BEL's/SDL's joint-chapter heading
string is configured in both schedules' vocabulary, running localization
for CEO_REVIEW and for CHAIR_REVIEW against the same report independently
finds the same heading and produces two separate `ScheduleInstance` rows
(one per schedule, per the existing `uq_schedule_instances_run_schedule`
uniqueness) whose `heading_text`/`start_page`/`end_page` are identical --
verified directly against the real database (Section 7's table). No source
text is duplicated (both rows are just page-range pointers into the same
report), and there is no contradictory provenance: both instances agree on
the same heading and page range, they simply carry two different
`schedule` labels. This is a pure configuration decision, not a new
capability -- confirmed with a unit test
(`test_joint_chapter_maps_to_both_ceo_and_chair_schedules`) and against
real BEL/SDL data.

## 7. Schedule-localization results (real corpus)

Full classification, all 30 report-years x 2 schedules, using the
milestone's own vocabulary (`RESOLVED`, `GENUINE_ABSENCE`,
`HEADING_VARIATION`, `LOCALIZATION_DEFECT`, `INCONCLUSIVE`):

| ticker | year | CEO_REVIEW | pages | CHAIR_REVIEW | pages |
|---|---|---|---|---|---|
| ACT | 2016 | LOCALIZATION_DEFECT (bleeds into STRATEGY/MATERIAL_RISKS chapters) | p28-51 | LOCALIZATION_DEFECT (truncated, "(continued)" w/ parens not recognized) | p24-25 |
| ACT | 2017 | RESOLVED | p51-56 | RESOLVED | p8-12 |
| ACT | 2018 | LOCALIZATION_DEFECT (exact-match continuation page outranks real earlier heading) | p26-26 | LOCALIZATION_DEFECT (same cause) | p12-12 |
| ACT | 2019 | RESOLVED, HEADING_VARIATION ("Strategic Review" not "Report") | p28-39 | INCONCLUSIVE (short; may be a genuinely short letter or the same "(continued)" truncation as 2016) | p8-10 |
| ACT | 2020 | RESOLVED (via this track's one generic fix, Section 19) | p41-55 | RESOLVED (same fix) | p24-27 |
| ACT | 2021 | RESOLVED | p53-60 | LOCALIZATION_DEFECT (severe bleed, swallows the CEO_REVIEW chapter and beyond) | p34-134 |
| ACT | 2022 | LOCALIZATION_DEFECT (severe bleed to near end of document) | p50-150 | RESOLVED | p10-15 |
| ACT | 2023 | RESOLVED | p54-61 | RESOLVED | p14-19 |
| ACT | 2024 | RESOLVED | p54-63 | RESOLVED | p14-18 |
| BEL | 2016-2022 (all 7) | RESOLVED (joint) | 2-4pp each | RESOLVED (joint) | 2-4pp each |
| KP2 | 2020-2025 (all 6) | GENUINE_ABSENCE | -- | GENUINE_ABSENCE | -- |
| SBP | 2023 | GENUINE_ABSENCE | -- | LOCALIZATION_DEFECT (bleeds to p42 of 48) | p2-42 |
| SBP | 2024 | GENUINE_ABSENCE | -- | LOCALIZATION_DEFECT (bleeds to p44 of 50) | p2-44 |
| SBP | 2025 | GENUINE_ABSENCE | -- | RESOLVED | p2-3 |
| SDL | 2024 | LOCALIZATION_DEFECT (truncated one page early) | p2-2 | LOCALIZATION_DEFECT (same) | p2-2 |
| SDL | 2025 | LOCALIZATION_DEFECT (same) | p2-2 | LOCALIZATION_DEFECT (same) | p2-2 |
| SUR | 2023 | RESOLVED | p68-74 | RESOLVED | p65-67 |
| SUR | 2024 | RESOLVED (short commentary, consistent with SUR's own content shape) | p11-11 | RESOLVED (same) | p8-8 |
| SUR | 2025 | RESOLVED | p17-25 | RESOLVED | p14-16 |

**Totals** (60 cells): RESOLVED 32, GENUINE_ABSENCE 15, LOCALIZATION_DEFECT
12, INCONCLUSIVE 1. CEO_REVIEW resolved in 16/30 years; CHAIR_REVIEW
resolved in 16/30 years; the BEL/SDL joint-mapping mechanism itself
(both schedules landing on an identical page range) was demonstrated in
all 9 joint-issuer-years (7 BEL + 2 SDL), even though SDL's boundary
itself carries a truncation defect in all 4 of its cells.

Every defect above was produced by the pre-existing (not newly introduced)
boundary algorithm hitting a real, understood limitation -- see Section 19.
None was fixed in this track beyond the one generic correction described
there, per the milestone's one-fix budget.

## 8. Semantic-unit inventory

Real internal subheadings were inspected directly (not just inferred from
7D.5a's screening) inside several resolved ACT spans:

- ACT CEO_REVIEW: "Strategy in action" appears as its own heading-candidate
  in 2019 (p30) and 2020 (p42), a short recap of specific strategic
  initiatives.
- ACT CHAIR_REVIEW: "Outlook"/"Appreciation" subheadings recur (2022: "Outlook",
  "Appreciation"; 2023: "OUTLOOK AND APPRECIATION", merged into one label)
  -- wording is not stable year to year.
- BEL/SDL joint chapter: no internal recurring subheading distinct from the
  whole joint narrative was found (consistent with 7D.5a).
- SBP Chairman's letter: internal subsections exist ("Overview", "2023
  performance", "Governance and functions of the Board", "Shareholders",
  "Appreciation") but the schedule instance itself is not reliably bounded
  in 2 of 3 years (Section 7) -- too risky to build a unit on top of it.

## 9. Selected units

**None.** `ACT_STRATEGY_IN_ACTION` (CEO_REVIEW, NEXT_HEADING,
start_heading="Strategy in action") was configured and actually run against
the full ACT corpus (`units extract ACT --schedule ceo_review`). Result:

```
2016-2018, 2021-2024: start heading 'Strategy in action' not found -- no row created
2019: UNRESOLVED -- next heading-candidate block immediately follows the start heading
2020: COMPLETED (the only year that resolved)
```

Resolving in exactly 1 of 9 real years is below the same multi-year-
recurrence bar Track 7D.2 already used to reject ACT's "Capital management"
candidate for FINANCIAL_PERFORMANCE (see `semantic_unit_config.py`'s own
changelog). The unit was removed after this real result, not kept as a
speculative placeholder.

## 10. Rejected/deferred units

- `ACT_STRATEGY_IN_ACTION` -- rejected (Section 9): 1/9 years resolves.
- ACT CHAIR_REVIEW "Outlook"/"Appreciation" -- deferred: wording drifts
  between adjacent years ("Outlook" vs "OUTLOOK AND APPRECIATION"), not
  independently verified stable enough to configure without over-broadening
  the anchor text.
- BEL/SDL joint-chapter internal units -- deferred: no internal recurring
  subheading found distinct from the whole joint narrative.
- SBP Chairman's-letter internal subsections -- deferred: the schedule
  instance itself is unreliable in 2 of 3 years; configuring a unit on top
  of a defective container would inherit that unreliability.

## 11. Whole-span-unit decisions

No whole-span unit was configured for any issuer. The codebase has no
distinct "whole-span" `SemanticUnitBoundaryStrategy` today (only
`NEXT_HEADING`/`ANCHOR_SENTENCE` exist); introducing one would itself be a
new generic capability, and this milestone's one-fix budget was already
spent on the heading-fragment-concatenation fix (Section 19). SBP's
Chairman's letter and BEL's/SDL's joint chapter were both considered as
whole-span candidates (per the milestone's Section 13/14) and explicitly
declined: SBP's schedule instance itself is not reliably bounded in 2 of
3 years, and BEL's/SDL's joint chapter has no distinct internal structure
that a whole-span unit would add value over comparing the schedule
instance's own page range directly in a later track.

## 12. Extraction coverage

Only one unit was ever configured (`ACT_STRATEGY_IN_ACTION`, since
rejected), and its full-corpus extraction run is the coverage table:

| ticker | year | schedule | unit_key | status | notes |
|---|---|---|---|---|---|
| ACT | 2016 | CEO_REVIEW | strategy_in_action | GENUINE_ABSENCE | heading not found |
| ACT | 2017 | CEO_REVIEW | strategy_in_action | GENUINE_ABSENCE | heading not found |
| ACT | 2018 | CEO_REVIEW | strategy_in_action | GENUINE_ABSENCE | heading not found |
| ACT | 2019 | CEO_REVIEW | strategy_in_action | EXTRACTION_DEFECT | start heading found, but immediately followed by another heading-candidate with no body text -- UNRESOLVED |
| ACT | 2020 | CEO_REVIEW | strategy_in_action | RESOLVED | only successful year |
| ACT | 2021-2024 | CEO_REVIEW | strategy_in_action | GENUINE_ABSENCE | heading not found |

No other unit exists, so there is no further extraction-coverage table to
produce this milestone.

## 13. Manual source validation

Every heading and page cited in Sections 3 and 7 was read directly from
the live database (canonical `source_adapter` output, or legacy
`TextBlock` rows before canonical extraction was run), not copied from
7D.5a's own screening output. Specific manual checks performed:

- ACT 2019 p27-30 and 2020 p23-25/p40-42/p42: confirmed the split-title
  defect (Section 19) block-by-block, including exact font sizes.
- ACT 2016 p28-55 and ACT 2022 p10-16/2023 p14-20: confirmed the bleed
  defects and the internal Outlook/Appreciation subheadings.
- SBP 2023 p1-14 (canonical, post-extraction): confirmed the letter's real
  internal subsections and that page 4's "CONTENTS Page" (a genuine TOC,
  10.17pt) is the real intended boundary that the font-ratio heuristic
  fails to recognize against the letter's own 20pt heading.
- SDL 2024 p1-15 (legacy `TextBlock`): confirmed the real chapter is
  p2-3, and that p3's un-suffixed repeat of the same heading text
  incorrectly ends the span one page early.

## 14. Speaker/function integrity

| ticker | intended function | source speaker/role | heading stability |
|---|---|---|---|
| ACT CEO_REVIEW | CEO's operational review | Group CEO (role title changes: "Chief Executive Officer" 2016 -> "Group CEO" 2017+; person changes 2024, "TAKING THE HELM AS CEO") | function stable, title/person changes documented, not treated as identity changes |
| ACT CHAIR_REVIEW | Board-level review | Chairperson/Chairman (title varies "Chairperson" 2016-2017 -> "Chairman" 2018+; same person, Dr Anna Mokgokong, 2018-2024) | function stable |
| BEL/SDL CEO_REVIEW + CHAIR_REVIEW | Joint operational + board review | Chairman and Chief Executive jointly, named byline every year | function stable, joint by design |
| SBP CHAIR_REVIEW | Board/shareholder-facing letter | Executive Chairman/CEO (same person holds both roles) | function stable |
| SUR CEO_REVIEW / CHAIR_REVIEW | Separate CEO/Chair reviews | Val Nichas (CEO) / Mike Bosman (Chairman) named in 2024; role separation stable across all 3 years despite heading-wording drift | function stable |

No case was found where a semantic unit's content silently crossed from one
speaker's review into the other's -- not applicable in practice since no
units were configured (Section 9), but the schedule-level spans themselves
were checked for this per Section 13/17, and no cross-speaker bleed was
found among the RESOLVED cells (the LOCALIZATION_DEFECT cells bleed into
*other schedules'* content, e.g. STRATEGY/MATERIAL_RISKS chapters, not into
the other role's review).

## 15. Alignment

Not applicable. Cross-year semantic-unit alignment (Track 7C.2) operates on
configured `UnitConfig` rows, and zero were configured for either schedule
(Section 9). No `units align --schedule ceo_review`/`chair_review` run
produces anything to inspect.

## 16. Analytical routing

Not applicable, for the same reason as Section 15 -- `UNIT_ANALYTICAL_MODES`
has no entries for either schedule.

## 17. Lexical comparison

Not applicable, for the same reason.

## 18. Longitudinal sanity check

Not applicable at the semantic-unit level (none configured). At the
schedule-localization level, a corpus-wide span-length sanity check was run
directly against the real database (flagging any instance whose span
exceeded 20 pages or ended within 2 pages of the report's last page) to
surface the bleed defects documented in Section 7 -- this *is* the
longitudinal/outlier check this section calls for, applied to the schedule
boundary itself rather than to a unit's metric time series.

## 19. Cross-schedule overlap observations, and the one generic fix

**The one bounded generic fix used this milestone**: a section's own title
is sometimes split across two consecutive same-page `HEADING_CANDIDATE`
blocks by the upstream extraction pipeline -- confirmed real-corpus cases:
ACT 2019's "Group CEO's" + "STRATEGIC REVIEW" (different fonts, reversed
reading order) and ACT 2020's "CHAIRMAN'S" + "REVIEW" / "CEO'S" + "REVIEW"
(identical fonts, adjacent reading order). `schedule_localization.py` now
also tries the concatenation of two consecutive same-page heading
candidates against the vocabulary when neither block matches alone
(`_combined_with_next_same_page`, `ALGORITHM_VERSION` 1.6.0). This is
generic (not issuer-specific) and recovered 3 of the 12 LOCALIZATION_DEFECT
cells this track would otherwise have had (ACT 2020 CEO, ACT 2020 CHAIR,
partially ACT 2019 CEO). It does not affect any previously-implemented
schedule's behavior for the real corpus (Section 30's regression check
found byte-identical warning/completion patterns for FINANCIAL_PERFORMANCE,
CORPORATE_GOVERNANCE, and REMUNERATION before and after, matching every
already-documented per-unit recurrence year exactly).

**Discovered, pre-existing limitations documented and deferred (not
fixed, per the one-fix-budget rule)**:

1. The `"<heading> continued"` boundary-exclusion check only recognizes a
   continuation heading with the literal suffix `"continued"` (no
   punctuation) -- a real `"(continued)"` (with parentheses) form does not
   match, causing an early truncation (ACT 2016 CHAIR_REVIEW, possibly
   2019 CHAIR_REVIEW).
2. The exact-match-always-wins primary-selection rule can pick a short,
   repeated, exact-match occurrence of a heading (e.g. on a "(continued)"
   page) over an earlier, longer, real chapter start that only matched via
   word-order tolerance -- causing a 1-page truncated span (ACT 2018, both
   schedules).
3. The `_END_BOUNDARY_FONT_RATIO` (0.78) relative-font-size end-boundary
   heuristic, calibrated against BEL's/ACT's specific font spectrum,
   assumes *something* else in the document shares a comparably large
   font. When a schedule's own heading happens to be the single largest
   font anywhere in the report (ACT 2021 CHAIR_REVIEW, ACT 2022
   CEO_REVIEW, SBP 2023/2024 CHAIR_REVIEW), nothing ever satisfies the
   ratio and the span bleeds to near the end of the document. This is a
   pre-existing characteristic of the boundary algorithm itself, not
   unique to CEO/Chair, and would in principle affect any schedule under
   the same font-shape condition.
4. The boilerplate-repeat exclusion (3+ occurrences) does not catch a
   heading repeated only 2 times without a "continued" suffix (SDL's
   "CHAIRMAN AND CEO REPORT" on both p2 and p3), truncating the span one
   page early.

Each of these is a real, understood, *pre-existing* limitation of the
shared boundary algorithm (not introduced by this track), surfaced here
because CEO/Chair's own heading-font shapes exercised it more than prior
schedules happened to. Per the milestone's own rule ("if multiple
unrelated parser defects appear: document and defer them"), none of these
four is fixed in this track.

**Cross-schedule overlap** (CEO/Chair vs. STRATEGY/OUTLOOK/
FINANCIAL_PERFORMANCE, neither of the first two implemented): ACT's CEO
review chapter contains genuine "Strategy in action"/strategic-commentary
content and, in several years, an immediately-following "Outlook"
subsection (e.g. ACT 2020 p25's "OUTLOOK" heading sits right after the
Chairman's review body) -- this content remains inside the CEO_REVIEW/
CHAIR_REVIEW span as ordinary source content, exactly as the milestone
requires, since no separate STRATEGY or OUTLOOK schedule is implemented.
No double-counting occurs because no unit was configured to extract that
subsection separately.

## 20. Coverage registry

Zero entries for either schedule -- `coverage_registry.COVERAGE_REGISTRY`
derives strictly from `UNIT_CONFIGS`, and none were configured (Section 9).
Guarded by `test_ceo_review_and_chair_review_have_no_coverage_registry_entries`.

## 21. Issuer-level summary

| ticker | report years | CEO resolved | Chair resolved | joint years | CEO units | Chair units | joint units | READY_FOR_CUTOVER | READY_WITH_CAVEAT | NOT_READY | major blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ACT | 9 | 6 | 5 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | no configured units to grade; localization itself has 6 LOCALIZATION_DEFECT + 1 INCONCLUSIVE cells (Section 19) |
| BEL | 7 | 7 | 7 | 7 | 0 | 0 | 0 | 0 | 0 | 0 | localization fully clean; no unit configured yet |
| KP2 | 6 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | GENUINE_ABSENCE, not a blocker -- no CEO/Chair content exists |
| SBP | 3 | 0 | 1 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | CEO GENUINE_ABSENCE; Chair localization bleeds in 2/3 years (font-ratio limitation) |
| SDL | 2 | 0 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | 0 | joint-mapping mechanism demonstrated but boundary truncated in all 4 cells (2-occurrence-repeat gap) |
| SUR | 3 | 3 | 3 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | localization fully clean; no unit configured yet |

No unit exists for any issuer, so every `READY_FOR_CUTOVER`/
`READY_WITH_CAVEAT`/`NOT_READY` count is 0 by construction (Section 25).

## 22. Corpus-wide acceptance matrix

| ticker | schedule | unit_key | years available | years resolved | adjacent pairs | analytical mode | comparison coverage | provenance coverage | cutover readiness |
|---|---|---|---|---|---|---|---|---|---|
| ACT | CEO_REVIEW | -- (no unit) | 9 | 6 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| ACT | CHAIR_REVIEW | -- (no unit) | 9 | 5 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| BEL | CEO_REVIEW | -- (no unit) | 7 | 7 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| BEL | CHAIR_REVIEW | -- (no unit) | 7 | 7 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| SBP | CHAIR_REVIEW | -- (no unit) | 3 | 1 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| SDL | CEO_REVIEW / CHAIR_REVIEW | -- (no unit) | 2 | 0 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| SUR | CEO_REVIEW | -- (no unit) | 3 | 3 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| SUR | CHAIR_REVIEW | -- (no unit) | 3 | 3 (localization) | n/a | n/a | none | schedule-level only | NOT_READY (no unit) |
| KP2 | CEO_REVIEW / CHAIR_REVIEW | -- (no unit) | 6 | 0 (GENUINE_ABSENCE) | n/a | n/a | none | n/a | NOT_APPLICABLE |

## 23. BEL/SDL joint-mapping matrix

| ticker | year | source joint heading | source span | mapped to CEO_REVIEW? | mapped to CHAIR_REVIEW? | semantic unit model | duplicated user-facing output? | provenance consistency | notes |
|---|---|---|---|---|---|---|---|---|---|
| BEL | 2016 | "joint report by the CHAIRMAN AND chief executive" | p24-25 | yes | yes | none configured | n/a (no unit) | consistent -- both instances agree on heading text and page range | |
| BEL | 2017 | "Joint Report by the Chairman and Chief Executive" | p22-23 | yes | yes | none configured | n/a | consistent | |
| BEL | 2018 | "Joint report by the chairman and chief executive" | p31-34 | yes | yes | none configured | n/a | consistent | |
| BEL | 2019 | same | p32-35 | yes | yes | none configured | n/a | consistent | |
| BEL | 2020 | same | p34-37 | yes | yes | none configured | n/a | consistent | |
| BEL | 2021 | same | p34-37 | yes | yes | none configured | n/a | consistent | |
| BEL | 2022 | same | p36-39 | yes | yes | none configured | n/a | consistent | |
| SDL | 2024 | "CHAIRMAN AND CEO REPORT" | p2-2 (truncated; real span p2-3) | yes | yes | none configured | n/a | consistent, but the shared span itself is truncated one page early (Section 19, item 4) | |
| SDL | 2025 | "CHAIRMAN AND CEO REPORT" | p2-2 (truncated; real span presumed p2-3) | yes | yes | none configured | n/a | consistent, same truncation | |

No case produces a duplicated user-facing comparison, since no semantic
unit exists for either schedule yet -- the "duplicate identical output"
question (Section 14 of the milestone) does not arise until a unit is
configured on top of these joint spans in a future track.

## 24. Configuration-driven assessment

- Units added through configuration + validation only: **0** (one
  candidate was configured, validated against the real corpus, and
  rejected -- see Section 9).
- Units requiring the one allowed generic fix: **0** (the fix operates at
  the schedule-localization layer, not the unit layer; it recovered 3
  schedule-instance cells, no units).
- Joint mappings added: **9** (7 BEL + 2 SDL issuer-years), all via pure
  vocabulary configuration (the same joint-chapter string listed under both
  schedules), no schema or algorithm change.
- Issuer-specific exceptions avoided: all of them -- SBP's chair-only
  absence, KP2's total absence, ACT's/SUR's per-year wording drift, and
  BEL's/SDL's joint mapping are all expressed as vocabulary entries and
  independent per-schedule runs, with zero issuer-specific branches in
  `schedule_localization.py` (the one generic fix is issuer-agnostic).
- Candidates deferred: 3 (ACT CHAIR_REVIEW "Outlook"/"Appreciation";
  BEL/SDL joint-chapter internal units; SBP internal letter subsections)
  -- see Section 10.
- Candidates requiring genuinely new architecture: **0** at the
  localization layer. A future semantic-unit milestone touching SBP's
  letter or BEL's/SDL's joint chapter would need either the font-ratio
  boundary limitation addressed (Section 19, item 3) or a whole-span
  extraction strategy (Section 11) -- both are real, identified, but
  out-of-budget generic corrections, not new capabilities.

**Did CEO/Chair expansion remain low-cost and configuration-driven as
7D.5a predicted?** Partially. Schedule *localization* was exactly as
cheap as predicted: pure vocabulary configuration plus one small, generic,
real-corpus-motivated boundary fix, reusing the existing architecture
without any schema change, and the joint-mapping design question (7D.5a's
central open question) resolved with zero new capability. What 7D.5a's
screening pass could not have predicted -- because it inspected headings,
not full boundary behavior -- is that CEO/Chair's own font-size shapes
(often the single largest heading in the whole document, and prone to
title-splitting across blocks) exercise several pre-existing boundary-
algorithm edge cases harder than FINANCIAL_PERFORMANCE/CORPORATE_
GOVERNANCE/REMUNERATION happened to. The semantic-unit layer, in
particular, turned out to have zero real, corpus-verified, multi-year-
recurring candidates once actually run against the full corpus, despite
7D.5a's own optimistic 2-3-concepts-per-schedule estimate.

## 25. Tests

- `tests/test_schedule_localization.py`: 12 new tests -- CEO_REVIEW/
  CHAIR_REVIEW basic localization, joint-chapter dual-schedule mapping,
  chair-only issuer (no CEO match), no-clear-section issuer (neither
  matched), TOC exclusion, the split-heading-fragment concatenation fix
  (both the positive same-page case and the negative different-page
  case), plus the pre-existing `test_unimplemented_schedule_raises_not_
  implemented` retargeted to `STRATEGY` (mirroring every prior track's own
  replacement of that test).
- `tests/test_ceo_chair_review_expansion.py` (new file): zero-units
  precedent guards (mirroring `test_material_risks_expansion.py`), bare-
  role-word vocabulary exclusion guards, and a joint-phrase-shared-between-
  both-schedules guard.
- Regression: re-ran `units localize --force` and `units extract --force`
  against the real corpus for BEL/ACT FINANCIAL_PERFORMANCE, ACT
  CORPORATE_GOVERNANCE, and ACT REMUNERATION after the shared
  `schedule_localization.py` change. Every completion/warning message
  matched the already-documented per-unit recurrence years from 7D.2/
  7D.3/7D.4 exactly (e.g. `ACT_HEALTHCARE_SERVICES_REVIEW` still only
  resolves 2021-2023, `ACT_REMUNERATION_POLICY_CHANGES` still only
  resolves 2018/2020-2024) -- no regression.
- Full suite: `1195 passed, 3 skipped` (see Section 26).

## 26. Fresh-database sanity result

No schema or migration change was made in this track -- `CEO_REVIEW`/
`CHAIR_REVIEW` were already declared in `NormalizedSchedule`'s full
ten-schedule taxonomy since Track 7C.1, so no new Alembic migration was
needed. The full pytest suite (which builds its own fixture database from
the current migration head for every DB-backed test) passed in full
(`1195 passed, 3 skipped`, ~168s), which already exercises this
milestone's configuration end-to-end against a fresh schema. A dedicated
fresh-database rehearsal remains a later, separate track, per the
milestone's own scope note.

## 27. Caveats

- 12 of 60 localization cells are `LOCALIZATION_DEFECT` and 1 is
  `INCONCLUSIVE` (Section 7) -- these are real, understood, pre-existing
  boundary-algorithm limitations (Section 19), not new defects introduced
  by this track, but they do mean roughly a fifth of the corpus's CEO/Chair
  schedule instances are not yet trustworthy for downstream comparison
  work without either fixing the underlying boundary heuristics (out of
  this milestone's one-fix budget) or manually re-bounding them.
- Zero semantic units are configured for either schedule. The one
  candidate investigated (`ACT_STRATEGY_IN_ACTION`) was rejected after
  real-corpus extraction, not merely deferred on paper.
- SDL's joint-mapping mechanism is demonstrated correctly (both schedules
  land on the identical page range every year) but that shared span is
  itself truncated one page early in all 4 cells -- a future track should
  not treat SDL's current CEO/Chair spans as source-complete.
- SBP's CHAIR_REVIEW localization is unreliable in 2 of its 3 years
  (2023, 2024) due to the font-ratio boundary limitation -- only 2025 is
  currently trustworthy as-is.
- The four discovered generic boundary-algorithm limitations (Section 19)
  are documented, not fixed, and may resurface in any future schedule
  whose heading happens to share the same font-shape characteristics.

## 28. Final verdict

**PASS WITH CAVEATS — CEO / CHAIR COVERAGE EXPANDED BUT JOINT-MAPPING OR
ISSUER GAPS REMAIN.**

Both of the milestone's central questions have real, evidence-based
answers:

1. **Can CEO and Chair reviews be brought into the semantic comparison
   system corpus-wide using the existing narrative architecture?**
   Localization: yes, largely, using pure configuration plus one small
   generic fix (16/30 years resolved per schedule, the rest either
   genuinely absent or a documented, pre-existing boundary-algorithm
   limitation). Semantic-unit extraction: not yet -- the one real
   candidate investigated did not survive corpus-wide verification.
2. **Can joint CEO/Chair source chapters be represented cleanly without
   inventing content or duplicating provenance?** Yes -- demonstrated
   cleanly for BEL (all 7 years) and functionally for SDL (both years,
   though the shared span itself needs re-bounding), using zero schema or
   algorithm changes.

Companies audited: 6 (ACT, BEL, KP2, SBP, SDL, SUR).
Report years audited: 30.
CEO schedules resolved: 16/30.
Chair schedules resolved: 16/30.
Joint schedules resolved (mapping mechanism demonstrated): 9/9 joint-issuer-years (BEL 7, SDL 2), though 4 of those (SDL) carry a boundary-truncation caveat.
Semantic units configured: 0.
READY_FOR_CUTOVER: 0.
READY_WITH_CAVEAT: 0.
NOT_READY: 0 (no unit exists to grade; see Section 21/25).

## Release-hardening checkpoint

Per the milestone's own instruction, 7D.5a's baseline stands:

    STRATEGY              deferred
    OUTLOOK               deferred
    LEGAL_REGULATORY      incompatible / absent
    MATERIAL_MATTERS      structured + overlap blocker
    OPERATING_ENVIRONMENT deferred

This track surfaced no new evidence that any of these five is
unexpectedly low-cost and narrative-compatible -- if anything, it surfaced
that even a schedule pre-screened as `IMPLEMENT_NEXT`/`LOW` difficulty
(CEO_REVIEW/CHAIR_REVIEW) had real, corpus-specific boundary-algorithm
friction once actually run end-to-end, which should raise rather than
lower the bar for STRATEGY/MATERIAL_MATTERS/OPERATING_ENVIRONMENT, all of
which 7D.5a already found structurally harder.

**Recommendation: PROCEED_TO_RELEASE_HARDENING.** Do not implement any
additional schedule in a follow-on track without first addressing this
track's own semantic-unit and boundary-algorithm caveats (Section 27), or
without new, stronger real-corpus evidence than 7D.5a's original screening
provided for CEO/Chair.

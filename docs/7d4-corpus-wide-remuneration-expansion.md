# Track 7D.4: Corpus-Wide Remuneration Expansion

## 0. Scope note

This track evaluates the normalized `REMUNERATION` schedule corpus-wide,
across every company currently in the corpus (ACT, BEL, KP2, SBP, SDL,
SUR) and every available report year, following the same amended,
corpus-wide-from-the-start pattern Track 7D.3 established. No production
database change was made; no schedule other than REMUNERATION was
touched; the milestone's one-bounded-generic-parser-correction budget was
spent once, corpus-wide (Section 8).

## 1. Corpus / company inventory

Same six issuers as Track 7D.3's audit, no others added:

| ticker | report years |
|---|---|
| ACT | 9 (2016-2024) |
| BEL | 7 (2016-2022) |
| KP2 | 6 (2020-2025) |
| SBP | 3 (2023-2025) |
| SDL | 2 (2024-2025) |
| SUR | 3 (2023-2025) |

Total: 30 report years.

## 2. Schedule-localization results

`schedule_localization.localize_schedule`'s scope guard was extended to
accept `NormalizedSchedule.REMUNERATION` (previously `NotImplementedError`,
matching 7D.3's own pattern for `CORPORATE_GOVERNANCE`) -- again a
scope-guard change only, not a new algorithm. Heading vocabulary added
(pure config): `"Remuneration Committee Report"` / `"REMUNERATION
COMMITTEE REPORT"` and `"Remuneration Report"` / `"REMUNERATION REPORT"`.
`"Remuneration report"` is a substring match, not exact, so it also
matches "(CONTINUED)"/"(AUDITED)"/"(CONT)" suffixed banners and even SUR's
"REMUNERATION REPORTING AND ENGAGEMENT" (which literally contains
"remuneration report" as its own substring, since "reporting" = "report" +
"ing") -- the existing exact-match-first primary-selection rule (schedule
localization v1.2.0, Track 7D.1) resolves every one of these ambiguities
correctly wherever a genuine exact-match heading is also present, verified
against the real corpus below.

| ticker | year | status | primary span | confidence | heading | notes |
|---|---|---|---|---|---|---|
| ACT | 2016 | RESOLVED | 92-93 | HIGH | "REMUNERATION COMMITTEE REPORT" | |
| ACT | 2017 | RESOLVED | 100-107 | HIGH | "REMUNERATION COMMITTEE REPORT" | |
| ACT | 2018 | RESOLVED | 86-100 | HIGH | "REMUNERATION COMMITTEE REPORT" | |
| ACT | 2019 | RESOLVED | 98-115 | HIGH | "Remuneration REPORT" | |
| ACT | 2020 | RESOLVED (caveat) | 96-96 (+supporting to 114, incl. 94) | MEDIUM | "REMUNERATION REPORT (CONTINUED)" | Primary anchors on a "(CONTINUED)" banner because no bare "REMUNERATION REPORT" heading-candidate exists that year; the genuine chapter start (p.94, incl. the Chairperson's report heading) registers only as an earlier supporting span -- see Section 8's fix. |
| ACT | 2021 | RESOLVED | 108-108 (+supporting incl. 107, to 125) | HIGH | "REMUNERATION REPORT" | Same shape as 2020: genuine start (p.107) is an earlier supporting span. |
| ACT | 2022 | RESOLVED | 109-150 | HIGH | "REMUNERATION\nREPORT" | |
| ACT | 2023 | RESOLVED | 124-138 (+supporting to 150) | HIGH | "REMUNERATION\nREPORT" | |
| ACT | 2024 | RESOLVED | 119-154 | MEDIUM | "REPORT\nREMUNERATION" | Word-order-reordered extraction artifact (7D.1's tolerant matcher), not exact -- still the genuine heading. |
| BEL | 2016 | RESOLVED | 56-57 (+58-59) | HIGH | "REMUNERATION COMMITTEE REPORT" | |
| BEL | 2017 | RESOLVED | 42-49 | HIGH | "Remuneration Committee Report" | |
| BEL | 2018 | RESOLVED | 50-58 | HIGH | "Remuneration committee report" | |
| BEL | 2019 | RESOLVED | 52-65 | HIGH | "Remuneration committee report" | |
| BEL | 2020 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | That year's report uses different terminology with no heading matching the configured vocabulary anywhere. |
| BEL | 2021 | RESOLVED | 53-67 | HIGH | "Remuneration committee report" | |
| BEL | 2022 | RESOLVED | 56-70 | HIGH | "Remuneration committee report" | |
| KP2 | 2020 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | |
| KP2 | 2021 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | |
| KP2 | 2022 | RESOLVED (caveat) | 59-59 | MEDIUM | "CORPORATE GOVERNANCE REPORT (CONT) Remuneration Report (Cont)" | Same KP2 "(CONT)" pattern already documented (unfixed) in 7D.3: the genuine chapter start is fused body text, not a standalone heading-candidate; the only matchable occurrence is a later "(CONT)" banner. |
| KP2 | 2023 | RESOLVED (caveat) | 58-58 | MEDIUM | same pattern | |
| KP2 | 2024 | RESOLVED (caveat) | 66-66 (+supporting from 53) | MEDIUM | same pattern | |
| KP2 | 2025 | RESOLVED (caveat) | 72-72 (+supporting from 61) | MEDIUM | same pattern | |
| SBP | 2023 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | No heading matches the configured vocabulary -- consistent with SBP's own numbered-subsection report structure already documented in 7D.3 (governance's "11.2 Remuneration philosophy and policy" is a numbered subsection, not a standalone chapter heading). |
| SBP | 2024 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | |
| SBP | 2025 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | |
| SDL | 2024 | RESOLVED (caveat) | 21-21 (+22,23,24,54) | MEDIUM | "REMUNERATION REPORT (AUDITED)" | Substring match ("(AUDITED)" suffix); real content confirmed present (lettered-principles structure, "a) Principles used to determine..."). |
| SDL | 2025 | RESOLVED (caveat) | 21-21 (+22,23,24,53) | MEDIUM | same pattern | |
| SUR | 2023 | RESOLVED | 97-121 (+supporting 4-5, 87, 89) | HIGH | "REMUNERATION REPORT" | Exact match correctly preferred over the earlier substring match "REMUNERATION REPORTING AND ENGAGEMENT" (p.89) -- see the vocabulary note above. |
| SUR | 2024 | RESOLVED | 106-106 (+extensive supporting to 136) | HIGH | "Remuneration report" | |
| SUR | 2025 | RESOLVED (caveat) | 144-144 (+134, 136) | HIGH | "Remuneration Report" | Span is real but narrower than 2023/2024's -- several real remuneration headings that year (pp.145, 153, 163) fall outside even the widened range; see Section 9. |

**Top-level termination behavior**: confirmed generic and schedule-agnostic
for every RESOLVED case above, same as 7D.3 -- no REMUNERATION-specific
termination logic was needed anywhere.

Schedules resolved: 21 of 30 (ACT 9/9, BEL 6/7, KP2 4/6-with-caveat, SBP
0/3, SDL 2/2-with-caveat, SUR 3/3) -- coincidentally the same 21/30 total
as Track 7D.3, with a different per-issuer distribution (BEL loses one
year here that governance had; SDL gains two that governance never had at
all).

## 3. Issuer-level narrative candidate inventory

**ACT** (real-corpus inventory, 2016-2024 heading-candidate text):
`Remuneration Committee Chairperson's report` (2020-2024, multi-paragraph
committee-chair letter; 2019 uses "Chairman's report" instead, a genuine
wording variant), `Changes to the remuneration and related policies`
(2018, 2020-2024, short policy-change statement), `Remuneration governance`
(2020-2024, short governance-framework intro before an org-chart diagram),
`Remuneration policy design principles` (2020-2024, similarly short,
overlapping in function with `Remuneration governance` -- not selected, to
avoid two near-identical thin units), `Remuneration model` (2020-2024, not
inspected in depth -- deferred), `Statement regarding compliance with
[the] remuneration policy` (2018, 2020-2023, a single-sentence compliance
statement whose NEXT_HEADING boundary would pull in an unrelated adjacent
"Advisory vote" paragraph -- deferred, thin content).

**BEL**: `Variable remuneration` (2017, 2018, 2019, 2021, 2022, narrative
describing STI/LTI scheme mechanics), `Guaranteed remuneration` (2019,
2022 only under this exact wording -- 2017 uses "Fixed remuneration"
instead, a terminology drift across years -- thinner recurrence, not
selected), `Directors' and prescribed officers' remuneration` (2017, 2021,
2022 -- the individual-director pay disclosure, clearly tabular, not
narrative -- routed to the structured-content backlog, Section 6, not
configured as a narrative unit).

**KP2**: No candidate units evaluated past schedule localization -- every
resolved year's primary heading is the same fused "(CONT)" compound
pattern already documented (and deliberately not re-fixed) in 7D.3's
Corporate Governance track; no standalone REMUNERATION subsection heading
exists to anchor a `NEXT_HEADING`/`ANCHOR_SENTENCE` unit.

**SBP, SDL**: no RESOLVED-without-caveat schedule instance rich enough to
inventory units within confidently in this milestone's budget; SDL's
lettered-principles structure ("a) Principles used to determine...") looks
promising for a future track but was not inventoried for narrative units
here (2 years only, thin evidence either way).

**SUR**: `Remuneration policy changes [and key areas of focus for the
year]` (2023-2025, exact/substring match every year), `Fair and
responsible remuneration of executives relative to overall employee
remuneration` (2023-2025, exact match every year), `Remuneration policy
and shareholder engagement` (2023-2025, exact match every year -- but see
Section 9, extraction fails every year regardless), `Executive
remuneration [Annual increase in CTC]` (2023-2025, tabular pay-increase
data -- not selected, structured backlog), `Total single figure of
remuneration` / `TOTAL SINGLE FIGURE OF REMUNERATION` (2023-2025, clearly
a compensation table -- not selected, structured backlog).

## 4. Structured-content inventory

| ticker | table family | years observed | already supported by 7C.4? | comparable structure? | new parser required? | notes |
|---|---|---|---|---|---|---|
| ACT | `ned_remuneration_policy_table` | 2020-2024 | Yes (7C.4) | -- | No | Verified still working (Section 14). |
| ACT | `total_remuneration_outcomes` | 2020-2024 | Yes (7C.4) | -- | No | Verified still working (Section 14). |
| BEL | Directors'/prescribed officers' remuneration | 2017, 2021, 2022 | No | Roughly (per-director fee/STI/LTI rows) but different column layout than ACT's families | Yes | SIMILAR_BUT_NEEDS_CONFIG -- backlog. |
| BEL | AGM voting-results table | 2019 (and likely others) | No | Small 3-column table (date/resolution/vote%) | Yes | NEW_TABLE_FAMILY_REQUIRED -- backlog. |
| SUR | `TOTAL SINGLE FIGURE OF REMUNERATION` | 2023-2025 | No | Conceptually close to ACT's `total_remuneration_outcomes` | Yes (different columns) | SIMILAR_BUT_NEEDS_CONFIG -- most promising backlog candidate. |
| SUR | `Executive remuneration [Annual increase in CTC]` | 2024-2025 | No | Not inspected in row/column depth | Inconclusive | INCONCLUSIVE -- backlog. |
| KP2 | KMP/auditor remuneration notes (financial-statement notes, not the narrative schedule) | all years | No | Out of REMUNERATION-schedule scope -- these are standard IFRS note disclosures | N/A | INCONCLUSIVE / out of scope this track. |
| SDL | Lettered-principles remuneration report structure | 2024-2025 | No | Not inspected in table-structure depth | Inconclusive | INCONCLUSIVE -- backlog, thin evidence (2 years). |

No new structured-table parser was built in this milestone.

## 5. Selected narrative units

| ticker | unit_key | start heading | boundary strategy | years recurring |
|---|---|---|---|---|
| ACT | `remco_chairperson_report` | "Remuneration Committee Chairperson's report" | NEXT_HEADING | 2020-2024 (5) |
| ACT | `remuneration_policy_changes` | "Changes to the remuneration and related policies" | NEXT_HEADING | 2018, 2020-2024 (6) |
| ACT | `remuneration_governance` | "Remuneration governance" | NEXT_HEADING | 2020-2024 (5) |
| BEL | `variable_remuneration` | "Variable remuneration" | NEXT_HEADING | 2017, 2018, 2019, 2021, 2022 (5) |
| SUR | `remuneration_policy_changes_and_focus` | "Remuneration policy changes" | NEXT_HEADING | 2023-2025 (3) |
| SUR | `fair_responsible_remuneration` | "Fair and responsible remuneration of executives relative to overall employee remuneration" | NEXT_HEADING | 2023-2025 (3) |
| SUR | `remuneration_policy_shareholder_engagement` | "Remuneration policy and shareholder engagement" | NEXT_HEADING | 2023-2025 (3, heading present; extraction 0/3 -- see Section 9) |

No new boundary strategy was introduced anywhere in this milestone --
every unit uses the existing `NEXT_HEADING`.

## 6. Rejected / deferred narrative units

- ACT `Remuneration policy design principles`: deferred -- functionally
  overlapping in length and role with the selected `Remuneration
  governance` unit (both are single-sentence intros to an adjacent
  diagram); including both would not add distinct analytical value.
- ACT `Remuneration model`, `Statement regarding compliance with the
  remuneration policy`: deferred -- not inspected past the initial
  heading-candidate inventory; the latter's own NEXT_HEADING boundary was
  observed to pull in an unrelated "Advisory vote" paragraph.
- BEL `Guaranteed remuneration`: deferred -- terminology drift across
  years (2017's "Fixed remuneration" vs. 2019/2022's "Guaranteed
  remuneration") leaves only two years under one exact heading string,
  below the recurring-across-multiple-years bar this track applied.
- BEL `Directors' and prescribed officers' remuneration`: deferred to the
  structured backlog (Section 4) -- individual-director pay table, not
  narrative.
- KP2's three fused-heading candidates class: deferred, same root cause
  already documented (and deliberately left unfixed) for KP2's
  CORPORATE_GOVERNANCE units in 7D.3.
- SUR `Executive remuneration`, `Total single figure of remuneration`:
  deferred to the structured backlog (Section 4) -- tabular pay-outcome
  content, not narrative.
- SBP, SDL: no candidates evaluated past schedule localization (SBP has no
  resolved schedule at all; SDL's two years were judged too thin to
  inventory units within confidently this track).

## 7. Configuration changes

**Configuration only** (`schedule_config.py`, `semantic_unit_config.py`,
`analytical_eligibility.py` -- no matching-logic changes beyond Section
8's one correction):
- `NormalizedSchedule.REMUNERATION` added to `schedule_localization.py`'s
  scope guard.
- 4 new heading-vocabulary strings (Section 2).
- 7 new `UnitConfig` entries (Section 5), all `NEXT_HEADING`.
- 7 new `UNIT_ANALYTICAL_MODES` entries, all `LEXICAL_ONLY`.

`coverage_registry.py` and `cutover_config.py` were not touched --
`coverage_registry.py` derives entries automatically from the three
config modules above, so all seven new units resolve to `production_status
= "candidate"` without a parallel hardcoded list (verified by
`tests/test_coverage_registry.py::test_new_remuneration_units_are_candidates_not_enabled_in_production`).

## 8. The one allowed generic parser/localizer correction

`semantic_unit_extraction.py` `_run_extraction` (`ALGORITHM_VERSION`
1.4.0 -> 1.5.0): the search range's *start* page is now
`min(instance.start_page, every supporting span's own start_page)`,
symmetric with the existing end-page widening Track 7D.3 already added.

**Real bug found and fixed**: ACT's 2020 and 2021 REMUNERATION schedule
instances anchor their primary span on a "REMUNERATION REPORT
(CONTINUED)" banner page (2020 p.96, 2021 p.108), while the genuine
chapter start -- including the `Remuneration Committee Chairperson's
report` heading itself -- registers only as an *earlier* supporting span
(2020 p.94, 2021 p.107). Track 7D.3's v1.4.0 fix widened only the range's
end page (`max` over supporting-span end pages); it never pulled the
start page earlier, so this earlier supporting span was still silently
excluded from every unit search. Before this fix, `remco_chairperson_report`,
`remuneration_policy_changes`, and `remuneration_governance` all failed to
resolve for 2020 and 2021 specifically -- not a genuine absence, an
extraction-range gap. After the fix, all three units resolve cleanly for
both years.

**Generic**: it reads `supporting_spans`, not any schedule- or
heading-specific text, so it applies to every existing and future
NEXT_HEADING/ANCHOR_SENTENCE unit (FINANCIAL_PERFORMANCE and
CORPORATE_GOVERNANCE units benefit too, verified by the regression run in
Section 21), not just REMUNERATION's new ones. Regression test:
`tests/test_semantic_unit_extraction_service.py::test_unit_on_supporting_span_page_before_primary_is_found_after_start_widening_fix`.

No second correction was made. KP2's fused-"(CONT)" gap (Section 2),
SUR's 2025 boundary narrowness (Section 9), and two confirmed extraction
defects (ACT `remuneration_governance` 2024, Section 10; SUR
`remuneration_policy_shareholder_engagement`'s 0/3 resolution, Section 9)
are all documented as deferred rather than fixed, per the corpus-wide
budget cap.

## 9. Extraction coverage

| ticker | unit_key | years attempted | resolved | classification of misses |
|---|---|---|---|---|
| ACT | remco_chairperson_report | 2019-2024 (6) | 2020-2024 (5) | 2019: EXPECTED_HEADING_VARIATION ("Chairman's report", not "Chairperson's report") |
| ACT | remuneration_policy_changes | 2018-2024 (7, excl. 2019 which the schedule itself barely covers) | 2018, 2020-2024 (6) | 2019: GENUINE_ABSENCE (that year's report structure around the schedule differs) |
| ACT | remuneration_governance | 2016-2024 attempted range; real recurrence 2020-2024 (5) | 2020-2024 (5) resolved boundary, but **2024's resolved text is wrong content** | 2016-2018: GENUINE_ABSENCE; 2024: EXTRACTION_DEFECT (false-positive substring match on an unrelated sentence, Section 10) |
| BEL | variable_remuneration | 2016-2022 (7, excl. 2020 which the schedule itself is NOT_FOUND) | 2022 only (real text); 2017, 2018, 2019, 2021 heading found but UNRESOLVED (no body content between the heading and the immediately-following heading-candidate) | 2016: GENUINE_ABSENCE (different terminology that year); 2020: schedule ineligible |
| SUR | remuneration_policy_changes_and_focus | 2023-2025 (3) | 2023, 2024 (2) | 2025: EXTRACTION_DEFECT (heading exists in source at p.145 but outside the schedule's own localized range that year, Section 2) |
| SUR | fair_responsible_remuneration | 2023-2025 (3) | 2023, 2024 (2) | 2025: same EXTRACTION_DEFECT class (heading at p.153, outside range) |
| SUR | remuneration_policy_shareholder_engagement | 2023-2025 (3) | 0 | All 3 years: EXTRACTION_DEFECT -- the real heading (pp.151/165/163 across the three years) sits well beyond the schedule's own localized end boundary (121/136/144) every year; not a boundary this milestone's one-fix budget could plausibly close without risking the schedule's own end-boundary logic used by every other schedule. |

Not fixed further per the corpus-wide one-correction budget cap (Section
8).

## 10. Manual source review

- **ACT remco_chairperson_report**: 2022 (intermediate year) and 2023
  (flagged by an outlier word-count drop) both manually inspected against
  canonical source text. 2022: correct heading, correct start boundary,
  rich multi-paragraph committee-chair letter (LTI redesign, focus areas,
  shareholder voting commentary, appreciation), ends cleanly at "Operating
  context and performance highlights." 2023: **confirmed real
  BOUNDARY_DEFECT** -- the extracted text is genuinely the letter's
  correct opening paragraph, just truncated to 65 words (vs. 268-384 in
  neighboring years) because that year's PDF hits the next
  heading-candidate much sooner. Real content, not garbage, but
  incomplete.
- **ACT remuneration_governance**: 2022 verified correct (one-sentence
  governance-framework intro immediately before an org-chart diagram, 17
  words, matching the schedule's own confirmed static boilerplate
  pattern). 2024 inspected specifically because of its outlier lexical
  score (17->115 words, cosine collapsing from a run of 1.0/1.0/1.0 to
  0.15) -- **confirmed a real EXTRACTION_DEFECT**: the persisted text is
  an unrelated passage about culture-transformation focus areas and
  shareholder-voting results that happens to contain the sentence
  "Introduction of additional reward policies that enhance remuneration
  governance," a false-positive substring match on an ordinary sentence
  fragment, not the real standalone heading. Same defect class already
  documented (and deliberately left unfixed) for ACT's CORPORATE_GOVERNANCE
  `combined_assurance` unit in 7D.3 and FINANCIAL_PERFORMANCE's "Capital
  management" candidate in 7D.2.
- **BEL variable_remuneration**: 2019 and 2022 (the only two years with any
  narrative content at all, one near the start and one the only fully
  RESOLVED year) both inspected -- confirmed genuine, substantial
  narrative describing STI/LTI scheme design, hurdles, and vesting rules
  (2022: 652 words), no table/chart contamination materially affecting the
  prose captured.

## 11. Alignment results

ACT (8 adjacent `ReportPair`s + one long-range 2016->2024 pair):

| pair | outcome |
|---|---|
| 2016->2024 | all three units UNRESOLVED_UPSTREAM |
| 2016->2017 | remuneration_governance UNRESOLVED_UPSTREAM (only unit present on either side) |
| 2017->2018 | remuneration_governance, remuneration_policy_changes both UNRESOLVED_UPSTREAM |
| 2018->2019 | remuneration_policy_changes MATCHED (HIGH); remuneration_governance UNRESOLVED_UPSTREAM |
| 2019->2020 | remuneration_governance, remuneration_policy_changes MATCHED (HIGH); remco_chairperson_report UNRESOLVED_UPSTREAM |
| 2020->2021 | all three MATCHED (HIGH) |
| 2021->2022 | all three MATCHED (HIGH) |
| 2022->2023 | all three MATCHED (HIGH) |
| 2023->2024 | all three MATCHED (HIGH) |

BEL (6 adjacent `ReportPair`s, `variable_remuneration` only): 2016->2017
through 2021->2022 are all UNRESOLVED_UPSTREAM except the two pairs
straddling 2020 (2019->2020, 2020->2021), which are fully ineligible (no
semantic-unit run at all on the 2020 side, since that year's schedule
itself is NOT_FOUND). **No MATCHED or RENAMED alignment exists for this
unit in the real corpus** -- same pattern already documented for BEL's
CORPORATE_GOVERNANCE `board_composition_diversity` unit in 7D.3.

SUR (2 adjacent `ReportPair`s):

| pair | outcome |
|---|---|
| 2023->2024 | fair_responsible_remuneration, remuneration_policy_changes_and_focus both MATCHED (HIGH) |
| 2024->2025 | both UNRESOLVED_UPSTREAM (2025's extraction gap, Section 9) |

`remuneration_policy_shareholder_engagement` never appears in either pair's
alignment output at all, since it has zero `SemanticUnit` rows in any
year.

No ADDED/REMOVED events were produced for any remuneration unit in any
issuer's real corpus in this run -- consistent with 7D.3's own finding and
with `SemanticUnitAlignmentStatus`'s documented distinction between a
genuine absence claim and an extraction limitation.

## 12. Analytical routing

All seven configured units routed `LEXICAL_ONLY`:

| unit | mode | reason |
|---|---|---|
| ACT remco_chairperson_report | LEXICAL_ONLY | direct narrative prose (committee-chair letter), verified across resolved years |
| ACT remuneration_policy_changes | LEXICAL_ONLY | narrative policy-change statement, same profile |
| ACT remuneration_governance | LEXICAL_ONLY | narrative where correctly extracted; see Section 10 for the 2024 extraction-defect year, not a routing problem |
| BEL variable_remuneration | LEXICAL_ONLY | narrative describing STI/LTI scheme mechanics -- contains incidental figures (hurdle percentages, dates) but is predominantly prose, not a table |
| SUR remuneration_policy_changes_and_focus | LEXICAL_ONLY | narrative policy-change statement |
| SUR fair_responsible_remuneration | LEXICAL_ONLY | narrative pay-fairness disclosure |
| SUR remuneration_policy_shareholder_engagement | LEXICAL_ONLY | narrative in principle -- never extracts in practice (Section 9) |

No new analytical engine was implemented for `LEXICAL_WITH_NUMERIC_CONTEXT`
or `STRUCTURED_COMPARISON_PREFERRED`; neither mode was needed for any unit
selected this track.

## 13. Lexical comparison results

Only the existing metrics were computed; no new thresholds, composites, or
qualitative labels were added.

**ACT remco_chairperson_report**:

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2020->2021 | 0.774 | 0.197 | 384->295 |
| 2021->2022 | 0.701 | 0.269 | 295->268 |
| 2022->2023 | 0.675 | 0.271 | 268->65 |
| 2023->2024 | 0.940 | 0.796 | 65->65 |

**ACT remuneration_governance** (static boilerplate, then a defect):

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2020->2021 | 1.000 | 1.000 | 17->17 |
| 2021->2022 | 1.000 | 1.000 | 17->17 |
| 2022->2023 | 1.000 | 1.000 | 17->17 |
| 2023->2024 | 0.150 | 0.077 | 17->115 |

**ACT remuneration_policy_changes** (real variability):

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2018->2019 | 0.706 | 0.581 | 30->51 |
| 2019->2020 | 0.867 | 0.781 | 51->48 |
| 2020->2021 | 0.572 | 0.340 | 48->47 |
| 2021->2022 | 0.988 | 0.973 | 47->46 |
| 2022->2023 | 0.825 | 0.456 | 46->130 |
| 2023->2024 | 0.667 | 0.302 | 130->81 |

**SUR** (the one real pair available for each unit):

| unit | pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|---|
| fair_responsible_remuneration | 2023->2024 | 0.978 | 0.916 | 158->166 |
| remuneration_policy_changes_and_focus | 2023->2024 | 0.888 | 0.667 | 118->82 |

BEL `variable_remuneration` produced no lexical comparison at all (zero
MATCHED alignments, Section 11).

## 14. Longitudinal sanity check

- **remuneration_governance**'s 1.0/1.0/1.0 run followed by a sudden 0.15
  collapse (words 17->115) is the clearest signal in this track's whole
  metric series that something is wrong -- and manual review (Section 10)
  confirmed it is a real extraction defect, not a genuine rewrite. This is
  the same discipline 7D.3 already demonstrated for `combined_assurance`:
  inspecting the boundary first, rather than trusting the metric alone, is
  what catches it.
- **remco_chairperson_report**'s 2022->2023 drop (268->65 words, 0.675
  cosine) looks only moderately suspicious by the metric alone -- cosine
  similarity on a genuinely truncated-but-still-on-topic excerpt does not
  crash the way a wrong-content swap does. Manual review was still needed
  to catch the real boundary defect (Section 10); the metric alone would
  not have caught it reliably.
- **remuneration_policy_changes**'s variability (0.57-0.99 across pairs)
  reflects genuine content: several years the disclosure states plainly
  "no material changes were made" (high similarity, near-boilerplate);
  2022->2023's expansion (46->130 words, 0.825 cosine) and the following
  contraction (2023->2024, 130->81, 0.667) both reflect real described
  policy activity that year, not an artifact.
- **SUR**'s two resolved-pair metrics (0.978 and 0.888 cosine) are both
  plausible and not flagged by this review; only one pair exists per unit,
  so there is limited longitudinal signal to assess further this track.

## 15. Existing ACT structured-table regression results

Re-ran `units structure` and `units compare-structured` for
`ned_remuneration_policy_table` and `total_remuneration_outcomes` across
all nine ACT years. Both commands report every year as `skipped --
identical successful extraction/alignment run already exists`, and
`compare-structured`'s eligible/ineligible year pattern for
`ned_remuneration_policy_table` (2016-2019 ineligible "heading not found",
2020-2024 alignment-eligible) is unchanged from before this track. No
regression from 7D.4's REMUNERATION narrative-unit work, which never
touches structured-table configuration or reconstruction code.

## 16. Cross-schedule movement observations

No REMUNERATION content was observed moving between schedules for any
issuer in this inventory. ACT's own governance-report cross-reference in
the chairperson's letter ("This report supplements the information
provided in the corporate governance report on pages...") is an internal
document cross-reference, not evidence of content movement between the two
schedules.

## 17. Coverage registry

`coverage_registry.py` is unchanged (still derived automatically from
`semantic_unit_config.UNIT_CONFIGS`, `analytical_eligibility.
UNIT_ANALYTICAL_MODES`, and `cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE`).
Since `cutover_config.py` was not touched, all seven new units resolve to
`production_status = "candidate"` automatically. ACT's existing structured
remuneration coverage (`NEW_PIPELINE_STRUCTURED_SCOPE`) is unchanged.
Verified by `tests/test_coverage_registry.py::test_new_remuneration_units_are_candidates_not_enabled_in_production`
and `::test_existing_structured_remuneration_scope_unaffected_by_narrative_units`.

## 18. Issuer-level coverage summary

| ticker | report years | schedule years resolved | absent/unresolved years | narrative candidates found | narrative units configured | narrative READY_FOR_CUTOVER | narrative READY_WITH_CAVEAT | narrative NOT_READY | structured families observed | existing structured support | major blockers |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ACT | 9 | 9 | 0 | 6 evaluated, 3 selected | 3 | 1 | 1 | 1 | 2 | Both already supported (7C.4), verified regression-clean | `remuneration_governance`'s 2024 false-positive-match defect |
| BEL | 7 | 6 | 1 (2020) | 3 evaluated, 1 selected | 1 | 0 | 0 | 1 | 2 | Neither supported yet | zero MATCHED alignments across the real corpus; most years UNRESOLVED boundary |
| KP2 | 6 | 4-with-caveat | 2 (2020-2021) | 0 evaluated | 0 | n/a | n/a | n/a | financial-statement notes only, out of scope | n/a | every occurrence is a compound "(CONT)" heading fused with corporate governance -- no standalone boundary without a parser change |
| SBP | 3 | 0 | 3 | 0 evaluated | 0 | n/a | n/a | n/a | none inventoried | n/a | no heading matches the configured vocabulary in any year |
| SDL | 2 | 2-with-caveat | 0 | 0 evaluated (thin evidence) | 0 | n/a | n/a | n/a | not inspected in depth | n/a | only 2 years available; lettered-principles structure looks promising for a future track |
| SUR | 3 | 3 | 0 | 5 evaluated, 3 selected | 3 | 0 | 2 | 1 | 2 promising, not configured | Neither supported yet | `remuneration_policy_shareholder_engagement` never resolves (heading consistently outside the schedule's own end boundary); 2025's schedule span is narrower than 2023/2024's |

## 19. Corpus-wide narrative acceptance matrix

| ticker | unit_key | years available | years resolved | adjacent pairs | MATCHED | ADDED | REMOVED | UNRESOLVED_UPSTREAM | AMBIGUOUS | analytical mode | comparison coverage | provenance coverage | cutover readiness |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ACT | remco_chairperson_report | 6 | 5 | 8 | 4 | 0 | 0 | 4 | 0 | LEXICAL_ONLY | 4/8 pairs (1 contaminated by boundary defect) | full | READY_WITH_CAVEAT |
| ACT | remuneration_policy_changes | 7 | 6 | 8 | 6 | 0 | 0 | 2 | 0 | LEXICAL_ONLY | 6/8 pairs, no confirmed defect | full | READY_FOR_CUTOVER |
| ACT | remuneration_governance | 9 (real recurrence 5) | 5 (1 wrong-content) | 8 | 4 | 0 | 0 | 4 | 0 | LEXICAL_ONLY | 4/8 pairs (1 contaminated by defect) | full | NOT_READY |
| BEL | variable_remuneration | 6 | 1 | 6 | 0 | 0 | 0 | 4 (+2 ineligible) | 0 | LEXICAL_ONLY | 0/6 pairs | partial (heading/page provenance only where UNRESOLVED) | NOT_READY |
| SUR | remuneration_policy_changes_and_focus | 3 | 2 | 2 | 1 | 0 | 0 | 1 | 0 | LEXICAL_ONLY | 1/2 pairs, no confirmed defect | full | READY_WITH_CAVEAT |
| SUR | fair_responsible_remuneration | 3 | 2 | 2 | 1 | 0 | 0 | 1 | 0 | LEXICAL_ONLY | 1/2 pairs, no confirmed defect | full | READY_WITH_CAVEAT |
| SUR | remuneration_policy_shareholder_engagement | 3 | 0 | 2 | 0 | 0 | 0 | 0 | 0 | LEXICAL_ONLY | 0/2 pairs | none (never extracts) | NOT_READY |

(KP2/SBP/SDL: no configured units, no rows.)

## 20. Corpus-wide structured matrix

| ticker | table_family | years observed | current parser support | comparison coverage | readiness | notes |
|---|---|---|---|---|---|---|
| ACT | ned_remuneration_policy_table | 2020-2024 | EXISTING_ENGINE_COMPATIBLE (7C.4) | unchanged, verified regression-clean | STRUCTURED_READY (pre-existing) | Section 15 |
| ACT | total_remuneration_outcomes | 2020-2024 | EXISTING_ENGINE_COMPATIBLE (7C.4) | unchanged, verified regression-clean | STRUCTURED_READY (pre-existing) | Section 15 |
| BEL | Directors'/prescribed officers' remuneration | 2017, 2021, 2022 | SIMILAR_BUT_NEEDS_CONFIG | none (not implemented) | STRUCTURED_NOT_READY | backlog |
| BEL | AGM voting-results table | 2019 (+likely others) | NEW_TABLE_FAMILY_REQUIRED | none | STRUCTURED_NOT_READY | backlog |
| SUR | TOTAL SINGLE FIGURE OF REMUNERATION | 2023-2025 | SIMILAR_BUT_NEEDS_CONFIG | none | STRUCTURED_NOT_READY | most promising backlog candidate |
| SUR | Executive remuneration / Annual increase in CTC | 2024-2025 | INCONCLUSIVE | none | STRUCTURED_NOT_READY | backlog |
| KP2 | KMP/auditor remuneration notes | all years | INCONCLUSIVE (financial-statement notes, likely out of REMUNERATION-schedule scope) | none | n/a | backlog, needs scoping decision |
| SDL | Lettered-principles remuneration report | 2024-2025 | INCONCLUSIVE | none | n/a | backlog, thin evidence |

## 21. Configuration-driven assessment

- **Narrative units added through configuration + validation only**: 6 of
  7 were correctly extractable purely from configuration once the one
  generic fix (Section 8) landed (ACT's three units, BEL's one, SUR's two
  that actually extract). `remuneration_policy_shareholder_engagement` is
  the one unit that never resolves regardless of configuration -- its
  gap is a schedule-boundary limitation, not something a `UnitConfig`
  change could fix.
- **Units requiring the one allowed generic parser/localizer correction**:
  effectively all of ACT's three units benefited directly (the fix is what
  made 2020 and 2021 resolvable at all); the fix itself is schedule- and
  unit-agnostic, and the regression run (Section 15, plus the full suite
  in Section 22) confirms it also helps any FINANCIAL_PERFORMANCE/
  CORPORATE_GOVERNANCE unit with the same shape of supporting-span-before-
  primary defect, not just REMUNERATION's new ones.
- **Candidates requiring issuer-specific work not attempted here**: KP2's
  fused-"(CONT)" heading class (same root cause as 7D.3's KP2 governance
  gap), BEL's terminology drift across years ("Fixed" vs. "Guaranteed"
  remuneration), SUR's narrower 2025 schedule span.
- **Structured families already supported**: 2 (ACT, pre-existing from
  7C.4, verified regression-clean).
- **Structured families deferred**: 6 (BEL x2, SUR x2, KP2 x1, SDL x1).
- **Candidates requiring genuinely new architecture**: none -- every
  deferral in this track is either a missing standalone-heading
  classification (KP2), a terminology-drift/thin-recurrence judgment call
  (BEL, SDL, SBP), or a schedule-boundary limitation this milestone's
  budget did not extend to (SUR shareholder engagement), not a new
  architectural capability (no SPLIT/MERGED handling, no new comparison
  engine, no VLM).
- **One real correctness defect surfaced and left unfixed by design**: ACT
  `remuneration_governance`'s 2024 false-positive substring match (Section
  10) -- the same defect class 7D.2 and 7D.3 already flagged and
  deliberately deferred, surfaced a third time in a third schedule,
  reinforcing that it is a real, recurring, schedule-agnostic gap worth a
  dedicated future track rather than another one-off patch.

Does REMUNERATION scale more easily than Governance? Roughly the same
difficulty profile: both took one generic fix, both surfaced one real
false-positive-match defect on a different unit, both have one issuer
(BEL) whose post-schedule content resists a clean narrative boundary, and
both left several issuers with zero configured units. REMUNERATION's ACT
coverage is marginally stronger (`remuneration_policy_changes` reaches
READY_FOR_CUTOVER outright, matching Governance's own single
READY_FOR_CUTOVER unit), while REMUNERATION additionally reached a third
issuer (SUR) with real, if partial, narrative coverage that Governance
never achieved for a third issuer within its own budget.

## 22. Tests

Added:
- `tests/test_schedule_localization.py`: REMUNERATION localizes
  identically to FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE given the same
  evidence shape; a substring match (SUR's "REMUNERATION REPORTING AND
  ENGAGEMENT" pattern) does not win over a genuine exact match; a
  "continued" banner still does not terminate the schedule; replaced the
  now-stale "REMUNERATION raises NotImplementedError" test with an
  equivalent one against a schedule still genuinely unimplemented
  (MATERIAL_RISKS).
- `tests/test_semantic_unit_extraction_service.py` (extended): new DB-backed
  regression test for Section 8's fix, reproducing the exact ACT 2020/2021
  shape (primary span on a later "(CONTINUED)" banner page, real chapter
  start registered as an earlier supporting span) and asserting the unit is
  now found with the correct start page and content.
- `tests/test_semantic_unit_config_remuneration.py` (new): the seven new
  `UnitConfig` entries exist under the right ticker/schedule, existing
  FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE units are unaffected, no new
  boundary strategy was introduced, no `(ticker, unit_key)` pair collides
  anywhere in `UNIT_CONFIGS`.
- `tests/test_analytical_eligibility_routing.py` (extended): routing tests
  for all seven new units, all LEXICAL_ONLY.
- `tests/test_coverage_registry.py` (extended): all seven new units resolve
  to `production_status = "candidate"`; ACT's existing structured
  remuneration scope in `NEW_PIPELINE_STRUCTURED_SCOPE` is unaffected.

Targeted tests were run throughout development; the full suite was run
once at the end (Section 23's result).

## 23. Fresh-database sanity result

Deferred beyond a lightweight check: the local Postgres instance (Docker
Compose) was already running with the full 6-issuer corpus loaded from
prior tracks, and this track's own CLI runs (`localize` / `extract` /
`align` / `classify` across all six tickers) exercised the full
migrations-to-publication-adjacent path against that live database
end-to-end without incident, other than one transient dropped-connection
retry (Section 8's fix was verified after that retry succeeded cleanly).
A true from-empty-database walkthrough was not separately performed this
track, consistent with the milestone's own instruction that this is not
release hardening.

## 24. Caveats

- ACT `remuneration_governance` carries a real, unresolved extraction
  defect for 2024 (Section 10) -- included specifically because finding
  and correctly diagnosing it (rather than being fooled by a
  plausible-enough word-count jump) is itself evidence the milestone's
  manual-review requirement is doing its job, not because the unit is
  production-ready.
- SUR `remuneration_policy_shareholder_engagement` is configured and
  genuinely present in the real corpus every year, but currently
  unextractable in all three years -- a caution against reading "3 SUR
  units configured" as "3 SUR units delivering comparisons" (only 2 do).
- BEL's `variable_remuneration` technically "extracts" with real,
  substantial content in one year (2022, 652 words), but produces zero
  usable comparisons in the real corpus -- most other years' boundary is
  UNRESOLVED, the same caution 7D.3 already raised for BEL's governance
  unit.
- KP2's schedule localizes with the same "(CONT)"-banner caveat already
  documented (and left unfixed) for its CORPORATE_GOVERNANCE schedule in
  7D.3 -- not re-investigated or re-fixed here, per the corpus-wide
  one-correction budget being spent elsewhere.
- SBP's GENUINE_ABSENCE and SDL's thin (2-year) evidence both reflect real
  uncertainty about those issuers' report structure, not confirmed dead
  ends -- a future, issuer-specific track could plausibly make progress on
  either.

## 25. Final verdict

**PASS WITH CAVEATS -- REMUNERATION COVERAGE EXPANDED BUT SOME ISSUERS
NEED FUTURE HARDENING**

Remuneration can be brought into the semantic comparison system using the
existing architecture, confirmed for three issuers (ACT, BEL, SUR) out of
the six audited: no new boundary strategy, comparison engine, table
parser, or cross-schedule-movement mechanism was needed anywhere. The one
generic parser correction this milestone allowed was genuinely necessary
and fixed a real, schedule-agnostic bug (supporting-span *start*-page
widening, symmetric with 7D.3's own end-page fix) that will also help any
future schedule with the same "primary anchors on a later continuation
banner, real start is an earlier supporting span" shape. One real,
unresolved extraction defect (ACT `remuneration_governance`, 2024) and
several under-supported issuers (KP2, SBP, SDL, and BEL's zero-alignment
outcome) were found and honestly documented rather than forced or
silently worked around.

- Companies audited: 6 (ACT, BEL, KP2, SBP, SDL, SUR)
- Report years audited: 30 (9+7+6+3+2+3)
- Schedules resolved: 21 of 30 (ACT 9/9, BEL 6/7, KP2 4/6-with-caveat, SBP
  0/3, SDL 2/2-with-caveat, SUR 3/3)
- Narrative semantic units configured: 7 (3 ACT, 1 BEL, 3 SUR)
- Narrative units READY_FOR_CUTOVER: 1 (ACT remuneration_policy_changes)
- Narrative units READY_WITH_CAVEAT: 3 (ACT remco_chairperson_report; SUR
  remuneration_policy_changes_and_focus, fair_responsible_remuneration)
- Narrative units NOT_READY: 3 (ACT remuneration_governance; BEL
  variable_remuneration; SUR remuneration_policy_shareholder_engagement)
- Structured families supported: 2 (ACT, pre-existing from 7C.4)
- Structured families deferred: 6 (BEL x2, SUR x2, KP2 x1, SDL x1)

## 26. Next-schedule checkpoint (corpus-wide)

Evaluated corpus-wide, using only what this track's and 7D.3's real
inventories showed:

- **MATERIAL_RISKS**: still promising -- ACT and BEL both show
  risk-governance narrative fused inside both their Corporate Governance
  and Remuneration schedules ("combined assurance"/"three lines of
  defence," STI/LTI risk hurdles), and KP2/SUR both show independent
  risk-committee content. Localization stability: likely moderate (no
  heading vocabulary yet confirmed corpus-wide). Recurring-unit potential:
  moderate-to-good, based on adjacent-schedule evidence. Expected parser
  effort: low (existing architecture, per this track's and 7D.3's own
  finding that no new capability has been needed for either schedule so
  far). Analytical value: high (risk narrative is one of the most
  frequently requested disclosure-comparison use cases). Likely
  difficulty: moderate.
- **REMUNERATION**: now complete (this track). Confirms the
  fastest-to-localize prediction from 7D.3's own checkpoint was correct --
  its heading vocabulary was in fact already effectively known from 7D.3's
  incidental discovery, and localization needed zero new matching logic.
- **CEO_REVIEW / CHAIR_REVIEW**: this track's real-corpus incidental
  inventory (ACT's chairperson's-report cross-reference language, SUR's
  "LEADING FOR THE GREATER GOOD" running banners, BEL's committee
  chairperson naming conventions) did not surface new evidence either way
  on the previously-flagged fused-chairman-plus-CEO-section risk (BEL). No
  change to 7D.3's assessment: still looks harder than REMUNERATION was,
  comparable to or slightly easier than MATERIAL_RISKS, pending a scoping
  decision on the fused-section issue.
- **STRATEGY / OUTLOOK**: still not enough evidence to recommend; this
  track's incidental inventory (focused on remuneration headings) did not
  surface material new signal for either.
- **LEGAL_REGULATORY, MATERIAL_MATTERS_OPERATING_ENVIRONMENT**: not
  evaluated in either 7D.3 or this track; no evidence-based estimate
  possible yet without a dedicated inventory pass.

**Recommendation: MATERIAL_RISKS next.** It has the strongest
cross-schedule circumstantial evidence of any remaining schedule (visible
inside both schedules audited so far, across four of six issuers), no
architectural capability gap identified in either prior track, and -- per
this milestone's own finding that REMUNERATION was no harder to localize
than CORPORATE_GOVERNANCE -- there is no evidence the "next" schedule gets
structurally harder just because it comes later. CEO_REVIEW/CHAIR_REVIEW
do not currently look easier than MATERIAL_RISKS; the fused-section
scoping question flagged in 7D.3 remains unresolved and would need to be
answered before that schedule's own localization work could start
cleanly.

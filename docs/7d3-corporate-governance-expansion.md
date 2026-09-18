# Track 7D.3: Corporate Governance Expansion (corpus-wide)

## 0. Scope note

This track started scoped to ACT and BEL, then was amended mid-track to
cover every company currently in the corpus (ACT, BEL, KP2, SBP, SDL, SUR)
and every available report year for each. All work below reflects the
amended, corpus-wide scope. No production database change was made; no
schedule other than CORPORATE_GOVERNANCE was touched; the milestone's
one-bounded-generic-parser-correction budget was spent once, corpus-wide
(Section 5).

## 1. Schedule localization inventory (all issuers, all years)

`schedule_localization.localize_schedule` was extended to accept
`NormalizedSchedule.CORPORATE_GOVERNANCE` (previously it raised
`NotImplementedError` for anything but `FINANCIAL_PERFORMANCE`) -- the
algorithm itself is schedule-agnostic, driven entirely by
`SCHEDULE_HEADING_VOCABULARY`, so this was a scope-guard change, not a new
algorithm. Heading vocabulary added (pure config, not a parser change):
`"Corporate governance report"`, `"CORPORATE GOVERNANCE REPORT"`,
`"Corporate governance review"`, `"CORPORATE GOVERNANCE REVIEW"`,
`"Governance and functions of the Board"`.

| ticker | year | status | start_page | end_page | heading evidence | notes |
|---|---|---|---|---|---|---|
| ACT | 2016 | RESOLVED | 83 | 91 | "CORPORATE GOVERNANCE REPORT" | |
| ACT | 2017 | RESOLVED | 92 | 95 | "CORPORATE GOVERNANCE REPORT" | |
| ACT | 2018 | RESOLVED | 78 | 81 | "CORPORATE GOVERNANCE REPORT" | |
| ACT | 2019 | HEADING_VARIATION | 84 | 84 | "Corporate governance review" | That year's continuation banner is truncated to "GOVERNANCE REPORT (CONTINUED)" (missing "CORPORATE"), so it never matches the vocabulary and no supporting spans are found -- primary span is a single page. Real content extends to ~p.97. Not fixed (see Section 5's budget note): broadening the vocabulary to bare "GOVERNANCE REPORT" would false-positive-match unrelated banners seen elsewhere in the same corpus ("ENTERPRISE RISK MANAGEMENT GOVERNANCE STRUCTURES", "INFORMATION AND SECURITY GOVERNANCE"). |
| ACT | 2020 | RESOLVED | 81 | 81 (+ supporting spans) | "CORPORATE GOVERNANCE REVIEW" | |
| ACT | 2021 | RESOLVED | 91 | 105 | "Corporate governance review" | |
| ACT | 2022 | RESOLVED | 87 | 150 | "CORPORATE GOVERNANCE REPORT" | |
| ACT | 2023 | RESOLVED | 99 | 99 (+ supporting spans to 123) | "CORPORATE GOVERNANCE REPORT" | |
| ACT | 2024 | RESOLVED | 99 | 154 | "CORPORATE GOVERNANCE REPORT" | |
| BEL | 2016 | RESOLVED | 43 | 53 | "corporate governance report" | |
| BEL | 2017 | RESOLVED | 28 | 39 | "Corporate Governance Report" | |
| BEL | 2018 | RESOLVED | 38 | 38 (+ supporting spans to 47) | "Corporate governance report" | |
| BEL | 2019 | RESOLVED | 40 | 40 (+ supporting spans to 49) | "Corporate governance report" | |
| BEL | 2020 | RESOLVED | 41 | 50 | "Corporate governance report" | |
| BEL | 2021 | RESOLVED | 41 | 49 | "Corporate governance report" | |
| BEL | 2022 | RESOLVED | 44 | 53 | "Corporate governance report" | |
| KP2 | 2020 | RESOLVED (caveat) | 61 | 81 (+ supporting spans from 35) | "CORPORATE GOVERNANCE REPORT (CONT)" | Real content starts p.34-35; the primary anchor lands on a later "(CONT)" occurrence because KP2's "(CONT)" continuation marker (vs. ACT/BEL's "continued") isn't recognized by the existing continuation-banner check, and the true page-34/35 standalone heading is not classified as its own HEADING_CANDIDATE block (fused with body text). Union of primary+supporting still covers pp.35-81, a ~1-page gap at the very front -- not pursued as a fix (see Section 5). |
| KP2 | 2021 | RESOLVED (caveat) | 60 | 78 (+ supporting) | same pattern | |
| KP2 | 2022 | RESOLVED (caveat) | 40 | 56 (+ supporting) | same pattern | |
| KP2 | 2023 | RESOLVED (caveat) | 55 | 74 (+ supporting) | same pattern | |
| KP2 | 2024 | RESOLVED (caveat) | 60 | 61 (+ supporting) | same pattern | |
| KP2 | 2025 | RESOLVED (caveat) | 67 | 69 (+ supporting) | same pattern | |
| SBP | 2023 | INCONCLUSIVE | 2 | 2 | "Governance and functions of the Board" | Heading matches, but the resolved span is a single page 2 -- implausibly short for a substantive governance chapter (SBP's real corpus shows governance-adjacent content scattered at pp.29/31/36/38 under numbered subsection labels like "10.2 Risk framework and the governance of risk" that don't match a top-level CORPORATE_GOVERNANCE heading). Not forced into a schedule instance the corpus doesn't clearly support. |
| SBP | 2024 | INCONCLUSIVE | 2 | 2 | same pattern | |
| SBP | 2025 | INCONCLUSIVE | 2 | 2 | same pattern | |
| SDL | 2024 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | SDL's governance content is fused entirely into a running "ENVIRONMENTAL, SOCIAL AND GOVERNANCE (ESG)" banner/chapter, not a standalone Corporate Governance schedule -- confirmed no heading-candidate anywhere matches the configured vocabulary. |
| SDL | 2025 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | same pattern |
| SUR | 2023 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | Real governance content exists (e.g. "Remuneration governance", "IT governance" subsection labels) but none of it uses a top-level heading matching the configured vocabulary; SUR does not appear to name a single standalone "Corporate Governance Report" section the way ACT/BEL/KP2 do. |
| SUR | 2024 | GENUINE_ABSENCE | -- | -- | NOT_FOUND | same pattern |
| SUR | 2025 | INCONCLUSIVE | 4 | 4 | "King IVTM Report on Corporate Governance (King IVTM Report)" | Matched, but SUR 2025's extraction quality is broadly degraded for this report (the large majority of HEADING_CANDIDATE blocks across ~190 pages are running-banner fragments like "REVIEW"/"OUR"/"AND PURPOSE", not real headings) -- a single-page match against this noise floor is not trustworthy evidence of a real schedule boundary. Not pursued (would need issuer-specific extraction-quality work, out of this milestone's scope per Section 5). |

**Top-level termination behavior**: confirmed generic and schedule-agnostic
for every RESOLVED case above -- a "continued"-suffixed heading extends the
span (existing 7C.1 v1.0.4 rule); a same-text banner recurring 3+ times is
treated as boilerplate, not a boundary (existing 7C.1 v1.0.3 rule); a
structurally-smaller internal subsection heading does not terminate the
span (existing 7C.1b rule). No CORPORATE_GOVERNANCE-specific termination
logic was needed anywhere.

## 2. Candidate unit inventory (by issuer)

Only issuers with a RESOLVED (or RESOLVED-with-caveat) schedule can
meaningfully contribute unit candidates.

**ACT** (real-corpus inventory, 2016-2024 heading-candidate text):
`Information and security governance` (8 of 9 years), `Governance policies,
procedures and processes` (7 years), `Combined assurance` (5 years,
narrative), `Remuneration governance` (5 years -- **excluded**, see below),
`Overview of critical/key corporate governance practices` (front-matter and
back-matter both use similar phrasing in different years -- flagged as
`POSSIBLE_CROSS_SCHEDULE_MOVEMENT`, not selected), `Corporate governance
structure`-style org-chart headings (table/diagram, not narrative,
deprioritized).

**BEL**: `Board composition and diversity` (4 years, table-heavy),
`Corporate governance structure` (org-chart diagram, deprioritized), `Third
line of defence` (recurring 2019-2022, but a small diagram caption embedded
in unrelated "Risk management" body text with no standalone
HEADING_CANDIDATE boundary after it -- real subsequent sub-topics like "Tip
off reporting line"/"Engagement with stakeholders" are fused into
run-in-paragraph text rather than their own heading blocks, so NEXT_HEADING
over-captures unrelated content; deferred, same class of gap 7D.2 already
documented for BEL's post-2018 subsections).

**KP2**: `Board Leadership and Company Purpose`, `Division of
Responsibilities`, `Other Corporate Governance Matters` all recur across
2020-2025, but every occurrence is fused into a single compound
HEADING_CANDIDATE block together with the running "(CONT)" banner and a
"Provisions" sub-caption (e.g. `"CORPORATE GOVERNANCE REPORT (CONT) \n
BOARD LEADERSHIP AND COMPANY PURPOSE (CONT) \n Provisions"` as one block) --
there is no standalone heading to anchor a `NEXT_HEADING`/`ANCHOR_SENTENCE`
unit without a bespoke fused-heading-splitting parser change. Deferred.

**SBP, SDL, SUR**: no RESOLVED schedule instance to inventory units within
(see Section 1).

## 3. Selected units

Per-issuer unit selection (not a milestone-wide cap):

| ticker | unit_key | start heading | boundary strategy | years recurring |
|---|---|---|---|---|
| ACT | `information_security_governance` | "Information and security governance" | NEXT_HEADING | 2016, 2018-2024 (8) |
| ACT | `governance_policies_processes` | "Governance policies, procedures and processes" | NEXT_HEADING | 2018-2024 (7) |
| ACT | `combined_assurance` | "Combined assurance" | NEXT_HEADING | 2018, 2020-2024 (6) |
| BEL | `board_composition_diversity` | "Board composition and diversity" | NEXT_HEADING | 2018-2021 (4) |
| KP2 | -- | -- | -- | 0 configured (Section 2) |
| SBP | -- | -- | -- | 0 configured (Section 1) |
| SDL | -- | -- | -- | 0 configured (Section 1) |
| SUR | -- | -- | -- | 0 configured (Section 1) |

No new boundary strategy was introduced anywhere in this milestone.

## 4. Rejected / deferred candidates

- ACT `Remuneration governance`: excluded -- real-corpus inspection (2022
  p.111) showed this heading actually lives inside the **REMUNERATION**
  report banner ("REMUNERATION REPORT" / "Remuneration oversight and
  policies" / "Remuneration governance"), not CORPORATE_GOVERNANCE, despite
  matching an ILIKE `'%governance%'` keyword search. A cross-schedule
  keyword match is not the same as cross-schedule content movement --
  correctly excluded, not a `POSSIBLE_CROSS_SCHEDULE_MOVEMENT` case.
- ACT `Overview of critical/key corporate governance practices`: appears
  both in a front-of-book narrative overview (2021 p.20) and inside the
  formal back-matter governance report (2022 p.88, 2024 p.100) --
  documented as `POSSIBLE_CROSS_SCHEDULE_MOVEMENT`/duplication candidate
  for a future track, not selected here (ambiguous which occurrence is
  "the" schedule instance's own heading).
- BEL `Third line of defence`: deferred -- see Section 2 (fused
  heading/no standalone subsequent boundary).
- KP2's three recurring concepts: deferred -- see Section 2 (fused
  compound heading blocks, would need a parser change not in this
  milestone's budget).
- SBP, SDL, SUR: no candidates evaluated past schedule localization
  (Section 1).

## 5. Configuration added, and the one parser correction

**Configuration only** (`schedule_config.py`, `semantic_unit_config.py`,
`analytical_eligibility.py` -- no matching-logic changes):
- `NormalizedSchedule.CORPORATE_GOVERNANCE` added to
  `schedule_localization.py`'s scope guard.
- 5 new heading-vocabulary strings (Section 1).
- 4 new `UnitConfig` entries (Section 3), all `NEXT_HEADING`.
- 4 new `UNIT_ANALYTICAL_MODES` entries: 3 `LEXICAL_ONLY` (ACT), 1
  `STRUCTURED_COMPARISON_PREFERRED` (BEL).

**The one allowed generic parser/localizer correction** (used once,
corpus-wide, not per-issuer): `semantic_unit_extraction.py`
`_run_extraction` (`ALGORITHM_VERSION` 1.3.0 -> 1.4.0) now searches the
**union** of a `ScheduleInstance`'s primary span and every
`ScheduleInstanceSupportingSpan`, instead of the primary span alone. Real
bug found and fixed: BEL's CORPORATE_GOVERNANCE 2018/2019 primary spans are
a single page each (pp.38, 40) because each "Corporate governance report
continued" occurrence registers as its own supporting span rather than
extending the primary (by design -- see `ScheduleInstanceSupportingSpan`'s
docstring) -- the pre-fix extraction code searched only that one primary
page and silently missed every unit heading on the "continued" pages.
Generic: it reads `supporting_spans`, not any schedule- or heading-specific
text, so it applies to every existing and future schedule/unit, not just
CORPORATE_GOVERNANCE's. Regression test:
`tests/test_semantic_unit_extraction_service.py`.

No second correction was made. ACT 2019's heading-variation gap (Section
1), KP2's fused-heading gap (Section 2), and SBP/SUR's inconclusive
localization (Section 1) are all documented as deferred rather than fixed,
per the corpus-wide budget cap.

## 6. Extraction coverage

| ticker | unit_key | years attempted | resolved | classification of misses |
|---|---|---|---|---|
| ACT | information_security_governance | 2016,2018-2024 (8) | 2016,2018,2020-2024 (7) | 2017: GENUINE_ABSENCE (no matching heading anywhere in that year's report) |
| ACT | governance_policies_processes | 2018-2024 (7) | 2018,2020,2021,2022,2024 (5); 2023 present but severely truncated | 2023: BOUNDARY_DEFECT (see Section 12); 2019: GENUINE_ABSENCE (schedule instance itself only covers 1 page that year, Section 1) |
| ACT | combined_assurance | 2018,2020-2024 (6) | 2018,2020,2021,2022,2023,2024 (6) resolved boundary, but **2022 and 2023's resolved text is wrong content** | EXTRACTION_DEFECT (Section 12) -- a false-positive start-heading match, not a genuine absence |
| BEL | board_composition_diversity | 2018-2021 (4) | 2021 only (real text); 2018-2020 heading found but UNRESOLVED (no paragraph content between heading and next heading -- it's a demographic table, not prose) | Not a defect -- expected, given STRUCTURED_COMPARISON_PREFERRED routing (Section 9); 2016/2017: GENUINE_ABSENCE; 2022: EXPECTED_HEADING_VARIATION ("Board committee composition", a different heading, real corpus 2022 p.47) |

## 7. Manual source review

- **ACT information_security_governance**: earliest (2016), an intermediate
  year (2022), and latest (2024) all manually inspected against canonical
  page text -- correct heading, correct start boundary, ends at a genuine
  next heading every time ("GOVERNANCE OUTLOOK" 2016, page-banner "The
  Board of Directors continued" 2022 -- excluded generically as boilerplate
  -- "TAX TRANSPARENCY" 2024), no neighboring-section spill-in, no
  chart/table contamination.
- **ACT governance_policies_processes**: 2022 and 2024 verified correct
  (compliance-focused narrative, ends cleanly at "Ethical behaviour"); 2023
  inspected specifically because of its outlier lexical score (Section 12)
  -- confirmed a real boundary defect (14 words captured vs. 176 in the
  adjacent year), not a genuine rewrite.
- **ACT combined_assurance**: 2020/2021/2024 verified correct (real
  three-lines-of-defence framework paragraph); 2022/2023 inspected because
  of an outlier lexical score and found to contain **wrong content
  entirely** -- an unrelated governance-practices overview infographic
  ("Strong Lead Independent Director", "‘Overboarding’... policy", board
  diversity criteria) that happens to also carry a heading-candidate
  matching "Combined assurance" earlier in reading order. Same defect class
  as Track 7D.2's documented, deliberately-unfixed "Capital management"
  false-positive risk.
- **BEL board_composition_diversity**: 2018 (earliest UNRESOLVED),
  2021 (only resolved year), and 2020 (intermediate) all inspected --
  confirmed genuinely tabular (director designation/age/gender/race), no
  narrative prose present in any year to have been missed.

## 8. Alignment results (Track 7C.2, unmodified)

ACT (8 adjacent/available `ReportPair`s):

| pair | outcome |
|---|---|
| 2016->2017 | information_security_governance: UNRESOLVED_UPSTREAM (2017 GENUINE_ABSENCE) |
| 2016->2024 | information_security_governance MATCHED; combined_assurance, governance_policies_processes: UNRESOLVED_UPSTREAM |
| 2017->2018 | no configured units present on either side (clean COMPLETED, zero alignments) |
| 2018->2019 | same |
| 2019->2020 | all three UNRESOLVED_UPSTREAM (2019's 1-page schedule instance) |
| 2020->2021 | all three MATCHED (HIGH) |
| 2021->2022 | all three MATCHED (HIGH) |
| 2022->2023 | all three MATCHED (HIGH) |
| 2023->2024 | combined_assurance, information_security_governance MATCHED; governance_policies_processes UNRESOLVED_UPSTREAM (2024's own boundary issue this pair, distinct from 2023's) |

BEL (6 adjacent `ReportPair`s, `board_composition_diversity` only):
2016->2017 COMPLETED (no unit present either side); every other pair
(2017->2018 through 2021->2022) is UNRESOLVED_UPSTREAM -- the unit's
boundary is UNRESOLVED in every year except 2021, so no pair has two
trustworthy sides. **No MATCHED or RENAMED alignment exists for this unit
in the real corpus.**

No ADDED/REMOVED events were produced for any governance unit in either
issuer's real corpus in this run (every non-MATCHED outcome was
UNRESOLVED_UPSTREAM, which correctly withholds a presence/absence claim
rather than asserting one from an extraction limitation) -- consistent
with `SemanticUnitAlignmentStatus`'s own documented distinction between the
two.

## 9. Analytical routing

| unit | mode | reason |
|---|---|---|
| ACT information_security_governance | LEXICAL_ONLY | direct narrative prose, no tabular/numeric framing, verified across all resolved years |
| ACT governance_policies_processes | LEXICAL_ONLY | narrative (compliance/ethics prose), same profile |
| ACT combined_assurance | LEXICAL_ONLY | narrative where correctly extracted; see Section 12 for the extraction-defect years, not a routing problem |
| BEL board_composition_diversity | STRUCTURED_COMPARISON_PREFERRED | demographic composition table, not prose -- declared routing outcome only, no engine implemented here |

## 10. Lexical comparison results

Only the existing metrics were computed (TF-IDF cosine, unigram/bigram
Jaccard, edit similarity, sequence similarity, word-count change); no new
thresholds, composites, or qualitative labels were added.

**ACT information_security_governance** (consistently high similarity,
consistent with a stable, boilerplate-anchored disclosure):

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2016->2024 | 0.645 | 0.315 | 266->188 |
| 2020->2021 | 0.978 | 0.899 | 145->141 |
| 2021->2022 | 0.968 | 0.852 | 141->133 |
| 2022->2023 | 0.922 | 0.712 | 133->189 |
| 2023->2024 | 0.967 | 0.948 | 189->188 |

**ACT governance_policies_processes** (real variability, one boundary-defect outlier):

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2020->2021 | 0.630 | 0.281 | 627->123 |
| 2021->2022 | 0.871 | 0.725 | 123->174 |
| 2022->2023 | 0.319 | 0.108 | 174->14 |

**ACT combined_assurance** (two years contaminated by the extraction defect):

| pair | tfidf_cosine | unigram_jaccard | words |
|---|---|---|---|
| 2020->2021 | 0.967 | 0.918 | 65->66 |
| 2021->2022 | 0.333 | 0.062 | 66->122 |
| 2022->2023 | 0.867 | 0.659 | 122->81 |
| 2023->2024 | 0.267 | 0.082 | 81->67 |

## 11. Longitudinal sanity check

- **information_security_governance**: stable disclosure, consistently
  high similarity every year -- plausible and confirmed by manual review
  (Section 7). No suspicious values.
- **governance_policies_processes**: 2020->2021's drop (627->123 words,
  0.63 cosine) reflects a genuine restructuring (2020's version bundles
  several extra compliance topics later years split out elsewhere);
  2022->2023's collapse (174->14 words, 0.32 cosine) is **not** a genuine
  rewrite -- confirmed a boundary defect (Section 7/12). Inspecting the
  boundary first, per this section's own instruction, is exactly what
  caught it.
- **combined_assurance**: 2021->2022 (0.33 cosine, words 66->122) and
  2023->2024 (0.27 cosine, 81->67) both look like extreme rewrites but are
  in fact the extraction defect (Section 12) on one or both sides of each
  pair -- 2022 and 2023 both hold the wrong content. 2020->2021 (0.97,
  stable) and 2022->2023 (0.87 -- misleadingly "plausible" only because
  *both* sides in that specific pair share the same wrong content) are the
  only two pairs whose score doesn't obviously flag the underlying defect
  by itself; the defect was only caught by reading the actual source text
  (Section 7), which is why manual review remains necessary and is not
  replaced by the metrics.

## 12. Extraction/boundary defects found (documented, not fixed further)

- **ACT combined_assurance, 2022 and 2023**: EXTRACTION_DEFECT. The
  configured start heading "Combined assurance" matches an earlier,
  unrelated governance-practices overview/infographic item before the real
  section heading in reading order in these two years specifically (same
  defect class as 7D.2's documented, deliberately-unfixed "Capital
  management" case). Not fixed here (budget spent on Section 5's
  correction). Downgrades this unit's cutover readiness (Section 15).
- **ACT governance_policies_processes, 2023**: BOUNDARY_DEFECT. NEXT_HEADING
  stops after the section's opening sentence (14 words) instead of
  continuing through its bullet list, in this year only. Not fixed here.

## 13. Cross-schedule movement observations

- ACT "Overview of critical/key corporate governance practices" content
  appears to exist in both a front-of-book narrative section and the
  formal back-matter governance report in different years --
  `POSSIBLE_CROSS_SCHEDULE_MOVEMENT` / duplication, flagged for a future
  track, not solved here.
- ACT "Remuneration governance" is correctly attributed to the
  REMUNERATION schedule, not CORPORATE_GOVERNANCE, despite surfacing in a
  governance keyword search (Section 4) -- documented as a
  keyword-search false lead, not a real movement case.
- No other governance content was observed moving between schedules across
  any issuer in this inventory.

## 14. Coverage registry

`coverage_registry.py` is unchanged (still derived automatically from
`semantic_unit_config.UNIT_CONFIGS`, `analytical_eligibility.
UNIT_ANALYTICAL_MODES`, and `cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE`).
Since `cutover_config.py` was not touched, all four new units resolve to
`production_status = "candidate"` automatically -- no parallel hardcoded
list was created. Verified by
`tests/test_coverage_registry.py::test_new_governance_units_are_candidates_not_enabled_in_production`.

## 15. Cutover-readiness matrix

| ticker | unit_key | readiness | why |
|---|---|---|---|
| ACT | information_security_governance | READY_FOR_CUTOVER | reliable localization+extraction across 7/8 attempted years, trustworthy MATCHED alignment on 5 of the available pairs, correct content verified in 3 manually-inspected years, no unresolved correctness defect |
| ACT | governance_policies_processes | READY_WITH_CAVEAT | correct on the large majority of resolved years, but one confirmed BOUNDARY_DEFECT year (2023) directly contaminates one adjacent-pair comparison |
| ACT | combined_assurance | NOT_READY | a confirmed, systematic false-positive EXTRACTION_DEFECT affects 2 of 5 resolved years' content, contaminating 3 of 4 available comparison pairs -- an unresolved correctness defect |
| BEL | board_composition_diversity | NOT_READY | STRUCTURED_COMPARISON_PREFERRED (no comparison engine exists), and separately: zero MATCHED alignments exist across the real corpus at all (every pair but one is UNRESOLVED_UPSTREAM) |

## 16. Issuer-level coverage summary

| ticker | report years | governance schedule years resolved | years absent/unresolved | candidate units found | units configured | cutover readiness | major blockers |
|---|---|---|---|---|---|---|---|
| ACT | 9 (2016-2024) | 8 (all but 2019, which is HEADING_VARIATION) | 1 (2019) | 4 evaluated, 3 selected | 3 | 1 READY_FOR_CUTOVER, 1 READY_WITH_CAVEAT, 1 NOT_READY | combined_assurance's false-positive-match defect; 2019's truncated continuation banner |
| BEL | 7 (2016-2022) | 7 | 0 | 3 evaluated, 1 selected | 1 | 1 NOT_READY | unit is table content with no comparison engine; alignment almost never resolves both sides |
| KP2 | 6 (2020-2025) | 6 (all RESOLVED with a ~1-page front gap caveat) | 0 | 3 evaluated | 0 | n/a | every recurring concept is a compound heading fused with the "(CONT)" banner -- no standalone boundary to configure without a parser change |
| SBP | 3 (2023-2025) | 0 (INCONCLUSIVE) | 3 | 0 evaluated | 0 | n/a | matched heading resolves an implausibly short (1-page) span; real governance content's structure in this issuer is not understood well enough to configure anything |
| SDL | 2 (2024-2025) | 0 (GENUINE_ABSENCE) | 2 | 0 evaluated | 0 | n/a | no standalone Corporate Governance schedule exists in this issuer's report structure (fused into an ESG chapter) |
| SUR | 3 (2023-2025) | 0 (GENUINE_ABSENCE 2023-2024, INCONCLUSIVE 2025) | 3 | 0 evaluated | 0 | n/a | no heading matches the configured vocabulary in 2023/2024; 2025's extraction quality is too degraded corpus-wide to trust a single-page match |

## 17. Corpus-wide acceptance matrix

| ticker | unit_key | years available | years resolved | adjacent pairs | MATCHED | ADDED | REMOVED | UNRESOLVED_UPSTREAM | AMBIGUOUS | analytical mode | comparison coverage | provenance coverage | cutover readiness |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ACT | information_security_governance | 9 | 7 | 8 | 5 | 0 | 0 | 3 | 0 | LEXICAL_ONLY | 5/8 pairs | full (canonical/legacy TextBlock provenance on every resolved unit) | READY_FOR_CUTOVER |
| ACT | governance_policies_processes | 7 | 5 (+1 boundary-defective) | 8 | 3 | 0 | 0 | 5 | 0 | LEXICAL_ONLY | 3/8 pairs (1 contaminated by defect) | full | READY_WITH_CAVEAT |
| ACT | combined_assurance | 6 | 6 (2 wrong-content) | 8 | 4 | 0 | 0 | 4 | 0 | LEXICAL_ONLY | 4/8 pairs (3 contaminated by defect) | full | NOT_READY |
| BEL | board_composition_diversity | 4 | 1 | 6 | 0 | 0 | 0 | 5 | 0 | STRUCTURED_COMPARISON_PREFERRED | 0/6 pairs | partial (heading/page provenance only where UNRESOLVED) | NOT_READY |

(KP2/SBP/SDL/SUR: no configured units, no rows.)

## 18. Configuration-driven assessment (quantified)

- **Units added through configuration + validation only**: 3 of 4
  (ACT information_security_governance, ACT governance_policies_processes
  [with a documented single-year defect], BEL board_composition_diversity).
- **Units requiring the one allowed generic parser/localizer correction**:
  effectively all 4 benefited from the Section 5 supporting-spans fix
  (it is what made BEL's unit resolvable at all in 2021, and widened every
  ACT year's search range), but the fix itself was schedule/unit-agnostic,
  not unit-specific.
- **Candidates requiring issuer-specific work not attempted here**: KP2's
  three candidates (compound-heading splitting), BEL's `Third line of
  defence` (same fused-heading-plus-missing-boundary class), ACT's
  `Overview of ... governance practices` (cross-schedule duplication
  resolution).
- **Candidates deferred because current architecture is insufficient**:
  none required a genuinely new architectural capability (no SPLIT/MERGED
  handling, no new comparison engine, no VLM) -- every deferral in this
  track is either a missing standalone-heading classification (KP2, BEL)
  or an unresolved cross-schedule-duplication question (ACT), both
  solvable with more configuration/parser work of the same kind already
  used here, not a new architecture.
- **One real correctness defect surfaced and left unfixed by design**:
  ACT combined_assurance's false-positive start-heading match (Section 12)
  -- this is the second candidate for a bounded generic fix (the same
  defect class 7D.2 already flagged for "Capital management"), explicitly
  deferred per the corpus-wide one-correction budget.

## 19. Tests

Added:
- `tests/test_schedule_localization.py`: CORPORATE_GOVERNANCE localizes
  identically to FINANCIAL_PERFORMANCE given the same evidence shape;
  "continued" banners still don't terminate the schedule; replaced the
  now-stale "CORPORATE_GOVERNANCE raises NotImplementedError" test with an
  equivalent one against a schedule still genuinely unimplemented
  (REMUNERATION).
- `tests/test_semantic_unit_extraction_service.py` (new): DB-backed
  regression test for the Section 5 supporting-spans fix, reproducing the
  exact BEL 2018/2019 shape (1-page primary + a supporting span reaching
  the real heading) and asserting the unit is now found.
- `tests/test_semantic_unit_config_governance.py` (new): the four new
  `UnitConfig` entries exist under the right ticker/schedule, existing
  FINANCIAL_PERFORMANCE units are unaffected, no new boundary strategy was
  introduced, no unit_key collides across tickers.
- `tests/test_analytical_eligibility_routing.py`: routing tests for all
  four new units, including that the BEL table unit does **not** silently
  become LEXICAL_ONLY just because it's MATCHED.
- `tests/test_coverage_registry.py`: all four new units resolve to
  `production_status = "candidate"`, and the BEL unit's routed mode is
  `STRUCTURED_COMPARISON_PREFERRED`.

Targeted tests were run throughout development; the full suite was run
once at the end (Section 21).

## 20. Caveats

- ACT `combined_assurance` carries a real, unresolved extraction defect
  (Section 12) -- included in the deliverables specifically because
  finding and correctly diagnosing it (rather than being fooled by a
  plausible-looking 0.87 cosine score on one contaminated pair) is itself
  evidence the milestone's manual-review requirement is doing its job, not
  because the unit is production-ready.
- KP2's schedule localizes with a small (~1 page) front-boundary gap that
  was not pursued given the corpus-wide one-correction budget was spent
  elsewhere; functionally immaterial (the union of primary+supporting
  spans still covers the overwhelming majority of the schedule's real
  content).
- SBP and SUR's INCONCLUSIVE schedule status reflects genuine uncertainty
  about those issuers' real report structure, not a confirmed absence --
  a future track with issuer-specific investigation (out of this
  milestone's scope) could plausibly resolve either.
- BEL's `board_composition_diversity` technically "extracts" in the sense
  that the heading is found, but produces zero usable comparisons in the
  real corpus -- a caution against reading "3 units configured" as "3
  units delivering comparisons."

## 21. Final verdict

**PASS WITH CAVEATS -- GOVERNANCE READY FOR CONTROLLED EXPANSION**

Corporate Governance can be brought into the semantic comparison system
using the existing architecture, confirmed corpus-wide: no new boundary
strategy, comparison engine, table parser, or cross-schedule-movement
mechanism was needed for any of the 6 issuers audited. The one generic
parser correction the milestone allowed was genuinely necessary and fixed
a real, schedule-agnostic bug (supporting-spans page-range widening) that
will also help any future schedule with multi-span "continued" content.
One real, unresolved extraction defect (ACT `combined_assurance`) and
several under-supported issuers (KP2, SBP, SDL, SUR) were found and
honestly documented rather than forced or silently worked around.

- Companies audited: 6 (ACT, BEL, KP2, SBP, SDL, SUR)
- Report years audited: 30 (9+7+6+3+2+3)
- Schedules resolved: 21 of 30 (ACT 8/9, BEL 7/7, KP2 6/6-with-caveat, SBP 0/3, SDL 0/2, SUR 0/3-with-1-inconclusive)
- Semantic units configured: 4 (3 ACT, 1 BEL)
- Units READY_FOR_CUTOVER: 1 (ACT information_security_governance)
- Units READY_WITH_CAVEAT: 1 (ACT governance_policies_processes)
- Units NOT_READY: 2 (ACT combined_assurance, BEL board_composition_diversity)

## 22. Next-schedule checkpoint (corpus-wide)

Evaluated corpus-wide, using only what this track's real inventory showed:

- **MATERIAL_RISKS**: promising -- ACT and BEL both already show
  substantial risk-governance narrative fused inside their Corporate
  Governance schedules ("INHERENT RISKS / RISK MITIGATION FACTORS", "Risk
  management", "combined assurance"/"three lines of defence"), suggesting
  a real, separately-headed MATERIAL_RISKS schedule likely exists nearby
  with a similar recurring-narrative profile. KP2 and SUR both show risk
  content too ("Audit and Risk Committee", "Risk framework and the
  governance of risk").
- **REMUNERATION**: ACT and BEL both have an obviously distinct,
  consistently-headed "Remuneration Committee Report"/"Remuneration
  Report" schedule every year (seen throughout this track's own
  inventory) -- likely the single easiest next schedule to localize, since
  its heading vocabulary is already effectively known from this track's
  incidental discovery (Section 4). Some structured-table work already
  exists for ACT remuneration (Track 7C.4), so a semantic-unit narrative
  layer alongside it (background statement, committee chair's report,
  focus areas) looks tractable.
- **CEO_REVIEW / CHAIR_REVIEW**: present in most issuers ("Joint report by
  the chairman and chief executive" for BEL) but frequently fused into one
  combined chairman+CEO section (BEL) rather than two separately-headed
  schedules -- would need a scoping decision before configuration.
- **STRATEGY / OUTLOOK**: seen only briefly and unevenly across issuers in
  this track's incidental inventory; not enough evidence yet to recommend.

**Recommendation: REMUNERATION next.** It has the clearest, most
consistently-named heading across the two best-supported issuers (ACT,
BEL), an existing structured-table precedent to build alongside (Track
7C.4), and -- per this amendment's new default -- should be evaluated
corpus-wide (including KP2, which also names a "Remuneration Report"
section, SBP, SDL, and SUR) from the start rather than ACT/BEL-first.

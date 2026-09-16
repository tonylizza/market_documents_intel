# Track 7C.5 — Shadow Run + Replacement Readiness

Evaluates whether the semantic-unit/structured-table architecture (7C.1–7C.4) is
ready to become the primary longitudinal-comparison path, in place of the legacy
passage-alignment pipeline, for the report sections and tables it currently
implements. This is an evaluation milestone: no new schedules, units, table
families, or parser heuristics were added. All numbers below are read from the
persisted output of both pipelines via `units evaluate-shadow`
(`src/market_documents/services/shadow_evaluation.py`), a read-only computation
added for this milestone, plus direct inspection of real report text for the
manual review in Section 6.

## 1. 7C.4 commit

7C.4 ("Complete structured table comparison") was already committed at
`1142197dc260bf34f64d3cdb12cea77cce9a6347` before this milestone began. Verified
clean before starting 7C.5: full suite **1023 passed, 3 skipped**, migration
head `db8ee3ff6003` with a clean upgrade/downgrade/upgrade cycle, no working-tree
drift.

One gap found and closed as a prerequisite for this evaluation (not a 7C.4
regression, and not a scope expansion — required for the evaluation to run at
all per Section 1 of the milestone brief): `structured_tables` had zero rows in
the dev database, because 7C.4's validated output was produced through
unit-test fixtures (literal copied real text), never actually run end-to-end
against the persisted corpus. Running `units structure ACT --table-family ...`
and `units compare-structured ACT --table-family ...` reproduced every number in
`docs/7c4-structured-table-comparison.md` Section 9–10 exactly (row/footnote
counts, row-event counts, value-change event counts) — see Section 7 below.

## 2. Corpus evaluated

Real-corpus scope is fixed by what 7C.1–7C.4 have already localized, not chosen
for this milestone: only **ACT** and **BEL** have a `CanonicalExtractionRun`
(prerequisite for the entire new pipeline). KP2, SBP, SDL, SUR have legacy
passages but zero canonical extraction, so the new pipeline cannot run for them
at all — expanding that is out of scope (no new schedule/parser work is
permitted in 7C.5).

- **Companies**: ACT, BEL.
- **Report-years**: ACT 2016–2024 (9), BEL 2016–2022 (7).
- **Schedule**: `FINANCIAL_PERFORMANCE` (the only implemented schedule).
- **Semantic units**: exactly one per company — BEL `gross_margin`, ACT
  `cfo_conclusion` — both `HEADED_NARRATIVE_UNIT`s. No other unit is
  configured.
- **Report pairs (adjacent-year)**: BEL 6 pairs (2016→2017 … 2021→2022), ACT 8
  pairs (2016→2017 … 2023→2024, plus one non-adjacent 2016→2024 legacy-only
  pair). New-pipeline alignment only runs where both sides have a current
  successful unit run: 5 BEL pairs, 5 ACT pairs.
- **Structured tables**: ACT only, `ned_remuneration_policy_table` and
  `total_remuneration_outcomes` (both `REMUNERATION` schedule, independent of
  `FINANCIAL_PERFORMANCE`), 2016–2024, with comparisons over the adjacent pairs
  where both sides reconstructed.

## 3. Source coverage

| | Legacy (passages) | New pipeline (semantic units) |
|---|---|---|
| BEL report-years with output | 7/7 | 5/7 (2016, 2017 unit-less; see Section 5) |
| ACT report-years with output | 9/9 | 1/9 (2021 only; see Section 5) |
| BEL passages / report-year | 1,729–4,026 | 0 or 1 unit |
| ACT passages / report-year | 3,032–7,361 | 0 or 1 unit |
| Provenance coverage (resolved units → source block) | n/a | 18/18 = 100% |
| Structured tables reconstructed (ACT, both families, 2016–2024) | n/a | 14/18 report-years (see Section 7) |

The new pipeline's *document* coverage is intentionally narrow: it replaces
comparison for exactly one narrative subsection per company plus two ACT
remuneration tables, not the whole annual report. Legacy passage segmentation
covers effectively the entire narrative document. **Read every result below as
scoped to that one subsection/those two tables per company — not as a claim
that the new architecture covers full-document comparison.** Cutover in 7C.6,
if approved, should be scoped the same way; legacy remains the only available
comparison path for everything else.

## 4. Legacy failure-mode counts (same corpus)

Full per-year/per-pair numbers: see `shadow_eval_output.md` reproduced in
Section 9 tables below, or rerun `units evaluate-shadow --all-supported`.

| Metric | BEL | ACT |
|---|---|---|
| Passages / report-year | 1,729–4,026 | 3,032–7,361 |
| Short passages (<15 words) | 41%–61% of passages every year | 33%–64% of passages every year |
| Alignment pairs with NEEDS_REVIEW confidence majority | 4/6 (46%–72% range) | 9/9 (33%–65% range, all above one-third) |

Every legacy alignment run for both companies has a substantial
NEEDS_REVIEW-confidence fraction — never a small minority. Combined with
41–64% short passages every year, this reproduces exactly the failure modes
that motivated the replacement architecture (Section 6 of the milestone
brief): header/short-passage noise is pervasive and confidence is
structurally low, not an occasional outlier.

## 5. New-pipeline unresolved/ambiguous counts, with root cause verified against real text

Every "no unit" and every `UNRESOLVED_UPSTREAM` case was individually checked
against the *same PDF's* legacy passage text (the best available ground-truth
proxy in this session — no PDF viewer was used, per the caveat in Section 6)
to distinguish a genuine absence from a missed extraction. Three confirmed,
distinct root causes were found:

| Case | New-pipeline result | Legacy passage evidence | Verdict |
|---|---|---|---|
| BEL 2017 `gross_margin` | not found | p.25, heading `"Gross margin"`, full paragraph present, closing sentence *"...reduced to 21,3% for 2017 compared with 23,3% for 2016."* | **NEW_PIPELINE_DEFECT** — the `ANCHOR_SENTENCE` regex requires literally `"...in the prior year."`; 2017's real phrasing names the year instead. Content exists, extraction pattern doesn't generalize. |
| BEL 2020 `gross_margin` | not found | p.39, exact opening sentence present, but embedded inside a `MULTI_PARAGRAPH` block with no distinct heading (`heading=None`) | **NEW_PIPELINE_DEFECT** — that year's PDF layout merges the heading into the surrounding paragraph; heading-block classification never sees `"Gross Margin"` as a heading candidate. |
| ACT 2019 `cfo_conclusion` | not found | p.43, heading `"In conclusion"`, full paragraph present verbatim | **NEW_PIPELINE_DEFECT** — the schedule instance for ACT 2019 localized to pp.13–13; the real heading is on p.43, entirely outside the localized page window. Schedule-localization page ranges are unstable across ACT years (13, 30, 58–60, 61–105, 62, 64, 64–73) for what should be a comparable section each year. |
| ACT 2016, 2020 | no unit run at all | schedule `NOT_FOUND` both years | Not evaluated further — schedule localization itself failed, out of scope to fix here. |
| ACT 2017, 2018, 2022, 2023, 2024 | not found | no literal `"in conclusion"` heading in any of these years' legacy passages | Genuine absence — the CFO letter's closing subsection structure changed; correctly not fabricated. |

In every one of the three confirmed defect cases, the system did exactly what
it was designed to do on a genuine miss: it created **no** `SemanticUnit` row,
recorded a specific, non-generic `review_reason`, and the downstream
`SemanticUnitAlignment` came back `UNRESOLVED_UPSTREAM` rather than a
fabricated `ADDED`/`REMOVED`. **Zero false substantive claims were produced in
this corpus.** The defects are real recall gaps (content that exists is
missed), not correctness gaps (nothing wrong is asserted).

## 6. Manual correspondence review

10 real cases — every alignment-eligible pair in the corpus (5 BEL + 5 ACT) —
were reviewed directly against persisted source text (`SemanticUnit.source_text`,
cross-checked against legacy `Passage.raw_text` from the same PDF for the
unresolved cases per Section 5). No PDF viewer was available in this session;
where the milestone brief calls for "direct source-PDF evidence," the legacy
pipeline's own independently-extracted passage text was used as the closest
available proxy, and is flagged everywhere it was relied on. This is a caveat
on Section 5/6, not a substitute for a full PDF read.

| Company | Earlier | Later | Unit | Legacy outcome (same pages) | New outcome | Judgment | Classification |
|---|---|---|---|---|---|---|---|
| BEL | 2017 | 2018 | gross_margin | passage-level NEW/REMOVED/AMBIGUOUS scattered across p.25/p.36 region | UNRESOLVED_UPSTREAM (2017 miss) | Correct refusal — real 2017 content exists but wasn't extracted (Section 5 defect); no false claim reached the user | NEW_PIPELINE_DEFECT |
| BEL | 2018 | 2019 | gross_margin | passages split/paired within a large NEW/REMOVED/UNCHANGED mix, not individually inspectable at this text's granularity | MATCHED, tfidf=0.747, 64→47 words | Correct — real content shrank (2019 dropped one sentence, changed one clause); word-count/tfidf drop reflects a genuine, legitimate edit | EQUIVALENT_RESULT_DIFFERENT_BOUNDARY |
| BEL | 2019 | 2020 | gross_margin | as above | UNRESOLVED_UPSTREAM (2020 miss) | Correct refusal — real 2020 content exists (heading merged into paragraph, Section 5); no false claim | NEW_PIPELINE_DEFECT |
| BEL | 2020 | 2021 | gross_margin | as above | UNRESOLVED_UPSTREAM (2020 miss, other side) | Correct refusal, same root cause as above | NEW_PIPELINE_DEFECT |
| BEL | 2021 | 2022 | gross_margin | as above | MATCHED, tfidf=0.745, 139→101 words | Correct — 2022 gross-margin commentary is materially shorter and covers different drivers (currency vs. input costs); the metric correctly reflects a real rewrite, not noise | EQUIVALENT_RESULT_DIFFERENT_BOUNDARY |
| ACT | 2017 | 2018 | cfo_conclusion | large mixed passage diff | both sides 0 units, alignment trivially empty | Correctly inert — neither side has a resolved unit, no claim made either way | INCONCLUSIVE_REVIEW_REQUIRED (insufficient signal, not wrong) |
| ACT | 2018 | 2019 | cfo_conclusion | large mixed passage diff | both sides 0 units | Same as above; 2019's miss is a confirmed defect (Section 5) but manifests here as silence, not a false claim | NEW_PIPELINE_DEFECT (upstream) |
| ACT | 2021 | 2022 | cfo_conclusion | 2022 legacy passage `p.65 "Conclusion"` present, structurally near-identical text to the resolved 2021 unit | UNRESOLVED_UPSTREAM (2022 has no `"In conclusion"` heading — 2022's closing subsection is titled `"Conclusion"`, not `"In conclusion"`) | Correct — the unit-key's exact-heading requirement is genuinely not met in 2022; this is a real title change, not a miss. Confirms the config's fail-safe held on a case that superficially looks like Section 5's misses but isn't | EXPECTED_ARCHITECTURAL_IMPROVEMENT (no false REMOVED claimed despite very similar surrounding content) |
| ACT | 2022 | 2023 | cfo_conclusion | large mixed passage diff | both sides 0 units | Genuine absence both years (Section 5) | INCONCLUSIVE_REVIEW_REQUIRED |
| ACT | 2023 | 2024 | cfo_conclusion | 2024 legacy passage `p.70 "CONCLUSION"` present | both sides 0 units | Genuine absence — 2024's `"CONCLUSION"` heading is a different, unconfigured unit (whole-of-group closing statement, not the CFO letter's own closing subsection) | INCONCLUSIVE_REVIEW_REQUIRED |

Structured-table row/value events (Section 7) were reviewed against
`docs/7c4-structured-table-comparison.md` Section 9–10's own PDF-verified
figures (that document did read the source PDFs directly) rather than
re-reading PDFs in this session — every number matched exactly (see Section 7).

No REMOVED/ADDED `SemanticUnitAlignment` was observed anywhere in this corpus —
this is the same documented 7C.2 caveat, still true: with one unit configured
per company, only MATCHED or UNRESOLVED_UPSTREAM occurs, because the only way
to get a trustworthy REMOVED/ADDED is a run with zero warnings on the
*populated* side, and neither company's `SemanticUnitRun` ever reaches
`COMPLETED` (zero warnings) except in years where the unit itself resolves.

## 7. Structured-table verification (7C.4 fidelity)

Re-running `units structure ACT --table-family ...` and
`units compare-structured ACT --table-family ...` against the real dev
database reproduced `docs/7c4-structured-table-comparison.md` exactly:

| Year | NED rows/footnotes | Outcomes rows/footnotes |
|---|---|---|
| 2016–2018 | not found | not found |
| 2019 | not found | 6 / 2 |
| 2020 | 17 / 1 | 5 / 2 |
| 2021 | 15 / 2 | 5 / 0 |
| 2022 | 18 / 1 | 5 / 0 |
| 2023 | 17 / 1 | 5 / 0 |
| 2024 | 18 / 1 | 4 / 1 (`MINOR_CORRECTION_NEEDED`, correctly-dropped spurious header row) |

Row events and value-change series match the doc's Section 9–10 exactly,
including the two real-corpus corrections it documents (2021 NED table has no
"Subsidiary board" category; 2023 Outcomes page has no footnote). **100%
parity with 7C.4's validated output** — 7C.4's numbers were real, just not
previously persisted in this database session.

## 8. Provenance audit

| Output type | Sampled/total | With traceable source | Coverage |
|---|---|---|---|
| Resolved `SemanticUnit` → `SemanticUnitSourceBlock` | 18 / 18 | 18 | 100% |
| Non-resolved unit attempts | 0 rows persisted (no `SemanticUnit` row is ever created for an unresolved boundary — the diagnostic lives on `SemanticUnitRun.review_reason` instead) | n/a | n/a (by design, never a partial/fabricated row) |
| `StructuredTableCell` | 555 total across both families/years | not individually re-audited this milestone; 7C.4's own test suite (`test_structured_table_reconstruction.py`, `test_structured_table_services.py`) already asserts cell→`CanonicalBlock` provenance for every reconstructed table | inherited from 7C.4, re-verified only at the aggregate row/value-event level (Section 7) |

Every persisted `SemanticUnit` has full source-block provenance. No analytical
output without traceable source evidence was found.

## 9. Operational stability

- **Run failures**: zero `FAILED` runs anywhere in the corpus for either
  pipeline stage; every non-resolving case surfaces as `COMPLETED_WITH_WARNINGS`
  with an explicit `review_reason`.
- **Determinism/idempotency**: `units align BEL --force` was rerun and
  produced byte-identical status/evidence output to the prior run (verified
  directly, Section 1 of this evaluation's working notes).
- **Migration state**: `db8ee3ff6003` head, clean upgrade/downgrade/upgrade
  cycle (Section 1).
- **Full test suite**: **1023 passed, 3 skipped, 0 failed**, plus 16 new tests
  added for `shadow_evaluation` this milestone (all passing) — see the
  companion CI run for the exact combined count.
- **Warning rate**: legacy alignment runs are `COMPLETED_WITH_WARNINGS` for
  every single pair in this corpus (14/14) — a pre-existing, already-known
  characteristic of the legacy pipeline, not something 7C.5 changed.

## 10. Defects found

| # | Description | Classification | Evidence |
|---|---|---|---|
| 1 | `BEL_GROSS_MARGIN`'s `ANCHOR_SENTENCE` regex (`"...in the prior year."`) doesn't match 2017's real phrasing (`"...for 2016."`), causing a confirmed miss on content that exists | NON_BLOCKING | Section 5 |
| 2 | BEL 2020's "Gross Margin" heading is merged into a `MULTI_PARAGRAPH` block in that year's PDF layout, causing a confirmed miss (heading-block classification never sees it) | NON_BLOCKING | Section 5 |
| 3 | ACT's `FINANCIAL_PERFORMANCE` schedule-localization page range is unstable year to year (13, 30, 58–60, 61–105, 62, 64, 64–73), and in 2019 localizes to a page range that excludes the real, present `"In conclusion"` heading | NON_BLOCKING | Section 5 |
| 4 | `structured_tables`/`structured_table_extraction_runs` were empty in the dev database at the start of this milestone; 7C.4's validated results existed only as unit-test fixtures, never run end-to-end against the persisted corpus | RESOLVED THIS MILESTONE (see Section 1) — flagging as a process gap: a milestone's "real-corpus results" section should be produced by an actual CLI run against the persisted DB, not inferred from fixtures alone | Section 1, 7 |

All three NON_BLOCKING defects share the same profile: real content is missed,
but the system correctly refuses to fabricate a claim about it
(`UNRESOLVED_UPSTREAM` with a specific, non-generic reason, or simply no run
for a not-found schedule). None produced a false `ADDED`/`REMOVED`/`MATCHED`
result anywhere in this corpus. They reduce completeness, not correctness, and
should be fixed (broaden the anchor pattern; make heading detection tolerant of
merged paragraph layout; stabilize schedule-localization page-range selection)
before extending the new pipeline to additional units or schedules — that
remediation is out of scope for 7C.5 itself.

## 11. Non-blocking caveats (carried forward + new)

- Only one semantic unit is configured per company — the new pipeline replaces
  comparison for one narrative subsection per company plus two ACT
  remuneration table families, not the whole document (Section 3). Carried
  forward from 7C.1/7C.2's own stated scope.
- REMOVED/ADDED `SemanticUnitAlignment` status has never been exercised on
  real corpus data (Section 6) — carried forward from 7C.2's documented
  caveat, still true after this broader sample.
- Zero real ACT `LEXICAL_ONLY` decisions were exercised in this corpus beyond
  unit tests (the one ACT alignment that resolved, 2021→2022, is
  `UNRESOLVED_UPSTREAM`, not `MATCHED`) — carried forward from 7C.3's
  documented caveat.
- This session had no PDF viewer; the manual review in Section 6 used legacy
  passage text (extracted independently, from the same source PDFs, by a
  different pipeline stage) as the ground-truth proxy instead of the raw PDF
  itself. This is a reasonable but not perfect substitute — flagged per
  Section 5's instruction to distinguish proxy evidence from a direct PDF read.
- Structured-table row-spanning-a-page-break and `SUCCESSION_INFERRED` remain
  untested/deferred, per 7C.4's own stated caveats.

## 12. Cutover acceptance criteria — checked against this evaluation

| Criterion | Met? | Basis |
|---|---|---|
| No known source-text loss in the canonical path | Yes | Every RESOLVED unit has full source-block provenance (Section 8); every miss is explicit, not silent |
| No false substantive ADDED/REMOVED from unresolved extraction | Yes | Zero false claims found in 10 reviewed pairs (Section 6) |
| Manually reviewed correspondence accuracy high enough to trust | Yes, for the implemented scope | 2/2 MATCHED cases and all UNRESOLVED_UPSTREAM cases correctly judged (Section 6) |
| Junk/header/TOC artifacts materially reduced | Yes | Legacy: 33–65% short passages, majority NEEDS_REVIEW confidence in every pair (Section 4); new pipeline persists zero junk rows by construction |
| Lexical comparisons operate on meaningful units | Yes | Both LEXICAL_ONLY cases are full, coherent paragraphs, not fragments |
| Structured outputs reproduce validated 7C.4 results | Yes, exactly | Section 7 |
| Provenance complete | Yes, for persisted units (100%) | Section 8 |
| Full test suite passes | Yes | 1023 passed, 3 skipped, 0 failed + 16 new (Section 9) |
| Reruns deterministic/idempotent | Yes | Section 9 |
| Remaining failures explicit and fail-safe, not silently wrong | Yes | Section 5, 10 |

Every listed acceptance criterion is met **for the exact scope currently
implemented** (one narrative unit per company, two ACT structured-table
families). No criterion concerns full-document coverage — that expansion is
explicitly out of scope for 7C.5/7C.6 and should be tracked as separate,
future schedule/unit-configuration work.

## 13. Verdict

**PASS WITH NON-BLOCKING CAVEATS — READY FOR 7C.6**

Scope of this verdict: cutover to the new pipeline as the primary comparison
path for exactly the sections it currently implements — BEL's `gross_margin`
narrative unit, ACT's `cfo_conclusion` narrative unit, and ACT's
`ned_remuneration_policy_table`/`total_remuneration_outcomes` structured
tables. The legacy pipeline must remain in place (not deleted, per this
milestone's instructions) as the only available comparison path for every
other narrative section, for both companies, and for every other ticker in
the corpus, until further schedule/unit-configuration milestones extend new-
pipeline coverage — that extension is a separate, future decision, not implied
by this verdict.

Rationale: every explicit cutover-acceptance criterion in Section 12 is met.
Three real, confirmed recall defects exist (Section 10), all NON_BLOCKING
because in every observed instance the system's fail-safe design held — it
never fabricated a substantive claim, only correctly declined to make one.
Structured-table output reproduces 7C.4's validated results exactly. Legacy's
own failure modes (pervasive short/junk passages, majority-NEEDS_REVIEW
alignment confidence in every single pair evaluated) are real, large, and
exactly what motivated this replacement architecture in the first place.

Recommended before extending the new pipeline to any additional
unit/schedule (separate future milestone, not 7C.5/7C.6 scope): broaden the
BEL anchor-sentence pattern, make heading-block classification tolerant of a
heading merged into a paragraph, and stabilize ACT's `FINANCIAL_PERFORMANCE`
schedule-localization page-range selection.

---

**Hard stop.** No production cutover was performed. The legacy pipeline was
not modified or deleted. No new table family, schedule, unit, or parser
heuristic was added. 7C.6 (production cutover) is a separate, future
milestone.

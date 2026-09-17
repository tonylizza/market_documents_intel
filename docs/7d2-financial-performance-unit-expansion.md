# Track 7D.2 — FINANCIAL_PERFORMANCE unit coverage expansion

Scope: expand semantic-unit coverage within the already-supported
FINANCIAL_PERFORMANCE schedule using the architecture completed in Track 7C
and hardened in Track 7D.1 (docs/7d1-known-recall-defect-remediation.md).
Out of scope, unchanged: canonical PDF extraction, schedule localization,
heading hierarchy, semantic-unit persistence, alignment, analytical
routing, lexical metrics, structured comparison, publishing architecture,
production cutover architecture. No new schedule, issuer, structured-table
family, or production-scope change is introduced.

## 1. Candidate inventory

Real canonical/legacy-corpus inspection of BEL's and ACT's FINANCIAL_PERFORMANCE
schedules across every available report year (via each report's current
`ScheduleInstance` primary span) surfaced:

**BEL** (7 report-years, 2016-2022): headings inside the primary span are
dense only in 2017 (`Gross Margin`, `Revenue analysis`, `Financial
position`, `Exchange rates`, all as standalone heading-candidate blocks).
From 2018 onward, the report's layout becomes chart/infographic-heavy and
every subsequent subsection heading (`Other operating income`, `Expenses`,
`Taxation`, `Financial position`, `Property, plant and equipment`,
`Working capital`, `Exchange rates`, `IAS 36 Impairment of Assets
assessment`, `Looking ahead`, ...) is fused run-in onto the start (or,
2020, the end) of its own PARAGRAPH block rather than segmented as a
standalone heading-candidate -- exactly the pattern `gross_margin`'s own
`ANCHOR_SENTENCE` configuration exists to handle. Only `gross_margin`
already has such an anchor calibrated and validated.

**ACT** (9 report-years, 2016-2024): recurring headed narrative subsections
inside the primary span, beyond the already-configured `cfo_conclusion`
("In conclusion"):

- `Capital management` -- 2021 and 2024 (non-adjacent).
- `Healthcare Services Financial Performance` -- 2021, 2022, 2023
  (adjacent 2021-2022-2023 span).
- `Diversification`, `Growth prospects`, `Normalised earnings and
  shareholder returns`, `Financial position and cash flow`, `Cash and
  working capital` -- each appears in exactly one report-year across the
  inventory.

## 2. Selected units

One new unit was selected and shipped:

| Ticker | unit_key | Heading | Boundary | Resolved years |
| --- | --- | --- | --- | --- |
| ACT | `healthcare_services_review` | "Healthcare Services Financial Performance" | `NEXT_HEADING` | 2021, 2022, 2023 |

Selection rationale: recurs across 3 years including two genuinely
*adjacent* `ReportPair`s (2021-2022, 2022-2023), giving real `MATCHED`
alignments and real lexical-comparison output, not just declared routing
outcomes. It is direct narrative prose (a review of the
Medscheme/medical-scheme-administration cluster's operating performance)
with a stable analytical role across its resolved years, and its
boundaries are fully supported by the existing `NEXT_HEADING` mechanism
once the one generic fix in Section 4 is applied.

A second candidate, ACT `Capital management`, was evaluated in full and
**rejected** -- see Section 3.

## 3. Rejected / deferred candidates

**ACT `Capital management`** (`start_heading="Capital management"`,
`NEXT_HEADING`): resolved cleanly in 2021, but its 2024 occurrence exposed
a pre-existing, generic defect: `semantic_unit_extraction._matches_heading`
does a bare case-insensitive substring match with no exactness/word-order
discrimination (unlike `schedule_localization._matches_vocabulary`'s
exact/substring/word-order tiers). ACT 2024 page 65 contains an unrelated
decorative pull-quote heading-candidate fragment, `"by prudent capital
management policies"`, which contains the substring "capital management"
and sits earlier in reading order than the real `"CAPITAL MANAGEMENT"`
section heading on page 69 -- so the false match wins, and the real
section is never reached; `extract_unit` returns `UNRESOLVED` ("next
heading-candidate block immediately follows the start heading").

Per the milestone's defect policy, only one bounded, generic parser
correction is allowed per track, and that budget was already spent on the
`NEXT_HEADING` continuation-banner fix (Section 4) -- which is unrelated
(it fixes end-boundary detection, not start-heading matching) and cannot
also fix this. Without a second fix, `Capital management` only safely
resolves in one year (2021), which fails the "recurring across multiple
years" selection criterion (Section 3 of the milestone instructions
explicitly bars selecting a candidate "merely because it appears in one
year"). **Dropped from 7D.2.** Recommended as a dedicated future
defect-remediation candidate: give `_matches_heading` the same
exact-match-preferred, substring-as-weaker-evidence tiering
`schedule_localization._matches_vocabulary` already has, verified against
this exact false-positive case plus a regression suite across the existing
corpus.

**BEL subsections** (`Financial position`, `Exchange rates`, `Working
capital`, `Other operating income`, `Taxation`, `Looking ahead`): all
recur conceptually, but after 2018 none is bounded by a standalone
heading-candidate before the next section -- the heading is fused run-in
onto its own paragraph (as `_heading_run_in_match` already handles for
`gross_margin`), and no subsequent standalone heading-candidate exists to
terminate `NEXT_HEADING` before the schedule's own end (which would sweep
in several unrelated later subsections as one incorrect blob). Bounding
any of these would require a bespoke `ANCHOR_SENTENCE` regex calibrated
and validated per unit, the same real-corpus effort `gross_margin`'s own
anchor took (docs/7d1-known-recall-defect-remediation.md) -- legitimate,
already-supported-mechanism work, but not a small, ordinary-case
configuration exercise, and out of this track's time-boxed scope. **Deferred**
as good 7D.3-class candidates, not excluded on principle.

**ACT single-year headings** (`Diversification`, `Growth prospects`,
`Normalised earnings and shareholder returns`, `Financial position and
cash flow`, `Cash and working capital`): each appears in exactly one
report-year in the inventory. **Excluded** per Section 3's explicit rule
against selecting on single-year appearance; none was investigated further.

## 4. Configuration added

**`services/semantic_unit_config.py`** (`CONFIG_VERSION` 1.2.0 → 1.3.0):
added `ACT_HEALTHCARE_SERVICES_REVIEW` (`unit_key="healthcare_services_review"`,
`schedule=FINANCIAL_PERFORMANCE`, `ticker="ACT"`,
`start_heading="Healthcare Services Financial Performance"`,
`boundary_strategy=NEXT_HEADING`) to `UNIT_CONFIGS`.

**`services/semantic_unit_extraction.py`** (`ALGORITHM_VERSION` 1.1.0 →
1.2.0): the one bounded generic parser correction this track allows.
`NEXT_HEADING`'s end-boundary scan now skips a heading-candidate that is a
`"<something> continued"` page-continuation banner (new
`_is_continuation_heading`, matching on the normalized trailing word
"continued") instead of treating it as the section's terminator --
mirroring the identical rule `schedule_localization.py` already applies at
the schedule level (its own v1.0.4). Real ACT 2021 corpus evidence
motivated this: the literal banner text `"CFO's review continued"` is
classified `excluded_from_narrative` (and so never even reaches the
extractor) in ACT 2022, but is classified as a genuine narrative
heading-candidate in ACT 2021 -- without the fix, 2021's unit is truncated
one page early and drops a real continuation paragraph. The fix is
generic (matches on structure, not any specific heading text or unit_key),
so it applies to any current or future `NEXT_HEADING` unit. Confirmed by
direct real-corpus regression run to leave `BEL gross_margin`
(`ANCHOR_SENTENCE`, untouched code path) and `ACT cfo_conclusion`
(`NEXT_HEADING`, no "continued" banner in either of its resolved years)
byte-for-byte unchanged (Section 8).

**`services/analytical_eligibility.py`** (`ALGORITHM_VERSION` 1.0.0 →
1.1.0): added `("ACT", "healthcare_services_review"): AnalyticalMode.LEXICAL_ONLY`
to `UNIT_ANALYTICAL_MODES`.

**`services/coverage_registry.py`** (new, `REGISTRY_VERSION` 1.0.0): see
Section 11.

## 5. Extraction coverage

Real-corpus extraction run (`market_documents units extract ACT --force`)
after the above configuration change:

| Year | Result | `healthcare_services_review` |
| --- | --- | --- |
| 2016 | ineligible (no primary span) | -- |
| 2017 | COMPLETED_WITH_WARNINGS | heading not found -- GENUINE_ABSENCE |
| 2018 | COMPLETED_WITH_WARNINGS | heading not found -- GENUINE_ABSENCE |
| 2019 | COMPLETED_WITH_WARNINGS | heading not found -- GENUINE_ABSENCE |
| 2020 | ineligible (no primary span) | -- |
| 2021 | COMPLETED | **RESOLVED**, pp.62-63, 305 words |
| 2022 | COMPLETED_WITH_WARNINGS (unrelated: `cfo_conclusion` absent) | **RESOLVED**, pp.62-62, 247 words |
| 2023 | COMPLETED_WITH_WARNINGS (unrelated: `cfo_conclusion` absent) | **RESOLVED**, pp.64-64, 138 words |
| 2024 | COMPLETED_WITH_WARNINGS | heading not found -- GENUINE_ABSENCE |

2024's absence is genuine, not an extraction failure: ACT 2024 restructured
this content under a different heading, `"MEDICAL SCHEME ADMINISTRATION,
RISK MANAGEMENT AND TECHNOLOGY CLUSTER"`, a materially different heading
string, not a minor variant worth chasing.

## 6. Manual source-faithful review

Reviewed the earliest (2021), latest (2023), and one intermediate,
substantially-changed year (2022) against real canonical/legacy PDF text
directly (not legacy passages):

- **2021** (pp.62-63, 305 words): heading matches the intended concept
  exactly; start is correct (right after the heading); end is correct
  (page 63, right before "Healthcare Retail Financial Performance
  (Pharmaceutical)", a genuinely different subsection -- no spill-in);
  source text is complete, including a real continuation paragraph on page
  63 that only the Section 4 fix recovers. **Caveat**: the legacy
  `TextBlock` extraction for this report year does not mark several small
  numeric chart-label fragments between the two page-62 paragraphs
  (`-2%`, `385 Denis`, `411 Denis`, `2021 (excluding Denis)`, `26 Denis`)
  as `excluded_from_narrative`, so they appear embedded in `source_text`.
  This is a pre-existing legacy-pipeline characteristic (the canonical/7C.1a
  pipeline classifies the equivalent content `NUMERIC_FRAGMENT`,
  `excluded=True`), not something this track introduced, and it is not
  unique to this unit -- see Section 14 caveats.
- **2022** (pp.62-62, 247 words): heading matches; start/end correct
  (ends right before "Operating margin"); source text is clean narrative
  prose apart from two trailing numeric fragments (`15.1% -2.1%`), the same
  pre-existing legacy-classification characteristic, much less pronounced
  than 2021.
- **2023** (pp.64-64, 138 words): heading matches (all-caps variant,
  matched case-insensitively as designed); start/end correct (ends right
  before "Five-year summary of Profit before tax"); source text is a
  single, complete, clean paragraph with no numeric leakage at all.

Provenance is exact in all three years: `start_page`/`end_page` and the
persisted `SemanticUnitSourceBlock` spans point at the real blocks quoted
above, verified by re-reading directly from the database.

## 7. Alignment results

Real-corpus alignment run (`market_documents units align ACT --force`,
Track 7C.2, unmodified):

| Pair | `healthcare_services_review` |
| --- | --- |
| 2021→2022 | **MATCHED** (HIGH) -- exact unit_key match |
| 2022→2023 | **MATCHED** (HIGH) -- exact unit_key match |
| 2023→2024 | **UNRESOLVED_UPSTREAM** (NEEDS_REVIEW) -- "later run completed with warnings and has no 'healthcare_services_review' unit -- extraction limitation, not confirmed removal" |

No `ADDED` or `REMOVED` event was emitted for this unit at all -- the
system's own conservative design (Section 9 of the milestone instructions)
correctly reported `UNRESOLVED_UPSTREAM` for the 2023→2024 boundary rather
than asserting a substantive removal, since 2024's non-resolution is a
`COMPLETED_WITH_WARNINGS` extraction outcome, not a confirmed clean run.
Manually verified against Section 6 and Section 5's 2024 finding: this is
correct -- the section genuinely disappears under this heading in 2024, but
the alignment layer is right not to claim that with HIGH confidence from
extraction warnings alone.

## 8. Analytical routing

Real-corpus routing + lexical run (`market_documents units classify ACT --force`,
Track 7C.3, unmodified): both `MATCHED` alignments routed to `LEXICAL_ONLY`
via the new `UNIT_ANALYTICAL_MODES` entry, `HIGH` confidence, reason
`"configured LEXICAL_ONLY for ACT unit_key 'healthcare_services_review'"`.

## 9. Lexical results

| Pair | tfidf_cosine | unigram_jaccard | bigram_jaccard | edit_sim | seq_sim | words |
| --- | --- | --- | --- | --- | --- | --- |
| 2021→2022 | 0.914 | 0.718 | 0.622 | 0.775 | 0.812 | 306→248 (−58) |
| 2022→2023 | 0.815 | 0.464 | 0.362 | 0.364 | 0.549 | 248→138 (−110) |

## 10. Longitudinal sanity check

- 2021→2022 is near-stable prose (both years discuss the same
  Medscheme/Bonitas/Fedhealth/Polmed/GEMS narrative in almost the same
  structure) -- high similarity across every metric, consistent with the
  real source text quoted in Section 6.
- 2022→2023 is a genuine, large content reduction (3 paragraphs → 1
  paragraph, real source text confirmed in Section 6, not an extraction
  artifact) -- correspondingly lower similarity and a real word-count drop,
  exactly the "obvious rewrite/reduction produces visibly lower overlap"
  behavior the sanity check is meant to confirm. Inspected source
  boundaries per Section 12 of the instructions before accepting this as
  genuine rather than a defect: both years' boundaries were independently
  confirmed correct in Section 6, so the metric divergence reflects a real
  authoring choice (ACT's 2023 report layout is markedly leaner), not a
  boundary or extraction defect.
- Word counts (305, 247, 138) are plausible for a one-to-three-paragraph
  narrative subsection and track the real, decreasing page-budget these
  reports give this content over time.

## 11. Coverage registry

New `services/coverage_registry.py` (`REGISTRY_VERSION` 1.0.0), derived
declaratively from `semantic_unit_config.UNIT_CONFIGS`,
`analytical_eligibility.UNIT_ANALYTICAL_MODES`, and
`cutover_config.NEW_PIPELINE_NARRATIVE_SCOPE` -- never an independent
second source of truth for any of them:

```
BEL
  FINANCIAL_PERFORMANCE
    gross_margin:
      extraction: supported
      alignment: supported
      analytical_mode: LEXICAL_ONLY
      production: enabled

ACT
  FINANCIAL_PERFORMANCE
    cfo_conclusion:
      extraction: supported
      alignment: supported
      analytical_mode: LEXICAL_ONLY
      production: enabled

    healthcare_services_review:
      extraction: supported
      alignment: supported
      analytical_mode: LEXICAL_ONLY
      production: candidate
```

## 12. ADDED/REMOVED verification

None emitted for `healthcare_services_review` (Section 7) -- nothing to
verify.

## 13. Tests

- `tests/test_semantic_unit_extraction.py`: 4 new tests --
  `test_next_heading_skips_continuation_banner_and_keeps_scanning` (the new
  behavior, using a synthetic fixture shaped exactly like the real ACT 2021
  defect), `test_next_heading_still_stops_at_a_genuine_non_continuation_heading`
  (regression guard: an ordinary heading must still terminate the section),
  `test_is_continuation_heading_matches_trailing_word_only` (unit test of
  the new helper's word-boundary precision), plus the pre-existing suite
  re-run unmodified as regression coverage.
- `tests/test_analytical_eligibility_routing.py`: 1 new test --
  `test_configured_act_healthcare_services_review_routes_to_lexical_only`.
- `tests/test_coverage_registry.py` (new file): 5 tests covering
  derivation-from-source-of-truth, the new unit's `candidate` production
  status, an existing unit's `enabled` status, an unconfigured lookup
  returning `None`, and hash determinism.
- Known-good 7D.1 regression cases rerun directly against the real
  database: BEL `units extract`/`units align` (all 6 resolvable years
  still `COMPLETED`/`MATCHED`, byte-identical to pre-7D.2 status output);
  ACT `cfo_conclusion`'s persisted `source_text` for its two resolved years
  (2019, 2021) confirmed unchanged after the Section 4 fix.

All new/updated targeted tests pass (29 in the three primary files; 32 in
the broader alignment/eligibility/cutover suite re-run for regression).

## 14. Production-cutover candidates

`healthcare_services_review`: **READY_WITH_CAVEAT**.

Meets: source-faithful extraction across a genuine 3-year longitudinal
span; trustworthy alignment (two real `MATCHED` pairs, one correctly
conservative `UNRESOLVED_UPSTREAM`, no unverified `ADDED`/`REMOVED`);
correct analytical routing; valid, sanity-checked comparison output;
complete provenance.

Caveat: the legacy `TextBlock` extraction path (not the canonical/7C.1a
path -- `semantic_unit_extraction._run_extraction` reads only `TextBlock`,
never `CanonicalBlock`, unlike `schedule_localization.py`) leaves a small
amount of numeric-fragment noise embedded in 2021's and 2022's
`source_text` (Section 6). This does not corrupt the unit or invalidate
its lexical comparisons (the noise is a handful of short numeric tokens
diluting, not reversing, the similarity signal), but it is a real,
pre-existing extraction-quality gap this track did not fix (out of budget
under the one-correction cap) and should be resolved -- most likely by
migrating `semantic_unit_extraction.py` to prefer the canonical source the
same way `schedule_localization.py` already does -- before this unit is
promoted past `candidate`.

**Not enabled in production this track** -- `cutover_config.py` is
untouched; `coverage_registry` reports `production: candidate`, not
`enabled`, for this unit, per Section 14's explicit instruction not to
widen production scope in this milestone.

## 15. Caveats

- The `_matches_heading` substring false-positive risk found while
  evaluating `Capital management` (Section 3) is real, generic, and not
  unique to that rejected candidate -- any future `NEXT_HEADING` (or
  `ANCHOR_SENTENCE`, via its own `_matches_heading`-style start-heading
  check) unit whose configured heading string is a plausible substring of
  unrelated decorative/pull-quote text is at risk. Recommended as the next
  dedicated defect-remediation track.
- `semantic_unit_extraction.py`'s exclusive use of legacy `TextBlock`
  (never canonical) is a real coverage/quality gap relative to
  `schedule_localization.py`'s already-migrated canonical-preferred path
  (Section 14).
- BEL's post-2018 report structure has no further `NEXT_HEADING`-shaped
  candidates; any further BEL coverage expansion requires per-unit
  `ANCHOR_SENTENCE` calibration, which is legitimate but materially more
  work than pure configuration.

## 16. Final verdict

**PASS WITH CAVEATS — READY FOR CONTROLLED FURTHER EXPANSION.**

One new unit (`ACT healthcare_services_review`) was added, extracted,
aligned, routed, and lexically compared entirely through configuration
plus one small, generic, precedented parser correction -- confirming the
core claim that ordinary coverage expansion is now a repeatable
configuration + validation exercise. A second candidate was correctly
rejected rather than forced through with a second parser change, per this
track's own one-correction cap -- itself evidence the process is working
as designed, not a failure of the premise. Further expansion is real but
gated by two now-documented, generic issues (the substring false-positive
risk, and the legacy-vs-canonical extraction-path gap) that should be
addressed before the next coverage-expansion track, plus BEL requiring
bespoke anchor calibration rather than pure configuration for any unit
beyond `gross_margin`.

Per-unit verdict:

- `ACT healthcare_services_review`: **READY_WITH_CAVEAT**

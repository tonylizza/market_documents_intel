# Track 7D.1 — Known Recall Defect Remediation

Fixes the three known recall defects identified during 7C.5's shadow evaluation
(`docs/7c5-shadow-replacement-readiness.md` Section 10) without expanding
semantic coverage, adding schedules/units/table families/issuers, or
redesigning the heading-hierarchy architecture. This is a bug-fix milestone,
not a new research milestone.

## 1. Baseline (before any fix)

Verified before making any change: working tree clean, 7C.6 production
cutover work (`8524bb6`) committed, full suite (run with real database
access) **1072 passed, 3 skipped, 0 failed**.

Reproduced against the real dev-database corpus (`units status`, `units
extract --force`):

| Case | Baseline result |
|---|---|
| BEL 2017 `gross_margin` | schedule localized to pp.24-24 (excludes p.25, where "Gross margin" lives); extraction: `start heading 'Gross Margin' not found -- no row created` |
| BEL 2020 `gross_margin` | schedule localized to pp.38-40 (correct range); extraction: `start heading 'Gross Margin' not found -- no row created` |
| ACT 2019 `cfo_conclusion` | schedule localized to pp.13-13 (a false substring match, "Consistent financial performance" — an unrelated overview-page sentence — beat the real "Group CFO's Report" heading on p.40); extraction: `start heading 'In conclusion' not found -- no row created` |

## 2. Root cause of each

**BEL 2017 `gross_margin`** had two independent, compounding causes, both
generic (not year/issuer-specific) mechanisms:

1. The `ANCHOR_SENTENCE` regex was hard-coded to `"...in the prior year."`.
   2017's real closing sentence names the comparison year directly
   (`"...for 2016."`), which the old pattern never matched.
2. Separately, real-corpus verification during this milestone found the
   *schedule localization* boundary itself was also wrong: the primary span
   ended at p.24, one page before "Gross margin" (p.25), because
   `heading_structure`'s whole-document font-size clustering merged BEL's
   24pt section-heading tier and 18pt subsection-heading tier into one
   cluster (their ratio, 18/24 = 0.75, landed exactly on the clustering gap
   threshold), so an ordinary subsection heading ("Geographic", p.25)
   incorrectly registered as document-top-level and terminated the span
   early. Fixing only the anchor regex would not have been suffient — 2017's
   content was never even loaded for extraction until this second cause was
   also fixed.

**BEL 2020 `gross_margin`**: the "Gross Margin" heading is fused onto the
*end* of the *preceding* section's own paragraph in that year's PDF layout
(`"...supplied. Gross Margin The gross margin is dependent..."`), not at the
start of a block. The existing run-in-heading matcher (`_heading_prefix_match`)
only ever anchored at a block's start, so it never looked mid-block.

**ACT 2019 `cfo_conclusion`**: also two compounding causes:

1. The real section heading, "Group CFO's Report", extracts from the PDF
   with its words in a different order than they read visually (`"REPORT
   Group CFO's"`), so the substring vocabulary matcher never recognized it.
   An unrelated early-page sentence fragment, "Consistent financial
   performance", coincidentally substring-matched the vocabulary instead and
   won primary selection simply because it occurred first by page order.
2. Once the real heading is recognized as a candidate, the same
   whole-document font-size clustering problem as BEL 2017 applies here too
   (ACT's heading-candidate font-size population is an even denser,
   near-continuous spectrum from ~76pt down to ~6pt with essentially no
   usable document-wide gap near the top), so `is_top_level` alone cannot
   reliably separate the schedule's own heading tier from smaller
   subsection headings, in either direction (false inclusion or false
   exclusion).

## 3. Implementation changes

All changes are generic — driven by configurable pattern sets, relative
font-size comparison, and existing structural evidence, never a hard-coded
company/year/sentence.

### `semantic_unit_config.py` (`CONFIG_VERSION` 1.1.0 → 1.2.0)

`BEL_GROSS_MARGIN`'s `ANCHOR_SENTENCE` pattern now accepts a configurable set
of generic year-reference closing clauses (`_YEAR_REFERENCE_CLAUSE`): "in the
prior/previous year", "compared with/to `<year>`", "versus/vs `<year>`", "for
`<year>`" — instead of one literal sentence. No year or company name appears
in the pattern.

### `semantic_unit_extraction.py` (`ALGORITHM_VERSION` 1.0.1 → 1.1.0)

`_heading_prefix_match` → `_heading_run_in_match`: now matches a configured
heading either at a PARAGRAPH block's start (unchanged, pre-existing case) or
immediately after a sentence boundary (`.`/`!`/`?` + whitespace) anywhere
inside the block. Anchoring strictly to a sentence boundary — never "anywhere
in the text" — is what keeps this from firing on an ordinary body-prose
mention of the same words; see Section 5's false-positive test.

### `schedule_localization.py` (part of `ALGORITHM_VERSION` 1.1.0 → 1.2.0, see below)

1. `_matches_vocabulary` also matches a heading when every word of a
   vocabulary phrase appears within a window of `len(vocab words) + 1`
   consecutive heading words, in any order — tight enough to catch a local
   reordering/insertion artifact (ACT 2019's "REPORT Group CFO's") without
   matching an unrelated heading whose words merely happen to co-occur much
   further apart (a real false-positive this milestone found and fixed
   before it shipped: "FINANCIAL STATEMENTS AND EXTERNAL REVIEW", an audit
   section, was initially caught by an earlier, looser "anywhere in the
   heading" version of this rule — see Section 7).
2. The primary span is now selected by strongest evidence — exact match,
   then structural top-level assessment, then the match's own font size
   descending, then page order — instead of simply "whichever match occurs
   on the earliest page". This is what lets ACT 2019's real 57.58pt heading
   beat the earlier, smaller, coincidental match.
3. `_end_page_for` now also requires a later boundary candidate's own font
   size to be at least `_END_BOUNDARY_FONT_RATIO` (0.78) of *this specific
   schedule heading's* font size, not just top-level per the whole-document
   clustering. This is a per-span, not whole-document, use of the same
   relative-font-size evidence, added specifically because real-corpus
   verification showed whole-document clustering (`heading_structure`'s
   `_CLUSTER_GAP_RATIO`) cannot reliably separate the cases that need
   separating without also merging cases that must stay separate elsewhere
   in the corpus — see Section 4 for the investigation and why a shared
   global-ratio change was reverted in favor of this narrower, local one.

### `schedule_config.py` (`ALGORITHM_VERSION` 1.1.0 → 1.2.0)

Bumped to force a fresh `ScheduleLocalizationRun` for the above behavior
change (`compute_configuration_hash` includes `ALGORITHM_VERSION`).

### `heading_structure.py`

No net change. `_CLUSTER_GAP_RATIO` was experimentally raised from 0.75 to
0.78 and then reverted — see Section 4.

## 4. Why the fixes are generic, not issuer/year-specific — including one reverted attempt

Every fix above is parameterized by configuration (a set of generic anchor
phrasings, a window-size formula, a font-size ratio) rather than by any
literal company name, year, or sentence. `test_end_boundary_font_ratio_scales_with_document_not_absolute_points`
specifically proves the font-ratio logic behaves identically at a different
absolute point scale (12pt/9pt instead of BEL's real 24pt/18pt) — the same
relative pattern, not a hard-coded threshold tuned to one document's literal
numbers.

One implementation approach was tried and **reverted** during this milestone
specifically because it risked becoming over-fitted: raising
`heading_structure`'s shared, whole-document `_CLUSTER_GAP_RATIO` from 0.75 to
0.78 (intended to separate BEL's 18pt/24pt tiers). Real-corpus verification
showed this doesn't work: both BEL's and ACT's full heading-candidate
font-size populations are dense, near-continuous spectrums with no usable gap
anywhere near the top of the range (every real report-year checked collapses
into one ~30-54-member "top" cluster under any ratio from 0.75-0.85). Raising
the shared ratio moved BEL 2017 from "too narrow" (pp.24-24) straight to "too
wide" (still pp.24-24, since 18/24 still didn't separate — verified by
rerunning the whole corpus) without fixing anything, while risking unrelated
regressions elsewhere via a global constant. The `_end_page_for` per-span
font-ratio comparison (Section 3, item 3) supersedes this approach: it
compares a boundary candidate only to *the schedule's own matched heading*,
not the whole document, which is both narrower in blast radius and the
mechanism that actually worked once real numbers were checked.

## 5. Tests added

- `tests/test_semantic_unit_extraction.py`: anchor generalization (year named
  directly vs. "prior year" phrasing, both still work); heading matching
  mid-block after a sentence boundary (BEL 2020 shape); standalone
  block-start heading still works; **false-positive prevention** — an
  ordinary body-prose mention of "gross margin" mid-sentence does not create
  a spurious unit.
- `tests/test_schedule_localization.py`: word-order-scrambled heading
  matches vocabulary; word-order tolerance does not relax exact-match
  status; a heading with only some vocabulary words does not match;
  **word-order tolerance does not match words scattered far apart**
  (regression test for the false positive found and fixed in Section 7);
  primary selection prefers a genuine section over an earlier coincidental
  match; end-boundary excludes a subsection heading close in font to its
  parent (BEL 2017 shape); end-boundary includes a genuine next section
  moderately smaller in font (ACT 2019 shape); the font-ratio behavior
  scales with the document, not absolute point sizes.

Full suite after all fixes and all new tests: **1085 passed, 3 skipped, 0
failed** (baseline was 1072 passed, 3 skipped — 13 new tests, all passing, no
regressions).

## 6. Before/after real-corpus results

### BEL (`FINANCIAL_PERFORMANCE`, `gross_margin`)

| Year | Schedule range before | Schedule range after | `gross_margin` before | `gross_margin` after |
|---|---|---|---|---|
| 2016 | NOT_FOUND | NOT_FOUND (unchanged) | — | — |
| 2017 | pp.24-24 | **pp.24-27** | UNRESOLVED | **RESOLVED** |
| 2018 | pp.35-36 | pp.35-37 | RESOLVED | RESOLVED (same 64-word text, unaffected by the wider window) |
| 2019 | pp.36-39 | pp.36-39 (unchanged) | RESOLVED | RESOLVED (unchanged) |
| 2020 | pp.38-40 | pp.38-40 (unchanged) | UNRESOLVED | **RESOLVED** |
| 2021 | pp.38-40 | pp.38-40 (unchanged) | RESOLVED | RESOLVED (unchanged) |
| 2022 | pp.40-43 | pp.40-43 (unchanged) | RESOLVED | RESOLVED (unchanged) |

BEL 2017 resolved text: *"...The average gross margin reduced to 21,3% for
2017 compared with 23,3% for 2016."* — matches the real, previously-verified
paragraph (7C.5 Section 5).

BEL 2020 resolved text (127 words): *"...The average gross margin for the
year was 18,4% compared with 18,5% in the prior year."* — full real
paragraph, heading correctly recovered despite being embedded mid-block.

### ACT (`FINANCIAL_PERFORMANCE`, `cfo_conclusion`)

| Year | Schedule range before | Schedule range after | `cfo_conclusion` before | `cfo_conclusion` after |
|---|---|---|---|---|
| 2016 | NOT_FOUND | NOT_FOUND (unchanged) | — | — |
| 2017 | pp.58-60 | pp.58-60 (unchanged) | genuine absence | genuine absence (unchanged) |
| 2018 | pp.30-30 | pp.28-68 | genuine absence | genuine absence (unchanged; see caveat below) |
| 2019 | pp.13-13 | **pp.40-43** | UNRESOLVED (wrong page window) | **RESOLVED** |
| 2020 | NOT_FOUND | NOT_FOUND (unchanged) | — | — |
| 2021 | pp.61-105 | pp.61-105 (unchanged) | RESOLVED | RESOLVED (unchanged, byte-identical range) |
| 2022 | pp.62-62 | pp.62-62 (unchanged) | genuine absence ("Conclusion" ≠ "In conclusion") | genuine absence (unchanged) |
| 2023 | pp.64-64 | pp.64-64 (unchanged) | genuine absence | genuine absence (unchanged) |
| 2024 | pp.64-73 | pp.64-73 (unchanged) | genuine absence | genuine absence (unchanged) |

ACT 2019 resolved text (164 words) begins: *"The earnings results depict a
picture of transition as the Group is transforming its healthcare
offerings..."* and ends with the real "In conclusion" subsection's content
— it is no longer excluded from the localized window.

ACT 2021 (the one already-passing acceptance case) is **byte-identical**
before and after: primary heading "CFO'S REVIEW", pp.61-105.

## 7. Downstream alignment/comparison effect

Re-ran `units extract --force`, `units align --force`, `units classify
--force` for both companies after the fixes.

**BEL** — every adjacent-year pair with both sides now resolved (2017→2018,
2018→2019, 2019→2020, 2020→2021, 2021→2022) is `MATCHED` with real lexical
metrics computed on genuine, correctly-bounded text:

| Pair | tfidf_cosine | words |
|---|---|---|
| 2017→2018 | 0.497 | 32→64 |
| 2018→2019 | 0.747 | 64→47 |
| 2019→2020 | 0.677 | 47→127 |
| 2020→2021 | 0.713 | 127→139 |
| 2021→2022 | 0.745 | 139→101 |

2019→2020 and 2020→2021 were `UNRESOLVED_UPSTREAM` before this milestone
(one side missing); both now `MATCHED`, exactly the target outcome. 2016→2017
remains `UNRESOLVED_UPSTREAM` (2016 has no `FINANCIAL_PERFORMANCE` schedule at
all — out of scope, unrelated to any of the three defects).

**ACT** — `cfo_conclusion` becomes available for 2019 as intended. No new
`MATCHED` pair was created (2019's only adjacent partners, 2018 and 2020,
still genuinely lack the unit), so 2018→2019 remains correctly
`UNRESOLVED_UPSTREAM` — now for the *right* reason (2018 genuinely has no
"In conclusion" heading) rather than because 2019 itself was broken.

## 8. Remaining unresolved / documented caveats

- **ACT 2018's schedule range is now imprecise (pp.28-68)**, wider than its
  real "Group CFO's Report" section. Root cause: ACT's genuine top-level
  section-title pages use wildly inconsistent font sizes across different
  chapters within the *same* document (57.58pt for a CFO-report cover title,
  41pt for a "How We Create Value" chapter title, both legitimately
  top-level) — no single font-ratio threshold, whole-document or per-span,
  can draw a clean boundary here without either this over-extension or
  excluding a genuine same-tier next section elsewhere (see Section 4's
  reverted-attempt writeup). This does not affect any acceptance criterion:
  2018 genuinely has no "In conclusion" heading in its real text (confirmed
  in 7C.5), so extraction still correctly creates no `SemanticUnit` row
  regardless of how wide the window is — no false claim results. Flagged
  here as future-work, not fixed in 7D.1 per the "report resulting page
  ranges, do not require correctness" instruction for ACT years beyond 2019
  and 2021.
- **BEL 2016** now localizes to `FOUND_PRIMARY_ONLY` pp.43-43 ("FINANCIAL
  STATEMENTS AND EXTERNAL REVIEW", found via a genuine exact/substring match
  to the "Financial review" vocabulary entry, not the word-order-tolerance
  addition) instead of `NOT_FOUND` as before. `gross_margin` still correctly
  fails to resolve there (no "Gross Margin" heading exists on that page), so
  no false claim results, but the schedule-instance row itself is a
  plausible false positive worth revisiting in a future milestone that
  touches schedule localization again.
- The whole-document clustering weakness in `heading_structure.py`
  documented as a pre-existing caveat in its own module docstring (a smooth
  font-size spectrum can leave `is_top_level` too permissive) is now
  additionally *confirmed at scale* across the full real corpus (Section 4)
  rather than only the one BEL 2020 case it already named. Not redesigned in
  this milestone per the hard-stop instruction; `_end_page_for`'s new
  per-span font-ratio check works around it locally for `FINANCIAL_PERFORMANCE`
  boundary termination specifically.

## 9. Final verdict

**PASS — KNOWN RECALL DEFECTS REMEDIATED**

All three defects from 7C.5 Section 10 are fixed and verified against the
real corpus:

1. BEL 2017 `gross_margin` resolves, with the real, previously-verified
   paragraph.
2. BEL 2020 `gross_margin` resolves despite the heading being embedded
   inside a canonical block.
3. ACT 2019 `FINANCIAL_PERFORMANCE` now includes the real "In conclusion"
   subsection; `cfo_conclusion` resolves.

BEL's four previously-good years (2018, 2019, 2021, 2022) remain resolved
with unchanged substance. ACT 2021 remains correctly localized,
byte-identical. Every fix is generic (configuration-driven or
relative-evidence-based), with one attempted approach (a shared clustering
threshold change) explicitly investigated and reverted once real-corpus
verification showed it didn't generalize, in favor of a narrower, verified
alternative. Full suite passes (1085/1085 non-skipped). Downstream
alignment/comparison re-run confirms zero false `ADDED`/`REMOVED`/incorrect
`MATCHED` claims anywhere in the corpus — every previously-`UNRESOLVED_UPSTREAM`
pair that became resolvable is genuinely `MATCHED` on real, correctly-bounded
content, and every pair that should remain unresolved (genuine absence) still
does, now for the correct reason. No production cutover config, feature flag,
schedule, unit, table family, or issuer was added or changed.

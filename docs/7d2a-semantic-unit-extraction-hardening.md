# Track 7D.2a — Semantic Unit Extraction Hardening

Scope: two generic hardening fixes to `services/semantic_unit_extraction.py`,
both explicitly deferred by Track 7D.2
(docs/7d2-financial-performance-unit-expansion.md), plus real-corpus
re-verification and a re-evaluation of `ACT healthcare_services_review`'s
production-cutover candidacy. No new unit, schedule, or issuer is added.
`Capital management` is verified, not shipped -- it remains unconfigured
in `semantic_unit_config.py`.

## 1. Canonical source preference

`semantic_unit_extraction._run_extraction` now prefers the canonical PDF
source (Track 7C.1a) over legacy `TextBlock` when a report has a current
successful `CanonicalExtractionRun`, mirroring
`schedule_localization._run_localization`'s own canonical preference (its
7C.1b) -- same `source_adapter.load_source_pages` /
`classify_source_pages` calls, and the already-existing
`source_adapter.build_unit_blocks` helper (previously unused) for the
report's schedule-instance page range. Falls back to legacy `TextBlock`,
unchanged, for a report with no canonical extraction yet (none observed in
the real BEL/ACT corpus -- all 16 report-years across both tickers have a
current canonical run).

**Schema change required**: `SemanticUnitSourceBlock.text_block_id` was a
required, non-nullable FK to `text_blocks.id` and cannot record provenance
from a canonical run, whose blocks live in `canonical_blocks`, a different
table with different primary keys. Migration `a4c1e8f2b6d9` makes
`text_block_id` nullable and adds a nullable `canonical_block_id` FK to
`canonical_blocks.id` (ondelete CASCADE, indexed), mirroring the same
canonical-block-FK pattern `structured_table.py` already uses (e.g.
`StructuredTableRow.canonical_block_id`). Exactly one of the two is set per
row, enforced in `_run_extraction` (never a database constraint, consistent
with how this codebase already treats other either/or provenance columns).

## 2. Exact/substring/word-order-aware heading matching

`_matches_heading` (formerly a bare case-insensitive substring check) now
returns `(matched, exact)` with the same exact/substring/word-order-
tolerant evidence hierarchy `schedule_localization._matches_vocabulary`
already uses. `extract_unit`'s start-heading scan now collects every
matching candidate in the report (standalone `HEADING_CANDIDATE` blocks via
`_matches_heading`, and `_heading_run_in_match`'s regex matches, which are
exact by construction) and ranks them -- an exact match first, then
earliest position -- instead of simply taking whichever match occurs first
in reading order.

This is exactly the generic false-positive risk Track 7D.2 documented and
deliberately left unfixed (its own one-bounded-generic-parser-correction
budget was already spent on the `NEXT_HEADING` continuation-banner fix):
real ACT 2024 corpus text contains an unrelated decorative pull-quote
heading-candidate fragment, "by prudent capital management policies", a
bare substring match for a heading like "Capital management" that sits
earlier in reading order (page 65) than the real, exact "CAPITAL
MANAGEMENT" section heading (page 69). The pre-7D.2a first-positional-match
behavior let the false match win and the real section was never reached.

## 3. Real-corpus re-run: no regressions

`market_documents units extract BEL --force` and
`market_documents units extract ACT --force`, re-run against the real
corpus after both changes:

- **BEL**: 2016 ineligible (no primary span), 2017-2022 all `COMPLETED` --
  identical status pattern to pre-7D.2a.
- **ACT**: identical `COMPLETED`/`COMPLETED_WITH_WARNINGS` pattern and the
  same genuine-absence years as Track 7D.2 Section 5 documented (2016/2020
  ineligible; `cfo_conclusion` absent 2017/2018/2022/2023/2024;
  `healthcare_services_review` absent 2017/2018/2019/2024, resolved
  2021/2022/2023).

Directly inspected the persisted rows for the current (post-7D.2a) run of
each previously-shipped unit:

- `BEL gross_margin`: all 6 resolvable years still `RESOLVED`, same
  start/end pages and word counts as before.
- `ACT cfo_conclusion`: 2019 and 2021 still `RESOLVED`, same pages/word
  counts (164 and 136 words respectively).
- `ACT healthcare_services_review`: 2021/2022/2023 still `RESOLVED`, same
  pages and word counts (305/247/138) as Track 7D.2 Section 5/9 documented.
  All three now persist via `canonical_block_id` (confirmed directly against
  the database), not `text_block_id`.

No unit lost a previously-`RESOLVED` year, gained a spurious one, or
changed its resolved page range -- both hardening changes are regression-
free against every unit shipped before this track.

## 4. Capital management: false-match fix verified against both source paths

Re-evaluated ACT `Capital management` (`NEXT_HEADING`) directly against the
real 2021 and 2024 corpus, using a throwaway `UnitConfig` (not added to
`semantic_unit_config.py` -- this track hardens the parser, it does not
re-open Track 7D.2's coverage-expansion decision):

- **Canonical source**: the pull-quote fragment "by prudent capital
  management policies" is classified `PARAGRAPH`, not `HEADING_CANDIDATE`,
  under the canonical/`source_adapter` path -- canonical block segmentation
  differs enough from legacy `TextBlock` that the false-positive risk does
  not even reproduce there for this specific case. 2021 resolves pp.64-65;
  2024 resolves to the real "CAPITAL MANAGEMENT" heading, pp.69.
- **Legacy `TextBlock` source** (forced, to isolate the matching fix from
  the source-preference fix): the same pull-quote fragment *is* classified
  `HEADING_CANDIDATE` on page 65, exactly as Track 7D.2 Section 3
  documented. Re-running `extract_unit` with the hardened `_matches_heading`
  against these legacy blocks correctly resolves to the real heading on
  page 69, not the page-65 false match -- confirming the ranking fix works
  on its own, independent of which source path is in effect.

Both the source-preference change and the matching-hierarchy change
independently prevent this specific defect; together they are
defense-in-depth, not redundant, since a future report or a report with no
canonical run yet could still reproduce the canonical-side non-reproduction
by coincidence.

## 5. `healthcare_services_review` production re-evaluation

Track 7D.2 Section 14 flagged one caveat blocking production promotion: a
small amount of numeric-fragment noise (`-2%`, `385 Denis`, `411 Denis`,
etc.) embedded in 2021's and 2022's persisted `source_text`, attributed to
legacy `TextBlock` extraction not marking these fragments
`excluded_from_narrative`, and recommended "most likely... migrating
`semantic_unit_extraction.py` to prefer the canonical source" as the fix.

**That migration is now done (Section 1) -- and the noise is still
present.** Re-inspected 2021's and 2022's persisted `source_text` after
this track's canonical-preference change: `-2%`, `385 Denis`, `411 Denis`,
`2021 (excluding Denis)`, `26 Denis` (2021) and `15.1% -2.1%` (2022) are
still embedded, unchanged from before.

Root cause, confirmed directly: `source_adapter.classify_source_pages`
deliberately reuses `block_classification.classify_block` verbatim (its own
docstring: "not reimplemented here... 7C.1a's job is to fix the *source*
representation, not to invent a second, divergent classification
heuristic"). A fragment like "385 Denis" has `digit_ratio` ≈0.33 (3 digits
out of 9 characters) -- below `numeric_fragment_min_digit_ratio` (0.5) --
and `alpha_ratio` ≈0.56 with only one numeric token, so it clears neither
the `NUMERIC_FRAGMENT` nor the `TABLE_LIKE` nor the `DECORATIVE_OR_FRAGMENT`
threshold in `classify_block`. This is a real, generic gap in the shared
digit-ratio classifier's handling of short alphanumeric chart-label
fragments (a number paired with a one-word data-series label) -- it exists
identically whether the block comes from canonical or legacy extraction,
because both paths call the same function. The canonical migration changed
*which table's row* records provenance (`canonical_block_id` vs.
`text_block_id`, Section 1) and, separately, prevented one specific
false-heading-match scenario from reproducing (Section 4) -- but it was
never going to change classification outcomes that don't depend on the
source table at all.

**Verdict: `healthcare_services_review` remains `candidate`, not
`enabled`.** `cutover_config.py` is untouched; `coverage_registry` still
reports `production: candidate` for this unit. The Section 14 caveat is
downgraded in severity (provenance is now canonical-sourced and the
false-heading-match risk is independently closed, Sections 1 and 4) but not
eliminated -- the numeric-fragment noise itself is unresolved and requires
a distinct, generic fix to `block_classification.classify_block`'s
digit-ratio/alpha-ratio thresholds for short mixed alphanumeric fragments,
verified against a regression suite across the existing corpus (BEL and
ACT both use table-like/chart-heavy layouts that would be affected).
Recommended as the next dedicated defect-remediation track -- **not**
attempted here, consistent with this track's own two-fix budget (canonical
preference + heading-matching hierarchy) already being spent.

## 6. Tests

`tests/test_semantic_unit_extraction.py`: 6 new pure-algorithm tests --
`test_matches_heading_exact_normalized_match`,
`test_matches_heading_substring_match_is_not_exact`,
`test_matches_heading_word_order_tolerant_match_is_not_exact`,
`test_matches_heading_unrelated_text_does_not_match`,
`test_start_heading_selection_prefers_exact_match_over_earlier_coincidental_substring`
(a synthetic fixture shaped exactly like the real ACT 2024 defect), and
`test_start_heading_selection_still_picks_earliest_among_equal_exactness`
(regression guard: equal-exactness ties still resolve to the earliest
match). All 20 tests in the file pass, plus the full existing suite (1100
passed, 3 skipped) after the migration and model changes.

The canonical-preference orchestration change is not separately unit
tested at the DB level -- mirroring `schedule_localization.py`'s own
canonical-preference change (7C.1b), which is likewise verified only via
real-corpus runs, not a DB-fixture test.

## 7. Final verdict

**PASS.** Both hardening fixes are shipped, generic, and verified
regression-free against every previously-shipped unit (BEL `gross_margin`,
ACT `cfo_conclusion`, ACT `healthcare_services_review`) via direct
real-corpus re-extraction. The `Capital management` false-match defect
Track 7D.2 identified and deferred is confirmed fixed against both the
canonical and legacy source paths. `healthcare_services_review`'s
production-candidacy re-evaluation is honest, not assumed: the specific
caveat Track 7D.2 flagged is not resolved by this track's canonical
migration, a distinct generic classifier gap is identified as the real
cause, and production status is correctly left unchanged at `candidate`
rather than promoted on the strength of an incomplete fix.

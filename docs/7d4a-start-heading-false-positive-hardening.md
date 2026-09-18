# Track 7D.4a: Start-Heading False-Positive Hardening

## 0. Scope note

This track fixes one recurring, schedule-agnostic semantic-unit
start-heading defect: ordinary prose that happens to open with a
configured heading's exact words can outrank the real, standalone section
heading later in the same document. No new schedule, semantic unit,
issuer, boundary strategy, comparison metric, or table parser was added.
No schedule localization, end-boundary logic, or analytical routing was
changed. Production remains on the existing stable publication; no
production database change was made; `cutover_config.py` was not touched.

## 1. Defect history across the three documented cases

Three independently-documented real-corpus cases motivated this track:

| schedule | unit | documented in |
|---|---|---|
| FINANCIAL_PERFORMANCE | "Capital management" (never configured) | docs/7d2-financial-performance-unit-expansion.md |
| CORPORATE_GOVERNANCE | `combined_assurance` | docs/7d3-corporate-governance-expansion.md |
| REMUNERATION | `remuneration_governance` | docs/7d4-corpus-wide-remuneration-expansion.md |

Real-corpus investigation (Section 3) found these are **not the same
defect mechanism**. "Capital management" was already fixed by Track
7D.2a's exact/substring/word-order-tolerant tiering on `HEADING_CANDIDATE`
blocks (`_matches_heading`, ranked `(exact, position)`): its false
candidate ("by prudent capital management policies") is a bare-substring
match beaten outright by the real, exact "CAPITAL MANAGEMENT" heading, and
`tests/test_semantic_unit_extraction.py::test_start_heading_selection_prefers_exact_match_over_earlier_coincidental_substring`
already regression-tests it. `combined_assurance` and
`remuneration_governance`, by contrast, are both caused by a different
path entirely: `_heading_run_in_match` (the PARAGRAPH run-in matcher
added in Track 7D.1 for the legitimate BEL "Gross Margin" fused-heading
case) firing on an ordinary paragraph that merely *opens* with the
configured heading's words before continuing the same grammatical
sentence. That match is exact-by-construction and can precede the real
`HEADING_CANDIDATE` heading in reading order, so it won outright under the
existing `(exact, position)` ranking -- no `HEADING_CANDIDATE`
exact/substring/word-order tiering was ever involved in either real
defect.

## 2. Current algorithm behavior (traced before any change)

`extract_unit` (`src/market_documents/services/semantic_unit_extraction.py`)
scans every block in the schedule's page range, in reading order:

- A `HEADING_CANDIDATE` block is tested with `_matches_heading`, which
  returns `(matched, exact)`: exact normalized-text match, then bare
  substring, then a tight word-order-tolerant window match.
- A `PARAGRAPH` block is tested with `_heading_run_in_match`, a regex
  anchored to the block's start or immediately after a sentence-ending
  `.`/`!`/`?`. A run-in match is always `exact=True` by construction (the
  regex requires the heading's exact word sequence).
- Every match across the whole range is collected as a candidate tuple
  `(position, exact, heading_text, remainder_offset)` and ranked by
  `(0 if exact else 1, position)` -- exact beats substring/tolerant;
  among ties, the earliest wins.

No other block type is ever a start-heading source, there is no
structural/font-based signal in this ranking at all (unlike
`schedule_localization.py`'s sibling `localize_schedule`, which also
weighs `is_top_level` and font size via `heading_structure.py`), and
`extract_unit`'s `UnitBlock` carries no font/structural fields to rank on
even if it wanted to.

## 3. Real-corpus failure reproductions

Queried the live local Postgres corpus directly (`docker compose`, canonical
extraction path) rather than relying on the docs' prose summaries alone.

**ACT 2022/2023 CORPORATE_GOVERNANCE `combined_assurance`** (config:
`start_heading="Combined assurance"`, NEXT_HEADING):

| field | value |
|---|---|
| false block (2022) | p.88, PARAGRAPH: `"Combined assurance approach\nStrong Lead Independent Director"` |
| false block (2023) | p.100, PARAGRAPH: `"Combined assurance approach\nStrong Lead Independent Director"` |
| match type | run-in, exact-by-construction, at block start |
| real heading (2022) | p.107, HEADING_CANDIDATE, exact: `"Combined assurance"` |
| real heading (2023) | p.120, HEADING_CANDIDATE, exact: `"Combined assurance"` |
| why the false candidate won | both are `exact=True` by the run-in matcher's construction; the false one is earlier in reading order, and `(exact, position)` ranking has no further tie-break |

**ACT 2024 REMUNERATION `remuneration_governance`** (config:
`start_heading="Remuneration governance"`, NEXT_HEADING):

| field | value |
|---|---|
| false block | p.121, PARAGRAPH: `"Remuneration governance to remain top of mind with a \ngreater focus on approval frameworks given the larger Sanlam Group structure AfroCentric is now part of."` |
| match type | run-in, exact-by-construction, at block start |
| real heading | p.122, HEADING_CANDIDATE, exact: `"Remuneration governance"` |
| why the false candidate won | same mechanism as above |

**ACT 2019 REMUNERATION `remuneration_policy_changes`** (a legitimate case
discovered while designing the fix, not a defect -- see Section 8):

| field | value |
|---|---|
| block | p.98, PARAGRAPH: `"Changes to the remuneration and related policies \nfor the 2019 financial year\nThe committee reviewed..."` |
| match type | run-in, exact, at block start |
| shape | the configured heading (`"Changes to the remuneration and related policies"`) is only the first line of the document's own two-line heading; the year suffix `"for the 2019 financial year"` wraps onto the next line before the real, capitalized body paragraph starts |

## 4. Selected evidence/ranking design

The false positives in Section 3 are not a `HEADING_CANDIDATE`
exact/substring/word-order ranking problem (7D.2a's fix already covers
that path correctly), so no change was made to `_matches_heading` or to
`HEADING_CANDIDATE` candidate ranking. The fix is scoped to
`_heading_run_in_match`'s PARAGRAPH path only, since that is where both
real defects occur.

The design principle: a genuine run-in heading is immediately followed by
a *fresh* sentence (the legitimate BEL case -- "Gross Margin The gross
margin is dependent on..."); a false positive is immediately followed by
a *continuation of the same sentence* (real ACT cases -- "Remuneration
governance **to remain** top of mind..."; "Combined assurance **approach**
Strong Lead Independent Director..."). Capitalization of the very next
letter after the match is a cheap, generic, deterministic proxy for that
distinction, requiring no new structural signal (font size, block width,
etc.) and no change to `UnitBlock` or the source-adapter pipeline.

The one refinement needed came directly from the ACT 2019 counter-example
(Section 3): a line break between the match and the lowercase continuation
must **not** trigger rejection, since a genuine heading can itself wrap a
suffix onto the next line before the real body starts. Both real false
positives have their lowercase continuation on the *same line* as the
match (no line break); the legitimate 2019 case has a line break. That is
the actual discriminating signal, not lowercase alone.

Substring/tolerant matching on `HEADING_CANDIDATE` blocks was left
untouched, per the milestone's explicit instruction not to solve this by
banning it globally -- it remains necessary for the real PDF-extraction
artifacts (`"(continued)"` suffixes, word reordering) it was built for.

## 5. Implementation

`semantic_unit_extraction.py`, `ALGORITHM_VERSION` 1.5.0 -> 1.6.0. One new
function, `_run_in_remainder_is_prose_continuation(text, match) -> bool`:
rejects a run-in match when the text immediately following it (after
stripping leading whitespace) starts with a lowercase letter **and** no
newline appears in the whitespace between the match and that letter.
Wired into `extract_unit`'s PARAGRAPH branch: a run-in match is only added
as a candidate when this returns `False`. A rejected candidate is treated
as no match at all, not merely demoted -- this lets a later, genuine
`HEADING_CANDIDATE` match win instead of the unit going `UNRESOLVED` or
`None`. No changes to `_matches_heading`, `HEADING_CANDIDATE` ranking,
`NEXT_HEADING`/`ANCHOR_SENTENCE` boundary logic, or `_run_extraction`'s
page-range widening (Tracks 7D.3/7D.4, unchanged).

## 6. Before/after known cases

Verified directly against the live corpus (canonical extraction path, real
`ScheduleInstance` ranges), not synthetic fixtures:

| case | before | after |
|---|---|---|
| ACT 2022 `combined_assurance` | p.88, wrong infographic content | p.107, RESOLVED, `"Our combined assurance framework is supported by the three lines of defence model..."` |
| ACT 2023 `combined_assurance` | p.100, wrong infographic content | p.120, RESOLVED, same stable framework text |
| ACT 2024 `remuneration_governance` | p.121, wrong culture/voting passage | p.122, RESOLVED, `"AfroCentric's remuneration policy, structures and processes are set within a governance framework..."` (the same stable boilerplate pattern as 2020-2023) |
| ACT 2020/2021 `combined_assurance` | already correct (p.92/p.104) | unchanged |
| ACT 2016-2023 `remuneration_governance` | already correct | unchanged |
| ACT 2019 `remuneration_policy_changes` | p.98, correct | unchanged after the line-break refinement (Section 8) |
| BEL `gross_margin` (all validated years) | correct (run-in and standalone) | unchanged |

All three of Section 9's required outcomes in the milestone brief are met:
Capital management was never regressed (untouched code path); `combined_assurance`
2022/2023 now resolve to the real section; `remuneration_governance` 2024
now resolves to the real heading.

## 7. Corpus-wide safety sweep

Ran every configured `UnitConfig` (14 units across ACT, BEL; KP2/SBP/SDL
have none configured; SUR has three) against every report year with a
current canonical extraction and schedule localization -- 6 tickers, every
available year, comparing the pre-7D.4a candidate-selection logic
(reproduced inline, not by reverting the fix) against the post-fix
`extract_unit` directly. Zero DB/query errors across the full sweep.

First pass (naive "lowercase == reject" rule, before the line-break
refinement) found 13 differing resolutions; one -- ACT 2019
`remuneration_policy_changes` -- was a real regression (RESOLVED -> `None`),
which motivated the Section 4 refinement. After the refinement, the same
13-row sweep was re-run.

## 8. Changed-resolution matrix (final, after refinement)

| ticker | year | schedule | unit_key | changed? | reason |
|---|---|---|---|---|---|
| ACT | 2017 | REMUNERATION | remuneration_governance | display-only | same page (102), same match; sweep's diff key compares full raw block text vs. `source_heading`-only, not a functional change |
| ACT | 2019 | REMUNERATION | remuneration_policy_changes | display-only | same page (98); confirmed **not** a regression after the line-break refinement -- the year-suffixed heading (Section 3) still resolves |
| ACT | 2019 | REMUNERATION | remuneration_governance | display-only | same page (101), same match |
| ACT | 2020 | CORPORATE_GOVERNANCE | combined_assurance | display-only | same page (92), already correct before and after |
| ACT | 2021 | CORPORATE_GOVERNANCE | combined_assurance | display-only | same page (104), already correct before and after |
| **ACT** | **2022** | **CORPORATE_GOVERNANCE** | **combined_assurance** | **real fix** | p.88 (wrong) -> p.107 (real section) |
| **ACT** | **2023** | **CORPORATE_GOVERNANCE** | **combined_assurance** | **real fix** | p.100 (wrong) -> p.120 (real section) |
| **ACT** | **2024** | **REMUNERATION** | **remuneration_governance** | **real fix** | p.121 (wrong) -> p.122 (real heading) |
| BEL | 2018 | FINANCIAL_PERFORMANCE | gross_margin | display-only | same page (36) |
| BEL | 2019 | FINANCIAL_PERFORMANCE | gross_margin | display-only | same page (37) |
| BEL | 2020 | FINANCIAL_PERFORMANCE | gross_margin | display-only | same page (39), the known 7D.1 mid-block-fusion case, already correct |
| BEL | 2021 | FINANCIAL_PERFORMANCE | gross_margin | display-only | same page (39) |
| BEL | 2022 | FINANCIAL_PERFORMANCE | gross_margin | display-only | same page (41) |

Every "display-only" row has an identical `start_page` before and after;
the apparent text difference is an artifact of the sweep script's own
diff key (full raw block text vs. `SemanticUnitExtractionResult.source_heading`,
which is heading-text-only for a run-in match), not a functional change --
manually inspected and confirmed for all 10 such rows. **Exactly 3 real
functional changes exist in the entire corpus, and all 3 are the intended
fixes.** No unit that previously resolved lost its heading; no unit
gained a spurious new resolution; no unrelated unit's page boundary moved.

## 9. Alignment/comparison effects

Recomputed lexical comparison (`compute_lexical_metrics`) on the corrected
content:

**`combined_assurance` adjacent-year pairs, before vs. after (2021->2022 and
2023->2024 were the two contaminated pairs 7D.3 documented):**

| pair | before (documented, 7D.3) | after (this track) |
|---|---|---|
| 2020->2021 | (already correct) | cosine=0.967, jaccard=0.918, words 65->66 |
| 2021->2022 | cosine=0.33 (misleadingly low -- both sides different wrong content) | cosine=0.960, jaccard=0.896, words 66->64 |
| 2022->2023 | cosine=0.87 (misleadingly *stable* -- both sides share the same wrong content) | cosine=1.000, jaccard=1.000, words 64->64 |
| 2023->2024 | cosine=0.27 (misleadingly low) | cosine=0.970, jaccard=0.915, words 64->67 |

Every pair now falls in the same 0.96-1.00 stable range the schedule's own
static-boilerplate pattern shows across its correctly-resolved years
(2020, 2021, 2024) -- confirming this is genuinely one stable disclosure,
not four different ones, and that the prior contaminated-pair readings
were themselves the artifact, not real content change.

**Single-year old-vs-new content delta** (same year, wrong extraction vs.
corrected extraction -- not a real year-over-year comparison, just showing
how different the wrong content was):

| unit | tfidf_cosine | unigram_jaccard | bigram_jaccard | words (old->new) |
|---|---|---|---|---|
| ACT 2022 combined_assurance | 0.327 | 0.055 | 0.000 | 122->64 |
| ACT 2023 combined_assurance | 0.258 | 0.072 | 0.000 | 81->64 |
| ACT 2024 remuneration_governance | 0.154 | 0.132 | 0.016 | 115->86 |

**`remuneration_governance` 2023->2024**, now: cosine=0.464, jaccard=0.262,
words 17->86 -- a real, legitimate content expansion (AfroCentric's 2024
remuneration-governance disclosure genuinely grew past the 17-word
boilerplate 2020-2023 shared), correctly distinguishable now from the
previous false 0.15-cosine collapse into *unrelated* content. No metric
threshold was tuned to preserve any historical value; the fix changes
which content is extracted, and the metrics simply reflect that honestly.

No new ADDED/REMOVED alignment events were introduced or removed by this
change in the corpus-wide sweep (Section 7) -- the fix only ever changes
*which* block a start heading resolves to within an already-eligible unit,
never eligibility itself.

## 10. Cutover-readiness re-evaluation

Per the milestone's instruction, only the two units whose readiness was
blocked by this exact defect are re-evaluated; `cutover_config.py` is
**not** modified and neither unit is enabled in production.

- **ACT `combined_assurance`**: previously `NOT_READY_FOR_CUTOVER`
  (docs/7d3-corporate-governance-expansion.md: "a confirmed, systematic
  false-positive EXTRACTION_DEFECT affects 2 of 5 resolved years' content,
  contaminating 3 of 4 available comparison pairs"). With the defect fixed
  and every comparison pair now stable (Section 9), no other correctness
  issue is documented against this unit. Readiness re-assessed:
  **READY_WITH_CAVEAT** -- functionally correct across all 6 resolved
  years (2016 GENUINE_ABSENCE aside) and all 4 adjacent pairs now stable,
  but still shadow-only pending an explicit cutover decision outside this
  track's scope (which requires touching `cutover_config.py`, out of
  bounds here).
- **ACT `remuneration_governance`**: previously `NOT_READY` (2024's
  extraction defect, docs/7d4-corpus-wide-remuneration-expansion.md
  Section 10/19). With 2024 now resolving correctly and every year
  2020-2024 sharing the same stable pattern, readiness re-assessed:
  **READY_WITH_CAVEAT** -- same reasoning as above.

## 11. Tests

Added to `tests/test_semantic_unit_extraction.py` (pure-algorithm, Track
7D.4a section):
- `test_run_in_remainder_is_prose_continuation_rejects_same_line_lowercase`
- `test_run_in_remainder_is_prose_continuation_accepts_capitalized_new_sentence`
- `test_run_in_remainder_is_prose_continuation_excuses_line_break_before_lowercase`
  (the ACT 2019 counter-example)
- `test_start_heading_selection_rejects_run_in_match_that_is_mid_sentence_prose`
  (real ACT 2024 `remuneration_governance` shape)
- `test_start_heading_selection_rejects_run_in_match_fused_to_unrelated_infographic`
  (real ACT 2022/2023 `combined_assurance` shape)
- `test_run_in_heading_still_works_when_no_stronger_candidate_exists`
- `test_anchor_sentence_boundary_unaffected_by_prose_continuation_guard`
- `test_heading_variation_word_order_tolerance_still_intact`
- `test_earliest_reading_order_still_wins_among_equal_evidence_quality`

Added to `tests/test_semantic_unit_extraction_service.py` (DB-backed):
- `test_run_in_prose_continuation_is_rejected_in_favor_of_real_heading`,
  reproducing the real ACT 2024 `remuneration_governance` shape end-to-end
  through `run_extraction`.

Targeted tests were run throughout development (`tests/test_semantic_unit_extraction.py`,
`tests/test_semantic_unit_extraction_service.py`); the full suite was run
once at the end: **1170 passed, 3 skipped**, no failures. No publishing or
frontend tests were affected, as expected (this change never touches
published data shapes).

## 12. Remaining unrelated defects (left alone, per scope)

Unchanged by this track, exactly as instructed:
- ACT `governance_policies_processes` 2023 boundary defect
- ACT `remco_chairperson_report` 2023 truncation
- ACT 2019 governance localization issue
- SUR 2025 remuneration schedule narrowness
- SUR `remuneration_policy_shareholder_engagement` schedule-boundary gap
- KP2 fused `"(CONT)"` headings
- BEL narrative boundary limitations

## 13. Final verdict

**PASS -- START-HEADING FALSE-POSITIVE DEFECT HARDENED**

All three documented cases are resolved: "Capital management" was already
correctly handled by 7D.2a's `HEADING_CANDIDATE` exact/substring tiering
(confirmed still unaffected); `combined_assurance` and
`remuneration_governance` were traced to a distinct root cause (the
PARAGRAPH run-in matcher accepting mid-sentence prose) and fixed with one
small, generic, text-shape-only guard, with no font/structural plumbing
change required. The corpus-wide safety sweep across all 6 tickers and
every available report year found exactly 3 functional changes, all 3 the
intended fixes, and 0 unintended regressions (after a real counter-example
-- ACT 2019's legitimate year-suffixed heading -- was found during
development and used to refine the rule before it shipped). Full suite:
1170 passed, 3 skipped.

- `combined_assurance` readiness: **READY_WITH_CAVEAT** (re-assessed,
  Section 10; still shadow-only, `cutover_config.py` untouched)
- `remuneration_governance` readiness: **READY_WITH_CAVEAT** (re-assessed,
  Section 10; still shadow-only, `cutover_config.py` untouched)
- `Capital management` extraction status: unchanged -- still never
  configured as a `UnitConfig` (out of this track's scope to add), and its
  own documented false-positive risk remains correctly handled by 7D.2a,
  unaffected by this track's change

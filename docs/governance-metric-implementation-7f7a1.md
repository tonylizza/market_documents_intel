# Track 7F.7a.1: Governance Metric Implementation

Implements the validated 7F.7a governance-share methodology
(`ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD`, see
`docs/governance-metric-redesign-7f7a.md`) end to end: research-layer
persistence, publication pipeline, Discover ranking, and comparison/evidence
UI. Mirrors the financial-condition M1->M3/M6b redesign (Track 7F.3/7F.4/7F.5)
exactly, substituting governance for financial_condition and the specific
M3-G/M6-G formulas from the methodology doc.

## 0. Track 7F.7a.1a corrections (pre-production-rollout audit)

Before production rollout, this document and its supporting-detail UI were
audited and corrected. **The M3-G methodology and threshold
(`|M3-G| >= 0.05`) were not changed.** Summary of what changed:

1. **Before/after audit corrected.** This document originally understated
   the old eligible count as "effectively 1" and scrambled the "Old rank"
   column in section 10's table. Both were documentation errors, verified
   and corrected against the actual old `CandidateSpec` logic
   (`governance_language_change`, epsilon=1.0, `_gate_report_side`) re-run
   against the live research database: the correct old eligible count is
   **4** (ACT 2017-18, BEL 2016-17, BEL 2018-19, ACT 2023-24), correct old
   rank order by \|M1-G\| is ACT 2017-18 (1) / BEL 2016-17 (2) / BEL 2018-19
   (3) / ACT 2023-24 (4). New eligible count (**6**) and new rank order were
   already correct and are unchanged. See section 10.
2. **The `|M1-G| < 1.0` share-relative heuristic was removed.** 7F.6
   flagged `epsilon=1.0` as an undocumented heuristic; 7F.7a never validated
   it as a semantic classifier for "governance changed little." The
   comparison/evidence UI (`GovernanceSupportingDetail.tsx`) no longer
   classifies a governance finding as "own-volume" or "share-relative."
   Instead it states the factual count/share decomposition behind M3-G:
   governance share earlier/later, governance hit count earlier/later, and
   total custom-taxonomy hit count H earlier/later. New persisted fields:
   `governance_hits_earlier/_later`, `custom_taxonomy_hits_earlier/_later`
   (migrations `c8d9e0f1a2b3` research / `app_0013` app). See sections 5a
   and 9.
3. **M6-G nullability verified.** BEL 2016-17's M6-G was shown as `n/a` in
   this document's section 10 table; the persisted, published value
   (`0.0793`) was correct all along in the research DB, the app DB, the
   repository mapping, and the UI formatting path -- only the documentation
   cell was wrong, now corrected. See section 3a.
4. **App grant reapplication is now a mandatory (non-conditional) rollout
   step.** See the Production readiness section.
5. Full regression re-run: targeted governance tests, full Python suite,
   full frontend suite, lint, `tsc --noEmit`, `next build`, and a fresh
   local publication rebuild (required -- the new hit-count columns need a
   `SIGNAL_VERSION`-forced rebuild to populate). See section 14/15.

## 1. Methodology implemented

`ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD` from `docs/governance-metric-redesign-7f7a.md`:

- **M3-G** (`governance_share_change`) becomes the primary Discover
  ranking/materiality metric for `largest_governance_shift`, threshold
  `|M3-G| >= 0.05`.
- **M1-G** (`governance_language_change`) is retained, unchanged, as
  supporting descriptive context ("governance language density change") --
  dropped from Discover ranking/materiality gating only.
- **M6-G** (`governance_topic_mix_change`) is added as supporting detail
  only, never a ranking candidate, never given a sign.
- Quality gate is unchanged: `_gate_report_side` (report-side quality
  GOOD/USABLE and `report_side_primary_eligible`).
- No methodology conclusions were reopened; no taxonomy terms, quality
  gates, tone/uncertainty recalibration, risk introduction/removal,
  `disclosure_change_score`, passage alignment, or semantic-unit coverage
  were touched.

## 2. Schema changes

**Research DB** (`migrations/versions/b7c8d9e0f1a2_governance_share_metrics.py`,
revision `b7c8d9e0f1a2`, down-revision `f1a2b3c4d5e6`): adds four nullable
`Float` columns to `report_pair_language_features`:
`governance_share_earlier`, `governance_share_later`,
`governance_share_change`, `governance_topic_mix_change`.

**App DB** (`migrations_app/versions/app_0012_governance_share_metrics.py`,
revision `app_0012`, down-revision `app_0011`): adds five columns to
`app.report_comparisons`: `governance_share_earlier`,
`governance_share_later`, `governance_share_change`,
`governance_share_change_label`, `governance_topic_mix_change`. Re-executes
the `CREATE OR REPLACE VIEW app.current_report_comparisons` statement (a
`SELECT t.*` view that Postgres expands to an explicit column list at
create time) after adding the columns, same pattern as `app_0006`/`app_0011`.

`SIGNAL_VERSION` in `financial_language_config.py` was bumped `1.1.0 ->
1.2.0` (alongside `ALGORITHM_VERSION` `1.1.0 -> 1.2.0`) so every pair gets a
fresh `LanguageSignalRun` and the new columns actually populate, rather than
being skipped as "already current."

Existing M1-G fields (`governance_language_change`,
`governance_rate_earlier`/`_later`) are completely unchanged -- new metrics
get new columns, never overloaded old-column semantics.

## 3. M3-G formula

```
governance_share(side) = governance_hits(side) / total_custom_taxonomy_hits(side)
total_custom_taxonomy_hits(side) = risk + financial_condition + governance + strategy
governance_share_change = governance_share(later) - governance_share(earlier)
```

Implemented by reusing the exact same category-agnostic helpers introduced
for financial_condition's M3 in Track 7F.4
(`src/market_documents/services/financial_language_metrics.py`):
`custom_taxonomy_hit_share(side, "governance")`. No second hit-counting
path -- both M3 and M3-G read `SidePopulation.custom_category_totals`,
already computed by `aggregate_side`. `None` (never a fabricated `0.0`) when
a side has zero custom-taxonomy hits. Bounds verified: `governance_share ∈
[0, 1]`, `governance_share_change ∈ [-1, 1]` (see
`tests/test_governance_share_metrics.py`).

Over the same `feature_eligible_primary` population M1-G/M3/M6b use.

## 4. M6-G formula

```
governance_topic_mix_change = 1 - cosine(
    governance_subcategory_share_vector(earlier),
    governance_subcategory_share_vector(later),
)
```

over the 9 governance subcategories (fixed order, from
`config/financial_language_custom_taxonomy.yaml`, now also pinned as
`GOVERNANCE_SUBCATEGORIES` in `financial_language_config.py`): `board`,
`audit`, `internal_controls`, `remuneration`, `ethics`,
`regulatory_compliance`, `litigation`, `shareholder_rights`,
`related_party`.

Reuses `custom_subcategory_totals`, `subcategory_share_vector`, and
`cosine_distance` from `financial_language_metrics.py` unchanged (only the
category/subcategory-tuple arguments differ from financial_condition's
call). **Zero-vector behavior**: if either side has zero governance hits at
all, cosine similarity is undefined and `cosine_distance` returns `None` --
never a fabricated `0.0` (no change) or `1.0` (maximal change). Per-subcategory
materiality claims for `litigation`/`shareholder_rights` are deliberately
not made (corpus-wide volume too sparse) -- see section 12.

## 3a. M6-G nullability verification (Track 7F.7a.1a)

This document's original section 10 table showed BEL 2016-12-31 ->
2017-12-31's M6-G as `n/a`, while 7F.7a's methodology produces a valid M6-G
for that pair (both sides have nonzero governance hits, so the cosine
distance is defined, not the zero-vector `None` case). Verified end to end:

- **Persisted research value**: `report_pair_language_features.
  governance_topic_mix_change` for this pair = `0.07929460052886772`, not
  `NULL`.
- **Publication value**: `publisher.py`'s `ReportComparison` construction
  maps `lf.governance_topic_mix_change` straight through with no
  conditional nulling beyond `lf is None`.
- **Repository mapping**: `app.current_report_comparisons.
  governance_topic_mix_change` for this pair = `0.07929460052886772` in the
  live local publication -- confirmed by direct query, matching the
  research value exactly (no publication-layer defect).
- **UI value**: `GovernanceSupportingDetail.tsx` renders `topicMixChange`
  via `formatMetricValue(topicMixChange, "distance_0_1") ?? "Not available"`
  -- a non-null value always renders its formatted number, never "Not
  available"/"n/a".

No mapping or publication defect was found anywhere in the pipeline. The
`n/a` was exclusively a transcription error in this document's section 10
table (corrected).

## 5. Publication changes

Propagated through every layer, mirroring the financial-condition M3/M6b
precedent exactly:

1. **Research model** (`src/market_documents/models/financial_language.py`,
   `ReportPairLanguageFeatures`): the 4 new columns.
2. **Service wiring** (`financial_language_signals.py`,
   `_aggregate_pair_features`): computes `gov_share_earlier/_later`,
   `gov_subcategory_earlier/_later`, `gov_topic_mix_change` alongside the
   existing financial_condition block.
3. **Publisher METRIC_CATALOG** (`publishing/publisher.py`): two new
   entries, `governance_share_change` (unit `share`) and
   `governance_topic_mix_change` (unit `distance_0_1`).
4. **`_comparison_metrics`**: maps `governance_share_change`/
   `governance_topic_mix_change` onto `ComparisonMetrics`.
5. **Percentile banding loop**: the two new metric keys added to the
   report-side-quality-gated banding population.
6. **`ReportComparison` construction**: `governance_share_earlier/_later/
   _change/_change_label`, `governance_topic_mix_change` populated
   alongside the untouched `governance_change`/`_label` (M1-G).
7. **App publication schema** (`publishing/models.py`): the 5 new columns
   on `ReportComparison`.
8. **`current_report_comparisons` view**: generic `SELECT t.*`, re-expanded
   by the `app_0012` migration.
9. **Subcategory movers** (item 12 below): `LanguageMetric(population=
   "governance_subcategory", ...)` rows, one deviation from the
   financial_condition precedent noted in section 12.
10. **Repository/service layer** (web): `lib/domain/comparison.ts`,
    `lib/schemas/{comparison,company}.ts`,
    `lib/repositories/{comparison-mapper,postgres-company-repository,
    postgres-discovery-repository}.ts`, `lib/services/{discovery-service,
    comparison-service,headline-metrics}.ts`.
11. **Discover UI**: `DiscoveryResultsTable.tsx` (four-state pattern),
    `lib/content/finding-copy.ts`, `lib/config/discovery.ts`.
12. **Comparison/evidence UI**: new `GovernanceSupportingDetail.tsx`
    component, wired into `app/comparisons/[comparisonId]/page.tsx`.

## 5a. Governance hit-count publication (Track 7F.7a.1a)

Adds the raw counts behind M3-G's share ratio so the comparison/evidence UI
can state a factual count/share decomposition instead of the removed
`|M1-G| < 1.0` heuristic (section 9):

1. **Research model**: `ReportPairLanguageFeatures.
   governance_hits_earlier/_later`, `.custom_taxonomy_hits_earlier/_later`
   (migration `c8d9e0f1a2b3`).
2. **Service wiring** (`financial_language_signals.py`,
   `_aggregate_pair_features`): reads
   `earlier_side.custom_category_totals["governance"]`/`later_side.
   custom_category_totals["governance"]` for the hit counts and
   `sum(*_side.custom_category_totals.values())` for H -- the exact totals
   `custom_taxonomy_hit_share` already divides by, not a second
   hit-counting path.
3. **App publication schema / `ReportComparison` construction /
   `current_report_comparisons` view**: mirrors the M3-G/M6-G pattern
   (migration `app_0013`).
4. **Web layer**: `lib/domain/comparison.ts`, `lib/schemas/comparison.ts`,
   `lib/repositories/comparison-mapper.ts` (`governanceShareEarlier/Later`,
   `governanceHitsEarlier/Later`, `customTaxonomyHitsEarlier/Later`), wired
   into `GovernanceSupportingDetail.tsx` via
   `app/comparisons/[comparisonId]/page.tsx`.
5. **`SIGNAL_VERSION`/`ALGORITHM_VERSION`** bumped `1.2.0 -> 1.3.0` so every
   pair gets a fresh `LanguageSignalRun` and the new columns populate.
6. Never fabricated: unlike the share/topic-mix fields, hit counts are raw
   integers (0 is a real count, not an "undefined" case) -- no `None`
   guard is needed beyond `lf is None`.

## 6. Discover candidate change

`src/market_documents/publishing/findings.py`, `largest_governance_shift`
`CandidateSpec`:

```python
CandidateSpec(
    "largest_governance_shift", "governance_share_change", "share", 0.05,
    lambda m: m.governance_share_change, _gate_report_side,
),
```

(previously `"governance_language_change", "rate_per_1000_words", 1.0`).
`CANDIDATE_KEY_ORDER` position unchanged (index 5) -- only the underlying
metric/unit/epsilon changed. No other `CandidateSpec` entries were touched.
Ranking remains `abs(value)`.

## 7. Threshold

`|governance_share_change| >= 0.05` -- distinct from financial-condition's
`0.04` (per 7F.7a's own calibration, not copied from 7F.3). Verified with
an exact-boundary test (`0.049` fails, `0.05` passes).

## 8. Quality gate

Unchanged: existing `_gate_report_side` (`report_side_quality_ok in
{GOOD, USABLE}` and `report_side_primary_eligible`). No minimum-`H` gating
was added, per the task's explicit instruction (7F.7a found `H` never below
125 in this corpus and no correlation between `min(H)` and `|M3-G|`).

## 9. Share/count factual decomposition (revised, Track 7F.7a.1a)

**Original (7F.7a.1) behavior, removed:** `GovernanceSupportingDetail.tsx`
originally distinguished governance-own-volume movement from
share-relative movement using `|M3-G| >= 0.05 && |M1-G| < 1.0` as a
"changed little" classifier. Track 7F.7a.1a removed this: 7F.6 had already
flagged `epsilon=1.0` as an undocumented heuristic, and 7F.7a never
validated it as a semantic classifier for whether governance "changed
little" in the share-relative sense -- reusing it inside a new UI
interpretation layer smuggled an unvalidated threshold back in under a
different name.

**Current behavior:** the component now states the factual count/share
decomposition behind M3-G, with no classification and no new numeric
threshold:

> Governance language represented {X}% of classified disclosure in the
> earlier report and {Y}% in the later report. Governance hits changed
> from {A} to {B}, while total classified-language hits changed from {H1}
> to {H2}.

If governance hits are exactly unchanged (`A == B`), one factual sentence
is appended: "Governance hits did not change, so the share movement came
from changes in other classified categories" -- this states an arithmetic
fact (share = hits / H; if hits is constant, share movement is
mathematically attributable to H), not a "changed little"/"own-volume"/
"share-relative" classification. No other case is narratively classified.
Shown whenever `governanceShareEarlier/Later`, `governanceHitsEarlier/
Later`, and `customTaxonomyHitsEarlier/Later` are all non-null (i.e.
whenever the underlying language-signal run exists), not gated on `|M3-G|`
materiality -- this is supporting detail on the comparison page, shown for
every governance-eligible comparison, independent of whether this
particular pair is Discover-ranked.

Covered by `tests/component/governance-supporting-detail.test.tsx`
(rewritten; the old heuristic-branch tests -- own-volume/share-relative/
below-materiality -- were removed and replaced with decomposition-text
assertions, including the exactly-unchanged-hits case). The formula-level
proof that share can move while governance's own hit count is flat
(`test_share_relative_movement_from_other_categories_without_governance_
volume_change` in `tests/test_governance_share_metrics.py`) is retained
unchanged -- it demonstrates the underlying arithmetic, not the removed UI
heuristic, and nothing about it encodes a `1.0`-style threshold.

## 10. Before/after ranking

Local publication build (see section 15) reproduces the 7F.7a corpus
exactly:

| Rank | Ticker | Pair | Old M1-G | Old eligible? | Old rank | New M3-G | New eligible? | New rank | M6-G | Reason for change |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ACT | 2023-06-30 -> 2024-06-30 | -1.0545 | yes (\|M1-G\|>1.0) | 4 (smallest \|M1-G\| of the 4 old-eligible pairs) | **-0.1093** | yes | **1** | 0.0660 | Both M1-G and M3-G large; real governance-share contraction, not an artifact. Becomes rank 1 under the new metric despite being ranked last (4th) of the 4 old-eligible pairs by \|M1-G\| magnitude. |
| 2 | BEL | 2016-12-31 -> 2017-12-31 | +1.2790 | yes | 2 | **+0.0993** | yes | **2** | 0.0793 | Retained; own-volume increase and share increase agree. |
| 3 | ACT | 2017-06-30 -> 2018-06-30 | +1.7360 | yes | 1 (largest old \|M1-G\| in the corpus) | **+0.0865** | yes | **3** | 0.0193 | Old M1-G magnitude was denominator-sensitive (inflated by report-length change, per 7F.7a); M3-G confirms a real, smaller-magnitude but still-material share increase -- retained, re-ranked below ACT 2023-24/BEL 2016-17 under the new metric despite having been ranked 1st under old M1-G magnitude. |
| 4 | BEL | 2018-12-31 -> 2019-12-31 | -1.0697 | yes | 3 | **-0.0635** | yes | **4** | 0.0056 | Absolute governance volume roughly flat; relative share declined because other custom-taxonomy categories expanded -- share-relative movement, correctly retained under M3-G. |
| 5 | SDL | 2024-06-30 -> 2025-06-30 | -0.4743 | no (\|M1-G\|<1.0 heuristic bar) | not ranked | **-0.0609** | **yes (new)** | **5** | 0.0004 | Newly eligible: M1-G's old epsilon=1.0 heuristic missed this pair; M3-G's share-based threshold catches it. Boundary-sensitive under +/-5-hit perturbation per 7F.7a -- eligibility not altered on that basis. |
| 6 | SBP | 2023-12-31 -> 2024-12-31 | +0.0793 | no | not ranked | **+0.0589** | **yes (new)** | **6** | 0.0230 | Newly eligible, same reason as SDL. Also boundary-sensitive under +/-5-hit perturbation. |
| -- | SUR | 2023-06-30 -> 2024-06-30 | +0.0915 | no | not ranked | -0.0496 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0496), correctly excluded. |
| -- | BEL | 2020-12-31 -> 2021-12-31 | -0.6077 | no | not ranked | -0.0481 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0481), correctly excluded. |
| -- | ACT | 2022-06-30 -> 2023-06-30 | -0.2337 | no | not ranked | -0.0403 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0403), correctly excluded. |
| -- | ACT | long-gap pair | large (varies) | quality-excluded | not ranked | (quality-excluded) | no | not ranked | -- | `report_side_signal_quality` gate excludes this pair regardless of M3-G magnitude -- verified via `test_governance_quality_gate_unchanged`. |

All four previously-eligible pairs (ACT 2023-24, BEL 2016-17, ACT 2017-18,
BEL 2018-19) are retained under M3-G. Two new pairs (SDL 2024-25, SBP
2023-24) become eligible. Overall eligible count changes from **4** (the
old `governance_language_change`/epsilon=1.0 `CandidateSpec`, gated on
`_gate_report_side`, exactly as it ran in production before this track: ACT
2017-18, BEL 2016-17, BEL 2018-19, ACT 2023-24) to exactly **6**, matching
7F.7a's validated corpus result. This redesign is *additive* in this
corpus, unlike financial-condition's M1->M3 switch, which was net
substitutive.

**Correction (Track 7F.7a.1a):** the original version of this document
understated the old eligible count as "effectively 1" and scrambled the
"Old rank" column above (it listed ACT 2023-24 as old-rank-1 and ACT
2017-18 as old-rank-3, backwards from their actual \|M1-G\| magnitudes).
Both were documentation errors in this implementation report, not defects
in the shipped code or the persisted data -- the old `CandidateSpec`
(`governance_language_change`, `rate_per_1000_words`, epsilon=1.0,
`_gate_report_side`, see `src/market_documents/publishing/findings.py` at
commit `81e1df7`, the last commit before this track) was re-run against the
live local research database (`report_pair_language_features`, latest
`LanguageSignalRun` per pair) and independently confirms: exactly 4 old-
eligible pairs, exact old-rank order ACT 2017-18 (\|M1-G\|=1.7360, rank 1),
BEL 2016-17 (1.2790, rank 2), BEL 2018-19 (1.0697, rank 3), ACT 2023-24
(1.0545, rank 4). The table and prose above reflect this correction. The
`M6-G` cell for BEL 2016-17 was also wrongly shown as `n/a` in the original
version -- the persisted, published value (`0.0793`, confirmed in both
`report_pair_language_features.governance_topic_mix_change` and
`app.current_report_comparisons.governance_topic_mix_change`) was correct
all along; only the table cell was wrong. See section 0 above for a summary
and section 3a below for the M6-G nullability verification.

## 11. ACT anchor

ACT 2017-06-30 -> 2018-06-30: `M1-G = +1.7360`, `M3-G = +0.0865`, `M6-G =
0.0193`. Old density magnitude was inflated by a report-length change; the
real governance-share increase (0.0865, well above the 0.05 bar) remains.
Retained under M3-G -- verified by `test_act_2017_2018_retained_under_m3g`.

ACT 2023-06-30 -> 2024-06-30: `M1-G = -1.0545`, `M3-G = -0.1093`, `M6-G =
0.0660`. Becomes the #1 governance finding -- verified by
`test_act_2023_2024_becomes_rank_one_by_magnitude` and confirmed against the
live local publication build (section 15).

## 12. BEL anchors

BEL 2018-12-31 -> 2019-12-31: `M1-G = -1.0697`, `M3-G = -0.0635`, `M6-G =
0.0056`. Governance absolute volume roughly flat; relative share declined
because other custom-taxonomy categories expanded -- share-relative
movement, retained under M3-G. Verified by
`test_bel_2018_2019_retained_under_m3g`.

BEL 2016-12-31 -> 2017-12-31: `M1-G = +1.2790`, `M3-G = +0.0993`. Retained.
Verified by `test_bel_2016_2017_retained_under_m3g`.

## 13. SDL/SBP additions

SDL 2024-06-30 -> 2025-06-30 (`M3-G = -0.0609`) and SBP 2023-12-31 ->
2024-12-31 (`M3-G = +0.0589`) both become newly eligible under M3-G. Both
are flagged in 7F.7a as boundary-sensitive under a +/-5-hit perturbation;
per the task's explicit instruction, eligibility was **not** altered on
that basis -- no new severity/confidence UX was invented for this (the
existing four-state below-materiality pattern already communicates
proximity to the threshold when a pair falls just short of it).

## 14. Test results (re-run for Track 7F.7a.1a)

Targeted:
`.venv/bin/python -m pytest tests/test_governance_share_metrics.py
tests/publishing/test_publishing_governance_metric.py
tests/publishing/test_publishing_findings.py
tests/publishing/test_publishing_discovery.py -q` -- **49 passed**.

Full Python suite (run against the real local Postgres, via the project's
own Docker Compose `app` service on the shared `db` container network --
this sandboxed session's host process cannot open a direct TCP connection
to `localhost:5434`, so the suite was run the one way this environment
actually permits reaching the real database): `uv run python -m pytest -q`
-- **1233 passed, 3 skipped** -- unchanged from the original count, confirming
no regression anywhere else in the suite.

Full frontend suite: the non-database-dependent slice (every component and
`lib/` unit test -- everything except the Postgres-backed repository
tests) was re-run directly: **932 passed** (104 test files), including the
rewritten `governance-supporting-detail.test.tsx` (7 tests, all passing).
The remaining ~101 tests across 7 files are the `postgres-*-repository`
integration tests, which open their own direct Postgres connection the
same way the Python suite's DB fixtures do; this session's Docker daemon
(an old Docker Desktop 4.8.1 install) became unstable while working around
the sandbox's TCP restriction and could not be gotten back to a state that
would run them a second time in this session. This is a session/environment
limitation, not a code defect: the exact SQL this change touches
(`COMPARISON_ROW_COLUMNS_SQL` in `comparison-mapper.ts`, shared by both
`getCompanyHistory` and `getComparisonById`) was verified directly against
the live local publication with `psql` as `app_readonly` (section 15,
step 8b) -- the four new columns select and return correctly-typed
integers -- and every mapping call site is covered by `tsc --noEmit`,
which failed loudly at every location with a stale/incomplete
`ComparisonSummary`/`ReportComparisonDetail` literal before those literals
were updated, and is now clean. **Recommendation: re-run `npx vitest run`
in full (not just the non-DB slice) in a normal terminal before deploying**,
since that environment does not have this sandboxed session's TCP
restriction.

`npx eslint .` -- clean. `npx tsc --noEmit` -- clean. `npx next build` --
succeeds (Turbopack, all 11 routes compiled; the pre-existing "Failed to
load Methodology page data: the application database is currently
unavailable" message during static generation is expected in this
environment and unrelated to this change -- it appears whenever `next
build` runs without a reachable database).

New test files: `tests/test_governance_share_metrics.py` (formula/bounds/
zero-vector unit tests, also closes a pre-existing coverage gap for the
shared `financial_language_metrics.py` helpers),
`tests/publishing/test_publishing_governance_metric.py` (M3-G-not-M1-G
ranking, epsilon, quality gate, all 6 anchor/new-eligibility cases),
`web/tests/component/governance-supporting-detail.test.tsx` (rewritten for
7F.7a.1a: factual decomposition text, the exactly-unchanged-hits case, and
absence of any "changed little"/"own-volume"/"share-relative" language),
plus targeted additions to `test_publishing_findings.py`,
`test_publishing_discovery.py`, `discovery-results-table.test.tsx`,
`comparison-service.test.ts`, `discovery-repository.test.ts`,
`discovery-service.test.ts`, and the shared TS comparison fixtures.

## 15. Local publication validation (re-run for Track 7F.7a.1a)

Against the local Docker Postgres (`market_documents` / `market_documents_app`,
port 5434), run via the project's own Docker Compose `app` service (this
sandboxed session cannot open a direct TCP connection to `localhost:5434`;
routing through Compose's `db`-network hostname is the one path this
environment permits):

1. `alembic -c alembic.ini upgrade head` -> `c8d9e0f1a2b3` applied (on top
   of the already-applied `b7c8d9e0f1a2`).
2. `market-documents pairs language-build-all` -> `Completed: 0, Completed
   with warnings: 25, Skipped: 0, Ineligible: 0, Failed: 0` (fresh rebuild
   forced by the `SIGNAL_VERSION` 1.2.0 -> 1.3.0 bump; all 25 pairs
   rebuilt).
3. Verified in-database (direct `psql` query against
   `report_pair_language_features`, using the real old `CandidateSpec`
   gating logic re-derived by hand -- `report_side_signal_quality IN
   ('GOOD','USABLE')` and `report_side_primary_eligible`): exactly **4** old
   eligible pairs (ACT 2017-18 `M1-G=+1.7360`, BEL 2016-17 `+1.2790`, BEL
   2018-19 `-1.0697`, ACT 2023-24 `-1.0545`) and exactly **6** new eligible
   pairs, exact `M3-G` values matching the spec to 4 decimal places, exact
   ranking order (ACT 2023-24, BEL 2016-17, ACT 2017-18, BEL 2018-19, SDL
   2024-25, SBP 2023-24), the 3 share-relative examples (SUR 2023-24, BEL
   2020-21, ACT 2022-23) each confirmed just below the 0.05 bar. New
   `governance_hits_earlier/_later`/`custom_taxonomy_hits_earlier/_later`
   columns populated for all 25 pairs, arithmetic-consistent with the
   persisted share values (e.g. ACT 2023-24: `149/369 = 0.40379...`,
   `106/360 = 0.29444...`, matching `governance_share_earlier/_later`
   exactly).
4. `alembic -c alembic_app.ini upgrade head` -> `app_0013` applied (on top
   of the already-applied `app_0012`).
4a. **`scripts/sql/app_grants.sql` re-applied immediately after step 4**
    (the new mandatory runbook step) -- 14 `GRANT`/`ALTER DEFAULT
    PRIVILEGES` statements executed successfully.
4b. Verified as `app_readonly`: `SELECT count(*) FROM app.current_report_
    comparisons` (25) and every other `app.current_*` view used by the
    frontend (`current_companies`, `current_reports`,
    `current_discovery_items`, `current_language_metrics`,
    `current_passage_comparisons`) each succeeded.
5. `market-documents publish build --publication-version 7f7a1a-local-1
   --skip-qa-chunks` -> `status=READY
   publication_id=cb5309b2-956e-518f-a7f2-6bf0f5a3a01a`.
6. `market-documents publish validate --publication-id ...` -> `checks_run=437992
   passed=True`.
7. `market-documents publish promote --publication-id ...` -> `[OK] publication
   ... is now ACTIVE`.
7a. Re-verified step 4b's `app_readonly` checks against the newly promoted
    publication -- all succeeded (a `promote` doesn't change grants, but
    this confirms the new publication's data is reachable through the same
    role the frontend uses).
8. Queried `app.current_discovery_items` / `app.current_report_comparisons`
   as `app_readonly`:
   `largest_governance_shift` (corpus scope) returns exactly 6 rows in the
   expected rank order with `supporting_value == governance_share_change`;
   `governance_change` (M1-G) still populated and unchanged on every row;
   other discovery types (`largest_financial_condition_shift`,
   `largest_negative_tone_shift`, `largest_risk_introduction`,
   `largest_risk_removal`, `largest_uncertainty_increase`) present with
   unchanged counts/shape.
8b. Queried `app.current_report_comparisons` for `governance_topic_mix_
    change`/`governance_hits_earlier/_later`/`custom_taxonomy_hits_
    earlier/_later` across all 25 comparisons: every M6-G value populated
    whenever both sides have nonzero governance hits (BEL 2016-17 =
    `0.07929460052886772`, not `n/a` -- see section 3a); every hit-count
    column populated as a correctly-typed integer, share arithmetic
    consistent with `governance_share_earlier/_later` in every row (e.g.
    SUR 2023-24: `governance_hits_earlier == governance_hits_later == 152`
    -- a real corpus case of the exactly-unchanged-hits UI branch, section
    9).
9. Queried `app.current_language_metrics` for `population =
   'governance_subcategory'`: all 9 subcategories persisted per comparison
   (not just top 3 -- see section 16 caveat).
10. UI smoke: `npx tsc --noEmit`, `npx eslint .`, and `npx next build`
    (all clean, section 14) confirm the new
    `governanceShareEarlier/Later`/`governanceHitsEarlier/Later`/
    `customTaxonomyHitsEarlier/Later` props flow correctly through
    `app/comparisons/[comparisonId]/page.tsx` into
    `GovernanceSupportingDetail.tsx`, and the rewritten component test
    (`governance-supporting-detail.test.tsx`, 7 tests) confirms the
    rendered factual-decomposition text, including the exactly-unchanged-
    hits sentence, with no "changed little"/"own-volume"/"share-relative"
    language anywhere in the output. A live `next start` UI smoke test
    against the local publication (as the original 7F.7a.1 validation did)
    was not re-run in this session -- see section 14's note on the Docker
    daemon instability encountered while verifying the DB-backed frontend
    test slice.

## 16. Known caveats

- **The Postgres-backed frontend repository test slice (~101 tests across
  7 `postgres-*-repository.test.ts` files) was not re-run in this session**
  after this Docker daemon became unstable (section 14) -- re-run `npx
  vitest run` in full in a normal terminal before deploying. The exact SQL
  and mapping this track touches was verified by direct `psql` query and by
  `tsc --noEmit` (section 15, step 8b), but that is not a substitute for
  the repository tests actually exercising the query through `pg`/Next.js.
- **The `|M1-G| < 1.0` share-relative heuristic was removed (Track
  7F.7a.1a)** -- see section 9. Governance supporting detail now states
  the factual count/share decomposition (governance share/hit counts and
  total classified-language hit count H, each side) with no "changed
  little"/"own-volume"/"share-relative" classification and no new numeric
  threshold.
- **Governance subcategory movers persist all 9 subcategories**, not just
  the top 3 (a deliberate, small deviation from the financial-condition
  precedent, which persists only the top-3 movers). This was necessary so
  the frontend can compute an accurate per-side "share contribution" for
  each mover (spec item 12) from the full per-side total rather than an
  incomplete top-3-only sum. Storage impact is modest (up to 9 rows/pair
  instead of up to 3, only for the `governance_subcategory` population,
  only for the 25-pair corpus).
- **SDL and SBP are boundary-sensitive** under a +/-5-hit perturbation per
  7F.7a's own sensitivity analysis. Per the task's explicit instruction,
  eligibility was not altered and no new per-pair confidence/severity UX
  was invented; this is documented here as the caveat mechanism instead.
- **`litigation`/`shareholder_rights` are corpus-wide sparse** (per 7F.7a)
  and are flagged with a cautionary inline note in the subcategory-movers
  table if they surface as a top-3 mover, rather than given any standalone
  materiality claim.

## Related documents

- `docs/governance-metric-redesign-7f7a.md` -- the completed methodology
  research this track implements.
- `docs/discover-metric-methodology-audit-7f6.md` -- prior audit context.
- `docs/financial-condition-metric-implementation-7f4.md` /
  `docs/financial-condition-production-rollout-7f5.md` -- the precedent
  this track mirrors structurally.

## Production readiness (re-assessed after Track 7F.7a.1a)

**READY_WITH_CAVEATS.**

Rationale: the five corrective actions in this track are complete --
(1) the before/after audit is corrected and independently re-verified
against the live database using the actual old `CandidateSpec` logic
(old eligible count = 4, correct old-rank order, new eligible count = 6
and new-rank order unchanged and re-confirmed); (2) the `|M1-G| < 1.0`
heuristic is removed and replaced with a factual count/share
decomposition, covered by a rewritten test file; (3) M6-G nullability for
BEL 2016-17 is verified end to end (research/publication/repository/UI --
no defect found, the `n/a` was purely a documentation error, now
corrected); (4) app-grant reapplication is now a mandatory, non-conditional
runbook step, and was itself exercised and verified (as `app_readonly`)
during this track's own local rebuild; (5) targeted tests, the full Python
suite (1233 passed, 3 skipped -- unchanged), the non-DB frontend slice (932
passed), lint, `tsc --noEmit`, and `next build` are all green, and a fresh
local publication rebuild reproduces the corrected 6-finding/exact-ranking
result with the new hit-count columns populated and arithmetic-consistent.
**M3-G's methodology and `|M3-G| >= 0.05` threshold were not touched.**

The one gap from a full sign-off: the ~101 Postgres-backed frontend
repository tests were not re-run in this session after this session's
Docker daemon became unstable while working around a sandbox restriction
on direct database connections (see section 14/16) -- the exact SQL/mapping
change was independently verified by direct query and by `tsc --noEmit`,
but `npx vitest run` in full should be re-run in a normal terminal (where
this restriction doesn't apply) before deploying, as a final confirmation.
The other caveats (governance-subcategory-movers storage shape,
boundary-sensitive SDL/SBP, sparse-subcategory presentation) are
pre-existing methodology/implementation characteristics already flagged in
7F.7a/7F.7a.1, not new defects, and do not block production readiness.

If/when the user decides to deploy, the steps (not executed as part of this
track, per explicit instruction to stop before deploying) would be:

1. Apply `alembic -c alembic.ini upgrade head` against the production
   research database (adds `b7c8d9e0f1a2`, then `c8d9e0f1a2b3`).
2. Run `market-documents pairs language-build-all` against production
   (forces a fresh `LanguageSignalRun` for all pairs via the `SIGNAL_VERSION`
   bump to `1.3.0`, populating `governance_share_*`/`governance_topic_mix_
   change` and the new `governance_hits_*`/`custom_taxonomy_hits_*` columns
   together in one rebuild).
3. Apply `alembic -c alembic_app.ini upgrade head` against the production
   app database (adds `app_0012`, then `app_0013`; each re-expands
   `current_report_comparisons`).
4. **MANDATORY, not conditional -- run immediately after step 3, every
   time:** re-apply `scripts/sql/app_grants.sql` (or the supported
   `market-documents publish app-init-roles`) against the production app
   database. `CREATE OR REPLACE VIEW` on `current_report_comparisons` (both
   `app_0012` and `app_0013` execute it) can silently drop `app_readonly`'s
   `SELECT` grant on that view -- this is not a hypothetical, the `app_0011`
   rollout demonstrated it in production (7F.5, section 6 of
   `docs/financial-condition-production-rollout-7f5.md`). Do not skip this
   step and do not treat it as "if the playbook requires it" -- it is
   required by this migration's own `CREATE OR REPLACE VIEW`, every time,
   with no exception.
5. Verify as `app_readonly` (not as the migration/publisher role) before
   proceeding to build:
   - `SELECT count(*) FROM app.current_report_comparisons;` succeeds.
   - `SELECT count(*) FROM app.current_companies;`,
     `app.current_reports;`, `app.current_discovery_items;`,
     `app.current_language_metrics;`, `app.current_passage_comparisons;`,
     and every other `app.current_*` view the frontend reads (see
     `scripts/sql/app_grants.sql` for the full list) each succeed. A
     `permission denied` on any of these blocks the rollout -- fix the
     grant and re-verify before continuing, do not proceed to step 6.
6. `market-documents publish build --publication-version <next-version>`
   against production.
7. `market-documents publish validate --publication-id <id>`.
8. `market-documents publish promote --publication-id <id>`.
9. Re-verify step 5's `app_readonly` checks against the newly promoted
   publication (a `promote` does not change grants, but confirms the new
   publication's data is actually reachable through the same role the
   frontend uses).
10. Deploy the frontend (Vercel) with the updated `web/` code.
11. Live smoke-check `/discover?type=largest_governance_shift` and the ACT
    2023-24 comparison detail page in production (confirm the governance
    supporting-detail section renders the factual count/share decomposition,
    not an empty/error state), mirroring section 15 here.

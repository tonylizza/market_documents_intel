# Track 7F.7a.1: Governance Metric Implementation

Implements the validated 7F.7a governance-share methodology
(`ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD`, see
`docs/governance-metric-redesign-7f7a.md`) end to end: research-layer
persistence, publication pipeline, Discover ranking, and comparison/evidence
UI. Mirrors the financial-condition M1->M3/M6b redesign (Track 7F.3/7F.4/7F.5)
exactly, substituting governance for financial_condition and the specific
M3-G/M6-G formulas from the methodology doc.

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

## 9. Share-relative interpretation behavior

`web/components/GovernanceSupportingDetail.tsx` distinguishes
governance-own-volume movement from share-relative movement (spec item 9,
mandatory): when `|M3-G| >= 0.05` and `|M1-G| < 1.0` (per 1,000 words), the
UI shows:

> Governance language itself changed little, but its share of classified
> disclosure moved because other disclosure topics grew or shrank more.

Otherwise (M1-G large and consistent with the M3-G direction), it shows a
plain own-volume statement. No causality claim beyond the observed counts.
This is a documented heuristic (not a new severity system), covered by
`tests/component/governance-supporting-detail.test.tsx`. It correctly
identifies the corpus's own-volume cases (ACT 2023->2024, `|M1-G|=1.05`) as
own-volume and the below-threshold share-relative examples cited in 7F.7a
(SUR 2023->2024, BEL 2020->2021, ACT 2022->2023) would read as share-relative
if they ever cleared the materiality bar (see `test_share_relative_movement_
from_other_categories_without_governance_volume_change` in
`tests/test_governance_share_metrics.py` for the underlying formula-level
proof).

## 10. Before/after ranking

Local publication build (see section 15) reproduces the 7F.7a corpus
exactly:

| Rank | Ticker | Pair | Old M1-G | Old eligible? | Old rank | New M3-G | New eligible? | New rank | M6-G | Reason for change |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | ACT | 2023-06-30 -> 2024-06-30 | -1.0545 | yes (\|M1-G\|>1.0) | 1 (was #1 under old M1-G magnitude too) | **-0.1093** | yes | **1** | 0.0660 | Both M1-G and M3-G large; real governance-share contraction, not an artifact. Becomes rank 1 under the new metric (was already the largest \|M1-G\| in the corpus). |
| 2 | BEL | 2016-12-31 -> 2017-12-31 | +1.2790 | yes | 2 | **+0.0993** | yes | **2** | n/a | Retained; own-volume increase and share increase agree. |
| 3 | ACT | 2017-06-30 -> 2018-06-30 | +1.7360 | yes | 3 (largest old \|M1-G\| in this set) | **+0.0865** | yes | **3** | 0.0193 | Old M1-G magnitude was denominator-sensitive (inflated by report-length change, per 7F.7a); M3-G confirms a real, smaller-magnitude but still-material share increase -- retained, re-ranked below ACT 2023-24/BEL 2016-17 under the new metric. |
| 4 | BEL | 2018-12-31 -> 2019-12-31 | -1.0697 | yes | 4 | **-0.0635** | yes | **4** | 0.0056 | Absolute governance volume roughly flat; relative share declined because other custom-taxonomy categories expanded -- share-relative movement, correctly retained under M3-G. |
| 5 | SDL | 2024-06-30 -> 2025-06-30 | -0.4743 | no (\|M1-G\|<1.0 heuristic bar) | not ranked | **-0.0609** | **yes (new)** | **5** | 0.0004 | Newly eligible: M1-G's old epsilon=1.0 heuristic missed this pair; M3-G's share-based threshold catches it. Boundary-sensitive under +/-5-hit perturbation per 7F.7a -- eligibility not altered on that basis. |
| 6 | SBP | 2023-12-31 -> 2024-12-31 | +0.0793 | no | not ranked | **+0.0589** | **yes (new)** | **6** | 0.0230 | Newly eligible, same reason as SDL. Also boundary-sensitive under +/-5-hit perturbation. |
| -- | SUR | 2023-06-30 -> 2024-06-30 | +0.0915 | no | not ranked | -0.0496 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0496), correctly excluded. |
| -- | BEL | 2020-12-31 -> 2021-12-31 | -0.6077 | no | not ranked | -0.0481 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0481), correctly excluded. |
| -- | ACT | 2022-06-30 -> 2023-06-30 | -0.2337 | no | not ranked | -0.0403 (below 0.05) | no | not ranked | -- | Share-relative case (7F.7a example): confirmed just below materiality (0.0403), correctly excluded. |
| -- | ACT | long-gap pair | large (varies) | quality-excluded | not ranked | (quality-excluded) | no | not ranked | -- | `report_side_signal_quality` gate excludes this pair regardless of M3-G magnitude -- verified via `test_governance_quality_gate_unchanged`. |

All four previously-eligible pairs (ACT 2023-24, BEL 2016-17, ACT 2017-18,
BEL 2018-19) are retained under M3-G. Two new pairs (SDL 2024-25, SBP
2023-24) become eligible. Overall eligible count changes from (effectively
1, under the old epsilon=1.0 heuristic which produced almost no eligible
findings, mirroring financial-condition's pre-M3 state) to exactly 6,
matching 7F.7a's validated corpus result. This redesign is *additive* in
this corpus, unlike financial-condition's M1->M3 switch, which was net
substitutive.

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

## 14. Test results

Targeted:
`.venv/bin/python -m pytest tests/test_governance_share_metrics.py
tests/publishing/test_publishing_governance_metric.py
tests/publishing/test_publishing_findings.py
tests/publishing/test_publishing_discovery.py -q` -- all pass.

Full Python suite: `.venv/bin/python -m pytest -q` -- **1233 passed, 3
skipped**.

Full frontend suite: `npx vitest run` -- **1033 passed** (111 test files).

`npx eslint .` -- clean. `npx tsc --noEmit` -- clean. `npx next build` --
succeeds (Turbopack, all 11 routes compiled).

New test files: `tests/test_governance_share_metrics.py` (formula/bounds/
zero-vector unit tests, also closes a pre-existing coverage gap for the
shared `financial_language_metrics.py` helpers),
`tests/publishing/test_publishing_governance_metric.py` (M3-G-not-M1-G
ranking, epsilon, quality gate, all 6 anchor/new-eligibility cases),
`web/tests/component/governance-supporting-detail.test.tsx`,
plus targeted additions to `test_publishing_findings.py`,
`test_publishing_discovery.py`, `discovery-results-table.test.tsx`,
`comparison-service.test.ts`, `discovery-repository.test.ts`,
`discovery-service.test.ts`, and the shared TS comparison fixtures.

## 15. Local publication validation

Against the local Docker Postgres (`market_documents` / `market_documents_app`,
port 5434):

1. `alembic -c alembic.ini upgrade head` -> `b7c8d9e0f1a2` applied.
2. `market-documents pairs language-build-all` -> `Completed: 0, Completed
   with warnings: 25, Skipped: 0, Ineligible: 0, Failed: 0` (fresh rebuild
   forced by the `SIGNAL_VERSION` bump; all 25 pairs rebuilt).
3. Verified in-database: exactly the 6 expected eligible pairs, exact
   `M3-G` values matching the spec to 4 decimal places, exact ranking order
   (ACT 2023-24, BEL 2016-17, ACT 2017-18, BEL 2018-19, SDL 2024-25, SBP
   2023-24), the 3 share-relative examples (SUR 2023-24, BEL 2020-21, ACT
   2022-23) each confirmed just below the 0.05 bar.
4. `alembic -c alembic_app.ini upgrade head` -> `app_0012` applied.
5. `market-documents publish build --publication-version 7f7a1-local-1
   --skip-qa-chunks` -> `status=READY publication_id=9ba89fc6-426c-58d6-8464-57d9e34f7795`.
6. `market-documents publish validate --publication-id ...` -> `checks_run=437992
   passed=True`.
7. `market-documents publish promote --publication-id ...` -> `[OK] publication
   ... is now ACTIVE`.
8. Queried `app.current_discovery_items` / `app.current_report_comparisons`:
   `largest_governance_shift` (corpus scope) returns exactly 6 rows in the
   expected rank order with `supporting_value == governance_share_change`;
   `governance_change` (M1-G) still populated and unchanged on every row;
   other discovery types (`largest_financial_condition_shift`,
   `largest_negative_tone_shift`, `largest_risk_introduction`,
   `largest_risk_removal`, `largest_uncertainty_increase`) present with
   unchanged counts/shape.
9. Queried `app.current_language_metrics` for `population =
   'governance_subcategory'`: all 9 subcategories persisted per comparison
   (not just top 3 -- see section 16 caveat).
10. UI smoke (`next start` against the local publication): `/discover?type=
    largest_governance_shift` returns 200 with the headline "Largest
    governance-language shift"; `/discover?type=largest_governance_shift&
    company=SUR` correctly renders the "Below materiality threshold" state;
    `/comparisons/<ACT 2023-24 id>` renders the "Governance supporting
    detail" section with M1-G density, M6-G topic-mix, the subcategory
    movers table (Board/Regulatory Compliance among the top movers), and
    the correct own-volume interpretation sentence for this pair (its
    `|M1-G| > 1.0`, consistent with `|M3-G|`'s direction).

## 16. Known caveats

- **Heuristic threshold in the share-relative interpretation** (section 9):
  `|M1-G| < 1.0` as the "own volume changed little" cutoff is a documented
  heuristic, not derived from a formal boundary in the 7F.7a methodology
  doc. It correctly classifies the corpus's clearest examples (ACT 2023-24
  as own-volume, the near-threshold SUR/BEL/ACT share-relative examples as
  share-relative once computed at the formula level) but is not claimed to
  be precise at arbitrary margins.
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

## Production readiness

**READY_WITH_CAVEATS.**

Rationale: implementation is complete, fully tested (Python + frontend
suites both green, lint/tsc/build clean), and verified against a fresh
local publication build that exactly reproduces the 7F.7a validated corpus
result (6 eligible findings, exact ranking, exact anchor values). The
caveats above (heuristic interpretation threshold, boundary-sensitive
SDL/SBP, sparse-subcategory presentation) are pre-existing methodology
characteristics already flagged in 7F.7a, not implementation defects, and
do not block production readiness -- they are documented so a future
reviewer doesn't rediscover them.

If/when the user decides to deploy, the steps (not executed as part of this
track, per explicit instruction to stop before deploying) would be:

1. Apply `alembic -c alembic.ini upgrade head` against the production
   research database (adds `b7c8d9e0f1a2`).
2. Run `market-documents pairs language-build-all` against production
   (forces a fresh `LanguageSignalRun` for all pairs via the `SIGNAL_VERSION`
   bump).
3. Apply `alembic -c alembic_app.ini upgrade head` against the production
   app database (adds `app_0012`; re-expands `current_report_comparisons`).
4. Re-apply `app_grants`/role permissions if the production rollout
   playbook requires it after a schema change (per the 7F.5 precedent,
   section 6 of `docs/financial-condition-production-rollout-7f5.md`).
5. `market-documents publish build --publication-version <next-version>`
   against production.
6. `market-documents publish validate --publication-id <id>`.
7. `market-documents publish promote --publication-id <id>`.
8. Deploy the frontend (Vercel) with the updated `web/` code.
9. Live smoke-check `/discover?type=largest_governance_shift` and the ACT
   2023-24 comparison detail page in production, mirroring section 15/23
   here.

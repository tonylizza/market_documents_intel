# Track 7F.4 — Financial-Condition Metric Implementation and Discover Update

Implements the methodology accepted by 7F.1–7F.3 end to end: M3
(financial-condition hit-share change) replaces M1 (density-rate change) as
the Discover ranking/materiality metric for financial-condition shifts; M6b
(subcategory topic-mix change) is added as supporting detail; M1 is retained,
unchanged, as descriptive context. No other Discover metric, quality gate, or
taxonomy was touched.

## 1. Methodology implemented

Per `docs/financial-condition-ranking-calibration-7f3.md`'s
`ADOPT_M3_WITH_THRESHOLD` decision:

- **Primary ranking/materiality metric**: M3, threshold `|M3| >= 0.04`.
- **Supporting detail**: M6b (no sign/direction), M1 (density, contextual),
  dominant financial-condition subcategory movers.
- **Quality gate**: unchanged (`report_side_signal_quality ∈ {GOOD, USABLE}`
  and `report_side_primary_eligible`), applied on top of the M3 threshold.
- No taxonomy change, no other Discover metric change, no epsilon
  recalibration for any other candidate.

## 2. Schema changes

**Research DB** (`migrations/versions/f1a2b3c4d5e6_...py`): four nullable
`Float` columns on `report_pair_language_features`:
`financial_condition_share_earlier`, `financial_condition_share_later`,
`financial_condition_share_change`, `financial_condition_topic_mix_change`.

**App DB** (`migrations_app/versions/app_0011_...py`, head advances
`app_0010` → `app_0011`): five columns on `app.report_comparisons`
(`financial_condition_share_earlier/_later/_change`,
`financial_condition_share_change_label`,
`financial_condition_topic_mix_change`), plus a `CREATE OR REPLACE VIEW` of
`app.current_report_comparisons` (required — Postgres freezes `SELECT t.*`
at view-creation time). No changes to `LanguageMetric`, `DiscoveryItem`,
`MetricDefinition`, or `MetricLabelThreshold` schemas; the new metric keys
and subcategory-mover rows use existing generic columns.

**SignalRowInput** (`financial_language_metrics.py`) gained one additive
field, `custom_subcategory_hits: dict[tuple[str, str], int]`, populated from
the *same* `match_passage` output the existing `custom_category_hits`
already collapses to category level — no second hit-counting path.
`SIGNAL_VERSION` was bumped (`1.0.0` → `1.1.0`) so the next
`language-build-all` rebuilds every pair rather than skipping.

## 3. M3 / M6b formulas

- **M3** (`financial_condition_share_change`): per side,
  `share = financial_condition_hits / total_custom_taxonomy_hits` (sum of
  the 4 `CUSTOM_TAXONOMY_CATEGORIES`), over `feature_eligible_primary` — the
  same population M1 uses. `M3 = share_later - share_earlier`, bounded
  `[-1, 1]` by construction (both shares are in `[0, 1]`).
- **M6b** (`financial_condition_topic_mix_change`): 12-dim subcategory-share
  vector within `financial_condition` only (order = 7F.3/taxonomy-yaml
  order: revenue, cost_margin, cash_flow, debt, liquidity,
  capital_expenditure, impairment, working_capital, dividends, tax,
  restructuring, acquisitions_disposals), share = subcategory hits /
  financial-condition-category hit total, per side.
  `M6b = 1 - cosine(vec_earlier, vec_later)`. **Zero-vector rule**: if
  either side has zero financial-condition hits, `M6b = None` (never a
  fabricated 0.0/1.0) — see `cosine_distance` in
  `financial_language_metrics.py`, tested explicitly.

## 4. Publication changes

- `findings.ComparisonMetrics` gained `financial_condition_share_change` and
  `financial_condition_topic_mix_change`.
- `publisher.METRIC_CATALOG` gained two entries (`financial_condition_share_change`,
  unit `share`, signed direction; `financial_condition_topic_mix_change`,
  unit `distance_0_1`, explicitly no direction interpretation).
- `publisher._comparison_metrics` and the `ReportComparison` row builder wire
  both new fields through; `financial_condition_change`/`_label` (M1) are
  populated exactly as before.
- New: up to 3 dominant financial-condition subcategory-mover rows per
  comparison, persisted as `LanguageMetric` rows
  (`metric_scope="report_side"`, `population="financial_condition_subcategory"`,
  `category="financial_condition"`, `subcategory=<name>`,
  `earlier_count`/`later_count`), selected by absolute hit-count change, from
  the same `PassageLanguageCategoryHit` data already iterated when building
  `passage_language_signals` rows.

## 5. Discover ranking change

`findings.CANDIDATES`'s `largest_financial_condition_shift` `CandidateSpec`:

| | Before | After |
|---|---|---|
| `metric_key` | `financial_condition_language_change` (M1) | `financial_condition_share_change` (M3) |
| `unit` | `rate_per_1000_words` | `share` |
| `epsilon` | `1.0` (undocumented heuristic) | `0.04` (7F.3 evidence-calibrated) |
| gate | `_gate_report_side` (unchanged) | `_gate_report_side` (unchanged) |

`discovery.py` required no change — it iterates `CANDIDATES` directly.

## 6. Threshold

`|M3| >= 0.04`, per 7F.3's convergence of the p75 percentile (0.0421) and
median + 1×scaled-MAD (0.0372) over the 25-pair corpus. A presentation-only
"near materiality threshold" band (item 9 of the brief) was evaluated and
**omitted**: 7F.3's boundary-sensitivity evidence does not identify a clean,
defensible band distinct from ordinary corpus variation, and inventing one
would misrepresent the calibration work as more precise than it is.

## 7. Quality gate

Unchanged. Verified: ACT 2016→2024 (`NEEDS_REVIEW`, `primary_eligible=False`)
stays excluded from Discover regardless of its M3 magnitude (0.0991, which
would otherwise clear 0.04) — see
`test_financial_condition_quality_gate_unchanged` and the live corpus query
in §13 below.

## 8. UI semantics

- Discover headline unchanged: "Largest financial-condition language shift."
  Description updated to: "Change in financial-condition language's share of
  classified risk / financial-condition / governance / strategy language."
  Value column now shows a `share` percentage, not a rate.
- Comparison-detail page: M1's headline card is relabeled "Financial-condition
  language density change" with explanation text making explicit it is
  contextual, not the ranking metric. A new "Financial-condition supporting
  detail" section shows M6b (unsigned, `distance_0_1`) and a subcategory-mover
  table (earlier/later hit counts, signed change), sourced from the new
  `LanguageMetric` population and kept out of the existing
  report-side rate chart/table (which assumes rate-shaped rows).
- Discover empty state for `largest_financial_condition_shift` + a company
  filter now distinguishes four states instead of one generic message:
  no comparisons / failed quality gate / below materiality (shows the
  largest observed quality-eligible M3, the 0.04 threshold, and a link to
  that comparison, explicitly labeled "Below materiality threshold," never
  ranked as an eligible finding) / normal ranked results.

## 9. Before/after findings (25-pair corpus)

| Ticker | Pair | Old M1 | Old eligible | New M3 | New eligible | M6b | Change reason |
|---|---|---|---|---|---|---|---|
| ACT | 2016-06-30→2017-06-30 | −0.9256 | No | −0.1002 | **Yes** | 0.0895 | M3 clears 0.04; M1 never cleared old epsilon=1.0 |
| ACT | 2017-06-30→2018-06-30 | +1.0019 | Yes | +0.0182 | **No** | 0.0043 | Demoted — M1 artifact (denominator shrinkage, ~35% word-count drop), M3 well below 0.04 |
| ACT | 2023-06-30→2024-06-30 | +0.1757 | No | +0.0421 | **Yes** | 0.0741 | M3 clears 0.04 |
| BEL | 2017-12-31→2018-12-31 | +0.5544 | No | +0.0423 | **Yes** | 0.0837 | M3 clears 0.04 |
| BEL | 2018-12-31→2019-12-31 | +0.1414 | No | +0.0501 | **Yes** | 0.0212 | M3 clears 0.04 |
| BEL | 2020-12-31→2021-12-31 | +0.2783 | No | +0.0531 | **Yes** | 0.0927 | M3 clears 0.04 |
| SBP | 2023-12-31→2024-12-31 | −1.1027 | Yes | −0.0725 | Yes | 0.0126 | Eligible under both — strongest cross-normalization positive control |
| SUR | 2024-06-30→2025-06-30 | −0.4671 | No | −0.0612 | **Yes** | 0.0343 | M3 clears 0.04 |

Every other pair (17 of 25, incl. all of KP2, SDL, and the remaining
ACT/BEL/SUR pairs) is ineligible under both M1 and M3 — no change. Every row
above was independently verified against a fresh local publication build
(§14).

**Result**: 7 eligible findings (was 2), 4 companies represented — ACT, BEL,
SBP, SUR (was 2 — ACT, SBP). Exactly matches 7F.3's projected retrospective
result.

## 10. BEL behavior

Before: BEL never appeared under `largest_financial_condition_shift` (all 6
BEL pairs had `|M1| < 1.0`). After: BEL has 3 eligible pairs (2018→2019,
2017→2018, 2020→2021, ranked 4th/5th/6th of 7 by `|M3|`), so BEL's Discover
company filter now shows real ranked results instead of the generic "No
results for these filters" message. Verified live (§14): `/discover?
type=largest_financial_condition_shift&company=BEL` returns 3 rows, largest
is 2020→2021 (M3 = +0.0531).

## 11. ACT artifact correction

ACT 2017→2018 (the flagship 7F.1 diagnosis): M1 = +1.0019 (would have been
eligible under the old epsilon=1.0), M3 = +0.0182, M6b = 0.0043. Confirmed
via the fresh local rebuild these values match the brief's approximate
figures (M1≈+1.0019, M3≈+0.0182, M6b≈0.0043) to 4 decimal places. No longer
an eligible Discover finding — regression test:
`test_act_2017_2018_artifact_demoted_by_m3`.

## 12. SBP positive control

SBP 2023→2024 (the strongest cross-normalization positive control):
M1 = −1.1027, M3 = −0.0725, M6b = 0.0126 — matches the brief's approximate
figures exactly. Remains eligible (rank 2 of 7). Regression test:
`test_sbp_2023_2024_positive_control_retained`.

## 13. Test results

Python (`.venv/bin/python -m pytest`): **1208 passed, 3 skipped**, full
suite. New/updated tests cover: `custom_taxonomy_hit_share`,
`cosine_distance` (incl. zero-vector → `None`), M3 bounds, candidate uses M3
not M1, epsilon=0.04, quality gate unchanged, ACT 2017→2018 demoted, SBP
2023→2024 retained, other Discover candidates unaffected
(`tests/test_financial_language_metrics.py`,
`tests/publishing/test_publishing_findings.py`).

Frontend (`npm test`): **1019 passed**, 110 test files, full suite,
including new tests for the four-state Discover empty state, the
`financialConditionCompanyStatus` service resolution, the
`financialConditionSubcategoryMovers` split from the report-side language
metrics chart, and a live-DB repository test for
`getFinancialConditionCompanyStatus`. `npm run lint` and `npx tsc --noEmit`
both clean. `npm run build` (production build) compiles cleanly.

## 14. Local publication validation

1. `pairs language-build-all` rebuilt all 25 pairs (forced by the
   `SIGNAL_VERSION` bump) — 25 `COMPLETED_WITH_WARNINGS`, 0 skipped, 0
   failed.
2. `publish build --publication-version 7f4-local-validation-1
   --skip-qa-chunks` → `status=READY`; `publish promote` activated it
   locally.
3. Verified directly against the local app DB:
   - M3/M6b non-null for all 25 quality-run pairs (via
     `report_pair_language_features`, research DB).
   - `app.current_report_comparisons` exposes the 5 new columns (proves the
     `CREATE OR REPLACE VIEW` step worked).
   - `largest_financial_condition_shift`, `rank_scope='corpus'`: exactly 7
     rows, exact pair/company set matches §9/§13 of the 7F.3 brief.
   - `app.current_language_metrics` has exactly 75 rows with
     `population='financial_condition_subcategory'` (25 pairs × 3 movers).
   - `metric_definitions` gained the 2 new metric-key rows with correct
     units.
   - Other discovery-type counts (governance, negative-tone, risk
     introduction/removal, uncertainty) unaffected by this change.
4. Live UI smoke test (local `next dev`, local app DB): Discover "all
   companies" (7 correctly ranked rows, share-percentage values), BEL/ACT/SBP
   company filters, KP2/SDL below-materiality empty states (with observed
   value + threshold + link), comparison-detail page (M1 relabeled/recontextualized,
   new M6b + subcategory-movers section rendering real data).

## 15. Known caveats

- **Local-migration grant drift (operational, not a code defect)**: this
  track's app migration re-creates `app.current_report_comparisons` via
  `CREATE OR REPLACE VIEW`, run under whatever role `APP_DATABASE_URL`
  connects as. Locally that is the plain `market_documents` role, not
  `app_publisher` — after running the migration, the view's owner changed
  and `app_readonly`'s prior `GRANT SELECT` on it no longer applied (Node's
  `pg` driver got `permission denied for view current_report_comparisons`,
  surfaced to the app as a generic `DatabaseUnavailableError`). Fixed locally
  by re-running `psql <app-db-url> -f scripts/sql/app_grants.sql`
  (idempotent, no password rotation) — this is the project's documented,
  expected step after any migration that touches a `current_*` view (see
  that file's own header), not something specific to this track, but it is
  easy to miss. **Anyone applying `app_0011` to any environment must
  re-run `app_grants.sql` (or `app-init-roles`) immediately afterward.**
  This is called out explicitly in the production steps below.
- The near-materiality-threshold presentation label (brief item 9) was
  deliberately omitted — see §6.
- The company-page "Latest financial-condition changes" surface
  (`postgres-company-repository.ts`) intentionally still reads M1 — out of
  this track's hard scope; a future track can decide whether to switch it
  to M3 or keep it as density context.
- Subcategory-mover selection uses simple top-3-by-absolute-change; no
  significance/materiality threshold is applied to individual subcategories
  (they're supporting detail, not a ranked finding).

## 16. Related documents

- `docs/financial-condition-shift-methodology-audit.md` — baseline pipeline
  trace and M1 shared-epsilon audit.
- `docs/financial-condition-metric-calibration-7f1.md` — Q1–Q6 diagnosis
  (denominator-shrinkage finding).
- `docs/financial-condition-metric-redesign-7f2.md` — M1–M6b candidate
  formulas, MODIFY recommendation.
- `docs/financial-condition-ranking-calibration-7f3.md` — M3 threshold
  selection, `ADOPT_M3_WITH_THRESHOLD` decision, this track's methodology
  source of truth.

# Track 7F.9 — Unified Discover Metrics: Implementation & Local Validation

**Status: implemented and validated locally as one release. No production actions:** no Neon
project was created or touched, no Vercel deploy, no production publication was promoted, and
the fresh-Neon cutover has not started.

**Question answered:** has the frozen 7F.8/7F.8a Discover methodology been implemented correctly,
validated locally as one coherent release, and shown to work with the shared-artifact
architecture without unnecessary storage growth?

**Verdict: `READY_WITH_CAVEATS`** (Section 20). The methodology, anchors, research parity,
expected findings and regressions are all exact and green. Two shared-artifact findings from
this track keep it from an unqualified READY:

- a language-signal re-run duplicates the signal-artifact generation by construction;
- QA-chunk vector search through the COALESCE view cannot use HNSW.

---

## 1. Pre-implementation inventory

| Area | Location | Change |
|---|---|---|
| Signal aggregation (pure) | `services/financial_language_metrics.py` | `SignalRowInput.passage_alignment_id`; `pair_mean_count_change`, `density_change`, `topic_change_conjunction`, `change_consistency_ratio`, `largest_passage_share`, `topic_unit_deltas`, `topic_change_diagnostics`, `compute_topic_change` |
| Signal orchestration | `services/financial_language_signals.py` | passes `passage_alignment_id`; computes and persists the 22 new fields |
| Signal version | `services/financial_language_config.py` | `SIGNAL_VERSION` 1.3.0 → **1.4.0** (folded into `configuration_hash`) |
| Research schema | `models/financial_language.py`, `migrations/versions/d9e0f1a2b3c4_…` | 22 nullable columns on `report_pair_language_features` |
| App schema | `publishing/models.py`, `migrations_app/versions/app_0015_…` | 26 nullable columns on `app.report_comparisons`, with the view re-expanded |
| Publisher | `publishing/publisher.py` | `_topic_change_fields` passthrough, `ComparisonMetrics` fields, band pools, METRIC_CATALOG rewrite |
| CandidateSpecs | `publishing/findings.py` | 4 published specs; `DISABLED_CANDIDATE_KEYS` |
| Discovery ranking | `publishing/discovery.py` | docstring only (ranks `CANDIDATES`, so disabled types are never ranked) |
| Validation | `publishing/validation.py` | `disabled_discovery_type_not_ranked`, `disabled_discovery_type_not_a_finding` (scoped to 7F.9-catalog publications) |
| API/repository | `web/lib/repositories/{comparison-mapper,postgres-comparison-repository,comparison-repository,postgres-discovery-repository,postgres-company-repository}.ts`, `web/lib/schemas/comparison.ts` | `TOPIC_CHANGE_COLUMNS_SQL`, `mapTopicChangeRow`, `getTopicEvidencePassages`; company-status fallbacks switched to the topic change at 0.25; risk types dropped from home-page language types |
| Discover UI config | `web/lib/config/discovery.ts` | titles/descriptions; `publicationStatus` (`published` / `under_review`) with reasons |
| Finding copy | `web/lib/content/finding-copy.ts`, `web/lib/services/headline-metrics.ts` | new semantics and units; explanations corrected |
| Pages/panels | `web/app/discover/page.tsx`, `web/app/comparisons/[comparisonId]/page.tsx`, `web/components/TopicChangeDecomposition.tsx` (new), `ComparisonEvidenceRow.tsx`, `FinancialConditionSupportingDetail.tsx`, `GovernanceSupportingDetail.tsx`, `DiscoveryResultsTable.tsx` | under-review states, decomposition panel, weak-alignment labelling |
| Services | `web/lib/services/{topic-change,alignment-caveat}.ts` (new), `discovery-service.ts`, `comparison-service.ts` | presentation helpers; published-type filtering |
| Tests | see Section 16 | |
| Scripts | `scripts/research_7f9_implementation_crosscheck.py`, `scripts/benchmark_7f9_current_views.py` (new, read-only) | |

**Not changed (deliberately):**

- matching, negation, taxonomy, population rules;
- alignment, similarity, embeddings, QA chunking;
- risk/disclosure-change formulas and weights;
- shared-artifact identity and version constants.

Internal discovery keys are unchanged, for example `largest_negative_tone_shift` is still the
URL/finding key. Only the product copy changed ("Net tone decline").

## 2. Implemented formulas

Per pair, over the `feature_eligible_primary` population (the same population as M1/M3/M6),
with `w1, w2` = eligible words:

```
D   = 1000 * (h2 - h1) / ((w1 + w2) / 2)            *_count_change_per_1000   (None if mean words <= 0)
M1  = 1000 * (h2/w2 - h1/w1)                        existing *_language_change / uncertainty_intensity_change
C   = sign(D) * min(|D|, |M1|)  if D*M1 > 0 else 0  *_topic_change            (None only if a leg is None)
```

- **Hits `h`:**
  - financial condition: `financial_condition_hits_*` (taxonomy, all subcategories);
  - governance: `governance_hits_*`;
  - uncertainty: Loughran-McDonald `uncertainty_count_*`.
- **Order of operations:** `M1` is computed in exactly the research order, so the research values
  are reproduced bit for bit.
- **Net tone (unchanged):** `1000 * [(P2-N2)/w2 - (P1-N1)/w1]`. It is published with
  `positive_rate_change` and `negative_rate_change`.

**Supporting diagnostics (never used for eligibility).** Hits are grouped by
`passage_alignment_id`, and `d_i` is the later-minus-earlier hit change of alignment unit `i`:

```
net = Σ d_i = h2 - h1          gross = Σ |d_i|
change_consistency_ratio = net / gross        (0 if gross = 0)
largest_passage_share    = max|d_i| / gross   (0 if gross = 0)
supporting_hits = Σ |d_i| where d_i shares sign(net); opposing_hits = Σ |d_i| against it (both 0 if net = 0)
```

- `sign(net) = sign(D)`, so this is the finding's direction whenever `C ≠ 0`.
- There is no `evidence_ok` field and no `net / sqrt(Σd²)` statistic. Nothing is labelled a
  z-score.

## 3. Thresholds and CandidateSpecs

| Discover type (key) | Metric | Unit | ε | Direction | Gate |
|---|---|---|---|---|---|
| `largest_financial_condition_shift` | `financial_condition_topic_change` | rate / 1,000 words | 0.25 | both | report-side |
| `largest_governance_shift` | `governance_topic_change` | rate / 1,000 words | 0.25 | both | report-side |
| `largest_uncertainty_increase` | `uncertainty_topic_change` | rate / 1,000 words | 0.75 | `v > 0` | report-side |
| `largest_negative_tone_shift` | `net_tone_change` | rate / 1,000 words | 2.25 | `v < 0` | report-side |

Magnitude is `|v| / ε`, and eligibility is `magnitude ≥ 1`. There is no evidence gate.

## 4. Disabled metrics

`DISABLED_CANDIDATE_KEYS` in `findings.py` covers these types. None has a CandidateSpec, so they
are never ranked and never selected as a finding.

| Type | Reason |
|---|---|
| `largest_risk_introduction` | NEW status unreliable (moved passages, alignment misses), per 7F.8 §9 |
| `largest_risk_removal` | REMOVED status unreliable, per 7F.8 §9 |
| `largest_overall_change` | Feature-quality gate fails 25/25 (confidence share, similarity disagreement), per 7F.8 §12 |
| `largest_new_disclosure_share` | **Confirmed** to use the same `_gate_feature` (feature quality + primary eligibility) that fails 25/25, so disabled in this batch |

How the disabled state appears:

- **Discover:** a "Not currently published" section lists all four with reasons. Requesting one
  directly (for example `?type=largest_risk_removal`) shows "Not currently published: methodology
  under review … This does not mean that no change occurred." It never falls back to another
  ranking.
- **METRIC_CATALOG:** the entries say "methodology under review". The NEW/SUBSTANTIALLY_MODIFIED
  copy mismatch for the risk metrics is fixed: they measure NEW-only / REMOVED-only passages, per
  1,000 words of those passages.

## 5. Migrations

| DB | Revision | Content | Round trip |
|---|---|---|---|
| research | `d9e0f1a2b3c4` (after `c8d9e0f1a2b3`) | 22 nullable columns: words ×2, FC hits ×2, count change ×3, topic change ×3, 4 diagnostics × 3 categories | applied locally |
| app | `app_0015` (after `app_0014`) | 26 nullable columns on `app.report_comparisons` (above + `uncertainty_hits_*`, `positive_rate_change`, `negative_rate_change`); re-creates `current_report_comparisons` | `test_app_0015_downgrade_to_app_0014_and_reupgrade` passes |

- **Existing columns:** all M1/M3/M6 columns are retained. Governance and uncertainty hit inputs
  already existed in research, so they were reused rather than duplicated.
- **Fresh-empty-database path:** verified on a brand-new local DB (`market_documents_app_7f9`):
  - `app-init` ran `app_0001`→`app_0014` (14 migrations);
  - a baseline was built natively in shared-artifact format;
  - `app_0015` was then applied;
  - a second publication was built.

  Nothing is backfilled, and no large content is copied into `app.*`.
- **Grants:** the rollout must follow `app_0015` with `scripts/sql/app_grants.sql` (password-free
  and idempotent), as for app_0011–0013.

## 6. Signal version behaviour

- **Version bump:** `SIGNAL_VERSION` is now 1.4.0, which changes `configuration_hash`.
- **Regeneration:** `pairs language-build-all` without `--force` produced 25 new runs, 0 skipped
  and 0 failed (1 min 48 s). The version bump alone forces regeneration.
- **Not required, confirmed:**
  - no passage re-extraction;
  - no alignment, feature or similarity rerun;
  - no embeddings;
  - no retrieval-artifact regeneration;
  - no QA-chunk regeneration.

  None of those tables changed in the research DB (Section 15). The new run pins the same
  feature and alignment runs.
- **Content identity:** every per-passage signal count in the new runs is identical to the old
  ones. The 7F.8a script output is byte-identical before and after (Section 13).

## 7. UI semantics

| Tab | Title | Must not imply |
|---|---|---|
| FC | Financial-condition language change | financial health, performance or risk (stated in copy) |
| Governance | Governance language change | governance quality better or worse |
| Uncertainty | Uncertainty-language increase | actual business uncertainty |
| Net tone | Net tone decline | sentiment, management sentiment, outlook |

**Topic-language changes panel** (comparison page, `TopicChangeDecomposition`). For each of
FC, governance and uncertainty it shows:

- the topic change and its threshold status;
- a plain statement of why it is or is not 0 (flat count, disagreeing legs, agreeing legs);
- hits earlier → later;
- the count leg, the density leg, and words earlier → later with the % length change;
- hits with vs against the net change, change consistency, and the largest single-passage share,
  explicitly labelled as supporting context that never decides publication;
- the **three highest-hit eligible passages in each report**.

Net tone shows the positive- and negative-density changes and the dominant driver ("Driven mainly
by fewer positive words").

**Supporting sections:**

- FC supporting detail now shows the M3 share alongside M6b and the subcategory movers.
- Governance supporting detail shows the M3-G share decomposition, M1-G, M6-G and the movers.

**Evidence and alignment:**

- Evidence is report-side on purpose: the panel shows each report's own high-hit passages, not
  earlier→later pairs, so a mis-pairing cannot be read as the cause of a change.
- A NEW, REMOVED or SUBSTANTIALLY_MODIFIED passage with LOW or NEEDS_REVIEW confidence is
  labelled **"Possibly moved or restructured"**. This applies both in the panel and as a badge on
  the evidence explorer (`alignment-caveat.ts`).

## 8. Anchor values (persisted, `report_pair_language_features`, run 1.4.0)

| Cat | Pair | Expected | Persisted | Eligible |
|---|---|---|---|---|
| FC | ACT 2017→2018 | 0 | +0.000000 | no |
| FC | BEL 2019→2020 | 0 | +0.000000 | no |
| FC | SBP 2023→2024 | ≈ −0.902 | −0.901586 | yes |
| FC | BEL 2020→2021 | ≈ +0.278 | +0.278294 | yes |
| FC | ACT 2016→2017 | ≈ −0.926 | −0.925620 | yes |
| GOV | SUR 2023→2024 | 0 | +0.000000 | no |
| GOV | BEL 2018→2019 | ≈ −0.139 (below) | −0.139100 | no |
| GOV | ACT 2017→2018 | ≈ +0.500 | +0.499796 | yes |
| GOV | BEL 2016→2017 | ≈ +1.189 | +1.188940 | yes |
| GOV | ACT 2023→2024 | ≈ −0.917 | −0.916825 | yes |
| UNC | BEL 2019→2020 | 0 | +0.000000 | no |
| UNC | BEL 2020→2021 | 0 | +0.000000 | no |
| UNC | ACT 2019→2020 | ≈ +0.760 | +0.759565 | yes |

Golden tests:

- `tests/test_topic_change_metrics.py::test_anchor_conjunction` checks the formula level.
- `tests/publishing/test_publishing_findings.py::test_anchor_case_eligibility` checks eligibility
  at the CandidateSpec level.

## 9. Final findings (local publication `7f9-local-1`, corpus scope, read from persisted data)

| Type | Rank | Pair | Value |
|---|---|---|---|
| FC | 1 | ACT 2016→2017 | −0.925620 |
| FC | 2 | SBP 2023→2024 | −0.901586 |
| FC | 3 | BEL 2017→2018 | +0.554362 |
| FC | 4 | SUR 2024→2025 | −0.373637 |
| FC | 5 | BEL 2020→2021 | +0.278294 |
| GOV | 1 | BEL 2016→2017 | +1.188940 |
| GOV | 2 | ACT 2023→2024 | −0.916825 |
| GOV | 3 | ACT 2017→2018 | +0.499796 |
| GOV | 4 | SDL 2024→2025 | −0.452412 |
| GOV | 5 | ACT 2020→2021 | −0.268963 |
| UNC | 1 | ACT 2019→2020 | +0.759565 |
| Net tone | 1 | ACT 2017→2018 | −6.634620 |
| Net tone | 2 | BEL 2018→2019 | −3.825999 |
| Net tone | 3 | ACT 2021→2022 | −2.446246 |

- **Match:** exactly the expected 5 / 5 / 1 / 3 sets, in the expected order.
- **Disabled types:** zero risk-introduction, risk-removal, overall-change or new-disclosure items.
- **Finding keys** across all comparisons: FC 5, governance 5, net tone 3, uncertainty 1 (no
  disabled key).
- **Validation:** inline validation passed (566,173 checks, including the two new
  disabled-type checks).

## 10. Research vs implementation

`scripts/research_7f9_implementation_crosscheck.py` recomputes every new field from raw passage
rows with the **unchanged** 7F.8/7F.8a loaders and aggregation. It then compares against the
persisted columns for **all 25 pairs** (not only the 24 report-side-gated ones):

- max absolute difference **0.000e+00** on all 24 compared fields (words, hits, D, C_min, both
  ratios, supporting/opposing hits for all three categories);
- 0 mismatches.

Re-running the original scripts against the new runs:

- **`research_7f8a_topic_conjunction_evidence.py`:** output byte-identical to the pre-change run.
  Its own cross-check vs 7F.8 stays at 0.00e+00.
- **`research_7f8_discover_metrics_consolidation.py`:** every numeric cell is identical. 3 cells
  differ, all in the free-text "top subcategory" label, where two subcategories tie at the same
  share (for example ACT 2019→2020, capital_expenditure vs dividends, both 0.22). The script
  breaks those ties by set-iteration order.

## 11. Shared-artifact reuse (identity semantics inspected, not assumed)

Built from the same source data except for the new signal runs: baseline `7f9-baseline-1`
(pre-7F.9 code, signal 1.3.0 runs), then `7f9-local-1` (7F.9 code, 1.4.0 runs). Both record
`alignment_v1 / signals_v1 / qa_chunk_v1`.

| Family | Identity key | Baseline artifacts | 7F.9 artifacts | Shared |
|---|---|---|---|---|
| passage comparisons | `ALIGNMENT_ARTIFACT_VERSION` + research `alignment.id` | 23,279 | 23,279 | **23,279 (100%)** |
| retrieval contexts (+children) | `ALIGNMENT_ARTIFACT_VERSION` + `source_alignment_id` + side | 34,099 | 34,099 | **34,099 (100%)** |
| QA chunks (+membership) | `QA_CHUNKING_ARTIFACT_VERSION` + report + chunk index + model | 6,088 | 6,088 | **6,088 (100%)** |
| passage language signals | `LANGUAGE_SIGNAL_ARTIFACT_VERSION` + **research `PassageLanguageSignal.id`** + category + subcategory | 54,003 | 54,003 | **0** |

**Decision: `LANGUAGE_SIGNAL_ARTIFACT_VERSION` was not bumped, and no other artifact version was
bumped.**

- **Why no bump:** per-passage signal content is unchanged. The new generation's
  `(passage, side, category, subcategory, content_hash)` multiset is identical to the old one
  (54,003 = 54,003 rows, verified).
- **Why a new generation appears anyway:** the signal family's identity includes the research
  signal row id. Every new `LanguageSignalRun` mints new `PassageLanguageSignal` ids, so a
  metric-only signal re-run always creates a duplicate generation. That holds with or without a
  version bump, and the content-hash guard cannot prevent it because the ids differ.
- **Regression test:**
  `test_signal_run_regeneration_creates_new_signal_artifact_generation_only` pins this behaviour.
- **Neon impact:**
  - The cutover itself is unaffected: a fresh Neon database receives exactly one generation.
  - Every future metric-only `SIGNAL_VERSION` bump costs one extra signal generation
    (≈ 20 MB now) until the superseded publication is cleaned up and `gc-artifacts` runs.
  - **Recommended follow-up (not done here):** re-key the signal family on
    `(passage_alignment_id, report_side, category, subcategory)`, which are stable across signal
    runs of the same alignment run, with a one-time `signals_v2` bump. The brief said not to
    modify the shared-artifact architecture, so this is not implemented.

## 12. Storage delta (local, `pg_total_relation_size`)

**Research DB (local only):** +14.2 MB.

- `passage_language_signals`: +35,116 rows, +11.3 MB.
- `passage_language_category_hits`: +11,496 rows, +3.3 MB.
- 25 new runs and pair-feature rows: ≈ +0.05 MB.
- No passage, alignment, embedding or QA table changed.

**App DB:**

| Schema | Fresh empty | Baseline built | 7F.9 republish | Delta (republish) |
|---|---|---|---|---|
| `app_artifacts` | 0.19 MB | 112.04 MB | 131.77 MB | **+19.67 MB** (entirely the duplicate signal generation) |
| `app_corpus` | 0.08 MB | 108.18 MB | 108.20 MB | +0.00 |
| `app` (thin) | 0.85 MB | 79.71 MB | 156.30 MB | **+76.6 MB** (a second publication's membership rows; the new columns on 25 comparisons are negligible) |
| `app_internal` | 0.06 MB | 0.10 MB | 0.10 MB | 0 |
| **database** | 10.0 MB | 309.6 MB | 406.5 MB | **+96.9 MB** |

- **Generations:** 3 reused (alignment, retrieval contexts, QA chunks) and 1 new (signals, same
  `signals_v1`).
- **Explanation:** all growth is explained. The thin layer (≈ 76 MB per publication) is expected
  per-publication cost. The +19.7 MB is the identity duplication in Section 11.
- **Reclaimable:** once the baseline publication is cleaned up, both its thin rows and the old
  signal generation can be removed via `cleanup` + `gc-artifacts`. That was not run, so both
  publications stay available for comparison.
- **Neon footprint:** a fresh Neon cutover with one publication is ≈ 300 MB on this measure
  (≈ 79 app + 112 artifacts + 108 corpus). The ≤ 2-retained-publications policy from 7F.7a.4a
  still governs steady state.

## 13. Query benchmark (closes the 7F.7a.5 caveat)

`scripts/benchmark_7f9_current_views.py`: 5 warm-up runs, then 50 timed runs per query, on the
same local server.

- **`shared`:** `market_documents_app_7f9` (active `7f9-local-1`, content resolved through the
  `app_artifacts` COALESCE joins).
- **`inline`:** the dev DB `market_documents_app` (active `7f7a1a-local-1`, content inline in the
  thin tables, built without QA chunks).

| Query (`app.current_*`) | Shared median / p95 ms | Inline median / p95 ms |
|---|---|---|
| comparison by id | 1.02 / 1.87 | 0.95 / 1.42 |
| passage comparisons for a comparison (≤200) | 2.41 / 3.48 | 2.19 / 2.91 |
| retrieval contexts for a comparison (≤200) | 2.71 / 3.59 | 3.03 / 3.98 |
| language signals, comparison + category | 1.85 / 2.88 | 2.63 / 3.33 |
| QA chunks for one report (381 rows) | 14.55 / 18.12 | n/a (no QA chunks) |
| QA chunk vector top-10 | 25.00 / 29.57 | n/a |

**No material regression on the relational lookups.** The differences are within about ±0.8 ms.

**Material finding on QA vector search:** through `app.current_qa_chunks` the ORDER BY runs on
`COALESCE(t.embedding, art.embedding)`, so the planner cannot use either HNSW index.

- It does a hash join, full scan and top-N sort over all 6,088 chunks: ≈ 25–34 ms, exact recall.
- The same query directly on `app_artifacts.qa_chunks` uses `ix_app_artifacts_qa_chunks_hnsw_cosine`
  at ≈ 4.3 ms.
- **Assessment:** acceptable at this corpus size, and exact search never loses recall. But the
  cost grows linearly with chunk count, and the web Q&A repository queries this view.
- **Not changed here** (architecture frozen). The fix belongs to a later shared-artifact track, for
  example a vector subquery on the artifact table joined back to the active publication's thin
  rows.

## 14. Test results

| Suite | Result |
|---|---|
| Python, full (`.venv/bin/python -m pytest`) | **1288 passed, 3 skipped, 0 failed** (1243 before this track) |
| Frontend, full (`vitest run`, including repository tests against the seeded test DB) | **1052 passed, 0 failed** (113 files) |
| `eslint` | clean (exit 0) |
| `tsc --noEmit` | clean |
| `next build` | success |
| Python lint | none configured in the project venv (no ruff/mypy installed) |

**New or updated Python tests:**

- `tests/test_topic_change_metrics.py` (new): helpers, zero and sign cases, the M1 volume+length
  identity, diagnostics, and the 13 anchors.
- `tests/test_financial_language_signals.py`: persistence consistency of every new field.
- `tests/publishing/test_publishing_findings.py`: rewritten for the frozen specs, disabled keys and
  anchor eligibility.
- `tests/publishing/test_publishing_governance_metric.py`: rewritten, M3-G is now supporting.
- `tests/publishing/test_publishing_discovery.py`: retargeted to a published type, plus a
  disabled-types test.
- `tests/publishing/test_publishing_disclosure_change_quality.py`: a GOOD score is now **not**
  ranked.
- `tests/publishing/test_publishing_topic_change.py` (new): passthrough, catalog, validation, and
  the artifact-regeneration behaviour.
- `tests/publishing/test_app_migrations.py`: `app_0015` round trip.

**New or updated frontend tests:**

- `tests/unit/topic-change.test.ts` (new): thresholds, explanations, net-tone driver, alignment
  caveat.
- `tests/component/topic-change-decomposition.test.tsx` (new).
- discovery-service tests: under-review states.
- Updated for the new semantics: discovery-results-table, discovery-repository, finding-copy,
  seed fixture, detail fixtures and mocks.

## 15. Local smoke tests

The production build (`next start`) was pointed at `market_documents_app_7f9` via `app_readonly`.
Grants were applied with the password-free `app_grants.sql`.

| Check | Result |
|---|---|
| Discover landing | 200; published tabs; "Not currently published" section listing all 4 |
| Disabled tab request (`?type=largest_risk_introduction`, `largest_overall_change`) | 200; "methodology under review … does not mean that no change occurred" |
| FC detail (SBP 2023→2024) | −0.90 / 1,000 words; hits 71 → 55; report-side high-hit passages (Dividend policy p.17) |
| Governance detail (BEL 2016→2017) | +1.19; hits 111 → 152; M3 share supporting detail |
| Uncertainty detail (ACT 2019→2020) | +0.76; hits 275 → 325; clears threshold |
| Net tone (ACT 2017→2018) | −6.63; positive −5.44, negative +1.20; "Driven mainly by fewer positive words" |
| Weak-alignment labelling | "Possibly moved or restructured" badges on LOW-confidence SUBSTANTIALLY_MODIFIED rows |
| Passage search (keyword) / detail | 200 |
| Semantic and hybrid retrieval | 200, 20 results each (HNSW mode, local embedding service) |
| Report comparison / evidence explorer | 200 |
| Q&A | Retrieval of QA-chunk evidence works through `current_qa_chunks`. Gemini generation timed out twice under the default 15 s budget, then answered with a grounded citation (SBP 2024 dividend, [E1] p.17) under a 60 s budget. This is local provider latency, not related to this track, and the default model (`gemini-flash-lite-latest`) was used. |

## 16. KP2 date issue — **REQUIRES_MANUAL_DECISION** (not changed)

What local data says for the KP2 report at `data/raw/KP2/2025/annual_report.pdf`:

- **Registration:**
  - `period_end` = **2024-12-31**, `metadata_status` VALIDATED, `metadata_source` MANUAL;
  - `fiscal_label` = "YEAR ENDED 31 DECEMBER 2025";
  - `publication_date` = **2026-03-24**.
- **Provenance note:** "manually corrected period_end from 2025-12-31 to 2024-12-31 after
  verification from the annual report" (updated 2026-07-17). It gives no page or source.
- **The document's own text** (extracted passages):
  - "31 December 2025" appears ×511, "year ended 31 December 2025" ×307;
  - "31 December 2024" appears ×52, and "31 December 2023" ×6;
  - the Directors' Report is dated March 2026: "…for the financial year ended 31 December 2025";
  - "31 December 2024" appears as the comparative ("…year ended 31 December 2025 amounted to
    USD985,276 (31 December 2024: USD1,146,535)").
- **Pattern:** every other KP2 report sits in directory `FY+1` and was published in March of
  `FY+1`. This file, in directory 2025, carries FY2025 and March-2026 publication instead.

**Assessment.** The text evidence contradicts the manual correction. The file appears to be the
FY2025 report, so FY2024 would be missing. The pair `KP2 2023→2024` (12 months) would then really
be FY2023→FY2025 (24 months, irregular).

**Not corrected:** no period end was inferred or changed. It does not affect any 7F.9 finding:

- no KP2 pair is eligible in any published tab;
- KP2 2023→2024 uncertainty is +0.533, below 0.75.

It must be decided before the production cutover.

## 17. Other observations

1. **`app-init --target-database-url` is silently ignored.**
   - **Cause:** `migrations_app/env.py` overwrites `sqlalchemy.url` with
     `get_settings().app_database_url`.
   - **What happened here:** running it against the new DB actually upgraded the dev DB
     `market_documents_app` from `app_0013` to `app_0014`. That is additive, the existing
     publications still resolve, and the `app_readonly` grants survived. The dev DB remains at
     `app_0014`.
   - **Workaround used:** setting `APP_DATABASE_URL` for the command.
   - **Cutover risk:** this is a real hazard for the fresh-Neon cutover, because the flag looks
     like it targets Neon when it doesn't. Fix it before cutover prep, or always set
     `APP_DATABASE_URL` explicitly.
2. **Local databases created by this track:** `market_documents_app_7f9`, holding the publications
   `7f9-baseline-1` (superseded) and `7f9-local-1` (active). The dev DB was not repointed.

## 18. Production-readiness caveats

1. The signal-artifact identity duplicates a generation on every signal re-run (Section 11). There
   is no effect at a fresh cutover. It needs cleanup+GC discipline or re-keying afterwards.
2. QA vector search through the COALESCE view cannot use HNSW (Section 13). Acceptable now, but it
   scales linearly.
3. The KP2 period-end registration conflicts with the document text (Section 16). A manual
   decision is required before cutover.
4. The `app-init --target-database-url` footgun (Section 17).
5. Thresholds remain single-corpus and provisional (7F.8/7F.8a). The uncertainty tab has 1
   finding.
6. Rollout order for the future cutover:
   1. research migration;
   2. `language-build-all`;
   3. app migrations to `app_0015`;
   4. `app_grants.sql`;
   5. publish;
   6. validate;
   7. promote.

## 19. Production discipline

No production changes: no Neon project, no production Neon access, no Vercel deploy, no
production publication promoted, and no cutover started.

## 20. Final verdict — `READY_WITH_CAVEATS`

| Requirement | Status |
|---|---|
| Implementation matches 7F.8/7F.8a | yes (formula parity 0.0 on all fields, all pairs) |
| Exact anchor cases pass | yes (13/13) |
| Research vs runtime values match | yes (max abs diff 0.000e+00) |
| Expected findings reproduced | yes (5/5/1/3, exact order; disabled types absent) |
| Artifact behaviour understood | yes: measured, content-verified, pinned by a test |
| Python/frontend regressions green | yes |
| lint / tsc / build green | yes |
| Shared-artifact benchmark completed | yes, with one material finding (QA vector search) |
| No unexplained storage growth | growth fully explained; ≈ 19.7 MB is avoidable duplication by design |

The methodology implementation itself is complete and exact. The caveats all concern
shared-artifact behaviour discovered while qualifying this release (signal-identity duplication,
QA-vector index use), plus the KP2 manual decision. They define the cutover-prep checklist; none
of them calls the metric implementation into question.

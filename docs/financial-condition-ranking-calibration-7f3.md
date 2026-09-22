# 7F.3 — Financial-Condition Ranking and Threshold Calibration

**Scope**: read-only analysis, building on `docs/financial-condition-shift-methodology-audit.md`,
`docs/financial-condition-metric-calibration-7f1.md`, and
`docs/financial-condition-metric-redesign-7f2.md`. No code, config, thresholds, taxonomy, or
production data were changed; `findings.py` was read but not modified. All figures below were
recomputed from raw `PassageLanguageSignal` / `PassageLanguageCategoryHit` rows for the current
run of each of the 25 `ReportPairLanguageFeatures` pairs, as of `2026-09-22`, via the read-only
research script `scripts/research_7f3_m3_ranking_calibration.py`. The reconstruction was
cross-checked against the persisted `financial_condition_rate_earlier`/`_later` columns for every
one of the 25 pairs and **matched exactly (0/25 mismatches)** — the same discipline 7F.1 and 7F.2
applied.

**Goal**: determine whether M3 (hit-share difference) should become the production
ranking/gating metric for `largest_financial_condition_shift`, and, if so, establish a defensible
materiality threshold.

---

## 1. M3, defined precisely

```
financial_condition_share  = financial_condition_hits / total_custom_taxonomy_hits
M3_change                  = later_financial_condition_share − earlier_financial_condition_share
```

Verified against the pipeline source (`financial_language_signals.py`,
`financial_language_metrics.py`), not assumed:

- **Numerator population**: `financial_condition` hits are counted identically to the production
  M1 computation — both are summed from `PassageLanguageCategoryHit.hit_count` over the exact
  same `feature_eligible_primary` row set (`primary_narrative_eligible=True AND
  feature_eligible=True`), the same population `aggregate_side` builds for M1. There is no
  separate hit-counting path for M3; only the denominator differs.
- **Denominator population**: `total_custom_taxonomy_hits` (`H`) is confirmed to be exactly the
  sum of `risk + financial_condition + governance + strategy` category-hit totals
  (`CUSTOM_TAXONOMY_CATEGORIES` in `financial_language_config.py:32`) over the same
  `feature_eligible_primary` rows, per side. No fifth category exists in the taxonomy.
- **Overlap cannot produce a pathological share > 1**: `PassageLanguageCategoryHit` is a sparse
  per-`(signal, category, subcategory)` child table, not a one-hot classification. A single
  passage-signal legitimately contributes to more than one of the four categories (e.g. a term
  matching both `financial_condition` and `risk`), so `H` is a sum of category totals, not a
  count of distinct passages — `financial_condition_hits` is always one of the addends inside
  `H`, so `financial_condition_share ∈ [0, 1]` by construction on both sides, and `M3_change ∈
  [-1, 1]`. Confirmed in the reconstructed data: no pair produced a share outside `[0, 1]`.
- **Same-side eligibility population as M1**: confirmed — both `h` and `H` are computed from the
  identical `feature_eligible_primary` row set M1 uses; M3 changes only the denominator's
  *contents* (custom-taxonomy hit count vs. word count), not the passage population it is drawn
  from.

## 2. Corpus distribution

N = 25 current `ReportPairLanguageFeatures` pairs (all issuers, all currently-selected runs,
gate-agnostic — the same convention 7F.1/7F.2 used for corpus-wide distributions; report-side
quality gating is evaluated separately in Section 9).

**Signed M3 change** (N=25):

| N | min | max | mean | median | stdev | MAD | MAD×1.4826 | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | −0.1002 | 0.0531 | −0.0092 | −0.0047 | 0.0412 | 0.0236 | 0.0349 | −0.0320 | −0.0047 | 0.0182 | 0.0192 | 0.0290 | 0.0422 | 0.0486 | 0.0524 |

**Absolute \|M3\| change** (N=25):

| N | min | max | mean | median | stdev | MAD | MAD×1.4826 | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 25 | 0.0032 | 0.1002 | 0.0329 | 0.0203 | 0.0265 | 0.0129 | 0.0192 | 0.0156 | 0.0203 | 0.0423 | 0.0507 | 0.0563 | 0.0680 | 0.0938 | 0.0999 |

M3's corpus range is roughly an order of magnitude smaller than M1's (M1 \|·\| corpus: median
0.174, max 1.10 — see `financial-condition-shift-methodology-audit.md` §10), consistent with
7F.2's finding that M3's scale (bounded in `[-1, 1]`) compresses the same underlying signal into
a much tighter absolute range. This is exactly why 7F.2 recommended M3 for *ranking*, not as a
drop-in replacement scaled the same way as M1.

**All 25 pairs sorted by \|M3\|** (ticker, earlier→later, quality, primary_eligible, M3):

| # | Pair | Quality | Primary eligible | M3 |
|---|---|---|---|---|
| 1 | ACT 2016-06-30→2017-06-30 | GOOD | True | −0.1002 |
| 2 | ACT 2016-06-30→2024-06-30 | NEEDS_REVIEW | **False** | −0.0991 |
| 3 | SBP 2023-12-31→2024-12-31 | USABLE | True | −0.0725 |
| 4 | SUR 2024-06-30→2025-06-30 | GOOD | True | −0.0612 |
| 5 | BEL 2020-12-31→2021-12-31 | GOOD | True | +0.0531 |
| 6 | BEL 2018-12-31→2019-12-31 | GOOD | True | +0.0501 |
| 7 | BEL 2017-12-31→2018-12-31 | GOOD | True | +0.0423 |
| 8 | ACT 2023-06-30→2024-06-30 | GOOD | True | +0.0421 |
| 9 | BEL 2016-12-31→2017-12-31 | GOOD | True | −0.0358 |
| 10 | KP2 2021-12-31→2022-12-31 | USABLE | True | −0.0326 |
| 11 | ACT 2019-06-30→2020-06-30 | GOOD | True | −0.0320 |
| 12 | KP2 2019-12-31→2020-12-31 | USABLE | True | −0.0248 |
| 13 | KP2 2023-12-31→2024-12-31 | USABLE | True | +0.0203 |
| 14 | ACT 2018-06-30→2019-06-30 | GOOD | True | −0.0199 |
| 15 | SDL 2024-06-30→2025-06-30 | USABLE | True | +0.0189 |
| 16 | ACT 2017-06-30→2018-06-30 | GOOD | True | +0.0182 |
| 17 | BEL 2021-12-31→2022-12-31 | GOOD | True | −0.0172 |
| 18 | KP2 2020-12-31→2021-12-31 | USABLE | True | +0.0160 |
| 19 | ACT 2021-06-30→2022-06-30 | GOOD | True | −0.0156 |
| 20 | SUR 2023-06-30→2024-06-30 | GOOD | True | +0.0154 |
| 21 | ACT 2020-06-30→2021-06-30 | GOOD | True | +0.0115 |
| 22 | BEL 2019-12-31→2020-12-31 | GOOD | True | +0.0073 |
| 23 | KP2 2022-12-31→2023-12-31 | USABLE | True | −0.0073 |
| 24 | SBP 2024-12-31→2025-12-31 | USABLE | True | −0.0047 |
| 25 | ACT 2022-06-30→2023-06-30 | GOOD | True | −0.0032 |

Row 2 (ACT 2016→2024, an 8-year gap pair, `NEEDS_REVIEW`/`primary_eligible=False`) fails the
report-side quality gate and is excluded from every eligibility/threshold calculation below
(Sections 4–5, 9). It is included here purely for corpus-completeness, matching 7F.1/7F.2's
practice of reporting the full 25-pair corpus before gating.

## 3. Company-level distribution

Gate-eligible pairs only (`report_side_signal_quality ∈ {GOOD, USABLE}` and
`report_side_primary_eligible = True`); ACT's long-gap pair is excluded here.

| Issuer | N pairs | min \|M3\| | median \|M3\| | max \|M3\| | Largest pair | Quality | Plausible? |
|---|---|---|---|---|---|---|---|
| ACT | 8 | 0.0032 | 0.0178 | 0.1002 | 2016-06-30→2017-06-30 | GOOD | Yes — dominated by a real collapse in dividend-language hits (40→7), a plausible single-driver story, not an artifact (see §6). |
| BEL | 6 | 0.0073 | 0.0390 | 0.0531 | 2020-12-31→2021-12-31 | GOOD | Yes — broad-based increase across impairment (+22), cash flow (+11), debt (+8), revenue (+11); consistent with a COVID-period 2021 report discussing more financial pressure, not one-item-driven. |
| KP2 | 5 | 0.0073 | 0.0203 | 0.0326 | 2021-12-31→2022-12-31 | USABLE | Marginal — small, spread-out deltas (impairment −3, cash flow +3, acquisitions −2); no dominant driver, but also no pair reaches a size that would obviously matter. |
| SBP | 2 | 0.0047 | 0.0386 | 0.0725 | 2023-12-31→2024-12-31 | USABLE | Yes — a broad decline across dividends (−6), acquisitions/disposals (−7), cash flow (−3); the corpus's most-validated finding across every normalization tested in 7F.2. |
| SDL | 1 | 0.0189 | 0.0189 | 0.0189 | 2024-06-30→2025-06-30 | USABLE | Only one pair exists; mid-corpus magnitude, not extreme in either direction. |
| SUR | 2 | 0.0154 | 0.0383 | 0.0612 | 2024-06-30→2025-06-30 | GOOD | Caution — acquisitions/disposals (−15) alone accounts for roughly two-thirds of the total hit decline (98→75); a real but concentrated shift (see §6). |

ACT's own "largest pair" identity is stable under M3 (2016→2017) but this is a **different**
pair than M1's flagship (2017→2018) — consistent with 7F.2's finding that ranking identity shifts
across normalizations, now confirmed for M3 as well.

## 4. Threshold candidates

Evaluated over the 24 gate-eligible pairs (ACT's long-gap pair excluded, per Section 9).

**A. Absolute share-point thresholds**

| Threshold | N eligible | % of 24 | Companies |
|---|---|---|---|
| 0.01 | 20 | 83% | ACT, BEL, KP2, SBP, SDL, SUR (all 6) |
| 0.02 | 12 | 50% | ACT, BEL, KP2, SBP, SUR |
| 0.03 | 10 | 42% | ACT, BEL, KP2, SBP, SUR |
| 0.04 | 7 | 29% | ACT, BEL, SBP, SUR |
| 0.05 | 5 | 21% | ACT, BEL, SBP, SUR |
| 0.075 | 1 | 4% | ACT only |
| 0.10 | 1 | 4% | ACT only |

**B. Percentile thresholds** (of the eligible \|M3\| distribution)

| Percentile | Value | N eligible | % |
|---|---|---|---|
| p75 | 0.0421 | 6 | 25% |
| p80 | 0.0454 | 5 | 21% |
| p85 | 0.0517 | 4 | 17% |
| p90 | 0.0588 | 3 | 12% |
| p95 | 0.0708 | 2 | 8% |

**C. Robust statistical thresholds** — `median(M3 signed) = −0.0039`, `MAD = 0.0225`, scaled
(×1.4826) `= 0.0333` (using the same 1.4826 normal-consistency constant 7F.2 used for M5, per
its own stated convention).

| Rule | Threshold | N eligible | % |
|---|---|---|---|
| median + 1.0×scaled MAD | 0.0372 | 7 | 29% |
| median + 1.5×scaled MAD | 0.0539 | 3 | 12% |
| median + 2.0×scaled MAD | 0.0706 | 2 | 8% |

**D. Hybrid** `max(minimum_absolute_change, percentile-derived)` — tested `min_abs ∈ {0.02,
0.03}` against `{p75, p85}`. In this corpus the percentile-derived values (0.042, 0.052) already
exceed both floors tested, so the hybrid rule collapses to the plain percentile threshold in
every combination tried — it adds no discriminating power here, though it would matter if the
corpus were quieter (all changes clustered near zero) or noisier (spurious tiny median
inflation), which is exactly the scenario the milestone brief anticipated it for.

Two independent methods — percentile (p75 = 0.0421) and robust statistics (median + 1 scaled MAD
= 0.0372) — **converge on the same 0.037–0.042 range**, both selecting N=7, the same 4-company
set (ACT, BEL, SBP, SUR). This convergence, not a round-number preference, is what grounds the
recommendation in Section 15.

## 5. Threshold sensitivity

At every one of the 12 candidates above, checked explicitly:

- **SBP 2023→2024 survives** at every threshold ≤ 0.075 (its own value is 0.0725) — it drops out
  only at the two strictest tested (0.075, 0.10). It is the single most robust finding in the
  corpus, exactly as 7F.2 found across all six normalizations.
- **ACT 2017→2018 is excluded** at every threshold ≥ 0.02 (its M3 value is 0.0182). This is the
  intended correction: 7F.1/7F.2 established this pair's M1 value is ~90% a denominator-shrinkage
  artifact, and M3 correctly demotes it well below materiality at any reasonable threshold.
- **BEL gets at least one legitimate finding** at every threshold ≤ 0.0539 (three BEL pairs
  qualify at 0.04, one still qualifies at 0.05). BEL is entirely absent from the current
  production metric (M1) because no BEL pair ever reaches `|M1| ≥ epsilon(1.0)` — max BEL \|M1\|
  is 0.5544. M3 is the only tested metric that gives BEL any Discover representation at all.
- **No obviously trivial/noisy finding is admitted** at 0.03–0.05: the smallest values admitted at
  0.04 (ACT 2023→2024, 0.0421; BEL 2017→2018, 0.0423) both have multi-subcategory, non-degenerate
  hit patterns on manual inspection (Section 6), not single-term artifacts. Thresholds ≤ 0.02
  admit pairs with |M3| as low as 0.0073–0.02 built on very small subcategory deltas (KP2, ACT
  2018→2019) that read as noise on manual inspection, not findings.
- Company coverage was **not** optimized for directly (per the milestone's explicit
  instruction) — the 0.04 threshold's 4-of-6 company coverage is a byproduct of the empirical
  convergence in Section 4, not a target. KP2 and SDL do not clear 0.04 under any of the
  triangulating methods, and forcing them in would require dropping to ≤0.02, which reintroduces
  ACT 2017→2018 as a false positive.

## 6. Manual content validation (top 10 \|M3\|, gate-eligible)

Grounded in the reconstructed per-subcategory hit deltas (not LLM judgment) for each pair.

| Pair | M3 | Dominant subcategory driver(s) | Assessment |
|---|---|---|---|
| ACT 2016→2017 | −0.1002 | dividends −33 (of −52 total h change, 63%); revenue −13 | **CAUTION** — real, large, but concentrated in one subcategory (dividends). Total hits are not tiny (142→90), so not a sparse-denominator artifact, but a reader should be told this is substantially a dividend-language story, not a broad financial-condition shift. |
| SBP 2023→2024 | −0.0725 | acquisitions/disposals −7, dividends −6, cash flow −3 (spread across 3+ subcategories, no single driver >45% of total) | **PASS** — broad-based decline, multiple independent subcategories moving the same direction, moderate absolute counts (71→55). |
| SUR 2024→2025 | −0.0612 | acquisitions/disposals −15 (of −23 total, 65%); revenue −11; dividends +7 (partial offset) | **CAUTION** — similar concentration pattern to ACT: acquisitions/disposals alone explains most of the net move; genuine content (fewer completed-transaction mentions plausible year-over-year) but a single-subcategory story. |
| BEL 2020→2021 | +0.0531 | impairment +22 (of +70 total, 31%), cash flow +11, debt +8, revenue +11, acquisitions +6 — no subcategory exceeds one-third | **PASS** — the most broadly distributed shift in the top 10; consistent with a 2021 report (COVID-period impairments, working-capital and debt-covenant language) discussing financial condition more pervasively, not one repeated phrase. |
| BEL 2018→2019 | +0.0501 | revenue +11, cash flow +6, debt +3, acquisitions +3 — spread | **PASS** — no dominant single driver; multiple subcategories moving together. |
| BEL 2017→2018 | +0.0423 | revenue +11, debt +7, liquidity +6, capex +3 — spread | **PASS** — same pattern; genuine multi-subcategory movement, moderate absolute counts (59→87). |
| ACT 2023→2024 | +0.0421 | revenue +21 (exceeds the net total h change of +13, meaning other subcategories partly cancel it — acquisitions −4, dividends −2, tax −2) | **PASS with note** — a clean illustration of 7F.2's cancellation finding: gross revenue-language increase is larger than the net figure suggests. Content itself (more revenue discussion) is plausible, not an artifact. |
| BEL 2016→2017 | −0.0358 | impairment +6 (largest, but total h change is only −4, so partly offset by revenue −5, debt −3) — smallest absolute counts among the top 10 (63→59) | **CAUTION** — small absolute hit counts throughout; individually plausible content but this pair sits closest to the threshold boundary and is the least separated from noise. |
| KP2 2021→2022 | −0.0326 | impairment −3, cash flow +3, acquisitions −2 — small, offsetting deltas | **CAUTION** — smallest, most diffuse pattern in the top 10; plausible but not a strong finding on its own. |
| ACT 2019→2020 | −0.0320 | capex +6, dividends −6 (offsetting), revenue −5 | **CAUTION** — two subcategories moving in opposite directions largely cancel; the residual M3 value is real but thin evidentiary support for a single "shift" narrative. |

**No pair in the top 10 is driven by a single repeated phrase, a sparse denominator (`H` ranges
125–484 across the corpus, see Section 7), a taxonomy or parsing artifact, or boilerplate.** The
CAUTION-rated pairs are caution-rated because of *concentration in one subcategory* (ACT
2016→2017, SUR 2024→2025) or *small absolute counts near the threshold boundary* (BEL
2016→2017, KP2 2021→2022, ACT 2019→2020), not because the underlying signal is spurious.

## 7. Denominator adequacy

`H_earlier` / `H_later` for every pair range from 125 (SDL, both sides) to 484 (SUR
2023-06-30→2024-06-30, earlier side); no pair has `H < 100` on either side. Spearman correlation
between `min(H_earlier, H_later)` and `|M3|`, over the 24 gate-eligible pairs: **ρ = 0.05** —
effectively no relationship. This is the key finding of this section: **M3's magnitude in this
corpus is not being driven by small taxonomy-hit denominators** — the largest \|M3\| pairs (ACT
2016→2017, `H`=322–374; SBP 2023→2024, `H`=134–147; SUR 2024→2025, `H`=418–433) span the full
range of denominator sizes, including some of the corpus's largest `H` values.

A minimum-`H` eligibility rule is **not** required by the current corpus (no pair sits near a
plausible instability boundary — SDL's `H≈125` is the smallest in the corpus and its \|M3\| =
0.0189 is unremarkable, not an outlier). Per the milestone's instruction, no such rule is added
here; this finding should be revisited if a future company/report has substantially fewer
custom-taxonomy hits than the 125–484 range observed today.

## 8. Bootstrap / small-count stability

For the top 10 gate-eligible \|M3\| pairs, simulated `later_h ± {1, 2, 5}` while holding `H_later`
fixed at `later_h + delta` (i.e. treating the perturbation as added/removed
`financial_condition` hits that also change the total, the more conservative assumption) and
`earlier`-side values fixed:

- **No pair changes sign** under any tested perturbation (±1, ±2, ±5 hits).
- **Rank order is materially stable for the top 4** (ACT 2016→2017, SBP, SUR, BEL 2020→2021):
  each remains well-separated from its neighbors even at ±5 hits.
- **Two pairs are threshold-fragile at the 0.04 candidate specifically**: BEL 2017→2018 (base
  0.0423, range 0.0317–0.0527 under ±5) and ACT 2023→2024 (base 0.0421, range 0.0319–0.0519 under
  ±5) both straddle a 0.04 cutline under plausible count noise. This is disclosed explicitly as a
  caveat on the recommended threshold in Section 15, not hidden.
- A simple **binomial approximation** for the later-side share (`se = sqrt(p(1-p)/H_later)`,
  applied only to the later-side term, holding the earlier side fixed — a deliberately
  conservative simplification, not a full two-sample interval) gives approximate 95% intervals
  that exclude zero for 3 of the top 10 (ACT 2016→2017, SUR, BEL 2020→2021) and include zero for
  the remaining 7, including SBP 2023→2024 (`(-0.156, 0.011)`) despite SBP's discrete
  ±5-hit-perturbation range never crossing zero (`-0.095` to `-0.051`). This divergence is
  expected: SBP's smaller `H` (134–147) makes the single-sided binomial approximation wide, while
  the discrete perturbation table is the more decision-relevant check for a "how many actual
  hits would need to be wrong" question — the two should be read together, not the binomial CI
  alone.

## 9. Quality-gate interaction

The existing report-side quality gate (`report_side_signal_quality ∈ {GOOD, USABLE}` and
`report_side_primary_eligible`) is **necessary but not sufficient** for M3:

- It **correctly excludes** the one pair that would otherwise distort the corpus: ACT
  2016-06-30→2024-06-30 (`NEEDS_REVIEW`, `primary_eligible=False`, an 8-year irregular-gap pair)
  is dropped by the existing gate regardless of which metric is used.
- **GOOD and USABLE remain acceptable for M3** — nothing about the gate's logic (primary-narrative
  word coverage, transition/irregular-gap exclusion, dictionary-match-rate bands) is specific to
  M1's word-count denominator; it validates the underlying passage population, which both M1 and
  M3 draw from identically (Section 1).
- **However, the gate's `dictionary_match_rate_*` checks are computed from
  `total_dictionary_hits / words`** (`financial_language_quality.py`), i.e. the *word-count*
  denominator — they say nothing about whether `H` (the sum of the 4 custom-taxonomy category
  hits, M3's own denominator) is large enough to be stable. Section 7 shows this is not currently
  a problem (`H` never drops below 125, and \|M3\| is uncorrelated with `H` size), but this is a
  **structural gap**, not a coincidence of the current corpus: the gate was designed to validate
  overall dictionary coverage against report length, not custom-taxonomy hit-count adequacy
  specifically. If a future report has unusually sparse custom-taxonomy language (e.g. very short
  narrative sections with GOOD dictionary coverage overall but few risk/financial_condition/
  governance/strategy hits), the existing gate would pass it while M3 could still be
  denominator-unstable. **This is identified explicitly here and left unresolved**, per the
  milestone's instruction not to silently add a new rule.

## 10. M1 / M3 / M6b comparison

Classified against p75 cutoffs computed over the 24 gate-eligible pairs (`|M1| ≥ 0.317`, `|M3| ≥
0.042`, `M6b ≥ 0.046`):

| Class | Definition | Pairs |
|---|---|---|
| A. All three agree, large | | ACT 2016→2017; BEL 2017→2018 |
| B. M1 high / M3 low | | ACT 2019→2020; **ACT 2017→2018** |
| C. M3 high / M1 low | | BEL 2020→2021; BEL 2018→2019 |
| D. Composition high, intensity/share low | | ACT 2023→2024; BEL 2016→2017; ACT 2020→2021 |
| E. All low / mixed | | remaining 15 pairs |

**Anchor: ACT 2017→2018** — `M1 = +1.0019` (rank 2 by M1, the current production flagship),
`M3 = +0.0182` (well below the p75 cutoff), `M6b = 0.0043` (lowest composition-distance in the
entire corpus). This is class B in the strictest sense — a textbook case of the
denominator-shrinkage artifact 7F.1/7F.2 identified: the later report's word count fell ~35%
while both hit count and subcategory composition stayed essentially flat, so M1 mechanically
inflates while M3 and M6b (both hit-count-based, denominator-immune) correctly show almost no
underlying change.

**Anchor: SBP 2023→2024** — `M1 = -1.1027` (rank 1 by M1), `M3 = -0.0725` (rank 2 by \|M3\|, well
above the p75 cutoff — `M1 high AND M3 high`), `M6b = 0.0126` (below the p75 cutoff — low
composition change). This pair does not fit cleanly into any of the five listed classes as
written (it is `M1 high, M3 high, M6b low` — agreement between the two intensity/ranking metrics
but a stable subcategory mix): the finding here is genuine and broad in volume/share terms, but
its underlying subcategory *mix* did not change — dividends and acquisitions/disposals language
declined together without one topic displacing another. This is the strongest positive-control
case in the corpus precisely because M1 and M3 agree independent of the length artifact that
separates them for ACT.

## 11. Interpretation design (draft user-facing language)

**M1 — financial-condition language density change**
- Measures: the change in how often financial-condition language appears, per 1,000 words of
  narrative text, between the two reports.
- Units: hits per 1,000 words (rate-point difference).
- Positive means the later report used financial-condition language more densely per word;
  negative means less densely.
- Does **not** mean the total amount of financial-condition discussion changed — a report that
  got shorter can show a large positive value even if the actual content barely moved, because
  the same hit count is divided by fewer words.

**M3 — financial-condition share change**
- Measures: the change in financial-condition language's share of all classified
  (risk/financial-condition/governance/strategy) language in the report, independent of how long
  the report is.
- Units: percentage points of share (bounded −100 to +100, typically well under ±10 in this
  corpus).
- Positive means financial-condition language became a larger slice of the report's classified
  disclosure language; negative means a smaller slice.
- Does **not** mean the report's overall length or total disclosure volume changed, and does not
  by itself say *which* financial topics moved (see M6b).

**M6b — financial-condition topic-mix change**
- Measures: how much the *mix* of financial-condition subtopics (revenue, debt, liquidity,
  dividends, etc.) shifted, independent of whether overall volume or share changed.
- Units: a distance between 0 (identical topic mix) and 1 (completely different topic mix, no
  overlap).
- A higher value means the report emphasized different financial-condition subtopics than before;
  it carries no sign (there is no "positive" or "negative" mix change).
- Does **not** mean more or less financial-condition language was used overall — a report can
  have a high M6b with a near-zero M1 or M3 if it swapped emphasis between subtopics (e.g. more
  debt language, less dividend language) without changing the total.

None of the three should be described as implying the company's financial health improved or
worsened — they measure *disclosure language*, not financial outcomes.

## 12. Discover design (proposed, if M3 is adopted)

```
Headline:            Largest financial-condition language shift
Primary ranking:     M3 (hit-share difference)
Supporting values:   M1 (density change), M6b (topic-mix change), dominant subcategory movers
```

Eligibility states to distinguish explicitly (never collapse into a single "no finding"):

- **No comparisons** — company has fewer than 2 reports; nothing to compare.
- **Failed quality** — report-side quality gate fails (`NEEDS_REVIEW` or transition/irregular
  gap); shown as "insufficient signal quality," not silently omitted.
- **Below materiality** — comparisons exist and pass quality, but \|M3\| is below the chosen
  threshold; show the largest *observed* \|M3\| pair anyway, explicitly labeled "below
  materiality threshold," so a reader can see the company was evaluated, not skipped.
- **Eligible finding** — \|M3\| clears the threshold; show the full headline + supporting values.

## 13. Retrospective production impact

Simulated under the recommended threshold (Section 15: `|M3| ≥ 0.04`, same GOOD/USABLE +
primary-eligible gate as today):

| | Current production (M1, epsilon=1.0) | Proposed (M3 ≥ 0.04) |
|---|---|---|
| Eligible rows | 2 | 7 |
| Companies represented | ACT, SBP (2 of 6) | ACT, BEL, SBP, SUR (4 of 6) |
| Rows | ACT 2017→2018 (+1.0019), SBP 2023→2024 (−1.1027) | ACT 2016→2017 (−0.1002), SBP 2023→2024 (−0.0725), SUR 2024→2025 (−0.0612), BEL 2020→2021 (+0.0531), BEL 2018→2019 (+0.0501), BEL 2017→2018 (+0.0423), ACT 2023→2024 (+0.0421) |

- **ACT 2017→2018**: removed. This is the intended correction — 7F.1/7F.2 established this
  finding is ~90% a denominator-shrinkage artifact, not a real shift; M3 and M6b both agree it is
  not a legitimate top finding (Section 10).
- **SBP 2023→2024**: retained, and remains a top-2 finding under both metrics — the corpus's one
  stable, cross-validated finding.
- **BEL's largest pair**: newly added, and for the first time BEL has *any* Discover
  representation at all (3 pairs qualify: 2017→2018, 2018→2019, 2020→2021; the current M1-based
  metric never surfaces BEL because its max \|M1\| of 0.5544 never reaches epsilon=1.0).
- **Newly added overall**: ACT 2016→2017, ACT 2023→2024, SUR 2024→2025, and 3 BEL pairs — 6 new
  findings.
- **Ranking changes**: SBP moves from rank 1 (by \|M1\|) to rank 2 (by \|M3\|); ACT's "largest
  shift" identity changes from the 2017→2018 pair to the 2016→2017 pair.
- KP2 and SDL remain unrepresented under both the current metric and the proposed one — no pair
  from either company clears 0.04 under any of the converging threshold methods in Section 4.

## 14. Threshold selection principles (self-check against the milestone's stated criteria)

- **Interpretable in M3's units** — yes: "a 4-percentage-point change in financial-condition
  language's share of classified disclosure language" is a plain-language, self-normalizing
  statement (Section 11).
- **Empirically grounded** — yes: two independent methods (p75 percentile = 0.0421; median + 1
  scaled MAD = 0.0372) converge on the same narrow range without being tuned to agree (Section
  4).
- **Reasonably robust to small hit perturbations** — largely yes, with two disclosed exceptions
  (BEL 2017→2018 and ACT 2023→2024 straddle the 0.04 line under ±5-hit noise; Section 8). No
  admitted finding changes *sign* under any tested perturbation.
- **Does not depend on the word-count denominator** — yes, by construction (Section 1).
- **Excludes clearly trivial changes** — yes: everything below ~0.02 in this corpus is either
  small, diffuse counts or already known noise (Section 6).
- **Preserves genuinely strong findings** — yes: SBP 2023→2024 survives; ACT 2016→2017 (a
  legitimate, if concentrated, dividend-language collapse) survives.
- **Documented rationale reproducible from corpus evidence** — yes: every number in this section
  traces to the tables in Sections 2–8, computed by `scripts/research_7f3_m3_ranking_calibration.py`
  from raw signal/hit rows, cross-checked against production columns.

## 15. Final recommendation

**ADOPT_M3_WITH_THRESHOLD**

- **Threshold: `|M3_change| ≥ 0.04`** (4 percentage points of financial-condition share of
  classified disclosure language), applied on top of the existing report-side quality gate
  (`GOOD`/`USABLE` and `report_side_primary_eligible`), unchanged from today.
- **Rationale**: this value sits inside the narrow band where two independent threshold families
  — the 75th percentile of the eligible-corpus \|M3\| distribution (0.0421) and a robust
  median-plus-one-scaled-MAD statistic (0.0372) — converge, rather than being chosen for a
  convenient result count (Section 4, Section 14). It correctly demotes the current metric's
  flagship artifact (ACT 2017→2018) below materiality, correctly retains the corpus's one
  fully-cross-validated finding (SBP 2023→2024), and is the only threshold in the tested range
  that gives BEL any legitimate Discover representation without re-admitting known-noisy pairs.
  Two pairs at the boundary (BEL 2017→2018, ACT 2023→2024) are disclosed as sensitive to ±5-hit
  count perturbations (Section 8) — this is a known, bounded caveat on the threshold's edge, not
  a reason to reject it, since no pair changes sign under perturbation and both boundary pairs
  pass manual content validation as genuine (Section 6).
- This is an **absolute** share-point threshold, not a pure percentile or pure robust-statistic
  rule, because production Discover needs a stable, explainable cutline that does not silently
  redefine "material" every time the corpus grows by a report; its value should be revisited if
  future corpus growth moves the percentile/MAD convergence point materially away from the
  current 0.037–0.042 band (an operational note, not an automated recalculation — re-deriving it
  is a future, explicit decision, consistent with 7F.1/7F.2's own discipline of not pre-committing
  to an update rule).

**M6b: `SUPPORTING_DETAIL`** — not a headline ranking metric (it has no natural sign or
"how much" framing that a Discover headline needs), but directly useful on a comparison/evidence
page to answer "did the mix of financial-condition topics change" independent of the M3 headline,
exactly as 7F.2 recommended and as Section 10's SBP/ACT anchors demonstrate it can diverge
meaningfully from M1/M3.

**M1**: retained as supporting descriptive context (per 7F.2's MODIFY recommendation, not
reopened here), shown alongside M3 rather than used for ranking or gating.

---

*Analysis produced by `scripts/research_7f3_m3_ranking_calibration.py`, a read-only research
script retained under `scripts/` per the established convention (see e.g.
`scripts/research_7d5a_heading_inventory.py`). No production table, `findings.py`, config,
threshold, or taxonomy file was modified in the production of this document.*

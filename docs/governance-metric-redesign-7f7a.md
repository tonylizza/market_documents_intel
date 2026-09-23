# 7F.7a — Governance-Language Metric Redesign

**Scope**: read-only methodology analysis. No code, configuration, threshold, taxonomy,
migration, or production data was changed to produce this document (the single exception,
performed alongside this milestone per its explicit instruction, is a wording-only correction
to `docs/discover-metric-methodology-audit-7f6.md`'s `net_tone_change` classification — see
Section 16). `findings.py` was read but not modified. All figures below were computed from raw
`PassageLanguageSignal` / `PassageLanguageCategoryHit` rows for the current run of each of the
25 `ReportPairLanguageFeatures` pairs (same "current run" selection rule as 7F.1–7F.6, via
`get_current_language_signal_runs_by_pair`), as of `2026-09-23`, using the read-only research
script `scripts/research_7f7a_governance_metric_redesign.py`. The governance-rate reconstruction
was cross-checked against the persisted `governance_rate_earlier`/`_later` columns for every one
of the 25 pairs and **matched exactly (0/25 mismatches)** — the same discipline 7F.1, 7F.2, 7F.3,
and 7F.6 applied.

**Trigger**: 7F.6 §16 proved `governance_language_change` (the current production metric,
referred to here as **M1-G**) reproduces the same word-count-denominator-shrinkage artifact
already diagnosed and fixed for the old financial-condition metric (M1), on two of its four
current Discover-eligible findings: ACT 2017-06-30→2018-06-30 (actual `+1.736`, length-controlled
`+0.413`, 24% survives) and BEL 2018-12-31→2019-12-31 (actual `-1.070`, length-controlled
`-0.158`, 15% survives). 7F.6 gave governance the verdict `MODIFY_METRIC_AND_THRESHOLD` and
proposed this milestone as the direct next step, mirroring 7F.2+7F.3's combined scope for
financial condition (M1→M3 redesign + threshold calibration) but for governance, and read-only.

**Goal**: determine whether governance should adopt a share-based metric analogous to
financial-condition's M3, what its denominator should be, whether M1-G should remain supporting
context, whether subcategory composition should be exposed, what threshold to use, and how
Discover rankings would change. **No production change is made here.**

---

## 1. Executive summary

This analysis finds a genuine methodological improvement (a share-based governance metric,
**M3-G**, that is structurally immune to the word-count-denominator artifact M1-G suffers from)
but **not** the same outcome the financial-condition precedent (7F.2/7F.3) produced. That
precedent's flagship result was that M3 *demoted* financial condition's artifact pair (ACT
2017→2018) from a top-2 finding to an unremarkable one, because that pair's financial-condition
hit count was essentially flat (90→89) and its subcategory composition was the *most stable* in
the entire corpus — the whole apparent "shift" was arithmetic, driven purely by a shrinking
word-count denominator.

**Governance's two flagged pairs do not reproduce that pattern.** Reconstructing every
governance hit and every custom-taxonomy hit directly from the database:

- **ACT 2017→2018**: governance hits rose 96→115 (+19.8%) while *total* custom-taxonomy hits
  (risk + financial_condition + governance + strategy) *fell* 322→299 (-7.1%) over the same
  period. Governance's share of all classified language therefore rose from 29.8% to 38.5%
  (`M3-G = +0.0865`) — the **3rd-largest share movement in the entire 25-pair corpus**, driven
  by broad gains across `board` (+10), `regulatory_compliance` (+9), and `remuneration` (+5).
  This is not the "flat hits / shrinking words" pattern that made the financial-condition
  analogue a pure artifact — governance hits genuinely grew here, in absolute terms and in share,
  even as the underlying report shrank.
- **BEL 2018→2019**: governance hits held nearly flat (171→165, -3.5%) while total
  custom-taxonomy hits *grew* (360→401, +11.4%) — governance's share fell from 47.5% to 41.1%
  (`M3-G = -0.0635`), the **4th-largest share movement in the corpus**. This *is* consistent with
  a genuine (if smaller-magnitude) relative decline in governance emphasis, not merely a word-count
  artifact.

**Neither pair is demoted below any reasonable M3-G materiality threshold** — both remain in the
corpus's top 4 by `|M3-G|`, the same rank tier as under the current M1-G ranking. This directly
answers the milestone's Section 7 question ("do not assume the answer is yes just because the
formulas are analogous") — **the answer here is no**, and the reason is fully traceable to the
raw hit-count evidence, not a modeling choice. This does **not** overturn 7F.6's core diagnosis
that M1-G's *specific rate-difference formula* is denominator-shrinkage-sensitive — that remains
true and is reconfirmed here (Section 2, Section 5). It does mean 7F.6's characterization of
these two pairs as "FAIL... report-length artifact" (7F.6 §16) needs a more nuanced restatement:
the *inflated magnitude* M1-G reports for them is a length artifact, but the *underlying
direction and rough size* of both pairs' governance-language shift is corroborated by a
denominator-robust metric, not invalidated by it. See Section 16 for the explicit flag on this
point, as the task instructs.

**Recommendation (Section 15 for full detail): `ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD`.**
Formula: `governance_share_change = later_governance_share − earlier_governance_share`, where
`governance_share = governance_hits / (risk + financial_condition + governance + strategy hits)`,
same population as M1-G. Threshold: **`|M3-G| ≥ 0.05`**, converging with both the empirical p75
(`0.0519`) and a robust median+1×scaled-MAD statistic (`0.0588`) over the 24 gate-eligible
pairs. M1-G is retained as supporting descriptive context (density change), not for ranking.
Governance's 9-subcategory taxonomy is sparse in 2 of 9 subcategories (`litigation`,
`shareholder_rights`, together 1.0% of all corpus governance hits) but adequately populated in
the other 7 to support a composition/topic-mix diagnostic (M6-G), recommended as supporting
detail only, mirroring 7F.3's M6b treatment for financial condition.

---

## 2. Current governance formula, defined precisely

```
governance_rate(side) = 1000 * governance_hit_count(side) / feature_eligible_primary_words(side)
governance_language_change = governance_rate(later) - governance_rate(earlier)
```

Source: `custom_category_rate` + `rate_change`, wired at
`financial_language_signals.py:830-832` (`custom_category_rate(later_side, "governance")` minus
`custom_category_rate(earlier_side, "governance")`).

- **Numerator**: `governance` category hit count, summed from `PassageLanguageCategoryHit.hit_count`
  over `feature_eligible_primary` rows on the given side (`aggregate_side`,
  `financial_language_metrics.py:127-143`).
- **Denominator**: `sum(passage_word_count for r in feature_eligible_primary if r.report_side ==
  side)` — the *whole report side's* feature-eligible primary-narrative word count, regardless of
  alignment status (identical population/denominator family 7F.6 §4 documented for
  `net_tone_change`/`uncertainty_intensity_change`).
- **Passage population**: `feature_eligible_primary` — `primary_narrative_eligible=True AND
  feature_eligible=True` (excludes the 6 structured-content categories and Milestone 3's
  low-information floor) — the same population every other Discover metric audited by 7F.6 uses.
- **Quality gate**: `_gate_report_side` → `assess_report_side_quality` (`report_side_quality_ok`
  ∈ {GOOD, USABLE} and `report_side_primary_eligible`), identical gate to `net_tone_change` and
  `uncertainty_intensity_change`.
- **Current epsilon**: `1.0`, unit `rate_per_1000_words`, no direction filter (shared literal
  constant introduced in commit `adc4c3d`, undocumented rationale — 7F.6 §6).
- **Current Discover ranking rule**: `eligible_candidates`/`select_findings`
  (`findings.py:140-171`) — magnitude `= |value| / epsilon`, sorted descending, tie-broken by
  `CANDIDATE_KEY_ORDER`.

**Confirmed structurally identical to the old (pre-7F.4) financial-condition M1**: both are
`rate_change(custom_category_rate(later, cat), custom_category_rate(earlier, cat))`; only `cat`
differs (`"governance"` vs. `"financial_condition"`). This was already established by 7F.6 §16
and is reconfirmed here by direct inspection of `financial_language_signals.py:817-832` — no
part of that wiring has changed since 7F.6.

---

## 3. Candidate formulas

Let `h` = governance hit count, `w` = feature-eligible primary-narrative word count (same
population as M1-G), on one report side. `H` = total custom-taxonomy hits (`risk +
financial_condition + governance + strategy`) on that side. Let `i` index the 9 governance
subcategories (`board, audit, internal_controls, remuneration, ethics,
regulatory_compliance, litigation, shareholder_rights, related_party`).

| # | Name | Formula |
|---|---|---|
| M1-G | Current rate difference (production) | `1000·h_later/w_later − 1000·h_earlier/w_earlier` |
| M2-G | Length-controlled hit change | `1000·h_later/w_earlier − 1000·h_earlier/w_earlier` (later hits re-normalized by the earlier side's word count, holding the denominator fixed — same convention 7F.1/7F.2/7F.6 used) |
| M3-G | Hit-share / compositional change | `(h_later/H_later) − (h_earlier/H_earlier)` |
| M4-G | Log-rate ratio | Not computed as a separate table here — 7F.2 already established (for the structurally identical financial-condition case) that log-rate ratio is a near-rescaling of M1 (ρ=0.985 there) that inherits M1's denominator sensitivity fully; nothing about governance's formula shape differs in a way that would change that conclusion, so this candidate is not independently re-derived (see Section 4 for the explicit non-fabrication note) |
| M5-G | Robust standardized M1-G (threshold-calibration tool only) | `(M1-G − median(M1-G corpus)) / (1.4826 × MAD(M1-G corpus))` — a monotonic transform of M1-G, reported for completeness per the milestone brief, not evaluated as an independent candidate |
| M6-G | Governance subcategory/topic composition change | `1 − cosine(comp_earlier, comp_later)`, where `comp` is the 9-dim vector of each subcategory's *share* of that side's governance hits |

**Verified properties of M3-G** (per the milestone's explicit checklist, Section 3 of the task
spec):

- **Same numerator source as M1-G**: yes — both draw `governance` hit counts from the identical
  `feature_eligible_primary` row set (`custom_category_totals["governance"]`, computed once by
  `aggregate_side`); M3-G's own reconstruction cross-checked exactly against the persisted M1-G
  rate columns (0/25 mismatches).
- **Same passage population**: yes — `H`'s four category totals are summed from the same
  `feature_eligible_primary` rows M1-G uses; only the denominator's *contents* change (hit count
  vs. word count), not the row population.
- **Share bounded in [0,1]**: confirmed — no pair in the reconstructed 25-pair corpus produced a
  share outside `[0,1]` (governance hits are always one addend of the sum `H`, so
  `governance_share ≤ 1` by construction).
- **Change bounded in [-1,1]**: confirmed by construction (difference of two values each in
  `[0,1]`); observed corpus range is `[-0.1093, +0.0993]`, far inside the theoretical bound
  (Section 4).

**M4-G is not independently computed** here (rather than fabricated): the milestone brief allows
this ("only if useful diagnostically"). 7F.2's own finding for the structurally identical
financial-condition case was that log-rate ratio's ranking is nearly indistinguishable from the
raw rate difference (ρ=0.985, identical top-10) because it is derived from the same two
already-denominator-sensitive rates as M1 — it does not fix denominator sensitivity, only
re-expresses it. Since M1-G and M4-G would inherit the identical mathematical relationship
(M4-G is a monotonic-in-spirit transform of the same two rates M1-G uses), running the
computation would not produce new diagnostic value beyond what 7F.2 already established for the
identical formula shape; it is omitted rather than re-derived to fabricate a distinct-looking
number.

---

## 4. Corpus-wide comparison

N = 25 current `ReportPairLanguageFeatures` pairs (gate-agnostic — matches 7F.1–7F.6's own
convention for corpus-wide distributions before gating).

**M1-G signed distribution** (N=25):

| min | max | mean | median | stdev | MAD | MAD×1.4826 | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| -1.0697 | 1.7360 | -0.0340 | -0.0467 | 0.5650 | 0.1633 | 0.2420 | -0.2690 | -0.0467 | 0.0915 | 0.1038 | 0.1276 | 0.2190 | 1.0770 | 1.6263 |

(Reproduces 7F.6 §7's own M1-G distribution exactly, confirming the reconstruction pipeline is
correct before introducing M2-G/M3-G/M6-G.)

**M3-G signed distribution** (N=25):

| min | max | mean | median | stdev | MAD | MAD×1.4826 | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| -0.1093 | 0.0993 | -0.0045 | -0.0132 | 0.0470 | 0.0303 | 0.0449 | -0.0385 | -0.0132 | 0.0194 | 0.0272 | 0.0400 | 0.0552 | 0.0810 | 0.0962 |

**M3-G |absolute| distribution** (N=25):

| min | max | mean | median | stdev | MAD | MAD×1.4826 | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0.0041 | 0.1093 | 0.0381 | 0.0321 | 0.0280 | 0.0173 | 0.0257 | 0.0149 | 0.0321 | 0.0496 | 0.0593 | 0.0619 | 0.0773 | 0.0968 | 0.1069 |

M3-G's corpus range (`±0.11`) is roughly an order of magnitude smaller than M1-G's (`±1.74`),
consistent with 7F.2/7F.3's finding for the analogous financial-condition case — the share
metric's bounded `[-1,1]` scale compresses the same underlying signal into a much tighter
absolute range, which is why threshold calibration must be done independently for M3-G rather
than reusing M1-G's epsilon (Section 10).

**Spearman correlation and top-10 overlap**: `ρ(|M1-G|, |M3-G|) = 0.6346` over all 25 non-null
pairs; **top-10 overlap = 6/10**. This is very close to 7F.2's finding for financial condition's
M1/M3 pair (`ρ=0.644`, `6/10` overlap) — M3-G is a genuinely different ranking from M1-G, not a
rescaling, to almost exactly the same degree the financial-condition precedent found.

---

## 5. Anchor-case analysis

All four required anchors, hits/words/H reconstructed directly from the database (matches the
persisted `governance_rate_earlier`/`_later` exactly):

| Pair | `h_earlier`→`h_later` | `w_earlier`→`w_later` | `H_earlier`→`H_later` | M1-G | M2-G | M3-G | M6-G (composition distance) |
|---|---|---|---|---|---|---|---|
| **ACT 2017-06-30→2018-06-30** | 96→115 (+19.8%) | 45,963→30,068 (-34.6%) | 322→299 (-7.1%) | **+1.7360** | +0.4134 | **+0.0865** | 0.0193 |
| **BEL 2016-12-31→2017-12-31** | 111→152 (+37.0%) | 34,891→34,078 (-2.3%) | 268→296 (+10.4%) | +1.2790 | +1.1751 | **+0.0993** | 0.0793 |
| **BEL 2018-12-31→2019-12-31** | 171→165 (-3.5%) | 38,063→48,206 (+26.6%) | 360→401 (+11.4%) | **-1.0697** | -0.1576 | **-0.0635** | 0.0056 |
| **ACT 2023-06-30→2024-06-30** | 149→106 (-28.9%) | 45,719→48,083 (+5.2%) | 369→360 (-2.4%) | -1.0545 | -0.9405 | **-0.1093** | 0.0660 |

**Which metric best reflects the underlying disclosure change, per pair**:

- **ACT 2017→2018**: M1-G's `+1.736` is driven substantially by the 34.6% word-count drop (a
  genuine length artifact in the rate framing, as 7F.6 established via M2-G). But M3-G shows
  governance's *share* of all classified language rose 8.65 percentage points — the 3rd-largest
  share movement in the corpus — because governance hits grew in absolute terms (+19.8%) *while
  total custom-taxonomy activity fell* (-7.1%). **M3-G is the metric that best reflects this
  pair**: it is denominator-robust and shows a real, broad-based increase (`board` +10,
  `regulatory_compliance` +9, `remuneration` +5 — Section 7), not the near-zero composition
  change (`M6-G = 0.0193`, low but not the corpus minimum) that would indicate a pure length
  artifact the way financial condition's ACT 2017→2018 pair showed (`M6b = 0.0043`, that
  corpus's lowest).
- **BEL 2016→2017**: M1-G (`+1.279`), M2-G (`+1.175`, 92% survives length control per 7F.6 §16),
  and M3-G (`+0.0993`, largest positive share movement in the corpus) all agree this is a real,
  broad-based governance-language increase. All four metrics converge; this is the corpus's
  cleanest positive control.
- **BEL 2018→2019**: M1-G's `-1.070` is mostly a word-count-growth artifact (48,206 words vs.
  38,063, +26.6%, while hits are nearly flat), as 7F.6 §16 established via M2-G (`-0.158`, 15%
  survives). M3-G shows a smaller but real relative decline (`-0.0635`, still the corpus's
  4th-largest share movement) — the decline here is driven less by governance itself changing
  (hits essentially flat, -3.5%) and more by *other* custom-taxonomy categories growing faster
  (`H` +11.4%), diluting governance's share. **M3-G best reflects this pair as "governance held
  roughly steady while other disclosure topics expanded," a materially different and more
  accurate story than M1-G's implied "governance language declined sharply."**
- **ACT 2023→2024**: M1-G (`-1.055`) and M2-G (`-0.941`, 89% survives, per 7F.6 §16) already
  agreed this is largely a genuine decline, not a length artifact. M3-G confirms this
  emphatically: `-0.1093` is the **single largest share movement in the entire 25-pair corpus**,
  driven by `regulatory_compliance` collapsing from 23 hits to **zero** and `board` falling
  15 hits (Section 7). All three metrics that test for genuineness (M2-G, M3-G, and the near-flat
  word-count ratio) agree this is the corpus's most substantial and best-corroborated governance
  finding.

---

## 6. Company-level analysis

Gate-agnostic (all 25 pairs; report-side gate applied separately in Section 8), per ticker:

| Ticker | N | `\|M1-G\|` min/median/max | `\|M3-G\|` min/median/max | Largest M1-G pair | Largest M3-G pair | Identity changes? |
|---|---|---|---|---|---|---|
| ACT | 9 | 0.0519 / 0.2337 / 1.7360 | 0.0110 / 0.0256 / 0.1093 | 2017-06-30→2018-06-30 | 2023-06-30→2024-06-30 | **Yes** |
| BEL | 6 | 0.0322 / 0.4383 / 1.2790 | 0.0132 / 0.0433 / 0.0993 | 2016-12-31→2017-12-31 | 2016-12-31→2017-12-31 | No |
| KP2 | 5 | 0.0315 / 0.0534 / 0.2836 | 0.0114 / 0.0227 / 0.0444 | 2020-12-31→2021-12-31 | 2021-12-31→2022-12-31 | **Yes** |
| SBP | 2 | 0.0793 / 0.0899 / 0.1006 | 0.0041 / 0.0315 / 0.0589 | 2024-12-31→2025-12-31 | 2023-12-31→2024-12-31 | **Yes** |
| SDL | 1 | 0.4743 (only pair) | 0.0609 (only pair) | 2024-06-30→2025-06-30 | 2024-06-30→2025-06-30 | No (only one pair) |
| SUR | 2 | 0.0915 / 0.1354 / 0.1792 | 0.0149 / 0.0322 / 0.0496 | 2024-06-30→2025-06-30 | 2023-06-30→2024-06-30 | **Yes** |

Four of six companies (ACT, KP2, SBP, SUR) have their "largest governance shift" identity change
between M1-G and M3-G — the same instability pattern 7F.2 found for financial condition (BEL's
identity changed there between M1 and M3). This confirms the general finding that
denominator/normalization choice materially affects *which* pair a company's headline finding
points to, independent of whether the specific artifact pairs 7F.6 flagged survive (Section 5).

---

## 7. Manual top-finding validation

Top 10 gate-eligible pairs by `|M3-G|`, with governance subcategory hit deltas reconstructed
directly from `PassageLanguageCategoryHit` rows (category=`governance`), classified
PASS/CAUTION/FAIL per the milestone's driver taxonomy:

| # | Pair | M3-G | Dominant subcategory driver(s) | Verdict | Driver classification |
|---|---|---|---|---|---|
| 1 | ACT 2023→2024 | -0.1093 | `regulatory_compliance` 23→0 (Δ-23, 53% of gross Δ); `board` 54→39 (Δ-15, 35%) | **CAUTION** | Real and largest in corpus, but concentrated in 2 of 9 subcategories; `regulatory_compliance` going to *literally zero* hits is a notable, disclosable fact in its own right (possible section restructuring or genuine compliance-topic drop — this audit did not re-inspect source text to adjudicate, consistent with scope) |
| 2 | BEL 2016→2017 | +0.0993 | `regulatory_compliance` +22 (54%), `remuneration` +14 (34%), `board` +12 (29%), partly offset by `audit` -4 | **PASS** | Broadly distributed across 3 independent subcategories, no single driver exceeds 54% of gross change, consistent with 7F.6 §16's own "real, broad-based change" verdict for this pair under M2-G |
| 3 | ACT 2017→2018 | +0.0865 | `board` +10 (53%), `regulatory_compliance` +9 (47%), `remuneration` +5 (26%), partly offset by `audit` -5 | **PASS** | Broadly distributed across 3 subcategories; this is the pair 7F.6 flagged as a suspected artifact, but the subcategory pattern here does not resemble a single-topic or sparse-count driver |
| 4 | BEL 2018→2019 | -0.0635 | `regulatory_compliance` -5, `related_party` -3, `board` -2, `internal_controls` -2, partly offset by `remuneration` +5, `audit` +2 | **CAUTION** | Small, diffuse, largely offsetting deltas (net hit change only -6 of 171); the share decline is driven more by `H`'s growth (other categories, +11.4%) than by governance itself moving — a genuine but thin signal |
| 5 | SDL 2024→2025 | -0.0609 | `board` -8 (100% of gross Δ -8) | **CAUTION** | Single-subcategory-driven; smallest `H` in the eligible corpus (125/126, Section 8) though not correlated with instability corpus-wide (Section 8) |
| 6 | SBP 2023→2024 | +0.0589 | `audit` +5, partly offset by `board` -1 | **CAUTION** | Effectively single-driver (`audit`); small absolute counts (44→48 total) |
| 7 | SUR 2023→2024 | +0.0496 | `remuneration` +15, offset by `regulatory_compliance` -9, `audit` -4; **total governance hits unchanged (152→152)** | **CAUTION** | Share change here is driven entirely by `H` shrinking (484→418, other categories declining) while governance itself is exactly flat — this is a genuine but denominator-relative fact, not a governance-language change in the intuitive sense; flagged explicitly so a Discover reader is not misled into thinking governance language itself moved |
| 8 | BEL 2020→2021 | -0.0481 | `remuneration` +30 (58%), `audit` +20 (38%), `regulatory_compliance` +10, offset by `board` -11 | **PASS with note** | Governance hits rose sharply in absolute terms (96→148, +54%) — a real, broad-based increase — but total custom-taxonomy `H` rose even faster (224→389, +73.7%, driven by financial-condition per 7F.3's own anchor for this same pair), so the *share* metric correctly shows a relative decline even though the *volume* metric would show an increase. Both should be disclosed together (Section 12). |
| 9 | KP2 2021→2022 | -0.0444 | `board` -7 (78% of gross Δ -9), `audit` -4, offset by `remuneration` +2 | **CAUTION** | Single-subcategory concentration (`board`), small counts |
| 10 | ACT 2022→2023 | -0.0403 | `litigation` +4, offset by `audit` -1, `regulatory_compliance` -1 (net hit change only +2 of 147) | **CAUTION** | Thinnest evidentiary support in the top 10 — net hit change is only 2 hits; share movement is almost entirely a denominator (`H` +11.5%) effect, not a governance-language change |

**No pair in the top 10 is a pure sparse-count artifact, boilerplate, or a parsing/taxonomy
artifact** in the sense 7F.6 found for `risk_language_introduction` (a single-hit-driven
finding). The CAUTION-rated pairs are caution-rated for **concentration in one or two
subcategories** (ACT 2023→2024, SDL, SBP, KP2 2021→2022) or because **the share movement is
substantially a denominator (other-category) effect rather than a governance-language change**
(BEL 2018→2019, SUR 2023→2024, ACT 2022→2023) — a distinct and previously undocumented driver
category this audit surfaces: **"share-relative" movement**, where governance's own hit count
barely moves but its share shifts because other custom-taxonomy categories move more. This is a
real, correctly-computed signal, but it should be disclosed differently to a Discover reader than
"governance language itself changed" (Section 12).

---

## 8. Denominator adequacy

`H_earlier`/`H_later` (total custom-taxonomy hits) range from **125 (SDL, both sides) to 418–484
(SUR)** across the 24 gate-eligible pairs (excluding ACT's long-gap `NEEDS_REVIEW` pair, same
exclusion 7F.3 applied for the analogous financial-condition case). No pair has `H < 100` on
either side.

**Spearman correlation between `min(H_earlier, H_later)` and `|M3-G|`, over the 24 gate-eligible
pairs: ρ = -0.1335** — weak and, if anything, in the opposite direction a destabilization concern
would predict (smaller `H` associated with *slightly* larger, not smaller, `|M3-G|`, though the
correlation is too weak to treat as a real relationship). This closely matches 7F.3's finding for
financial condition (`ρ=0.05`, also near-zero) — **`M3-G`'s magnitude in this corpus is not being
driven by small taxonomy-hit denominators.**

Per the milestone's instruction, **no minimum-`H` eligibility rule is added here**: the smallest
`H` observed (SDL, 125–126) does not sit near an obvious instability boundary — SDL's `|M3-G|`
(0.0609) is mid-corpus, not an outlier, and its perturbation range (Section 9) is proportionally
wide but not qualitatively different from other pairs'. This finding should be revisited if a
future report pair has substantially fewer than ~125 custom-taxonomy hits per side.

---

## 9. Perturbation analysis

Simulated `later_h ± {1, 2, 5}` governance hits, with `H_later` changing consistently (the more
conservative assumption — a perturbation hit is treated as also changing the total), for the top
10 gate-eligible `|M3-G|` pairs:

| Pair | Base M3-G | -5 | -2 | -1 | +1 | +2 | +5 | Sign-stable? |
|---|---|---|---|---|---|---|---|---|
| ACT 2023→2024 | -0.1093 | -0.1193 | -0.1133 | -0.1113 | -0.1074 | -0.1055 | -0.0997 | Yes |
| BEL 2016→2017 | +0.0993 | +0.0910 | +0.0960 | +0.0977 | +0.1010 | +0.1026 | +0.1074 | Yes |
| ACT 2017→2018 | +0.0865 | +0.0760 | +0.0823 | +0.0844 | +0.0885 | +0.0906 | +0.0966 | Yes |
| BEL 2018→2019 | -0.0635 | -0.0710 | -0.0665 | -0.0650 | -0.0621 | -0.0606 | -0.0563 | Yes |
| SDL 2024→2025 | -0.0609 | -0.0889 | -0.0718 | -0.0663 | -0.0556 | -0.0503 | -0.0350 | Yes |
| SBP 2023→2024 | +0.0589 | +0.0340 | +0.0492 | +0.0541 | +0.0636 | +0.0683 | +0.0820 | Yes |
| SUR 2023→2024 | +0.0496 | +0.0419 | +0.0465 | +0.0481 | +0.0511 | +0.0526 | +0.0571 | Yes |
| BEL 2020→2021 | -0.0481 | -0.0562 | -0.0513 | -0.0497 | -0.0465 | -0.0449 | -0.0402 | Yes |
| KP2 2021→2022 | -0.0444 | -0.0556 | -0.0489 | -0.0466 | -0.0422 | -0.0400 | -0.0335 | Yes |
| ACT 2022→2023 | -0.0403 | -0.0485 | -0.0436 | -0.0419 | -0.0387 | -0.0371 | -0.0323 | Yes |

**Sign stability**: perfect — **no pair changes sign under any tested perturbation** (±1, ±2,
±5 hits), matching 7F.3's finding for the financial-condition M3 case.

**Rank stability**: the top 4 (ACT 2023→2024, BEL 2016→2017, ACT 2017→2018, BEL 2018→2019) remain
well-separated from their nearest neighbors even at ±5 hits — no rank crossing among these four
under any tested perturbation.

**Threshold fragility, specifically at the recommended `0.05` cutline (Section 10)**: two pairs
straddle it under ±5-hit noise — **SDL 2024→2025** (base `-0.0609`, range `-0.0889` to `-0.0350`,
crosses below `0.05` at `+5`) and **SBP 2023→2024** (base `+0.0589`, range `+0.0340` to `+0.0820`,
crosses below `0.05` at `-5`). Both are disclosed explicitly as boundary-sensitive, the same
category of caveat 7F.3 disclosed for its own threshold's two boundary pairs (BEL 2017→2018, ACT
2023→2024 in the financial-condition analysis) — neither changes sign, and both pass manual
validation (Section 7) as real, if concentrated, findings, not noise.

**Does any candidate finding depend on only a few hits?** No pair in the top 10 rests on fewer
than 40 later-side governance hits (SDL's 41 is the smallest); this is a materially larger and
more stable base than `risk_language_introduction`/`_removal`'s single-digit-hit populations
(7F.6 §11, §15) — governance's report-side population is structurally larger than the
alignment-restricted NEW/REMOVED populations those two metrics use.

---

## 10. Threshold calibration

Evaluated over the 24 gate-eligible pairs (`report_side_quality_ok ∈ {GOOD, USABLE}` and
`report_side_primary_eligible`; excludes ACT's `NEEDS_REVIEW` long-gap pair, same exclusion rule
as 7F.3):

**A. Absolute share-point thresholds**

| Threshold | N eligible | % of 24 | Companies |
|---|---|---|---|
| 0.01 | 23 | 96% | all 6 |
| 0.02 | 15 | 62% | all 6 |
| 0.03 | 13 | 54% | all 6 |
| 0.04 | 10 | 42% | all 6 |
| 0.05 | 6 | 25% | ACT, BEL, SBP, SDL |
| 0.075 | 3 | 12% | ACT, BEL |
| 0.10 | 1 | 4% | ACT only |

**B. Percentile thresholds** (of eligible `|M3-G|` distribution)

| Percentile | Value | N eligible | % |
|---|---|---|---|
| p75 | 0.0519 | 6 | 25% |
| p80 | 0.0597 | 5 | 21% |
| p85 | 0.0623 | 4 | 17% |
| p90 | 0.0796 | 3 | 12% |
| p95 | 0.0974 | 2 | 8% |

**C. Robust statistical thresholds** — `median(M3-G signed) = -0.0132`, `MAD = 0.0308`, scaled
(×1.4826) `= 0.0456`.

| Rule | Threshold | N eligible | % |
|---|---|---|---|
| median + 1.0×scaled MAD | 0.0588 | 6 | 25% |
| median + 1.5×scaled MAD | 0.0816 | 3 | 12% |
| median + 2.0×scaled MAD | 0.1044 | 1 | 4% |

**D. Hybrid** `max(min_abs, percentile)` — tested `min_abs ∈ {0.01, 0.02}` against `{p75, p85}`.
As in 7F.3's financial-condition analysis, the percentile-derived values already exceed both
floors tested, so the hybrid rule collapses to the plain percentile threshold in every
combination tried.

**Convergence**: the p75 percentile (`0.0519`) and the robust median+1×scaled-MAD statistic
(`0.0588`) both select **N=6, the same 4-company set (ACT, BEL, SBP, SDL)** — a narrower
convergence band than 7F.3 found for financial condition (`0.037–0.042`, ~13% spread) but the
same *N and company membership* on both independent methods, which is the load-bearing
convergence property, not the raw percentage gap between the two threshold values. A round-number
threshold of **`0.05`** sits inside this band and produces the identical N=6/ACT,BEL,SBP,SDL set
as both p75 and (nearly) median+1×MAD.

**Perturbation robustness at `0.05`** (Section 9): SDL and SBP are boundary-sensitive under
±5-hit noise; neither changes sign; both pass manual content validation (Section 7).

**Does the threshold exclude trivial shifts and preserve validated findings?** At `0.05`: the six
admitted pairs are exactly the top 6 manually validated in Section 7 (PASS or CAUTION, none
FAIL) — nothing admitted at `0.05` is a pure sparse-count or single-hit artifact. Thresholds
`≤0.02` admit pairs with `|M3-G|` as low as `0.011–0.022` (e.g. KP2 2019→2020, ACT 2016→2017,
`H`-flat small deltas) that read as diffuse noise on inspection, not findings, mirroring 7F.3's
own finding for the financial-condition case at low thresholds.

---

## 11. Discover before/after simulation

Simulated current (`governance_language_change`/M1-G, `epsilon=1.0`, report-side gate) vs.
proposed (M3-G, `|M3-G| ≥ 0.05`, same report-side gate, unchanged):

| Ticker | Pair | Current M1-G | Current eligible? | New M3-G | New eligible? | Reason for change |
|---|---|---|---|---|---|---|
| ACT | 2017-06-30→2018-06-30 | +1.7360 | Yes (rank 1) | +0.0865 | **Yes (rank 3)** | Retained under both — magnitude interpretation changes (density spike → real but smaller share gain), but eligibility does not |
| BEL | 2016-12-31→2017-12-31 | +1.2790 | Yes (rank 2) | +0.0993 | **Yes (rank 2)** | Retained under both; rank order swaps with ACT 2017→18 (M3-G ranks it above) |
| BEL | 2018-12-31→2019-12-31 | -1.0697 | Yes (rank 3) | -0.0635 | **Yes (rank 4)** | Retained under both — same nuance as ACT 2017→18 |
| ACT | 2023-06-30→2024-06-30 | -1.0545 | Yes (rank 4) | -0.1093 | **Yes (rank 1)** | Retained under both; becomes the #1-ranked finding under M3-G (was #4 under M1-G) |
| SDL | 2024-06-30→2025-06-30 | -0.4743 | No (below eps=1.0) | -0.0609 | **Yes (newly added)** | New: below current epsilon but clears the new share threshold; CAUTION on manual validation (single-subcategory `board` driver, Section 7) |
| SBP | 2023-12-31→2024-12-31 | +0.0793 | No | +0.0589 | **Yes (newly added)** | New: SBP has no representation under M1-G at all (max `|M1-G|`=0.1006); gains one finding under M3-G, boundary-sensitive to perturbation (Section 9) |

**Explicit explanation of the four named anchors** (per the milestone's requirement):

- **ACT 2017→2018 and BEL 2018→2019 remain Discover-eligible under the proposed metric** — this
  is the central, non-obvious finding of this analysis (Section 1, Section 5). The financial-
  condition precedent's flagship result was demotion; here it is *retention with corrected
  magnitude and interpretation*. Both pairs' M1-G values were substantially inflated by
  word-count changes, but both pairs also show genuine, non-trivial relative-share movement once
  the denominator artifact is removed. **Neither should be described as a pure artifact.**
- **BEL 2016→2017 is preserved**, as expected — it was already the corpus's cleanest
  non-artifact finding under 7F.6's own length-control analysis (92% survives), and M3-G confirms
  it as the corpus's single largest *positive* share movement.
- **ACT 2023→2024 is preserved and promoted** to the #1-ranked M3-G finding (from #4 under
  M1-G) — this pair was already flagged by 7F.6 as largely non-artifactual (89% survives length
  control), and M3-G's share-based view makes it the corpus's single largest movement of any
  kind, driven by `regulatory_compliance` collapsing to zero hits (Section 7) — a striking,
  disclosable, and well-supported finding.

**No pair is removed** by the proposed threshold in this corpus — unlike the financial-condition
precedent (where ACT FC 2017→2018 was removed outright), **governance's redesign is additive**
(2 new findings, SDL and SBP) rather than substitutive. This is a direct, evidence-grounded
consequence of the anchor-case finding in Section 5, not an assumption carried over from the
financial-condition playbook.

---

## 12. Interpretation design (draft user-facing language)

**M1-G — governance language density change** (supporting detail only, not primary ranking)
- Measures: the change in how often governance-related language appears, per 1,000 words of
  narrative text, between the two reports.
- Units: hits per 1,000 words (rate-point difference).
- Positive means the later report used governance language more densely per word; negative means
  less densely.
- Does **not** mean the total amount of governance discussion changed — a report that got shorter
  can show a large positive value even if the actual content barely moved, because the same hit
  count is divided by fewer words (Section 5's ACT 2017→2018 case).

**M3-G — governance language share change** (primary ranking metric, headline "Largest
governance-language shift")
- Measures: the change in governance language's share of all classified (risk /
  financial-condition / governance / strategy) language in the report, independent of report
  length.
- Units: percentage points of share (bounded -100 to +100, typically well under ±11 in this
  corpus).
- Positive means governance language became a larger slice of the report's classified disclosure
  language; negative means a smaller slice.
- Does **not** mean the total amount of governance language changed in absolute terms — a report
  can show a governance share *decline* even while governance hits rose in absolute count, if
  other disclosure topics (e.g. financial-condition language) grew even faster (Section 7's BEL
  2020→2021 case). Does **not** mean governance quality, compliance posture, or oversight
  improved or worsened — this measures disclosure *language*, not governance outcomes.
- **Explicit caution for "share-relative" pairs** (Section 7): when a pair's own governance hit
  count barely moved but its share moved because *other* categories changed more (e.g. SUR
  2023→2024, ACT 2022→2023), the supporting text should say so directly — "governance language
  itself was essentially unchanged; its relative share moved because other disclosure topics grew
  or shrank" — rather than implying governance-specific movement.

**M6-G — governance topic-mix change** (supporting/evidence-page detail only, if adopted)
- Measures: how much the *mix* of governance subtopics (board, audit, remuneration, etc.) shifted,
  independent of whether overall governance volume or share changed.
- Units: a distance between 0 (identical topic mix) and 1 (completely different topic mix, no
  overlap).
- Higher means the report emphasized different governance subtopics than before; carries no sign.
- Does **not** mean more or less governance language was used overall.

None of the three should be described as implying the company's governance quality, board
effectiveness, or compliance improved or worsened — they measure disclosure language, not
governance outcomes, mirroring 7F.3 §11's identical caution for the financial-condition case.

---

## 13. Quality-gate assessment

The existing `_gate_report_side` gate (`report_side_quality_ok ∈ {GOOD, USABLE}` and
`report_side_primary_eligible`) remains appropriate for M3-G, unchanged:

- **GOOD/USABLE acceptable, NEEDS_REVIEW excluded** — confirmed correct: it validates the
  underlying passage population (primary-narrative word coverage, dictionary match rate,
  transition/irregular-gap exclusion), which M1-G and M3-G draw from identically (Section 2,
  Section 3). Nothing about the gate's logic is specific to M1-G's word-count denominator.
- **The one pair the gate correctly excludes** (ACT 2016-06-30→2024-06-30, `NEEDS_REVIEW`,
  8-year irregular-gap pair) is excluded from every table in this document that filters on the
  gate (Sections 6, 7, 8, 9, 10, 11), matching 7F.3's identical treatment of the analogous
  financial-condition pair.
- **Does the share denominator (`H`) require an additional check the current gate does not
  cover?** No, per the evidence in Section 8: `H` never drops below 125 in this corpus, and
  `|M3-G|` is not meaningfully correlated with `H` size (`ρ=-0.13`). This mirrors 7F.3 §9's
  identical conclusion for financial-condition's `H` — the gate's `dictionary_match_rate_*`
  checks are computed from the word-count denominator, not `H` directly, which is a **structural
  gap, not a coincidence of the current corpus** (same caveat 7F.3 raised): a future report with
  unusually sparse custom-taxonomy language could pass the existing gate while still being
  `H`-unstable for M3-G specifically. **This is identified here and left unresolved**, per the
  milestone's explicit instruction not to silently add a new rule.
- **No change to the gate is made or proposed here.**

---

## 14. Taxonomy diagnostics (governance, diagnostic only — no redesign)

Governance's 9 subcategories (`config/financial_language_custom_taxonomy.yaml`), with 2-3 seed
terms/phrases each — sparser than financial_condition's 12 subcategories or risk's 11
subcategories, as the milestone brief already anticipated. Corpus-wide subcategory hit
distribution (both sides, all 25 pairs, N=5,815 total governance hits):

| Subcategory | Hits | Share of corpus governance hits |
|---|---|---|
| `board` | 2,002 | 34.4% |
| `audit` | 1,362 | 23.4% |
| `remuneration` | 1,257 | 21.6% |
| `regulatory_compliance` | 584 | 10.0% |
| `ethics` | 246 | 4.2% |
| `internal_controls` | 235 | 4.0% |
| `related_party` | 68 | 1.2% |
| `litigation` | 43 | 0.7% |
| `shareholder_rights` | 18 | 0.3% |

- **Does one subcategory dominate?** No single subcategory exceeds 40% of all governance hits
  (`board` at 34.4% is the largest) — meaningfully more distributed than a single-topic-dominated
  taxonomy would be, and comparable in concentration to financial-condition's own subcategory
  spread (7F.2/7F.3 did not report a dominance figure directly, but no single financial-condition
  subcategory was flagged as dominant either).
- **Is the taxonomy sparse enough to threaten stability?** **Partially, for 2 of 9
  subcategories**: `litigation` (0.7%) and `shareholder_rights` (0.3%) together account for only
  1.0% of all governance hits corpus-wide — individually, neither carries enough volume to
  support a standalone per-subcategory materiality claim (a single pair's `litigation` delta of
  ±4, as seen in ACT 2022→2023 and ACT 2023→2024, Section 7, is a large *relative* move for that
  subcategory but a trivial *absolute* count). The other 7 subcategories (`board`, `audit`,
  `remuneration`, `regulatory_compliance`, `ethics`, `internal_controls`, `related_party`) have
  adequate volume (68–2,002 hits corpus-wide) to support the aggregate composition metric.
- **Is a composition breakdown meaningful overall?** **Yes, for the metric as a 9-dimensional
  aggregate** — M6-G (cosine distance over the full 9-subcategory share vector) is not driven by
  the two sparse subcategories alone (their combined 1.0% share means they contribute
  negligibly to the vector's norm in virtually every pair), so the aggregate composition-distance
  number remains meaningful even though a per-subcategory breakdown for `litigation` or
  `shareholder_rights` specifically should be treated with caution if ever surfaced individually.
  This diagnostic conclusion does not require or recommend any taxonomy change (out of scope,
  per the milestone's hard rule) — it is reported as evidence for the composition-metric adoption
  decision only (Section 15).

---

## 15. Final recommendation

**`ADOPT_GOVERNANCE_SHARE_WITH_THRESHOLD`**

- **Formula**: `governance_share_change = (governance_hits_later / H_later) −
  (governance_hits_earlier / H_earlier)`, where `H = risk_hits + financial_condition_hits +
  governance_hits + strategy_hits`, both computed over the existing `feature_eligible_primary`
  population — identical numerator source and passage population to the current production
  metric; only the denominator changes (Section 2, Section 3).
- **Threshold**: **`|governance_share_change| ≥ 0.05`** (5 percentage points of governance's
  share of classified disclosure language), applied on top of the existing, unchanged
  `_gate_report_side` quality gate (Section 13).
- **Rationale**: this value sits inside the convergence band of two independent threshold
  families — the 75th percentile of the eligible-corpus `|M3-G|` distribution (`0.0519`) and a
  robust median+1×scaled-MAD statistic (`0.0588`) — both of which select the identical N=6,
  4-company set (ACT, BEL, SBP, SDL), mirroring the convergence discipline 7F.3 established for
  the financial-condition case (Section 10). It preserves every pair 7F.6 identified as
  non-artifactual (BEL 2016→2017, ACT 2023→2024) and — unlike the financial-condition
  precedent — **also preserves, rather than demotes**, the two pairs 7F.6 flagged as suspected
  artifacts (ACT 2017→2018, BEL 2018→2019), because direct reconstruction of the underlying hit
  counts shows both pairs carry genuine, broad-based (or genuinely-if-modestly relative) share
  movement independent of the word-count artifact in M1-G's rate framing (Section 5). No admitted
  finding changes sign under ±5-hit perturbation (Section 9); two admitted pairs (SDL, SBP) are
  disclosed as boundary-sensitive at this specific threshold, consistent with 7F.3's own
  precedent of disclosing rather than hiding boundary fragility.
- **Quality gate**: unchanged (`_gate_report_side`, GOOD/USABLE + primary-eligible), per Section
  13 — no new minimum-`H` rule is added, consistent with the evidence in Section 8.
- **M1-G status**: retained as `SUPPORTING_DETAIL` (governance language *density* change),
  displayed alongside M3-G but never used for ranking or gating — matching 7F.3's identical
  treatment of financial condition's M1 (Section 15 there).
- **Composition detail (M6-G)**: recommended as `SUPPORTING_DETAIL` on comparison/evidence pages
  only, not a headline ranking metric — it has no natural sign or "how much" framing suited to a
  Discover headline, but is directly useful for explaining *which* governance subtopics moved,
  with the caveat that per-subcategory claims involving `litigation` or `shareholder_rights`
  alone should be treated cautiously given their sparse corpus-wide volume (Section 14).

**This is `ADOPT`, not `RETAIN`**, because M1-G's specific rate-difference formula remains
confirmed denominator-sensitive (Section 2, and reconfirmed by the same length-control mechanism
7F.6 already applied) — the production ranking metric should change. **It is not
`USE_HYBRID_GOVERNANCE_METRIC`**, because no hybrid combination was found necessary: M3-G alone,
with M1-G and M6-G as clearly-labeled supporting context (not blended into a single ranking
score), satisfies every threshold-selection criterion the milestone specifies (Section 10). **It
is not `REMOVE_GOVERNANCE_FROM_DISCOVER`**, because the underlying phenomenon (real,
quality-good, non-trivial governance-language shifts exist in this corpus, both under M1-G's
framing and, independently, under M3-G's) is corroborated by two structurally different metrics,
not merely asserted by one.

---

## 16. Net-tone documentation correction (cross-reference)

Per this milestone's explicit instruction, `docs/discover-metric-methodology-audit-7f6.md` was
corrected in three places — **wording only, no other 7F.6 conclusion, rationale, or figure was
touched**:

1. **Executive summary** (originally: `net_tone_change` — **MODIFY_NORMALIZATION**): corrected to
   **RECALIBRATE_THRESHOLD / VERIFY_NORMALIZATION**, with the phrase "own epsilon, not a
   threshold-only fix" replaced by wording that states the metric needs a metric-specific epsilon
   as a threshold/calibration correction, not a formula redesign — consistent with 7F.6's own
   Section 14 finding that 4 of the top 5 `net_tone_change` findings survive length control
   (53–128%) and its own "Plain answers" #2, which already stated in prose that
   `net_tone_change` "needs threshold/normalization work but not a formula change." The prior
   `MODIFY_NORMALIZATION` label was inconsistent with that same document's own body evidence.
2. **Section 21 verdict table** (the metric-by-metric verdict row for `net_tone_change`):
   classification corrected identically; the rationale cell's opening clause ("Not merely a
   threshold problem") was changed to "Primarily a threshold problem, not a formula defect" and
   one closing sentence was added explicitly distinguishing this from `governance_language_change`'s
   confirmed structural defect (the comparison this milestone's evidence directly supports — see
   Section 2 of this document) — this is the minimal wording change needed to keep the sentence
   logically consistent with the corrected classification, per this milestone's explicit
   instruction not to touch rationale prose beyond what grammatical/logical consistency requires.
3. **Final summary table**: classification cell corrected identically; no other cell in that row
   (formula family, quality gate, epsilon, selectivity, risk driver, priority) was touched.

**No other metric's verdict, rationale, or supporting figure in `docs/discover-metric-methodology-
audit-7f6.md` was modified.** `uncertainty_intensity_change` (RECALIBRATE_THRESHOLD),
`risk_language_introduction`/`_removal` (MODIFY_METRIC_AND_THRESHOLD),
`disclosure_change_score` (MORE_DATA_NEEDED), and `governance_language_change`'s own verdict
(MODIFY_METRIC_AND_THRESHOLD) are all left exactly as 7F.6 wrote them.

**Flagged tension with 7F.6, not silently resolved** (per this milestone's explicit instruction):
7F.6 §16 characterizes ACT 2017→2018 and BEL 2018-12-31→2019-12-31 as "**FAIL as a standalone
claim**" and classifies both as "**report-length artifact**," based on M2-style length control
alone. This milestone's M3-G evidence (Section 5, Section 7, Section 11 of this document) shows
that under a denominator-robust share-based metric, **both pairs remain among the corpus's
largest governance-share movements (top 4 of 25) and are not removed by any reasonable
threshold** — the underlying hit-count evidence (broad multi-subcategory gains for ACT 2017→2018;
a genuine, if smaller, relative decline for BEL 2018→2019, Section 7) does not support
classifying either pair as a pure artifact once the word-count denominator is removed from the
picture. **This does not contradict 7F.6's narrower, and still-correct, finding that M1-G's
specific rate-difference formula inflates these pairs' *magnitude* via the same denominator-
shrinkage mechanism already proven for financial condition** — that mechanism is confirmed again
here (Section 2, Section 5's M1-G-vs-M2-G comparison). What this milestone's evidence contradicts
is the *stronger* implied conclusion in 7F.6 §16 that these two findings should not be considered
genuine governance-language shifts at all. Per this milestone's explicit instruction, **7F.6's
own text has not been rewritten to reflect this** (only the net-tone wording described above was
touched) — this is reported directly here for the requester's review and disposition.

---

*Analysis produced by `scripts/research_7f7a_governance_metric_redesign.py`, a read-only research
script retained under `scripts/` per the 7D.5a/7F.3-established convention. No production table,
`findings.py`, config, taxonomy, or migration file was modified in the production of this
document; the only file besides this one that was edited is the three wording-only corrections to
`docs/discover-metric-methodology-audit-7f6.md` described in Section 16.*

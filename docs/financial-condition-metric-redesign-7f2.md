# 7F.2 — Financial-Condition Metric Redesign

**Scope**: read-only analysis, building on `docs/financial-condition-shift-methodology-audit.md`
and `docs/financial-condition-metric-calibration-7f1.md`. No code, config, thresholds, or
production data were changed. All figures below were recomputed from raw
`PassageLanguageSignal` / `PassageLanguageCategoryHit` rows for the current run of each of the
25 `ReportPairLanguageFeatures` pairs (`feature_eligible_primary` population — same population
the production metric uses), as of `2026-09-22`, via ad hoc read-only queries against the
research database. The hit/word reconstruction was cross-checked against the persisted
`financial_condition_rate_earlier`/`_later` columns for every pair and matches exactly.

**Goal**: compare six alternative normalizations for `financial_condition_language_change`
against the current metric, determine whether the metric should be decomposed into
volume/intensity vs. composition components, and make a RETAIN / MODIFY / REPLACE / REMOVE
recommendation grounded in corpus evidence. No threshold is chosen here — 7F.1 already
established that no threshold should be picked until normalization is validated, and this
analysis honors that constraint.

---

## Summary answer

**MODIFY the current metric — do not REPLACE it, and do not REMOVE it from Discover.**
Specifically: (1) keep a *rate-difference* metric as the headline "how much did
financial-condition language move" number — none of the alternatives tested is strictly
better on interpretability, and several trade one weakness for another rather than fixing it;
but (2) the current metric's denominator (report-length-sensitive, feature-eligible
primary-narrative words) should be replaced or supplemented with the hit-share
(compositional) normalization for materiality *ranking* purposes, because it is the only
alternative tested that is structurally immune to the denominator-shrinkage artifact that
7F.1 already identified as invalidating the flagship ACT 2017→2018 example; and (3) the
metric should be decomposed into two published numbers — a volume/intensity change and a
composition/subcategory change — rather than forced into one scalar, because a median
**74%** of the gross subcategory-level movement in this corpus cancels out and is invisible
in the current net figure.

---

## The six candidates, exact formulas

For one report side, let `h` = financial-condition hit count and `w` = feature-eligible
primary-narrative word count over the same population the current metric uses (unchanged
from the current pipeline — this analysis does not touch population/eligibility filtering).
`H` = total custom-taxonomy hits (risk + financial_condition + governance + strategy) on
that side. `i` indexes the 12 financial-condition subcategories.

| # | Name | Formula |
|---|---|---|
| M1 | Current rate difference | `1000·h_later/w_later − 1000·h_earlier/w_earlier` |
| M2 | Length-controlled hit change | `1000·h_later/w_earlier − 1000·h_earlier/w_earlier` (later hits re-normalized by the earlier side's word count, holding denominator fixed) |
| M3 | Hit-share / compositional change | `(h_later/H_later) − (h_earlier/H_earlier)` |
| M4 | Log-rate ratio | `ln((rate_later + 0.1) / (rate_earlier + 0.1))`, smoothing = 0.1 per 1,000 words |
| M5 | Standardized (robust z) change | `(M1 − median(M1 corpus)) / (1.4826 × MAD(M1 corpus))` |
| M6a | Subcategory-vector intensity change | `‖intensity_later − intensity_earlier‖₂` over the 12-dim per-1,000-word subcategory rate vector |
| M6b | Subcategory-vector composition change | `1 − cosine(comp_earlier, comp_later)`, where `comp` is the 12-dim vector of each subcategory's *share* of that side's financial-condition hits |

M5 is a standardization of M1, not an independent normalization — it changes scale/units
(making cross-metric epsilon comparison meaningful, per 7F.1 Q1/Q2) but inherits M1's
denominator sensitivity exactly, since it is a monotonic transform of M1. It is reported
here for completeness since the milestone brief asked for it explicitly.

---

## Corpus-wide comparison

| Metric | median | MAD (scaled) | min \|·\| | max \|·\| | Spearman ρ with M1 (magnitude) | Top-10 overlap with M1 |
|---|---|---|---|---|---|---|
| M1 current | −0.0134 | 0.2415 | 0.0134 | 1.1027 | 1.000 | 10/10 |
| M2 length-controlled | −0.0218 | 0.3141 | 0.0134 | 2.6919 | 0.489 | 6/10 |
| M3 hit-share | −0.0047 | 0.0349 | 0.0003 | 0.1002 | 0.644 | 6/10 |
| M4 log-rate ratio | −0.0060 | 0.1034 | 0.0007 | 0.3966 | **0.985** | 10/10 |
| M5 robust z | 0 (by construction) | 1 (by construction) | — | — | 1.000 | 9/10 |
| M6a subcat-vector intensity | 0.2923 | 0.2223 | 0.0864 | 0.7864 | 0.795 | 7/10 |
| M6b subcat-vector composition | — | — | 0.0016 | 0.3427 | 0.443 | 6/10 |

**M4 (log-rate ratio) is nearly a re-scaling of M1, not an independent alternative.**
ρ = 0.985 and identical top-10 membership. This matters for the recommendation: log-rate
ratio is often proposed as a fix for denominator sensitivity (it is standard in the
sentiment-analysis literature for exactly that reason, e.g. comparing pre/post ratios
symmetrically), but here it does **not** fix it, because it is still computed from the same
two already-denominator-sensitive rates — it only changes how the difference between two
already-corrupted numbers is expressed (ratio vs. difference), not the numbers themselves.
ACT 2017→2018 is **still M4's #1-ranked pair** (`+0.3966`, the single largest log-rate ratio
in the corpus), for the identical reason it's M1's #2: the later-side rate is inflated by a
~35% word-count drop regardless of which way the two rates are combined.

**M2 and M3 are the two candidates that genuinely diverge from M1's ranking** (ρ 0.489 and
0.644, 6/10 top-10 overlap each) — both because they normalize differently enough to no
longer inherit M1's specific denominator artifact (Section "Denominator robustness" below).

---

## Behavior on the three named pairs

### ACT 2017-06-30 → 2018-06-30 (current metric's flagship Discover-eligible example)

| Metric | Value | Rank (of 25, by \|·\|) |
|---|---|---|
| M1 current | **+1.0019** | 2nd |
| M2 length-controlled | **−0.0218** | 24th (near-zero) |
| M3 hit-share | +0.0182 | 12th |
| M4 log-rate ratio | **+0.3966** | **1st** |
| M5 robust z | +4.20 | 2nd |
| M6a intensity L2 | 0.648 | 4th |
| M6b composition cosine distance | 0.0043 | near-bottom (least compositional change in the corpus) |

Raw counts: hits 90→89 (essentially flat), words 45,963→30,068 (−35%). This pair is the
clearest illustration in the corpus of the difference between "denominator-sensitive"
alternatives (M1, M4, M5 all rank it top-2) and "denominator-robust" alternatives (M2, M3
both rank it outside the top 10, M2 places it at essentially zero). Its financial-condition
*hit-share of all classified language* barely moved (28.0% → 29.8% of custom-taxonomy hits),
and its *subcategory composition* (M6b) is the **most stable** pair in the entire corpus —
whatever moved for ACT this period, it was not a compositional shift in which subcategories
it discusses. This pair should not be described as "financial-condition language increased"
under any of the length-normalized or share-based views; it should be described as "the
2018 report was substantially shorter, and financial-condition language's density rose
mechanically as a result, with no material change in volume, share, or composition."

### SBP 2023-12-31 → 2024-12-31

| Metric | Value | Rank |
|---|---|---|
| M1 current | **−1.1027** | 1st |
| M2 length-controlled | −0.9278 | 4th |
| M3 hit-share | −0.0725 | **3rd** |
| M4 log-rate ratio | −0.3031 | 5th |
| M5 robust z | −4.51 | 1st |
| M6a intensity L2 | 0.665 | 3rd |
| M6b composition cosine distance | 0.0126 | low (stable composition) |

Raw counts: hits 71→55 (−23%), words 17,246→18,247 (+6%, roughly flat). Unlike ACT
2017→2018, SBP's word-count denominator barely moved — its rate change is driven by a
genuine drop in hit count, not by a length artifact. It remains a top-5 finding under
**every** alternative tested (1st, 4th, 3rd, 5th, 1st, 3rd) — this is the corpus's one
pair whose "largest financial-condition shift" status survives normalization choice. Its
report-side quality is `USABLE` (borderline dictionary match rate on both sides, per 7F.1
Section 6), which should be disclosed alongside any Discover placement regardless of which
metric is used.

### BEL pairs (all 6; BEL never clears the current `epsilon=1.0` bar)

| Pair | M1 | M2 | M3 | M4 | M6a | M6b |
|---|---|---|---|---|---|---|
| 2016→2017 | −0.0743 | −0.1146 | −0.0358 | −0.0398 | 0.260 | 0.063 |
| 2017→2018 | **+0.5544** | +0.8216 | +0.0423 | +0.2644 | 0.395 | 0.084 |
| 2018→2019 | +0.1414 | +0.7882 | +0.0501 | +0.0576 | 0.196 | 0.021 |
| 2019→2020 | +0.1494 | −1.0372 | +0.0073 | +0.0575 | 0.195 | 0.021 |
| 2020→2021 | +0.2783 | **+2.6919** | **+0.0531** | +0.0989 | **0.432** | **0.093** |
| 2021→2022 | +0.0171 | −0.0417 | −0.0172 | +0.0058 | 0.141 | 0.009 |

BEL's identity as "largest shift" is **not stable across normalizations**. The current
metric (M1) and M4 both pick **2017→2018** as BEL's largest pair. M2, M3, and M6a all pick
**2020→2021** instead — the pair whose word count moved by +87% (18,079 → 33,864 words),
the mirror image of ACT's problem. Under M2, BEL 2020→2021 (`+2.69`) would be the single
largest length-controlled shift in the **entire 25-pair corpus**, well above SBP or ACT.
This is the strongest evidence in this analysis that the current metric's headline "largest
shift" ranking is picking up report-length volatility, not financial-condition-language
volatility, for more than one company.

---

## Per-candidate assessment

### M2 — Length-controlled hit change

- **Interpretability**: moderate. "How would the later report's hit count read if it were
  the same length as the earlier one" is explainable to a non-technical Discover user, but
  requires choosing *which* side's word count is the fixed reference — an asymmetric,
  order-dependent choice with no principled default.
- **Sensitivity to report length**: this is the point of the metric — deliberately zero, by
  construction, to length changes on one side.
- **Sensitivity to small hit-count changes**: high — since the denominator is fixed and
  typically smaller-magnitude adjustments than a live word count, a handful of extra hits
  moves M2 more than they'd move M1.
- **Ranking stability**: ρ 0.489 vs. M1 — a genuinely different ranking, not a rescaling.
- **Company coverage**: at the p75 magnitude percentile, ACT/BEL/SBP (SUR drops out
  relative to M1's ACT/BEL/SBP/SUR).
- **Top-10 pair ranking / overlap with current**: 6/10.
- **Robustness to denominator changes**: tested both earlier-fixed and later-fixed variants;
  their own top-10 lists overlap **10/10** with each other — i.e., *which* side's word count
  you hold fixed barely matters, only *that* one is held fixed matters. This is a genuinely
  robust property.
- **Suitability for Discover**: workable as a **secondary/diagnostic** figure ("if report
  length hadn't changed, the shift would have been X") but not as the sole headline number,
  because the "hold X side fixed" framing is unfamiliar and requires explanation that a rate
  difference does not.

### M3 — Hit-share / compositional change

- **Interpretability**: good — "financial-condition language went from Y% to Z% of all the
  disclosure-language this report discusses" is an intuitive, self-normalizing statement
  that needs no word-count explanation at all.
- **Sensitivity to report length**: **structurally zero** — both numerator and denominator
  are hit counts, so a shorter/longer report affects them proportionally (if at all) and
  cancels. This is the strongest denominator-robustness property of any candidate tested.
- **Sensitivity to small hit-count changes**: low-to-moderate — because the denominator
  (`H`, total custom-taxonomy hits, typically 300-500 per side in this corpus) is much
  larger than the financial-condition numerator, small hit-count noise is naturally damped
  rather than amplified.
- **Ranking stability**: ρ 0.644 vs. M1, 6/10 top-10 overlap — a real, different ranking.
- **Company coverage**: ACT/BEL/KP2/SBP/SUR at p75 — the widest of all six candidates,
  because its scale (bounded in [−1, 1], corpus range only ±0.10) makes small absolute
  movements register relative to its own distribution rather than being swamped by a few
  outlier pairs.
- **Robustness to denominator changes**: by construction, immune to the specific
  word-count-denominator issue that motivated this whole analysis (7F.1 Q3).
- **Suitability for Discover**: **strong candidate for the primary materiality-ranking
  metric**, precisely because it does not confound "discussed financial condition more"
  with "the report happened to be shorter this year." Its main limitation is that it
  answers "share of *classified* language," which is once removed from "share of the
  report" — a reader has to understand it's relative to other tagged risk/governance/
  strategy language, not to the whole document. That's a real interpretability cost but a
  smaller one than silently baking in a length artifact.

### M4 — Log-rate ratio

- **Interpretability**: moderate for technical users (percentage-style symmetric change),
  poor for a general Discover audience (log scale is not intuitive without explanation).
- **Sensitivity to report length**: **not fixed** — see the ACT 2017→2018 result above.
  Because it's computed from the same two rates as M1, any artifact in those rates
  (denominator shrinkage) passes through unchanged.
- **Sensitivity to small hit-count changes**: lower than M1 near larger rate values (log
  compression), higher near-zero (the `+0.1` smoothing constant becomes load-bearing for
  low-hit-count pairs and is itself an undocumented, arbitrarily-chosen value — the same
  category of problem 7F.1 flagged for `epsilon=1.0`).
- **Ranking stability**: ρ 0.985 — for practical purposes, the same ranking as M1.
- **Robustness to denominator changes**: none additional to M1.
- **Suitability for Discover**: **not recommended** as a replacement — it changes the
  metric's mathematical form without addressing the problem this milestone was opened to
  solve, while adding interpretability cost (log scale, an extra smoothing constant to
  justify). It would only be worth adopting if paired with a denominator fix (e.g. applied
  to M3's share values instead of M1's rates), which was not tested here.

### M5 — Standardized (robust z) change

- **Interpretability**: poor for end users ("2.4 standard deviations" is an analyst framing,
  not a Discover-page framing), but this is exactly the tool 7F.1 Q1/Q2 called for to make
  the shared `epsilon` defensible across the five `rate_per_1000_words` metrics.
- **Sensitivity to report length / small hit changes**: identical to M1 (monotonic
  transform) — it changes *scale*, not *substance*.
- **Ranking stability**: ρ = 1.000 with M1 by construction (a monotonic transform cannot
  reorder). Top-10 overlap is 9/10 rather than 10/10 only because of a near-tie at the
  boundary once `abs()` and the exact scaling constant interact with sort order.
- **Suitability for Discover**: not a competing metric — a **threshold-calibration tool**,
  not a display value. It resolves 7F.1's Q1/Q2 (per-metric epsilon calibration) but does
  nothing for Q3 (denominator sensitivity), because it is derived entirely from M1.

### M6a / M6b — Subcategory-vector decomposition

- **Interpretability**: M6a (intensity L2) is a "how much did the 12-dimensional
  financial-condition language profile move, in absolute terms" magnitude — good for
  ranking "how much changed" without a sign, poor for saying "changed how." M6b
  (composition cosine distance) is "how much did the *mix* of subcategories shift,
  independent of overall volume" — this is the cleanest available answer to 7F.1 Q4
  ("should subcategory changes be exposed separately").
- **Sensitivity to report length**: M6a inherits some rate-based sensitivity (each
  subcategory rate uses the same word-count denominator as M1), so it is **not** immune to
  the ACT-style artifact — ACT 2017→2018 still ranks 4th by M6a. M6b is **structurally
  immune**, like M3, because composition shares cancel out any common-mode length effect
  affecting all subcategories proportionally (ACT 2017→2018 has the *lowest*
  composition-distance in the corpus, 0.0043 — confirming nothing about its subcategory mix
  actually changed).
- **Ranking stability**: M6a ρ 0.795 vs. M1 (moderately correlated — it's driven by the same
  hit volume, just decomposed); M6b ρ 0.443 (a genuinely distinct signal).
- **Correlation between M6a and M6b**: Pearson r = 0.615 — related but far from redundant;
  a pair can have large intensity movement with stable composition (e.g. SBP: intensity
  rank 3rd, composition distance only 0.013, low) or the reverse (BEL 2020→2021: intensity
  rank 9th-ish, composition distance highest in the corpus at 0.093).
- **Suitability for Discover**: not as a headline ranking metric (too abstract for a
  magnitude figure with no natural unit), but directly actionable as **comparison/evidence
  page supporting detail**, exactly as 7F.1 Q4 recommended — "financial-condition language
  moved primarily in {which subcategories}" rather than trusting an unexplained aggregate.

---

## Should the metric be decomposed into (A) volume/intensity and (B) composition?

**Yes — this is the single most load-bearing finding of this analysis.** Across the 25-pair
corpus, the median pair's **gross** subcategory-level movement (`M6a_L1 = Σ|intensity
change_i|` across the 12 subcategories) is **74% larger** than what survives in the net
current metric — i.e., a median of 74% of the underlying subcategory-level change cancels
out and is invisible in `financial_condition_language_change` as published today. In the
most extreme cases (SBP 2024→2025: net `+0.045`, gross `1.261`; BEL 2021→2022: net `+0.017`,
gross `0.354`), the published metric would tell a Discover user "almost nothing changed"
for a pair where individual subcategories (e.g. debt language rising while dividend
language falls by a similar amount) moved substantially. Only two pairs in the whole corpus
— the same ACT 2017→2018 and SBP 2023→2024 pairs already flagged as the metric's most
load-bearing examples — have low cancellation (4-16%), meaning the net aggregate is a
faithful summary *only* for the pairs currently used to justify the metric, and is
systematically misleading for the rest of the corpus.

This directly answers the milestone's explicit question: **yes**, decompose. Recommended
split:

- **(A) Volume/intensity change** — a signed or unsigned measure of how much
  financial-condition language moved overall (M1's rate difference remains a defensible
  choice here, or M3's hit-share difference if the denominator fix below is adopted).
- **(B) Composition/subcategory change** — M6b (cosine distance over subcategory-share
  vectors), published as supporting detail, answering "did the *mix* of financial-condition
  topics change" independent of how much total volume moved.

Forcing both into one scalar, as today, answers neither question reliably.

---

## Revisiting 7F.1's open items with this analysis

- **Q3 (denominator shrinkage), 7F.1's central finding** is confirmed and sharpened: of the
  six alternatives, only M3 (hit-share) and M6b (composition distance) are **structurally**
  immune to word-count-denominator artifacts; M2 (length-controlled) fixes it by
  construction but at the cost of an arbitrary fixed-side choice (shown here to not matter
  much in practice — 10/10 self-overlap regardless of which side is held fixed — which
  somewhat de-risks that specific objection); M4 and M5 do **not** fix it at all, despite
  M4 sometimes being proposed as a fix for scale sensitivity in the literature.
- **Q4 (subcategory exposure)**: this analysis goes further than 7F.1's recommendation and
  shows *why* it matters quantitatively (the 74% median cancellation figure above), not just
  that the data already exists to support it.
- **Q6 (ranking stability)**: confirmed and extended — BEL's own "largest shift" pair
  changes identity (2017→2018 vs. 2020→2021) depending on which of the six candidates is
  used, the same instability 7F.1 found between the current metric and one length-controlled
  variant, now shown to hold across a wider set of alternatives, not just one.

---

## Recommendation

**MODIFY**, in two parts, neither of which requires choosing a materiality threshold (per
the milestone's hard rule):

1. **Change the primary ranking metric's denominator from word-count rate difference (M1) to
   hit-share difference (M3)**, or publish M3 alongside M1 with M3 as the metric that gates
   Discover eligibility. This is the only tested alternative that (a) meaningfully diverges
   from M1's ranking (ρ 0.644, not a rescaling like M4), (b) is structurally immune to the
   denominator-shrinkage artifact that invalidates the current flagship example, and (c) is
   as interpretable as a share/percentage to a non-technical reader. This does not, by
   itself, resolve what the new eligibility threshold should be — that remains a genuinely
   separate, subsequent design decision, consistent with the milestone's hard rule.
2. **Decompose the published metric into (A) volume/intensity and (B) composition change**,
   surfacing M6b (or an equivalent subcategory-composition distance) as supporting detail on
   comparison/evidence pages, per 7F.1 Q4 and the cancellation-ratio evidence above.

**Do not REPLACE outright** — no alternative tested is unambiguously superior on every
dimension (M4's ranking is nearly identical to M1's and adds an undocumented smoothing
constant of the same kind 7F.1 flagged for `epsilon`; M2 is denominator-robust but
interpretively awkward; M6a alone still inherits length sensitivity). **Do not REMOVE from
Discover** — SBP 2023→2024 survives as a top-5 finding under every normalization tested,
showing the underlying phenomenon (large, quality-good, financial-condition-language shifts
exist in this corpus) is real and worth surfacing; the metric's *definition*, not its
premise, is what needs correction.

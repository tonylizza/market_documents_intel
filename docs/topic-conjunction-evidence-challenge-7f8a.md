# Track 7F.8a — Topic-Conjunction & Evidence-Gate Challenge Test

**Status**: research / analysis only. No code path, CandidateSpec, threshold, schema,
migration, taxonomy, or production data was changed. No deployment, no Neon work.

**Scope**: only the two methodological choices 7F.8 introduced for the
financial-condition (FC), governance (GOV) and uncertainty (UNC) topic metrics:

1. the conjunction magnitude rule `sign · min(|D|, |M1|)` when the legs agree, else 0;
2. the evidence statistic `net / sqrt(Σ unit_delta²)` with the floor |value| ≥ 1.

Every other 7F.8 decision stays frozen. That covers passage population, M3/M6 demotion,
the net-tone formula, the risk and disclosure-change disables, the taxonomy and the
shared-artifact architecture.

**Data**: the 7F.8 CURRENT population, unchanged. That is 24 report-side-gated pairs from 6
companies.

**Reproducibility**: `scripts/research_7f8a_topic_conjunction_evidence.py` (SELECT-only).
It reuses the 7F.8 loader and aggregation. It reproduces the 7F.8 `C_conj` and
`signflip_z` values exactly (max abs diff 0.0), and the identity in Section 5 to 4e-16. Run
it with `.venv/bin/python scripts/research_7f8a_topic_conjunction_evidence.py [--cache PATH]`.

Notation, per pair:

- `h1, h2`: the category's hit counts; `w1, w2`: eligible words; `w̄ = (w1+w2)/2`.
- **Count leg**: `D = 1000(h2−h1)/w̄`, the change in amount per 1,000 average words.
- **Density leg**: `M1 = 1000(h2/w2 − h1/w1)`, the density change per 1,000 words.
- **Unit deltas**: `d_i` is the later-minus-earlier hit change in alignment unit i.
  `net = Σd_i = h2 − h1` and `gross = Σ|d_i|`.

---

## 0. Executive summary

1. **The anchor cases do not separate the five magnitude rules.** All five share the
   sign-agreement gate. The gate alone zeroes every flat-count and whole-report-scaling
   anchor (ACT FC 2017→2018, BEL FC 2019→2020, SUR GOV 2023→2024, BEL UNC 2019→2020 and
   2020→2021). It also keeps every clean broad change. The rules differ only on
   **partially scaled pairs**, where the legs agree in sign but one leg is inflated by the
   change in report length.

2. **On those pairs, `min` is the only rule with a construct justification.**
   - The two legs are the topic change under two counterfactuals:
     - **fixed-content model**: category text does not scale with report length. The
       topic change is the amount change, D.
     - **proportional model**: category text scales with the report. The topic change is
       the excess over proportional scaling, M1.
   - Which model holds is unknown, and governance and FC text is partly mandatory,
     fixed-size content. So `min` is **the largest change that both counterfactuals
     support**.
   - The geometric and harmonic rules average the two models. That credits part of
     whichever model gives the larger number, without saying why.
   - The count-only rule admits four pairs where 77–94% of the count change is predicted
     by report-length scaling.
   - The density-only rule admits a governance pair that 7F.8 read as flat (BEL
     2018→2019). It also reports ACT GOV 2017→2018 at +1.74, when the actual amount
     change was +19 hits (+0.50).

3. **Keep `C_min`.** Rename it to describe what it is, a "length-robust topic change",
   and keep the 7F.8 thresholds (FC 0.25, GOV 0.25, UNC 0.75 per 1,000 words).

4. **The evidence statistic is not a z-score in any useful sense.**
   - It is exactly `net/gross × sqrt(n_eff)`: a directional-consistency ratio times the
     square root of the *effective number of changed passages*.
   - Under a sign-flip null it has mean 0 and variance 1. But that null is not the
     question of interest, alignment units are not exchangeable (moved content creates
     deterministic ± pairs), and a single changed passage gives exactly ±1 however large
     it is.
   - Rename it `net_to_l2_churn_ratio`.

5. **A hard evidence gate fails the single-passage materiality requirement, whichever
   measure is used.**
   - The largest single passage alone clears the magnitude threshold in 3 FC and 7 GOV
     pairs.
   - Keep that passage as the pair's only net change, with the pair's actual remaining
     churn, and it scores `|net_to_l2_churn_ratio|` 0.35–0.74 and `|net/gross|`
     0.06–0.44. It would be rejected by the 7F.8 floor and by any consistency floor of
     similar strictness.
   - Concentration and churn both lower these ratios, so they cannot tell the two apart.
     Only showing concentration and churn separately does that.

6. **Manual validation does not support a hard gate.** There are 11 reviewed findings,
   including exactly 1 FAIL.
   - The 7F.8 floor (|z| ≥ 1) was chosen after seeing those labels.
   - It rejects the single FAIL (SDL GOV 2024→2025) through the `sqrt(n_eff)` breadth
     factor. That factor penalizes short reports (SDL and SBP are about 18k words).
   - On consistency alone, the FAIL (0.25) cannot be told apart from a PASS (0.28).
   - A re-read shows that SDL's report-side governance decline (49→41 hits, shorter
     director and key-management rosters) is real. What failed in 7F.8 was the
     evidence *explanation*, which led with an alignment mis-pairing.

7. **Decision: evidence strength is a supporting diagnostic only (option C).** No hard
   gate and no threshold-based caution flag. For every finding, display the supporting
   hits, the opposing hits, `change_consistency_ratio = net/gross` (signed, in
   [−1, 1]) and the share of the largest passage.

8. **Effect on the 7F.8 Discover proposal.**
   - FC: 5 findings, unchanged. The floor removed none.
   - UNC: 1 finding, unchanged.
   - GOV: 2 → 5. ACT 2017→2018 (at +0.50, not the length-inflated +1.74), SDL
     2024→2025 and ACT 2020→2021 return, all CAUTION-grade.
   - BEL GOV 2018→2019 and SUR GOV 2023→2024 remain non-findings. The conjunction
     removes them, not the floor.

**Final status: `TOPIC_METRICS_FREEZE_READY_WITH_CAVEATS`** (Section 11).

---

## 1. Constructs

- **FC / governance**: did the category's own language change in amount, in a way not
  explained merely by the whole report growing or shrinking?
- **Uncertainty**: did uncertainty vocabulary increase both in amount and in density?

Both constructs are conjunctions of two conditions:

- an **amount** condition (D ≠ 0);
- a **beyond-scaling** condition (M1 has the same sign).

This follows from the algebra. `M1 = 1000·(h2 − h1·w2/w1)/w2`, which is the hit change
*in excess of proportional scaling*, per 1,000 later words. So:

- D answers "did the amount change?";
- M1 answers "did it change by more than report scaling predicts?".

The sign gate enforces "both". The only remaining question is how large to call the
change once both hold.

## 2. The five magnitude rules

| Rule | Magnitude means | Units | One leg tiny | Both large | Can one leg dominate? | Arbitrary composite? |
|---|---|---|---|---|---|---|
| **A. C_min** | The largest change both counterfactuals support. It is the actual amount change when length inflates density, and the excess over scaling when length inflates the count. | per 1,000 words (either leg's own) | → 0, continuously | ≈ both legs | No. It is bounded by the weaker leg. | No. It is a worst-case bound over two named counterfactuals. |
| B. C_count | The amount change. The density leg only gates the sign. | per 1,000 average words | **Jumps** from D to 0 as M1 crosses 0 (a cliff) | D | Yes, the count leg. Length-driven volume passes through. | No, but it ignores the beyond-scaling half of the construct. |
| C. C_density | The excess over proportional scaling. The count leg only gates the sign. | per 1,000 words | **Jumps** from M1 to 0 as D crosses 0 | M1 | Yes, the density leg. It assumes category text scales with the report. | No, but it ignores the amount half. |
| D. C_geo | `sqrt(D·M1)` | dimensionally per 1,000 words, with no counterfactual meaning | → 0 continuously, but only as the square root of the tiny leg | ≈ both | Partly. It credits sqrt of the larger leg. | **Yes.** |
| E. C_harm | `2·D·M1/(D+M1)`, which lies in [min, 2·min] | same as D | ≈ 2 × the tiny leg | ≈ both | No, but it doubles the weak leg as the legs diverge | **Yes.** |

On ordering: whenever the legs agree, `min ≤ harm ≤ geo ≤ max(count, density)`. The rules
coincide when `|D| ≈ |M1|`, which is the clean broad-change case. They diverge by the
length component `M1 − M1_volume = 1000·h̄·(1/w2 − 1/w1)`.

On the cliff for count and density: KP2 GOV 2019→2020 has `C_count` = −0.276, which is
eligible. Its density leg is only −0.032. A density move of +0.033 would drop the pair to
exactly 0. `min`, `geo` and `harm` all shrink smoothly to 0 as either leg approaches 0.

## 3. Empirical comparison

### 3.1 Distribution (|v|, 24 gated pairs)

| Metric | Rule | zeros | median | p75 | p90 | p95 | max | eligible at base threshold |
|---|---|---|---|---|---|---|---|---|
| FC (0.25) | **C_min** | 6 | 0.072 | 0.179 | 0.500 | 0.850 | 0.926 | **5** |
| | C_count | 6 | 0.141 | 0.301 | 0.864 | 1.064 | 1.892 | 8 |
| | C_density | 6 | 0.072 | 0.228 | 0.528 | 0.870 | 1.103 | 6 |
| | C_geo | 6 | 0.099 | 0.277 | 0.705 | 0.956 | 1.006 | 7 |
| | C_harm | 6 | 0.095 | 0.239 | 0.598 | 0.940 | 1.002 | 6 |
| GOV (0.25) | **C_min** | 7 | 0.072 | 0.163 | 0.486 | 0.854 | 1.189 | **5** |
| | C_count | 7 | 0.205 | 0.417 | 0.528 | 0.859 | 1.189 | 9 |
| | C_density | 7 | 0.090 | 0.273 | 1.065 | 1.248 | 1.736 | 7 |
| | C_geo | 7 | 0.123 | 0.266 | 0.791 | 0.976 | 1.233 | 6 |
| | C_harm | 7 | 0.102 | 0.247 | 0.682 | 0.950 | 1.232 | 5 |
| UNC (0.75, v > 0) | **C_min** | 9 | 0.232 | 0.535 | 0.729 | 0.806 | 2.619 | **1** |
| | C_count | 9 | 0.397 | 0.842 | 1.252 | 1.342 | 2.870 | 5 |
| | C_density | 9 | 0.373 | 0.673 | 0.761 | 0.993 | 2.619 | 2 |
| | C_geo | 9 | 0.428 | 0.681 | 0.884 | 0.998 | 2.741 | 3 |
| | C_harm | 9 | 0.348 | 0.675 | 0.867 | 0.963 | 2.739 | 2 |

The UNC maximum of 2.6 is a decrease (SUR 2023→2024). The tab is increase-only.

### 3.2 Rank agreement

| Metric | Rule | ρ \|v\| vs C_min | top-10 ∩ C_min | ρ (signed) vs length change |
|---|---|---|---|---|
| FC | C_count / C_density / C_geo / C_harm | 0.92 / 1.00 / 0.98 / 0.99 | 9 / 10 / 10 / 10 | 0.47 / 0.37 / 0.43 / 0.41 (C_min 0.38) |
| GOV | same order | 0.85 / 0.94 / 0.98 / 1.00 | 7 / 9 / 10 / 10 | 0.24 / 0.03 / 0.11 / 0.12 (C_min 0.12) |
| UNC | same order | 0.90 / 0.94 / 0.99 / 0.99 | 8 / 9 / 10 / 10 | 0.31 / 0.15 / 0.24 / 0.24 (C_min 0.23) |

The rules rank the corpus almost identically. **The choice matters only at the eligibility
margin**, and C_count is the most length-correlated rule.

### 3.3 Company-level largest finding (signed, direction-filtered for UNC)

| Company | FC: C_min | Differs under | GOV: C_min | Differs under | UNC: C_min | Differs under |
|---|---|---|---|---|---|---|
| ACT | 2016→2017 (−0.93) | — | 2023→2024 (−0.92) | C_density: 2017→2018 (+1.74) | 2019→2020 (+0.76) | — |
| BEL | 2017→2018 (+0.55) | C_count, C_geo: 2020→2021 (+1.89, +0.73) | 2016→2017 (+1.19) | — | 2017→2018 (+0.49) | — |
| KP2 | 2023→2024 (+0.15) | C_count: 2019→2020 | 2020→2021 (−0.22) | C_count: 2019→2020 | 2023→2024 (+0.53) | — |
| SBP | 2023→2024 (−0.90) | — | 2024→2025 (+0.10) | C_count/geo/harm: 2023→2024 | 2023→2024 (+0.58) | — |
| SDL | 2024→2025 (+0.09) | — | 2024→2025 (−0.45) | — | none | — |
| SUR | 2024→2025 (−0.37) | — | 2024→2025 (−0.02) | — | 2024→2025 (+0.54) | — |

Every divergence follows the same pattern. A single-leg or averaging rule promotes a pair
whose larger leg is inflated by report length: BEL FC 2020→2021 (the report returned to
normal length) and ACT GOV 2017→2018 (the report was 35% shorter).

### 3.4 Threshold sensitivity (eligible count, magnitude and direction only)

| × base | FC min / count / dens / geo / harm | GOV min / count / dens / geo / harm | UNC min / count / dens / geo / harm |
|---|---|---|---|
| 0.5 | 10 / 13 / 10 / 11 / 10 | 8 / 14 / 9 / 12 / 10 | 6 / 8 / 6 / 8 / 7 |
| 0.75 | 6 / 10 / 7 / 9 / 9 | 6 / 13 / 7 / 9 / 9 | 2 / 6 / 4 / 5 / 5 |
| **1.0** | **5** / 8 / 6 / 7 / 6 | **5** / 9 / 7 / 6 / 5 | **1** / 5 / 2 / 3 / 2 |
| 1.25 | 4 / 6 / 5 / 6 / 5 | 4 / 8 / 5 / 6 / 4 | 0 / 4 / 0 / 1 / 1 |
| 1.5 | 3 / 5 / 4 / 5 / 5 | 4 / 7 / 5 / 5 / 4 | 0 / 4 / 0 / 0 / 0 |
| 2.0 | 3 / 5 / 3 / 4 / 3 | 2 / 4 / 4 / 3 / 3 | 0 / 0 / 0 / 0 / 0 |

`C_min` degrades smoothly. `C_count` is the least threshold-sensitive in GOV (13 of 24
pairs at ×0.75) because it keeps pairs where the count merely scaled with the report.

### 3.5 What each alternative adds at the base threshold

"Scaling share" is the share of the observed count change that proportional scaling with
report length would predict: `(h1·w2/w1 − h1)/(h2 − h1)`. Near 1 means the count change is
almost entirely report scaling.

| Metric | Pair | Admitted by | Scaling share | C_min | Reading |
|---|---|---|---|---|---|
| FC | BEL 2018→2019 | count, geo | 0.77 | 0.141 | +30 hits, report +24%. 7F.8 already removed it. |
| FC | KP2 2019→2020 | count | 0.80 | −0.059 | −13 hits, report −10% |
| FC | ACT 2023→2024 | count | 0.35 | 0.176 | +13 hits. Modest, below threshold under min. |
| FC | ACT 2019→2020 | density, geo, harm (edge 0.250) | −1.03 | −0.189 | −7 hits while the report grew. Density is length-amplified. |
| GOV | BEL 2018→2019 | **density (−1.07), geo (−0.39)** | −7.6 | −0.139 | **7F.8 read: governance flat (171→165)** |
| GOV | BEL 2017→2018 | count | 0.94 | 0.032 | +19 hits, of which proportional scaling predicts about 18 |
| GOV | KP2 2019→2020 | count | 0.89 | −0.032 | as above |
| GOV | ACT 2021→2022 | count | 0.77 | 0.117 | as above |
| GOV | ACT 2019→2020 | count | 0.63 | 0.144 | as above |
| GOV | KP2 2020→2021 | density | −0.31 | −0.220 | −10 hits. Density slightly amplified. |
| UNC | SBP 2023→2024 | count, geo, harm | 0.47 | 0.578 | +20 hits in a small report. The leg-averaging rules lift it over 0.75. |
| UNC | SUR 2024→2025, BEL 2017→2018, ACT 2021→2022 | count (+geo for BEL) | 0.40–0.85 | 0.16–0.54 | length-supported volume |
| UNC | KP2 2023→2024 | density | −0.41 | 0.533 | +25 hits (D 0.53). The report shrank slightly, which inflates density. |

`C_min` admits no unreviewed pair and no pair that 7F.8 read as a non-event. All its
eligible findings (FC 5, GOV 5, UNC 1) have existing manual reviews.

## 4. Anchor behaviour

| Metric | Pair | hits | Δlen | D | M1 | min | count | density | geo | harm |
|---|---|---|---|---|---|---|---|---|---|---|
| FC | ACT 2017→2018 | 90→89 | −0.42 | −0.026 | +1.002 | 0 | 0 | 0 | 0 | 0 |
| FC | SBP 2023→2024 | 71→55 | +0.06 | −0.902 | −1.103 | −0.902 | −0.902 | −1.103 | −0.997 | −0.992 |
| FC | BEL 2019→2020 | 117→67 | −0.60 | −1.348 | +0.149 | 0 | 0 | 0 | 0 | 0 |
| FC | BEL 2020→2021 | 67→137 | +0.59 | +1.892 | +0.278 | **+0.278** | **+1.892** | +0.278 | +0.726 | +0.485 |
| FC | ACT 2016→2017 | 142→90 | −0.07 | −1.092 | −0.926 | −0.926 | −1.092 | −0.926 | −1.006 | −1.002 |
| GOV | ACT 2017→2018 | 96→115 | −0.42 | +0.500 | +1.736 | **+0.500** | +0.500 | **+1.736** | +0.931 | +0.776 |
| GOV | BEL 2018→2019 | 171→165 | +0.24 | −0.139 | −1.070 | −0.139 | −0.139 | **−1.070** | **−0.386** | −0.246 |
| GOV | BEL 2016→2017 | 111→152 | −0.02 | +1.189 | +1.279 | +1.189 | +1.189 | +1.279 | +1.233 | +1.232 |
| GOV | ACT 2023→2024 | 149→106 | +0.05 | −0.917 | −1.055 | −0.917 | −0.917 | −1.055 | −0.983 | −0.981 |
| GOV | SUR 2023→2024 | 152→152 | −0.04 | 0 | +0.092 | 0 | 0 | 0 | 0 | 0 |
| UNC | BEL 2019→2020 | 366→254 | −0.60 | −3.019 | +2.175 | 0 | 0 | 0 | 0 | 0 |
| UNC | BEL 2020→2021 | 254→349 | +0.59 | +2.568 | −2.495 | 0 | 0 | 0 | 0 | 0 |
| UNC | ACT 2019→2020 | 275→325 | +0.07 | +1.349 | +0.760 | +0.760 | +1.349 | +0.760 | +1.012 | +0.972 |
| UNC | SBP 2023→2024 | 163→183 | +0.06 | +1.127 | +0.578 | +0.578 | +1.127 | +0.578 | +0.807 | +0.764 |

Acceptance criteria:

- **Zero on a flat count with denominator-only density movement** (ACT FC 2017→2018, SUR
  GOV 2023→2024): all five rules pass. The sign gate does the work.
- **Suppress whole-report scaling where the legs disagree** (BEL FC 2019→2020, BEL UNC
  2019→2020 and 2020→2021): all five pass.
- **Retain clean broad changes** (BEL GOV 2016→2017, ACT GOV 2023→2024, ACT FC
  2016→2017, SBP FC 2023→2024): all five pass, and the rules agree within 10%.

The criteria that tell the rules apart are the **partially scaled** anchors:

- **BEL FC 2020→2021.** C_count makes it the corpus's largest FC event (+1.89), yet 81%
  of the count change is the report returning to its normal length.
- **ACT GOV 2017→2018.** C_density reports +1.74, but the amount change is +19 hits
  (+0.50), and the rest is the 35% shrink applied to fixed governance content.
- **BEL GOV 2018→2019.** C_density and C_geo make a flat category (171→165) eligible.
  C_harm lands 0.004 below the threshold.

`C_min` is the only rule that handles all three as the construct requires.

## 5. What the 7F.8 evidence statistic actually is

`E = net / sqrt(Σ d_i²)`, over the alignment units with d_i ≠ 0.

- **Numerator**: `net = Σ d_i = h2 − h1`, the category's raw hit change. The units
  partition the population, so this is exact.
- **Denominator**: the L2 norm of the per-unit hit changes, a churn measure weighted
  toward large movers.
- **Range**: `|E| ≤ sqrt(n)` by Cauchy–Schwarz, where n is the number of changed units.
  Equality holds only when every unit moves by the same amount in the same direction.
- **Exact identity** (verified to 4e-16):

      E = (net / gross) × sqrt(n_eff),    n_eff = (Σ|d_i|)² / Σd_i²  ∈ [1, n]

  Here `net/gross` is directional consistency, and `n_eff` is the effective number of
  changed passages (a participation ratio). **E conflates consistency with breadth.**
- **Dependence on unit count**: the same +12 hits give E = 1.00 in one passage, 2.00
  spread over 4 passages, and 3.46 spread over 12. So fragmentation raises E, including
  artificial fragmentation from how passages were segmented.
  - A floor of |E| ≥ 1 is equivalent to `|net/gross| ≥ 1/sqrt(n_eff)`.
  - At the median n_eff (FC 28, GOV 30, UNC 72), that is a consistency floor of 0.19,
    0.18 and 0.12.
  - For a short report such as SDL (n_eff 9) it is 0.33.
  - So the same "1.0" is stricter for short reports and for less fragmented categories.
- **Dependence on concentration**: one passage with no other churn gives exactly ±1.0,
  however large it is. Any unrelated churn anywhere else in the pair pushes it below 1.
- **Many offsetting changes**: they drive both the numerator and E toward 0. That is the
  correct direction for churn, but see concentration above.
- **One large substantive passage**: `E = d/sqrt(d² + q)` where q is everyone else's
  squared churn, so it is always < 1 when any churn exists.
- **Independence of unit deltas**:
  - The lag-1 correlation of adjacent deltas, ordered by page, is near zero (Pearson FC
    0.01, GOV 0.04, UNC 0.05), so there is little local serial dependence.
  - But dependence is **structural**. Moved or mis-paired content produces deterministic
    ± pairs, and exactly equal-magnitude REMOVED/NEW pairs number 45 (FC), 48 (GOV) and
    157 (UNC) across the corpus. That is an upper bound, since small magnitudes coincide
    by chance.
  - SDL GOV 2024→2025 is one instance: the Board of Directors passage was mis-paired as
    SUBSTANTIALLY_MODIFIED (−6), then re-appears as NEW (+5).
- **Inferential interpretation**:
  - Conditional on the |d_i|, and treating each sign as an independent fair coin, E has
    mean 0 and variance 1. So it is the net standardized by its sign-flip randomization
    SD.
  - That is the only sense in which it is "z-like", and it does not justify inference:
    1. The null ("each passage's direction is a coin flip") is not the construct
       question. Real reorganizations and moves violate it.
    2. With few effective units the randomization distribution is far from normal. For a
       single changed unit it is {−1, +1}, so the exact p-value is 1.0 at any size.
    3. The floor |E| ≥ 1 corresponds to about p = 0.32 (two-sided, normal approximation).
       That is not evidence by any convention.
    4. The same data set the magnitude.

**Conclusion**: E is a descriptive ratio, not a z statistic. If it is retained anywhere, it
should be named **`net_to_l2_churn_ratio`**. It should not be published, because it mixes
two things users need to see separately.

## 6. Evidence measures compared

| Measure | Definition | Range | Unit-count dependence | Concentration | Churn | Moved content (±k) |
|---|---|---|---|---|---|---|
| A. net / L2 | `net/sqrt(Σd²)` | ±sqrt(n) | **grows with sqrt(n_eff)** | lowered | lowered | lowered |
| B. net / gross | `net/Σ\|d\|` | [−1, 1] | none | unaffected by itself; lowered only if the rest churns | lowered | lowered (correctly) |
| C. dominant-unit share | `max\|d\|/Σ\|d\|` | (0, 1] | falls as 1/n for even spread | **measures it** | lowered | 0.5 for a pure move |
| D. same- vs opposing-sign units / hits | counts | — | raw counts | invisible | **measures it** | visible as one of each |
| E. none | magnitude only | — | — | — | — | — |

Empirical relationships (24 gated pairs):

| Metric | median changed units | median n_eff | ρ(\|A\|, \|B\|) | ρ(\|A\|, n_eff) | ρ(\|A\|, C) | pairs with \|A\| ≥ 1 | pairs with \|B\| ≥ 0.25 |
|---|---|---|---|---|---|---|---|
| FC | 46 | 28 | 0.98 | −0.01 | 0.08 | 8 | 7 |
| GOV | 50 | 30 | 0.94 | −0.09 | 0.06 | 8 | 6 |
| UNC | 118 | 72 | 0.95 | 0.23 | −0.17 | 13 | 7 |

Within one category, A and B rank pairs almost identically, because n_eff varies modestly.
They differ where n_eff is atypical (short reports, concentrated changes), which is exactly
where a gate bites.

**Every topic finding in this corpus is diffuse.** The largest single passage is at most
19% of gross movement (the largest-passage share, `top1`, ranges 0.04–0.19). So C and D are
uninformative as gates here: `top1 ≤ 0.5` and "more same-sign units than opposing" retain
every finding.

## 7. Single-passage materiality test

**Requirement**: the evidence measure must not automatically reject a genuinely material
change merely because it is concentrated.

**Topic counterfactual.** Take each pair's largest alignment unit. Treat it as the pair's
only net change, keeping the pair's remaining churn (assumed net-zero).

| Metric | Pair | Largest unit Δhits | D if alone | other changed units | net / L2 | net / gross |
|---|---|---|---|---|---|---|
| FC | BEL 2020→2021 | +12 | 0.32 | 45 | 0.49 | 0.10 |
| FC | SBP 2023→2024 | −5 | 0.28 | 17 | −0.56 | −0.16 |
| FC | SDL 2024→2025 | −6 | 0.34 | 11 | −0.53 | −0.19 |
| GOV | ACT 2017→2018 | +11 | 0.29 | 51 | 0.48 | 0.09 |
| GOV | ACT 2018→2019 | +9 | 0.27 | 55 | 0.46 | 0.08 |
| GOV | ACT 2019→2020 | +12 | 0.32 | 52 | 0.59 | 0.12 |
| GOV | BEL 2019→2020 | −13 | 0.35 | 48 | −0.49 | −0.09 |
| GOV | BEL 2020→2021 | −10 | 0.27 | 62 | −0.35 | −0.06 |
| GOV | SBP 2024→2025 | +8 | 0.44 | 4 | 0.74 | 0.44 |
| GOV | SDL 2024→2025 | −6 | 0.34 | 14 | −0.57 | −0.19 |

In 10 of 48 FC/GOV pair-categories, one passage alone can clear the magnitude threshold.
**Every one of them would fail the 7F.8 floor.** Every one except SBP GOV 2024→2025 (only 4
other changed units) would also fail a net/gross floor at the 0.25 level. For uncertainty, no single passage can reach 0.75, so
this cannot arise there.

**Risk-audit exemplars (conceptual).** These are the two single-passage risk changes 7F.8
rated PASS, scored for the risk category over all alignment units:

- **KP2 2020→2021**: the auditor's going-concern material-uncertainty paragraph was
  removed (a REMOVED unit, −7). The net is −5 against a gross of 47, giving net / L2
  −0.38 and net / gross −0.11. Ordinary churn elsewhere in the report buries the most
  material single-passage change in the audit.
- **BEL 2019→2020**: a new supply-chain continuity section. The pair-level risk net is
  −17, because the report halved. A pair-level ratio says nothing about one new section.

**Distinction.** Concentration ("the change is in one place") and churn ("changes point
both ways") are different properties. Both A and B go down under either. So neither can
serve as a gate that rejects churn while sparing concentration. Showing them **separately**
works: supporting and opposing hits for churn, the largest passage's share for
concentration.

## 8. Manual validation

These are the reviewed findings that are magnitude-eligible under C_min: 4 PASS, 6
CAUTION and 1 FAIL across FC, GOV and UNC. The 7F.8 "not a topic event" anchors are all 0
under the sign gate, so they need no evidence rule.

| Evidence rule | PASS retained | CAUTION retained | FAIL retained |
|---|---|---|---|
| E. no floor | 4/4 | 6/6 | 1/1 |
| A. \|net/L2\| ≥ 1 (7F.8) | 4/4 | 4/6 | 0/1 |
| B. \|net/gross\| ≥ 0.25 | 4/4 | 2/6 | 1/1 |
| B. \|net/gross\| ≥ 1/3 | 2/4 | 1/6 | 0/1 |
| C. top1 ≤ 0.5 | 4/4 | 6/6 | 1/1 |
| D. same-sign units > opposing | 4/4 | 6/6 | 1/1 |

| Metric | Pair | Manual | C_min | net/L2 | net/gross | n_eff | units same/opp |
|---|---|---|---|---|---|---|---|
| FC | ACT 2016→2017 | CAUTION | −0.926 | −2.16 | −0.32 | 45 | 46/34 |
| FC | SBP 2023→2024 | CAUTION | −0.902 | −1.79 | −0.50 | 13 | 13/5 |
| FC | BEL 2017→2018 | PASS | +0.554 | 1.37 | 0.28 | 24 | 25/16 |
| FC | SUR 2024→2025 | CAUTION | −0.374 | −1.26 | −0.19 | 43 | 37/28 |
| FC | BEL 2020→2021 | PASS | +0.278 | 2.83 | 0.58 | 24 | 34/12 |
| GOV | BEL 2016→2017 | PASS | +1.189 | 2.11 | 0.32 | 44 | 38/23 |
| GOV | ACT 2023→2024 | PASS | −0.917 | −2.16 | −0.34 | 41 | 42/21 |
| GOV | ACT 2017→2018 | CAUTION | +0.500 | 0.83 | 0.16 | 27 | 29/23 |
| GOV | SDL 2024→2025 | FAIL (see below) | −0.452 | −0.76 | −0.25 | **9** | 10/5 |
| GOV | ACT 2020→2021 | CAUTION | −0.269 | −0.94 | −0.16 | 35 | 27/22 |
| UNC | ACT 2019→2020 | CAUTION | +0.760 | 1.72 | 0.18 | 96 | 93/66 |

Reading:

- **Consistency does not separate the labels.** PASS net/gross is 0.28–0.58, CAUTION is
  0.16–0.50, and the FAIL is 0.25.
- The CAUTION reasons were content-level: legal share-terms text, section restructuring,
  label-heavy passages, thin evidence. None of these is churn.
- Rule A's clean-looking 4/4, 4/6, 0/1 is **in-sample**, because 7F.8 chose the floor
  after these reviews. Its one FAIL rejection comes from the `sqrt(n_eff)` factor
  (n_eff 9 for an 18k-word report), not from consistency.
- With 11 labels and a single FAIL, **no cutoff can be validated** on this corpus.

**SDL GOV 2024→2025 re-read.**

- Report-side governance hits went 49→41 (17,607→17,759 words). That decline is real:
  - director biographies were shortened (the Information on Directors unit −4);
  - key-management lists were condensed (−3, −1);
  - one director biography was added (+4, AMBIGUOUS).
- The 7F.8 FAIL came from the **explanation**. The largest two units are one Board of
  Directors passage, mis-paired as SUBSTANTIALLY_MODIFIED with a tenements passage (−6),
  that re-appears as NEW (+5). They net to −1.
- The magnitude is correct (−0.45 per 1,000 words, D ≈ M1, so no scaling). The finding is
  thin (8 hits), which makes it CAUTION-grade, not an artifact.
- The failure mode is **evidence display trusting alignment**. That is fixed by how the
  evidence is shown (Section 9), not by an eligibility gate on a report-side metric.

## 9. Threshold role — decision

**C. Supporting diagnostic only.** Evidence strength is not a hard gate, and there is no
threshold-based caution flag.

Why not a hard gate:

1. It fails the single-passage materiality requirement for *every* candidate ratio
   (Section 7).
2. FC, GOV and UNC are **report-side** metrics: counts and densities per side. Their
   magnitude does not depend on alignment. A gate built from alignment units imports
   alignment errors (moved and mis-paired content) into eligibility, the very dependency
   7F.8 disabled the risk and disclosure metrics over.
3. Every available cutoff is corpus-calibrated on 11 labels with 1 FAIL. None has a
   theoretical grounding. The 7F.8 z = 1 reading as "one standard error" does not survive
   Section 5.

Why not a soft caution flag (B): a flag still needs a cutoff, and the same objection
applies. The measures also do not separate PASS from CAUTION (Section 8), so a flag would
be noise presented as signal.

What to show with every FC, GOV and UNC finding, all descriptive and all from alignment
units:

- **supporting hits / opposing hits** (and passages). Example: "+85 hits across 38
  passages, −44 across 23". This is the plain-language churn view.
- **`change_consistency_ratio`** = net / gross, signed, in [−1, 1]. It is independent of
  passage count.
- **`largest_passage_share`** = max|d| / gross, the concentration view.
- The existing report-side context: h1→h2, the density change, the report-length change
  and the top subcategories.

Display caveat: evidence listings should present each side's highest-hit passages rather
than lean only on alignment-unit deltas. When a unit is REMOVED/NEW or
SUBSTANTIALLY_MODIFIED with low confidence, it should be labelled as possibly moved, so
the SDL-style mis-pairing is not presented as the explanation.

`net_to_l2_churn_ratio` (the 7F.8 statistic) is **not published**.

## 10. Final topic-metric decision

| Metric | Magnitude rule | Name | Threshold (per 1,000 words) | Direction | Evidence statistic | Evidence role |
|---|---|---|---|---|---|---|
| Financial condition | `C_min`: `sign(D)·min(\|D\|,\|M1\|)` if signs agree, else 0 | `financial_condition_topic_change` | 0.25 | both | `change_consistency_ratio`, supporting/opposing hits, `largest_passage_share` | supporting diagnostic only |
| Governance | `C_min` | `governance_topic_change` | 0.25 | both | same | supporting diagnostic only |
| Uncertainty | `C_min` | `uncertainty_topic_change` | 0.75 | increase only | same | supporting diagnostic only |

The thresholds are the 7F.8 values: 10% of the corpus-median category density, rounded to
the nearest 0.25. Their rule is construct-anchored and independent of the combination
rule, so they are not recalibrated here.

Resulting Discover eligibility (report-side gate + direction + magnitude):

| Metric | 7F.8 proposal (with floor) | 7F.8a | Change |
|---|---|---|---|
| FC | ACT 2016→2017, SBP 2023→2024, BEL 2017→2018, SUR 2024→2025, BEL 2020→2021 | same 5 | none |
| GOV | BEL 2016→2017, ACT 2023→2024 | + ACT 2017→2018 (+0.50), SDL 2024→2025 (−0.45), ACT 2020→2021 (−0.27) | 2 → 5, adds SDL |
| UNC | ACT 2019→2020 | same | none |

Interpretation changes relative to 7F.8:

- **ACT GOV 2017→2018 returns as a modest own-count increase** (+19 hits, shown at
  +0.50). 7F.8 excluded it only through the floor. Its churn (+69/−50 hits) is shown
  alongside.
- The historical "+1.74 governance shift" reading remains wrong: that figure was the
  length-inflated density leg.
- BEL GOV 2018→2019 and SUR GOV 2023→2024 remain non-findings, removed by the conjunction.
- ACT GOV 2020→2021 sits at the threshold edge. 7F.8 §7 found that it crosses to −0.245
  under the CLEANED diagnostic population.

Consistency note (not a recalibration): 7F.8 also attached |z| ≥ 1 to net tone. There it
removed nothing, because every pair it excluded is already below the 2.25 threshold. The
implementation batch should drop it there too, so the statistic is used the same way
everywhere.

Implementation deltas relative to 7F.8 §21 (for the future batch; nothing implemented
here):

- Replace the `{…}_evidence_z` columns with `{…}_supporting_hits`, `{…}_opposing_hits`,
  `{…}_change_consistency_ratio` and `{…}_largest_passage_share`.
- Drop the `evidence_ok` CandidateSpec hook.
- Unit tests should cover the Section 5 identity and the C_min continuity and zero cases.

## 11. Freeze status

**`TOPIC_METRICS_FREEZE_READY_WITH_CAVEATS`**

- **Frozen**:
  - `C_min` as the magnitude rule for FC, GOV and UNC;
  - the 7F.8 thresholds;
  - evidence as a supporting diagnostic only, under the names above;
  - `net_to_l2_churn_ratio` kept out of the product.
- **Caveats that travel with the freeze**:
  - The thresholds are provisional on a 24-pair, 6-company corpus.
  - GOV ACT 2020→2021 and UNC ACT 2019→2020 sit at the threshold edge.
  - 3 of the 5 GOV findings and all UNC findings are CAUTION-grade. Findings are
    published with visible churn context rather than filtered.
  - The alignment-trusting evidence display must be fixed before those findings are shown
    (Section 9 display caveat).
  - `C_min`'s selection rests on the construct argument (the bound robust to both
    counterfactuals). The data only corroborate it: it is the one rule that admits no
    unreviewed pair and no pair 7F.8 read as a non-event. That corroboration comes from a
    small corpus.

No further topic research is required to freeze. Revisit the thresholds when the corpus
grows, as 7F.8 §23 already records.

## 12. Production discipline

No production changes, no Neon project, no Vercel deployment, no migrations, no runtime
code changes. The only new files are this document and the read-only research script.

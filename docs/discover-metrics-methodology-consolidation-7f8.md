# Track 7F.8 — Discover Metrics Methodology Consolidation

**Status**: research / analysis only. No code path, CandidateSpec, threshold, schema,
migration, taxonomy, or production data was changed. No deployment, no Neon work.

**Data**: local research database, current language-signal run per pair
(`get_current_language_signal_runs_by_pair`, same rule as 7F.1–7F.7a), 25 pairs, 6
companies (ACT, BEL, KP2, SBP, SDL, SUR), 30 unique reports, 12,110 feature-eligible
primary-narrative passage rows, 2,029,004 words. 24 pairs pass the report-side gate
(ACT 2016→2024, a 96-month gap, is excluded). 23 pairs pass the alignment-change gate.

**Reproducibility**: `scripts/research_7f8_discover_metrics_consolidation.py` (SELECT-only).
Every production metric it reconstructs matches the persisted column exactly: the maximum
absolute difference is 0.0 for `net_tone_change`, `uncertainty_intensity_change`,
`financial_condition_share_change`, `governance_share_change`,
`governance_language_change`, `risk_language_introduction` and `risk_language_removal`,
and 1e-16 for `disclosure_change_score`. Run it with
`.venv/bin/python scripts/research_7f8_discover_metrics_consolidation.py [--cache PATH]`.

Notation, per pair: `h1, h2` are the category hit counts (earlier, later). `w1, w2` are the
`feature_eligible_primary` words. `H1, H2` are the total custom-taxonomy hits (risk +
financial_condition + governance + strategy). `w̄ = (w1+w2)/2`.

---

## 0. Executive summary

1. **The "denominator problem" was mainly a construct problem, not a passage-population
   problem.** The eligible population already has a hard 40-word floor. Transparent
   low-information rules (TOC-like, numeric-heavy, duplicates, page furniture, table
   residue) flag only **1.2%** of eligible words (at most 5.8% for any one report). Every
   candidate formula keeps ρ ≥ 0.98 between the CURRENT and CLEANED populations, and no
   proposed metric changes sign.

2. **The report-length swings are real.** BEL 2020 is 72 pages against 124 on either side,
   and ACT 2018 is 118 pages against 146. So "report got shorter" is a real publication
   event, not an extraction defect, and any topic metric must decide whether a whole-report
   contraction counts as a topic shift.

3. **M3 (taxonomy share) did not remove compositional artifacts. It relocated and slightly
   increased them.** The density difference M1 splits exactly into an own-count part and a
   length part, and the share difference M3 splits exactly into an own-count part and an
   other-categories part (both Shapley). Against the category's own hit change:
   - **M3 points the wrong way in 9/24 FC pairs and 8/24 governance pairs.** M1 does so in
     6/24 and 5/24.
   - The median share of each metric's movement that comes from outside the category is
     **0.53 (FC) and 0.57 (governance) for M3**, against 0.39 and 0.45 for M1.
   - The two share metrics are also mechanically coupled across Discover tabs (FC share vs
     governance share ρ = −0.46).

4. **Pure volume normalizations (raw count, pair-mean, company-median, corpus-median) mostly
   detect report-length change.** They correlate 0.65 (FC) and 0.49 (governance) with
   length change. Their top findings are BEL 2019→2020 and 2020→2021, where every taxonomy
   category halved and then doubled with the report.

5. **Recommended topic metric (FC, governance, uncertainty): the "topic-specific change" C.**
   It counts a change only when the category's own count change (per 1,000 pair-average
   words) and its density change (per 1,000 words) agree in sign. Its magnitude is the
   smaller of the two. It is zero when the category's own language is flat (ACT FC
   2017→2018, SUR governance 2023→2024) and small when the category merely scaled with the
   report (BEL 2019→2020).

6. **Add an evidence floor.** A within-pair sign-flip statistic
   `z = net / sqrt(Σ unit_delta²)` over alignment units measures whether the net change
   exceeds the passage-level churn. Governance findings with |z| < 1 were exactly the ones
   manual review rated CAUTION or FAIL.

7. **Net tone keeps its formula. Its threshold and copy change.** Count and density agree
   (ρ = 0.99), and cleaning does not move it. But most net-tone variance comes from the
   *positive* component (var 5.79 against 1.23 for negative), so "tone shifted more
   negative" usually means "fewer positive words".

8. **Uncertainty needs the conjunction.** Count and density disagree in 8/24 pairs. The only
   currently eligible uncertainty finding (BEL 2019→2020, +2.18) happened while uncertainty
   hits *fell* from 366 to 254.

9. **Risk introduction/removal should be disabled pending upstream fixes.**
   - The data are extremely sparse: 45 introduction hits and 58 removal hits across the
     entire gated corpus.
   - **22 of the 58 removal hits and 8 of the 45 introduction hits sit in passages that
     reappear nearly word for word on the other side** (alignment misses).
   - The #1 removal finding (KP2 2022→2023, rated PASS in 7F.6) is entirely Note 14 tables
     that moved.
   - Of the currently live findings, 2 are real, 4 are CAUTION and 3 are FAIL.
   - Single passages *can* be material: an auditor's going-concern material-uncertainty
     paragraph was removed. The defect is the validity of the NEW/REMOVED status, not small
     counts as such.

10. **The disclosure-change score should stay disabled pending upstream alignment-quality
    work.** The feature gate fails 25/25 pairs because the LOW/NEEDS_REVIEW confidence share
    is 0.35–0.83 against a 0.25 ceiling, and document_quality fails 17/25 on a
    metric-disagreement rule that fires almost by construction. The weights are not the
    issue: rankings are nearly invariant to them (ρ ≥ 0.986). The score tracks plain
    document-level (1 − TF-IDF cosine) at ρ = 0.95.

11. **Data-integrity flag (out of scope, must be resolved before cutover).** KP2's report
    registered with period_end 2024-12-31 has the fiscal label "YEAR ENDED 31 DECEMBER
    2025" and publication date 2026-03-24. Its text says "31 December 2025" 40 times and
    "31 December 2024" 7 times. It was "manually corrected" to 2024. This track does not
    infer the correct date.

**Final verdict: `METHODOLOGY_FREEZE_READY_WITH_CAVEATS`** (Section 24).

---

## 1. Target constructs (defined before evaluating formulas)

| Metric | Target estimand (one sentence) |
|---|---|
| Financial-condition change | Did the report's own financial-condition language change in amount **in a way not explained by the report simply growing or shrinking**? |
| Governance change | Same construct, for governance language. |
| Net tone change | Did the balance of Loughran-McDonald positive vs negative vocabulary *per word of narrative* fall materially? (An intensive, length-free property.) |
| Uncertainty change | Did uncertainty vocabulary increase both in amount and as a share of the narrative? |
| Risk introduction | Did the later report add risk-language passages that genuinely did not exist before? |
| Risk removal | Did the later report drop risk-language passages that genuinely no longer exist? |
| Disclosure-change score | What share of the narrative was materially rewritten, added or removed? |

Three distinct constructs exist for the topic metrics, and this track keeps them separate:

- **Volume**: did the report say more or less about X? (`h2 − h1`, scaled)
- **Prominence / density**: does X take up more or less of the narrative? (`h/w`)
- **Taxonomy share**: is X a larger or smaller part of *classified topic language*? (`h/H`)

The Discover label "X-language shift" implies something happened *to X-language*. A pair
where X-text is unchanged (ACT FC 2017→2018: 90→89 hits) should not headline an X shift.
Neither should a pair where X-text merely scaled with the whole report (BEL 2019→2020:
every category roughly halved). Volume alone fails the second test; density and share alone
fail the first. This is the reasoning behind the conjunction metric (Section 3).

---

## 2. Passage-population audit

**What contributes to `feature_eligible_primary_words`**: passages in a primary
`PassageAlignment` row that are both

- `primary_narrative_eligible`: not in the six structured-content exclusion categories
  (`short_fragment_invalid`, `broken_fragment_sequence`, `numeric_or_table_like_source`,
  `contents_or_index_like`, `caption_or_label_like`, `financial_table_rendered_as_prose`);
  and
- `feature_eligible`: `word_count ≥ 40` (`FeatureConfig.minimum_feature_passage_words`),
  with no exemption for low-information or heading-only passages.

No passage is counted twice per side: the table has 12,110 rows and 12,110 distinct (run,
passage, side) keys. Every report's eligible word count is identical across the pairs it
appears in (0 of 30 reports differ).

**Length distribution** (12,110 rows):

| min | p1 | p5 | p10 | median | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|---|---|
| 40 | 41 | 46 | 52 | 146 | 301 | 339 | 391 | 400 |

| Below | 3 w | 5 w | 10 w | 20 w | 40 w | 60 w | 80 w |
|---|---|---|---|---|---|---|---|
| Passages | 0 | 0 | 0 | 0 | 0 | 1,818 | 3,200 |
| Word share | 0 | 0 | 0 | 0 | 0 | 4.4% | 9.0% |

Heading-only passages cannot exist in this population: every `HEADING_WITH_BODY` row
(7,551 in total) has a body of at least 20 words after its heading. TOC fragments are
already removed by `contents_or_index_like`.

**CLEANED_DIAGNOSTIC rules** (`cleaning_flags`, diagnostic only):

| Rule | Definition | Rows | Word share of corpus |
|---|---|---|---|
| `toc_like` | dotted leaders or ≥3 "page N" references | 63 | 0.53% |
| `intra_report_duplicate` | same `content_hash` already seen in that report | 40 | 0.25% |
| `numeric_heavy` | ≥30% numeric tokens | 33 | 0.16% |
| `furniture_dominated` | ≥50% of 6-word shingles recur in ≥2% (and ≥8) of that report's passages | 29 | 0.07% |
| `low_alpha` | <60% tokens contain letters | 22 | 0.12% |
| `table_residue_category` | `table_context` / `currency_exposure_table_mixed` | 12 | 0.11% |
| **Any rule** | | **~190** | **1.21%** |

Per report, the excluded word share is 0–1.8% for 27 of 30 reports. The exceptions are
ACT 2023 (5.8%, 14 duplicated passages), SUR 2023 (3.0%, a repeated navigation band) and
KP2 2020 (2.0%). The full per-report table is in script Section 1.

**Rule precision caveat**: `toc_like` also catches genuine narrative containing "refer to
page N" cross-reference lists. The rules are deliberately transparent, not tuned.

**Result, for the metric-design question**: across all candidate formulas for FC and
governance, CURRENT vs CLEANED gives ρ = 0.979–0.996, top-10 overlap of 9–10/10, and at
most one sign flip (none for any proposed metric). The largest single effect is SUR
2023→2024 uncertainty, whose density change moves from −2.62 to −2.00. That pair is a
decrease, so it is outside the increase-only tab either way. **The apparent denominator
problem is roughly entirely metric design (construct choice) combined with real
report-length variation. Passage quality contributes little.** No eligibility-rule change
is recommended.

---

## 3. Financial-condition candidates

N = 24 gated pairs. "ρ vs M3" is the Spearman correlation of |value| with |M3|, the
current metric. "CUR/CLN" compares the CURRENT and CLEANED populations.

| Candidate | Formula | Units | Median | max\|v\| | MAD | p75 | p90 | p95 | ρ vs M3 | top-10 vs M3 | ρ CUR/CLN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| FC-A raw | `h2−h1` | hits | 0 | 70 | 7.5 | 17.8 | 44.0 | 51.7 | 0.52 | 7 | 0.985 |
| FC-B M1 | `1000(h2/w2−h1/w1)` | per 1k words | 0.002 | 1.10 | 0.161 | 0.317 | 0.814 | 0.990 | 0.61 | 6 | 0.990 |
| FC-C M2 | `1000(h2−h1)/w1` | per 1k earlier words | 0.003 | 2.69 | 0.192 | 0.487 | 1.004 | 1.053 | 0.56 | 7 | 0.991 |
| FC-D pair-mean (AM) | `1000(h2−h1)/w̄` | per 1k avg words | −0.001 | 1.89 | 0.183 | 0.454 | 1.035 | 1.309 | 0.55 | 7 | 0.993 |
| FC-D (HM, GM) | harmonic / geometric mean | same | ≈ AM | 2.08 / 1.98 | — | — | — | — | 0.55 | 7 | 0.993 |
| FC-E company median | `1000(h2−h1)/median_w(company)` | per 1k typical words | 0 | 1.84 | 0.159 | 0.463 | 1.128 | 1.302 | 0.51 | 7 | 0.987 |
| FC-F corpus median | `1000(h2−h1)/44,614.5` | per 1k corpus words | 0 | 1.57 | 0.168 | 0.398 | 0.986 | 1.159 | 0.52 | 7 | 0.985 |
| FC-G M3 (current) | `h2/H2−h1/H1` | share | −0.004 | 0.100 | 0.023 | 0.042 | 0.059 | 0.071 | 1 | 10 | 0.990 |
| FC-H log ratio | `ln(h2/h1)` | log | 0.001 | 0.72 | 0.078 | 0.258 | 0.436 | 0.542 | 0.52 | 7 | 0.987 |
| FC-H log-density ratio | `ln((h2/w2)/(h1/w1))` | log | 0 | 0.41 | 0.070 | 0.118 | 0.327 | 0.379 | 0.60 | 6 | 0.987 |
| FC-I topic mix (M6b) | cosine distance of subcategory shares | [0,1] | 0.021 | 0.093 | 0.014 | 0.046 | 0.081 | 0.089 | 0.34 | 6 | 0.983 |
| **FC-C\* conj (proposed)** | `sign·min(\|D_AM\|,\|M1\|)` if signs agree, else 0 | per 1k words | 0 | 0.93 | 0.072 | 0.179 | 0.500 | 0.850 | 0.74 | 8 | 0.977 |

**Exact decompositions** (they hold for every pair, by algebra):

- `M1 = 1000·Δh / HM(w1,w2)  +  1000·h̄·(1/w2 − 1/w1)`, which is the volume part plus the
  length part. The harmonic-mean-normalized count change is precisely the Shapley
  own-count component of M1.
- `M3 = own part (h moves, other categories fixed) + other part (other categories move)`,
  by two-path Shapley.

Anchor cases (FC):

| Pair | h | w | M1 | M1 volume / length | M3 | M3 own / other | Conj | z | Reading |
|---|---|---|---|---|---|---|---|---|---|
| ACT 2017→2018 | 90→89 | 45,963→30,068 | +1.002 | −0.028 / **+1.029** | +0.018 | −0.002 / **+0.020** | **0** | −0.06 | FC text unchanged. Both M1 and M3 moved only because *other* content moved. |
| SBP 2023→2024 | 71→55 | 17,246→18,247 | −1.103 | −0.902 / −0.200 | −0.073 | −0.063 / −0.010 | **−0.902** | −1.79 | Genuine own-count decline. |
| BEL 2020→2021 | 67→137 | 26,004→47,989 | +0.278 | +2.075 / −1.797 | +0.053 | +0.155 / −0.101 | **+0.278** | +2.83 | Mostly the report returning to normal length, plus a new IAS 36 impairment note. |
| BEL 2019→2020 | 117→67 | 48,206→26,004 | +0.149 | −1.480 / +1.629 | +0.007 | −0.114 / +0.122 | **0** | −2.86 | The whole report halved. Not an FC event. |
| ACT 2016→2017 | 142→90 | 49,242→45,963 | −0.926 | −1.094 / +0.168 | −0.100 | −0.100 / 0.000 | **−0.926** | −2.16 | Genuine removal (preference-share terms schedule). |

Sign disagreement with the own-count change: **M1 6/24, M3 9/24**. Examples of M3
pointing the wrong way: ACT 2020→2021 (hits 88→79, M3 +0.012) and SUR 2023→2024 (hits
106→98, M3 +0.015).

---

## 4. Governance candidates

| Candidate | Median | max\|v\| | MAD | p75 | p90 | p95 | ρ vs M3 | top-10 vs M3 | ρ CUR/CLN |
|---|---|---|---|---|---|---|---|---|---|
| GOV-A raw | 0 | 69 | 10.0 | 19.0 | 42.4 | 50.7 | 0.35 | 4 | 0.992 |
| GOV-B M1 | −0.050 | 1.74 | 0.175 | 0.361 | 1.065 | 1.248 | 0.61 | 6 | 0.994 |
| GOV-C M2 | 0 | 2.00 | 0.247 | 0.480 | 1.105 | 1.393 | 0.43 | 5 | 0.989 |
| GOV-D pair-mean (AM) | 0 | 1.86 | 0.251 | 0.507 | 1.107 | 1.373 | 0.44 | 5 | 0.993 |
| GOV-E company median | 0 | 1.81 | 0.238 | 0.464 | 1.061 | 1.323 | 0.42 | 5 | 0.991 |
| GOV-F corpus median | 0 | 1.55 | 0.224 | 0.426 | 0.950 | 1.135 | 0.35 | 4 | 0.992 |
| GOV-G M3 (current) | −0.013 | 0.109 | 0.031 | 0.052 | 0.080 | 0.097 | 1 | 10 | 0.979 |
| GOV-H log ratio | 0 | 0.54 | 0.098 | 0.160 | 0.333 | 0.419 | 0.41 | 5 | 0.990 |
| GOV-I topic mix (M6-G) | 0.017 | 0.161 | 0.013 | 0.021 | 0.070 | 0.078 | 0.25 | 5 | 0.996 |
| **GOV conj (proposed)** | 0 | 1.19 | 0.072 | 0.163 | 0.486 | 0.854 | 0.52 | 6 | 0.980 |

Anchor cases (governance):

| Pair | h | w | M1 (vol / len) | M3 (own / other) | Conj | z | Net / gross | Reading |
|---|---|---|---|---|---|---|---|---|
| ACT 2017→2018 | 96→115 | 45,963→30,068 | +1.736 (+0.523 / **+1.213**) | +0.087 (+0.040 / +0.046) | +0.500 | **0.83** | 19/119 | A real but modest own increase inside heavy churn. 70% of M1 is length. |
| BEL 2018→2019 | 171→165 | 38,063→48,206 | −1.070 (−0.141 / **−0.929**) | −0.064 (−0.009 / **−0.055**) | −0.139 | −0.33 | 6/114 | Governance roughly flat. Both M1 and M3 are driven by the rest of the report. |
| BEL 2016→2017 (positive control) | 111→152 | 34,891→34,078 | +1.279 (+1.189 / +0.090) | +0.099 (+0.078 / +0.021) | **+1.189** | 2.11 | 41/129 | Clean, broad increase. Every metric agrees. |
| ACT 2023→2024 | 149→106 | 45,719→48,083 | −1.055 (−0.917 / −0.137) | −0.109 (−0.077 / −0.032) | **−0.917** | −2.16 | 43/127 | Genuine decline. |
| SUR 2023→2024 | 152→152 | 61,735→59,522 | +0.092 (0 / +0.092) | **+0.0496** (0 / **+0.0496**) | **0** | 0 | 0/104 | **A purely compositional share movement.** Risk, FC and strategy fell (H 484→418). |

Sign disagreement with own-count change: **M1 5/24 (+2 flat-count), M3 8/24 (+2 flat-count)**.

Financial condition and governance end up with the same formula because the same
construct and the same failure modes apply to both, not because consistency was forced.
Their subcategory profiles differ. FC top findings are often single-subcategory
concentrated (dividends 61% for ACT 2016→2017); governance is dominated by `board`.

---

## 5. Symmetric normalization review

- **Symmetry.** AM, HM and GM of `(w1, w2)` are all order-symmetric, whereas M2 is not.
  They are practically interchangeable: ρ ≈ 1.00 among them and identical top-10s. They
  differ by the factor `(1+r)²/4r` for length ratio `r = w2/w1`: 4.6% at r = 0.65 (ACT
  2017→2018) and 9.8% at r = 0.54 (BEL 2019→2020).
- **The HM variant is not arbitrary.** It is exactly the volume component of M1. A more
  complicated exposure term is not warranted. **Use the arithmetic pair mean for display**
  ("per 1,000 words of the two reports' average length") and note the HM equivalence.
- **Does pair-mean scaling merely rescale the count change?** Largely yes. Within a
  company, `w̄` varies modestly, so pair-mean D ranks almost like the raw count (ρ with
  |M3| is 0.55 vs 0.52 for raw). Its only real benefit is cross-company comparability
  between 18k-word (SBP, SDL) and 45–64k-word reports.
- **Sensitivity to report length.** D does not inflate a flat count (h2 = h1 gives D = 0,
  the property M1 and M3 lack). But it faithfully reports whole-report scaling as topic
  volume change: correlation with length change is 0.65 (FC) and 0.49 (governance). That
  is why D is used only as one leg of the conjunction.
- **Sensitivity to bad or short passages.** Negligible (Section 2).

## 6. Company-median / corpus-median normalization

- **FC-F / GOV-F (corpus median) is a scaled raw count in disguise.** It divides every
  pair by the same constant (44,614.5 words), so ρ with raw = 1.0.
- **FC-E / GOV-E (company median) is a raw count scaled by a per-company constant.** It is
  identical to raw within a company, so it adds nothing to within-company comparability.
  Across companies it rescales by typical report size, roughly the same effect as the
  pair-mean without the pair's own length information. Company medians: ACT 42,087;
  BEL 38,063; KP2 46,157; SBP 18,247; SDL 17,683; SUR 61,735.
- Neither fixes the whole-report-scaling issue, and both are unstable for 1–2-report
  companies (SDL has 2 reports; the SBP median rests on 3). **Neither is recommended.**

## 7. Passage-cleaning sensitivity (FC and governance)

For every candidate: ρ(CURRENT, CLEANED) = 0.977–0.996, top-10 overlap 9–10/10, and at
most 1 sign flip (in M1: KP2 2019→2020 FC and BEL 2017→2018 governance, both near zero).
Threshold crossings for the proposed metrics:

- **Financial condition:** none.
- **Governance:** 1 (ACT 2020→2021, −0.269 → −0.245 against the 0.25 threshold).

Company-level largest findings are unchanged. Anchor magnitudes move by 0–10% (ACT FC
2016→2017 conj −0.93 → −1.02; ACT governance 2017→2018 +0.50 → +0.45).

## 8. Anchor cases — summary

| Case | Current | Proposed | Change in interpretation |
|---|---|---|---|
| FC ACT 2017→2018 | M1 +1.002 (old), M3 +0.018 | conj **0** | Not an FC finding: FC text is flat. |
| FC SBP 2023→2024 | M3 −0.0725 (#2) | conj −0.902 (#2), z −1.79 | Retained. CAUTION (restructured dividend and valuation summaries, small counts). |
| FC BEL 2020→2021 | M3 +0.053 (#4) | conj +0.278 (#5), z 2.83 | Retained at modest magnitude (a restored report length plus a new IAS 36 note). |
| GOV ACT 2017→2018 | M3 +0.0865 (#3) | conj +0.500, **z 0.83 → fails evidence floor** | Removed: net +19 inside 119 hits of churn. |
| GOV BEL 2018→2019 | M3 −0.0635 (#4) | conj −0.139 | Removed: governance flat. |
| GOV BEL 2016→2017 | M3 +0.099 (#2) | conj +1.189 (#1), z 2.11 | Retained, #1. |
| GOV ACT 2023→2024 | M3 −0.109 (#1) | conj −0.917 (#2), z −2.16 | Retained. |
| GOV SUR 2023→2024 | M3 +0.0496 (just below 0.05) | conj **0** | Confirmed as a pure share artifact. It would have become a finding under any slightly lower M3 threshold. |

---

## 9. Net tone review

The formula is `1000[(P2−N2)/w2 − (P1−N1)/w1]`, with a negative-direction filter.

- **Denominator.** Tone is an intensive property, so per-word density is the right
  exposure. Count and density disagree in only 2/24 pairs. The conjunction has ρ = 0.992
  with plain net tone, so applying it would change nothing, and it is not recommended here.
  The pair-mean count form (ρ 0.99) adds nothing either.
- **Report-length sensitivity.** Low. ACT 2017→2018 (report 35% shorter) is the largest
  finding, but its sign-flip z is −5.39: positive words fell 947→456 across SUBSTANTIALLY
  and LIGHTLY_MODIFIED and REMOVED passages. It is a real, broad change.
- **Cleaning.** ρ = 0.989, and top-3 membership is unchanged.
- **Interpretability problem (the main finding).** ρ(net tone, Δpositive rate) = 0.83
  against ρ(net tone, −Δnegative rate) = 0.45, and var(Δpos) = 5.79 against
  var(Δneg) = 1.23.
  - **ACT 2017→2018** (−6.63) is Δpos −5.44 and Δneg +1.20: promotional language was
    condensed.
  - **BEL 2018→2019** (−3.83) is genuinely negative-driven: negative words rose 311→521,
    with new COVID-19 impact text and risk registers.
  - **ACT 2021→2022** (−2.45) is new ethics and malus/clawback policy text whose
    vocabulary is LM-negative.

  Loughran-McDonald positive words are known to be weaker and negation-prone. **Surface
  both components**, and label the direction honestly ("net tone fell") rather than
  "language became more negative".
- **Direction filter.** Keep it (the tab is a decline tab). A symmetric "net tone rise" tab
  is a product option, not a methodology requirement.
- **Classification: the problem is threshold plus semantics, not formula, denominator, or
  population.**

## 10. Uncertainty review

| Formula | Behaviour |
|---|---|
| Current density change | Count/density disagreement in **8/24** pairs. The only eligible finding (BEL 2019→2020 +2.175) has hits 366→254 (z −3.49). BEL 2020→2021 (−2.50) has hits +95 (z +3.14). |
| Raw count / pair-mean | Tracks report length (BEL 2019→2020 −3.02, BEL 2020→2021 +2.57, ACT 2017→2018 −3.58). |
| **Conjunction** | ρ 0.77 with the current metric. Largest increases: ACT 2019→2020 +0.760 (z 1.72), SBP 2023→2024 +0.578 (z 2.29), SUR 2024→2025 +0.539, KP2 2023→2024 +0.533. |
| Company / corpus median | Scaled raw count, as in Section 6. |
| Cleaned sensitivity | ρ 0.991. ACT 2019→2020 moves 0.760 → 0.750 and **crosses the 0.75 threshold**. SUR 2023→2024 moves −2.62 → −2.00 (furniture passages). |

- **Negation.** Negated uncertainty terms are tracked but not subtracted, the same as every
  core category. This is not quantified per category (only a total `negated_hit_count` is
  stored), so it is left as a known limitation.
- **Direction filter.** The corpus's largest well-evidenced uncertainty movement is a
  *decrease* (SUR 2023→2024, −174 hits, z −4.79), which the increase-only tab never shows.
  Keep the filter, and treat a decrease tab as a product option.
- **Diagnosis: primarily a denominator/construct problem plus a threshold problem.** It is
  not a passage-population problem. Real uncertainty increases in this corpus are all
  small (≤ 0.76 per 1,000 words, about 10% of the typical density of 7.9), so the tab will
  be nearly empty under any defensible definition.

## 11. Risk introduction / removal review

**Sparsity.** The median report's risk-taxonomy density is **0.21 hits per 1,000 words**,
against 2.2 for FC and 2.7 for governance. There are only **45 introduction hits and 58
removal hits** across all 23 gated pairs. The current metric is zero in 11/23
(introduction) and 13/23 (removal) pairs.

**Candidates** (gated pairs, ρ against the current metric):

| Candidate | Intro ρ / top-10 | Removal ρ / top-10 | Note |
|---|---|---|---|
| Raw risk hits in NEW/REMOVED | 0.94 / 9 | 0.97 / 10 | the same events, re-ordered by size |
| Distinct risk-bearing passages | 0.93 / 9 | 0.96 / 10 | 1–5 passages per pair |
| Share of NEW/REMOVED passages with risk | 0.98 / 10 | 0.99 / 10 | inherits the tiny-denominator problem |
| `1000·hits/w̄` | 0.95 / 9 | 0.97 / 10 | sensible magnitude, same events |
| Gross risk additions/removals over *all* alignment units | 0.48 / 7 | 0.74 / 8 | captures risk language added inside modified passages. The NEW-only construct misses most of it (e.g. KP2 2021→2022 gains +31 hits in modified passages but 0 in NEW). |

**Moved-content check.** A NEW or REMOVED passage counts as "likely moved" if at least 50%
of its 5-word shingles appear anywhere in the other report. **8/45 introduction hits and
22/58 removal hits** are in likely-moved passages.

**Manual validation of every live finding:**

| Pair | Metric | Hits / words / passages | Content | Verdict |
|---|---|---|---|---|
| BEL 2019→2020 | intro | 3 / 686 / 4 | New "Business continuity due to supply chain failure" risk section | **PASS** (substantive, single passage). The rate of 4.37 is an artifact of the 686-word denominator. |
| KP2 2022→2023 | intro | 16 / 4,638 / 15 | 9 hits in new going-concern text. 7 in Note 14 tables that moved (containment 0.96–1.00). | **CAUTION** |
| BEL 2016→2017 | intro | 3 / 958 / 10 | Strategy-table bullet labels ("Currency risk • Supply chain") | **FAIL** (label fragments) |
| BEL 2018→2019 | intro | 6 / 4,416 / 25 | New JSE credit-risk thematic-review note, plus ECL table residue and a share-option "market" hit | **CAUTION** |
| SDL 2024→2025 | intro | 1 / 794 / 2 | Directors'-report passage (containment 0.82 with an earlier passage) | **FAIL** (alignment miss) |
| KP2 2022→2023 | removal | 18 / 3,703 / 20 | Note 14 financial-risk tables that reappear in 2023 (containment 0.82–1.00) | **FAIL** (alignment miss / table residue) |
| KP2 2020→2021 | removal | 10 / 3,079 / 18 | Auditor's "Material uncertainty related to going concern" paragraph dropped (containment ≤ 0.19) | **PASS** (highly material, single passage) |
| KP2 2023→2024 | removal | 3 / 1,587 / 10 | Going-concern note reworded (counterpart AMBIGUOUS) | **CAUTION** |
| BEL 2016→2017 | removal | 3 / 2,189 / 18 | "GOING CONCERN" paragraph moved (containment 1.00) | **FAIL** (alignment miss) |

**Statistical instability vs substantive importance.** The two PASS cases are one passage
each, so **a single passage can be material**, and a minimum hit count would wrongly
suppress them. A count floor is not recommended. The actual failure modes are:

1. **NEW/REMOVED status validity.** Table-mixed financial-statement notes fail alignment
   when their numbers change.
2. **Label and table fragments** getting through primary-narrative classification.
3. **Construct mismatch.** A rate over NEW words measures "how risk-dense the new text is",
   not "how much risk language was introduced".
4. **The NEW/SUBSTANTIALLY_MODIFIED copy mismatch** (7F.6 §19), which remains.

These need an alignment-level guard, and ideally an upstream alignment improvement for
financial-statement notes, before any formula can be frozen.

## 12. Disclosure-change score review

- **Is the construct worth keeping?** Yes. "How much of the narrative was rewritten, added
  or removed" is useful and distinct: ρ ≈ 0 with net tone, and it is not a topic metric.
- **Weights.** Rankings are almost invariant to the weights.

  | Scheme | ρ vs current | top-10 |
  |---|---|---|
  | exclude AMBIGUOUS | 0.997 | 10 |
  | NEW = REMOVED = 1.0 | 0.998 | 10 |
  | linear (0, ⅓, ⅔, 1) | 0.997 | 9 |
  | LIGHTLY_MODIFIED = 0 | 0.993 | 10 |
  | NEW 1.0 / REMOVED 0.7 | 0.986 | 9 |
  | NEW + REMOVED only | 0.880 | 9 |

  The weights are therefore defensible *for ranking*. Equal NEW/REMOVED weights are fine.
  Excluding AMBIGUOUS is immaterial. Median score contributions are LIGHTLY_MODIFIED 29%,
  SUBSTANTIALLY_MODIFIED 27%, NEW + REMOVED 34% and AMBIGUOUS 12%.
- **Continuous vs categorical.** Keep it continuous. The score has ρ = 0.95 with
  (1 − document TF-IDF cosine) and ρ = 0.69 with |report-length change|.
- **Word-share weighting.** Keep it. It is length-robust by construction.
- **What blocks it.** The gate, entirely.
  - The share of rows at LOW/NEEDS_REVIEW confidence is **0.35–0.83 in all 25 pairs**,
    against a 0.25 ceiling.
  - `document_quality = NEEDS_REVIEW` in 17/25 pairs, mostly "metric disagreement spread
    > 0.4". TF-IDF cosine sits around 0.9 while bigram Jaccard and edit similarity are
    structurally far lower on long documents, so this rule fires almost by construction.
  - Either reason alone excludes the corpus.
- **Decision.** Keep it disabled until the confidence calibration and the similarity
  disagreement rule are revisited upstream. **No threshold is tuned** (0/25 eligible).

---

## 13. Common evaluation framework — recommended primary metrics

| | FC topic change | Governance topic change | Uncertainty topic change | Net tone change |
|---|---|---|---|---|
| Formula | `conj(1000Δh/w̄, 1000Δ(h/w))` | same | same, core `uncertainty` | `1000Δ((P−N)/w)` |
| Numerator | FC taxonomy hits | governance hits | LM uncertainty hits | LM positive − negative |
| Exposure | pair-average words / each side's words | same | same | each side's words |
| Units | per 1,000 words | same | same | same |
| Theoretical range | (−∞, ∞), 0 when the legs disagree | same | same | (−∞, ∞) |
| Observed range | −0.93 … +0.55 | −0.92 … +1.19 | −2.62 … +0.76 | −6.63 … +5.92 |
| Median / MAD | 0 / 0.072 | 0 / 0.072 | 0 / 0.232 | 0.196 / 1.194 |
| \|v\| p75/p80/p85/p90/p95 | .179/.225/.331/.500/.850 | .163/.240/.370/.486/.854 | .535/.555/.621/.729/.806 | 3.09/3.62/4.26/4.67/5.73 |
| Gated pairs / companies | 24 / 6 | 24 / 6 | 24 / 6 | 24 / 6 |
| Sign meaning | + more FC language and a larger share of the narrative | same | + increase (tab shows + only) | − decline (tab shows − only) |
| ρ vs current metric | 0.855 (vs M3, signed) | 0.663 | 0.773 | 1.000 |
| Top-10 vs current | 8 | 6 | 6 | 10 |
| ρ CURRENT vs CLEANED | 0.977 | 0.980 | 0.991 | 0.989 |
| Perturbation | sign-flip z reported for every finding | same | same | same |

## 14. Manual content validation (proposed-metric findings, top by magnitude)

| Metric | Pair | Value | z | Evidence | Verdict |
|---|---|---|---|---|---|
| FC | ACT 2016→2017 | −0.93 | −2.16 | Removed redeemable-preference-share terms schedule (dividends 61% of gross) | CAUTION: genuine removal, but legal share-terms text and single-subcategory concentration |
| FC | SBP 2023→2024 | −0.90 | −1.79 | Removed cash-flow restatement note. Dividend summaries restructured into valuation summaries. | CAUTION: section restructuring, small counts |
| FC | BEL 2017→2018 | +0.55 | 1.37 | IFRS 15 restatement, EPS and revenue analysis across 41 units | PASS: broad |
| FC | SUR 2024→2025 | −0.37 | −1.26 | Revenue/scorecard label passages restructured | CAUTION: restructuring / label-heavy |
| FC | BEL 2020→2021 | +0.28 | 2.83 | New IAS 36 impairment-considerations note (+68 hits in NEW) | PASS |
| GOV | BEL 2016→2017 | +1.19 | 2.11 | King IV committee duties and board/committee disclosures | PASS: broad |
| GOV | ACT 2023→2024 | −0.92 | −2.16 | Board-approval and attendance text shortened. Regulatory-compliance reductions. | PASS |
| GOV | ACT 2017→2018 | +0.50 | 0.83 | Restructured attendance/activity tables (board +10, audit −9) | CAUTION: net small relative to churn |
| GOV | SDL 2024→2025 | −0.45 | −0.76 | Directors' report mis-paired as SUBSTANTIALLY_MODIFIED with a tenements passage, then re-appears as NEW | FAIL: alignment artifact |
| GOV | ACT 2020→2021 | −0.27 | −0.94 | AGM-resolution and "governance and leadership" rewording | CAUTION: thin |
| Uncertainty | ACT 2019→2020 | +0.76 | 1.72 | ERM / material-matters sections reworded, +50 hits over 284 gross | CAUTION: thin, at the threshold edge |
| Net tone | ACT 2017→2018 | −6.63 | −5.39 | Promotional strategy text condensed (positive −491) | PASS for "net tone fell", CAUTION for "more negative" |
| Net tone | BEL 2018→2019 | −3.83 | −2.35 | New COVID-19 impact text and risk registers (negative +210) | PASS |
| Net tone | ACT 2021→2022 | −2.45 | −1.08 | New ethics and malus/clawback policy vocabulary | CAUTION: vocabulary-driven |

Fewer than 10 findings clear the threshold for every metric. The sub-threshold top-10
evidence (net/gross, top-unit share, subcategory concentration) is printed in script
Section 2. **Observation:** every governance FAIL or CAUTION has |z| < 1, and every
FC/governance PASS has |z| ≥ 1.37. This is what supports an evidence floor of |z| ≥ 1.
It comes from the same corpus, so it is provisional.

No finding above is read as financial health, governance quality, business risk, or
management intent.

## 15. Threshold calibration (after formula selection)

**Rule (not derived from the change distribution):** the threshold is about **10% of the
metric's corpus-median exposure density per 1,000 words, rounded to the nearest 0.25**.

| Metric | Median level density | 10% | Threshold |
|---|---|---|---|
| FC | 2.23 | 0.22 | **0.25** |
| Governance | 2.68 | 0.27 | **0.25** |
| Uncertainty | 7.89 | 0.79 | **0.75** |
| Net tone | 23.3 (positive + negative tone words) | 2.33 | **2.25** |

**Evidence floor:** |sign-flip z| ≥ 1.0 for all four (within-pair, not corpus-calibrated).

Sensitivity (magnitude + direction only):

| Rule | FC | GOV | UNC (+) | Tone (−) |
|---|---|---|---|---|
| base ×0.5 | 10 | 8 | 6 | 4 |
| base ×0.75 | 6 | 6 | 2 | 4 |
| **base** | **5** | **5** | **1** | **3** |
| base ×1.25 | 4 | 4 | 0 | 2 |
| base ×1.5 | 3 | 4 | 0 | 2 |
| p80 of \|v\| | 5 (0.225) | 5 (0.240) | 2 (0.555) | 2 (3.62) |
| median + 2×scaled MAD | 4 (0.287) | 4 (0.284) | 0 (0.920) | 1 (4.22) |

The percentile and MAD values are shown only as a sanity check. They come from the same
24 pairs, so their proximity to the base rule is **not** independent validation. The
conjunction metrics are zero-inflated by construction (6–7 of 24 pairs are exactly 0), so
MAD-based rules are unreliable here, as 7F.6 found for risk removal. All thresholds are
provisional for a 6-company corpus.

## 16. Current vs proposed Discover diff

Proposed eligibility = report-side gate + direction + |v| ≥ threshold + |z| ≥ 1.

**Financial condition** (current: M3, ε 0.04):

| Pair | Current value | Current eligible / rank | Proposed value | z | Proposed eligible / rank | Reason |
|---|---|---|---|---|---|---|
| ACT 2016→2017 | −0.1002 | Y / 1 | −0.926 | −2.16 | Y / 1 | own-count decline confirmed |
| SBP 2023→2024 | −0.0725 | Y / 2 | −0.902 | −1.79 | Y / 2 | — |
| SUR 2024→2025 | −0.0612 | Y / 3 | −0.374 | −1.26 | Y / 4 | — |
| BEL 2020→2021 | +0.0531 | Y / 4 | +0.278 | 2.83 | Y / 5 | length-driven share of the volume removed |
| BEL 2018→2019 | +0.0501 | Y / 5 | +0.141 | 1.59 | **N** | +30 hits, but the report grew 27%. Density barely moved. |
| BEL 2017→2018 | +0.0423 | Y / 6 | +0.554 | 1.37 | Y / 3 | — |
| ACT 2023→2024 | +0.0421 | Y / 7 | +0.176 | 0.93 | **N** | below magnitude and evidence |

Net: 7 → 5. Removed: BEL 2018→2019 and ACT 2023→2024. Added: none. Companies unchanged
(ACT, BEL, SBP, SUR).

**Governance** (current: M3, ε 0.05):

| Pair | Current value | Current eligible / rank | Proposed value | z | Proposed eligible / rank | Reason |
|---|---|---|---|---|---|---|
| ACT 2023→2024 | −0.1093 | Y / 1 | −0.917 | −2.16 | Y / 2 | — |
| BEL 2016→2017 | +0.0993 | Y / 2 | +1.189 | 2.11 | Y / 1 | — |
| ACT 2017→2018 | +0.0865 | Y / 3 | +0.500 | 0.83 | **N** | net +19 within churn. 70% of old M1 was length. |
| BEL 2018→2019 | −0.0635 | Y / 4 | −0.139 | −0.33 | **N** | governance flat. Share moved via other categories. |
| SDL 2024→2025 | −0.0609 | Y / 5 | −0.452 | −0.76 | **N** | alignment mis-pairing (FAIL) |
| SBP 2023→2024 | +0.0589 | Y / 6 | +0.079 | 1.15 | **N** | +4 hits. Share moved via other categories. |
| ACT 2020→2021 | +0.0194 | N | −0.269 | −0.94 | **N** | passes magnitude, fails evidence |

Net: 6 → 2 (BEL 2016→2017, ACT 2023→2024). Companies lose SBP and SDL. Without the
evidence floor the count would be 5, including ACT 2017→2018, SDL and ACT 2020→2021.
**Material interpretation change:** ACT 2017→2018 and BEL 2018→2019, both historically
cited as governance "shifts", are no longer findings. Neither is SUR 2023→2024.

**Uncertainty** (current: density, ε 1.0, v > 0):

| Pair | Current | Proposed | Reason |
|---|---|---|---|
| BEL 2019→2020 | +2.175, Y / 1 | 0, **N** | uncertainty hits fell 366→254. The density rose only because the report halved. |
| ACT 2019→2020 | +0.760, N | +0.760 (z 1.72), **Y / 1** | +50 hits and higher density. Edge-of-threshold. |

Company changes from BEL to ACT. Under CLEANED the tab would be empty.

**Net tone** (current: ε 1.0, v < 0):

| Pair | Value | z | Current | Proposed |
|---|---|---|---|---|
| ACT 2017→2018 | −6.63 | −5.39 | Y / 1 | Y / 1 |
| BEL 2018→2019 | −3.83 | −2.35 | Y / 2 | Y / 2 |
| ACT 2021→2022 | −2.45 | −1.08 | Y / 3 | Y / 3 |
| ACT 2019→2020 | −2.15 | −0.89 | Y / 4 | **N** |
| BEL 2017→2018 | −1.06 | −0.39 | Y / 5 | **N** |

5 → 3. Companies unchanged (ACT, BEL).

**Risk introduction / removal / overall change:** currently 5 / 4 / 0 findings, proposed
0 / 0 / 0 (tabs disabled).

## 17. Multi-metric redundancy (signed Spearman, 24 gated pairs)

| Pair of metrics | ρ | Reading |
|---|---|---|
| FC conj vs FC M1 / volume / M3 | 0.86 / 0.87 / 0.86 | same topic, different constructs; conj is the intersection |
| GOV conj vs GOV M1 / volume / M3 | 0.80 / 0.83 / 0.66 | — |
| FC M3 vs FC topic mix | 0.10 | distinct constructs, so keep mix as supporting |
| GOV M3 vs GOV topic mix | 0.23 | distinct |
| **FC M3 vs GOV M3** | **−0.46** | closure coupling: one share rising forces others down |
| FC M1 vs GOV M1 | −0.15 | — |
| FC conj vs GOV conj | −0.21 | much weaker cross-tab coupling |
| Net tone vs uncertainty | 0.02 | not redundant |
| FC / GOV volume vs length change | 0.65 / 0.49 | volume is largely a length detector |
| GOV M1 vs length change | −0.42 | the dilution effect |
| Disclosure score vs \|length change\| | 0.69 | expected for its construct |

No metric is removed because of correlation. M3 is demoted because of its construct
behaviour (Sections 3–4), not its correlation.

## 18. Product semantics

**Financial-condition language change** (tab: "Largest financial-condition-language change")

- **Measures:** change in financial-condition vocabulary from the project taxonomy
  (liquidity, debt, dividends, impairment and similar). It counts only where the amount of
  that vocabulary *and* its density in the narrative moved the same way.
- **Units:** per 1,000 words of narrative.
- **Positive:** the later report uses more financial-condition vocabulary, and it forms a
  larger part of the narrative.
- **Negative:** less, and a smaller part.
- **Does NOT mean:** financial health improved or worsened, more or less financial risk,
  or better or worse results. Always show the supporting counts (h1→h2), the density
  change, the report-length change, the top subcategories and the evidence strength.

**Governance language change**

- **Measures:** the same, for governance vocabulary (board, audit, remuneration,
  compliance and similar).
- **Does NOT mean:** governance quality improved or worsened.

**Net tone decline** (rename from "Largest negative-tone shift")

- **Measures:** Loughran-McDonald positive-word density minus negative-word density, per
  1,000 words, fell.
- **Required display:** both components ("driven mainly by fewer positive words" or "by
  more negative words").
- **Does NOT mean:** management sentiment, outlook or performance changed.

**Uncertainty-language increase**

- **Measures:** Loughran-McDonald uncertainty vocabulary increased in amount and as a share
  of the narrative, per 1,000 words.
- **Does NOT mean:** business uncertainty or risk actually increased.

**Supporting-only displays**

- Taxonomy share (M3, labelled "share of classified topic language").
- Topic mix (M6b / M6-G, "change in the mix of subtopics").
- Density change and count change as the two legs.

**Disabled tabs** (risk introduction, risk removal, overall change): show an explicit
"not currently published: methodology under review" state, not the generic empty result.

## 19. Decision table

| Metric | Target construct | Current formula | Recommended formula | Threshold | Quality gate | Supporting metrics | Passage-population change? | Implementation? | Confidence | Main caveat | Classification |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Financial-condition change | own FC language change beyond report scaling | M3 `h2/H2−h1/H1`, ε 0.04 | conj(`1000Δh/w̄`, `1000Δ(h/w)`) + \|z\| ≥ 1 | 0.25 per 1k words | report-side (unchanged) | count change, density change, M3 share, M6b mix, length change, top subcategories | No | Yes | Moderate | 5 findings, 3 of them CAUTION on content grounds (legalese/restructuring). Taxonomy precision, not formula. | **MODIFY_METRIC_AND_THRESHOLD** |
| Governance change | own governance language change beyond report scaling | M3-G, ε 0.05 | same form | 0.25 | report-side | same | No | Yes | Moderate | Only 2 findings survive. The evidence floor is corpus-validated only. | **MODIFY_METRIC_AND_THRESHOLD** |
| Net tone change | fall in LM positive-minus-negative density | density change, ε 1.0, v < 0 | unchanged, + \|z\| ≥ 1 (no current effect) | 2.25 | report-side | Δpositive rate, Δnegative rate | No | Threshold, copy and component display | Moderate–high | Positive-word dominance | **RECALIBRATE_THRESHOLD** |
| Uncertainty change | increase in LM uncertainty language, amount and density | density change, ε 1.0, v > 0 | conj + \|z\| ≥ 1, v > 0 | 0.75 | report-side | count change, density change | No | Yes | Low–moderate | 1 finding, at the threshold edge. The tab will be near-empty. | **MODIFY_METRIC_AND_THRESHOLD** |
| Risk introduction | genuinely new risk-language passages | `1000·risk_hits_NEW/words_NEW` | none frozen. Candidate: `1000·hits/w̄` over NEW passages passing a moved-content guard, plus a passage list | — | alignment-change + a (new) moved-content guard | passage list | No (but table-residue review) | Disable only | — | alignment misses and label fragments | **DISABLE_PENDING_UPSTREAM_FIX** |
| Risk removal | genuinely removed risk-language passages | REMOVED analogue | as above | — | as above | as above | as above | Disable only | — | 22/58 hits in moved passages | **DISABLE_PENDING_UPSTREAM_FIX** |
| Disclosure-change score | share of narrative materially rewritten, added or removed | weighted word-share composite | unchanged (weights are immaterial to ranking) | none (do not tune) | feature (fails 25/25) | 1 − document cosine | No | Disable/empty-state copy only | — | the gate fails on confidence share and similarity disagreement | **DISABLE_PENDING_UPSTREAM_FIX** |
| M3 / M3-G taxonomy share | share of classified topic language | primary | supporting only | — | — | — | — | Copy | High | compositional | **KEEP_AS_SUPPORTING_ONLY** |
| M6b / M6-G topic mix | subtopic mix change | supporting | supporting | — | — | — | — | — | High | — | **KEEP_AS_SUPPORTING_ONLY** |
| M1 density (FC, governance) | topic density change | supporting | supporting (one leg of the conj) | — | — | — | — | — | High | — | **KEEP_AS_SUPPORTING_ONLY** |

## 20. Methodology freeze recommendation

**A. Ready to freeze**

- Net tone: formula retained, threshold 2.25, component display, renamed copy.
- Demotion of M3/M3-G and M6b/M6-G to supporting-only.
- Disabling risk introduction, risk removal and the overall-change tab. Disabling is itself
  a frozen decision.

**B. Ready with caveats**

- The FC and governance conjunction metric, with threshold 0.25 and |z| ≥ 1.
- The uncertainty conjunction, with threshold 0.75 and |z| ≥ 1.

Caveats: the thresholds and the z-floor are provisional and set on a single 24-pair,
6-company corpus. Uncertainty sits at a threshold edge. FC findings inherit
taxonomy-precision issues, such as "dividend" repeating in legal share-terms text.

**C. Not ready**

- The replacement risk introduction/removal formula (needs the moved-content guard,
  financial-statement-note table handling, and a decision on whether additions inside
  SUBSTANTIALLY_MODIFIED passages count).
- Disclosure-change score re-enablement (needs alignment-confidence calibration and the
  similarity disagreement rule revisited).
- The KP2 fiscal-date registration (a data issue, not methodology).

## 21. Implementation batch plan (one batch, one production publication)

**Research signals** (`financial_language_signals` / `financial_language_metrics`):

- Add `passage_alignment_id` to `SignalRowInput` so per-alignment-unit deltas can be
  computed.
- Add pure functions `pair_mean_count_change`, `topic_change_conjunction` and
  `signflip_evidence_z`.
- Bump `signal_version` / `configuration_hash`. This forces fresh `LanguageSignalRun`s for
  all pairs. **No alignment, feature, similarity or embedding rerun is needed.**

**Research schema** (one Alembic migration on `report_pair_language_features`):

- `feature_eligible_primary_words_earlier/_later`
- `financial_condition_hits_earlier/_later` (governance hit counts already exist)
- `{financial_condition, governance, uncertainty}_count_change_per_1000`
- `{financial_condition, governance, uncertainty}_topic_change`
- `{financial_condition, governance, uncertainty, net_tone}_evidence_z`

The existing M1/M3/M6 columns are retained.

**App schema / publication** (one `migrations_app` revision; ride the shared-artifact
architecture from 7ca372ac unchanged):

- `ComparisonMetrics` and the app comparison-metrics table gain the columns above.
- The publisher `METRIC_CATALOG` entries are updated. This also fixes the NEW/SM copy
  mismatch for the disabled risk metrics.

**CandidateSpecs** (`findings.py`):

- Add an `evidence_ok` hook to `CandidateSpec`.
- FC: `financial_condition_topic_change`, unit `rate_per_1000_words`, ε 0.25, \|z\| ≥ 1.
- Governance: `governance_topic_change`, ε 0.25, \|z\| ≥ 1.
- Uncertainty: `uncertainty_topic_change`, ε 0.75, v > 0, \|z\| ≥ 1.
- Net tone: unchanged key, ε 2.25, v < 0, \|z\| ≥ 1.
- Remove `largest_risk_introduction`, `largest_risk_removal` and `largest_overall_change`.
- `largest_new_disclosure_share` shares the failing feature gate. It is out of scope here,
  but should be decided in the same batch (recommendation: disable for the same reason).

**UI** (`web/lib/config/discovery.ts`, `web/lib/content/finding-copy.ts`, comparison
supporting detail):

- New labels and copy per Section 18.
- A decomposition panel: count change, density change, share, mix, length change, evidence
  strength.
- Net-tone component attribution.
- Explicit "not currently published" states for disabled tabs.

**Tests:**

- Unit tests for the three new functions (including the exact M1 = volume + length
  identity and the conj zero cases).
- CandidateSpec tests for the evidence gate.
- Golden anchor-case tests using the Section 8/16 values, with this script as a cross-check
  against the persisted columns.

**Sequence:** shared-artifact qualification (done) → this freeze → unified local
implementation → full local validation (rerun this script and require a 0.0 diff against
the persisted columns) → resolve KP2 registration → fresh-Neon cutover preparation →
**one** production deployment.

## 22. Production discipline

No production changes, no Neon project, no Vercel deployment, no migrations, no runtime
code changes. The only new files are this document and the read-only research script.

## 23. Unresolved questions

1. **KP2 "2024" registration.** Fiscal label FY2025, publication 2026-03-24, manually
   corrected to 2024-12-31. Verify before cutover. If it is FY2025, KP2 2023→2024 becomes
   a 24-month irregular pair.
2. Revisit the z-floor (1.0) and the four thresholds when the corpus grows beyond 6
   companies.
3. Should Discover add "uncertainty decrease" and "net tone rise" tabs? The largest
   well-evidenced uncertainty movement is a decrease.
4. Risk construct: NEW-only vs all added risk language (including inside modified
   passages); moved-content guard threshold (0.5 containment); handling of table-mixed
   financial-statement notes. **Proposed 7F.9.**
5. Disclosure-change score: alignment-confidence calibration (why 35–83% of rows are
   LOW/NEEDS_REVIEW), and the similarity disagreement-spread rule. Consider 1 − document
   cosine as an alignment-independent alternative (ρ 0.95).
6. Loughran-McDonald negation handling for positive words (not separable with the
   currently persisted fields).
7. Taxonomy precision (e.g. "dividend" in share-terms legalese). Out of scope; affects
   content validity of FC findings, not the formula.

## 24. Final verdict

**`METHODOLOGY_FREEZE_READY_WITH_CAVEATS`**

- **Freezable now:** the four report-side metrics have defensible constructs, formulas,
  exposures and interpretations, backed by exact decompositions, cleaning-insensitivity
  and manual validation. The three alignment-dependent metrics have a defensible frozen
  decision: disable, with documented reasons.
- **Caveats that must travel with the freeze:**
  - The thresholds and evidence floor are provisional and single-corpus.
  - The uncertainty and governance tabs will be sparse (1 and 2 findings).
  - The KP2 fiscal-date question must be resolved before the cutover.

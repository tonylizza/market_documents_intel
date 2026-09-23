# Track 7F.6 — Discover Metric Methodology Audit (remaining six metrics)

**Scope**: read-only audit. No code, configuration, threshold, taxonomy, migration, or
production data was changed to produce this document. All corpus figures below were read
from the local research database (`market_documents`, 25 current `ReportPairLanguageFeatures`
/ `ReportPairFeatures` rows — same "current run" selection rule as 7F.1–7F.5, via
`get_current_language_signal_runs_by_pair` / `get_current_feature_runs_by_pair`) as of
`2026-09-23`, using ad hoc read-only SQL/ORM queries executed through `.venv/bin/python`
scripts. No script here was retained in `scripts/` (none was requested to be); the full
reconstruction methodology is described inline wherever a number is quoted, exactly as
7F.1–7F.3 did.

**Object of study**: the six Discover metrics *not* already redesigned by 7F.1–7F.5 —
`disclosure_change_score`, `uncertainty_intensity_change`, `net_tone_change`,
`risk_language_introduction`, `risk_language_removal`, `governance_language_change`.
`financial_condition_share_change` (M3) and its predecessor M1 are out of scope here; they
are referenced only as a comparison point, per the precedent this audit is asked to match.

---

## 1. Executive summary

Applying the same rigor the financial-condition work (7F.1–7F.5) applied to one metric, to
the remaining six, finds a mix of genuinely different problems — not a uniform verdict:

- **`disclosure_change_score` is currently a dead Discover tab.** Its quality gate
  (`feature_quality_ok` and `feature_primary_eligible`, both required by
  `_gate_feature`) requires `FeatureQuality ∈ {GOOD, USABLE}` **and**
  `disclosure_change_score is not None`, but the corpus-wide `feature_quality` is
  `NEEDS_REVIEW` for **all 25 of 25** current pairs (Section 5, Section 7). The epsilon
  (`0.05`) is irrelevant: every pair's raw value already clears it (min observed 0.182), but
  zero pairs ever reach the gate. This is already partially acknowledged in the frontend
  (`web/lib/config/discovery.ts`'s comment that this type is "currently empty... because
  `disclosure_change_quality` is `NEEDS_REVIEW` corpus-wide"), but the magnitude — **100%
  gate failure, not partial** — and the fact that the dominant driver is upstream
  document-level similarity quality (`document_quality == NEEDS_REVIEW` in 17/25 cases) and a
  low/needs-review-confidence-share threshold (`> 0.25`) that a majority of pairs also exceed,
  do not appear to have been quantified anywhere before this audit.
- **`governance_language_change`'s current top Discover findings reproduce the exact
  denominator-shrinkage artifact that 7F.1–7F.4 already diagnosed and fixed for the old
  financial-condition metric (M1) — on the *same underlying report pair*.** ACT
  2017-06-30→2018-06-30, governance's #1 ranked eligible finding (`+1.736`), is **76% a
  report-length artifact**: holding the earlier side's word count fixed, the length-controlled
  change is only `+0.413` (Section 16). BEL 2018-12-31→2019-12-31, governance's #3 finding
  (`-1.070`), is **85% artifact** (`-0.158` length-controlled). `governance_language_change`
  uses the identical `rate_change` formula over the identical `feature_eligible_primary`
  word-count denominator that M1 used — nothing about 7F.4's fix was generalized to this
  metric, and nothing in the current quality gate detects it (Section 5, Section 16). **Correction
  (7F.7a, see Section 16's callout below)**: this bullet's magnitude claims stand — both pairs'
  M1-G *rate* values are still confirmed denominator-inflated — but 7F.7a's share-based M3-G
  metric (denominator-robust by construction) shows both pairs still register as the corpus's
  3rd- and 4th-largest governance-language *share* movements, i.e. the underlying direction and
  rough size of each pair's governance-language shift is real, not purely artifactual. "Report-
  length artifact" was too strong a characterization of the *disclosure change itself*, even
  though it correctly describes why the *rate metric's magnitude* is unreliable.
- **`risk_language_introduction`/`_removal`'s largest corpus findings rest on extremely small
  hit counts.** The single largest `risk_language_introduction` value in the whole 25-pair
  corpus (BEL 2019→2020, `+4.373`) is **3 dictionary hits across 4 passages, 686 words total**
  (Section 15, Section 17). SDL's only Discover-eligible risk-introduction finding (`+1.259`)
  is **one hit**. A ±1-hit perturbation moves these values 25–100%; ±5 hits (a plausible range
  for boilerplate phrase variation) can more than double or zero several of the corpus's top
  findings (Section 11, Section 15).
- **`net_tone_change`'s corpus distribution genuinely differs from the other four
  `rate_per_1000_words` metrics sharing `epsilon = 1.0`.** Its median absolute value
  (`1.271`) is itself already above the shared epsilon; **60% of the 25-pair corpus**
  (15/25) clears `|net_tone_change| ≥ 1.0` on magnitude alone (Section 14) — this is not an
  assumption carried over from the prompt, it is verified directly against the live corpus
  and matches 7F.1's own comparison table exactly (15/25, 60%). By contrast
  `uncertainty_intensity_change` (5/25, 20%) and `governance_language_change` (4/25, 16%)
  are far more selective at the identical numeric threshold. A single shared epsilon across
  metrics whose natural scales differ by roughly 3x is not defensible as one materiality
  standard, exactly as 7F.1 already established for the financial-condition case, now shown
  to generalize to at least these three of the four remaining `rate_per_1000_words` metrics.
- **Two UI/catalog description mismatches were found and confirmed against the code**, not
  merely inferred: both the Python `METRIC_CATALOG` entry
  (`publisher.py:118`) and the frontend copy (`finding-copy.ts:46`) describe
  `risk_language_introduction`/`_removal` as counting hits in
  "NEW/SUBSTANTIALLY_MODIFIED" passages ("new or substantially changed" in the frontend
  copy), but the actual formula (`introduction_or_removal_rate`,
  `financial_language_metrics.py:200-207`, wired at
  `financial_language_signals.py:825-826`) only ever sums hits from rows whose
  `alignment_status` is exactly `NEW` (for introduction) or `REMOVED` (for removal) —
  `SUBSTANTIALLY_MODIFIED` rows are never included in either metric's numerator or
  denominator (Section 19).
- No epsilon for any of the six metrics has documented empirical rationale beyond the same
  literal-constant pattern 7F.1 found for the financial-condition metric's old epsilon
  (Section 6): `disclosure_change_score`'s `0.05` and the four remaining
  `rate_per_1000_words` metrics' `1.0` were all introduced whole, in the same single commit
  (`adc4c3d`, 2026-07-29) that also introduced the financial-condition metric's original
  (now-superseded) `1.0`. No later commit touches any of these six epsilon values
  (`git log --follow -p` on `findings.py` shows two commits total: `adc4c3d` and `81e1df7`,
  the latter being 7F.4's financial-condition-only change).

Metric-by-metric verdicts (full rationale in Section 21): `net_tone_change` —
**RECALIBRATE_THRESHOLD / VERIFY_NORMALIZATION** (own metric-specific epsilon is needed given
the shared-scale problem found here, but this is a threshold/calibration correction, not a
formula redesign, since most top findings are individually length-control-robust — see
Section 14's plain-answer note); `uncertainty_intensity_change` —
**RECALIBRATE_THRESHOLD**; `governance_language_change` —
**MODIFY_METRIC_AND_THRESHOLD** (needs the same M3-style share-based fix financial condition
received); `risk_language_introduction` / `risk_language_removal` —
**MODIFY_METRIC_AND_THRESHOLD** (denominator/sparsity problem, not merely a bad threshold);
`disclosure_change_score` — **MORE_DATA_NEEDED** (the metric's own formula and weights are
not indicted here, but it cannot be usefully calibrated while its quality gate excludes the
entire corpus).

---

## 2. Metric inventory

| Metric | Source (function / formula) | Persisted research column(s) | Publication column(s) | Discover candidate | Quality gate | Epsilon (materiality) | Ranking rule | Unit |
|---|---|---|---|---|---|---|---|---|
| `disclosure_change_score` | `feature_metrics.compute_score_components` + `ScoreComponents.total`, wired in `feature_extraction.py:375-386` | `ReportPairFeatures.disclosure_change_score` (+ 6 `score_*_component` columns) | `ComparisonMetrics.disclosure_change_score`; `ReportComparison.disclosure_change_score` | `largest_overall_change` | `_gate_feature`: `feature_quality_ok` (`FeatureQuality ∈ {GOOD,USABLE}`) **and** `feature_primary_eligible` | `0.05`, unit `score_0_1` | magnitude = `|value|/epsilon`, sort desc, tie-break by `CANDIDATE_KEY_ORDER` | `score_0_1` |
| `net_tone_change` | `financial_language_metrics.net_tone` + `rate_change`, wired at `financial_language_signals.py:817-819` | `ReportPairLanguageFeatures.net_tone_change` (+ `net_tone_earlier/_later`) | `ComparisonMetrics.net_tone_change` | `largest_negative_tone_shift` | `_gate_report_side`: `report_side_quality_ok` **and** `report_side_primary_eligible` | `1.0`, direction filter `v < 0` only | same | `rate_per_1000_words` |
| `uncertainty_intensity_change` | `financial_language_metrics.compute_core_category_change("uncertainty", ...).rate_change`, wired at `financial_language_signals.py:820` | `ReportPairLanguageFeatures.uncertainty_intensity_change` (+ `uncertainty_count/rate_earlier/_later`) | `ComparisonMetrics.uncertainty_intensity_change` | `largest_uncertainty_increase` | `_gate_report_side` | `1.0`, direction filter `v > 0` only | same | `rate_per_1000_words` |
| `risk_language_introduction` | `financial_language_metrics.introduction_or_removal_rate(new_hits, "risk")`, wired at `financial_language_signals.py:825` | `ReportPairLanguageFeatures.risk_language_introduction` | `ComparisonMetrics.risk_language_introduction` | `largest_risk_introduction` | `_gate_alignment_change`: `alignment_change_quality_ok` **and** `alignment_change_primary_eligible` | `1.0`, no direction filter (value is non-negative by construction) | same | `rate_per_1000_words` |
| `risk_language_removal` | `financial_language_metrics.introduction_or_removal_rate(removed_hits, "risk")`, wired at `financial_language_signals.py:826` | `ReportPairLanguageFeatures.risk_language_removal` | `ComparisonMetrics.risk_language_removal` | `largest_risk_removal` | `_gate_alignment_change` | `1.0`, no direction filter | same | `rate_per_1000_words` |
| `governance_language_change` | `financial_language_metrics.custom_category_rate(..., "governance")` + `rate_change`, wired at `financial_language_signals.py:830-832` | `ReportPairLanguageFeatures.governance_language_change` (+ `governance_rate_earlier/_later`) | `ComparisonMetrics.governance_language_change` | `largest_governance_shift` | `_gate_report_side` | `1.0`, no direction filter | same | `rate_per_1000_words` |

All six candidate specs live in `src/market_documents/publishing/findings.py:89-127`
(`CANDIDATES` tuple); `eligible_candidates`/`select_findings` (same file, lines 140-171) are
the sole ranking logic, shared verbatim between per-comparison finding selection and
corpus-wide `discovery.py::rank_discovery_items`.

---

## 3. Exact formulas

Quoted, not paraphrased, from the actual implementation.

**`disclosure_change_score`** (`feature_metrics.py:258-279`, `ScoreComponents.total` at
`feature_metrics.py:159-166`):

```
word_rates[status] = words[status] / sum(words.values())     # feature-eligible rows only
component(status, weight) = word_rates[status] * weight       # None if word_rates[status] is None
disclosure_change_score = clamp(0, 1,
    component(UNCHANGED,              w=0.00)
  + component(LIGHTLY_MODIFIED,       w=0.25)
  + component(SUBSTANTIALLY_MODIFIED, w=0.65)
  + component(NEW,                    w=0.85)
  + component(REMOVED,                w=0.85)
  + component(AMBIGUOUS,              w=0.50)
)
```

This is **not** a cosine-similarity score. `document_cosine_similarity` (TF-IDF-weighted
cosine over the two full documents, `similarity_metrics.py`) is a *separate*, independently
persisted metric (`ReportPairFeatures.document_cosine_similarity`) used only for
`document_quality` assessment and the `document_cosine_change` diagnostic transform — it is
never an input to `disclosure_change_score`'s formula (confirmed: `compute_score_components`
takes only `eligible_word_rates`, no similarity value, `feature_metrics.py:258-259`). See
Section 12.

`disclosure_change_score = None` (not a low number) whenever
`coverage.coverage_words < 0.80` or either side's embedding coverage is `< 0.80`
(`feature_extraction.py:377-386`).

**`net_tone_change`** (`financial_language_metrics.py:172-175`, wired
`financial_language_signals.py:817-819`):

```
net_tone(side) = positive_rate(side) - negative_rate(side)     # both per 1,000 words
net_tone_change = net_tone(later) - net_tone(earlier)
```

**`uncertainty_intensity_change`** (`compute_core_category_change`,
`financial_language_metrics.py:156-169`):

```
uncertainty_rate(side) = 1000 * uncertainty_hit_count(side) / feature_eligible_primary_words(side)
uncertainty_intensity_change = uncertainty_rate(later) - uncertainty_rate(earlier)
```

**`risk_language_introduction`** / **`risk_language_removal`**
(`introduction_or_removal_rate`, `financial_language_metrics.py:200-207`):

```
new_hits   = hits_for_status(feature_eligible_primary_rows, AlignmentStatus.NEW)
removed_hits = hits_for_status(feature_eligible_primary_rows, AlignmentStatus.REMOVED)

risk_language_introduction = 1000 * new_hits.custom["risk"]     / new_hits.words
risk_language_removal      = 1000 * removed_hits.custom["risk"] / removed_hits.words
```

`hits_for_status` (`financial_language_metrics.py:190-197`) filters to rows whose
`alignment_status` equals exactly the given status — `NEW` rows only exist on the later side
(no earlier passage), `REMOVED` rows only on the earlier side (no later passage); each
metric's denominator is therefore the word count of *only its own single-sided NEW or
REMOVED population*, not a two-sided report-level word count.

**`governance_language_change`** (`custom_category_rate` + `rate_change`,
`financial_language_signals.py:830-832`):

```
governance_rate(side) = 1000 * governance_hit_count(side) / feature_eligible_primary_words(side)
governance_language_change = governance_rate(later) - governance_rate(earlier)
```

Structurally **identical formula shape** to the pre-7F.4 financial-condition metric (M1):
`rate_change(custom_category_rate(later, cat), custom_category_rate(earlier, cat))`, only
`cat` differs (`"governance"` vs. `"financial_condition"`). See Section 16.

---

## 4. Denominators / populations

All six metrics draw from **`feature_eligible_primary`**
(`financial_language_signals.py:585-586`): rows that are both `primary_narrative_eligible`
(excludes the 6 structured-content categories — `short_fragment_invalid`,
`broken_fragment_sequence`, `numeric_or_table_like_source`, `contents_or_index_like`,
`caption_or_label_like`, `financial_table_rendered_as_prose`,
`PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES`) **and** `feature_eligible` (excludes passages the
Milestone 3 feature pipeline treats as non-substantive). This population is identical to the
one the financial-condition audit (7F.1 §5) documented for M1 — no metric in this batch uses
a different base population.

Beyond that shared base, the six metrics split into two denominator families:

- **Report-side, two-sided per-side sums** (`disclosure_change_score` excepted, see below):
  `net_tone_change`, `uncertainty_intensity_change`, `governance_language_change`. Each
  side's denominator is `sum(passage_word_count for r in feature_eligible_primary if
  r.report_side == side)` (`aggregate_side`, `financial_language_metrics.py:127-143`) — the
  **whole report side's** feature-eligible primary-narrative words, regardless of alignment
  status (UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED/NEW/REMOVED/AMBIGUOUS rows on
  that side all count toward the denominator if they carry a passage on that side).
- **Single-sided, alignment-status-restricted sums**: `risk_language_introduction` /
  `risk_language_removal`. The denominator is `hits_for_status(...).words`
  (`financial_language_metrics.py:190-197`) — **only** the word count of rows whose
  `alignment_status` is exactly `NEW` (introduction) or `REMOVED` (removal), a much smaller
  and much more volatile population than the report-side total (Section 15 quantifies this:
  corpus NEW/REMOVED populations for the top findings run from ~700 to ~4,600 words, versus
  30,000–48,000 words for the report-side metrics' denominators over the same pairs).
- **`disclosure_change_score`** uses yet a third population: `eligible_word_rates`
  (`word_rates(eligible)`, `feature_extraction.py:335-336`) — the **Milestone-3 feature**
  eligible population (`aggregate_outcomes(..., eligible_only=True)`,
  `feature_metrics.py:116-131`), built from `AlignmentRowInput` (one row per accepted
  `PassageAlignment` row, not one row per `PassageLanguageSignal` side) and gated by
  `is_row_eligible`/`passage_excluded_from_features` — a **different, independently
  maintained eligibility computation** from `feature_eligible_primary` above, even though
  both encode a similar "exclude low-information passages" intent. The two populations are
  not guaranteed to be numerically identical (different exclusion rule: Milestone 3's
  `minimum_feature_passage_words=40` low-information floor vs. Milestone 6's
  `PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES` structured-content classifier) — this audit did not
  reconcile them further, since `disclosure_change_score`'s Discover eligibility already fails
  entirely upstream of any denominator question (Section 5).

None of the six metrics' denominators exclude AMBIGUOUS rows, collision-flagged rows, or any
alignment-confidence tier by default — the report-side metrics' denominators include
everything in `feature_eligible_primary` regardless of alignment confidence (matching M1's
documented behavior); `risk_language_introduction`/`_removal`'s NEW/REMOVED populations are
disjoint from AMBIGUOUS by construction (an AMBIGUOUS row is neither NEW nor REMOVED).

---

## 5. Quality gates

| Metric | Gate function | Inputs considered | Ignores |
|---|---|---|---|
| `disclosure_change_score` | `_gate_feature` (`findings.py:61-62`) → `assess_feature_quality` (`feature_quality.py:46-153`) | document-level similarity quality, alignment run status, irregular gap/transition, alignment coverage (count+words ≥ 0.80), embedding coverage (≥ 0.80 both sides), ambiguous word share (≤ 0.15), low/needs-review confidence share (≤ 0.25) | Nothing report-side-specific (dictionary coverage is irrelevant to this metric) |
| `net_tone_change`, `uncertainty_intensity_change`, `governance_language_change` | `_gate_report_side` (`findings.py:65-66`) → `assess_report_side_quality` (`financial_language_quality.py:69-147`) | transition/irregular-gap flag, primary-narrative word coverage (≥ 0.70 both sides), dictionary match rate (anomalous < 0.02, borderline < 0.05) | Alignment confidence, collision, correspondence uniqueness — **and, structurally, denominator/word-count-shrinkage stability** (Section 16) |
| `risk_language_introduction`, `risk_language_removal` | `_gate_alignment_change` (`findings.py:69-70`) → `assess_alignment_change_quality` (`financial_language_quality.py:167-260`) | upstream `FeatureQuality`, alignment run status, ambiguous word share (≤ 0.15), collision-flagged word share (warning > 0.60, review > 0.85), unmatched word share (informational > 0.40) | **The size of the NEW/REMOVED hit-count population itself** — nothing here checks whether the single-sided population the rate is computed over is large enough to be stable (Section 15) |

**GOOD / USABLE / NEEDS_REVIEW / FAILED**, as defined for each layer:

- Report-side (`assess_report_side_quality`): `NEEDS_REVIEW` if irregular unexplained gap,
  or either side's primary-narrative word coverage `< 0.70`, or either side's dictionary
  match rate `< 0.02`; `USABLE` if neither of those but either side's dictionary match rate is
  in `[0.02, 0.05)` (informational only); else `GOOD`. `primary_eligible` requires quality
  `∈ {GOOD, USABLE}` and no transition/irregular-gap flag.
- Alignment-change (`assess_alignment_change_quality`): `FAILED` immediately if upstream
  `FeatureQuality == FAILED`; else `NEEDS_REVIEW` if irregular unexplained gap, ambiguous word
  share `> 0.15`, or collision-flagged word share `> 0.85`; `USABLE` if alignment run
  completed with warnings, upstream feature quality is `NEEDS_REVIEW`, collision-flagged share
  is in `(0.60, 0.85]`, or unmatched share `> 0.40` (all informational-only triggers); else
  `GOOD`.
- Feature (`assess_feature_quality`): `FAILED` if `document_quality == FAILED`; else
  `NEEDS_REVIEW` if `document_quality == NEEDS_REVIEW`, irregular unexplained gap, either
  coverage floor (`0.80`) is missed, ambiguous word share `> 0.15`, or low/needs-review
  confidence share `> 0.25`; `USABLE` if alignment run completed with warnings; else `GOOD`.
  `primary_eligible` additionally requires `disclosure_change_score is not None`.

**Current corpus quality-tier distribution** (25 current pairs, this audit's own query):

| Layer | GOOD | USABLE | NEEDS_REVIEW | FAILED | `primary_eligible=True` |
|---|---|---|---|---|---|
| report-side | 16 | 8 | 1 | 0 | 24/25 |
| alignment-change | 0 | 23 | 2 | 0 | 23/25 |
| feature | 0 | 0 | **25** | 0 | **0/25** |

**Assessment — does the gate logically match what the metric computes?**

- Report-side metrics (`net_tone_change`, `uncertainty_intensity_change`,
  `governance_language_change`): the gate is appropriately scoped in principle (report-side
  rates never need passage-to-passage correspondence, matching the Milestone 6 recalibration
  rationale documented in `financial_language_quality.py`'s module docstring). **But it is
  incomplete**: none of these three metrics' denominators are word-count-stable across a
  report-length change (Section 4), and the gate has no check for denominator-shrinkage risk
  — the same structural gap 7F.3 §9 already identified for M1's `H` (custom-taxonomy hit
  total) denominator, here affecting the word-count denominator these three metrics all
  share. `governance_language_change`'s top findings demonstrate this concretely (Section
  16).
- Alignment-change metrics (`risk_language_introduction`/`_removal`): the gate is correctly
  scoped to alignment trustworthiness (these genuinely need correspondence quality), but,
  like M3's `H` gap identified in 7F.3, has **no check on the size of the NEW/REMOVED
  population itself** — a report pair could have `GOOD`/`USABLE` alignment-change quality
  (correspondence is trustworthy) while the NEW or REMOVED population is a handful of
  passages and a few hundred words, which is exactly the corpus's actual top-finding pattern
  (Section 15).
- `disclosure_change_score`'s gate is the most conservative of the six by a wide margin
  (0/25 primary-eligible vs. 23–24/25 for the other layers) — not because the metric's
  formula is unusually risky, but because it additionally requires `document_quality !=
  NEEDS_REVIEW` (17/25 pairs fail this alone) and a `low_confidence_share ≤ 0.25` (a stricter
  numeric bar than the alignment-change layer's `ambiguous_word_share ≤ 0.15` /
  `collision_flagged_word_share` bands applied to a conceptually similar signal). Whether this
  is the *right* strictness for this metric specifically, versus an artifact of `feature_quality`
  being defined once and shared by both `disclosure_change_score` and `new_rate_words`
  (the other `_gate_feature` candidate, also 0/25 eligible), is a genuine open question this
  audit surfaces but does not resolve (Section 22, Section 23).

---

## 6. Threshold origins

| Metric | Epsilon | Unit | Quality gate | Documented origin | Classification |
|---|---|---|---|---|---|
| `disclosure_change_score` | `0.05` | `score_0_1` | feature | Code comment (`findings.py:78-80`) explains *why a materiality bar exists*, not why `0.05`. No test, doc, or commit ties `0.05` to a distributional/empirical source. | **G — unknown / undocumented heuristic** |
| `net_tone_change` | `1.0` | `rate_per_1000_words` | report-side | Same generic comment; shared literal with 4 other candidates (was originally 5, before 7F.4 changed financial condition's). | **G — unknown / undocumented heuristic**, with the same (F) inherited/shared-default character 7F.1 found for the pre-7F.4 financial-condition epsilon |
| `uncertainty_intensity_change` | `1.0` | `rate_per_1000_words` | report-side | Same | **G / F**, as above |
| `risk_language_introduction` | `1.0` | `rate_per_1000_words` | alignment-change | Same | **G / F**, as above |
| `risk_language_removal` | `1.0` | `rate_per_1000_words` | alignment-change | Same | **G / F**, as above |
| `governance_language_change` | `1.0` | `rate_per_1000_words` | report-side | Same | **G / F**, as above |

**Evidence checked, per the audit's discipline of not inferring rationale where none is
documented:**

- `git log --follow -p -- src/market_documents/publishing/findings.py` returns exactly two
  commits: `adc4c3d` (2026-07-29, "Front end built in React..." — introduces the whole file,
  all six epsilons among them) and `81e1df7` (7F.4, changes only the financial-condition
  candidate's `metric_key`/`unit`/`epsilon`). No commit ever touches the epsilon for any of
  the six metrics audited here.
- `git log --all --grep="epsilon" -i` and `git log --all --grep="threshold" -i` return only
  those same two commits.
- `docs/publishing.md:180` documents the *mechanism* ("Every candidate must also clear a
  per-metric materiality epsilon... to be eligible at all") — mechanics, not derivation, as
  7F.1 already found for the old financial-condition epsilon.
- `tests/publishing/test_publishing_findings.py` tests gate/epsilon *mechanism* only
  (`test_sub_epsilon_candidate_never_selected` uses `disclosure_change_score`'s `0.05` purely
  as a worked example of the comparison logic, not to justify the value); no test encodes a
  rationale for any of the six values here.
- Contrast case, confirming this project *does* document calibrated thresholds elsewhere when
  they exist: `dictionary_match_rate_anomalous_threshold`/`_borderline_threshold`
  (`financial_language_config.py:102-121`) and `collision_flagged_word_share_*`
  (`financial_language_config.py:123-138`) both carry detailed, corpus-evidence comments
  ("the post-Loughran-McDonald-import corpus (25 pairs, 6 companies) has a per-side... match
  rate ranging 0.043-0.069..."). No comparable comment exists anywhere near any of the six
  Discover epsilons audited here.
- `feature_config.py`'s own module docstring is explicit that its weights (which feed
  `disclosure_change_score` directly) are **"provisional, set from first principles (not
  tuned against market outcomes, per the milestone's explicit prohibition) and are expected
  to be revised after inspecting real feature results on the corpus."** This is the clearest
  documented statement in the codebase about any of the six metrics' parameters — it
  confirms the weights are **deliberately not empirically calibrated**, by explicit project
  policy, not merely undocumented. This is closer to classification **E — heuristic, by
  documented design** for the weights specifically (distinct from the epsilon, which remains
  G).

---

## 7. Corpus-wide distributions

N = 25 current `ReportPairLanguageFeatures`/`ReportPairFeatures` pairs (gate-agnostic —
every pair with a non-null value), computed directly from the research database.

| Metric | N | min | max | mean | median | stdev | MAD |
|---|---|---|---|---|---|---|---|
| `disclosure_change_score` | 25 | 0.1823 | 0.6623 | 0.4219 | 0.4227 | 0.1081 | 0.0625 |
| `net_tone_change` (signed) | 25 | -6.6346 | 5.9152 | 0.6764 | 0.2998 | 2.8782 | 1.3581 |
| `uncertainty_intensity_change` (signed) | 25 | -2.6186 | 2.1753 | -0.0984 | 0.0544 | 1.0079 | 0.5162 |
| `risk_language_introduction` | 25 | 0.0000 | 4.3732 | 0.6568 | 0.1292 | 1.2083 | 0.1292 |
| `risk_language_removal` | 25 | 0.0000 | 4.8609 | 0.5805 | 0.0000 | 1.1755 | 0.0000 |
| `governance_language_change` (signed) | 25 | -1.0697 | 1.7360 | -0.0340 | -0.0467 | 0.5766 | 0.1633 |

`disclosure_change_score` and the two risk-attribution metrics are unsigned by construction
(risk introduction/removal are non-negative rates by construction; `disclosure_change_score`
is clamped `[0,1]`) — no separate signed/magnitude split is reported for them.
`net_tone_change`, `uncertainty_intensity_change`, `governance_language_change` are signed;
absolute-magnitude percentile bands below are the ones the Discover materiality gate actually
uses.

**Absolute-magnitude percentile bands and threshold crossings** (`|value|`, N=25 for every
metric):

| Metric | p25 | p50 | p75 | p80 | p85 | p90 | p95 | p99 | ≥0.25 | ≥0.50 | ≥0.75 | ≥1.00 | ≥1.25 | ≥1.50 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| `disclosure_change_score` | 0.3719 | 0.4227 | 0.4937 | 0.5021 | 0.5331 | 0.5479 | 0.5603 | 0.6383 | 23 | 5 | 0 | 0 | 0 | 0 |
| `net_tone_change` | 0.9182 | 1.2709 | 3.4788 | 3.9650 | 4.5605 | 4.6638 | 5.6708 | 6.4620 | 23 | 19 | 19 | 15 | 13 | 12 |
| `uncertainty_intensity_change` | 0.2967 | 0.5394 | 0.7596 | 0.8114 | 1.0204 | 1.7189 | 2.4312 | 2.5890 | 19 | 13 | 7 | 5 | 3 | 3 |
| `risk_language_introduction` | 0.0000 | 0.1292 | 0.4815 | 1.0405 | 1.2991 | 2.4224 | 3.3861 | 4.1516 | 9 | 6 | 6 | 5 | 5 | 3 |
| `risk_language_removal` | 0.0000 | 0.0000 | 0.6165 | 0.7807 | 1.0332 | 1.6824 | 2.9763 | 4.4738 | 8 | 8 | 6 | 4 | 4 | 3 |
| `governance_language_change` | 0.0644 | 0.1441 | 0.3236 | 0.5010 | 0.7864 | 1.0637 | 1.2372 | 1.6263 | 10 | 5 | 4 | 4 | 2 | 1 |

`disclosure_change_score`'s own scale (`[0,1]`) makes its `≥1.00`-style rows structurally
meaningless (the metric never exceeds `1.0`); its epsilon (`0.05`) sits far below its own p25
(`0.3719`) — magnitude alone would admit all 25 pairs at that epsilon (Section 9). The
column headers above are shared across metrics purely for layout; read
`disclosure_change_score`'s row against its own `score_0_1` scale, not the `rate_per_1000_words`
scale the other five share.

**Note on the count for `≥0.25` through `≥1.5` above**: these counts are **magnitude-only**,
before either quality-gate or direction-filter is applied — matching the audit's requested
Section 7 scope exactly, and matching the convention 7F.1 §10 used for the financial-condition
corpus table. Section 9 applies the full production gate (quality + direction + epsilon)
for the actual Discover-eligible counts.

---

## 8. Company-level distributions

Magnitude-only (no quality/direction gating applied here, matching Section 7's convention);
tickers ACT, BEL, KP2, SBP, SDL, SUR, all 25 pairs represented across the six companies.

**`disclosure_change_score`** (epsilon 0.05 — every company clears it on every pair; not a
discriminating threshold for this metric at all):

| Ticker | N | min | median | max | Clears 0.05 | Largest pair | Quality (blocks eligibility regardless) |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.391 | 0.494 | 0.662 | 9/9 (100%) | 2016-06-30→2024-06-30 | NEEDS_REVIEW |
| BEL | 6 | 0.368 | 0.425 | 0.562 | 6/6 (100%) | 2019-12-31→2020-12-31 | NEEDS_REVIEW |
| KP2 | 5 | 0.343 | 0.372 | 0.396 | 5/5 (100%) | 2019-12-31→2020-12-31 | NEEDS_REVIEW |
| SBP | 2 | 0.182 | 0.189 | 0.195 | 2/2 (100%) | 2024-12-31→2025-12-31 | NEEDS_REVIEW |
| SDL | 1 | 0.298 | 0.298 | 0.298 | 1/1 (100%) | 2024-06-30→2025-06-30 | NEEDS_REVIEW |
| SUR | 2 | 0.429 | 0.457 | 0.485 | 2/2 (100%) | 2024-06-30→2025-06-30 | NEEDS_REVIEW |

Every one of the 25 pairs has `feature_quality = NEEDS_REVIEW` (Section 5) — no company is
special-cased; this is corpus-wide.

**`uncertainty_intensity_change`** (|Δ|, epsilon 1.0):

| Ticker | N | min | median | max | N≥1.0 | % | Largest pair (signed) |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.054 | 0.450 | 1.011 | 1 | 11% | 2018-06-30→2019-06-30 (-1.011) |
| BEL | 6 | 0.027 | 0.328 | 2.495 | 2 | 33% | 2020-12-31→2021-12-31 (-2.495) |
| KP2 | 5 | 0.124 | 0.680 | 1.034 | 1 | 20% | 2020-12-31→2021-12-31 (-1.034) |
| SBP | 2 | 0.578 | 0.633 | 0.688 | 0 | 0% | 2024-12-31→2025-12-31 (-0.688) |
| SDL | 1 | 0.462 | 0.462 | 0.462 | 0 | 0% | 2024-06-30→2025-06-30 (-0.462) |
| SUR | 2 | 0.539 | 1.579 | 2.619 | 1 | 50% | 2023-06-30→2024-06-30 (-2.619) |

**`net_tone_change`** (|Δ|, epsilon 1.0):

| Ticker | N | min | median | max | N≥1.0 | % | Largest pair (signed) |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.300 | 3.479 | 6.635 | 8 | 89% | 2017-06-30→2018-06-30 (-6.635) |
| BEL | 6 | 0.443 | 1.165 | 3.826 | 4 | 67% | 2018-12-31→2019-12-31 (-3.826) |
| KP2 | 5 | 0.065 | 0.374 | 1.010 | 1 | 20% | 2021-12-31→2022-12-31 (+1.010) |
| SBP | 2 | 0.093 | 0.538 | 0.983 | 0 | 0% | 2023-12-31→2024-12-31 (+0.983) |
| SDL | 1 | 0.928 | 0.928 | 0.928 | 0 | 0% | 2024-06-30→2025-06-30 (+0.928) |
| SUR | 2 | 2.518 | 4.216 | 5.915 | 2 | 100% | 2024-06-30→2025-06-30 (+5.915) |

**`risk_language_introduction`** (epsilon 1.0):

| Ticker | N | min | median | max | N≥1.0 | % | Largest pair |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.000 | 0.000 | 0.213 | 0 | 0% | 2022-06-30→2023-06-30 |
| BEL | 6 | 0.000 | 0.920 | 4.373 | 3 | 50% | 2019-12-31→2020-12-31 |
| KP2 | 5 | 0.000 | 0.313 | 3.450 | 1 | 20% | 2022-12-31→2023-12-31 |
| SBP | 2 | 0.000 | 0.000 | 0.000 | 0 | 0% | (both pairs zero) |
| SDL | 1 | 1.259 | 1.259 | 1.259 | 1 | 100% | 2024-06-30→2025-06-30 |
| SUR | 2 | 0.000 | 0.085 | 0.169 | 0 | 0% | 2023-06-30→2024-06-30 |

**`risk_language_removal`** (epsilon 1.0):

| Ticker | N | min | median | max | N≥1.0 | % | Largest pair |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.000 | 0.000 | 0.617 | 0 | 0% | 2023-06-30→2024-06-30 |
| BEL | 6 | 0.000 | 0.387 | 1.370 | 1 | 17% | 2016-12-31→2017-12-31 |
| KP2 | 5 | 0.214 | 1.890 | 4.861 | 3 | 60% | 2022-12-31→2023-12-31 |
| SBP | 2 | 0.000 | 0.000 | 0.000 | 0 | 0% | (both zero) |
| SDL | 1 | 0.000 | 0.000 | 0.000 | 0 | 0% | (zero) |
| SUR | 2 | 0.000 | 0.082 | 0.164 | 0 | 0% | 2023-06-30→2024-06-30 |

**`governance_language_change`** (|Δ|, epsilon 1.0):

| Ticker | N | min | median | max | N≥1.0 | % | Largest pair (signed) |
|---|---|---|---|---|---|---|---|
| ACT | 9 | 0.052 | 0.234 | 1.736 | 2 | 22% | 2017-06-30→2018-06-30 (+1.736) |
| BEL | 6 | 0.032 | 0.438 | 1.279 | 2 | 33% | 2016-12-31→2017-12-31 (+1.279) |
| KP2 | 5 | 0.032 | 0.053 | 0.284 | 0 | 0% | 2020-12-31→2021-12-31 (-0.284) |
| SBP | 2 | 0.079 | 0.090 | 0.101 | 0 | 0% | 2024-12-31→2025-12-31 (+0.101) |
| SDL | 1 | 0.474 | 0.474 | 0.474 | 0 | 0% | 2024-06-30→2025-06-30 (-0.474) |
| SUR | 2 | 0.092 | 0.135 | 0.179 | 0 | 0% | 2024-06-30→2025-06-30 (-0.179) |

`risk_language_removal`'s zero-inflation (median 0.000, MAD 0.000; ACT, SBP, SDL all show a
median of exactly zero) reflects a genuine feature of the data, not a computation error: a
sizable share of pairs have **no** risk-category hits at all in their REMOVED-status
population — the metric is discrete/sparse for several companies, not continuously
distributed (Section 11, Section 15).

---

## 9. Threshold selectivity

Full production-equivalent Discover-eligible counts (quality gate + direction filter +
`|value| ≥ epsilon`, computed by running the actual `findings.eligible_candidates` function
against every current pair's reconstructed `ComparisonMetrics`):

| Metric | Epsilon | Eligible (full gate) | % of 25 | Approx. empirical percentile of eps (magnitude-only) | Companies represented |
|---|---|---|---|---|---|
| `disclosure_change_score` | 0.05 | **0/25** | 0% | ~p0 (below every observed value; gate is the sole blocker) | none |
| `net_tone_change` | 1.0 | 5/25 | 20% | ~p40 (magnitude-only 15/25 clear it; direction filter `v<0` cuts this to 5) | ACT, BEL |
| `uncertainty_intensity_change` | 1.0 | 1/25 | 4% | ~p80 (magnitude-only 5/25; direction filter `v>0` cuts to 1) | BEL |
| `risk_language_introduction` | 1.0 | 5/25 | 20% | ~p80 | BEL, KP2, SDL |
| `risk_language_removal` | 1.0 | 4/25 | 16% | ~p84 | BEL, KP2 |
| `governance_language_change` | 1.0 | 4/25 | 16% | ~p84 | ACT, BEL |

The gap between "magnitude-only" and "full gate" counts is large and metric-specific — not a
uniform quality-gate discount:

| Metric | Non-null | Gate-pass | Magnitude-pass | Direction-pass | Gate+magnitude | **Full eligible** |
|---|---|---|---|---|---|---|
| `disclosure_change_score` | 25 | **0** | 25 | 25 | 0 | **0** |
| `net_tone_change` | 25 | 24 | 15 | 10 | 14 | **5** |
| `uncertainty_intensity_change` | 25 | 24 | 5 | 13 | 5 | **1** |
| `risk_language_introduction` | 25 | 23 | 5 | 25 (no filter) | 5 | **5** |
| `risk_language_removal` | 25 | 23 | 4 | 25 (no filter) | 4 | **4** |
| `governance_language_change` | 25 | 24 | 4 | 25 (no filter) | 4 | **4** |

For `net_tone_change` and `uncertainty_intensity_change`, the **direction filter** (only
negative-tone shifts count for `largest_negative_tone_shift`; only positive uncertainty
increases count for `largest_uncertainty_increase`) removes more eligible candidates than the
quality gate does — a genuinely large share of this corpus's biggest tone/uncertainty moves
run in the "wrong" direction for their respective Discover tab (e.g., `net_tone_change`'s
15 magnitude-qualifying pairs include both increases and decreases; only 10 of those are
negative, and only 5 also clear the report-side quality gate).

---

## 10. Threshold sensitivity analysis

Simulated `epsilon × {0.5, 0.75, 1.0, 1.25, 1.5}`, percentile thresholds `{p75, p85, p90,
p95}`, and `median(|value|) + {1, 1.5, 2} × scaled MAD` (scale factor `1.4826`, the same
normal-consistency constant 7F.2/7F.3 used), all computed magnitude-only (pre-gate, matching
the audit's own convention for isolating threshold behavior from quality/direction effects).

**`net_tone_change`** (eps=1.0):

| Rule | Threshold | N | Companies |
|---|---|---|---|
| eps×0.5 | 0.500 | 19 | ACT,BEL,KP2,SBP,SDL,SUR (all 6) |
| eps×0.75 | 0.750 | 19 | same (all 6) |
| eps×1.0 | 1.000 | 15 | ACT,BEL,KP2,SUR |
| eps×1.25 | 1.250 | 13 | ACT,BEL,SUR |
| eps×1.5 | 1.500 | 12 | ACT,BEL,SUR |
| p75 | 3.479 | 7 | ACT,BEL,SUR |
| p85 | 4.561 | 4 | ACT,SUR |
| p90 | 4.664 | 3 | ACT,SUR |
| p95 | 5.671 | 2 | ACT,SUR |
| median+1×MAD | 3.013 | 7 | ACT,BEL,SUR |
| median+1.5×MAD | 3.885 | 5 | ACT,SUR |
| median+2×MAD | 4.756 | 2 | ACT,SUR |

KP2 and SDL drop out entirely once any percentile/robust-statistic rule is applied — they
only appear at `eps×0.5`–`eps×1.0`. SBP never appears at any tested threshold — its largest
`|net_tone_change|` (0.983) sits just under even the lowest threshold tested. The current
raw `epsilon=1.0` (before direction filtering) already sits well below the corpus's own
median (1.271) — this metric's natural scale is simply larger than the shared constant
assumes (Section 14 examines why).

**`uncertainty_intensity_change`** (eps=1.0):

| Rule | Threshold | N | Companies |
|---|---|---|---|
| eps×0.5 | 0.500 | 13 | ACT,BEL,KP2,SBP,SUR |
| eps×0.75 | 0.750 | 7 | ACT,BEL,KP2,SUR |
| eps×1.0 | 1.000 | 5 | ACT,BEL,KP2,SUR |
| eps×1.25 | 1.250 | 3 | BEL,SUR |
| eps×1.5 | 1.500 | 3 | BEL,SUR |
| p75 | 0.760 | 7 | ACT,BEL,KP2,SUR |
| p85 | 1.020 | 4 | BEL,KP2,SUR |
| p90 | 1.719 | 3 | BEL,SUR |
| p95 | 2.431 | 2 | BEL,SUR |
| median+1×MAD | 0.869 | 5 | ACT,BEL,KP2,SUR |
| median+1.5×MAD | 1.033 | 4 | BEL,KP2,SUR |
| median+2×MAD | 1.198 | 3 | BEL,SUR |

SBP and SDL never clear any tested threshold. `eps=1.0` (magnitude-only) coincides almost
exactly with `median+1×scaledMAD` (1.000 vs. 0.869) and sits between p75 and p85 — this is
one of the two metrics (with `risk_language_introduction`) where the *raw* `1.0` value
happens to land in a plausible empirical range, even though no evidence suggests it was
chosen that way (Section 6).

**`risk_language_introduction`** (eps=1.0):

| Rule | Threshold | N | Companies |
|---|---|---|---|
| eps×0.5 | 0.500 | 6 | BEL,KP2,SDL |
| eps×0.75 | 0.750 | 6 | BEL,KP2,SDL |
| eps×1.0 | 1.000 | 5 | BEL,KP2,SDL |
| eps×1.25 | 1.250 | 5 | BEL,KP2,SDL |
| eps×1.5 | 1.500 | 3 | BEL,KP2 |
| p75 | 0.481 | 7 | BEL,KP2,SDL |
| p85 | 1.299 | 4 | BEL,KP2 |
| p90 | 2.422 | 3 | BEL,KP2 |
| p95 | 3.386 | 2 | BEL,KP2 |
| median+1×MAD | 0.321 | 8 | BEL,KP2,SDL |
| median+1.5×MAD | 0.416 | 7 | BEL,KP2,SDL |
| median+2×MAD | 0.512 | 6 | BEL,KP2,SDL |

ACT and SBP **never** clear any tested threshold, magnitude-only — ACT's max is 0.213, SBP's
is 0.000 (both of SBP's pairs have zero NEW-side risk hits).

**`risk_language_removal`** (eps=1.0):

| Rule | Threshold | N | Companies |
|---|---|---|---|
| eps×0.5 | 0.500 | 8 | ACT,BEL,KP2 |
| eps×0.75 | 0.750 | 6 | BEL,KP2 |
| eps×1.0 | 1.000 | 4 | BEL,KP2 |
| eps×1.25 | 1.250 | 4 | BEL,KP2 |
| eps×1.5 | 1.500 | 3 | KP2 |
| p75 | 0.617 | 7 | ACT,BEL,KP2 |
| p85 | 1.033 | 4 | BEL,KP2 |
| p90 | 1.682 | 3 | KP2 |
| p95 | 2.976 | 2 | KP2 |
| median+1×MAD | **0.000** | **25** | **all 6 (degenerate)** |
| median+1.5×MAD | 0.000 | 25 | all 6 |
| median+2×MAD | 0.000 | 25 | all 6 |

The robust-statistic rule **breaks down entirely** for this metric: because the corpus
median is exactly `0.000` and MAD is also `0.000` (more than half the pairs have literally
zero risk-removal hits in their REMOVED population), `median + k×scaledMAD = 0.000` for
every `k` tested — the rule admits every pair including the true zeros, providing no
discrimination at all. This is a direct consequence of the metric's zero-inflation
(Section 8, Section 11) and should be treated as a hard limitation on any future robust-
statistic threshold-setting exercise for this specific metric, not a bug in the
computation.

**`governance_language_change`** (eps=1.0):

| Rule | Threshold | N | Companies |
|---|---|---|---|
| eps×0.5 | 0.500 | 5 | ACT,BEL |
| eps×0.75 | 0.750 | 4 | ACT,BEL |
| eps×1.0 | 1.000 | 4 | ACT,BEL |
| eps×1.25 | 1.250 | 2 | ACT,BEL |
| eps×1.5 | 1.500 | 1 | ACT |
| p75 | 0.324 | 7 | ACT,BEL,SDL |
| p85 | 0.786 | 4 | ACT,BEL |
| p90 | 1.064 | 3 | ACT,BEL |
| p95 | 1.237 | 2 | ACT,BEL |
| median+1×MAD | 0.288 | 7 | ACT,BEL,SDL |
| median+1.5×MAD | 0.361 | 6 | ACT,BEL,SDL |
| median+2×MAD | 0.361→6 | 6 | ACT,BEL,SDL |

KP2, SBP, SUR never clear any threshold tested. **Obvious false positives**: as Section 16
shows in detail, 2 of the 4 pairs that clear `eps=1.0` today (ACT 2017→2018, BEL 2018→2019)
are 76–85% denominator-shrinkage artifacts, not genuine governance-language changes —
lowering the threshold (e.g., to `p75`/`median+1×MAD`, both ≈0.3) does not fix this; it only
adds more pairs without removing the two already-flagged as artifacts, since neither is a
threshold problem (Section 16).

`disclosure_change_score` is omitted from this table: every sensitivity variant tested is
irrelevant while the quality gate excludes 100% of the corpus (Section 5, Section 9) — any
threshold choice for this metric is moot until the gate question is resolved (Section 21).

---

## 11. Robustness to small perturbations

**Risk introduction/removal — hit-count perturbation, ±1/±2/±5, on the top findings**
(reconstructed directly from `PassageLanguageSignal`/`PassageLanguageCategoryHit` rows for
the current run, category=`risk`, restricted to the metric's own NEW or REMOVED population):

| Pair | Metric | Base hits / words | Base rate | ±1 hit range | ±2 hit range | ±5 hit range |
|---|---|---|---|---|---|---|
| BEL 2019→2020 | introduction | 3 / 686 | 4.373 | 2.915 – 5.831 | 1.458 – 7.289 | 0.000 – 11.662 |
| KP2 2022→2023 | introduction | 16 / 4,638 | 3.450 | 3.235 – 3.665 | 3.019 – 3.881 | 2.372 – 4.528 |
| BEL 2016→2017 | introduction | 3 / 958 | 3.132 | 2.088 – 4.175 | 1.044 – 5.219 | 0.000 – 8.351 |
| BEL 2018→2019 | introduction | 6 / 4,416 | 1.359 | 1.132 – 1.585 | 0.906 – 1.812 | 0.226 – 2.491 |
| SDL 2024→2025 | introduction | **1** / 794 | 1.259 | 0.000 – 2.518 | 0.000 – 3.778 | 0.000 – 7.556 |
| KP2 2022→2023 | removal | 18 / 3,703 | 4.861 | 4.591 – 5.131 | 4.321 – 5.401 | 3.511 – 6.211 |
| KP2 2020→2021 | removal | 10 / 3,079 | 3.248 | 2.923 – 3.573 | 2.598 – 3.898 | 1.624 – 4.872 |
| KP2 2023→2024 | removal | 3 / 1,587 | 1.890 | 1.260 – 2.521 | 0.630 – 3.151 | 0.000 – 5.041 |
| BEL 2016→2017 | removal | 3 / 2,189 | 1.370 | 0.913 – 1.827 | 0.457 – 2.283 | 0.000 – 3.655 |

**Reading this table**: the corpus's single largest `risk_language_introduction` finding
(BEL 2019→2020) is 3 hits over 4 NEW-status passages, 686 words — a ±1-hit change moves it
33%; ±2 moves it 67% either direction; ±5 (not an unreasonable range for how a single
boilerplate risk phrase might be phrased across similar report years) zeroes it entirely or
more than doubles it. SDL's only Discover-eligible risk-introduction finding is **literally
one hit** — the metric offers no way to distinguish "one genuinely new risk disclosure" from
"one incidental dictionary match in an otherwise-unremarkable NEW passage." Every pair in
this table would remain Discover-eligible under a ±1-hit perturbation except SDL (which would
drop to exactly zero, below epsilon, on a −1 perturbation) — but several pairs' *rank order*
among each other would change under even a ±1 perturbation (e.g. BEL 2016→2017's introduction
value at +1 hit, 4.175, would overtake BEL 2019→2020's base value of 4.373 only if BEL
2019→2020 simultaneously moved down, illustrating how close several of these values sit to
each other relative to their own noise band).

**Report-side metrics — denominator/report-length sensitivity**: covered in depth for
`governance_language_change` in Section 16 (the length-controlled recomputation there is this
section's report-side analogue to the risk-metrics' hit-count perturbation). The same
length-control method applied to the `net_tone_change` top-5 findings (Section 14) shows a
much more mixed picture — some pairs are robust to length control (76–128% of the actual
change survives), one is not (BEL 2017→2018, 53% surviving, would drop below epsilon).

**Collision/ambiguity exclusions**: none of the six metrics' denominators exclude
collision-flagged or ambiguous rows by default (Section 4) — `risk_language_introduction`/
`_removal`'s alignment-change quality gate treats collision as informational-only up to a
0.85 share, meaning a NEW/REMOVED population that is mostly boilerplate/duplicate content
(a legitimate, common corpus condition per `financial_language_config.py`'s own documented
evidence) still contributes fully to these metrics' numerators and denominators without any
downweighting.

---

## 12. `disclosure_change_score` deep dive

**Exact components and weights** (Section 3, `feature_config.py:50-55`): `unchanged=0.00`,
`lightly_modified=0.25`, `substantially_modified=0.65`, `new=0.85`, `removed=0.85`,
`ambiguous=0.50`. Each weight multiplies that alignment-outcome category's **share of
feature-eligible words** (`word_rates`, a partition summing to 1.0 across the six outcome
categories), so the composite is a weighted average, not a sum of independent signals.

**Were the weights calibrated?** No — explicitly, by the module's own docstring
(`feature_config.py:11-14`): "Weights and thresholds below are provisional, set from first
principles (not tuned against market outcomes, per the milestone's explicit prohibition) and
are expected to be revised after inspecting real feature results on the corpus." This is the
single clearest first-party statement about calibration status found anywhere among the six
metrics in this audit (Section 6) — the weights are heuristic **by documented project
policy**, not merely undocumented.

**Cosine representation**: **not used**. `disclosure_change_score` contains no cosine-
similarity term. TF-IDF cosine similarity (`similarity_metrics.pairwise_tfidf_cosine_
similarity` / `lexical_cosine_similarity`) is computed and persisted separately
(`ReportPairFeatures.document_cosine_similarity`), feeding only `document_quality`
assessment and the `document_cosine_change` diagnostic — never `disclosure_change_score`
itself (Section 3). Any description of this metric as "cosine similarity between reports" is
inaccurate; it is a **word-weighted composite over discrete alignment-outcome classes**
(UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED/NEW/REMOVED/AMBIGUOUS), where the
classification of each passage pair into one of those classes is itself upstream (produced
by `passage_alignment.py`, using embedding similarity among other signals) but the score
formula operates on the classification labels' word shares, not on a raw similarity value.

**Are edit/Jaccard/sequence metrics normalized comparably?** Not applicable to this metric
directly — `document_edit_similarity`, `document_bigram_jaccard`, `document_diff_similarity`
are separate `ReportPairFeatures` columns (feeding `document_metric_disagreement_spread` and
the `document_*_change` transforms), not inputs to `disclosure_change_score`. They are all
independently bounded `[0,1]` similarity scores inverted the same way
(`compute_document_change_transforms`, `feature_metrics.py:230-255`: `1 - value`), so they
*are* comparably normalized among themselves, but this is a separate diagnostic axis from
the score this audit is auditing.

**Direction intuitiveness**: the score is unsigned (`[0,1]`, "how much changed," never
"changed how") — this matches the catalog's own stated interpretation
(`direction_interpretation`: "the score does not indicate whether the change is positive or
negative for the company," `publisher.py:93`) and is internally consistent; there is no
direction mismatch to flag here, unlike the risk-attribution UI-copy issue (Section 19).

**Scale stability across document length**: word-*share* based (each category's share of
the total feature-eligible word count, summing to 1.0), so it is **not** vulnerable to the
same absolute-word-count-denominator artifact that affects the `rate_per_1000_words` metrics
(Section 16) — a shorter report shifts which categories' *shares* are larger, but the
denominator (total feature-eligible words on both sides combined, implicitly, via
`aggregate_outcomes`) does not shrink independently of the numerator the way a single-side
rate's denominator can. This is a structurally more robust normalization choice than the
`rate_per_1000_words` metrics use, even though its weights are undocumented/unvalidated
(Section 6).

**Section/reorganization effects**: handled via `AlignmentStatus` classification upstream
(a reorganized-but-unchanged passage should ideally land in `UNCHANGED`/`LIGHTLY_MODIFIED`
rather than `NEW`+`REMOVED`); this audit did not re-examine the alignment classifier itself
(explicitly out of scope per the task's hard constraints — "never modify passage alignment
logic," and this audit does not re-derive alignment quality either).

**Is `epsilon=0.05` empirically grounded?** No (Section 6) — and, separately and more
consequentially, it is **moot**: the metric's quality gate currently excludes 100% of the
corpus (Section 5, Section 9), so no threshold value for this metric currently determines
any Discover outcome.

**Comparison to Lazy Prices**: see Section 20. `disclosure_change_score` is the metric in
this audit's batch most methodologically adjacent to Lazy Prices' spirit (a whole-document,
alignment-based "how much changed" measure), but its concrete mechanism — a fixed-weight
composite over discrete alignment-outcome-class word shares — is a **project-specific
extension**, not a direct reimplementation of Lazy Prices' cosine-similarity approach; the
project's own docs (cited in the financial-condition audit, Section 15) already draw this
same distinction.

---

## 13. `uncertainty_intensity_change` deep dive

**Dictionary source**: Loughran-McDonald `uncertainty` core category
(`CORE_CATEGORIES`, `financial_language_config.py:34`) — the standard, third-party,
literature-established Loughran-McDonald uncertainty word list, imported and matched exactly
like the other six core categories (positive/negative/litigious/constraining/strong_modal/
weak_modal). Unlike the custom taxonomy categories (risk/financial_condition/governance/
strategy), this is not project-authored.

**Denominator**: `feature_eligible_primary` words, per side (Section 4) — the same
report-side population `net_tone_change`/`governance_language_change` use. **Same denominator
issue check, per the audit's explicit instruction to verify this**: the length-control test
applied to `governance_language_change`'s top findings (Section 16) was not separately
re-run for `uncertainty_intensity_change`'s own top findings in this pass (time/scope
constraint of this audit round), but the **mechanism is identical** — `uncertainty_rate`
uses the exact same `feature_eligible_primary` per-side word-count denominator as
`governance_rate`, via the same `compute_core_category_change`/`custom_category_rate`
family of functions (Section 3). Given that `governance_language_change`'s top findings
were shown to be substantially denominator-driven for the *same report pairs* that also
appear near the top of several other metrics (ACT 2017→2018 in particular), this metric
should be treated as **presumptively equally exposed** to the same artifact until a
dedicated length-control pass is run — this is flagged as an open follow-up (Section 23),
not resolved here.

**Negation handling**: same mechanism as the financial-condition taxonomy (7F.1 §3) —
negation is tracked (`negated_hit_count`) but never subtracted from the raw count; a negated
"no uncertainty" phrase still counts as an uncertainty hit. This applies identically to all
core categories, uncertainty included.

**Directionality**: signed, with a direction filter (`v > 0` only, i.e. only *increases* in
uncertainty language are Discover-eligible for `largest_uncertainty_increase` — a decrease,
however large, is never shown under this tab). Section 9 shows this filter is the dominant
factor cutting this metric's eligible pool from 5 (magnitude-only) to 1 (full gate) — 13 of
25 pairs have `uncertainty_intensity_change > 0` at all, but only 5 of those also clear
`epsilon=1.0` in magnitude, and only 1 survives with report-side quality also passing.

**Report-length sensitivity**: presumptively material, per above — not independently
re-verified in this pass.

**Threshold scale-appropriateness**: of the four remaining `rate_per_1000_words` metrics
sharing `epsilon=1.0`, `uncertainty_intensity_change`'s raw `epsilon=1.0` happens to land
close to an empirically defensible band (between p75=0.760 and p85=1.020, and almost exactly
at `median+1×scaledMAD`=0.869 — Section 10) — this is the metric in the group where the
shared constant is *least* obviously miscalibrated relative to its own distribution, though
still undocumented as having been chosen that way (Section 6).

---

## 14. `net_tone_change` deep dive

**Exact formula**: change-in-difference, not a simple rate difference of one category —
`net_tone(side) = positive_rate(side) - negative_rate(side)`, then
`net_tone_change = net_tone(later) - net_tone(earlier)` (Section 3). Algebraically this
equals `(positive_rate_later - positive_rate_earlier) - (negative_rate_later -
negative_rate_earlier)` — a **difference of two independent rate-changes**, not a ratio and
not a single category's rate difference.

**Vocabulary balance**: Loughran-McDonald `positive` and `negative` word lists are
independently sized, third-party dictionaries — this audit did not re-count list sizes (out
of scope: "never alter dictionary/taxonomy terms," and counting list length does not require
altering it, but was not prioritized in this pass given the larger structural findings
below). The metric is symmetric in *formula* (equal weight to positive and negative rate
changes) regardless of any size imbalance in the underlying word lists.

**Denominator**: `feature_eligible_primary` words per side (Section 4), same population as
`governance_language_change`/`uncertainty_intensity_change`.

**Report-length sensitivity — directly tested** (length-controlled variant, holding the
earlier side's word count fixed for the later-side rate, the same M2-style method 7F.1 used
for financial condition), for the current top-5 Discover-eligible `net_tone_change` pairs:

| Pair | Actual change | Length-controlled change | Later/earlier word ratio | % of actual surviving |
|---|---|---|---|---|
| ACT 2017-06-30→2018-06-30 | -6.635 | **-8.463** | 0.654 | 128% (magnitude *increases* under length control) |
| BEL 2018-12-31→2019-12-31 | -3.826 | -3.704 | 1.266 | 97% |
| ACT 2021-06-30→2022-06-30 | -2.446 | -1.876 | 1.128 | 77% |
| ACT 2019-06-30→2020-06-30 | -2.153 | -1.653 | 1.076 | 77% |
| BEL 2017-12-31→2018-12-31 | -1.058 | -0.558 | 1.117 | **53%** (would drop below epsilon under length control) |

**Which side drives large values**: for ACT 2017→2018 specifically — the same pair flagged
as the flagship pre-7F.4 financial-condition denominator-shrinkage artifact — the *raw hit
counts* collapsed even more sharply than the word count did (`positive_count`: 947→456,
a 52% drop, versus a 35% word-count drop), so length-controlling this pair actually makes
its negative-tone-shift finding **larger**, not smaller: this is evidence of a genuine
decline in positive-tone language use, not primarily a length artifact, in sharp contrast to
the same pair's `governance_language_change` and (previously) financial-condition M1 findings
(Section 16). **`net_tone_change` is not uniformly a denominator-shrinkage artifact metric**
— it is genuinely mixed: 4 of the top 5 findings above are robust (53–128% survive length
control) with only one falling meaningfully (BEL 2017→2018, 53%).

**Does `epsilon=1.0` admit ~60% of pairs, and is the threshold far too permissive? — verified
empirically, not assumed**: **yes, confirmed**. `net_tone_change`'s magnitude-only pass rate
at `epsilon=1.0` is **15/25 = 60%** (Section 7, Section 9) — the corpus's own median absolute
value (1.271) already exceeds the shared epsilon. This is the most selectivity-mismatched
metric of the six audited here relative to the identical numeric epsilon its four siblings
share: `uncertainty_intensity_change` (20%), `risk_language_introduction` (20%),
`risk_language_removal` (16%), `governance_language_change` (16%) are all 3–4x more
selective at the same raw number. (After the direction filter, `net_tone_change`'s
*Discover-eligible* count drops to 5/25 = 20% — comparable to the others — but that is an
artifact of the direction filter removing more than half the magnitude-qualifying pairs, not
evidence that the underlying epsilon is well-calibrated to this metric's scale; Section 9's
full breakdown makes this visible.)

---

## 15. `risk_language_introduction`/`removal` deep dive

**Exact NEW/REMOVED passage population**: `hits_for_status(feature_eligible_primary,
AlignmentStatus.NEW)` for introduction, `AlignmentStatus.REMOVED` for removal (Section 3,
Section 4) — passages with genuinely no counterpart on the other side (a NEW passage exists
only in the later report; a REMOVED passage only in the earlier report), restricted to the
same `feature_eligible_primary` base population as every other metric in this audit.

**Denominator**: the single-sided word count of exactly that NEW or REMOVED population
(Section 4) — **not** the report-side total. This is the structurally smallest, most
volatile denominator of any metric in this audit: the top findings' underlying populations
range from **686 to 4,638 words** and **4 to 25 passages** (Section 11), versus 30,000–
48,000 words for the report-side metrics over comparable pairs.

**Collision/ambiguity handling impact**: none of the six metrics' populations exclude
collision-flagged content (Section 11) — for `risk_language_introduction`/`_removal`
specifically, a NEW/REMOVED population that is largely re-worded boilerplate (a legitimate,
common, evidence-documented corpus condition per `financial_language_config.py`'s collision
thresholds) still contributes fully.

**Restructuring false-positive risk**: real, though not directly quantified in this pass — a
passage reclassified from `SUBSTANTIALLY_MODIFIED` to `NEW`+`REMOVED` by the alignment
classifier (a boundary case the alignment logic itself governs, out of this audit's scope to
re-derive) would shift risk-language hits from *not counted at all* by either metric into
*fully counted* by one or both — this is a structural exposure of the metric's population
definition to alignment-classification boundary behavior, not something this audit
re-verified against raw alignment data.

**Alignment defect dominance vs. taxonomy sparsity**: for this corpus's actual top findings,
the dominant issue is **taxonomy/hit-count sparsity**, not an alignment defect per se — the
underlying NEW/REMOVED populations are not implausibly assembled (10–25 passages is a
plausible amount of genuinely new/removed content across a year), but the `risk` category's
hit *rate* within that small population is thin enough (1–18 hits) that the resulting
per-1,000-word rate is dominated by single-digit count noise (Section 11's perturbation
table).

**Symmetry by construction**: yes — `risk_language_introduction` and `risk_language_removal`
use structurally identical formulas (`introduction_or_removal_rate`), differing only in
which `AlignmentStatus` and which side's word count they draw from. Their corpus
distributions are similar in shape (both right-skewed, both zero-inflated: `risk_language_
removal`'s median is exactly 0.000; `risk_language_introduction`'s is 0.129, close to zero)
but not identical in scale by company (Section 8) — BEL and KP2 dominate both, ACT and SBP
are near-zero on both, SDL only registers on introduction, SUR only marginally on either.

**Top-finding manual inspection** (all 9 currently Discover-eligible pairs across both
metrics, reconstructed hit/word/passage counts — Section 11's table):

| Pair | Metric | Hits/Words/Passages | Verdict | Driver classification |
|---|---|---|---|---|
| BEL 2019→2020 | introduction | 3/686/4 | **CAUTION** | taxonomy/hit-count artifact — 3 hits is not a statistically meaningful "risk language introduced" claim |
| KP2 2022→2023 | introduction | 16/4,638/15 | **PASS** | genuine broad-based signal — largest hit count and passage count of the introduction group |
| BEL 2016→2017 | introduction | 3/958/10 | **CAUTION** | same sparsity concern as BEL 2019→2020, though spread across more passages |
| BEL 2018→2019 | introduction | 6/4,416/25 | **PASS with caution** | larger population (25 passages), but still only 6 hits — plausible but thin |
| SDL 2024→2025 | introduction | **1**/794/2 | **FAIL** | a single dictionary hit driving the entirety of SDL's only Discover-eligible risk-introduction finding — not a defensible "largest risk introduction" claim |
| KP2 2022→2023 | removal | 18/3,703/20 | **PASS** | genuine broad-based signal, same pair as KP2's introduction PASS above (both directions moved this year) |
| KP2 2020→2021 | removal | 10/3,079/18 | **PASS with caution** | plausible, moderate count |
| KP2 2023→2024 | removal | 3/1,587/10 | **CAUTION** | sparsity concern |
| BEL 2016→2017 | removal | 3/2,189/18 | **CAUTION** | sparsity concern (same pair as BEL 2016→2017's introduction CAUTION above — both directions thin for this pair) |

Classified drivers: KP2's two 2022→2023 findings (introduction and removal on the same pair)
and KP2 2020→2021 removal are the corpus's strongest genuine broad-based signals for this
metric pair. SDL's single-hit finding is the clearest taxonomy-artifact case in this entire
audit — weaker evidentiary support than any finding flagged in the 7F.1–7F.4 financial-
condition work.

---

## 16. `governance_language_change` deep dive — structural comparison to the old
financial-condition metric

**Direct structural comparison, as requested**: `governance_language_change` uses the
*exact same* formula shape the pre-7F.4 financial-condition metric (M1) used —
`rate_change(custom_category_rate(later, cat), custom_category_rate(earlier, cat))`
(Section 3) — over the identical `feature_eligible_primary` per-side word-count denominator.
The only difference from the old M1 is which custom-taxonomy category (`"governance"` vs.
`"financial_condition"`) is being rated. **This audit tested directly whether the same
denominator-shrinkage artifact 7F.1–7F.4 diagnosed and fixed for M1 also appears in
`governance_language_change`'s current top findings — it does:**

| Pair | Governance actual change | Length-controlled change (earlier words held fixed) | Later/earlier word ratio | % of actual surviving |
|---|---|---|---|---|
| ACT 2017-06-30→2018-06-30 | **+1.736** (current #1 eligible finding) | **+0.413** | 0.654 | **24%** |
| BEL 2016-12-31→2017-12-31 | +1.279 (#2) | +1.175 | 0.977 | 92% |
| BEL 2018-12-31→2019-12-31 | **-1.070** (#3) | **-0.158** | 1.266 | **15%** |
| ACT 2023-06-30→2024-06-30 | -1.055 (#4) | -0.941 | 1.052 | 89% |

**Two of the four current Discover-eligible governance findings — including the #1-ranked
finding — are 76% and 85% denominator-shrinkage artifacts respectively.** ACT
2017-06-30→2018-06-30 is the identical report pair 7F.1 used as the flagship worked example
for M1's artifact (words 45,963→30,068, a 35% drop): the governance hit count barely moved
(96→115, +20%) while the rate moved sharply (+83% relative) purely because the shared
denominator shrank. This is not a coincidence of shared word-count tables — it is the same
underlying mechanism (report got shorter → per-1,000-word rate inflates for any category
whose hit count didn't shrink proportionally) that 7F.4 already built a specific fix for
(M3, share-of-custom-taxonomy-hits) — **but that fix was applied only to the financial-
condition candidate, not generalized to `governance_language_change`, which remains on the
old M1-style formula.**

**Manual top-3 case work**:

1. **ACT 2017→2018 (+1.736, 24% survives length control)**: governance hits 96→115 (earlier)
   → (later); words 45,963→30,068. The 19-hit increase, spread over a report that also
   shrank by 15,895 words, is mostly a length artifact by the same standard 7F.1–7F.4 already
   applied to this exact pair's financial-condition value. **Verdict (superseded, see
   correction below): FAIL as a standalone "largest governance shift" claim** — classified as
   **report-length artifact**.
2. **BEL 2016→2017 (+1.279, 92% survives)**: governance hits 111→152 (+37%), words
   34,891→34,078 (essentially flat, -2.3%). This is a genuine, non-artifactual governance-
   language increase. **Verdict: PASS.** Classified as a **real, broad-based change**.
3. **BEL 2018→2019 (-1.070, 15% survives)**: governance hits 171→165 (essentially flat,
   -3.5%), words 38,063→48,206 (+26.6%). The near-flat hit count combined with a large word-
   count increase mechanically depresses the rate — this is the inverse-direction version of
   the same artifact (report got *longer*, diluting an unchanged amount of governance
   language). **Verdict (superseded, see correction below): FAIL as a standalone claim** —
   classified as **report-length artifact**.

> **Correction (added post-hoc, Track 7F.7a, 2026-09-23)** — read before relying on verdicts 1
> and 3 above. 7F.7a built and validated the share-based governance replacement metric this
> section's own Assessment paragraph called for (`governance_share_change`, "M3-G": governance
> hits ÷ total custom-taxonomy hits, denominator-robust by construction — full derivation in
> `docs/governance-metric-redesign-7f7a.md` Section 3–5). Testing M3-G directly against ACT
> 2017→2018 and BEL 2018→2019 — the same test this section performed with the length-controlled
> M2-G figures above — produces a materially different verdict than "report-length artifact":
>
> - **ACT 2017→2018**: M3-G = **+0.0865**, the corpus's **3rd-largest** share movement (not
>   demoted to noise). Governance hits grew +19.8% *while total custom-taxonomy activity fell*
>   -7.1% (`H`: 322→299) — a real, broad-based increase (`board` +10, `regulatory_compliance`
>   +9, `remuneration` +5 hits), not merely a shrinking-denominator inflation of a flat hit
>   count. Revised verdict: **CAUTION, not FAIL** — the *rate* (`M1-G = +1.736`) is still
>   unreliable and should not be quoted as-is, but the underlying claim "governance-language
>   disclosure increased in this pair" is directionally correct and non-trivial in magnitude,
>   not a pure artifact of the report getting 34.6% shorter.
> - **BEL 2018→2019**: M3-G = **-0.0635**, the corpus's **4th-largest** share movement.
>   Governance hits are indeed nearly flat (-3.5%, as this section found), but the decline in
>   *share* is driven by other custom-taxonomy categories (`risk`, `financial_condition`,
>   `strategy`) growing faster than governance as the report lengthened (`H`: 360→401,
>   +11.4%) — a real relative decline in governance's share of disclosure attention, distinct
>   from this section's "diluting an unchanged amount of governance language" framing, which
>   implied no real change occurred at all. Revised verdict: **CAUTION, not FAIL** — "governance
>   held roughly steady in absolute terms while other disclosure topics expanded around it" is
>   the more accurate reading than "artifact, no real change."
>
> **What stands, and what's corrected**: the diagnosis that `governance_language_change`
> (M1-G)'s *rate* is denominator-shrinkage-sensitive, structurally identical to pre-7F.4
> financial-condition M1, and unsafe to publish as-is remains fully valid — that is this
> section's central claim and the reason 7F.7a was commissioned. What's corrected is the
> stronger, pair-level claim that these two specific pairs' *underlying disclosure changes*
> were themselves mostly-artifactual — a share-based, denominator-robust metric shows both are
> real, non-trivial governance-language shifts, just not of the magnitude M1-G's raw rate
> implies. The Section 21 verdict (`MODIFY_METRIC_AND_THRESHOLD`) and Section 22 HIGH risk
> ranking for this metric are unaffected by this correction — if anything the case for
> replacing M1-G with a share-based metric is strengthened, since M1-G is now shown to produce
> not just an inflated magnitude but occasionally a wrong qualitative story ("artifact" vs.
> "real, different in size than reported").

**Assessment**: `governance_language_change` should be treated as carrying the same
methodological risk 7F.1 originally identified for financial-condition M1, until an
equivalent share-based (or otherwise length-normalized) alternative is evaluated. This audit
does not prescribe the specific replacement formula (consistent with the discipline 7F.1–7F.3
applied before recommending M3) — that is future-track work (Section 23).

---

## 17. Manual top-finding validation (all six metrics)

Top 5 currently-eligible findings per metric (fewer than 5 shown where fewer are eligible),
PASS/CAUTION/FAIL verdict, and driver classification.

**`disclosure_change_score`**: **0 currently eligible findings** (Section 5, Section 9) —
no top-5 table is possible; every pair fails the quality gate regardless of value. Not
independently assessable via manual inspection until the gate question is resolved.

**`uncertainty_intensity_change`** (1 eligible):

| Rank | Pair | Value | Quality | Driver | Verdict | Classification |
|---|---|---|---|---|---|---|
| 1 | BEL 2019-12-31→2020-12-31 | +2.175 | GOOD/USABLE | uncertainty hits 366→254 but *rate* rose 7.59→9.77 (words must have shrunk faster than hits) | **CAUTION** | plausibly a **report-length interaction** (not independently length-controlled in this pass — flagged, not confirmed, per Section 13) |

**`net_tone_change`** (5 eligible — full table already in Section 14's length-control test):
ACT 2017→2018 **PASS** (genuine decline, length control *increases* the magnitude);
BEL 2018→2019 **PASS** (97% survives); ACT 2021→2022 **PASS** (77% survives); ACT 2019→2020
**PASS** (77% survives); BEL 2017→2018 **CAUTION** (only 53% survives length control,
borderline). Classified as **real, broad-based tone change** for 4 of 5; **report-length-
sensitive, borderline** for BEL 2017→2018.

**`risk_language_introduction`** (5 eligible) / **`risk_language_removal`** (4 eligible):
full table in Section 15. Summary: **PASS** — KP2 2022→2023 (both directions), KP2
2020→2021 (removal). **CAUTION** — BEL 2019→2020, BEL 2016→2017 (both directions), BEL
2018→2019 (introduction), KP2 2023→2024 (removal). **FAIL** — SDL 2024→2025 (introduction,
single-hit artifact).

**`governance_language_change`** (4 eligible): full case work in Section 16, corrected by the
Section 16 callout above (7F.7a). **CAUTION** (rate magnitude denominator-inflated, but
underlying share-based signal real per 7F.7a M3-G — not a pure artifact) — ACT 2017→2018, BEL
2018→2019. **PASS** (real, broad-based change) — BEL 2016→2017. Fourth eligible pair (ACT
2023→2024, -1.055, 89% survives length control) — **PASS**.

**Aggregate driver classification across all 19 top findings inspected in this pass**:

| Classification | Count | Metrics |
|---|---|---|
| Real, broad-based disclosure change | 8 | net_tone_change (4), governance (2), risk intro/removal (2) |
| Report-length-inflated rate, but share-based signal real (corrected, 7F.7a) | 2 | governance (2) |
| Report-length artifact | 1 | net_tone (1, borderline) |
| Taxonomy/hit-count sparsity artifact | 6 | risk introduction/removal (6, of which 1 is a single-hit FAIL) |
| Not independently assessed (gate excludes / not length-controlled) | 2 | disclosure_change_score (all), uncertainty (1, flagged not confirmed) |

---

## 18. Cross-metric comparability

**Units**: four of the six metrics (`net_tone_change`, `uncertainty_intensity_change`,
`risk_language_introduction`, `risk_language_removal`, `governance_language_change` — five,
not four; `disclosure_change_score` is the only one on a different unit) share the literal
unit `rate_per_1000_words` and the literal epsilon `1.0`. Their empirical distributions
differ by roughly **3x in scale** at the median (`net_tone_change` median |Δ| = 1.271 vs.
`governance_language_change` median |Δ| = 0.144 — an 8.8x ratio at the median, even wider
than the 3x figure at the shared threshold's empirical percentile), and their **selectivity
at the identical numeric epsilon ranges from 16% to 60%** of the corpus (Section 7, Section
9).

**Is one shared epsilon for rate-per-1000 metrics methodologically defensible?** **No** —
this generalizes 7F.1's finding (originally made only for the financial-condition metric
relative to its four then-siblings) to the four remaining `rate_per_1000_words` metrics
audited here directly against each other, with the same evidence standard: `net_tone_change`
admits 60% of the corpus at magnitude-only `epsilon=1.0`; `governance_language_change` and
`risk_language_removal` admit only 16%. A single shared constant cannot simultaneously
represent "materially large" for both a metric whose median pair already exceeds it and a
metric whose 85th percentile pair does not reach it.

**Does Discover give a false impression that "material" means the same thing across
metrics?** Yes, as currently presented: all `rate_per_1000_words` metrics (and financial
condition's old M1, pre-7F.4) use the identical unit label and, historically, the identical
threshold, with no UI signal that the underlying corpus distributions differ this much.
7F.4 has already partially addressed this for financial condition by moving it to a
different unit (`share`) with its own independently-calibrated threshold; the same
asymmetry remains live for all five of the metrics audited here that still use
`rate_per_1000_words`/`1.0`.

---

## 19. UI semantics

| Metric | Discover label (`web/lib/config/discovery.ts`) | Finding-copy description (`web/lib/content/finding-copy.ts`) | What it actually measures | Issue found |
|---|---|---|---|---|
| `disclosure_change_score` | "Largest overall disclosure change" | "the largest overall disclosure-change magnitude currently published, based on lexical and structural passage-alignment change" | Correctly described in spirit, but **currently always empty** (0/25 eligible) — the description does not warn the reader that this tab may show nothing, nor why | UI does not distinguish "no findings because nothing changed" from "no findings because the quality gate excludes the whole corpus" (same collapsing issue 7F.1 §16 found for financial condition, here total rather than partial) |
| `uncertainty_intensity_change` | "Largest uncertainty increase" | "Uncertainty-related language increased notably compared with the prior report" | Change in Loughran-McDonald `uncertainty` category rate, positive-direction only | Reasonably accurate; does not mention report-length sensitivity (presumptively shared with governance, Section 13) |
| `net_tone_change` | "Largest negative-tone shift" | "Overall language tone shifted notably more negative" | `(positive_rate - negative_rate)` change, negative-direction only | Reasonably accurate; "overall tone" slightly overstates precision — this is specifically Loughran-McDonald positive-vs-negative word-list balance, not a general sentiment model |
| `risk_language_introduction` | "Largest risk-language introduction" | "New risk-related language was introduced in passages that are **new or substantially changed** since the prior report" | Only `AlignmentStatus.NEW` passages (Section 3, confirmed against `introduction_or_removal_rate`/`hits_for_status`) | **Confirmed mismatch**: `SUBSTANTIALLY_MODIFIED` passages are never included in either the numerator or denominator. The Python `METRIC_CATALOG` entry (`publisher.py:118`) makes the identical claim ("NEW/SUBSTANTIALLY_MODIFIED-introduced passage content") — this is a two-place, not one-place, documentation error, both inconsistent with the actual formula |
| `risk_language_removal` | "Largest risk-language removal" | "Previously present risk-related language was removed from passages **changed** since the prior report" | Only `AlignmentStatus.REMOVED` passages | Same category of mismatch as above (the frontend copy's "changed" phrasing implies `SUBSTANTIALLY_MODIFIED` involvement; the Python catalog is explicit: "REMOVED/SUBSTANTIALLY_MODIFIED-removed passage content", `publisher.py:127`) |
| `governance_language_change` | "Largest governance-language shift" | "Governance-related language changed notably compared with the prior report" | Change in custom-taxonomy governance rate | Accurate as far as it goes, but does not flag the metric's demonstrated denominator-shrinkage sensitivity (Section 16) — a reader has no way to know the published *magnitude* is inflated for 2 of this metric's 4 current findings, even though 7F.7a's correction (Section 16) shows the underlying direction/rough size for both is real, not purely artifactual |

**Does the UI collapse no-data/failed-quality/below-materiality states?** Yes, for all six
metrics — `DiscoveryResultsTable`'s generic "No results for these filters" empty state
(referenced in the financial-condition audit, §16, and unchanged for these six metrics)
applies uniformly. This is most consequential for `disclosure_change_score`
(`largest_overall_change`): a user who filters to any company sees the same generic empty
message whether that company has genuinely small disclosure changes or (the actual,
corpus-wide reality) a universally-failing quality gate — there is no path in the current UI
for a user to discover that `largest_overall_change` is not currently a functioning ranking
at all.

---

## 20. Relationship to Lazy Prices

| Metric | Classification | Rationale |
|---|---|---|
| `disclosure_change_score` | **INSPIRED_BY_LAZY_PRICES** | Whole-document, alignment-based "how much changed" measure — the same conceptual territory as Lazy Prices' document-similarity approach, per the project's own README framing and the financial-condition audit's citation of this project's "Lazy-Prices-style" characterization of Milestone 3 work. The *concrete mechanism* (fixed-weight composite over discrete alignment-outcome-class word shares, not cosine similarity — Section 12) is a project-specific design choice built on top of that inspiration, not a reimplementation of the paper's own method. |
| `net_tone_change` | **PROJECT_SPECIFIC_EXTENSION** | Built entirely on Loughran-McDonald sentiment dictionaries (`positive`/`negative` core categories) — a separate, well-established third-party accounting-text literature (Loughran & McDonald 2011), not the Lazy Prices paper's own methodology (document-level cosine similarity). No repo doc attributes this metric's formula to Lazy Prices specifically. |
| `uncertainty_intensity_change` | **PROJECT_SPECIFIC_EXTENSION** | Same rationale — Loughran-McDonald `uncertainty` category, not Lazy Prices. |
| `risk_language_introduction` / `risk_language_removal` | **PROJECT_SPECIFIC_EXTENSION** | Built on the project's own custom taxonomy (`risk` category) combined with this project's own passage-alignment NEW/REMOVED attribution — neither Loughran-McDonald nor Lazy Prices defines an equivalent construct. |
| `governance_language_change` | **PROJECT_SPECIFIC_EXTENSION** | Same rationale as financial condition's original classification (7F.1 §15) — built on the project's own custom taxonomy, authored in-house per `config/financial_language_custom_taxonomy.yaml`'s own header comment, distinct from both Loughran-McDonald and Lazy Prices. |

No metric in this batch is classified **DIRECTLY_ADAPTED_FROM_LAZY_PRICES** — consistent with
the instruction not to attribute custom language-rate metrics to Lazy Prices without direct
repo-doc support, and consistent with 7F.1 §15's identical finding for the (methodologically
similar) financial-condition metric.

---

## 21. Metric-by-metric verdict

| Metric | Verdict | Rationale |
|---|---|---|
| `disclosure_change_score` | **MORE_DATA_NEEDED** | The formula and (documented-as-provisional) weights are not indicted by this audit on their own terms, and the underlying normalization (word-share composite) is structurally more length-robust than the rate-per-1000-word metrics (Section 12). But the metric cannot be usefully calibrated, ranked, or even observed in Discover while its quality gate excludes 100% of the current corpus (Section 5, Section 9) — any threshold or weight recalibration would be working against zero eligible data points. The dominant blocker (`document_quality == NEEDS_REVIEW` in 17/25 pairs) is a Milestone 3 similarity-quality question outside this metric's own formula, and outside `findings.py`/`labels.py`'s scope entirely. |
| `net_tone_change` | **RECALIBRATE_THRESHOLD / VERIFY_NORMALIZATION** | Primarily a threshold problem, not a formula defect: the metric's own scale is ~3-9x larger than its `rate_per_1000_words` siblings (Section 7, Section 18), making the shared `epsilon=1.0` both too permissive for this metric specifically (60% magnitude-only pass rate) and incomparable across metrics. The direction-filter interaction (Section 9) further complicates simple threshold recalibration alone. A metric-specific epsilon (following 7F.1 Q2's precedent) is necessary at minimum; the rate-difference-of-a-difference formula itself does not need to change, since most top findings are individually length-control-robust (Section 14) — hence "VERIFY_NORMALIZATION" rather than a confirmed normalization defect: the scale mismatch is a calibration/epsilon problem, distinct in kind from `governance_language_change`'s confirmed structural denominator-shrinkage defect (Section 16). |
| `uncertainty_intensity_change` | **RECALIBRATE_THRESHOLD** | The raw `epsilon=1.0` already sits in a plausible empirical band for this specific metric (between p75 and p85, near `median+1×scaledMAD` — Section 10) — the least-miscalibrated of the four `rate_per_1000_words` siblings. A dedicated, metric-specific empirical threshold (rather than the shared literal) is still warranted for defensibility and cross-metric consistency, but the magnitude of change needed is smaller than for the other three. The presumptive-but-unconfirmed shared denominator-shrinkage exposure (Section 13) should be checked before finalizing any new threshold. |
| `risk_language_introduction` | **MODIFY_METRIC_AND_THRESHOLD** | The corpus's largest findings rest on single-digit hit counts over populations as small as 686 words / 4 passages (Section 11, Section 15) — a threshold fix alone cannot address a denominator that is structurally too small to be stable; the population itself (single-sided NEW-only, no minimum-size floor) needs reconsideration, analogous to how 7F.3 found M3's denominator needed a structural change, not just a different cutoff, though here the deeper problem is population *size*, not population *definition*. |
| `risk_language_removal` | **MODIFY_METRIC_AND_THRESHOLD** | Same rationale as introduction, plus a zero-inflation problem (Section 8, Section 10) that breaks robust-statistic threshold-setting methods entirely (median/MAD both collapse to 0). |
| `governance_language_change` | **MODIFY_METRIC_AND_THRESHOLD** | Directly reproduces the pre-7F.4 financial-condition M1 artifact on the same underlying report pairs (Section 16) — 2 of its 4 current eligible findings are 76-85% denominator-shrinkage artifacts. This is not a threshold problem (lowering or raising `epsilon` does not fix a numerator/denominator mismatch); it needs the same category of structural fix 7F.3/7F.4 already validated and shipped for financial condition (e.g., a share-of-custom-taxonomy-hits reformulation), followed by its own independent threshold calibration exercise mirroring 7F.3's method. |

---

## 22. Risk prioritization

Ranked by methodological risk (normalization weakness, threshold weakness, quality-gate
mismatch, ranking instability, interpretability, source-text validation) — **not** by
business importance, per the task's instruction.

| Rank | Metric | Risk | Primary driver |
|---|---|---|---|
| 1 (HIGH) | `governance_language_change` | **HIGH** | Confirmed, reproduced denominator-shrinkage artifact on real top findings (76-85% of two of its four current findings) — the exact defect class already proven serious enough to warrant a full four-track remediation (7F.1-7F.4) for a structurally identical metric. This is the only metric in this batch with **direct, quantified evidence** of a materially wrong headline finding currently live in Discover. |
| 2 (HIGH) | `risk_language_introduction` / `risk_language_removal` | **HIGH** | Structural denominator-size fragility (686-4,638 words, 1-25 hits) makes the corpus's largest findings for both metrics trivially sensitive to single-digit count noise (Section 11); one currently-eligible finding (SDL) rests on exactly one dictionary hit. Zero-inflation additionally breaks standard robust-threshold methods for removal specifically. |
| 3 (MEDIUM) | `net_tone_change` | **MEDIUM** | Largest scale-mismatch of any metric relative to its shared epsilon (Section 18), but most top findings are individually robust to length control (Section 14) and the underlying signal (positive/negative dictionary rates) is a well-established, literature-standard construct. The fix needed is threshold/normalization recalibration, not a formula redesign. |
| 4 (MEDIUM) | `disclosure_change_score` | **MEDIUM** | Not because the formula is unsound (it is the most length-robust normalization of the six, Section 12) but because it is currently **entirely non-functional in production** (0/25 eligible) — a different kind of risk (complete absence of signal) than the others' risk of a *wrong* signal. Ranked below the HIGH tier because there is no evidence of an actively misleading published finding (there are no published findings for this metric at all currently). |
| 5 (LOW-MEDIUM) | `uncertainty_intensity_change` | **LOW-MEDIUM** | Best-calibrated-by-coincidence of the four `rate_per_1000_words` siblings (Section 10, Section 13); the outstanding open question (shared denominator-shrinkage exposure) is presumptive, not yet confirmed to be a live problem the way it is for governance. |

---

## 23. Proposed next milestones

Grouped, not six independent tracks, consistent with the task's preference and with how
7F.1-7F.5 sequenced the financial-condition work.

- **7F.7a — Governance-language metric redesign** (highest risk, most directly analogous to
  completed work): apply the same M1→M3-style methodology 7F.1-7F.4 already validated —
  candidate share-based/length-normalized alternatives, corpus-wide comparison, threshold
  calibration, implementation, production rollout. This is the metric with the clearest,
  already-proven remediation path.
- **7F.7b — Risk introduction/removal population-size review**: determine whether a minimum
  NEW/REMOVED word-count or hit-count floor should gate eligibility (paralleling 7F.3 §9's
  identified-but-unresolved `H`-denominator gap for M3), and/or whether a smoothed/shrinkage
  estimator is warranted given the demonstrated single-digit-hit fragility (Section 11,
  Section 15). Should also resolve the two confirmed UI/catalog description mismatches
  (Section 19) as a low-risk, low-effort companion fix.
- **7F.7c — Per-metric threshold recalibration for `net_tone_change` and
  `uncertainty_intensity_change`**: apply 7F.3's percentile/robust-MAD convergence method to
  set metric-specific epsilons (not a shared `1.0`) for these two, without necessarily
  changing either metric's underlying formula — `net_tone_change`'s formula does not need
  redesign (Section 14's length-control results are largely reassuring), only its threshold
  and, ideally, resolution of the direction-filter interaction documented in Section 9.
- **7F.7d — `disclosure_change_score` quality-gate investigation** (distinct from a metric
  redesign — the formula itself is not implicated): determine why `document_quality` is
  `NEEDS_REVIEW` for 17/25 pairs and why `low_confidence_share` exceeds 0.25 for a majority
  of the corpus, whether those upstream Milestone 3 thresholds are themselves as
  conservative as intended, and whether `_gate_feature`'s strictness (shared with
  `new_rate_words`, also currently 0/25 eligible) should be reconsidered independently of
  this metric's own formula/weights. This is a prerequisite to any future weight-calibration
  work the `feature_config.py` docstring already anticipates ("expected to be revised after
  inspecting real feature results on the corpus") — that inspection cannot happen with zero
  eligible pairs.
- **7F.7e — Discover empty-state/materiality UX harmonization** (can run in parallel with
  the above, low engineering risk): generalize the four-state empty-state pattern 7F.4
  already shipped for financial condition (no comparisons / failed quality / below
  materiality / normal results) to the remaining five metrics, so `disclosure_change_score`'s
  100% gate failure and `net_tone_change`'s direction-filter exclusions are visible to a user
  instead of collapsing into one generic message (Section 18, Section 19).

---

## Final summary table

| Metric | Formula family | Quality gate | Current epsilon | Empirical selectivity (full gate) | Main methodological risk | Verdict | Priority |
|---|---|---|---|---|---|---|---|
| `disclosure_change_score` | Word-weighted composite over alignment-outcome-class shares | feature | 0.05 (`score_0_1`) | 0% (0/25 — gate excludes entire corpus) | Quality gate excludes 100% of corpus; weights explicitly documented as uncalibrated | MORE_DATA_NEEDED | MEDIUM |
| `net_tone_change` | Change-in-difference of two Loughran-McDonald rates | report-side | 1.0 (`rate_per_1000_words`) | 20% (5/25, after direction filter); 60% magnitude-only | Scale mismatch vs. shared epsilon; direction filter removes most magnitude-qualifying pairs | RECALIBRATE_THRESHOLD / VERIFY_NORMALIZATION | MEDIUM |
| `uncertainty_intensity_change` | Single-category rate difference | report-side | 1.0 (`rate_per_1000_words`) | 4% (1/25, after direction filter); 20% magnitude-only | Presumptive (unconfirmed) shared denominator-shrinkage exposure | RECALIBRATE_THRESHOLD | LOW-MEDIUM |
| `risk_language_introduction` | Single-sided NEW-population rate | alignment-change | 1.0 (`rate_per_1000_words`) | 20% (5/25) | Extremely small hit-count/word denominators; one finding rests on 1 hit | MODIFY_METRIC_AND_THRESHOLD | HIGH |
| `risk_language_removal` | Single-sided REMOVED-population rate | alignment-change | 1.0 (`rate_per_1000_words`) | 16% (4/25) | Same as introduction, plus zero-inflation breaking robust thresholds | MODIFY_METRIC_AND_THRESHOLD | HIGH |
| `governance_language_change` | Report-side category rate difference (M1-style) | report-side | 1.0 (`rate_per_1000_words`) | 16% (4/25) | Confirmed, reproduced denominator-shrinkage artifact (2 of 4 current findings 76-85% artifact) | MODIFY_METRIC_AND_THRESHOLD | HIGH |

### Plain answers

1. **Which current Discover metrics are trustworthy as-is?** None of the six without
   qualification. `net_tone_change` is the closest — most of its top findings survive length
   control, and its underlying dictionaries are literature-standard — but its threshold is
   demonstrably miscalibrated relative to its own scale.
2. **Which only need threshold recalibration?** `uncertainty_intensity_change` most cleanly
   (its formula is not implicated by this audit's evidence); `net_tone_change` needs
   threshold/normalization work but not a formula change.
3. **Which have normalization problems?** `governance_language_change` (confirmed, same
   defect class as the old financial-condition M1) and `net_tone_change` (scale mismatch
   relative to its rate-per-1000-word siblings, though its formula itself tested largely
   robust).
4. **Which are alignment-sensitive enough to require deeper review?**
   `risk_language_introduction`/`risk_language_removal` — their single-sided NEW/REMOVED
   populations are the smallest, most volatile denominators of any metric audited, directly
   exposed to alignment-classification boundary behavior (NEW+REMOVED vs.
   SUBSTANTIALLY_MODIFIED).
5. **Which thresholds are undocumented heuristics?** All six — `git log` confirms every
   epsilon value in this batch was introduced whole, in one commit, with no later revision
   and no documented empirical, percentile, or literature-based rationale (Section 6),
   exactly matching 7F.1's finding for the pre-7F.4 financial-condition epsilon.
6. **Which metrics genuinely inherit methodology from Lazy Prices?** None directly.
   `disclosure_change_score` is the closest in spirit (INSPIRED_BY_LAZY_PRICES); the other
   five are PROJECT_SPECIFIC_EXTENSIONs built on Loughran-McDonald dictionaries or this
   project's own custom taxonomy, not Lazy Prices' document-similarity method.
7. **Which metrics should not remain user-facing without redesign?**
   `governance_language_change` (confirmed misleading top finding, live in production today)
   and `risk_language_introduction` (a single-hit-driven finding, SDL, currently live in
   production) are the two with the clearest, most concrete evidence of a currently-
   publishable, currently-eligible finding that a careful reader would not consider a
   trustworthy "largest shift."

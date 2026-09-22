# Methodology audit: "Largest financial-condition shift" (Discover)

**Scope**: read-only audit. No code, configuration, thresholds, or production
data were changed to produce this document. All corpus figures below were
read from the local research database (`market_documents`, 25 current
`ReportPairLanguageFeatures` rows as of `2026-09-11` builds) via ad hoc,
read-only SQL — the same tables the publishing pipeline reads, not a
re-derivation.

---

## 1. Executive summary

`largest_financial_condition_shift` ranks report-pairs by the **absolute
year-over-year change in how densely a custom "financial_condition"
vocabulary appears in a company's primary narrative text**, normalized to a
rate per 1,000 words. It is a **language-intensity** metric, not a sentiment
or performance metric: it cannot tell you whether financial condition
improved or worsened, only that the *volume of financial-condition
terminology* changed.

Key facts established below:

- The formula, denominator, and gating logic are fully traceable and
  reproducible by hand (Sections 2–5); worked examples for ACT, BEL, and SBP
  reproduce the production values exactly (Section 6, within float rounding).
- The materiality threshold `epsilon = 1.0` (per 1,000 words) is a literal
  constant in `findings.py`, applied uniformly to **five different**
  `rate_per_1000_words` metrics (tone, uncertainty, governance, risk
  introduction/removal, financial condition) — not calibrated per-metric.
  No commit message, comment, test, or design document in this repository
  attributes it to empirical calibration, percentile analysis, or published
  literature (Section 9).
- Across the current 25-pair corpus, only **2 of 25 pairs** (ACT
  2017→2018, SBP 2023→2024) clear both the quality gate and the epsilon
  gate for this metric. BEL — despite always passing report-side quality —
  never comes close: its largest observed shift is 0.55, about half the
  threshold (Section 11).
- The metric is **not** derived from the *Lazy Prices* paper's methodology
  (cosine similarity of whole filings); it is a project-specific extension
  built on Loughran-McDonald-style dictionary counting plus an
  internally-authored taxonomy (Section 15).

---

## 2. End-to-end calculation pipeline

```
source annual report PDF (outside Docker, on disk)
   -> extraction / segmentation -> Passage rows (research DB)
        [services/passage_segmentation.py]
   -> PassageAlignment (earlier <-> later passage correspondence)
        [models/alignment.py; services/passage_alignment.py]
   -> structured-content classification (per passage, recomputed each run)
        [services/structured_content_audit.py::classify_passage]
   -> financial-language matching (per passage, per side)
        [services/financial_language_signals.py::match_passage,
         services/financial_language_tokenization.py]
        -> PassageLanguageSignal (per-passage counts, eligibility flags)
        -> PassageLanguageCategoryHit (per-category/subcategory hit counts)
   -> pair-level aggregation
        [services/financial_language_signals.py::_aggregate_pair_features]
        [services/financial_language_metrics.py::aggregate_side,
         custom_category_rate, rate_change]
        -> ReportPairLanguageFeatures.financial_condition_rate_earlier
        -> ReportPairLanguageFeatures.financial_condition_rate_later
        -> ReportPairLanguageFeatures.financial_condition_language_change
   -> quality/eligibility assessment
        [services/financial_language_quality.py::assess_report_side_quality]
        -> ReportPairLanguageFeatures.report_side_signal_quality
        -> ReportPairLanguageFeatures.report_side_primary_eligible
   -> publication build (research DB -> app DB, one immutable snapshot)
        [publishing/publisher.py::_comparison_metrics]
        -> ComparisonMetrics.financial_condition_language_change
        -> ComparisonMetrics.report_side_quality_ok / report_side_primary_eligible
   -> materiality + quality gate, magnitude ranking
        [publishing/findings.py::CANDIDATES (epsilon=1.0),
         publishing/findings.py::eligible_candidates,
         publishing/discovery.py::rank_discovery_items]
        -> app.discovery_items (discovery_type='largest_financial_condition_shift')
   -> Discover page query + render
        [web/lib/repositories/postgres-discovery-repository.ts,
         web/lib/services/discovery-service.ts,
         web/components/DiscoveryResultsTable.tsx]
```

### Step-by-step, with exact citations

1. **Passage matching** — for every `PassageAlignment` row marked
   `primary_alignment = True` in the alignment run pinned to the pair's
   current `FeatureRun`, both the earlier- and later-side passage text is
   tokenized sentence-by-sentence and matched against the dictionary term
   index.
   `src/market_documents/services/financial_language_signals.py:428-458`
   (`_run_signal_build`, `match_for`), matching logic in
   `src/market_documents/services/financial_language_signals.py:161-200`
   (`match_passage`).

2. **Per-passage persistence** — one `PassageLanguageSignal` row per
   (passage, alignment row, side), carrying `primary_narrative_eligible`,
   `feature_eligible`, `passage_word_count`, and core-category counts
   (`src/market_documents/services/financial_language_signals.py:482-506`,
   columns defined at `src/market_documents/models/financial_language.py:147-198`).
   Custom-taxonomy hits (including `financial_condition`) are persisted
   separately, one row per (signal, category, subcategory), in
   `PassageLanguageCategoryHit`
   (`src/market_documents/services/financial_language_signals.py:508-520`).

3. **Population filtering and aggregation** — of all matched passages, only
   those that are both `primary_narrative_eligible` (not one of six
   structured-content categories, Section 4) **and** `feature_eligible` are
   included in the rate calculation. This population is called
   `feature_eligible_primary` in code
   (`src/market_documents/services/financial_language_signals.py:577-596`).
   `aggregate_side` (`src/market_documents/services/financial_language_metrics.py:119-135`)
   sums `financial_condition` hits and words per side over exactly this
   population.

4. **Rate and change** —
   `custom_category_rate` → `rate_per_1000_words` → `rate_change`, all pure
   functions in `src/market_documents/services/financial_language_metrics.py:100-107,212-213`.
   The pair-level result is assembled at
   `src/market_documents/services/financial_language_signals.py:809-811,814-815`
   and persisted on `ReportPairLanguageFeatures`
   (`src/market_documents/models/financial_language.py:410,415-416`).

5. **Quality/eligibility** —
   `assess_report_side_quality`
   (`src/market_documents/services/financial_language_quality.py:69-147`)
   runs against `FinancialLanguageConfig` thresholds
   (`src/market_documents/services/financial_language_config.py:55-113`)
   and sets `report_side_signal_quality` / `report_side_primary_eligible`.

6. **Publication mapping** — `_comparison_metrics`
   (`src/market_documents/publishing/publisher.py:196-213`) copies these
   fields verbatim (never re-derived) into `ComparisonMetrics`.

7. **Materiality + ranking gate** — `CANDIDATES`
   (`src/market_documents/publishing/findings.py:83-116`) defines the
   `largest_financial_condition_shift` candidate with `epsilon=1.0` and
   gate `_gate_report_side` (both `report_side_signal_quality_ok` and
   `report_side_primary_eligible` must be true). `eligible_candidates`
   (`src/market_documents/publishing/findings.py:129-147`) drops any
   candidate whose `|value| / epsilon < 1.0`. `rank_discovery_items`
   (`src/market_documents/publishing/discovery.py:64-98`) applies the same
   gate corpus-wide and writes ranked `DiscoveryItem` rows, `score =
   magnitude = |value| / epsilon`.

8. **Discover UI** reads `app.discovery_items` for
   `discovery_type='largest_financial_condition_shift'`
   (`web/lib/repositories/postgres-discovery-repository.ts`), and the page
   only lists a type tab at all if `listAvailableDiscoveryTypes` returns at
   least one row for it (`web/lib/services/discovery-service.ts:42-53,90`).

---

## 3. Taxonomy / dictionary definition

Two distinct, coexisting dictionaries feed the financial-language pipeline,
distinguished by `category`:

- **Loughran-McDonald** (imported, third-party): `positive, negative,
  uncertainty, litigious, constraining, strong_modal, weak_modal` — the
  `CORE_CATEGORIES`
  (`src/market_documents/services/financial_language_config.py:28`).
  **None of these contribute to `financial_condition_language_change`.**
- **Custom project taxonomy** (authored in-house, not third-party):
  `risk, financial_condition, governance, strategy` — `CUSTOM_TAXONOMY_CATEGORIES`
  (`src/market_documents/services/financial_language_config.py:32`), defined in
  `config/financial_language_custom_taxonomy.yaml`.

`financial_condition` has **12 subcategories**, each a short seed list, not
an exhaustive lexicon (`config/financial_language_custom_taxonomy.yaml:27-40`):

| Subcategory | Terms |
|---|---|
| revenue | revenue, turnover, sales growth |
| cost_margin | cost of sales, gross margin, operating margin |
| cash_flow | cash flow, operating cash flow, free cash flow |
| debt | borrowings, debt covenant, gearing ratio |
| liquidity | current ratio, working capital, cash reserves |
| capital_expenditure | capital expenditure, capex, investment in property plant and equipment |
| impairment | impairment, impairment charge, write-down |
| working_capital | working capital, inventory days, receivables days |
| dividends | dividend, dividend declared, dividend cover |
| tax | taxation, effective tax rate, deferred tax |
| restructuring | restructuring, restructuring costs, retrenchment |
| acquisitions_disposals | acquisition, disposal, business combination |

The YAML's own header comment states this taxonomy is "authored by this
project (not a third-party dictionary)... deliberately small and
defensible — seed terms per subcategory, not an exhaustive lexicon... per
the milestone brief's instruction not to implement every conceivable
category. Reviewed and approved before implementation (see Milestone 6
planning conversation)." No further written rationale for *which* seed
terms were chosen is present in this repository beyond that note.

**Matching mechanics** (`services/financial_language_tokenization.py`):

- **Case-sensitivity**: no. The base tokenizer NFKC-normalizes and
  lowercases before matching (`services/financial_language_tokenization.py:5-8`
  docstring; `similarity_tokenization.tokenize`).
- **Stemming/lemmatization**: explicitly not used. Only "regular English
  pluralization" and two narrow UK/SA spelling-variant suffix swaps
  (`-ize/-ization → -ise/-isation`, `-yze → -yse`) are applied, and only
  **at dictionary-import time** (generating extra literal term rows), never
  as a runtime stemmer (`services/financial_language_tokenization.py:30-103`).
- **Phrase matching**: yes, longest-phrase-first, greedy, left-to-right per
  sentence (`match_phrases_and_unigrams`,
  `services/financial_language_tokenization.py:122-158`). A hyphenated token
  is also checked against its hyphen-split form so "going concern" and
  "going-concern" match once, never twice.
- **Duplicate/overlapping matches**: a token consumed by an accepted phrase
  match is never separately counted as a unigram match (same function,
  phrase precedence). Overlapping hits across *different* categories are
  still possible (nothing prevents a term appearing in more than one
  taxonomy category from being counted for each).
- **Negation**: tracked but **does not change the metric**. `match_passage`
  increments `custom_hits[hit_key]` unconditionally, and separately
  increments `custom_hits_negated[hit_key]` only informationally
  (`services/financial_language_signals.py:181-192`, specifically line
  190 vs. 191-192). A negated "no impairment" is counted exactly the same
  as "impairment." Negation window is 5 tokens, sentence-scoped, with a
  fixed set of clause-boundary conjunctions that stop the scope early
  (`negated_token_positions`, `services/financial_language_tokenization.py:161-186`).
  Empirically, in the SBP example below, 3 of 71 earlier-side hits and 4 of
  55 later-side hits were flagged negated but still counted.
- **Structured content (tables/headers/captions/boilerplate)**: passages
  classified as `short_fragment_invalid`, `broken_fragment_sequence`,
  `numeric_or_table_like_source`, `contents_or_index_like`,
  `caption_or_label_like`, or `financial_table_rendered_as_prose` are
  **excluded** from the population that drives this rate
  (`PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES`,
  `services/financial_language_metrics.py:22-31`). `list_content`,
  `table_context`, `currency_exposure_table_mixed`, and `uncertain`
  passages **are retained by default** — only available as separate
  sensitivity variants, not applied to the headline rate.
- **Passages vs. whole report vs. filtered narrative**: the rate is computed
  over a **filtered narrative subset** — the intersection of
  primary-narrative-eligible and feature-eligible passages on each side —
  not whole-report text and not raw passages.

---

## 4. Exact formulas

For one report side (earlier or later):

```
custom_category_rate(side, "financial_condition")
    = 1000 * financial_condition_hit_count / feature_eligible_primary_word_count
```

(`rate_per_1000_words`, `services/financial_language_metrics.py:100-101`;
`custom_category_rate`, same file, `212-213`; denominator is
`side.words`, itself `sum(passage_word_count for feature_eligible_primary
rows on that side)`, `aggregate_side`, `119-135`.)

```
financial_condition_language_change
    = financial_condition_rate_later - financial_condition_rate_earlier
```

This is a **plain arithmetic difference of two rates**, not a relative
percentage, not a log difference, not a standardized (z-scored) difference
(`rate_change`, `services/financial_language_metrics.py:104-107`; wired at
`services/financial_language_signals.py:809-811`).

**Sign**: positive means the later report used more financial-condition
terminology per 1,000 words than the earlier one; negative means less. This
is stated directly in code/docs
(`src/market_documents/publishing/publisher.py:142-148` metric-catalog
entry: "Positive means more financial-condition language; negative means
less"; confirmed in `docs/implementation-details.md:385-388`).

**Discover ranks by magnitude, not signed value**: `eligible_candidates`
computes `magnitude = abs(value) / epsilon`
(`publishing/findings.py:143`) and both per-comparison finding selection
and corpus ranking sort by `-magnitude`
(`publishing/findings.py:155-157`; `publishing/discovery.py:86-88`). A
large increase and a large decrease are treated as equally "large" a
shift — the metric answers "how much did financial-condition language
intensity move," not "did it move up or down."

---

## 5. The denominator, precisely

The denominator is **not** any of: whole-report word count, all matched
passages, or a dedicated "financial analysis" section. It is:

> the total word count of passages on one report side that are (a)
> `primary_narrative_eligible` (excludes the 6 structured-content
> categories in Section 3) **and** (b) `feature_eligible` (excludes
> passages the Milestone 3 feature pipeline itself treats as
> non-substantive — see `feature_metrics.py::passage_excluded_from_features`).

This population is `feature_eligible_primary` in
`_aggregate_pair_features` (`services/financial_language_signals.py:577-596`),
and it is **narrower** than the persisted
`primary_narrative_earlier_words`/`primary_narrative_later_words` columns
on `ReportPairLanguageFeatures`, which apply only filter (a), not (b). This
is confirmed empirically below (Section 6): for ACT's 2017→2018 pair,
`primary_narrative_earlier_words = 47,811` but the actual rate denominator
(reconstructed from raw hit counts) is `45,963` — about 3.9% smaller. A
reader trying to reproduce the rate from the persisted
`primary_narrative_*_words` columns alone would get a slightly wrong
answer; the true denominator requires the `feature_eligible` filter too.

**Sensitivity to parsing/structure**: yes, materially. Because the
denominator is a *filtered* population, anything that shifts how many
words land in `feature_eligible_primary` — extraction/segmentation
differences, a passage getting reclassified as `table_context` vs. prose,
a change in `feature_excluded` logic — changes the rate even if the
underlying disclosure content is identical. The pipeline records five
alternate alignment-change denominators precisely because of this
sensitivity (`alignment_change_analyzed_words_all/_excl_ambiguous/_hml/_hm/_h`,
`services/financial_language_signals.py:834-837`), though note those
alternates apply to the *alignment-change* layer, not the report-side rate
this Discover metric uses (Section 7).

---

## 6. Worked examples (reproduced from the live database, 2026-09-22)

All three pairs below were located by matching the requested approximate
deltas against the current `report_pair_language_features` rows. Values
close to +0.553/+1.021/-1.103 are used; the corpus's actual current values
differ slightly from the prompt's figures (production data has moved since
those figures were noted — see caveat at the end of this section), but the
same reconstruction method applies unchanged.

Raw counts below were queried directly from `passage_language_signals` /
`passage_language_category_hits`, filtered to
`primary_narrative_eligible = true AND feature_eligible = true` and
`category = 'financial_condition'` — i.e., exactly the population and
category the production code uses.

### BEL, 2017-12-31 → 2018-12-31

| | Earlier (FY2017) | Later (FY2018) |
|---|---|---|
| financial_condition hits | 59 | 87 |
| feature-eligible primary-narrative words | 34,078 | 38,063 |
| rate per 1,000 words | 59,000 / 34,078 = **1.7313** | 87,000 / 38,063 = **2.2857** |

`financial_condition_language_change = 2.2857 - 1.7313 = +0.5544`
(persisted value: `0.554361999609233`). Matches the requested "≈ +0.553."
`report_side_signal_quality = GOOD`, `report_side_primary_eligible = True`.
Magnitude `0.5544 / 1.0 = 0.5544` — **below** the 1.0 materiality bar, so
this pair never appears in `largest_financial_condition_shift`.

### ACT, 2017-06-30 → 2018-06-30

| | Earlier (FY2017) | Later (FY2018) |
|---|---|---|
| financial_condition hits | 90 | 89 |
| feature-eligible primary-narrative words | 45,963 | 30,068 |
| rate per 1,000 words | 90,000 / 45,963 = **1.9581** | 89,000 / 30,068 = **2.9600** |

`financial_condition_language_change = 2.9600 - 1.9581 = +1.0019`
(persisted value: `1.0018606998472677`). Requested figure was "≈ +1.021";
the current corpus's actual closest ACT pair is `+1.0019` — close but not
identical, likely reflecting corpus/pipeline drift since that figure was
recorded (this project's own docs note re-extraction and alignment
corrections have changed downstream counts over time, e.g.
`docs/exact-hash-reconciliation-experiment.md`). `report_side_signal_quality
= GOOD`, `primary_eligible = True`. Magnitude `1.0019` clears the `1.0`
bar — **this pair is Discover-eligible.**

### SBP, 2023-12-31 → 2024-12-31

| | Earlier (FY2023) | Later (FY2024) |
|---|---|---|
| financial_condition hits (incl. 3 negated) | 71 | 55 (incl. 4 negated) |
| feature-eligible primary-narrative words | 17,246 | 18,247 |
| rate per 1,000 words | 71,000 / 17,246 = **4.1169** | 55,000 / 18,247 = **3.0142** |

`financial_condition_language_change = 3.0142 - 4.1169 = -1.1027`
(persisted value: `-1.102702557591038`). Matches the requested "≈ -1.103"
almost exactly. `report_side_signal_quality = USABLE` (both sides' dictionary
match rate is just under the 0.05 "borderline" band —
`report_side_warning_reasons`: "earlier dictionary match rate 0.049 is
borderline... later dictionary match rate 0.047 is borderline"),
`primary_eligible = True` (USABLE still counts as eligible — Section 7).
Magnitude `1.1027` clears the bar — **Discover-eligible.**

**Caveat on reproducibility**: raw hit/word counts *are* persisted exactly
(one `PassageLanguageCategoryHit` row per category/subcategory per
passage-signal, one `PassageLanguageSignal.passage_word_count` per
passage), so the calculation above is a genuine reconstruction from stored
data, not an approximation — anyone with research-database access can
re-run the two SQL queries used here and get the same integers.

---

## 7. Report-side vs. alignment-change quality, and eligibility interaction

The project deliberately splits quality into two independent layers
(`services/financial_language_quality.py`, module docstring lines 1-29):

- **Report-side quality** (`assess_report_side_quality`): gates on
  transition-period/irregular-gap flags, primary-narrative word coverage,
  and dictionary match-rate bands. It **never** takes alignment confidence,
  collision, or passage-correspondence uniqueness as input — by
  construction, since report-side rates are just per-side sums, they never
  required a proven one-to-one passage correspondence.
- **Alignment-change quality** (`assess_alignment_change_quality`): gates
  on alignment confidence, ambiguous-word share, collision-flagged share,
  and upstream `FeatureQuality` — because NEW/REMOVED attribution and
  substantially-modified deltas genuinely depend on trustworthy
  passage-to-passage correspondence.

`financial_condition_language_change` is a **pure report-side metric**: it
sums hits and words per side independently and differences the two rates.
**Passage alignment does not affect the value itself** — the alignment run
is only used to select *which* passages exist on each side (via
`PassageAlignment.primary_alignment = True` rows) and their eligibility
flags, not to pair earlier/later occurrences of a term. This is why
`largest_financial_condition_shift` is gated by `_gate_report_side`, not
`_gate_alignment_change`
(`publishing/findings.py:104-111`; confirmed in
`publishing/publisher.py:81` `_CANDIDATE_QUALITY_SCOPE` mapping it to
`"report_side"`).

**Why BEL passes quality but fails materiality**: BEL's report-side quality
is `GOOD` for every one of its 6 current pairs (Section 11) — coverage and
dictionary match rate are all comfortably inside the "no penalty" bands.
Nothing about BEL's *data quality* is in question. It simply never
generates a large enough swing in financial-condition-term density: its
largest observed `|change|` is 0.5544, about 55% of the 1.0 threshold. BEL's
absence from this Discover ranking is a **materiality-filter effect**, not
a quality exclusion (Section 11 quantifies this further).

---

## 8. Origin of epsilon = 1.0

**Where it lives**: a literal float, `1.0`, passed as the fourth positional
argument to `CandidateSpec` for five of the eight discovery candidates —
`largest_uncertainty_increase`, `largest_negative_tone_shift`,
`largest_risk_introduction`, `largest_risk_removal`,
`largest_governance_shift`, and `largest_financial_condition_shift` — all
sharing the `unit="rate_per_1000_words"`
(`src/market_documents/publishing/findings.py:88-111`). The other two
candidates use different units and different epsilons: `0.05` for
`disclosure_change_score` (`score_0_1` unit) and `0.02` for
`new_rate_words` (`share` unit).

**Git history**: `findings.py` was added in its entirety in a single
commit, `adc4c3d` ("Front end built in React; includes companies page,
discover page, comparison evidence, comparison summary, and methodology"),
2026-07-29. `git log --follow -p` shows no prior revision of this file —
the epsilon values, including `1.0`, appear fully-formed with no
incremental history to inspect for rationale.

**What the code comment says** (`findings.py:72-75`, directly above the
`epsilon` field):

> "Materiality bar: a candidate whose `|value|` is below `epsilon` is
> dropped even if it is the only eligible candidate in the pool — never
> headline a change too small to matter."

This explains the *purpose* of having an epsilon at all, not why `1.0`
specifically was chosen.

**What `docs/publishing.md` says** (line 180): "Every candidate must also
clear a per-metric materiality epsilon (magnitude ≥ 1× epsilon) to be
eligible at all — a technically-largest-in-its-pool value that's still
immaterial never ranks." Again, mechanics, not derivation.

**Searched and found nothing** attributing `1.0` to: academic literature,
the *Lazy Prices* paper, Loughran-McDonald methodology, a percentile/
distribution analysis of this corpus, or a documented manual-inspection
exercise. No test encodes *why* `1.0` was picked (tests only verify the
gate mechanism works, e.g. `tests/publishing/test_publishing_findings.py`'s
`test_sub_epsilon_candidate_never_selected`, which uses the
`disclosure_change_score` epsilon of `0.05`, not `1.0`, as its example).

**Contrast with a threshold that *is* documented this way**: elsewhere in
this same codebase, `dictionary_match_rate_anomalous_threshold`/
`dictionary_match_rate_borderline_threshold`
(`services/financial_language_config.py:77-96`) carry an explicit,
detailed evidentiary comment: "the post-Loughran-McDonald-import corpus
(25 pairs, 6 companies) has a per-side primary-narrative match rate ranging
0.043-0.069 (median ~0.056); only KP2's five pairs (0.043-0.050) sit under
0.05... Three explicit bands, evidence-calibrated rather than chosen to
make every pair pass." **No comparable comment or evidence trail exists
for `epsilon = 1.0`.** The project's own convention for what a calibrated
threshold looks like in writing is well established elsewhere; its absence
here is conspicuous rather than merely undocumented-by-omission.

**Conclusion, mapped to the audit's lettered options**: closest match is
**(G) a heuristic design choice**, with elements of **(H) inherited/default
value** (the same `1.0` is reused unchanged across five semantically
different metrics — uncertainty, tone, governance, risk introduction, risk
removal, and financial condition — suggesting it was chosen once, as a
round-number default for the `rate_per_1000_words` unit generally, not
derived per-metric). There is no evidence for (A) literature, (B) Lazy
Prices, (C) Loughran-McDonald methodology, (D) empirical calibration on
this corpus, or (E) percentile/distribution analysis. (F) manual inspection
cannot be ruled out (it may have "looked reasonable" against the same
corpus this audit examines) but is not documented anywhere found.

---

## 9. Git/history evidence (Section 8 of the requested outline)

- Commit `adc4c3d`, 2026-07-29, author `tonylizza`: introduces `findings.py`
  whole, alongside the entire React frontend, publishing tests, and dozens
  of data/audit CSVs in the same commit. This was a large, multi-part
  frontend-launch commit, not a focused "add materiality threshold" change.
- No later commit modifies the epsilon values in `findings.py` (single
  `git log --follow` entry for the file).
- No design/milestone doc (`docs/*.md`) discusses `1.0` specifically for
  `rate_per_1000_words` candidates; `docs/publishing.md`'s "Discovery
  rankings and findings" section documents the *mechanism* only.

**Explicit statement, since the audit asks not to infer rationale where
none is documented**: the origin of the specific numeric value `1.0` for
this metric's materiality threshold is **undocumented**. It is possible it
was chosen by informal inspection during frontend development, but no
artifact in this repository records that reasoning.

---

## 10. Corpus-wide distribution of |financial_condition_language_change|

Computed over all 25 current `ReportPairLanguageFeatures` rows (one per
report pair, current successful `LanguageSignalRun`), regardless of
eligibility/quality — i.e., every pair with a non-null value:

| Stat | Value |
|---|---|
| N | 25 |
| min | 0.0134 |
| max | 1.1027 |
| mean | 0.2930 |
| median | 0.1744 |
| std dev (population) | 0.3223 |
| p25 | 0.0593 |
| p50 | 0.1744 |
| p75 | 0.3696 |
| p90 | 0.8686 |
| p95 | 0.9866 |
| p99 | 1.0785 |

Threshold crossings (magnitude only, not yet quality-gated):

| Threshold | Count ≥ threshold |
|---|---|
| 0.25 | 9 |
| 0.50 | 5 |
| 0.75 | 4 |
| 1.00 | 2 |
| 1.25 | 0 |
| 1.50 | 0 |

Full sorted list (ticker, earlier period end → later period end, signed
change, `report_side_primary_eligible`, `report_side_signal_quality`):

```
SBP   2023-12-31 -> 2024-12-31   -1.1027  eligible=True   quality=USABLE
ACT   2017-06-30 -> 2018-06-30   +1.0019  eligible=True   quality=GOOD
ACT   2016-06-30 -> 2017-06-30   -0.9256  eligible=True   quality=GOOD
ACT   2016-06-30 -> 2024-06-30   -0.7832  eligible=False  quality=NEEDS_REVIEW
BEL   2017-12-31 -> 2018-12-31   +0.5544  eligible=True   quality=GOOD
SUR   2024-06-30 -> 2025-06-30   -0.4671  eligible=True   quality=GOOD
ACT   2019-06-30 -> 2020-06-30   -0.3696  eligible=True   quality=GOOD
ACT   2018-06-30 -> 2019-06-30   -0.2991  eligible=True   quality=GOOD
BEL   2020-12-31 -> 2021-12-31   +0.2783  eligible=True   quality=GOOD
ACT   2021-06-30 -> 2022-06-30   -0.2160  eligible=True   quality=GOOD
KP2   2023-12-31 -> 2024-12-31   +0.2109  eligible=True   quality=USABLE
ACT   2023-06-30 -> 2024-06-30   +0.1757  eligible=True   quality=GOOD
ACT   2020-06-30 -> 2021-06-30   -0.1744  eligible=True   quality=GOOD
BEL   2019-12-31 -> 2020-12-31   +0.1494  eligible=True   quality=GOOD
BEL   2018-12-31 -> 2019-12-31   +0.1414  eligible=True   quality=GOOD
SDL   2024-06-30 -> 2025-06-30   +0.0903  eligible=True   quality=USABLE
BEL   2016-12-31 -> 2017-12-31   -0.0743  eligible=True   quality=GOOD
SUR   2023-06-30 -> 2024-06-30   -0.0706  eligible=True   quality=GOOD
KP2   2019-12-31 -> 2020-12-31   -0.0593  eligible=True   quality=USABLE
KP2   2020-12-31 -> 2021-12-31   +0.0499  eligible=True   quality=USABLE
SBP   2024-12-31 -> 2025-12-31   +0.0447  eligible=True   quality=USABLE
KP2   2021-12-31 -> 2022-12-31   -0.0313  eligible=True   quality=USABLE
ACT   2022-06-30 -> 2023-06-30   +0.0240  eligible=True   quality=GOOD
BEL   2021-12-31 -> 2022-12-31   +0.0171  eligible=True   quality=GOOD
KP2   2022-12-31 -> 2023-12-31   -0.0134  eligible=True   quality=USABLE
```

Only 2 of 25 pairs (8%) clear `1.0` at all, and both do so barely (1.0019,
1.1027) — the threshold sits almost exactly at the corpus's own p95-p99
band (p95 = 0.9866, p99 = 1.0785). Practically, the 1.0 threshold currently
functions as roughly a **top-5-percentile filter** on this metric for this
corpus — whether by design or by coincidence is not documented (Section 8).

---

## 11. Company-level distribution

| Ticker | N pairs | min \|Δ\| | max \|Δ\| | median \|Δ\| | N ≥ 1.0 | % ≥ 1.0 |
|---|---|---|---|---|---|---|
| ACT | 9 | 0.0240 | 1.0019 | 0.2991 | 1 | 11.1% |
| BEL | 6 | 0.0171 | 0.5544 | 0.1454 | 0 | 0.0% |
| KP2 | 5 | 0.0134 | 0.2109 | 0.0499 | 0 | 0.0% |
| SBP | 2 | 0.0447 | 1.1027 | 0.5737 | 1 | 50.0% |
| SDL | 1 | 0.0903 | 0.0903 | 0.0903 | 0 | 0.0% |
| SUR | 2 | 0.0706 | 0.4671 | 0.2688 | 0 | 0.0% |

BEL, KP2, SDL, and SUR — 4 of 6 companies — **never** produce a
financial-condition shift large enough to clear 1.0 in the current corpus,
regardless of quality. SBP's 50% figure is based on only 2 pairs and should
not be read as a stable company characteristic. This is consistent with
"the 1.0 threshold is high relative to this corpus's typical variation," a
question the sensitivity analysis below quantifies further, without this
audit recommending a specific alternative.

---

## 12. Threshold sensitivity analysis (descriptive only — no change made)

Magnitude-only pass counts vs. eligibility-and-quality-gated pass counts
(the second column is what Discover would actually show at that
threshold, since `_gate_report_side` still applies regardless of epsilon):

| Threshold | Magnitude-only pass | Gated pass (eligible + quality) | Companies represented (gated) |
|---|---|---|---|
| 0.25 | 9 | 8 | ACT, BEL, SBP, SUR |
| 0.50 | 5 | 4 | ACT, BEL, SBP |
| 0.75 | 4 | 3 | ACT, SBP |
| 1.00 | 2 | 2 | ACT, SBP |
| 1.25 | 0 | 0 | — |
| 1.50 | 0 | 0 | — |

Notes:
- At `0.25`, one magnitude-passing pair (ACT 2016-06-30 → 2024-06-30,
  `NEEDS_REVIEW` / `report_side_primary_eligible=False`) is excluded by the
  quality gate, hence 9 magnitude-passing vs. 8 gated.
- **BEL only enters the eligible pool at or below ~0.55** (its own max);
  it never appears at `0.75` or above.
- **KP2 and SDL never enter the eligible pool at any threshold tested**
  down to `0.25`; KP2's max is 0.2109, SDL's only pair is 0.0903. They
  would need thresholds below ~0.21 and ~0.09 respectively to ever surface
  in this ranking.
- Rank ordering of the largest shifts is stable across all thresholds
  tested (SBP first, ACT second by a hair, then the rest) — lowering the
  threshold only adds more companies to the *bottom* of an already-fixed
  order; it never reorders the top of the list.

This analysis does not recommend a specific threshold. It shows that `1.0`
currently admits exactly 2 companies (ACT, SBP) out of 6, and that
materially different thresholds (0.5, 0.75) would still exclude most of
the corpus — the metric's underlying year-over-year variation in this
corpus is simply small for most companies.

---

## 13. Robustness / sensitivity to small changes

**How many additional hits would flip a near-miss?**

*BEL, +0.5544 (well below 1.0)*: earlier side fixed at 59 hits /
34,078 words (rate 1.7313); later side currently 87 hits / 38,063 words
(rate 2.2857). Holding both denominators constant, reaching `change = 1.0`
requires the later-side rate to reach `1.7313 + 1.0 = 2.7313`, i.e.
`2.7313 × 38,063 / 1000 ≈ 104.0` hits → **17 additional financial-condition
hits** in the later report (a ~20% increase over the current 87), with no
change in word count. BEL is not a borderline case relative to 1.0 — it
would need a substantial, not marginal, increase in term density.

*ACT, -0.9256 (a genuine near-miss just under 1.0)*: this is the 2016→2017
pair, not the eligible 2017→2018 one. Earlier side: 142 hits / 49,242 words
(rate 2.8837); later side fixed at 90 hits / 45,963 words (rate 1.9581).
Reaching `change = -1.0` requires the earlier-side rate to reach
`1.9581 + 1.0 = 2.9581`, i.e. `2.9581 × 49,242 / 1000 ≈ 145.7` hits → **only
4 additional financial-condition hits** in the earlier report (142 → 146,
a 2.8% increase) would have flipped this pair from "just below" to
"at/above" the materiality bar, with no change in word count. This
illustrates that at the margin, the threshold's practical selectivity can
hinge on single-digit term-occurrence differences — a handful of
boilerplate phrase repetitions (e.g., a "dividend declared" mentioned an
extra few times, or a slightly longer "impairment" discussion) is enough
to cross or miss the line.

**General sensitivity factors**:
- **Document length / denominator changes**: since the denominator is the
  feature-eligible primary-narrative word count (Section 5), a shorter
  later-side report (as in ACT 2017→2018: 45,963 → 30,068 words, a ~35%
  drop) inflates the later rate for a *fixed* hit count, independent of any
  real change in financial-condition disclosure. ACT's case shows this
  concretely: hit count barely changed (90 → 89, a decrease of 1), but the
  rate rose substantially (1.96 → 2.96) purely because the denominator
  shrank by over 15,000 words.
- **Parsing/structural differences**: any reclassification of passages
  into/out of the 6 excluded structured-content categories, or into/out of
  `feature_eligible`, changes the denominator (and possibly the numerator,
  if the reclassified passage contained hits) without any change in the
  underlying disclosure.
- **Tables vs. prose**: `financial_table_rendered_as_prose` is excluded
  from the denominator; `table_context`, `currency_exposure_table_mixed`,
  and `list_content` are *not* excluded by default, so numeric-heavy
  contexts can contribute to both numerator and denominator in ways a
  reader expecting "prose only" might not anticipate.
- **Repeated headings/boilerplate**: not specifically filtered for this
  metric; a repeated section heading like "Financial performance" is not a
  dictionary term itself, but standard boilerplate phrases like "dividend
  declared" or "cash flow" that recur verbatim across many short
  paragraphs will count every occurrence, with no deduplication beyond the
  phrase-vs-unigram precedence rule (Section 3).

---

## 14. Interpretability

Taking the formula literally: a change of **+X** per 1,000 words means "the
later report used, on net, X more financial-condition-taxonomy term
occurrences per 1,000 words of primary-narrative text than the earlier
report." For the specific bands requested:

- **+0.25**: roughly one additional financial-condition term for every
  4,000 words of narrative text, net.
- **+0.50**: roughly one additional term for every 2,000 words, net.
- **+1.00**: roughly one additional term for every 1,000 words, net — this
  is the literal reading, and it is correct: `rate_per_1000_words` is
  defined so that "1.0" is exactly "one hit per 1,000 words," not an
  approximation.
- **-1.00**: the mirror image — one *fewer* financial-condition term per
  1,000 words in the later report, net.

These are *net* changes, aggregated across all 12 subcategories (revenue,
cash flow, debt, impairment, dividends, etc.) — a +1.0 change could be one
subcategory increasing by 1.0 while all others are flat, or several
subcategories moving in different directions that happen to net to +1.0.
The metric as published does not decompose by subcategory.

**What the metric does NOT tell us**:

- **Deterioration vs. improvement**: no. "Financial condition" here is a
  *topic* label (revenue, debt, cash flow, impairment, dividends...), not
  a valence label. More impairment-related language and more
  dividend-related language both count toward the same positive number —
  the metric cannot distinguish a company writing more about a growing
  cash pile from one writing more about a going-concern-adjacent
  write-down. (Loughran-McDonald `positive`/`negative` sentiment is a
  *separate* set of core categories, used by `net_tone_change`, not by
  this metric at all.)
- **Positive vs. negative financial condition**: no, for the same reason.
- **Topic intensity vs. actual financial performance**: the metric measures
  language intensity (word choice/frequency) only. It has no access to,
  and makes no claim about, actual reported financial figures (revenue
  growth, margin, leverage ratios) beyond how often those *topics* are
  discussed in prose.
- **One concentrated new disclosure vs. diffuse wording changes**: no. The
  metric is a single aggregate rate difference; it cannot distinguish "one
  new 500-word impairment note" from "the same 20 extra term occurrences
  spread evenly across the whole report." (The pipeline *does* separately
  compute NEW/REMOVED attribution via alignment-change metrics like
  `risk_language_introduction`, but no equivalent
  `financial_condition_language_introduction`/`removal` metric is
  published or used by Discover — only the report-side net rate is.)

---

## 15. Relationship to Lazy Prices

**Not directly derived.** The project's own README states the *inspiration*
plainly (`README.md:5`): Lazy Prices "examines changes in U.S. SEC filings...
and studies whether those textual changes contain information about future
firm behavior and market outcomes." Multiple internal docs
(`docs/table-fragment-hardening-experiment.md:217`,
`docs/embedding-eligibility-token-limit-diagnostic.md:297,337`) describe
this project's core "unit of textual comparison" — the aligned passage,
and whole-document similarity/dissimilarity — as the "Lazy Prices-style"
measurement this project adapts. That describes **Milestone 3's**
`disclosure_change_score` (cosine/edit/structural similarity across
aligned passages — `services/similarity_metrics.py`,
`services/feature_extraction.py`) much more directly than it describes
`financial_condition_language_change`.

**Where they differ methodologically**:

| | Lazy Prices (per the repo's own characterization) | `financial_condition_language_change` |
|---|---|---|
| Core technique | Document-level similarity (cosine similarity over term-frequency vectors / edit distance) between consecutive filings | Loughran-McDonald-style dictionary counting against a small, project-authored custom taxonomy |
| Output | A single similarity/dissimilarity score per filing pair | A signed, topic-specific rate delta (financial-condition-term density) |
| Vocabulary basis | None — vocabulary is built from the two documents being compared, no external dictionary | An explicit, hand-authored 12-subcategory term list, distinct from Loughran-McDonald |
| Directionality | Magnitude of change only (how different, not what changed) | Signed (more/less financial-condition language), but not valenced (positive/negative) |

The custom taxonomy YAML's own header makes clear it is neither a
Lazy-Prices artifact nor a Loughran-McDonald extension: "Custom domain
taxonomy for Milestone 6 financial-language signals... Authored by this
project (not a third-party dictionary)."

**Conclusion**: `financial_condition_language_change` is a
**project-specific extension** of the broader disclosure-change research
program this codebase is built for, methodologically closer to a
Loughran-McDonald-style category-rate analysis than to Lazy Prices'
document-similarity approach. It should not be described as "the Lazy
Prices metric," nor should its threshold be assumed to inherit any
justification from that paper.

---

## 16. Discover UI semantics

The label "Largest financial-condition shift" currently means:

> **the largest shift, by magnitude, among report pairs that (a) pass
> `report_side` quality/eligibility gating and (b) have `|change| ≥ 1.0`
> per 1,000 words** — not the largest shift among *all* report pairs.

This is the second of the two options the audit asked to distinguish, and
it is confirmed directly in code: `eligible_candidates`
(`publishing/findings.py:129-147`) drops any candidate below `epsilon`
*before* ranking ever happens, and `rank_discovery_items`
(`publishing/discovery.py:64-98`) applies the identical filter corpus-wide.
A pair with the technically largest raw `|financial_condition_language_
change|` in the whole corpus that happened to be quality-excluded (e.g.
ACT 2016→2024 at 0.7832, `NEEDS_REVIEW`) would not appear even though its
magnitude is well above several eligible pairs.

**What the UI shows for each failure mode** — traced through
`web/lib/services/discovery-service.ts` and
`web/components/DiscoveryResultsTable.tsx`:

- **A discovery type with zero rows corpus-wide** (e.g., if no pair ever
  cleared `1.0` for financial condition): `listAvailableDiscoveryTypes`
  would not include it in `availableTypes`
  (`discovery-service.ts:90`), so the "Financial condition shift" tab
  itself would not be offered — a user could not select it and would never
  see a dedicated empty state for it specifically.
- **The selected type has rows generally, but the current filter
  combination (company/period/min-quality) excludes all of them**:
  `DiscoveryResultsTable` renders a generic empty state, "No results for
  these filters" / "Try a different company, period range, or a lower
  minimum quality" (`DiscoveryResultsTable.tsx:18-24`).
- **Metrics exist but a specific pair's value is missing (`None`)**: such a
  pair is simply never a candidate (`value is None: continue` in
  `eligible_candidates`, `findings.py:139-140`) — indistinguishable in the
  UI from a pair whose value existed but was quality-gated or
  sub-materiality.
- **Quality fails**: same as above — a `NEEDS_REVIEW`/`FAILED`-quality pair
  is silently absent from the ranked list, with no distinguishing UI signal
  (the requested comparison's own detail page does separately surface
  quality labels, but the Discover ranking list itself does not explain
  *why* a given pair is absent).
- **No report comparisons exist at all for a company/filter combination**:
  same generic empty state as above.

**As the audit anticipated**: these are collapsed into the same "No results
for these filters" message in the current UI. A user cannot currently tell,
from the Discover page alone, whether "no financial-condition shift shown
for BEL" means "BEL has no comparisons," "BEL's comparisons failed
quality," or "BEL's shifts are real but below the materiality bar" (which,
per Section 11, is BEL's actual situation in every case).

---

## 17. Methodology assessment

### A. Facts (what the code actually does)

- `financial_condition_language_change` is a signed, unstandardized
  difference of two per-1,000-word dictionary-hit rates, computed over a
  feature-eligible, primary-narrative-only passage population per report
  side.
- The taxonomy is a small, project-authored, 12-subcategory seed list,
  distinct from Loughran-McDonald.
- Negation does not change the count; case does not matter; stemming is not
  used (only regular pluralization and two narrow spelling-variant rules,
  applied at import time).
- Discover ranking requires both `report_side_primary_eligible`/quality
  ∈ {GOOD, USABLE} **and** `|change| ≥ 1.0` (per 1,000 words); it ranks by
  magnitude, not signed direction.
- `epsilon = 1.0` is a shared literal applied identically to five distinct
  `rate_per_1000_words` metrics; nothing in the codebase ties it to this
  specific metric's own distribution.
- Currently, 2 of 25 corpus pairs (ACT, SBP) clear this bar; 4 of 6
  companies (BEL, KP2, SDL, SUR) never do, in any of their current pairs.

### B. Documented rationale (why prior design artifacts say it was built
that way)

- The report-side/alignment-change quality split is thoroughly documented
  and evidence-based (Milestone 6 recalibration audit figures cited
  directly in `financial_language_quality.py`'s and
  `financial_language_config.py`'s docstrings/comments).
- The custom taxonomy's existence and scope ("deliberately small and
  defensible... per the milestone brief's instruction not to implement
  every conceivable category") is documented, though the specific term
  choices within each subcategory are not individually justified in
  writing.
- The materiality-gate *mechanism* (never headline an immaterial value) is
  documented; the specific *value* `1.0` is not.

### C. Inferences (reasonable interpretation where documentation is absent)

- `1.0` was most plausibly chosen as a single, round-number default applied
  uniformly across all `rate_per_1000_words`-unit candidates when the
  Discover feature was first built (commit `adc4c3d`), rather than derived
  separately for each of the five metrics that share it. This is inferred
  from the value's uniform reuse and the absence of any per-metric
  calibration comment, contrasted with the detailed evidentiary comments
  present elsewhere in the same module family for other thresholds.
- The current effect of `1.0` on this corpus — admitting roughly the top
  5-8% of observed shifts — is very likely incidental to how the value was
  originally chosen, since there is no evidence the corpus's actual
  distribution (Section 10) was consulted when `1.0` was set.

### D. Open questions (unresolved methodological questions)

1. Was `1.0` intended as a per-metric threshold or a shared placeholder
   default? If shared, should the five `rate_per_1000_words` metrics
   (tone, uncertainty, governance, risk introduction/removal, financial
   condition) really share one epsilon, given they may have very different
   natural distributions?
2. Should the Discover UI distinguish "no comparisons," "quality-excluded,"
   and "below materiality" instead of a single generic empty state,
   especially given this audit's finding that BEL is *always* the latter,
   never the former two?
3. Is a magnitude-per-1,000-words rate the right normalization at all,
   given its demonstrated sensitivity to denominator shrinkage (ACT's case,
   Section 13) independent of any real change in disclosure content? Would
   a word-count-controlled or share-of-report-length-adjusted measure
   behave more stably?
4. Should `financial_condition_language_change` be decomposed by
   subcategory (revenue, debt, impairment, dividends, etc.) so that a
   published finding can say *what kind* of financial-condition language
   moved, not just that the aggregate moved?
5. Given the taxonomy's individual term choices are undocumented beyond
   "reviewed and approved... see Milestone 6 planning conversation" (a
   conversation not preserved in this repository), is there a written
   record anywhere else (e.g., meeting notes, an external planning
   document) that could be linked here for future auditability?

---

## 18. Plain answers

1. **What exactly does `financial_condition_language_change` measure?**
   The year-over-year change in how often a small, project-authored list of
   ~40 financial-condition-topic terms/phrases (revenue, cash flow, debt,
   impairment, dividends, etc.) appears per 1,000 words of a company's
   primary narrative text, comparing the earlier and later report in a
   pair.

2. **Can I reproduce it manually from two reports?** Yes, and this audit
   did — Section 6 reconstructs BEL, ACT, and SBP's values from raw,
   persisted hit and word counts, matching the production values exactly
   (within floating-point rounding). You need database access to the raw
   `PassageLanguageCategoryHit`/`PassageLanguageSignal` rows (or the
   already-persisted `financial_condition_rate_earlier`/`_later` columns);
   the taxonomy and eligibility rules are also fully reproducible from
   files in this repository.

3. **Why is it normalized per 1,000 words?** So that reports/sides of
   different lengths can be compared on density rather than raw count —
   this is the standard convention this whole pipeline uses for every
   dictionary-based rate (`rate_denominator_words = 1000`, shared by all
   Loughran-McDonald and custom-taxonomy rates alike).

4. **Why is the materiality threshold 1.0?** Undocumented. It is a shared
   literal default applied to five different `rate_per_1000_words`
   metrics, introduced whole in one large frontend-launch commit with no
   design note explaining the specific value.

5. **Is 1.0 empirically calibrated or heuristic?** Best available
   classification: heuristic/inherited default (option G/H in Section 8's
   framework). No evidence of empirical calibration, percentile analysis,
   or literature-based derivation was found, in contrast to other
   thresholds in the same module family that *are* documented that way.

6. **How selective is 1.0 in the current corpus?** Very — only 2 of 25
   pairs (8%) and 2 of 6 companies clear it. It sits almost exactly at the
   corpus's own p95-p99 band (Section 10).

7. **Is BEL's lack of a Discover result analytically meaningful or mostly a
   consequence of threshold design?** Both, but primarily the latter as
   currently configured. BEL's report-side quality is `GOOD` throughout —
   there is nothing wrong with its data — but its actual observed
   financial-condition-language variation (max 0.5544) is real and about
   half the threshold. Whether "true stability" or "a threshold too high
   for this corpus" is the better description is exactly the open question
   Section 12's sensitivity table was built to surface, and this audit
   does not resolve it either way.

8. **Does this metric measure financial deterioration/improvement, or only
   change in the intensity of financial-condition language?** Only
   intensity/topic-density of language. It cannot distinguish improving
   from deteriorating financial condition, and it is entirely separate from
   the Loughran-McDonald `positive`/`negative` sentiment categories that
   drive `net_tone_change`.

9. **Is this metric directly supported by Lazy Prices, or is it a
   project-specific extension?** A project-specific extension. Lazy Prices'
   own approach (per this repo's characterization) is whole-document
   similarity/dissimilarity, which maps much more directly onto this
   project's Milestone 3 `disclosure_change_score`. The financial-condition
   metric is a separate, dictionary-based addition built on top of (and
   methodologically distinct from) that foundation.

10. **What methodological questions should be resolved before treating this
    threshold as a durable research choice?** See Section 17.D in full;
    most centrally: (a) whether one shared epsilon across five differently-
    distributed rate metrics is defensible, (b) whether the rate's
    sensitivity to denominator shrinkage from unrelated parsing/length
    effects (Section 13) undermines treating small crossings of `1.0` as
    meaningful, and (c) whether the Discover UI's collapsing of "no data,"
    "quality-excluded," and "below materiality" into one empty state should
    be fixed before this threshold is relied on for external communication.

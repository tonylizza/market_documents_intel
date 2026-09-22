# 7F.1 — Financial-Condition Metric Calibration

**Scope**: read-only analysis, building on
`docs/financial-condition-shift-methodology-audit.md`. No code, config,
thresholds, or production data were changed. All figures below were
computed from the current `market_documents` research database (25
current `ReportPairLanguageFeatures` rows, selected via
`get_current_language_signal_runs_by_pair`, the same "current run" rule
the publishing pipeline uses) as of `2026-09-22`.

**Goal**: determine whether `financial_condition_language_change` and its
materiality threshold are robust enough for production research use, and
answer the six questions posed for this milestone.

---

## Summary answer

**Not yet, as currently configured.** The metric itself is well-defined
and reproducible (confirmed again here). The problem is calibration: the
shared `epsilon = 1.0` is not empirically grounded for this metric, and —
more importantly — the metric's own normalization is sensitive enough to
denominator (word-count) changes that the single most load-bearing example
of a "real" Discover-eligible finding (ACT 2017→2018, `+1.0019`) is **~90%
denominator-shrinkage artifact, not a change in financial-condition
language volume**. Any of the six questions below can be answered
individually, but the denominator-sensitivity finding (Q3) is the one that
should gate whether this metric ships to users making decisions, because
it undermines the other five answers' practical significance.

---

## Q1: Should the threshold be empirical rather than fixed?

**Yes.** Per-metric percentile analysis (this section) shows `epsilon=1.0`
selects wildly different fractions of the corpus depending on the metric:

| Metric | min | median | p90 | p95 | max | N ≥ 1.0 (of 25) |
|---|---|---|---|---|---|---|
| `financial_condition_language_change` | 0.0134 | 0.1744 | 0.9256 | 1.0019 | 1.1027 | 2 (8%) |
| `governance_language_change` | 0.0315 | 0.1441 | 1.0697 | 1.2790 | 1.7360 | 4 (16%) |
| `net_tone_change` | 0.0650 | 1.2709 | 4.6930 | 5.9152 | 6.6346 | 15 (60%) |
| `uncertainty_intensity_change` | 0.0265 | 0.5394 | 2.1753 | 2.4952 | 2.6186 | 5 (20%) |

A single `1.0` epsilon is roughly a top-8-percentile filter for
`financial_condition_language_change`, but a top-40-percentile (median!)
filter for `net_tone_change`. `net_tone_change`'s median pair already
clears the bar; `financial_condition_language_change`'s p90 pair does not.
This is not "the same materiality bar applied fairly across five metrics"
— it is a bar that is nearly always cleared for tone and rarely cleared
for financial condition, purely because the two metrics have different
natural scales. That asymmetry has no principled basis in the shared
`epsilon=1.0` and should not be presented to users as consistent
materiality across the five `rate_per_1000_words` findings.

## Q2: Should each rate-per-1000 metric have its own epsilon?

**Yes, following directly from Q1.** A defensible empirical approach: set
each metric's epsilon at a fixed percentile of its own current-corpus
distribution (e.g., p85 or p90), documented the same way
`dictionary_match_rate_anomalous_threshold` already is in this codebase
(`services/financial_language_config.py:77-96` — the audit's own example
of what a calibrated threshold looks like in writing). This is a policy
choice, not purely a statistical one — a percentile-based epsilon will
always select roughly the same *fraction* of pairs regardless of a
metric's absolute scale, trading "is this shift big in real terms" for
"is this shift big relative to what this corpus has shown for this
metric." Both are legitimate interpretations of "materiality" for a
disclosure-intelligence product; the current code silently mixes them
across metrics without stating which one it means for any of the five.

## Q3: Should the metric control for denominator shrinkage?

**Yes — this is the central finding of this analysis.** The audit
(Section 13) already flagged that ACT 2017→2018's rate change is driven
substantially by a ~35% denominator drop (45,963 → 30,068 words), not hit
count (90 → 89, essentially flat). This analysis quantifies that
precisely by recomputing each pair's later-side rate using the
**earlier-side word count as a fixed denominator** (i.e., "how would the
later report's hit count read, if the later report were the same length
as the earlier one?"):

| Pair | Actual change | Length-fixed change | later/earlier words |
|---|---|---|---|
| ACT 2017-06-30→2018-06-30 | **+1.0019** | **+0.1013** | 0.696 |
| SBP 2023-12-31→2024-12-31 | -1.1027 | -0.9470 | 1.052 |
| ACT 2016-06-30→2017-06-30 | -0.9256 | -1.0467 | 0.938 |
| BEL 2017-12-31→2018-12-31 | +0.5544 | +0.8293 | 1.120 |
| BEL 2020-12-31→2021-12-31 | +0.2783 | +2.7572 | 1.868 |
| BEL 2019-12-31→2020-12-31 | +0.1494 | -1.0273 | 0.543 |

ACT 2017→2018 — the pair this project's own audit used as its primary
worked example of a Discover-eligible finding, and one of only two pairs
that currently clear the materiality bar at all — nearly vanishes
(`+1.0019 → +0.1013`) once report-length is held constant. Its entire
Discover-eligible status is a near-pure artifact of the later report being
about a third shorter, not of the company discussing financial condition
more. Conversely, BEL 2020→2021 and BEL 2019→2020 — both currently
**sub-materiality and absent from Discover** — would be top-tier findings
(`+2.76`, `-1.03`) under a length-controlled view, because their word
counts moved by ±87%/±45% between sides.

Comparing top-6-by-magnitude rankings under the two normalizations: only
**3 of 6** pairs overlap (`SBP 2023→2024`, `ACT 2016→2017`,
`BEL 2017→2018`). ACT 2017→2018 and SUR 2024→2025 drop out of the top 6
entirely under length control; three different BEL pairs enter it. This
is not a minor sensitivity — it is a different ranking, built from the
same underlying dictionary-hit data, depending purely on how the
denominator is defined. **The current, unadjusted rate is not distinguishing
"more financial-condition language" from "a shorter/longer report with
the same underlying discussion."** Before this metric is used to support
external claims ("Company X talked about financial condition much more
this year"), it needs either (a) a denominator-shrinkage-controlled
variant published alongside the raw rate, or (b) the raw rate's
description changed from "financial-condition language intensity change"
to the more accurate but weaker "financial-condition language density
change, which conflates topic volume with report-length change."

## Q4: Should subcategory changes be exposed separately?

**Yes, as a diagnostic — not as a replacement for the aggregate.** The
audit (Section 14) already notes the published metric nets across all 12
subcategories (revenue, debt, cash flow, impairment, dividends, etc.), so
a `+1.0` change could be one subcategory moving alone or several offsetting
partially. The raw data to do this already exists per-pair in
`PassageLanguageCategoryHit` (one row per passage-signal × subcategory), so
this is an aggregation/exposure change, not a new data-collection effort.
Recommendation: publish a subcategory breakdown as supporting detail on
comparison/evidence pages (not a new Discover ranking type), so a user
who sees "+1.10 financial-condition shift" can see *which* of the 12
subcategories drove it rather than trusting an unexplained aggregate.

## Q5: Should Discover show the largest observed shift even when sub-threshold?

**Yes, framed explicitly as sub-threshold.** The audit (Section 16)
already documents that the current UI collapses three distinct situations
("no comparisons," "quality-excluded," "below materiality") into one
generic empty state, and that BEL is *always* the third case for this
metric, never the first two (Section 11). A user cannot currently tell
"BEL has genuinely stable financial-condition language" from "the
threshold happens to exclude BEL." Given that materiality thresholds are,
per Q1/Q2, more heuristic-scale-normalization than corpus-calibrated
today, hiding the largest sub-threshold value entirely overstates the
threshold's authority. Showing it, visually distinguished (e.g., grayed
out, labeled "below materiality bar"), lets a user judge for themselves
whether a 0.55 shift matters for their purposes, without this project
having to claim `1.0` is a validated cutoff it currently is not.

## Q6: How stable are rankings under alternative normalizations?

**Not very, at the top of the ranking — see Q3's overlap analysis
(3 of 6 in common).** Two additional observations sharpen this:

- Rank order among the currently-eligible pairs is itself fragile: ACT
  2017→2018 (`+1.0019`) and SBP 2023→2024 (`-1.1027`) are separated by
  0.10 in the current metric, well inside the range that a handful of
  boilerplate-phrase repetitions can produce (audit Section 13: **4**
  additional hits would flip ACT 2016→2017 from sub- to supra-threshold).
  A single subcategory's phrasing choices in one report side can reorder
  the "top" Discover finding.
- The length-controlled variant is one specific alternative normalization
  (hold earlier-side words fixed). A share-of-narrative-length variant
  (e.g., normalize by total report length instead of primary-narrative
  words) or a subcategory-weighted variant would likely produce yet a
  third ranking — this analysis did not compute those, but given how much
  a single normalization choice already reorders the top 6, additional
  normalization variants should be expected to move rankings further, not
  converge on the same order.

**Conclusion for Q6**: rankings under this metric should be treated as
sensitive to normalization choice, not as a stable, singularly "correct"
ordering. This matters most for any downstream use (e.g., a future
milestone-8 relationship to market outcomes) that would treat "ranked
1st vs. 2nd by financial-condition shift" as a meaningful distinction
rather than noise.

---

## Recommendation (descriptive, not a decision)

This analysis does not choose specific epsilon values or normalization
formulas — that is a design decision for the team, consistent with how
the original audit avoided prescribing a corrected threshold. It does
establish, with corpus evidence, that:

1. The shared `epsilon=1.0` is not empirically defensible as-is (Q1/Q2).
2. The metric's sensitivity to denominator shrinkage is large enough to
   invalidate the current flagship eligible example (Q3) — this is the
   most consequential finding and should be resolved before the metric is
   used in any user-facing claim about "how much" financial-condition
   language changed.
3. Subcategory decomposition (Q4) and honest sub-threshold display (Q5)
   are low-risk, additive UI/publishing changes that improve
   interpretability without requiring a threshold decision first.
4. Ranking stability (Q6) is low enough that any "largest shift" framing
   should be treated as provisional, not authoritative, until Q3 is
   addressed.

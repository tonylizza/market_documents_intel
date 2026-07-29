# Report-side vs. alignment-dependent language-signal quality: a proposed separation

Status: **proposal only** -- not implemented. Per the Milestone 6 calibration brief, no
calibration or schema change is made until this is reviewed, except where a change was
required solely to import both dictionaries with correct lineage (none was: the existing
dictionary-bundle design already handled that -- see the final report's Phase 4 section).

## Finding that motivates this proposal

After importing the Loughran-McDonald dictionary, dictionary coverage is no longer the
limiting factor (see `language_dictionary_coverage_audit.csv`: per-side match rate now
ranges 0.043-0.069, median ~0.056, only KP2's five pairs sit marginally under the 0.05
threshold). But **every one of the 25 pairs remains `NEEDS_REVIEW`/`primary_eligible=False`**,
now driven almost entirely by one gate: `low_confidence_share` (share of rows at LOW/
NEEDS_REVIEW alignment confidence) exceeding the 0.25 threshold -- observed values range
0.31 to 0.83 across all 25 pairs (see `pairs language-status` output and
`alignment_confidence_word_distribution.csv`).

`alignment_confidence_word_distribution.csv` shows NEEDS_REVIEW confidence alone accounts
for **1,519,971 of 2,261,259 analyzed words (67%)** -- more than HIGH+MEDIUM+LOW combined.
Of the 20,560 NEEDS_REVIEW rows, 17,156 (83%) are flagged purely by
`detect_candidate_collisions` (duplicate/boilerplate text competing for the same match,
or exact-duplicate passages) -- a signal that deliberately forces NEEDS_REVIEW
*regardless of match quality* (see `passage_alignment.py`'s `assess_confidence`). Spot-checks
in `deterministic_alignment_confidence_review.csv` confirm this: several collision-flagged
rows have `semantic_similarity=1.0`, `lexical_cosine_similarity=1.0` -- a perfect textual
match, downgraded solely because the source text is duplicated elsewhere in the report
(e.g. repeated risk-disclosure boilerplate). Only ~3,130 of 20,560 NEEDS_REVIEW rows (15%)
are truly `AMBIGUOUS` (no accepted correspondence at all).

`language_confidence_sensitivity.csv` confirms the practical consequence: restricting to
HIGH/MEDIUM/LOW (i.e. excluding NEEDS_REVIEW) keeps only ~30% of analyzed words and swings
`net_tone_change` by a median of ~2.0 (max ~7.6) -- a large, corpus-population-driven
shift, not evidence that the excluded content was analytically worthless. Excluding only
truly `AMBIGUOUS` rows, by contrast, retains 96% of words and shifts `net_tone_change` by
a median of just ~0.29.

**Conclusion: the current single `primary_eligible` gate conflates two different kinds of
trustworthiness that the corpus's actual failure mode has already separated for us.**

## The two analytical layers (already implicit in the milestone brief)

**A. Report-side aggregate signals** -- category counts/rates per 1,000 words, net tone,
uncertainty/risk/governance/financial-condition intensity, forward-looking-caution rate.
These are computed by summing dictionary hits and words across the primary-narrative
population; they do **not** require a unique one-to-one correspondence between an earlier
and later passage. A passage's own text and its dictionary hits are valid regardless of
which specific duplicate-boilerplate candidate the alignment step happened to pair it
with. Quality here should depend on:
- correct current passage lineage (Milestone 5 segmentation/embedding currency)
- primary-narrative coverage (already tracked: `primary_narrative_word_coverage_earlier/later`)
- dictionary availability (now satisfied for all 25 pairs)
- structured-content exclusions (already applied via `structured_content_category`)
- report-side word coverage (`analyzed_word_coverage`)

**B. Alignment-dependent change signals** -- NEW/REMOVED attribution, SUBSTANTIALLY_MODIFIED
before/after deltas, and any claim like "risk language X was newly introduced in the later
report." These genuinely require the specific correspondence to be trustworthy: a NEW/REMOVED
call is only meaningful if we believe *that specific* passage really is new or removed, not
one half of an arbitrarily-broken tie between duplicate candidates. Quality here should
depend on:
- alignment confidence (HIGH/MEDIUM most trustworthy; LOW/NEEDS_REVIEW downgraded)
- ambiguity (`AlignmentStatus.AMBIGUOUS` -- no accepted correspondence at all)
- collision flag (duplicate/boilerplate content -- correspondence is provably non-unique)
- split/merge status (not observed in this corpus -- `alignment_type` is only ever
  `ONE_TO_ONE`/`UNMATCHED_EARLIER`/`UNMATCHED_LATER` across all 25 pairs; `ONE_TO_TWO`/
  `TWO_TO_ONE` never occur, so this dimension is currently moot but should stay in the
  model for when it does occur)
- unmatched coverage

## Recommended schema/model change (proposal, not implemented)

Split the single `language_signal_quality` / `primary_eligible` pair on
`ReportPairLanguageFeatures` into two independent quality assessments:

- `report_side_signal_quality: LanguageSignalQuality` + `report_side_primary_eligible: bool`
  -- gated by dictionary availability/match-rate, primary-narrative coverage, and upstream
  feature/extraction quality. **Not** gated by `low_confidence_share`.
- `alignment_change_signal_quality: LanguageSignalQuality` + `alignment_change_primary_eligible: bool`
  -- gated by everything the report-side gate uses, *plus* `low_confidence_share`,
  `ambiguous_word_share`, and (once observed in a corpus) a split/merge share.

`assess_language_quality` in `financial_language_quality.py` would compute both
assessments from the same `LanguageQualityInputs`, rather than folding every trigger into
one verdict. `warning_reasons`/`exclusion_reasons` would need a similar split, or a prefix
per reason (`"[report-side]"` / `"[alignment]"`) so a human reader can tell which layer a
given warning applies to.

Existing consumers (CLI `pairs language-status`, `language-audit`, ranking/export logic)
would need to pick which eligibility flag matters for their use case -- e.g. a
cross-sectional net-tone-change ranking across companies should use
`report_side_primary_eligible`; a "what specifically changed" drill-down should require
`alignment_change_primary_eligible`.

## Why this is the smaller, more defensible change

- It does not touch alignment computation, `AlignmentRun`, or `PassageAlignment` at all --
  the audit found no evidence of *material alignment errors* (collision-flagged rows are
  frequently near-perfect matches; genuine `AMBIGUOUS` non-correspondence is a small,
  low-impact 15% minority of NEEDS_REVIEW, and excluding it barely moves the result).
- It does not lower any threshold to manufacture eligibility -- report-side signals earn
  their own eligibility on their own (already-adequate) merits; alignment-dependent
  signals keep today's stricter bar unchanged.
- It preserves full lineage: nothing is silently merged or discarded, only labeled with
  which claims it is fit to support.

## What this proposal does NOT resolve

- KP2's five pairs remain borderline on dictionary match rate (0.043-0.050) even under
  `report_side_primary_eligible` -- worth a dictionary-specific or company-specific look
  before treating KP2's report-side numbers as equally trustworthy to the other five
  companies.
- Upstream `FeatureQuality.NEEDS_REVIEW` (Milestone 3/5) is set for all 25 pairs
  independently of anything Milestone 6 controls, which caps quality at `USABLE` rather
  than `GOOD` even under the split model above. That is expected/appropriate, not a
  Milestone 6 defect, but it means "report-side eligible" pairs would still carry a
  `USABLE`, not `GOOD`, label.

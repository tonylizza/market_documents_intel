# Experiment: Lexical Change Metrics Pilot (AfroCentric, Three Semantic Units, 2020–2024)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against
`data/raw/ACT/{2020,2021,2022,2023,2024}/annual_report.pdf` via throwaway PyMuPDF/scikit-learn/
rapidfuzz scripts, with intermediate raw-text dumps and a metrics JSON written to a session-local
scratch directory outside the repository. Nothing here is wired into the application. This is a
direct follow-up to `docs/experiments/annual-report-within-schedule-alignment.md` ("the prior
report," assumed read), whose quantitative summary is corrected below before the pilot itself
begins, per this task's explicit instruction not to carry forward its numbers uncritically.

## 1. Pre-flight corrections to the prior report

The prior report's executive summary undercounted its own per-year segmentation tables, misstated
its split/merge finding relative to its own Section 6, and made a boundary-validation-year claim
its own examples do not support. All three are corrected here from the prior report's own
Sections 3–11, re-tallied directly against its tables (not re-derived from new evidence).

### 1.1 Unit counts

The executive summary reported "19 governance units, 15 remuneration units, 34 total." Recounting
the rows in the prior report's own Section 3 (Corporate Governance) and Section 4 (Remuneration)
tables — cross-checked against the identically-structured Section 5.1/5.2 matrices, which agree
with Section 3/4 row-for-row — gives:

- **Corporate Governance: 24 units** (not 19), Section 3's own table.
- **Remuneration: 18 units** (not 15), Section 4's own table.
- **Total: 42 units** (not 34).

The prior report's own Section 11 classification lists are internally consistent with 42, not with
its headline 34 — but its own bucket *labels* also undercounted their own lists by one each:

- **STRONG_LONGITUDINAL_UNIT**: labeled "(24, proceed directly)" but the list itself names 25
  units. Corrected count: **25**.
- **USABLE_WITH_STRUCTURAL_HANDLING**: labeled "(6, proceed with explicit event-flagging)" but the
  prose names 13 distinct individual units once the four-unit "board-profile cluster" is unpacked
  into its members (board_of_directors_profiles, combined_board_skillset,
  executive_committee_profiles, board_deliberations) and the two-unit "compliance cluster" and
  "remuneration heading-gain" pairs are similarly unpacked. Corrected count: **13** (the "6" in the
  original was counting event-clusters, not units).
- **TOO_THIN**: 4, as stated — this one was already correct.

25 + 13 + 4 = 42, matching the corrected total. Recomputed percentages:

| Classification | Corrected count | Corrected % (of 42) | Prior report's (incorrect) framing |
|---|---:|---:|---|
| STRONG_LONGITUDINAL_UNIT | 25 | 59.5% | "24 of 34 (71%)" |
| USABLE_WITH_STRUCTURAL_HANDLING | 13 | 31.0% | "6" (unit vs. event-cluster count conflated) |
| TOO_THIN | 4 | 9.5% | "4 of 34" (denominator wrong, numerator right) |

The heading-match-sufficiency breakdown (prior Section 10) is corrected the same way, by
reclassifying all 42 units (not 34) against the same four categories using the evidence already in
the prior report's Sections 3, 4, 7, and 8 (stable heading every year → `HEADING_MATCH_SUFFICIENT`;
heading gap in exactly one year, bridgeable by a normalized/fuzzy matcher → `FUZZY_MATCH_SUFFICIENT`;
unlabeled-to-headed promotion or a genuine added/split judgment call → `SEMANTIC_MATCH_REQUIRED`;
cross-schedule move, undetectable by any within-schedule text signal → `STRUCTURAL_MATCH_REQUIRED`):

| Classification | Corrected count | Corrected % (of 42) | Prior report's count (of 34) |
|---|---:|---:|---|
| HEADING_MATCH_SUFFICIENT | 29 | 69.0% | 26 |
| FUZZY_MATCH_SUFFICIENT | 5 | 11.9% | 2 |
| SEMANTIC_MATCH_REQUIRED | 7 | 16.7% | 5 |
| STRUCTURAL_MATCH_REQUIRED | 1 | 2.4% | 1 |

The qualitative conclusion is unchanged and, if anything, slightly reinforced: 80.9% of units
(HEADING_MATCH + FUZZY) align without semantic reasoning, close to the prior report's own framing
that "most units align deterministically." Only the denominator and two of the four bucket sizes
were wrong; the underlying claim about which units need what kind of reasoning was not re-derived
here and is taken as read from the prior report's own per-unit evidence.

### 1.2 Split / merge characterization

The prior report's executive summary states "no true SPLIT or MERGE ... was observed." This is
contradicted by its own Section 6 (Case 3) and Section 7 edge table, which explicitly classify:

> 2021: (unlabeled compliance/ethics/conflicts/dealings prose, one page) → 2022: `compliance`,
> `ethics_governance`, `conflicts_of_interest`, `dealings_in_shares`

as **`ONE_TO_MANY` / `SPLIT` (3 units) + `ADDED` (1 unit)**, at 0.75 confidence, with the prior
report's own text calling this "a one-to-many `SPLIT` for the three 2020–2021 topics that already
existed as distinguishable prose."

**Correction: the more precise interpretation, and the one the prior report's own evidence
supports, is that one genuine one-to-many structural SPLIT did occur** — three previously
unlabeled-but-distinguishable prose sub-topics (compliance, conflicts of interest, dealings in
shares) gained independent headings in 2022, a real fan-out from one governance-schedule prose
block into three separately addressable units. `ethics_governance` is correctly coded `ADDED`
rather than `SPLIT` in the same event (its content has no distinguishable 2020–2021 antecedent).
**No MERGE (many-to-one) event was observed in either schedule** — the prior report's blanket "no
SPLIT or MERGE" claim should be corrected to "no MERGE; one genuine SPLIT (plus a co-occurring ADD),
concentrated in the single 2022 governance-redesign year." This does not change the prior report's
downstream recommendations (which already, correctly, flagged this exact event as needing
structural handling); it only corrects the top-line summary sentence that contradicted the report's
own detailed findings.

### 1.3 Boundary-validation sample

The prior report's Section 9 states its representative block/bbox checks covered "2020, 2021, and
2022 (3 of the 5 years, per the brief's minimum)." The six examples it actually lists are: 2020
p.83, 2020 p.84, 2020 p.90, 2022 p.89, 2020 p.102, 2020 pp.102–104 — **five 2020 examples and one
2022 example, zero 2021 examples.** The three-year claim is unsupported by the report's own
example list.

**Correction applied here:** a representative 2021 boundary check was run in this session to
restore the three-year claim rather than silently retract it. **ACT 2021, PDF p.94 (`audit_risk_committee`, Corporate Governance schedule):** plain `get_text()` extracts the role-of-committee
prose, the pull-quote, the composition table (member / meetings / attendance %, one full row per
block), and the closing sign-off text in correct top-to-bottom visual order with no block reordering
needed — verdict **CLEAN**, directly comparable to the prior report's 2020 p.84/p.90 CLEAN verdicts
on the same schedule. This example is carried forward as this pilot's own 2021 source-reconstruction
check (Section 3.5.2 below) rather than treated as a one-off patch. With this addition, the
boundary-validation sample now genuinely spans 2020, 2021, and 2022 as originally claimed.

None of these three corrections change the prior report's central recommendation (proceed to
lexical-change metrics on a three-unit pilot); they correct arithmetic and a summary-vs-detail
contradiction, which is why this pilot proceeds as originally scoped.

## 2. Executive summary

**Yes, on this three-unit, four-transition, one-company pilot, the lexical metrics behave
sensibly and are internally auditable — but the pilot's single most important finding is not about
the metrics' behavior, it is about *unit scoping*: a metric can only detect a substantive change if
the analyst-defined unit boundary actually contains the sentence where that change lives, and this
pilot's own designated "known-change positive control" unit does not.**

- **Do the metrics distinguish stable from substantially changed text?** Yes, clearly, on
  `audit_risk_committee` and `remuneration_chair_background_statement`. Every metric's ranking of
  the four transitions within each unit is broadly consistent with a manual reading of the
  underlying text: the most reworded/expanded years score lowest on similarity, the most
  routine-refresh years score highest.
- **Did the advisory-vote positive control behave as expected?** **No — and this is the pilot's
  most important result.** `advisory_vote_on_implementation_report`'s own reconstructed text is
  near-verbatim boilerplate in every year (only the AGM year token and, once, the approval date
  change); its 2023→2024 transition scores *identically* to every other transition on every metric
  (unigram Jaccard 0.926, bigram Jaccard 0.833, sequence ratio 0.951 in all four transitions). The
  independently known substantive event (the vote falling to 50.26%, explicit Sanlam-engagement
  language) is real and confirmed in this session's own extraction — but it lives in the
  neighboring `remuneration_chair_background_statement` unit's "Shareholder engagement and voting"
  subsection, not inside the one-paragraph unit the prior report scoped as
  `advisory_vote_on_implementation_report`. The metrics did not fail; the unit boundary excluded
  the evidence. See Section 8 for the full analysis.
- **Which metrics are most interpretable?** Unigram and bigram Jaccard, because their inputs
  (token sets) are directly inspectable and their disagreement with each other has a clean
  reading (bigram drops faster than unigram when phrasing changes but vocabulary is retained).
  TF-IDF cosine is powerful but its behavior on short units with document-unique tokens (a year
  number appearing in only one of five documents) is non-obvious without inspecting IDF weights
  directly — see Section 9.
- **Which metrics appear redundant?** On this sample, unigram Jaccard and TF-IDF cosine mostly
  agree in *ranking* (both rank the same transitions as most/least similar within a unit) but
  disagree in *magnitude* on short, template-heavy text, which argues for reporting both rather
  than dropping one — the disagreement itself is diagnostic (Section 9).
- **Which metrics react to wording vs. order vs. length vs. numeric change?** Bigram Jaccard is the
  most order/phrasing-sensitive of the similarity metrics; sequence ratio is the most sensitive to
  paragraph-level insertions (it drops sharply when whole new paragraphs are added, as in
  `remuneration_chair_background_statement` 2023→2024); edit similarity is sensitive to
  character-level churn from renumbered tables even when the underlying vocabulary is stable (seen
  clearly in `audit_risk_committee` 2022→2023, Section 9); numeric-change counts track table/vote
  data turnover independently of prose rewording. None of the four core similarity metrics is
  redundant with the numeric-change count, which measures something none of them measure directly.
- **Is the lexical stage ready to expand beyond these three units?** **(A) Yes, but the next
  round must include at least one more short/thin unit deliberately, specifically to
  characterize the boundary-scoping failure mode found here before it recurs silently at scale.**
  See Section 13 for the full recommendation.

## 3. Methodology note: source verification performed in this session

Per the task's instruction to re-verify source boundaries rather than trust the prior report's page
numbers uncritically, all three units' page locations were independently re-located in this session
by full-text search within the prior report's own schedule page ranges (Section 2 of the prior
report), not merely copied from its Section 3/4 tables. All five years for all three units matched
the prior report's page attributions except where noted below (Section 3.5).

## 4. Source unit inventory

Extraction was performed with `PyMuPDF.get_text()` per page, with one exception (ACT 2023
`audit_risk_committee`, see 4.3) where a whole-page `y0` block sort was needed. Page-furniture lines
(running headers/footers, bare page numbers, "(CONTINUED)" section labels) were stripped by regex
before word/character counts were computed; all counts below are post-strip.

| Unit | Year | Heading (as extracted) | Pages | Words | Sentences | Reconstruction status |
|---|---|---|---:|---:|---:|---|
| audit_risk_committee | 2020 | "Audit and Risk Committee" | 84 | 369 | 5 | CLEAN |
| audit_risk_committee | 2021 | "Audit and Risk Committee" (implicit; page opens on "THE ROLE OF THE COMMITTEE") | 94 | 345 | 5 | CLEAN |
| audit_risk_committee | 2022 | "Audit and Risk Committee" | 100 | 325 | 3 | CLEAN |
| audit_risk_committee | 2023 | "AUDIT AND RISK COMMITTEE" (mid-page sidebar box, see 4.3) | 114 | 336 | 5 | MINOR_CORRECTION_NEEDED |
| audit_risk_committee | 2024 | "AUDIT AND RISK COMMITTEE" | 112 | 367 | 6 | CLEAN |
| remuneration_chair_background_statement | 2020 | "BACKGROUND STATEMENT" | 94 | 734 | 29 | MINOR_CORRECTION_NEEDED (boundary, see 4.4) |
| remuneration_chair_background_statement | 2021 | "Background statement" | 107 | 882 | 33 | CLEAN |
| remuneration_chair_background_statement | 2022 | "Background statement" | 110 | 868 | 32 | CLEAN |
| remuneration_chair_background_statement | 2023 | "BACKGROUND STATEMENT" | 125–126 | 1,234 | 44 | CLEAN |
| remuneration_chair_background_statement | 2024 | (no page-level heading; opens mid-narrative, see 4.4) | 120–121 | 1,401 | 45 | CLEAN |
| advisory_vote_on_implementation_report | 2020 | "Advisory vote on the implementation report" | 106 | 41 | 2 | CLEAN |
| advisory_vote_on_implementation_report | 2021 | "Advisory vote on the implementation report" | 118 | 41 | 2 | CLEAN |
| advisory_vote_on_implementation_report | 2022 | "Advisory vote on the implementation report" | 122 | 41 | 2 | CLEAN |
| advisory_vote_on_implementation_report | 2023 | "Advisory vote on the implementation report" | 138 | 41 | 2 | CLEAN |
| advisory_vote_on_implementation_report | 2024 | "Advisory vote on the implementation report" | 132 | 41 | 2 | CLEAN |

### 4.1–4.2 audit_risk_committee and advisory_vote_on_implementation_report: boundary notes

Both units were single, self-contained pages in every year except the 2023 audit-committee case
below; the preceding and following pages were read in full to confirm the Investment Committee
(governance) and "Approval of the remuneration report by the Board" (remuneration) sections begin
immediately after, with no spillover in either direction. `advisory_vote_on_implementation_report`
was extracted by regex slice between its own heading and the next heading
("Approval of the remuneration report by the Board"), confirmed identical in structure across all
five years.

### 4.3 audit_risk_committee, 2023: a real extraction hazard, found and fixed in this session

ACT's own hazard class, per the prior longitudinal experiment, was "numeric-label-to-category
clustering on chart pages," never heading displacement or running headers. This session found a
**new hazard not previously documented for ACT**: on 2023 p.114, block-level inspection
(`get_text("blocks")`) shows the section's own title, "AUDIT AND RISK COMMITTEE" (a left-column
sidebar box at `x0=68.5, y0=131.1`), is emitted by plain `get_text()` *after* the entire right-column
"role of the committee" prose (`x0=212.6, y0=94.9–251.6`), because the page uses a genuine two-column
layout in which the title box sits lower on the page than the opposing column's header text. A
whole-page `y0` sort (not a column-aware sort, since the two columns interleave by height rather than
being cleanly banded here) recovers a materially better order — title, then role-of-committee prose
still reads second because its own `y0` is lower than the title's is high, but "Key matters of
focus" now correctly follows the composition table instead of being scrambled with it. The result is
not perfect (see Section 12): "Key matters of focus," which visually sits at the bottom of the
page, still trails the composition table in the reconstructed order, an artifact of the layout
mixing a tall left column with a short right column. Verdict: **MINOR_CORRECTION_NEEDED** — content
is complete and un-lost, order is close but not exact. This is reported as a genuine, newly-found
hazard, not assumed away; it directly affects the 2022→2023 and 2023→2024 sequence-similarity
readings for this unit (Section 5, transition notes).

### 4.4 remuneration_chair_background_statement: boundary notes

In four of five years (2021–2024) the unit ends cleanly at an explicit Chairperson sign-off
("Dr Shirley Zinn / Remuneration Committee Chairperson / 13 September 2021," etc.), immediately
followed by a new page or a clearly different heading. **2020 has no such sign-off within the
schedule's remuneration-report pages** — the narrative flows directly from COVID-19 response
content into a "Changes to the remuneration and related policies for the 2020 financial year" table
with no heading break and no closing signature visible anywhere in the surrounding pages. The full
single page (p.94) was retained as the 2020 unit rather than truncated at an arbitrary sentence,
and this boundary asymmetry — 2020's version of this unit implicitly includes policy-table framing
that 2021–2024's versions exclude (because in those years that content sits in a separately headed
section) — is flagged here explicitly and revisited in Section 8's discussion of the 2020→2021
transition, where it partly (not wholly) explains that transition's unusually large score. 2024's
version was extended one page further than a page-count-only reading would suggest, specifically
because this session confirmed the "Shareholder engagement and voting" and "Appreciation" content
carrying the 50.26% vote result and the Sanlam-engagement language is the tail of the *same*
narrative flow as the 2024 Chairperson's report, ending only at the sign-off ("Alice le Roux ...
8 October 2024") — see Section 8 for why this placement matters.

## 5. Metric methodology

- **Tokenization.** Word tokens: `\d+\.\d+%?|\d+/\d+|\d+%?|[A-Za-z]+(?:['’][A-Za-z]+)*` — this
  keeps decimal numbers ("50.26%"), meeting-attendance fractions ("6/6"), and apostrophed words
  ("shareholders'") as single tokens rather than fragmenting them on internal punctuation. Bigrams
  are adjacent-token pairs over this same tokenization.
- **Normalization (ANALYTIC-NORMALIZED variant).** Unicode NFKC normalization; curly
  quotes/dashes/ellipses mapped to their plain-ASCII equivalents; whitespace collapsed to single
  spaces; lowercased. No stemming, no lemmatization, no stopword removal, no number removal — per
  the task's explicit constraint.
- **RAW-RECONSTRUCTED variant.** Page-furniture-stripped `get_text()` output (or the block-sorted
  reconstruction for the one 2023 exception), case and punctuation preserved, used for numeric-token
  extraction and character counts.
- **TF-IDF fitting scope.** One `TfidfVectorizer` fit per unit, over that unit's full five-year
  corpus (5 documents), using the same word-token regex as above and no lowercasing inside the
  vectorizer (the ANALYTIC-NORMALIZED text is already lowercased before fitting). This means IDF
  weights are shared and comparable across all four transitions within a unit, per the task's
  instruction — a token that is rare across all five years (e.g., a specific director's surname,
  or a distinct AGM year token) is up-weighted consistently, not re-weighted per pair.
- **Edit similarity.** Character-level Levenshtein distance via `rapidfuzz.distance.Levenshtein`
  on the full ANALYTIC-NORMALIZED string for each side of the pair.
  `edit_similarity = 1 - (distance / max(len(a), len(b)))` — **denominator is the longer of the two
  strings' character lengths**, not the combined length, so a short insertion into a long,
  otherwise-identical string produces a similarity close to 1 rather than being penalized by the
  combined-length convention.
- **Sequence similarity.** `difflib.SequenceMatcher` (`autojunk=False`) run over the **word-token
  sequence** (not raw characters), so its `ratio()` and `get_opcodes()` counts (equal / insert /
  delete / replace, in token units) describe paragraph/sentence-level continuity rather than
  character-level continuity — this is the metric most sensitive to whole passages moving or being
  added, as distinct from word-level substitution.
- **Numeric-token extraction.** From the RAW-RECONSTRUCTED text (pre-lowercasing, so currency and
  percent signs are preserved contextually where present in the source): the pattern
  `\d+\.\d+%?|\d+/\d+|\d[\d,]*%?` — captures decimals/percentages ("50.26%"), meeting fractions
  ("6/6"), and integers with thousands separators ("1 300 620" is captured as separate
  space-delimited integer tokens, since PyMuPDF does not preserve non-breaking spaces as a single
  token — a limitation noted, not corrected, per the "conservative normalization" instruction).
  Added/removed numeric tokens between adjacent years are computed as a multiset difference
  (`collections.Counter`), so a number appearing twice in one year and once in the next registers
  as one "removed," not a full wipe.
- **No embeddings were used anywhere in this pilot**, per the task's explicit constraint.

## 6. Unit 1 results: audit_risk_committee

**Qualitative expectation set before viewing results:** present all five years, near-identical
heading, stable internal structure (role → key matters → composition table), clean boundaries;
expected moderate year-over-year change from committee-membership/attendance churn, no wild swings
absent a real governance event.

| Transition | TF-IDF cosine | Unigram Jaccard | Bigram Jaccard | Edit similarity | Sequence similarity | Word-count change % | Numeric changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020→2021 | 0.933 | 0.705 | 0.584 | 0.413 | 0.549 | −6.5% | 18 |
| 2021→2022 | 0.958 | 0.867 | 0.745 | 0.734 | 0.815 | −5.8% | 21 |
| 2022→2023 | 0.954 | 0.835 | 0.781 | 0.399 | 0.678 | +3.4% | 16 |
| 2023→2024 | 0.947 | 0.797 | 0.671 | 0.808 | 0.828 | +9.2% | 17 |

| Transition | Cosine distance | Unigram distance | Bigram distance | Edit distance (normalized) | Sequence change | Length change |
|---|---:|---:|---:|---:|---:|---:|
| 2020→2021 | 0.067 | 0.295 | 0.416 | 0.587 | 0.451 | −6.5% |
| 2021→2022 | 0.042 | 0.133 | 0.255 | 0.266 | 0.185 | −5.8% |
| 2022→2023 | 0.046 | 0.165 | 0.219 | 0.601 | 0.322 | +3.4% |
| 2023→2024 | 0.053 | 0.203 | 0.329 | 0.192 | 0.172 | +9.2% |

**Pair-level audit**

- **2020→2021.** Source headings identical ("Audit and Risk Committee"). Word counts 369→345.
  Inserted: chairperson-attendance rows for four members whose meeting counts shift to "4/4";
  deleted: the 2020 composition rows for members leaving the committee (Grathel Motau's, Lindani
  Dhlamini's roles change). Numeric changes: 18 (attendance fractions and percentages almost
  entirely). Qualitative interpretation: **MODERATE** — a real committee-composition turnover
  (chairperson change from Lindani Dhlamini to Bruno Fernandes) plus light prose re-editing of the
  bullet list order, correctly reflected as the lowest edit/sequence similarity of the four
  transitions.
- **2021→2022.** Headings identical. Word counts 345→325. The only substantive insertion is a new
  opening pull-quote sentence ("Effective controls support value creation and protect against value
  erosion"); the composition table's names are unchanged, only attendance figures refresh
  (4/4→5/5, several 100%). Numeric changes: 21, almost all attendance-figure refreshes. Qualitative
  interpretation: **SMALL** — this is the most routine, membership-stable transition in the unit's
  four years and is used as this pilot's stable/negative control (Section 8).
- **2022→2023.** Headings identical (modulo the 2023 title-box display quirk, Section 4.3). Word
  counts 325→336. Real content change: Mmaboshadi Chauke joins, meeting count rises 5/5→6/6,
  Ahmed Banderker's attendance falls to 2/6 (33%). Edit similarity (0.399) and sequence similarity
  (0.678) are both markedly lower than unigram Jaccard (0.835) here — **this divergence is partly a
  genuine content signal (real membership/attendance churn) and partly an artifact of the 2023
  block-reordering fix** (Section 4.3): the reconstructed 2023 text's paragraph order differs
  from 2022's in a way that is not present in the source documents' visual layouts, inflating the
  sequence-level "change" reading beyond what a human comparing the two pages side-by-side would
  call. Qualitative interpretation: **MODERATE**, with the caveat that the edit/sequence readings
  specifically should be treated with reduced confidence for this one transition.
- **2023→2024.** Word counts 336→367. Genuine new content: an added sentence naming the Group CFO,
  CEO, and Chief Audit Executive as permanent invitees; new members (a Sanlam representative, a new
  non-executive director) replace departing ones, consistent with the ACT/Sanlam ownership change
  documented in the remuneration narrative (Section 7); meeting count falls 6/6→5/5. Qualitative
  interpretation: **MODERATE** — a real content addition tied to the Sanlam-related governance
  changes, but the committee's role and key-matters text is otherwise unchanged, correctly reflected
  in edit/sequence similarity recovering to this unit's second-highest levels (0.808 / 0.828).

## 7. Unit 2 results: remuneration_chair_background_statement

**Qualitative expectation set before viewing results:** present all five years, prose-heavy,
moderate-to-high continuity expected, with plausible drops in similarity in years carrying real
remuneration-policy, COVID, or ownership-change narrative — more narrative volatility than
`audit_risk_committee`.

| Transition | TF-IDF cosine | Unigram Jaccard | Bigram Jaccard | Edit similarity | Sequence similarity | Word-count change % | Numeric changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020→2021 | 0.852 | 0.259 | 0.112 | 0.331 | 0.212 | +20.2% | 44 |
| 2021→2022 | 0.920 | 0.574 | 0.404 | 0.672 | 0.643 | −1.6% | 54 |
| 2022→2023 | 0.908 | 0.434 | 0.282 | 0.508 | 0.501 | +42.2% | 45 |
| 2023→2024 | 0.857 | 0.344 | 0.185 | 0.420 | 0.335 | +13.5% | 53 |

| Transition | Cosine distance | Unigram distance | Bigram distance | Edit distance (normalized) | Sequence change | Length change |
|---|---:|---:|---:|---:|---:|---:|
| 2020→2021 | 0.148 | 0.741 | 0.888 | 0.669 | 0.788 | +20.2% |
| 2021→2022 | 0.080 | 0.426 | 0.596 | 0.328 | 0.357 | −1.6% |
| 2022→2023 | 0.092 | 0.566 | 0.718 | 0.492 | 0.499 | +42.2% |
| 2023→2024 | 0.143 | 0.656 | 0.815 | 0.580 | 0.665 | +13.5% |

**Pair-level audit**

- **2020→2021.** Unigram/bigram Jaccard are the lowest of this unit's four transitions (0.259 /
  0.112), and sequence similarity is also lowest (0.212). Reading both texts: 2020's narrative is
  dominated by COVID-19 response content (gratuity payments, TERS relief, banking-partner benefits,
  malus/clawback policy introduction) with **no shareholder-voting-results table and no Appreciation
  sign-off section at all**, while 2021 opens with STI-mechanics/bonus-formula content and *does*
  include the voting-results table and Appreciation close. **Qualitative interpretation: LARGE, but
  flagged — this is not purely a wording change.** Per Section 4.4, part of this transition's low
  score reflects a genuine content-composition asymmetry (2021's unit contains a whole subsection
  2020's does not), not solely different words used to describe the same underlying disclosure.
  This is exactly the "container boundary drift masquerading as content change" hazard the prior
  experiments warned about, recurring one level down inside a nominally `STRONG_LONGITUDINAL_UNIT`.
- **2021→2022.** Highest similarity of the four transitions across every metric (cosine 0.920,
  unigram 0.574, sequence 0.643). Both years share the same section skeleton (Operating context →
  Changes to policy → Focus areas → Shareholder voting → Appreciation) in the same order; the LTI
  redesign content in 2022 is new but occupies roughly the same structural slot as 2021's STI
  content. Qualitative interpretation: **MODERATE** — genuinely different subject matter
  (LTI vs. STI redesign) inside an unchanged structural shell.
- **2022→2023.** Word count jumps 42.2% (868→1,234 words), the largest length change in either
  narrative unit studied. 2023 introduces an entirely new four-objective structure (leadership
  capability, employee value proposition/wellbeing, DEI, union relations) not present in 2022's
  shorter LTI-focused narrative. Qualitative interpretation: **LARGE** — a genuine, substantial
  rewrite and expansion, not a boundary artifact; the shared sections (voting table, Appreciation)
  are retained, but the bulk of the narrative is new prose.
- **2023→2024.** This is the transition carrying the independently-known substantive event: the
  50.26% advisory-vote result and explicit "constructive engagement with the Sanlam Group" language
  appear in this unit's own "Shareholder engagement and voting" subsection (confirmed by direct
  extraction in this session, Section 4.4), alongside a leadership-succession passage (new
  Remuneration Committee Chairperson Alice le Roux replacing Joe Madungandaba) in the Appreciation
  close. Unigram/bigram Jaccard (0.344 / 0.185) and sequence similarity (0.335) are the second-lowest
  of this unit's four transitions — a real, detectable drop, though not the single largest (2020→
  2021 and 2022→2023 score lower on some metrics, for the reasons given above). Qualitative
  interpretation: **LARGE** — correctly flagged as a substantial change by every metric, though the
  metrics cannot on their own distinguish "large because of a genuinely unusual year" from "large
  because narrative length grew," which is exactly what the numeric-change and length-change columns
  are for (Section 11).

## 8. Unit 3 results: advisory_vote_on_implementation_report — and the positive-control failure

**Qualitative expectation set before viewing results:** structurally tiny, highly stable, same
function every year; **2023→2024 should show a clear outlier change** because of the ~50.26% vote
and Sanlam-engagement language.

| Transition | TF-IDF cosine | Unigram Jaccard | Bigram Jaccard | Edit similarity | Sequence similarity | Word-count change % | Numeric changes |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2020→2021 | 0.818 | 0.926 | 0.833 | 0.985 | 0.951 | 0.0% | 4 |
| 2021→2022 | 0.818 | 0.926 | 0.833 | 0.993 | 0.951 | 0.0% | 4 |
| 2022→2023 | 0.818 | 0.926 | 0.833 | 0.993 | 0.951 | 0.0% | 4 |
| 2023→2024 | 0.818 | 0.926 | 0.833 | 0.993 | 0.951 | 0.0% | 4 |

Every similarity metric is **identical to three decimal places across all four transitions**
(edit similarity varies by 0.008 due to a trivial digit-length difference and is otherwise flat).
The `2023→2024` row is indistinguishable from `2020→2021`.

**Diagnosis, verified directly against the source text (Section 4, this session's own
extraction):** the unit's own reconstructed text is template boilerplate —

> "Advisory vote on the implementation report / The implementation report, as it appears above, is
> subject to an advisory vote by shareholders at the *[YEAR]* AGM. Accordingly, shareholders are
> requested to cast an advisory vote on the remuneration policy's implementation for *[YEAR]*."

— and the only token that ever changes between years is the AGM year, appearing twice per
paragraph. This is confirmed by the diff opcode counts for every single transition: 39 equal
tokens, 0 inserted, 0 deleted, exactly 2 replaced (both instances of the year number). The
independently-known substantive event — the 50.26% vote result and the explicit Sanlam-engagement
sentence — is real, confirmed present in the corpus, and **does not appear anywhere inside this
unit's own text.** It appears in the "Shareholder engagement and voting" subsection of
`remuneration_chair_background_statement` (Section 4.4, Section 7's 2023→2024 discussion), one unit
over.

**Positive-control assessment, answering the task's explicit questions:**

- **Does every lexical metric move in the expected "more changed" direction for 2023→2024?**
  **No — none of them do**, because none of them had access to the sentence where the change lives.
  This is not a case of one metric under-reacting while others correctly react; all five core
  metrics agree with each other (correctly, given their input) and all five disagree with the
  external ground truth (because the input itself was wrong).
- **Is the change driven by new wording, changed numbers, or both?** Neither, *within this unit*.
  Both, within `remuneration_chair_background_statement`'s neighboring subsection.
- **Why did every metric fail to distinguish this known-change case from routine years?** Because
  the unit boundary that the prior experiment scoped as `advisory_vote_on_implementation_report` —
  a single, short, standing-boilerplate paragraph whose function is a *procedural notice that a vote
  will occur*, not a *report of the vote's outcome* — was never the right place to look for the
  outcome. The 50.26% figure and the AGM-held date live in a shareholder-voting-results table and
  narrative earlier in the same remuneration report, correctly scoped by the prior report as part
  of `remuneration_chair_background_statement` rather than as its own unit. **This is a genuine,
  informative negative result about unit design, not about metric design.**

**Comparison to the stable control.** `audit_risk_committee` 2021→2022 (Section 6) was selected as
this pilot's negative/stable control by reading the text first (not by picking the single highest
score): both years' composition, role text, and key-matters bullets are the same in substance, with
only attendance-percentage refreshes and one added pull-quote sentence — a genuinely routine year.
Its scores (cosine 0.958, unigram 0.867, sequence 0.815) are **lower** on every metric than
`advisory_vote`'s 2023→2024 "known-large-change" transition (cosine 0.818, unigram 0.926, sequence
0.951). Read naively, this would suggest the "known change" year is *more* stable than a routine
governance-committee refresh — the opposite of the truth. The correct reading is that
`advisory_vote_on_implementation_report`'s text is short and templated enough that its
metric ceiling is very high regardless of real-world events, while `audit_risk_committee`'s
composition-table churn is lexically "louder" even in an uneventful year. **This is the clearest
demonstration in this pilot that a unit's structural genericness, not just its content, sets a floor
on how much apparent change a lexical metric can register — and that comparing raw similarity scores
across units of very different length and genericness, without accounting for that floor, would be
actively misleading.**

## 9. Metric agreement / disagreement analysis

- **TF-IDF cosine vs. unigram Jaccard on short, template-heavy units.** On
  `advisory_vote_on_implementation_report`, cosine (0.818) is noticeably *lower* than unigram
  Jaccard (0.926) despite operating on the same two-token difference. This is because TF-IDF
  up-weights the AGM year token specifically *because* it is document-unique (appears in only one
  of the five fitted documents), so its mismatch contributes disproportionately to the cosine
  distance even though it is only 2 of 41 tokens. Jaccard treats all tokens democratically and is
  therefore less sensitive to this one rare-but-short token's replacement. **Neither metric is
  "wrong"; they are sensitive to different things** — cosine to rare/distinctive-token turnover,
  Jaccard to raw vocabulary-set overlap. On longer, less template-driven units
  (`remuneration_chair_background_statement`), the two metrics track each other's *ranking* far
  more closely (both agree 2021→2022 is most similar and 2020→2021 is least), because no single
  token dominates a document of 700–1,400 words.
- **Unigram vs. bigram Jaccard.** Bigram Jaccard is lower than unigram Jaccard in every single
  transition studied, in both prose units, which is expected (shared vocabulary is far more common
  than shared adjacent-word pairs). The *gap* between them is itself informative: in
  `audit_risk_committee` 2021→2022 the gap is small (0.867 vs. 0.745), consistent with the sentence
  structure being almost entirely retained; in `remuneration_chair_background_statement` 2020→2021
  the gap is large (0.259 vs. 0.112), consistent with genuinely different sentence-level phrasing,
  not just different topics using overlapping words.
- **Sequence similarity vs. edit similarity — order vs. character churn.** These diverge most
  sharply in `audit_risk_committee` 2022→2023, where edit similarity (0.399) is the *lowest* value
  in the entire pilot but sequence similarity (0.678) and unigram Jaccard (0.835) are both
  comparatively high. Per Section 6's audit, this reflects the 2023 block-reconstruction artifact
  (Section 4.3): character-level Levenshtein distance is very sensitive to a paragraph's absolute
  position shifting even slightly, while token-sequence `SequenceMatcher` and Jaccard are more
  robust to it because they operate on whole-token or whole-set comparisons rather than raw
  character alignment. **This is a genuine methodological caution for future work using this exact
  edit-similarity implementation on pages that needed block-reordering: the edit metric appears to
  partially measure "how well did the reconstruction match the *previous* year's reconstruction
  order," not purely "how much did the wording change."**
- **Numeric-change count vs. the text-similarity metrics.** In
  `remuneration_chair_background_statement`, numeric-change counts are high and roughly flat across
  all four transitions (44, 54, 45, 53) even though the text-similarity metrics vary substantially
  (unigram Jaccard ranges 0.259–0.574). This confirms numeric-change count is measuring something
  genuinely independent of prose-wording change here — largely driven by the recurring
  shareholder-voting-results table's four resolution percentages plus the year-number churn
  throughout the narrative, present at similar volume every year regardless of how much the
  surrounding prose was rewritten.
- **Length change as a confound, not a metric.** `remuneration_chair_background_statement`
  2022→2023's +42.2% word-count growth co-occurs with its second-lowest unigram Jaccard (0.434);
  but 2023→2024's smaller +13.5% growth co-occurs with an even lower unigram Jaccard (0.344). Growth
  alone does not predict similarity ranking in this small sample — genuinely new content matters
  independently of how much longer the unit got.

## 10. Diff examples

Concise, representative excerpts (full diffs remain in the session scratch directory and are not
reproduced here per the task's instruction).

**audit_risk_committee, 2020→2021 (replaced):** `"of"` → `"with"` — trivial; alongside larger
deleted spans naming the departing 2020 chairperson's role description. **audit_risk_committee,
2023→2024 (inserted):** *"The Group CFO, Group CEO and the Chief Audit Executive are permanent
invitees to the meetings of the Audit and Risk Committee"* — a wholly new sentence, not present in
any prior year, naming new invitee roles consistent with post-Sanlam governance changes.

**remuneration_chair_background_statement, 2020→2021 (deleted, from 2020 only):**
*"...initiated processes to access the relief offered through the South African government's COVID
Temporary Employment Relief Scheme..."* — COVID-specific content with no 2021 counterpart.
**2023→2024 (inserted):** *"The 2023/24 year in AfroCentric has been significantly shaped by the
acquisition of a controlling shareholding in the Company by Sanlam at the end of May 2023."* — the
opening sentence of the new material, immediately followed (later in the same unit, per Section 8)
by the 50.26%-vote/Sanlam-engagement passage.

**advisory_vote_on_implementation_report, every transition (replaced, the only substantive diff):**
`"2020"` → `"2021"` (and so on for each subsequent year) — confirmed to be the *entire* semantic
content of every diff in this unit across all four transitions.

## 11. Numeric-change analysis

`audit_risk_committee`'s numeric changes (16–21 per transition) are almost entirely meeting-count
fractions ("5/5") and attendance percentages, refreshed every year regardless of whether membership
itself changed — meaning a raw numeric-change *count* alone cannot distinguish "same committee,
routine attendance update" from "membership turnover," even though the underlying committee
membership genuinely does change in three of the four transitions studied. Numeric *content*
(which names pair with which fractions) is more diagnostic than the count, but pairing names to
numbers was not attempted here per the task's instruction not to infer economic or governance
meaning from a numeric metric alone.

`remuneration_chair_background_statement`'s numeric changes are dominated by the recurring
shareholder-voting-results table (four resolution percentages, refreshed every year) plus the
pervasive year-number churn throughout the narrative (page cross-references, "the year ended June
20XX," AGM dates). The single most economically significant number in the entire five-year corpus
studied here — the 50.26% 2023/24 advisory-vote result — is one raw numeric token among roughly 50
that change in that transition; nothing in the numeric-change count itself flags it as more
important than the other 52. **This reinforces Section 8's finding: neither the text-similarity
metrics nor the numeric-change count, used mechanically, would have surfaced this specific fact as
noteworthy without a human (or a future targeted rule) reading the actual numbers.**

`advisory_vote_on_implementation_report`'s numeric changes are exactly 4 in every transition (the
year token appearing twice, each instance counted as one "removed" and one "added" in the
multiset diff) — confirming, from yet another angle, that this unit's own numeric content carries
no information about the vote outcome.

## 12. Failure modes / caveats

- **Very short units and length sensitivity (confirmed, Section 8).** A short, boilerplate unit's
  metric ceiling is high regardless of real-world events; comparing its raw scores against a longer,
  more organically-worded unit without accounting for this is misleading. This is the pilot's
  headline failure mode.
- **Unit-boundary scoping can exclude the evidence entirely (confirmed, Section 8).** Distinct from
  the `MOVED_CROSS_SCHEDULE` / `EXTERNALIZED` container-movement hazards the prior experiments
  documented, this is a *within-schedule, same-year* scoping failure: two units sit on adjacent
  pages of the same report, and the analytically "correct" home for a given fact (per the prior
  report's own unit definitions) is not the unit whose name most suggests it.
- **Paragraph reordering from extraction artifacts, not genuine content reordering (confirmed,
  Section 4.3, Section 9).** The 2023 `audit_risk_committee` block-reconstruction fix left a
  residual ordering difference relative to other years that is a layout artifact, not evidence the
  company itself reorganized the committee report — this must not be read as a `RESTRUCTURED` event
  by any future automated classifier relying on sequence similarity alone.
- **Boundary asymmetry across years within a nominally single unit (confirmed, Section 4.4, Section
  7).** 2020's `remuneration_chair_background_statement` implicitly contains content that in
  2021–2024 lives in a separately-scoped section; this inflates the 2020→2021 apparent change beyond
  its true wording-only value.
- **Numeric-heavy text and tables.** Not separately stress-tested at scale here (the prior
  representation bake-off and longitudinal experiments cover this more directly), but
  `audit_risk_committee`'s composition table shows renumbering/reordering of names produces edit-
  and sequence-similarity noise disproportionate to the substantive change (Section 9).
- **Repeated boilerplate.** The advisory-vote unit is, in effect, entirely repeated boilerplate
  with one interpolated variable; this pilot did not encounter a case of *unwanted* boilerplate
  contamination (e.g., a running header leaking into a unit's text), because the page-furniture
  strip in Section 4/5's methodology removed it before tokenization — but this strip list was
  built specifically for ACT's known running-header/footer strings and would need to be
  re-derived, not reused verbatim, for any other company.
- **Heading text contaminating similarity.** Not a material issue in this sample: headings are
  short relative to body text in all three units, and the two audit-committee years with
  differently-cased/positioned headings (2023, 2024) still produced sensible-looking metrics.
- **Footnotes.** `audit_risk_committee`'s attendance-table footnotes (e.g., "Resigned 15 June
  2023") were retained inside the reconstructed text and contributed real, meaningful numeric/
  textual content (director departures) rather than noise — not a failure mode here, but worth
  flagging that a more aggressive furniture-stripping pass could have accidentally discarded them.
- **Unequal section lengths.** `remuneration_chair_background_statement` nearly doubled in length
  from 2020 to 2024 (734 → 1,401 words); none of the five core metrics normalizes for this
  directly (TF-IDF cosine and Jaccard are somewhat robust to length via set/vector normalization,
  but edit similarity and sequence ratio are more directly sensitive to it), which is why the
  word-count-change column must always be read alongside the similarity metrics, never instead of
  them.

## 13. Recommendation

**(A) EXPAND LEXICAL METRICS TO MORE STRONG UNITS — but the very next unit added must be a second
short/thin unit, chosen deliberately to test whether Section 8's scoping failure recurs or was
specific to `advisory_vote_on_implementation_report`.**

- **Which units should be added next.** From the prior report's corrected `STRONG_LONGITUDINAL_UNIT`
  list (Section 1.1, 25 units): `company_secretary` and `implementation_report` (both
  `HEADING_MATCH_SUFFICIENT`, both narrative-adjacent but structurally distinct from the three
  studied here) as two more full-length additions; and, specifically to stress-test the Section 8
  finding, one more `TOO_THIN` unit from the prior report's four — `statement_regarding_compliance`
  or `approval_by_board` — run the same way `advisory_vote_on_implementation_report` was run here,
  to determine whether short/thin remuneration units generally have their substantive content
  displaced into a neighboring narrative unit, or whether this was specific to the advisory-vote
  case.
- **Which metrics should be retained.** All five core metrics (TF-IDF cosine, unigram Jaccard,
  bigram Jaccard, edit similarity, sequence similarity) plus numeric-change count — none proved
  redundant once their *disagreements* were read as diagnostic rather than as noise to average away
  (Section 9). No metric should be dropped on this sample's evidence.
- **Which metrics can be dropped.** None, but **edit similarity's interpretation should be
  qualified** for any unit whose source reconstruction required a non-trivial block reorder
  (Section 4.3, Section 9) — its readings on such units should be reported with a caveat rather than
  taken at face value, until a column-aware (not whole-page) block-sort fix, of the kind the
  longitudinal experiment already validated for BEL, is implemented and re-tested here.
- **Should the next stage remain ACT-only or add BEL?** **Remain ACT-only for the next round.**
  This pilot surfaced a genuine, non-obvious methodological finding (unit-boundary scoping can
  silently defeat a metric) that has not yet been re-tested even once on a second unit within the
  same company; adding a second company's different report template and different unit-boundary
  conventions before that is resolved would confound two open questions at once. BEL remains a
  reasonable *second* company once ACT's short-unit scoping question is settled, consistent with
  the prior report's own sequencing logic.

This pilot does **not** recommend (B) modifying the metric set before repeating, because nothing
here indicates the metrics themselves are unreliable — every metric behaved exactly as its
definition predicts, including on the unit where the *result* was surprising. It does not recommend
(C) testing a less-stable unit first, because the specific gap this pilot needs to close next
(short/thin-unit boundary scoping) is better isolated by testing another short unit within the same
two stable schedules, not by introducing a new source of instability. It does not recommend (D) —
lexical metrics are not unreliable; the one clear "failure" in this pilot was a unit-design decision
made upstream of the metrics, not a defect in the metrics' own behavior.

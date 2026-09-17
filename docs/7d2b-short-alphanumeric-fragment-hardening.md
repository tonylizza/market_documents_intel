# Track 7D.2b — Short Alphanumeric Fragment Classification Hardening

Scope: one generic hardening fix to the shared block classifier
(`services/block_classification.py`), the single remaining defect Track
7D.2a identified and deliberately left unfixed (docs/7d2a-semantic-unit-
extraction-hardening.md Section 5): short mixed alphanumeric chart/data-
label fragments (e.g. "385 Denis", "15.1% -2.1%") clear neither the
`NUMERIC_FRAGMENT` nor `TABLE_LIKE` nor `DECORATIVE_OR_FRAGMENT` threshold
and leak into narrative `source_text`. No new semantic unit, schedule,
issuer, or structured table is added. `Capital management` remains
unconfigured, as instructed.

## 1. Baseline defect

Reproduced directly against `classify_block` before any change, using the
config's actual thresholds:

| text | chars | words | digit_ratio | alpha_ratio | classifier result (before) |
| --- | --- | --- | --- | --- | --- |
| `385 Denis` | 9 | 2 | 0.333 | 0.556 | PARAGRAPH, not excluded |
| `411 Denis` | 9 | 2 | 0.333 | 0.556 | PARAGRAPH, not excluded |
| `2021 (excluding Denis)` | 22 | 3 | 0.182 | 0.636 | PARAGRAPH, not excluded |
| `26 Denis` | 8 | 2 | 0.250 | 0.625 | PARAGRAPH, not excluded |
| `15.1% -2.1%` | 11 | 2 | 0.455 | 0.000 | PARAGRAPH, not excluded |

Root cause (confirmed, matching 7D.2a Section 5's analysis): each falls
below `numeric_fragment_min_digit_ratio` (0.5) because the label token (or
a second sign/percent character) dilutes the ratio, below
`table_like_min_digit_ratio`'s companion `numeric_token_count >= 3`
requirement (only 1-2 numeric tokens), and above the `alpha_ratio < 0.3`
bar `DECORATIVE_OR_FRAGMENT` requires. With no font/bold signal (the
canonical `source_adapter` path, which 7D.2a made the default preferred
source, does not carry font metadata at all -- `canonical_blocks` has no
font columns) and mixed case (not `is_shouty`), nothing claims them before
the PARAGRAPH default.

Real corpus text from the same pages (ACT 2021, p62), for the
false-positive boundary:

- `revenue increased by 15%` -- contains "by" (unattested here, but
  functionally identical to the real "increase revenue by 4.3%" nearby)
- `If the effect of Denis is excluded, the services business were able to
  increase revenue by 4.3% whilst only increasing operating costs by 2.6%.`
- `This resulted in the double digit increase in operating profit of 11%
  if Denis is excluded.`

These are long, grammatical, contain connector words ("by", "if", "of"),
and end in sentence punctuation -- structurally distinct from the bare
2-3-token label fragments above.

## 2. Rule introduced

`is_short_alphanumeric_fragment` (`block_classification.py`), a narrow
pure helper, called from `classify_block` immediately after the existing
digit-ratio checks and the heading-candidate signal computation (but
before the heading-candidate branch itself decides), reusing the existing
`NUMERIC_FRAGMENT` `BlockType` rather than adding a new enum value (both
options were acceptable per the milestone; reusing keeps the enum and
every downstream consumer of `BlockType` unchanged).

A block qualifies only if **all** of:

1. `word_count` is 1 or 2 (`short_alphanumeric_fragment_max_words = 2`,
   new `ExtractionConfig` constant). Capping at two words means at most
   one token can be the non-numeric label, so the rule never has to weigh
   one label word against another.
2. Total length is at most `short_alphanumeric_fragment_max_chars = 30`.
3. It does not end in sentence punctuation (`_SENTENCE_END_RE`).
4. It does not look like a list item (`_LIST_ITEM_RE`).
5. At least one token contains a digit -- via `_has_digit`, which also
   excludes a footnote-marker-suffix shape (see below).
6. No token, once stripped of surrounding punctuation and lower-cased, is
   a generic English function word (`_NARRATIVE_CONNECTOR_WORDS`: articles,
   prepositions, conjunctions, copula/auxiliary verbs, demonstratives).

The caller additionally withholds the rule whenever the block already
reads as heading-like -- shouty case, bold, or a large font relative to
the page median -- so a heading-candidate signal always wins first; see
Section 5's false-positive account of why this ordering is necessary.

A second narrow guard, `_FOOTNOTE_MARKER_SUFFIX_RE`
(`^[A-Za-z]{3,}\d{1,2}$`), excludes a token from counting as "having a
digit" when it is a run of 3+ letters with 1-2 digits glued directly onto
the end and nothing else numeric -- the shape of a footnote/superscript
reference mark that lost its formatting and merged into the preceding
word during PDF extraction (e.g. "structure1"), not a real numeric label.
This is also structural and generic (not tied to any specific word),
distinct from real figures, which either stand alone ("385", "2022") or
lead with a currency/unit affix ("R450m").

## 3. Why it is generic

The rule contains no ticker, company name, page number, or year literal.
Every signal is structural (word/char count, sentence punctuation, list-
item shape, digit presence, a fixed generic English function-word list,
a fixed footnote-marker shape) or reuses an existing structural signal
(heading-like font/bold/shouty). Verified against the milestone's stated
generalization targets, none of which appear in ACT's real corpus text
verbatim except the first four:

| text | result |
| --- | --- |
| `385 Denis` | NUMERIC_FRAGMENT, excluded |
| `411 Denis` | NUMERIC_FRAGMENT, excluded |
| `26 Denis` | NUMERIC_FRAGMENT, excluded |
| `15.1% -2.1%` | NUMERIC_FRAGMENT, excluded |
| `26 Retail` | NUMERIC_FRAGMENT, excluded |
| `2022 Core` | NUMERIC_FRAGMENT, excluded |
| `R450m Revenue` | NUMERIC_FRAGMENT, excluded |

False-positive guards, verified:

| text | result |
| --- | --- |
| `revenue increased by 15%` | PARAGRAPH, not excluded (connector "by"; also exceeds word cap) |
| `operating margin declined to 8.2%` | PARAGRAPH, not excluded (connector "to"; exceeds word cap) |
| `membership grew by 385 lives` | PARAGRAPH, not excluded (connector "by"; exceeds word cap) |
| `Revenue increased by 15.1% during the year.` | PARAGRAPH, not excluded (sentence punctuation + connectors) |
| `Segment Results 2022` | PARAGRAPH, not excluded (exceeds word cap) |
| `Financial Highlights` | PARAGRAPH, not excluded (no digit token) |
| `Committee` | PARAGRAPH, not excluded (no digit token) |
| `Note 12: Refer to the 2022 annual financial statements for detail.` | PARAGRAPH, not excluded (sentence punctuation + connectors + word cap) |
| `OUR BUSINESS \n6` (real ACT TOC entry) | HEADING_CANDIDATE, not excluded (shouty case wins first) |
| `Group structure1` (real ACT/BEL heading, footnote-marker digit glued on) | PARAGRAPH, not excluded (footnote-marker guard) |

## 4. ACT/BEL real-corpus safety sample

Ran the classifier (before vs. after) against every canonical block in
both companies' full corpora -- 73,525 blocks across ACT (2016-2024, 9
report-years) and BEL (2016-2022, 7 report-years) -- not a hand-picked
sample. This is broader than the milestone's "bounded representative
sample" requirement; it was cheap to do exhaustively once the before/after
comparator existed, and gives a real denominator for the false-positive
rate below rather than an estimate.

**330 of 73,525 blocks (0.45%) changed classification.** All 330 were
inspected. Categories observed (counts approximate, several dozen each):

- **A. Chart/infographic data labels** -- bare figures or percentages
  paired with a short label or unit: `Category 1`-`Category 4`/`Category
  6` (ACT emissions chart), `Tranche 1` (recurring, share-scheme chart),
  `Level 1`/`Level 2` (recurring, a rating-scale label), `10 years`-`40
  years` (BEL tenure-bucket axis labels), `tCO2e` (a single-token ESG
  unit label containing a digit -- "CO2" chemical notation -- appearing
  standalone on an emissions chart), `R4.8 million`-`R758 million`-family
  bare monetary callouts, bare percentage figures like `(0.83%)`, `-3.5%`,
  `17%\n-8%`. **Correct catches**, matching the milestone's own
  generalization targets (`26 Retail`, `2022 Core`, `R450m Revenue`
  shape).
- **B. Table/chart column headers** -- `R'000\nRevenue`, `fund\nR000`,
  `December 2019`/`June 2020`-style bare date headers (recurring across
  every BEL year), `2020 \nTarget`/`2021 \nTarget`-style bare
  year+label pairs (ACT KPI-target tables, recurring across years).
  **Correct catches** -- these are exactly the "chart/data-label fragment"
  shape the milestone describes, not narrative.
- **C. Address/registration boilerplate** -- `Empangeni, 3880` (BEL's
  registered-office postal code line, recurring across 5 years).
  Reasonable to exclude (contact metadata, not narrative prose); not
  narrative loss.
- **D. One genuine ambiguity remaining**: none of the 330 changed blocks
  land inside any currently-configured unit's resolved page range for any
  ticker/year (see Section 6) or represent a full sentence -- the
  narrowest residual risk is a short bare heading paired with a real
  number in a position with no font signal (e.g. a hypothetical "Outlook
  2022" heading in a canonical-only report with no bold/large-font
  metadata). None was observed in either corpus's real 330-block diff;
  documented as a caveat (Section 11), not fixed further, per the
  milestone's own "prefer under-firing" design principle and its explicit
  instruction not to broaden thresholds further once acceptance is met.

Two headings/footnotes/prose categories the milestone specifically asked
to verify were unaffected, confirmed present among the untouched 73,195
blocks: table-of-contents entries in shouty case (protected by the
heading-first ordering fix, Section 5), and every paragraph-length
sentence containing a percentage or year anywhere in either corpus.

## 5. False positive found and fixed during development

The first implementation (rule checked *before* the heading-candidate
branch, `max_words = 3`) caused two real regressions, found only by
running the exhaustive real-corpus diff before finalizing:

1. **Table-of-contents entries** such as `OUR BUSINESS \n6` (real ACT
   2016 corpus, p4) are shouty-case and previously correctly classified
   `HEADING_CANDIDATE`. Because the new rule ran first, it intercepted
   them as a "short label + bare page number" fragment before the
   heading-candidate branch had a chance to fire. **Fix**: moved the
   fragment check to run only after computing (and checking) the
   heading-like signals -- `is_heading_like_font`, `is_bold`, `is_shouty`
   -- and withhold the fragment classification whenever any of those is
   true. This is now covered by
   `test_bold_large_font_short_block_with_number_stays_heading_not_fragment`.
2. **A recurring genuine heading with a glued footnote-marker digit**,
   `Group structure1` / `Activo Health1` (real ACT/BEL corpus, recurring
   across multiple report-years -- a genuine section heading where a
   footnote/superscript reference mark merged into the last word during
   PDF extraction). At `max_words = 3` this was also caught by an
   earlier, since-removed multi-titlecase-word guard; tightening the word
   cap to 2 (Section 2, point 1) made that guard mathematically
   unreachable, so it was deleted, and the real fix is the
   `_FOOTNOTE_MARKER_SUFFIX_RE` guard (Section 2) added specifically for
   this shape. Covered by
   `test_word_with_glued_footnote_marker_digit_not_reclassified`.

Both fixes are reflected in the final rule described in Section 2; the
numbers in Section 4 are post-fix.

## 6. `healthcare_services_review` before/after text quality

Re-ran `market-documents units extract ACT --force` and `... BEL --force`
against the real corpus after the classifier change. Directly confirmed:
none of the 330 real-corpus blocks whose classification changed (Section
4) falls within BEL `gross_margin`'s resolved page range (pp.25/36/37/
39/41 across its 6 resolved years) or ACT `cfo_conclusion`'s (pp.43, 65)
for any ticker/year -- so this section's before/after comparison is
scoped, correctly, to `healthcare_services_review` alone.

| year | pages (before) | pages (after) | word count (before) | word count (after) |
| --- | --- | --- | --- | --- |
| 2021 | 62-63 | 62-63 (unchanged) | 305 | 296 |
| 2022 | 62-62 | 62-62 (unchanged) | 247 | 245 |
| 2023 | 64-64 | 64-64 (unchanged) | 138 | 138 (unchanged) |

Boundaries, heading, and start/end pages are byte-for-byte the same for
all three years -- only in-boundary fragment text changed.

2021's persisted `source_text` before this track (verbatim, blank lines
included) contained inline, between two real paragraphs:

```
-2%

385 Denis

411 Denis

2021
(excluding

Denis)

26 Denis
```

After: the same span now reads

```
Denis)
```

-- every digit-bearing fragment (`-2%`, `385 Denis`, `411 Denis`,
`2021\n(excluding`, `26 Denis`) is now excluded. The one residual token,
a lone `Denis)` (real block, p63#20 in the canonical source, per direct
DB inspection), is not touched: it is a single word with **no digit at
all**, so it falls outside this rule's deliberately numeric-adjacent
scope (Section 2, point 5) -- see Section 11.

2022's persisted `source_text` before this track ended with:

```
With this investment in digitalisation, the cluster's operating profit decreased slightly by 2.4%.

15.1%
-2.1%
```

After: the trailing `15.1%\n-2.1%` block (both purely numeric tokens, no
label at all) is fully excluded -- 2022's `source_text` is now completely
clean, ending at the genuine closing sentence.

2023 had no noise to begin with and is confirmed byte-for-byte unchanged.

## 7. Regression check — existing units

Directly re-inspected the persisted rows for every previously-shipped
unit after the real-corpus re-extraction:

- **BEL `gross_margin`**: all 6 resolvable years (2017-2022) still
  `RESOLVED`, identical start/end pages (25, 36, 37, 39, 39, 41). No
  classifier-changed block (Section 4) falls on any of these pages, so
  this is a structural guarantee, not just an observed match.
- **ACT `cfo_conclusion`**: 2019 (p.43) and 2021 (p.65) still `RESOLVED`,
  same pages. Same structural guarantee -- neither page appears among the
  330 changed blocks.
- **ACT `healthcare_services_review`**: 2021/2022/2023 still `RESOLVED`,
  identical start/end pages, per Section 6. No spurious new unit
  appeared; no previously-resolved year became unresolved (2017-2019/2024
  remain genuinely absent, matching the exact pre-7D.2a/7D.2b pattern);
  provenance remains `canonical_block_id`-sourced throughout (unaffected
  by this track, which only changes classification, not the source-
  preference logic 7D.2a shipped).

No resolved year became unresolved, no page boundary changed, no
legitimate prose disappeared, no spurious new unit appeared, in either
company's full real-corpus re-run.

## 8. Lexical comparison effect

Recomputed `services.lexical_unit_comparison.compute_lexical_metrics` for
`healthcare_services_review`'s two real adjacent-year pairs, using the
actual before/after `source_text` (before = the persisted rows prior to
this track's code change; after = the real-corpus re-extraction in
Section 6):

| pair | metric | before | after |
| --- | --- | --- | --- |
| 2021 -> 2022 | earlier/later word count | 306 / 248 | 297 / 246 |
| | tfidf_cosine | 0.9140 | 0.9367 |
| | unigram_jaccard | 0.7179 | 0.7487 |
| | bigram_jaccard | 0.6219 | 0.6440 |
| | edit_similarity | 0.7746 | 0.7941 |
| | sequence_similarity | 0.8123 | 0.8287 |
| 2022 -> 2023 | earlier/later word count | 248 / 138 | 246 / 138 |
| | tfidf_cosine | 0.8154 | 0.8169 |
| | unigram_jaccard | 0.4643 | 0.4699 |
| | bigram_jaccard | 0.3619 | 0.3647 |
| | edit_similarity | 0.3643 | 0.3670 |
| | sequence_similarity | 0.5492 | 0.5521 |

All six metrics move consistently upward (more similar) by small amounts
for both pairs, as expected: removing chart-noise present in 2021 and
2022 but never in 2023 makes the surviving text a cleaner, more directly
comparable prose signal. No metric was tuned to preserve the prior
values -- the classifier change was finalized (Section 4/5) before this
comparison was run, and no code changed afterward.

## 9. Production-candidacy re-evaluation

`healthcare_services_review`'s remaining Track 7D.2a caveat -- numeric-
fragment noise in the persisted `source_text` -- is resolved for 2021 and
2022 (Section 6), down to one residual single-word token with no digit
(Section 11 caveat). Source text is source-faithful (still built from the
same canonical `source_adapter` path 7D.2a shipped), alignments and
lexical comparisons remain valid (Section 8), provenance remains complete
(`canonical_block_id`-only, unaffected), and no correctness regression
appears anywhere in the real corpus (Section 7).

`coverage_registry.CoverageEntry.production_status` for a narrative unit
is a strict binary derived from `cutover_config.NEW_PIPELINE_NARRATIVE_
SCOPE` membership: `"enabled"` if listed, `"candidate"` otherwise -- there
is no intermediate `"ready"` status in the current schema (`_production_
status` in `coverage_registry.py`), and `cutover_config.py`'s own
docstring is explicit that membership in that set *is* "the live
production cutover path", not a staging flag, and that "expanding this
scope is explicitly out of [7C.6's] own stated scope."

Per this milestone's own explicit instruction ("Do NOT enable/deploy
production in this milestone unless the existing coverage-expansion
convention explicitly includes deployment"), and consistent with 7D.2a's
identical choice to leave `cutover_config.py` untouched: **this track does
not add `healthcare_services_review` to `NEW_PIPELINE_NARRATIVE_SCOPE`.**
Doing so would be a live production-routing change, not a "configured for
next publication/cutover update" step -- there is no separate staging
list to add it to instead. `healthcare_services_review`'s registry status
remains `"candidate"`, with the quality caveat that blocked promotion now
resolved; a future, deliberately-scoped cutover track (mirroring 7C.6's
own process) is the correct place to make the live-routing decision.

## 10. Tests

`tests/test_block_classification.py`: 20 new tests, all pure-function
(no DB), 11 using the real ACT/BEL corpus block text captured during this
track's investigation:

- **Known fragment shapes** (5): `test_number_plus_short_label_
  classified_as_fragment`, `test_multiple_percentage_tokens_classified_
  as_fragment`, `test_year_plus_short_label_classified_as_fragment`,
  `test_currency_unit_prefixed_figure_with_label_classified_as_fragment`,
  plus the helper-level `test_helper_true_for_known_fragment_shapes`.
- **False-positive prevention** (6): legitimate short sentence with a
  percentage, legitimate sentence with a year, ordinary heading, footnote
  text, the real ACT table-of-contents shouty-case regression, and the
  real recurring footnote-marker-glued-digit heading regression.
- **Existing-behavior regression guards** (2): `NUMERIC_FRAGMENT` and
  `TABLE_LIKE` cases from before this track still classify identically.
- **Direct helper unit tests** (6): `is_short_alphanumeric_fragment`
  exercised directly for sentence punctuation, connector words, no-digit
  input, list-item shape, and the word cap.
- **Semantic-unit regression** (via the real-corpus re-run, Sections 6-7,
  not a new DB-fixture test -- consistent with 7D.2a's own choice to
  verify canonical-preference/heading-matching changes only via
  real-corpus runs, not DB fixtures).

Targeted run: 70 passed (block classification + semantic unit extraction
+ source adapter). Full suite, run once at the end: **1118 passed, 3
skipped** (up from 7D.2a's 1100 passed, 3 skipped -- entirely the 18 net
new tests this track adds; no prior test's outcome changed).

## 11. Caveats

1. **A bare single-word residual** ("Denis)", Section 6) survives in
   2021's `source_text` because it contains no digit at all -- this
   rule's scope is deliberately limited to the numeric-adjacent case
   (Section 2, point 5). A rule that also excluded isolated single words
   with no other signal would risk excluding genuine one-word headings
   ("Committee", "Overview") corpus-wide; per the milestone's own
   conservative-bias precedent (`find_table_header_fragment_indices`'s
   documented under-firing preference), this is accepted rather than
   chased with a broader, riskier heuristic.
2. **A short bare heading paired with a real number, with no font
   signal available**, is structurally indistinguishable from a genuine
   chart label of the same shape (e.g. a hypothetical "Outlook 2022"
   section heading in a report whose canonical extraction carries no
   bold/font metadata). None was observed in either corpus's real
   330-block safety sample (Section 4), but the theoretical risk is not
   eliminated by this rule -- it is bounded by capping at 2 words and by
   requiring the heading-like signals (font/bold/shouty) to win first
   whenever they are available.
3. **The generic connector-word list is a fixed, hand-authored set of
   ~35 common English function words.** It generalizes across any
   English-language report (nothing ticker- or issuer-specific), but a
   grammatical fragment that happens to omit every such word and also
   fits in 2 words or fewer is not protected by it -- no such case was
   found in either real corpus.
4. **Address/registration boilerplate** (e.g. BEL's recurring
   "Empangeni, 3880" postal-code line, Section 4.C) is now excluded
   as a side effect of the same structural shape as a real chart label.
   This is treated as acceptable, not a regression -- it is contact
   metadata, not narrative disclosure text -- but it was not a
   specifically requested target of this track.

## 12. Final verdict

**PASS — FRAGMENT CLASSIFICATION HARDENED.**

The generic classifier gap Track 7D.2a identified and deferred is fixed,
verified against the milestone's own generalization targets and an
exhaustive (not sampled) real-corpus safety pass across both companies'
full histories (73,525 blocks, 330 changed, all inspected), with two real
false positives found and fixed during development before finalizing.
`healthcare_services_review`'s source text is materially cleaner for
2021/2022 with byte-identical boundaries, no shipped unit regressed, and
the full test suite passes.

`healthcare_services_review`: **REMAINS_CANDIDATE.** Its extraction-
quality caveat is resolved; the only remaining step toward `"enabled"` is
a deliberate, separately-scoped live-cutover decision (Section 9), which
this milestone's own instructions explicitly exclude from being made
here.

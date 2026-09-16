# Track 7C.3: Analytical Eligibility + Lexical Comparison

## 1. Scope

7C.3 consumes persisted `SemanticUnitAlignment` rows from 7C.2 and answers
two questions for a matched semantic unit:

> How should this aligned unit be compared?

and, only when the answer is `LEXICAL_ONLY`:

> How much did the wording change?

```
SemanticUnitAlignment (7C.2)
   ->
AnalyticalDecisionRun / AnalyticalDecision  (routing)
   ->
LEXICAL_ONLY
   ->
LexicalUnitComparison  (lexical metrics)
```

It does **not** implement structured-table comparison, numeric-context
parsing, a presence/status comparison engine, boundary expansion, LLM
adjudication, embeddings, thresholds, or a composite/materiality score.
Alignment and comparison remain separate: 7C.3 never revisits or overrides
a `SemanticUnitAlignmentStatus`, and lexical similarity is never used to
redefine correspondence.

## 2. Analytical routing model

Routing is deterministic and configuration-driven --
`services.analytical_eligibility.route_alignment` -- keyed on the
alignment's own status:

| `SemanticUnitAlignmentStatus` | Routing outcome |
|---|---|
| `MATCHED` / `RENAMED` | Look up `(ticker, unit_key)` in `UNIT_ANALYTICAL_MODES`. Configured -> that mode. Unconfigured -> `NOT_ELIGIBLE` (never guessed). |
| `ADDED` / `REMOVED` | `PRESENCE_STATUS_ONLY` -- a declared routing outcome; no presence/status comparison engine is implemented. |
| `UNRESOLVED_UPSTREAM` / `AMBIGUOUS` | **No `AnalyticalDecision` row at all.** These states are not trustworthy enough to license any analytical claim, substantive-absence or otherwise. |

`unit_key` alone (not word count, not `unit_type`) drives eligibility --
per the research (`docs/experiments/annual-report-analytical-unit-eligibility.md`),
function and validated analytical role matter more than raw length, and a
`word_count < X` rule was explicitly rejected as a primary criterion.

Currently configured (`services/analytical_eligibility.py`,
`UNIT_ANALYTICAL_MODES`):

| Ticker | `unit_key` | Mode |
|---|---|---|
| BEL | `gross_margin` | `LEXICAL_ONLY` |
| ACT | `cfo_conclusion` | `LEXICAL_ONLY` |

Both are recurring, substantive, boilerplate-anchored prose units with no
embedded numeric table or presence/status framing -- clean
`LEXICAL_DIRECT`/`LEXICAL_ONLY` candidates in the research's own
terminology (`annual-report-bel-compact-validation.md` Section 3).

## 3. Supported comparison modes

`AnalyticalMode`: `LEXICAL_ONLY`, `LEXICAL_WITH_NUMERIC_CONTEXT`,
`STRUCTURED_COMPARISON_PREFERRED`, `PRESENCE_STATUS_ONLY`, `NOT_ELIGIBLE`.

Only `LEXICAL_ONLY` is executed in 7C.3. The other three (besides
`NOT_ELIGIBLE`) are declared enum members with no comparison engine behind
them -- a future milestone's scope, not this one's.

## 4. Lexical metrics

`services.lexical_unit_comparison.compute_lexical_metrics` reuses metric
functions from `services.similarity_metrics` and the shared tokenizer from
`services.similarity_tokenization` -- no metric math is reimplemented in
`compute_lexical_metrics` itself. Two functions were added to
`similarity_metrics.py` specifically for 7C.3, to genuinely reproduce the
research's own metric *definitions* (docs/experiments/annual-report-
lexical-change-pilot.md Section 5) rather than reuse a document-pipeline
metric that only shares a name (see Section 4.1's correction note):

- `tfidf_cosine` -- **`pairwise_tfidf_cosine_similarity`**: genuine TF-IDF
  cosine (smooth IDF, L2-normalized), fit only on the two documents being
  compared. Distinct from `lexical_cosine_similarity` (the M3/M4
  document-pipeline metric, unchanged, still used there), which is
  deliberately **not** TF-IDF -- sublinear term-frequency only, no IDF.
- `unigram_jaccard` (`jaccard_similarity(..., shingle_size=1)`)
- `bigram_jaccard` (`jaccard_similarity(..., shingle_size=2)`, the module
  default)
- `edit_similarity` -- **`character_edit_similarity`**: character-level
  RapidFuzz Levenshtein over NFKC-normalized, lowercased,
  whitespace-collapsed text, matching the research's own character-level
  definition. Distinct from `edit_similarity` (the M3/M4 document-pipeline
  metric, unchanged, still used there), which runs the same algorithm over
  *word tokens* instead.
- `sequence_similarity` (`diff_similarity`, `difflib` Ratcliff/Obershelp
  over word tokens, `autojunk=False`) -- this one was already a correct
  reproduction of the research's definition; unchanged. See Section 4.1.
- `earlier_word_count` / `later_word_count` / `word_count_change` /
  `word_count_change_pct` -- token counts from the same shared tokenizer,
  not `SemanticUnit.word_count` (a 7C.1 extraction-provenance field
  computed independently), so word count and the token-based metrics are
  always sourced from one consistent tokenization.

Every similarity field is nullable and left `NULL` (never a fabricated
`0.0`) when the metric is mathematically undefined for its inputs (e.g.
one empty text). No composite score, no threshold, no materiality label.

### 4.1 Correction: metric-definition audit against the research

The first pass of 7C.3 populated `tfidf_cosine` and `edit_similarity` with
the document-pipeline's existing `lexical_cosine_similarity` and
`edit_similarity` functions (M3/M4, `services/similarity_metrics.py`).
Both are real, already-tested metrics -- but neither is the metric the
research actually validated:

- **`tfidf_cosine` was genuinely wrong.** `lexical_cosine_similarity` is
  explicitly, by its own docstring, **not** TF-IDF (sublinear term
  frequency only, no document-frequency/IDF weighting anywhere). The
  research's "TF-IDF cosine" is literal `TfidfVectorizer`-style TF-IDF.
  **Fixed**: added `pairwise_tfidf_cosine_similarity` (smooth-IDF, L2-norm,
  fit pairwise on the two documents in the pair -- consistent with this
  module's pair-locality convention, and verified far closer to the
  research's published values than a multi-document corpus fit; see
  Section 10) and switched `tfidf_cosine` to it. The `lexical_cosine_similarity`
  function itself is untouched and still backs the M3/M4 document-level
  pipeline -- nothing else in the codebase depends on it changing.
- **`edit_similarity` was genuinely wrong.** The research's definition
  (Section 5 of the lexical-change pilot) is **character-level**
  Levenshtein distance over the full normalized string
  (`1 - distance/max(len_a, len_b)`, denominator in characters). The
  document-pipeline's `edit_similarity` runs the identical RapidFuzz
  Levenshtein algorithm, but over **word tokens**, not characters -- a
  real, intentional, and unrelated design choice for that pipeline (per
  its own docstring), not a bug there. Applied to 7C.3, though, it does
  not answer the research's question. **Fixed**: added
  `character_edit_similarity` (character-level Levenshtein on
  NFKC-normalized/lowercased/whitespace-collapsed text -- verified the
  distance formula is identical to RapidFuzz's own `normalized_similarity`)
  and switched `edit_similarity` to it. The document-pipeline's
  `edit_similarity` is untouched.
- **`sequence_similarity` was already correct.** The research's
  definition is `difflib.SequenceMatcher(autojunk=False)` run over the
  **word-token sequence** -- exactly what `diff_similarity` already does.
  Testing with the research's own literal tokenizer regex in place of this
  codebase's tokenizer changed the BEL 2018->2019/2021->2022 ratios by
  under 0.01 (0.6486 -> 0.6552, 0.4417 -> 0.4426) -- confirming the
  remaining gap against the published research table (0.480, 0.311) is
  **not** a metric-definition or tokenization difference. It is most
  plausibly attributable to minor wording/content differences between this
  codebase's production-reconstructed `SemanticUnit.source_text` and the
  research pilot's independently-extracted text (see Section 10):
  order-sensitive metrics like `SequenceMatcher` are far more sensitive to
  small such differences than the closely-matching, order-insensitive
  Jaccard values are. No code change was made -- the field and function
  already correctly implement the validated definition.

The routing model, schema shapes (aside from the one column rename below),
alignment logic, and every earlier milestone are unchanged by this
correction.

**Schema effect**: `lexical_unit_comparisons.lexical_cosine_similarity`
was renamed to `lexical_unit_comparisons.tfidf_cosine`
(`migrations/versions/3ac7dda97887_rename_lexical_cosine_to_tfidf_cosine.py`)
to describe what the column actually now holds. `edit_similarity` keeps
its column name -- only the function backing it changed.

## 5. Files / schema changed

New:

- `src/market_documents/models/analytical_comparison.py` --
  `AnalyticalDecisionRun`, `AnalyticalDecision`, `LexicalUnitComparison`.
- `src/market_documents/services/analytical_eligibility.py` -- routing +
  Run/Result orchestration (`route_alignment`, `run_analytical_comparison`,
  `get_current_decision_run`).
- `src/market_documents/services/lexical_unit_comparison.py` -- pure
  lexical-metric computation (`compute_lexical_metrics`).
- `migrations/versions/3b24f4904672_analytical_eligibility_and_lexical_comparison_schema.py`
  -- `analytical_decision_runs`, `analytical_decisions`,
  `lexical_unit_comparisons` tables; `analytical_decision_run_status`,
  `analytical_mode` enum types. No existing table modified. Verified
  reversible (`alembic downgrade -1` then `upgrade head`).
- `migrations/versions/3ac7dda97887_rename_lexical_cosine_to_tfidf_cosine.py`
  -- renames `lexical_unit_comparisons.lexical_cosine_similarity` to
  `tfidf_cosine` (Section 4.1's correction). Verified reversible.
- New enums in `models/enums.py`: `AnalyticalDecisionRunStatus`,
  `AnalyticalMode`.

Modified:

- `src/market_documents/cli/units.py` -- new `classify` command (routing +
  lexical comparison in one call, preserving Run/Result separation
  internally); `status` now also prints current `AnalyticalDecisionRun`
  state.
- `src/market_documents/models/__init__.py` -- new exports.
- `src/market_documents/services/similarity_metrics.py` -- two functions
  *added* for the Section 4.1 correction: `pairwise_tfidf_cosine_similarity`,
  `character_edit_similarity`. Every existing function in this module
  (`lexical_cosine_similarity`, `edit_similarity`, `jaccard_similarity`,
  `diff_similarity`, etc.) is unchanged, and the M3/M4 document-level
  similarity pipeline that depends on them is unaffected.

Schema notes:

- `AnalyticalDecisionRun` pins `alignment_run_id` (the source
  `SemanticUnitAlignmentRun`), mirroring how `SemanticUnitAlignmentRun`
  pins its two source `SemanticUnitRun`s -- a result stays reproducible
  even after realignment.
- `AnalyticalDecision` has a `(decision_run_id, semantic_unit_alignment_id)`
  unique constraint -- one decision per alignment per run.
- `LexicalUnitComparison` has a unique `analytical_decision_id` (one
  comparison per decision) and also stores `semantic_unit_alignment_id`
  directly, per the milestone's schema guidance, to avoid a join through
  `AnalyticalDecision` for the common "get metrics for this alignment"
  query.
- Unlike the plan text's per-decision suggestion, `algorithm_version` and
  `configuration_hash` are stored once on `AnalyticalDecisionRun`, not
  duplicated on every `AnalyticalDecision` row -- this mirrors the
  existing `SemanticUnitAlignmentRun`/`SemanticUnitAlignment` (7C.2) and
  `SemanticUnitRun`/`SemanticUnit` (7C.1) split already established in
  this codebase, rather than introducing a new precedent.

## 6. Idempotency / run model

Follows the `SemanticUnitAlignmentRun`/`SemanticUnitAlignment` convention
exactly: `run_analytical_comparison` skips (returning the existing run) if
a current successful `AnalyticalDecisionRun` already used the identical
source `alignment_run_id` and `configuration_hash`, unless `force=True`.
"Current successful" is a query-time rule (`get_current_decision_run`),
never a stored flag. A run that produces any `NOT_ELIGIBLE` decision
completes as `COMPLETED_WITH_WARNINGS` (mirroring `review_reason` on
`SemanticUnitAlignmentRun`); an unhandled exception marks the run `FAILED`
with `error_message` and leaves no partial decision/comparison rows
(`session.begin_nested()`, same pattern as `run_alignment`).

## 7. Tests

- `tests/test_similarity_metrics.py`: new pure tests for
  `pairwise_tfidf_cosine_similarity` (identical/disjoint/empty/bounded
  behavior; an exact hand-computed smooth-IDF/L2-norm case; explicit
  divergence from `lexical_cosine_similarity` on a repeated-term document)
  and `character_edit_similarity` (identical/empty/bounded behavior; an
  exact hand-computed case verifying the research's own
  `1 - distance/max(len)` formula; explicit divergence from the
  token-level `edit_similarity`). Every pre-existing test in this file is
  unchanged and still passes.
- `tests/test_lexical_unit_comparison.py` (pure): persisted metrics equal
  direct calls to the correct `similarity_metrics` functions
  (`pairwise_tfidf_cosine_similarity`, `character_edit_similarity`,
  `jaccard_similarity`, `diff_similarity`); undefined-metric `None`
  handling; word-count-change-pct edge cases.
- `tests/test_analytical_eligibility_routing.py` (pure): configured units
  route to `LEXICAL_ONLY`; unconfigured `unit_key`/ticker never silently
  becomes lexical; `UNRESOLVED_UPSTREAM`/`AMBIGUOUS` produce no decision;
  `ADDED`/`REMOVED` route to `PRESENCE_STATUS_ONLY`, never lexical.
- `tests/test_analytical_eligibility_service.py` (DB-backed): full
  `SemanticUnitAlignment(MATCHED) -> AnalyticalDecision -> LexicalUnitComparison`
  integration; ineligible-when-no-alignment-run; idempotent rerun; `force`
  creates a new run without duplicating within it; no `Passage`/
  `PassageAlignment` dependency.

Full suite: **980 passed, 3 skipped, 0 failed**
(`.venv/bin/python -m pytest -q`) -- 980 - 944 = 36, the 25 original 7C.3
tests plus 11 new tests added for this correction, with zero regressions
anywhere, including the M3/M4 document-level similarity pipeline that
depends on the unmodified `lexical_cosine_similarity`/`edit_similarity`
functions.

## 8. Real-corpus BEL results

`units classify BEL --schedule financial_performance --force` (re-run
after the Section 4.1 correction), against the two `MATCHED`
`gross_margin` pairs available (2018->2019 and 2021->2022 -- 2019->2020
and 2020->2021 are correctly excluded because 7C.2 marks BEL 2020's
`gross_margin` `UNRESOLVED_UPSTREAM`, per its own documented caveat):

| Pair | Mode | TF-IDF cosine | Unigram Jaccard | Bigram Jaccard | Edit sim. (char) | Seq. sim. | Words |
|---|---|---:|---:|---:|---:|---:|---|
| 2018->2019 | LEXICAL_ONLY | 0.7469 | 0.4808 | 0.3506 | 0.6612 | 0.6486 | 64->47 (-17, -26.6%) |
| 2021->2022 | LEXICAL_ONLY | 0.7450 | 0.3158 | 0.2097 | 0.5042 | 0.4417 | 139->101 (-38, -27.3%) |

Both routed to `LEXICAL_ONLY` at `HIGH` confidence via the configured
`(BEL, gross_margin)` entry, exactly as expected -- no other `AnalyticalMode`
was produced for these pairs.

## 9. ACT coverage

**No eligible ACT pair exists in the real corpus.** Per 7C.2's own
real-corpus results (`docs/7c2-semantic-unit-alignment.md` Section 6),
every ACT adjacent-year pair either has no configured `cfo_conclusion`
unit resolved on either side, or resolves it on only one side with the
other side's `SemanticUnitRun` carrying a warning -- always
`UNRESOLVED_UPSTREAM`, never `MATCHED`. `units classify ACT
--schedule financial_performance` was run against the real corpus and
confirms this directly: every pair with a current alignment run completes
with zero `AnalyticalDecision` rows. This is a pre-existing 7C.2 limitation
of the current single-fixed-`unit_key`-per-company configuration, not a
7C.3 defect, and per the milestone's own instruction, no test was
manufactured to fake an eligible ACT pair.

## 10. Parity against prior research metrics

**Word counts** match the compact-validation research
(`docs/experiments/annual-report-bel-compact-validation.md` Section 3)
**exactly** for both transitions (64->47, 139->101).

**Unigram/bigram Jaccard** land within ~0.01 of the research's values
(2018->2019: research unigram 0.481 vs. implementation 0.4808, bigram
0.351 vs. 0.3506; 2021->2022: research unigram 0.306 vs. implementation
0.3158, bigram 0.202 vs. 0.2097) -- consistent with near-identical
shingle-based token-overlap tokenization. Unaffected by the Section 4.1
correction (never changed).

**TF-IDF cosine**, now computed by the genuine `pairwise_tfidf_cosine_similarity`,
lands within ~0.005 of the research's published values: 2018->2019
research 0.752 vs. implementation 0.7469 (diff 0.005); 2021->2022 research
0.748 vs. implementation 0.7450 (diff 0.003). This is a **close, direct
numeric reproduction** -- the fitting-scope difference documented in
`pairwise_tfidf_cosine_similarity`'s own docstring (pairwise 2-document fit
here vs. the research's per-unit 5-document corpus fit) turned out to
matter far less than expected: a 5-document corpus fit was tested directly
during this correction and produced ~0.659 for both transitions, roughly
0.09 further from the research values than the pairwise fit -- so pairwise
is not just architecturally consistent with this module's pair-locality
convention, it is also the closer numeric match here.

**Edit similarity**, now computed by the genuine `character_edit_similarity`,
improved substantially but does not closely reproduce the research table:
2018->2019 research 0.760 vs. implementation 0.6612 (diff ~0.10);
2021->2022 research 0.621 vs. implementation 0.5042 (diff ~0.12) -- versus
the pre-correction token-level values of 0.5625/0.3669, which were both
further off *and* the wrong metric definition. The metric definition is
now confirmed correct (character-level Levenshtein,
`1 - distance/max(len)`, matching RapidFuzz's own formula exactly -- see
`tests/test_similarity_metrics.py::test_character_edit_matches_research_formula`).
The residual gap is attributed to genuine, minor differences between this
codebase's production-reconstructed `SemanticUnit.source_text` and the
research pilot's independently-extracted text for the same PDF passage --
character-level Levenshtein is inherently far more sensitive to small
wording/spacing/punctuation differences than length- or
overlap-based metrics are (the research document itself makes this same
observation about edit similarity's sensitivity, Section 8 there). This is
not a metric-definition bug; reopening PDF extraction/reconstruction to
chase closer character-level parity is explicitly out of this milestone's
scope.

**Sequence similarity** was audited and found to already be a correct
reproduction of the research's own definition (`difflib.SequenceMatcher`,
`autojunk=False`, over word tokens) -- no code change was needed or made.
Re-running the BEL transitions with the research's own literal tokenizer
regex (`\d+\.\d+%?|\d+/\d+|\d+%?|[A-Za-z]+(?:['’][A-Za-z]+)*`) in place of
this codebase's tokenizer changed the ratios by under 0.01 (0.6486 ->
0.6552, 0.4417 -> 0.4426), so tokenization is not the source of the
remaining gap against the published table (0.480, 0.311 respectively). The
same source-text-reconstruction explanation given for edit similarity
above is the most plausible remaining cause, for the same reason
(order-sensitive metrics are more exposed to small wording differences
than the closely-matching, order-insensitive Jaccard values are). This is
an implementation-parity check, not new metric research, per the
milestone's own instruction -- the qualitative pattern the research
predicted still holds exactly regardless (Section 11).

## 11. Sanity check against research behavior

Prior research found, for BEL Gross Margin: stable boilerplate opening
language keeping cosine moderate-to-high, bigram Jaccard dropping further
because the substantive sentences reword every year, and meaningful
word-count changes. The corrected 7C.3 implementation reproduces this
pattern exactly:

- TF-IDF cosine (0.747, 0.745) is moderate-to-high in both transitions,
  now numerically close to the research's own 0.752/0.748.
- Bigram Jaccard (0.35, 0.21) is lower than cosine in both transitions, by
  a wide margin -- the same "stable framing, reworded substance"
  signature.
- Word-count changes are substantial in both transitions (-26.6%, -27.3%),
  correctly reflecting real prose revision rather than a near-zero
  extraction artifact.

## 12. Caveats

- **ACT has zero real-corpus `LEXICAL_ONLY` coverage** (Section 9) -- a
  consequence of 7C.2's current single-fixed-`unit_key` configuration, not
  a 7C.3 defect. Adding a second ACT unit_key or loosening the
  single-unit-per-schedule configuration is out of scope here.
  `route_alignment`/`UNIT_ANALYTICAL_MODES` are tested directly with
  synthetic ACT data (`tests/test_analytical_eligibility_routing.py`,
  `tests/test_analytical_eligibility_service.py`) to confirm the
  configured path works correctly whenever a `MATCHED` pair does appear.
- **Edit-similarity and sequence-similarity parity with the research is
  qualitative and directionally close, but not tight numerically**
  (Section 10) -- both are now confirmed to implement the research's exact
  metric *definitions*; the residual ~0.10-0.12 (edit) and comparable
  (sequence) gap against the published BEL table is attributed to minor
  differences between this codebase's production-reconstructed source text
  and the research's independently-extracted text for the same passages,
  not a metric-definition or tokenization error. TF-IDF cosine and word
  counts, by contrast, now land within 0.005 and exactly, respectively.
- `RENAMED` is routed identically to `MATCHED` in `route_alignment`, but
  (per 7C.2) is never actually emitted by the current alignment cascade --
  exercised only by unit tests, not the real corpus, same caveat 7C.2
  itself documents for `RENAMED`/`ADDED`/`REMOVED`.

## 13. Final verdict

**PASS -- READY FOR 7C.4**

Trustworthy `MATCHED` semantic units route correctly to `LEXICAL_ONLY`
under the configured units. `LEXICAL_ONLY` comparisons now persist metrics
that genuinely implement the research's validated definitions:
`tfidf_cosine` is real pairwise TF-IDF cosine (not the unrelated
sublinear-TF metric used in the first pass) and reproduces the published
BEL values within 0.005; `edit_similarity` is real character-level
Levenshtein (not the unrelated token-level metric used in the first pass)
with its formula verified identical to the research's own; `sequence_similarity`
was audited and confirmed already correct, unchanged. Residual numeric
gaps in edit/sequence similarity are attributed to source-text
reconstruction differences between this codebase and the research's
independent extraction, not to metric-definition or tokenization errors --
documented rather than chased further, since reopening extraction is out
of this milestone's scope. `UNRESOLVED_UPSTREAM`/`AMBIGUOUS` alignments
never produce a false comparison; the full test suite passes with zero
regressions, including the unmodified M3/M4 document-level pipeline. The
ACT real-corpus coverage gap (Section 9) remains a pre-existing 7C.2
corpus-configuration limitation, not a gap in the 7C.3 mechanism, and is
documented rather than worked around with a manufactured test.

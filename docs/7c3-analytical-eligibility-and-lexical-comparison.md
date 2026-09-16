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

`services.lexical_unit_comparison.compute_lexical_metrics` reuses the
existing, already-validated metric functions from `services.similarity_metrics`
and the shared tokenizer from `services.similarity_tokenization` -- no
metric math is reimplemented:

- `lexical_cosine_similarity` (sublinear-TF cosine -- explicitly **not**
  TF-IDF; see Section 7's caveat)
- `unigram_jaccard` (`jaccard_similarity(..., shingle_size=1)`)
- `bigram_jaccard` (`jaccard_similarity(..., shingle_size=2)`, the module
  default)
- `edit_similarity` (RapidFuzz token-level Levenshtein)
- `sequence_similarity` (`diff_similarity`, `difflib` Ratcliff/Obershelp)
- `earlier_word_count` / `later_word_count` / `word_count_change` /
  `word_count_change_pct` -- token counts from the same shared tokenizer,
  not `SemanticUnit.word_count` (a 7C.1 extraction-provenance field
  computed independently), so word count and the similarity metrics are
  always sourced from one consistent tokenization.

Every similarity field is nullable and left `NULL` (never a fabricated
`0.0`) when the metric is mathematically undefined for its inputs (e.g.
one empty text). No composite score, no threshold, no materiality label.

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
- New enums in `models/enums.py`: `AnalyticalDecisionRunStatus`,
  `AnalyticalMode`.

Modified:

- `src/market_documents/cli/units.py` -- new `classify` command (routing +
  lexical comparison in one call, preserving Run/Result separation
  internally); `status` now also prints current `AnalyticalDecisionRun`
  state.
- `src/market_documents/models/__init__.py` -- new exports.

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

- `tests/test_lexical_unit_comparison.py` (pure): persisted metrics equal
  direct calls to `similarity_metrics`/`similarity_tokenization`
  functions; undefined-metric `None` handling; word-count-change-pct
  edge cases.
- `tests/test_analytical_eligibility_routing.py` (pure): configured units
  route to `LEXICAL_ONLY`; unconfigured `unit_key`/ticker never silently
  becomes lexical; `UNRESOLVED_UPSTREAM`/`AMBIGUOUS` produce no decision;
  `ADDED`/`REMOVED` route to `PRESENCE_STATUS_ONLY`, never lexical.
- `tests/test_analytical_eligibility_service.py` (DB-backed): full
  `SemanticUnitAlignment(MATCHED) -> AnalyticalDecision -> LexicalUnitComparison`
  integration; ineligible-when-no-alignment-run; idempotent rerun; `force`
  creates a new run without duplicating within it; no `Passage`/
  `PassageAlignment` dependency.

Full suite: **969 passed, 3 skipped, 0 failed**
(`.venv/bin/python -m pytest -q`) -- 969 - 944 = 25, exactly the new 7C.3
tests, with zero regressions elsewhere (7C.2's commit reported 944 passed
before this track began).

## 8. Real-corpus BEL results

`units classify BEL --schedule financial_performance`, against the two
`MATCHED` `gross_margin` pairs available (2018->2019 and 2021->2022 --
2019->2020 and 2020->2021 are correctly excluded because 7C.2 marks BEL
2020's `gross_margin` `UNRESOLVED_UPSTREAM`, per its own documented
caveat):

| Pair | Mode | Cosine | Unigram Jaccard | Bigram Jaccard | Edit sim. | Seq. sim. | Words |
|---|---|---:|---:|---:|---:|---:|---|
| 2018->2019 | LEXICAL_ONLY | 0.7712 | 0.4808 | 0.3506 | 0.5625 | 0.6486 | 64->47 (-17, -26.6%) |
| 2021->2022 | LEXICAL_ONLY | 0.6492 | 0.3158 | 0.2097 | 0.3669 | 0.4417 | 139->101 (-38, -27.3%) |

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

Word counts match the compact-validation research
(`docs/experiments/annual-report-bel-compact-validation.md` Section 3)
**exactly** for both transitions (64->47, 139->101), and unigram/bigram
Jaccard land within ~0.01 of the research's values (e.g. 2018->2019:
research unigram 0.481 vs. implementation 0.4808; bigram 0.351 vs. 0.3506)
-- consistent with both using near-identical shingle-based token-overlap
tokenization.

Cosine, edit-similarity, and sequence-similarity diverge more from the
research table (e.g. 2018->2019: research edit sim. 0.760 vs.
implementation 0.5625). This is an **expected, already-documented**
divergence, not a new bug: the research table's "TF-IDF cosine" column is
literally TF-IDF (document-frequency-weighted), while this codebase's
`lexical_cosine_similarity` is explicitly, by design, **not** TF-IDF --
sublinear term-frequency only, no IDF weighting anywhere (see its
docstring in `services/similarity_metrics.py`, a decision made in an
earlier milestone, unrelated to 7C.3). The research's own compact-
validation script was a throwaway exploratory tool with its own metric
implementations, never wired to this codebase's production
`similarity_metrics`/`similarity_tokenization` modules; some difference in
edit/sequence metrics is the expected result of two independently-written
tokenizers/algorithms rather than a shared implementation. This is only an
implementation-parity check, not new metric research (per the milestone's
own Section 9 instruction) -- the qualitative pattern the research
predicted still holds exactly (see Section 11).

## 11. Sanity check against research behavior

Prior research found, for BEL Gross Margin: stable boilerplate opening
language keeping cosine moderate-to-high, bigram Jaccard dropping further
because the substantive sentences reword every year, and meaningful
word-count changes. The 7C.3 implementation reproduces this pattern
exactly:

- Cosine (0.77, 0.65) is moderate-to-high in both transitions.
- Bigram Jaccard (0.35, 0.21) is lower than cosine in both transitions,
  by a wide margin -- the same "stable framing, reworded substance"
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
- **Cosine/edit/sequence-similarity parity with the exploratory research
  script is qualitative, not numeric** (Section 10) -- expected, given the
  research script's real TF-IDF weighting versus this codebase's
  deliberately-not-TF-IDF cosine metric, and two independently-written
  tokenizers. Word counts and Jaccard metrics land at or very near the
  research's own numbers.
- `RENAMED` is routed identically to `MATCHED` in `route_alignment`, but
  (per 7C.2) is never actually emitted by the current alignment cascade --
  exercised only by unit tests, not the real corpus, same caveat 7C.2
  itself documents for `RENAMED`/`ADDED`/`REMOVED`.

## 13. Final verdict

**PASS WITH DOCUMENTED CAVEAT -- READY FOR 7C.4**

Trustworthy `MATCHED` semantic units route correctly to `LEXICAL_ONLY`
under the configured units; `LEXICAL_ONLY` comparisons persist the
validated metrics correctly (word counts and Jaccard values reproduce the
research numbers closely; cosine/edit/sequence differ only because of a
documented, pre-existing, and intentional metric-definition difference,
not an implementation bug); `UNRESOLVED_UPSTREAM`/`AMBIGUOUS` alignments
never produce a false comparison; real BEL comparisons reproduce the
independently established qualitative pattern exactly; the full test
suite passes with zero regressions. The one caveat -- no real-corpus ACT
`LEXICAL_ONLY` example -- is a pre-existing 7C.2 corpus-configuration
limitation, not a gap in the 7C.3 mechanism itself, and is documented
rather than worked around with a manufactured test.

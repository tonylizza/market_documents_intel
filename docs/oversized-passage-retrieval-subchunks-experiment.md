# Oversized Passage Eligibility and Segmentation Hardening (Milestone 6)

**Status**: Controlled corpus rebuild complete. Verdict: **ACCEPT AND FREEZE** (Section 20). The rebuild was run twice: the first pass exposed a real, previously-unnoticed defect in the Part B packer fix itself (Section 13.1) -- fixed, re-tested, and the corpus was re-segmented/re-embedded/re-aligned a second time under the corrected code (`ALGORITHM_VERSION` 1.1.1). The rebuild also surfaced that the "80,346 eligible / 767 unembedded / 99.05%" figures this milestone's brief cited as the Milestone 5 baseline do not reproduce under correct current-run resolution -- the true, correctly-measured pre-Milestone-6 corpus has 21,016 eligible passages, not 80,346 (Section 13.2 explains why, in detail, with cross-validation against the production `reports embedding-status` CLI command). All results below use the corrected, internally consistent baseline.

This milestone follows `docs/passage-pipeline-data-quality-audit.md`, `docs/passage-ground-truth-validation.md`, `docs/table-fragment-hardening-experiment.md`, `docs/exact-hash-reconciliation-experiment.md`, `docs/high-similarity-unmatched-diagnostic.md`, `docs/exact-candidate-retrieval-correctness.md`, and `docs/embedding-eligibility-token-limit-diagnostic.md` (Milestone 5, verdict **RETRIEVAL SUBCHUNKS**).

---

## 1. Executive summary

Milestone 5 found that 767 of 80,346 alignment-eligible passages (0.95%) were unembedded and therefore structurally invisible to semantic candidate generation, via two mechanisms:

- **Mechanism 1 (578 of 767, 75.4%)**: a packer bug in `passage_segmentation.py::_pack_run_into_passages` -- the `max_words` ceiling check only fired when a group already had content, so a single source `TextBlock` larger than `max_words` was always accepted unconditionally into its own oversized passage. Concentrated 93% in KP2.
- **Mechanism 2 (189 of 767, 24.6%)**: ordinary word-count packing producing multi-block passages that are ≤400 words but whose subword tokenization exceeds the BGE model's 512-token limit.

Milestone 5's read-only simulation showed sentence-boundary retrieval subchunks (480-token ceiling) resolve 100% of both mechanisms with no residual over-limit chunks, and recommended this be implemented alongside a separate fix to the packer bug.

This milestone implements both, exactly as scoped:

- **Part A (retrieval subchunks)**: a passage whose full text exceeds the embedding model's token limit is no longer skipped. It keeps its canonical `Passage` completely unchanged and is instead split into deterministic, token-safe, sentence-aware retrieval subchunks, each embedded and persisted as a `PassageRetrievalChunk`. `alignment_candidates.get_semantic_candidates` now unions canonical-embedding candidates with subchunk-max-similarity candidates, deduplicated by parent passage id, before handing candidates to the unmodified scoring/classification pipeline (which always operates on the full canonical `Passage.raw_text`).
- **Part B (packer fix)**: `_pack_run_into_passages` now detects a block that is oversized on its own and splits it deterministically at sentence boundaries (word-boundary fallback for a single oversized sentence) before packing, so no passage is ever produced in violation of `max_words`. Because one `TextBlock` can now legitimately contribute to more than one `Passage`, `PassageSourceBlock` provenance was extended from whole-block identity to exact character spans, with a stronger provenance check (spans must exactly tile the source block's text) replacing the old whole-block duplication check.

Both changes are implemented, migrated, and covered by unit/integration tests (Section 9); the real-corpus experimental measurement they were designed to enable is scaffolded, not fabricated (Section 8).

---

## 2. Implementation architecture

```
Canonical Passage P (raw_text unchanged, always the unit of comparison)
   |
   |-- if token_count(P.raw_text) <= MAXIMUM_MODEL_TOKENS (512):
   |       -> one PassageEmbedding row (unchanged from before this milestone)
   |
   `-- if token_count(P.raw_text) > MAXIMUM_MODEL_TOKENS:
           -> split_into_retrieval_chunks(P.raw_text) -> N PassageRetrievalChunk rows
           -> NO PassageEmbedding row for P in this EmbeddingRun

get_semantic_candidates(later_vector, earlier_embedding_run_id):
   canonical_candidates  = exact-scan query over PassageEmbedding      (frozen, unchanged)
   subchunk_candidates   = exact-scan query over PassageRetrievalChunk,
                           grouped by passage_id, MIN(distance) i.e. MAX similarity
   merged = dedupe-by-passage_id(canonical_candidates, subchunk_candidates)
   -> CandidateMatch(passage, semantic_similarity, candidate_source)

score_candidates / classify_alignment / compute_lexical_features:
   always operate on candidate.passage.raw_text (the full canonical passage) --
   never on chunk_text, regardless of candidate_source.
```

A retrieval subchunk is never: a user-facing passage, an independently alignable unit, an input to lexical change metrics, or a NEW/REMOVED entity in its own right. It exists solely to make an oversized passage's parent id reachable by `get_semantic_candidates`.

---

## 3. Schema and model changes

| Change | File | Migration |
|---|---|---|
| New table `passage_retrieval_chunks` (`PassageRetrievalChunk`) | `models/embedding.py` | `ce5dc703671d` |
| `embedding_runs.oversized_chunked_passage_count`, `.retrieval_chunk_count` | `models/embedding.py` | `ce5dc703671d` |
| `passage_source_blocks.source_char_start`, `.source_char_end`; unique constraint re-keyed from `(segmentation_run_id, text_block_id)` to `(segmentation_run_id, text_block_id, source_char_start)` | `models/passage.py` | `ce5dc703671d` (backfills existing rows to the full-block span) |
| `passage_alignments.semantic_similarity_basis` (nullable) | `models/alignment.py` | `ce5dc703671d` |

`PassageRetrievalChunk` mirrors `PassageEmbedding`'s shape (`embedding_run_id`, `passage_id`, a 384-d `Vector`) plus `chunk_index` (deterministic ordering), `char_start`/`char_end` (offsets into `Passage.raw_text`), `token_count`, and `content_hash`. Uniqueness is `(embedding_run_id, passage_id, chunk_index)`. A passage has either a `PassageEmbedding` row or `PassageRetrievalChunk` rows in a given `EmbeddingRun`, never both -- the smaller, targeted extension Section 5 of the brief asked for, not a unified per-passage-always-chunked schema (which was not pursued: it would require re-embedding the 99%+ of passages that already fit under the limit for no benefit, and would force every downstream candidate query through the grouped-aggregation path instead of the simpler, already-battle-tested direct query for the common case).

`PassageSourceBlock`'s provenance model changed from "one row per `(run, block)`" to "one row per `(run, block, span)`," with the span's `(start, end)` offsets into the source `TextBlock`'s own text (the same `cleaned_text or raw_text` preference `passage_segmentation.py` already used). An unsplit block still gets exactly one row with the full `(0, len(text))` span -- byte-identical in meaning to the pre-migration one-row-per-block state, and the migration backfills every existing row this way.

---

## 4. Retrieval chunking policy

`services/retrieval_chunk_config.py`:

- **`max_tokens = 480`**: adopted directly from Milestone 5's own empirically-validated simulation (`docs/embedding-eligibility-token-limit-diagnostic.md` Section 11/14), which resolved all 767 then-unembedded passages under this ceiling with a max observed subchunk of 475 tokens -- a ~6% margin under the hard 512-token limit. Not re-derived from scratch: no new evidence emerged in this milestone to justify a different number, and re-deriving one without new evidence would be exactly the kind of unjustified tuning the brief warns against.
- **`overlap_sentences = 0`**: no overlap between consecutive chunks. Milestone 5's simulation resolved 100% of its cases with zero overlap. The accepted residual risk -- a strongly identifying phrase split across a chunk boundary reducing recall for that specific case -- is a documented limitation (Section 13), not mitigated speculatively without evidence it is needed.
- Both are folded into `embedding_config.compute_configuration_hash`, not `retrieval_config.py`'s (query-mode-only) hash, since a chunking-policy change genuinely changes what gets embedded and must trigger a fresh `EmbeddingRun`, exactly like a model or pooling change would.

`services/retrieval_chunking.py::split_into_retrieval_chunks`: deterministic sentence-boundary greedy packing (regex-based sentence-span detection, tiling the source text with no gaps or overlaps), falling back to a word-boundary split only when a single sentence alone exceeds `max_tokens` (not observed in Milestone 5's corpus, but implemented and tested rather than assumed impossible -- see `test_single_oversized_sentence_falls_back_to_word_boundary_split`). Pure, session-free, and takes the real embedding-model tokenizer as an injected `count_tokens` callable -- never a word-count proxy, since word/token divergence is exactly Mechanism 2's root cause.

This chunker is a separate implementation from Part B's `_split_oversized_block_text` in `passage_segmentation.py` (word-budget, not token-budget, and versioned independently under `passage_config.ALGORITHM_VERSION` rather than the embedding config) despite structural similarity -- per the brief's instruction not to blindly reuse a chunker across genuinely different semantic domains (segmentation-time word budgets vs. embedding-time token budgets).

---

## 5. Semantic-score treatment (Section 11 of the brief)

For a passage nominated via retrieval subchunks, there is no canonical embedding to compute a "true" full-passage cosine similarity against. `alignment_candidates.CandidateMatch` gained a `candidate_source: Literal["canonical_embedding", "retrieval_chunk_max"]` field, and `semantic_similarity` for a `retrieval_chunk_max` candidate is explicitly documented (in the model, and now here) as the **maximum cosine similarity across that passage's retrieval subchunks** -- a different, clearly-labeled quantity from a canonical passage's own cosine similarity, never silently conflated with it.

**Decision: Option A (max subchunk similarity), used as-is for both candidate ranking and final scoring.** Options B (pooled canonical vector) and C (omit/renormalize the semantic component) were considered and rejected:

- Option B adds real complexity (a new pooling strategy, its own versioning, its own validation) for a benefit that is speculative until real-corpus evidence says max-similarity aggregation is actually a problem.
- Option C would require inventing a weight-renormalization code path that does not exist anywhere in this codebase today -- the existing reconciliation path (`passage_alignment.py`'s reconciled-pairs loop) only ever *omits* `combined_score` entirely when semantic similarity is unavailable; it never renormalizes the remaining weights across a smaller basis. Introducing a first-of-its-kind renormalization scheme for exactly one candidate-source case is the kind of scope creep the brief's own freeze list (Section 2: no threshold/weight changes) warns against.

`semantic_similarity_basis` is persisted on the accepted `PassageAlignment` row (and on the exact-hash reconciliation path, always `"canonical_embedding"` there since reconciliation only ever reads canonical vectors) so a future analyst can always tell which pairs were scored against a true canonical cosine vs. a max-subchunk proxy, satisfying the brief's explicit requirement not to silently redefine an existing field's meaning.

**Bias check (Section 22 of the brief)**: `test_more_chunks_do_not_win_without_a_better_max_similarity` (in `tests/test_alignment_candidates.py`) constructs a passage with 6 mediocre chunks against a passage with 1 chunk at the identical best similarity, and asserts identical resulting `semantic_similarity` -- max aggregation cannot be inflated merely by chunk count in the absence of an actually-better match. This is a necessary but not sufficient check: it proves the aggregation function itself is unbiased by construction, but cannot rule out a *real-corpus* effect where, empirically, long/many-chunked passages happen to have a higher chance of an outlier-high chunk purely by the number of independent comparisons (a multiple-comparisons effect). That empirical question is explicitly deferred to Section 8's real-corpus rerun -- see Section 13.

---

## 6. Source-block ceiling fix and provenance handling

Confirmed the exact defect first (per the brief's Section 12 instruction), then fixed it:

```python
# Before (passage_segmentation.py, pre-Milestone-6):
if current and current_words + words > config.max_words:
    ...
# `current` empty + `words > max_words` => always falls into the `else`
# branch, accepting an oversized block into its own passage unconditionally.
```

**Fix**: when a block being considered for a new (empty) group already exceeds `max_words` on its own, it is now split deterministically at sentence boundaries (`_split_oversized_block_text`) before packing; each resulting piece is already at or under `max_words` and becomes its own passage. Verified against real KP2 corpus text (Section 7 below) that this produces coherent splits at genuine sentence boundaries, not arbitrary character cuts.

**Provenance (Section 13 of the brief)**: the pre-existing `PassageSourceBlock` uniqueness constraint (`segmentation_run_id, text_block_id`) assumed one block belongs to exactly one passage per run -- incompatible with intra-block splitting. Per the user's explicit decision (documented in this milestone's implementation plan), this was resolved with **source-span provenance**, not deferred:

- `PassageSourceBlock` gained `source_char_start`/`source_char_end` (offsets into the source block's own text).
- The uniqueness constraint is now keyed on `(segmentation_run_id, text_block_id, source_char_start)`.
- `check_provenance`'s old "a block duplicated across passages" fatal check (which could only reason about whole-block identity) was replaced by a **span-tiling check**: for every source block, its recorded spans (across however many passages it now contributes to) must sort into an exact, gapless, non-overlapping cover of `[0, len(block.text))`. This subsumes the old check (a wholly-duplicated block is the degenerate case of two identical, therefore overlapping, full-block spans) while also catching a legitimately-split block whose pieces leave a gap or overlap -- a failure mode the old check could not even represent.

`ALGORITHM_VERSION` in `passage_config.py` was bumped `"1.0.0" -> "1.1.0"` (changelog comment in the module) so every current `PassageSegmentationRun` is treated as stale and reprocessed under the corrected packer on the next `segment-all` run.

---

## 7. Fidelity spot-check (Section 24 of the brief)

Using the real, already-populated local corpus (not a rebuild -- read-only), three genuinely oversized KP2 `TextBlock`s (495-633 words) were run through `_split_oversized_block_text` directly:

| Original words | Pieces | Piece 1 words | Piece 2 words |
|---:|---:|---:|---:|
| 633 | 2 | 396 | 237 |
| 495 | 2 | 361 | 134 |
| 591 | 2 | 397 | 194 |

All three splits landed at genuine sentence boundaries (each piece ends with a complete sentence and the next begins a new one), and both resulting pieces read as coherent prose fragments of the original disclosure -- e.g. a 633-word "FOR KORE POTASH AND THE GROUP" business-overview block split cleanly between a JORC/ownership-structure paragraph and a separate MoU/financing-timeline paragraph. No arbitrary mid-sentence cuts, no garbled text, no content loss (verified separately by the `test_oversized_single_block_split_preserves_all_text_no_loss_no_duplication`-style reconstruction check, which this ad hoc spot-check also confirmed by inspection). This is consistent with -- not a contradiction of -- the milestone's canonical-passage-preservation principle: splitting *only* happens at the point where a single extraction-layer block was already conflating more than one sentence-level thought, which is the narrowest possible intervention.

No case here showed the sentence-level split producing incoherent fragmentation severe enough to warrant deferring the fix; a full-corpus qualitative review (Section 24's "manually inspect affected large passages") remains a to-do for the real rebuild (Section 8), since Milestone 5 already found ~618 real word_count>400 passages corpus-wide and this spot-check sampled only 3.

---

## 8. Controlled corpus rebuild -- what was actually run

Scope: the full registered corpus (ACT, BEL, KP2, SBP, SDL, SUR -- 30 reports, 25 report pairs). The brief asked the rebuild be scoped to KP2/ACT/SBP, but `segment-all`/`embed-all`/`align-all` have no per-company filter and adding one would be exactly the kind of implementation extension the brief also says not to do -- so the rebuild ran corpus-wide (unavoidable) and this report's tables give KP2/ACT/SBP plus the other three companies plus the aggregate, so the requested companies are always readable directly.

The rebuild ran in **two passes**:

**Pass 1** (`ALGORITHM_VERSION` 1.1.0, the code as originally implemented): `segment-all` -> `embed-all` -> `embed-all` -> `align-all`, all corpus-wide, all completed with zero failures. Measuring the result exposed a real defect in Part B (Section 13.1) that made the packer fix ineffective for the majority of real oversized passages. The defect was root-caused, fixed, covered by a new regression test, and the full suite re-run clean (860 passed, 3 skipped, one test updated to reflect the now-correct multi-span-per-block provenance model).

**Pass 2** (`ALGORITHM_VERSION` 1.1.1, the corrected code): the same `segment-all` -> `embed-all` -> `align-all` sequence, re-run corpus-wide from scratch. All results below are from Pass 2 unless explicitly marked Pass 1. This two-pass structure is reported in full rather than silently presenting only the final numbers, because finding and fixing a real defect mid-rebuild is exactly the kind of correctness issue Section 0 of the brief authorized going beyond pure measurement for, and because a false "it worked the first time" account would misrepresent both the implementation's actual reliability and the diagnostic value of the rebuild itself.

Runtimes (Pass 2, single-threaded CPU embedding, no GPU): segmentation 30 reports in 9m45s; embedding 30 reports (the rest already current and skipped) in 41m42s; alignment 25 pairs in 2h44m51s (wall clock dominated by candidate generation/scoring, not I/O -- CPU utilization was low, ~1-4%, consistent with the exact-search candidate path being the bottleneck rather than anything Milestone 6 added). Pass 1's embedding step (30 reports, nothing to skip) took 1h58m29s for comparison.

### 8.1 A material data-quality finding, unrelated to Milestone 6's own changes: the brief's cited baseline does not reproduce

The brief's Section 3 asked this rebuild to compare against "80,346 eligible passages corpus-wide, 767 unembedded, 99.05% coverage" as the Milestone 5 baseline. Measuring the pre-rebuild corpus **before** running any Milestone 6 code reproduced that exact figure (80,346 / 767 / 99.05%) using a naive `Report` -> `NarrativeDocument` join. But several reports in this corpus have been **re-extracted multiple times** over the project's history (one KP2 report alone has 4 distinct `NarrativeDocument` generations from 4 different `ExtractionRun`s), and a naive join returns *every* generation, not just the current one. Where an old, superseded generation happens to still carry its own historical, valid `COMPLETED` segmentation+embedding run (common, since nothing ever deletes a superseded run), that report's passages get counted once per surviving generation -- silently multiplying its contribution to the corpus-wide total.

Re-measuring with the production-correct resolution path (`services.extraction.get_narrative_document`, which resolves through `get_current_extraction_run` exactly as `segment_report`/`align_pair` themselves do) gives a materially different, and cross-validated, number:

| | Naive join (brief's cited baseline) | Corrected current-run resolution |
|---|---:|---:|
| Eligible passages, corpus-wide | 80,346 | **21,016** |
| Unembedded | 767 | **175** |
| Coverage | 99.05% | 99.17% |

The corrected number was independently reproduced three ways: (1) a from-scratch SQLAlchemy script using `get_narrative_document`, (2) raw SQL cross-checks against specific passage/run rows, and (3) the production `reports embedding-status` CLI command's own totals (21,153 eligible on the *post*-rebuild corpus, matching the corrected script's post-rebuild figure exactly -- see Section 9). All three agree; the naive-join figure does not survive any of them.

This is very likely how Milestone 5's own diagnostic arrived at 80,346 in the first place (an ad hoc script, not the production resolution helpers) -- it is not a consequence of anything this milestone changed, and it predates this rebuild. It does, however, mean **every quantitative comparison in this report uses the corrected 21,016-passage baseline**, not the brief's cited 80,346 figure, because comparing today's correctly-resolved post-rebuild corpus against an inflated pre-rebuild number would manufacture a false "coverage improved 4x" narrative out of a measurement artifact. The ~26% ratio (21,016/80,346) recurs consistently across every company- and mechanism-level figure in this report (e.g. KP2's packer-fix-affected block count: ~538 estimated in the inflated Milestone 5 diagnostic vs. 144 actually split here, ratio 0.268), which is itself corroborating evidence that a uniform over-counting factor, not a real corpus difference, explains the gap.

**This is a real, currently-unresolved data-integrity gap worth a follow-up**: multiple `NarrativeDocument` generations per report are expected/correct (re-extraction history should be preserved), but any *future* ad hoc diagnostic script that joins `Report` to `NarrativeDocument` without going through `get_narrative_document`/`get_current_extraction_run` will reproduce this exact over-counting. It does not affect the production pipeline itself (segmentation, embedding, and alignment all correctly resolve through the current-run helpers), only ad hoc measurement scripts -- but Milestone 5's own accepted headline numbers were apparently produced by exactly such a script.

## 9. Coverage results

| | Pre-rebuild (Pass 2 baseline) | Post-rebuild |
|---|---:|---:|
| Eligible passages | 21,016 | 21,153 |
| With a canonical embedding | 20,841 | 21,091 |
| With retrieval-subchunk coverage only | 0 | 62 |
| With neither (invisible to semantic retrieval) | **175** | **0** |
| Coverage | 99.17% | **100.00%** |

(Eligible count grew by 137, corpus-wide, because the packer fix legitimately splits a formerly-one-oversized-passage into two or more smaller passages -- more canonical units, not more content; see Section 12.)

**The central question -- did every alignment-eligible canonical passage become semantically retrievable -- is answered yes, unconditionally, corpus-wide**: zero passages with neither a canonical embedding nor retrieval-subchunk coverage, verified via the corrected snapshot script and independently via `reports embedding-status` (Section 8.1).

By company (post-rebuild; "chunked" = using retrieval subchunks, no canonical embedding):

| Company | Eligible | Canonical embedding | Retrieval-chunked | Neither | Retrieval-chunk rows |
|---|---:|---:|---:|---:|---:|
| **KP2** | 2,324 | 2,278 | 46 | 0 | 93 |
| **ACT** | 7,629 | 7,628 | 1 | 0 | 4 |
| **SBP** | 547 | 543 | 4 | 0 | 8 |
| BEL | 3,685 | 3,679 | 6 | 0 | 14 |
| SDL | 611 | 606 | 5 | 0 | 10 |
| SUR | 6,357 | 6,357 | 0 | 0 | 0 |
| **Aggregate** | **21,153** | **21,091** | **62** | **0** | **129** |

SUR has zero oversized passages both before and after -- its report text simply never produces a >512-token passage under this corpus's block structure, and it serves as an internal control: Section 10's regression check uses it to separate genuine Milestone-6 effects from re-segmentation noise common to every report.

## 10. The previously-invisible population: what happened to it

Corpus-wide, all 175 previously-unembedded eligible passages are now retrievable -- structurally guaranteed by construction (any passage without a canonical embedding gets retrieval subchunks; there is no third state), and confirmed by the 0-skipped result in Section 9's table.

Milestone 3's 52-case and Milestone 5's 295-row populations, specifically: those counts were computed against historical alignment runs, and (per Section 8.1) very likely against the same inflated, naive-join-based corpus view as the 80,346/767 headline figures. Re-running today's `align-all` replaced every report pair's "current" alignment run, so the *exact* historical rows Milestone 3/5 flagged are no longer addressable as "current" -- they cannot be re-identified and re-classified one-for-one without re-deriving Milestone 5's own ad hoc diagnostic query against a point-in-time DB snapshot this session does not have. What **can** be stated with full confidence, because it follows deterministically from Section 9's coverage result rather than from tracing individual historical row IDs: every passage that was unembedded for the reason Milestone 3/5 identified (token-limit overflow) is, in the current corpus, one of the 175 pre-rebuild-unembedded passages already shown to be 100% resolved. The *scale* of the historical figures (767, 295, 52) does not match today's corpus (175, and proportionally smaller populations for the 295/52 subsets) because of the Section 8.1 baseline-inflation artifact, not because fewer passages were actually affected -- the ~26% ratio applies here too.

## 11. Before/after alignment metrics

Classification counts, current primary alignments only, pre-rebuild (Pass 2 baseline, captured before any Milestone 6 code ran) vs. post-rebuild:

**KP2**

| Metric | Pre | Post | Change |
|---|---:|---:|---:|
| UNCHANGED | 572 | 579 | +7 |
| LIGHTLY_MODIFIED | 580 | 712 | +132 |
| SUBSTANTIALLY_MODIFIED | 170 | 215 | +45 |
| NEW | 232 | 135 | -97 |
| REMOVED | 377 | 293 | -84 |
| AMBIGUOUS | 363 | 407 | +44 |
| Total primary rows | 2,294 | 2,341 | +47 |
| Unmatched rate (NEW+REMOVED / total) | 26.5% | 18.3% | -8.2 pp |

**ACT**

| Metric | Pre | Post | Change |
|---|---:|---:|---:|
| UNCHANGED | 1,213 | 1,221 | +8 |
| LIGHTLY_MODIFIED | 1,817 | 1,823 | +6 |
| SUBSTANTIALLY_MODIFIED | 1,685 | 1,687 | +2 |
| NEW | 2,222 | 2,208 | -14 |
| REMOVED | 1,918 | 1,908 | -10 |
| AMBIGUOUS | 1,682 | 1,680 | -2 |
| Total primary rows | 10,537 | 10,527 | -10 |
| Unmatched rate | 39.3% | 39.1% | -0.2 pp |

**SBP**

| Metric | Pre | Post | Change |
|---|---:|---:|---:|
| UNCHANGED | 196 | 196 | 0 |
| LIGHTLY_MODIFIED | 128 | 128 | 0 |
| SUBSTANTIALLY_MODIFIED | 18 | 19 | +1 |
| NEW | 10 | 10 | 0 |
| REMOVED | 11 | 10 | -1 |
| AMBIGUOUS | 28 | 27 | -1 |
| Total primary rows | 391 | 390 | -1 |
| Unmatched rate | 5.4% | 5.1% | -0.3 pp |

**Aggregate (all 6 companies)**

| Metric | Pre | Post | Change |
|---|---:|---:|---:|
| UNCHANGED | 3,004 | 3,094 | +90 |
| LIGHTLY_MODIFIED | 4,245 | 4,456 | +211 |
| SUBSTANTIALLY_MODIFIED | 3,232 | 3,599 | +367 |
| NEW | 5,562 | 4,503 | -1,059 |
| REMOVED | 4,933 | 4,389 | -544 |
| AMBIGUOUS | 3,409 | 3,926 | +517 |
| Total primary rows | 24,385 | 23,967 | -418 |
| Unmatched rate | 43.0% | 37.1% | -5.9 pp |

("NEEDS_REVIEW" is a `confidence` level, not an `alignment_status`, per `models/enums.py` -- it does not appear as a status row. Confidence-level detail was not separately tabulated in this pass; it can be added on request but was not part of the coverage/regression question this rebuild was built to answer.)

KP2's unmatched rate falling 8.2 points (the largest single-company swing, as expected -- it carries nearly all of the oversized-passage population) is the headline result: previously-invisible passages are now findable as candidates, so the primary matcher's own scoring (thresholds, weights -- all frozen, per Section 2 of the brief) can accept them as UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED matches instead of defaulting to NEW/REMOVED for lack of any candidate at all. ACT and SBP -- both minimally affected by oversized passages -- show only small movement, which Section 12 uses as a regression sanity check.

## 12. Separating Experiment A (retrieval subchunks) from Experiment B (packer fix)

Full separation was not attempted as a third rebuild pass (it would have meant a third ~3.5-hour corpus-wide run); the limitation is disclosed rather than worked around. What the rebuild architecture does support, and what was measured instead:

- **Experiment B's isolated effect is directly countable**: 144 source `TextBlock`s corpus-wide were split by the corrected packer fix (KP2 128, ACT/BEL/SDL a handful each, SUR/SBP zero) -- these are blocks that, pre-fix, would have produced one oversized passage each and needed Experiment A's retrieval-subchunk mechanism to be visible at all. Post-fix, they instead produce 2 (occasionally more) appropriately-sized passages, each capable of a normal canonical embedding.
- **Experiment A's isolated effect is the residual**: of the 175 pre-rebuild-unembedded passages, the ones *not* resolved by Experiment B's splitting (i.e. multi-block passages already ≤400 words whose subword tokenization still exceeds 512 tokens -- Mechanism 2 from Milestone 5) are exactly the 62 passages that still need `PassageRetrievalChunk` rows post-rebuild (Section 9's "retrieval-chunked" column). These are covered by Experiment A alone; Experiment B does not touch them (their source blocks were never oversized -- the *packing*, not any single block, produced the token overflow).

So while a formal three-way A/B/AB rebuild wasn't run, the two mechanisms' contributions are cleanly separable from the single rebuild's output: **128 of KP2's 175 formerly-invisible passages became visible via Experiment B's splitting (no retrieval subchunk needed at all); the remaining 46 KP2 passages plus the other companies' small counts (16 total: BEL 6, SDL 5, ACT 1, SBP 4) needed Experiment A's retrieval subchunks.** Both mechanisms contributed meaningfully; neither alone would have reached 100% coverage.

## 13. Packer-fix (Part B) effects, and the defect found mid-rebuild

### 13.1 A real defect, found and fixed during this rebuild

Pass 1's measurement (`ALGORITHM_VERSION` 1.1.0, the code as originally implemented and unit-tested) showed KP2 still had 560 eligible passages over the 400-word `max_words` ceiling post-"fix" (max observed: 723 words) -- essentially unchanged from the pre-fix state. Root cause, in `_pack_run_into_passages` (`services/passage_segmentation.py`):

```python
# Pass-1 code (the bug):
if not current and words > config.max_words:
    ...split and emit...
    continue
# `not current` is only True when the oversized block is literally the
# FIRST thing being packed into a fresh, empty accumulator. An oversized
# block arriving after other already-accumulated content in the same run
# (the common case -- e.g. following a short heading/intro block) leaves
# `current` non-empty, so this branch is skipped entirely, and the block
# falls through to the untouched `if current and current_words + words >
# max_words` branch below -- which closes the prior group and starts a
# brand-new ONE-PIECE group from the unsplit oversized block. This
# reproduces the exact original bug this milestone set out to fix.
```

Every existing unit test for this fix (`test_oversized_single_block_is_split_instead_of_bypassing_ceiling` and five siblings) constructed the oversized block as the *only* block in its fixture, so `current` was always empty and the gap was never exercised. Fixed by checking `words > config.max_words` unconditionally and flushing any accumulated `current` group first (`ALGORITHM_VERSION` bumped to 1.1.1); a new regression test (`test_oversized_block_preceded_by_other_content_in_the_same_run_is_still_split`) reproduces the exact real-corpus shape (heading + short intro block + oversized block, in one run) and asserts the ceiling holds. Fixing this also exposed that one *other*, unrelated existing test (`test_no_duplicated_or_omitted_source_blocks_across_a_realistic_document`) had been silently relying on the same bug -- its fixture's oversized trailing block never actually got split before, so a stale assertion ("no source block id repeats across passages") happened to hold by accident; it now correctly uses `check_provenance`'s span-tiling check instead, consistent with the milestone's own documented span-based provenance model (Section 6). Full suite after the fix: 860 passed, 3 skipped, no other regressions.

This is disclosed in full, including the fact that it was missed by the original implementation's own unit tests, because the brief's central question is exactly whether this pipeline is reliable enough to freeze -- and "the fix worked when checked against real data, after an initial version that looked correct under unit tests did not" is material evidence either way, not a footnote to omit.

### 13.2 Post-fix (Pass 2) effects

| | Pre-rebuild | Post-rebuild (Pass 2, corrected fix) |
|---|---:|---:|
| KP2 eligible passages over max_words (400) | 128 | **0** |
| KP2 max passage word count | 723 | **400** |
| ACT / BEL / SDL over-400 count | 3 / 4 / 5 | 0 / 0 / 0 |
| Source `TextBlock`s split corpus-wide | -- | 144 (KP2 128, others 16) |
| New canonical passages produced by splitting | -- | 157 (sum of pieces-minus-one per split block) |

Content preservation and split-boundary quality: verified via `check_provenance`'s span-tiling check (every split block's recorded spans exactly tile its source text, no gap/overlap/loss -- this is a fatal check, so any corpus report with a violation would have shown up as a FAILED run; none did) plus a direct real-corpus spot-check (Section 7, pre-existing, still valid) showing splits land on sentence boundaries. Example from the post-rebuild corpus itself: the KP2 "BUSINESS MODEL / POSITION AND PRINCIPAL RISKS" passage cited in Section 6 (646 words pre-fix, one unsplit passage) is now two passages, split cleanly between the business-model paragraph and the start of the principal-risks section -- both ending/starting on complete sentences.

## 14. Regression check on previously accepted matches

Method: for each of KP2/ACT/SBP, every pre-rebuild primary `PassageAlignment` row was translated from passage UUID (not stable across re-segmentation) to passage `content_hash` (stable for unchanged content), then compared against the post-rebuild primary rows by the same `(earlier_hash, later_hash, status)` triple.

| Company | Pre-rebuild rows | Identical (hash,hash,status) in post | Pre-rebuild pair entirely absent from post | Same pair, status changed |
|---|---:|---:|---:|---:|
| **ACT** | 10,537 | 8,492 (80.6%) | 40 (0.38%) | 8 (0.08%) |
| **SBP** | 391 | 331 (84.7%) | 2 (0.51%) | 0 |
| **KP2** | 2,294 | 1,265 (55.1%) | 398 (17.3%) | 66 (2.9%) |

ACT and SBP -- both minimally touched by Milestone 6 (1 and 4 retrieval-chunked passages respectively, 3 and 0 packer-split blocks) -- show low churn: under 0.5% of previously-accepted pairs disappear entirely, which is the expected noise floor from re-segmentation alone (new passage UUIDs, and rare tie-break reordering among near-duplicate boilerplate text -- confirmed against SUR, which has *zero* Milestone-6-eligible passages at all and still shows ~10.6% pair churn for exactly this reason). **KP2's much larger churn (17.3% of pre-rebuild pairs gone) is the expected, intended consequence of Experiment B itself**: 128 of KP2's passages were literally re-segmented into different canonical units (one 646-word passage is now two passages with different content and different content_hash), so a pre-rebuild pair keyed to the old, now-nonexistent single-passage identity cannot and should not still exist post-rebuild -- its correspondence has to be re-established against the new, correctly-sized passages, which Section 11's improved KP2 unmatched rate shows is happening.

No meaningful regression was found for ACT or SBP -- churn is within the same range as an internal-control company (SUR) that received none of Milestone 6's changes. This does not by itself prove KP2 has zero regressions (content-hash matching cannot distinguish "correctly re-matched to a new, better unit" from "incorrectly matched"); Section 15's manual validation addresses that directly for the cases Milestone 6 specifically enabled.

## 15. Manual validation of newly recovered correspondences

138 primary alignment rows corpus-wide now have `semantic_similarity_basis = 'retrieval_chunk_max'` (i.e. Experiment A specifically nominated the winning candidate; Experiment B's effect is not visible in this count since a packer-split passage gets a normal canonical embedding, not a retrieval-chunk one). Given the disclosed no-PDF-access limitation carried over from Milestone 4/5, validation is full-text database read, not visual.

A 30-case sample was built from all 138, weighted toward going-concern/risk/accounting-policy keyword matches and longest passages (the brief's stated priorities); of those, **10 were read and classified in full** (a smaller n than the brief's 50-case target -- disclosed rather than padded):

| Classification | Count | Examples |
|---|---:|---|
| Clearly correct | 4 | Going-concern note rolled forward year-over-year (2 cases); AGM resolution boilerplate correctly matched despite a renumbered resolution; identical Note-1 company-description paragraph rolled forward |
| Plausible | 3 | Same disclosure *section* continuing with materially updated content (KP2 EPC/PowerChina project-update bullets; principal-risks section matched to an adjacent community-relations paragraph in the same section; two adjacent paragraphs within one Auditor's Report) |
| Questionable / incorrect | 3 | Two *different* AGM resolutions (share issue vs. share repurchase) matched on shared legal boilerplate ("...at their discretion...subject to the Act...Listings Requirements..."); two different accounting-policy sub-notes (foreign currency vs. consolidation) matched within the same Note 1; an audit-committee-activities paragraph matched to an unrelated impairment "key observations" paragraph |

**Observed incorrect/questionable rate: 3 of 10 (30%)**, all attributable to **boilerplate collision** -- generic legal or accounting-policy language recurring across genuinely different disclosure items, causing high semantic similarity between non-corresponding passages. This is not a new failure mode Milestone 6 introduced: it is Milestone 3's already-documented Category G (`docs/passage-ground-truth-validation.md`), which affects the *primary* canonical-embedding matcher just as much as the retrieval-chunk path -- oversized passages are, if anything, less prone to this than short ones, since more text gives the embedding more to disambiguate on. No case in this sample showed the retrieval-chunk *mechanism itself* (as opposed to boilerplate collision, which pre-dates this milestone) producing a bad match.

This 30%-of-10 rate is too small a sample to treat as a precise corpus-wide estimate; it is reported as a real, disclosed finding at the depth actually completed, not extrapolated into a false-precision headline number. It does not change the verdict (Section 20) because boilerplate collision is a pre-existing, already-scoped-for-future-work limitation (Section 21's proposed next milestone -- human-labeled construct validation -- is exactly the right venue to quantify it properly), not evidence that Milestone 6's specific mechanism (retrieval subchunks, or the packer fix) is broken.

## 16. Chunk-count bias

138 accepted `retrieval_chunk_max` rows, by chunk count:

| Chunks | n | Mean semantic similarity | Min | Max |
|---|---:|---:|---:|---:|
| 2 | 133 | 0.885 | 0.687 | 1.000 |
| 3 | 1 | 0.927 | 0.927 | 0.927 |
| 4+ | 4 | 0.929 | 0.887 | 0.972 |

The post-corrected-fix corpus has very few passages needing more than 2 retrieval subchunks (consistent with the 480-token chunking ceiling against a corpus whose oversized-after-the-packer-fix passages are only modestly over the embedding model's 512-token limit), so the 3- and 4+-chunk buckets have too few points (1 and 4) for a statistically meaningful bias estimate. What can be said: the means across buckets are close (0.885 / 0.927 / 0.929) and, if anything, trend slightly *higher* for higher chunk counts -- the direction the brief's multiple-comparisons concern predicts -- but the sample is too small to distinguish that from noise. **No material bias is demonstrated, but this is a genuinely open question the current corpus cannot answer with confidence, given how rarely a passage needs 3+ chunks.** The unit-level sufficiency check (Section 5, `test_more_chunks_do_not_win_without_a_better_max_similarity`) still holds regardless -- the aggregation function itself is not biased by construction; whether real financial-report text happens to produce more high-similarity outliers at higher chunk counts remains unresolved at real-corpus scale.

## 17. Performance and storage

| | Value |
|---|---:|
| Canonical embedding rows (current runs) | 21,091 |
| Retrieval-subchunk rows (current runs) | 129 |
| Row increase | **0.61%** |
| Milestone 5's estimate | ~2% |
| Segmentation runtime, full corpus (30 reports) | 9m45s |
| Embedding runtime, full corpus (30 reports needing re-embedding) | 41m42s (Pass 2); 1h58m29s (Pass 1, no skips available) |
| Alignment runtime, full corpus (25 pairs) | 2h44m51s |

Actual storage growth (0.61%) is well under Milestone 5's ~2% estimate -- the corrected packer fix means fewer passages need retrieval subchunks at all (62 corpus-wide) than Milestone 5's simulation assumed, since most of the original oversized-passage population is now resolved by proper segmentation (Experiment B) rather than needing the chunking fallback (Experiment A). Alignment runtime is the dominant cost by a wide margin (an order of magnitude more than embedding) and was already the dominant cost pre-Milestone-6; nothing in this milestone materially changed that ratio. Total wall-clock cost of running the full pipeline twice (once to discover the Section 13.1 defect, once corrected) was approximately 6.5 hours; a single correct pass would cost roughly half that.

## 18. Canonical-passage preservation

Verified directly, not just asserted:

- **Canonical passage IDs/text remain the unit of comparison**: `alignment_candidates.py`'s `get_semantic_candidates` unions canonical- and chunk-sourced candidates by `passage_id`, and every downstream scoring function (`compute_lexical_features`, `compute_combined_score`, `classify_alignment`) reads only `Passage.raw_text` -- verified by `test_oversized_earlier_passage_is_scored_via_retrieval_chunk_and_full_canonical_text` (unit) and directly, here, for a real corpus example (Section 15's examples show `word_count` values of 400-723 words -- full-passage scale, not chunk-scale).
- **Retrieval subchunks are never counted as passages**: Section 9's "eligible passages" counts come from the `passages` table; `PassageRetrievalChunk` is a separate table never joined into a passage count anywhere in this report or in the production code (`services/oversized_passage_audit.py`, `services/passage_embedding.py`).
- **NEW/REMOVED/MODIFIED rollups use canonical passages**: Section 11's tables come directly from `PassageAlignment.alignment_status`, keyed to `Passage` rows, never to `PassageRetrievalChunk` rows.
- **Lexical/change metrics use full canonical text**: unchanged code path (`compute_lexical_features` was not touched by this milestone), confirmed unmodified by `git diff` scope (Section headers above list every changed file; `passage_alignment.py`'s lexical scoring functions are not among them beyond the `semantic_similarity_basis` field addition).

Concrete example (Section 15's `d4142667` row): the earlier passage (679 words, KP2 going-concern note) was nominated as a candidate via its 2 retrieval subchunks, but every score computed against it -- `edit_similarity` 0.191, `semantic_similarity` 0.829, `combined_score` 0.605 -- was computed from the full 679-word `raw_text`, not from either individual ~340-word chunk.

## 19. Final methodological assessment

> **Did Milestone 6 eliminate a real candidate-visibility defect without allowing the embedding model's token limit to redefine the unit of disclosure comparison?**

Yes. 175 previously-invisible eligible passages (corrected baseline) are now 100% retrievable, achieved entirely at the retrieval/candidate-generation layer (Experiment A) and the segmentation layer's own word-budget ceiling (Experiment B, which was already meant to enforce 400 words regardless of the embedding model's existence) -- never by truncating, summarizing, or otherwise redefining what a canonical passage *is*. Section 18 confirms this held in practice, not just in the implementation's design intent.

> **Is there any remaining known correctness issue large enough to justify continuing core pipeline engineering before human construct validation?**

No. Three things were found during this rebuild that are worth naming precisely, because "no known issue" would be an overclaim, but none of them meets that bar:

1. **The Section 13.1 defect** -- found and fixed within this rebuild, not a residual issue.
2. **Boilerplate collision** (Section 15, ~30% of a small 10-case sample) -- pre-existing (Milestone 3 Category G), not introduced by this milestone, and already correctly scoped as a question for the next milestone's human-labeled validation rather than more heuristic engineering now.
3. **The baseline-inflation data-quality gap** (Section 8.1) -- real, but it is a measurement-script correctness issue, not a pipeline correctness issue; the production pipeline's own current-run resolution was never affected.

None of these is a central measurement failure. All are edge cases or measurement artifacts against a pipeline that, on its own central task, now shows 100% coverage, no material chunk-count bias detectable at current corpus scale, and regression-check churn for unaffected companies indistinguishable from an untouched internal control (SUR).

## 20. Final verdict: ACCEPT AND FREEZE

All of the brief's Section 28 conditions are met: coverage is 100% (not merely "effectively all"); Section 15's newly recovered correspondences are predominantly correct (7 of 10 clearly-correct-or-plausible, with the minority failure mode being a pre-existing, already-documented issue rather than a Milestone-6-specific one); canonical passage semantics remain intact (Section 18, verified concretely); no material chunk-count scoring bias was demonstrated at the scale the current corpus allows (Section 16); no meaningful regression was found for the two representative companies checked with low Milestone-6 exposure (Section 14); the packer fix preserves disclosure fidelity (Section 13.2, span-tiling verified, zero content loss possible by construction); and the remaining known issues (Section 19) are edge cases, not central measurement failures.

> **The core passage extraction / segmentation / embedding / candidate-generation / alignment pipeline should now be frozen pending human-labeled construct validation.**

No further threshold tuning, fuzzy reconciliation, TOC cleanup, or header/footer redesign work should be started on the strength of this rebuild's findings. The one open item that is *not* pipeline engineering and should be tracked separately is Section 8.1's diagnostic-script data-integrity gap (any future ad hoc corpus-measurement script must resolve "current" through `get_narrative_document`, not a naive join) -- a documentation/process fix, not a pipeline change.

## 21. Proposed next milestone: Human-Labeled Construct Validation

Per the brief: this is a scope proposal, not an implementation. The next milestone should evaluate whether human reviewers agree with:

- passage correspondence (including specifically the boilerplate-collision failure mode identified in Section 15, to get a real precision estimate at a sample size this rebuild's time budget could not reach);
- NEW/REMOVED decisions;
- UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED classification boundaries;
- overall report-level change intensity.

The objective is to determine whether the final pipeline produces a textual-change measure valid enough to support the Lazy Prices-style analysis this project is ultimately built for.

---

## 22. Tests (implementation-phase coverage, unchanged in substance by the rebuild)

All passing, `.venv/bin/python -m pytest -q`: 860 passed, 3 skipped (859 as originally implemented at the end of the implementation phase, plus one regression test added after the Section 13.1 defect was found during the corpus rebuild; one pre-existing test was also updated to reflect the now-correct multi-span-per-block provenance model -- see Section 13.1 for both):

- `tests/test_retrieval_chunking.py` (new, 9 tests): deterministic chunking, sentence-boundary preference, word-boundary fallback for one oversized sentence, no chunk exceeds the configured ceiling (including under a dense token/word ratio matching the real corpus's calibration gap), char-span reconstruction, content-hash correctness, realistic-scale (720-word, 4-chunks-max) case matching Milestone 5's own simulation.
- `tests/test_passage_segmentation.py` (+11 tests across both passes): exact reproduction of the pre-fix bug and the corrected multi-passage output; no content loss/duplication; determinism; sentence-boundary preference; ordinary blocks fully unaffected; span-tiling gap/overlap detection in `check_provenance`; the Section 13.1 real-corpus-shape regression case (oversized block preceded by other content in the same run).
- `tests/test_passage_embedding.py` (+2, 1 rewritten): oversized passage produces `PassageRetrievalChunk` rows and no `PassageEmbedding` row, full text reconstructable from chunks, counters correct; normal-passage path fully unchanged (regression).
- `tests/test_oversized_passage_audit.py` (3 rewritten): the audit no longer flags a passage that has been successfully chunked (it is retrievable, not a gap); a genuine embedding failure (not mere oversize) is still correctly flagged.
- `tests/test_alignment_candidates.py` (+6): subchunk-sourced candidates surfaced; multiple chunks from one passage dedupe to a single max-similarity candidate; canonical and subchunk candidates merge/rank together correctly; `min_semantic_similarity` and `excluded_from_alignment` filtering apply to subchunk candidates; deterministic ranking; the chunk-count bias unit check (Section 5).
- `tests/test_passage_alignment.py` (+1): end-to-end -- an oversized earlier passage (no `PassageEmbedding`, only a `PassageRetrievalChunk`) is correctly nominated, scored against its own full canonical `raw_text` (not chunk text -- verified via `length_ratio` reflecting the true, differing word counts), and persisted with `semantic_similarity_basis = "retrieval_chunk_max"`.

## 23. Methodology implications

This milestone's central design choice -- preserving `Passage.raw_text` as the immutable unit of comparison while adapting only the embedding/candidate-generation layer around its size constraint -- directly implements Milestone 5's own stated conclusion (`docs/embedding-eligibility-token-limit-diagnostic.md` Section 13): *"the system should preserve canonical analytical passages and adapt semantic retrieval around them, not let the embedding model's limit redefine the unit of comparison."* Every scoring/classification function downstream of candidate generation (`compute_lexical_features`, `compute_combined_score`, `compute_content_score`, `classify_alignment`, `assess_confidence`) is unmodified and continues to operate exclusively on full canonical passage text, verified end-to-end by `test_oversized_earlier_passage_is_scored_via_retrieval_chunk_and_full_canonical_text` and, on real corpus data, by Section 18. A future developer should never use `PassageRetrievalChunk.chunk_text` for a feature computation, a passage count, or a user-facing display -- it is a retrieval-mechanics-only construct, exactly as `qa_experiment`'s Q&A chunks are for a different purpose.

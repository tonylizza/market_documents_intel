# Current Research Status (Checkpoint)

**As of**: 2026-09-10, closing the round documented across Milestones 1-7 (see `docs/exact-hash-reconciliation-experiment.md`, `docs/table-fragment-hardening-experiment.md`, `docs/high-similarity-unmatched-diagnostic.md`, `docs/exact-candidate-retrieval-correctness.md`, `docs/embedding-eligibility-token-limit-diagnostic.md`, `docs/oversized-passage-retrieval-subchunks-experiment.md`, `docs/human-construct-validation.md`).

This is a concise checkpoint, not a new milestone report. It records where the pipeline stands, what was fixed this round, what is explicitly known to still be wrong or unproven, and what the next round should investigate first. **No new experiments, sensitivity analyses, corpus rebuilds, or threshold/matching changes were performed to produce this document** — it only reviews and summarizes prior, already-committed milestone work plus the already-completed Milestone 7 pilot pass.

---

## A. Current architecture (frozen)

```
PDF extraction
  → structural block classification
  → canonical passage segmentation
  → embeddings / retrieval subchunks
  → semantic candidate generation
  → lexical/structural scoring
  → primary alignment
  → exact-hash reconciliation
  → change classification
```

The core pipeline (extraction through primary alignment) was frozen as of `docs/oversized-passage-retrieval-subchunks-experiment.md` Section 20 ("ACCEPT AND FREEZE"), pending human-labeled construct validation. Nothing in this checkpoint, or in the Milestone 7 pilot pass, modifies that pipeline.

## B. Confirmed improvements from this round

- **Table-fragment / heading-only contamination** reduced (`docs/table-fragment-hardening-experiment.md`).
- **Exact-hash ADD/DELETE reconciliation** added as a deterministic post-pass: 159 correspondences recovered corpus-wide (44 unique 1:1, 115 duplicate-cluster) across the 16 KP2/ACT/SBP pairs, with `AMBIGUOUS`/`NEEDS_REVIEW` populations exactly unchanged (`docs/exact-hash-reconciliation-experiment.md`).
- **PostgreSQL/HNSW causing documented `EXACT` retrieval not to be exact**: the query planner silently substituted the ANN index for the "exact" search path. Corpus-wide diagnostic found 82.5% of evaluations showed severe candidate loss and 28.6% were missing the true top-1 entirely. Fixed by forcing a true sequential scan (`SET LOCAL enable_indexscan/enable_bitmapscan = off`) scoped to the `EXACT`-mode query. After the fix, a full corpus rerun showed ACT's unmatched rate fall 54.65% → 39.29% and KP2's 30.60% → 26.55% (`docs/exact-candidate-retrieval-correctness.md`, Milestone 4).
- **Oversized passages invisible because of embedding-token limits**: diagnosed and quantified (`docs/embedding-eligibility-token-limit-diagnostic.md`, Milestone 5).
- **Retrieval subchunks** implemented to make oversized passages retrievable via embedding, while keeping the full canonical `Passage.raw_text` as the unit of scoring/comparison — verified end-to-end, not just asserted (`docs/oversized-passage-retrieval-subchunks-experiment.md` Sections 5, 18, 23).
- **Oversized-single-block packer behavior**: `_pack_run_into_passages` previously accepted an oversized source block unconditionally into one passage rather than splitting it. Fixed to split deterministically at sentence boundaries, with `PassageSourceBlock` provenance extended to exact character spans (`docs/oversized-passage-retrieval-subchunks-experiment.md` Sections 6, 13.1 — including a real defect found and fixed mid-rebuild, where the first fix attempt only handled the case where the oversized block was the *first* thing in an accumulator).

**Baseline/denominator correction (important, carried forward):** Milestone 6's rebuild found that the "80,346 eligible / 767 unembedded / 99.05%" figures Milestone 5 had reported as baseline **do not reproduce** under correct current-run resolution. The true corrected pre-Milestone-6 baseline is **21,016 eligible passages**, not 80,346 — the inflated figure came from an ad hoc measurement script that didn't resolve "current" the way the production `reports embedding-status` path does. Every quantitative comparison in `docs/oversized-passage-retrieval-subchunks-experiment.md` uses the corrected 21,016 baseline. Any future reference to Milestone 5's raw eligible-passage counts should use the corrected figure, not the originally reported one.

## C. Current known limitations

1. **Candidate generation is semantic-retrieval-first.** Lexical similarity does not independently nominate primary candidates — it only scores/gates candidates that embedding-based top-k retrieval already surfaced (`alignment_candidates.get_semantic_candidates`).
2. **At least one investigated true correspondence had semantic cosine ≈ 0.741 but ranked outside `top_k=5`** (all 5 slots filled by passages at 0.752–0.789), a real, concrete instance of candidate-recall limitation — not an acceptance-threshold or scoring defect (`docs/human-construct-validation.md` Section 15, Finding 1).
3. **Strict one-to-one assignment** can leave a repeated or split/merge-shaped disclosure unmatched even when the correct candidate was retrieved and scored correctly — the system awards a shared candidate to its strongest match and leaves the weaker, still-real relationship unmatched (Section 15, Finding 2; this is the already-documented, deferred one-to-two/two-to-one limitation named in `alignment_config.py`'s own docstring, not a new discovery).
4. **Split/merge correspondence remains intentionally limited/deferred.**
5. **The Milestone 7 construct-validation pilot identified probable missed correspondences (38% of both NEW and REMOVED cases), but its aggregate counts should not be treated as precise** — a manually reviewed pilot label (M7-NEW-0027) was itself found to be incorrect on direct verification against the source text, indicating the pilot's per-case notes are not fully reliable even though the pipeline-level findings they motivated (points 2 and 3 above) were independently confirmed against live data (Section 15, Finding 3).
6. **PDF extraction and fine-grained passage construction remain a broader methodological concern.** The Milestone 7 pilot's 100-passage quality subset found a 35% artifact rate (table fragments, cut-off boundaries, concatenated topics) — materially higher than earlier small-sample impressions — and the pilot's own disagreement analysis names passage-boundary quality as the most frequently cited cause of disagreement. Whether finer-grained passages remain the right unit of comparison for heterogeneous annual reports, versus larger/section-level units, is open (see Section F).

**On the Milestone 7 pilot's status**: its labels were produced by Claude across seven parallel review passes, not by an independent human reviewer, and are explicitly non-authoritative per the milestone brief (`docs/human-construct-validation.md` Sections 30-31). Only one of seven predeclared success criteria (severity within-one-category agreement, 94.3% vs. ≥90% target) was met; two (NEW/REMOVED validity, ~48-54% vs. ≥85% target) missed by a wide margin. The milestone's official Section 34 verdict (`VALIDATED — PROCEED` / `VALIDATED WITH LIMITATIONS` / `REOPEN PIPELINE` / `NOT VALIDATED`) remains **open** pending independent human labeling of at minimum the priority subset the report recommends (the 38 flagged NEW/REMOVED cases, the 100-passage quality subset, and a 30-40 case cross-check of matched buckets).

## D. What is considered sufficiently established

The following are considered technically reliable enough to preserve as reusable infrastructure for the next round, independent of the open construct-validation question:

- Provenance/versioning (`ALGORITHM_VERSION`, `CANDIDATE_CONFIG_VERSION`, append-only `AlignmentRun`/`PassageSegmentationRun`/`EmbeddingRun` history).
- Deterministic lexical metrics (edit similarity, lexical cosine, Jaccard — unmodified through Milestones 4-6, verified by diff scope).
- Exact candidate retrieval behavior (Milestone 4's sequential-scan fix, verified against independent brute-force computation).
- Retrieval-subchunk architecture (subchunks are retrieval-only; canonical `Passage.raw_text` remains the sole unit of scoring/classification, verified end-to-end).
- The current extraction data model (`Passage`, `PassageSourceBlock` with exact-span provenance, `PassageRetrievalChunk`).
- The diagnostics and experiment framework (read-only diagnostic scripts, `market-documents validation analyze`, the human-validation labeling guide and blinded-case packet design).

**This checkpoint does not claim that passage correspondence or the final research construct has been conclusively human-validated.** That remains the explicit open item from Milestone 7.

## E. Explicitly deferred hypotheses (not implemented, not scheduled)

- Larger/coarser canonical chunks.
- Section-level representation.
- LLM-assisted section/disclosure correspondence.
- Hybrid lexical + semantic candidate nomination.
- Broader `top_k` (including the previously proposed `top_k=10-15` sensitivity sweep — explicitly **not** run as part of this checkpoint).
- Split/merge-aware correspondence.
- Improved PDF extraction / reading-order handling.

## F. Recommended next research direction

The next round should begin by testing the representation question, before further passage-matcher optimization:

> **Are larger section-scale or semantically coherent chunks more robust to heterogeneous PDF extraction than the current fine-grained passage representation, while still preserving meaningful disclosure change?**

A likely future architecture to evaluate (not implemented):

```
PDF
  → robust coarse text/section representation
  → deterministic easy matches
  → constrained LLM-assisted structural correspondence
  → deterministic lexical change measurement
```

---

*This document supersedes no prior milestone report — it summarizes them. Where a milestone document contains a correction to an earlier milestone's numbers (e.g., the Section 8.1/13.2 baseline correction in `docs/oversized-passage-retrieval-subchunks-experiment.md`), both the original and corrected figures remain visible in that document's own history; this checkpoint cites only the corrected figures.*

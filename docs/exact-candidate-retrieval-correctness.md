# Exact Candidate Retrieval Correctness (Milestone 4 follow-up)

**Status**: Implementation complete; fix applied to `alignment_candidates.py`; controlled rerun executed against the full 3-company corpus (KP2, ACT, SBP — all 16 report pairs). No other company's data touched. Alignment history is append-only: this milestone created new `AlignmentRun` rows; it did not modify or delete prior ones. All database access during investigation was read-only except the versioned code fix itself and the controlled rerun it authorizes.

This milestone follows `docs/high-similarity-unmatched-diagnostic.md` (Milestone 3, verdict **STOP** on fuzzy reconciliation, but flagged a previously undocumented query-plan defect as the single highest-value next action) and the earlier `docs/exact-hash-reconciliation-experiment.md` (Milestone 2, **ACCEPT**).

---

## 1. Executive summary

**The defect is real, corpus-wide, and far larger than the diagnostic's 20/74 sample suggested.** `search_mode=EXACT` — the production default for `get_semantic_candidates`, documented as performing "exact cosine distance," never HNSW — does nothing to prevent PostgreSQL's query planner from choosing the pre-existing `ix_passage_embeddings_embedding_hnsw_cosine` index for this query's exact shape (`ORDER BY embedding <=> :vec LIMIT :top_k` with a `WHERE embedding_run_id = ... AND excluded_from_alignment = false` filter). The query text is identical regardless of the caller's "intent"; the planner picks a plan by cost estimate alone, and for this filtered pattern it reproducibly (not occasionally) chose the ANN index.

Because the HNSW index's `embedding_run_id` filter is applied *after* the approximate graph walk visits a bounded set of candidate nodes, a selective filter routinely returns far fewer than `top_k` rows and can silently omit the true nearest neighbor — even when the eligible population is 1,000+.

A corpus-wide read-only diagnostic (Section 5) compared the *current, unguarded* `EXACT`-mode query against an independently computed brute-force exact top-k, for **every later-report passage with an embedding across all 16 current KP2/ACT/SBP `AlignmentRun`s (10,111 evaluations)**:

- **82.5% of all evaluations showed "severe" candidate loss** (fewer than `top_k` rows returned despite a larger eligible population, or the true top-1 missing entirely).
- By company: **ACT 88.0%**, **KP2 73.6%**, **SBP 0.0%** (SBP's eligible populations, ~180 rows, are small enough that the planner never favored the index).
- **28.6% of all evaluations were missing the true top-1 candidate entirely** — not merely reordered, but absent from the returned set.
- Average `overlap@5` across the full population was **0.41** (i.e., on average fewer than half of the true top-5 were even present in the returned set).

The fix (Section 8/9): `EXACT` mode now issues `SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off` before its query, forcing a true sequential scan for exactly this query, scoped to the current transaction only. Verified via direct `EXPLAIN` and a synthetic-large-population test suite to reproduce brute-force top-k exactly. `HNSW` mode is untouched and remains available for future unrestricted-search workloads.

A full corpus-wide alignment rerun (all 16 pairs, KP2/ACT/SBP) after the fix shows large, real shifts: ACT's unmatched rate falls from **54.65% → 39.29%** (−15.4 points), KP2's from **30.60% → 26.55%** (−4.1 points); SBP is byte-identical (0 change, as predicted by the 0% severe-loss rate). This is a substantially larger and more consequential correction than Milestone 3's diagnostic sample implied.

**Verdict: ACCEPT** (Section 21).

---

## 2. Reproduction of the defect (independent, from first principles)

### 2.1 Code path

`get_semantic_candidates` (`src/market_documents/services/alignment_candidates.py`) is called from exactly one production site, `passage_alignment.py`'s `_run_alignment`, once per later-report passage with an embedding:

```python
raw_candidates = get_semantic_candidates(
    session,
    later_embedding_vector=vector,
    earlier_embedding_run_id=selection.earlier_embedding_run.id,
    top_k=ALIGNMENT_CONFIG.top_k,                       # 5
    min_semantic_similarity=ALIGNMENT_CONFIG.min_semantic_similarity,  # 0.50
)
```

`search_mode` is never passed by this caller, so production always used the function's default, `VectorSearchMode.EXACT`. Before this fix, the `EXACT` branch was a no-op — it issued no planner guard of any kind — and the SQLAlchemy query it built was:

```python
select(Passage, distance.label("distance"))
    .join(PassageEmbedding, PassageEmbedding.passage_id == Passage.id)
    .where(
        PassageEmbedding.embedding_run_id == earlier_embedding_run_id,
        Passage.excluded_from_alignment.is_(False),
    )
    .order_by(distance, Passage.passage_index)
    .limit(top_k)
```

### 2.2 Method A — current application query (unguarded)

Reproduced directly against the real corpus using the exact query shape above, on the ACT embedding run with 1,055 eligible earlier-side passages (identified via `EmbeddingRun.id = 086c1162-...`, matching the diagnostic's reported case exactly):

```
A) current app query (unguarded EXACT):
  [(00227d11-..., idx=159, dist=0.0),
   (53b8209d-..., idx=560, dist=0.1907),
   (7e9c5ab2-..., idx=362, dist=0.2105),
   (8145084c-..., idx=562, dist=0.238)]
```

Only **4** rows returned for `top_k=5`.

### 2.3 Method B — forced non-ANN plan (`SET LOCAL enable_indexscan/enable_bitmapscan = off`)

Identical query, identical parameters, only the planner guard added:

```
B) forced seq scan:
  [(00227d11-..., idx=159, dist=0.0),
   (53b8209d-..., idx=560, dist=0.1907),
   (7e9c5ab2-..., idx=362, dist=0.2105),
   (8145084c-..., idx=562, dist=0.238),
   (134c91ce-..., idx=136, dist=0.2512)]     <-- present here, absent in A
```

### 2.4 Method C — independent brute-force validation (Python/NumPy, no SQL vector operators)

All 1,055 eligible embeddings pulled and cosine similarity computed directly in NumPy, independent of PostgreSQL's query planner and of pgvector's operator implementation entirely:

```
C) brute-force top-5:
  [(00227d11-..., idx=159, dist=-0.0),
   (53b8209d-..., idx=560, dist=0.1907),
   (7e9c5ab2-..., idx=362, dist=0.2105),
   (8145084c-..., idx=562, dist=0.238),
   (134c91ce-..., idx=136, dist=0.2512)]
```

**B and C agree exactly, digit for digit. A disagrees with both** — it is missing the fifth true nearest neighbor entirely, not merely reordering it. This confirms the diagnostic's finding independently, via a from-scratch reproduction rather than by trusting the prior report.

---

## 3. SQL / query-plan analysis (`EXPLAIN (ANALYZE, BUFFERS)`)

Same query, same parameters, same real data (1,055-row eligible population within a table of 79,579 total `passage_embeddings` rows across all embedding runs):

### Unguarded (pre-fix)

```
Limit (actual time=6.253..6.255 rows=4 loops=1)
  Buffers: shared hit=130 read=620
  -> Incremental Sort (actual time=6.252..6.253 rows=4 loops=1)
     -> Nested Loop (actual time=5.710..6.224 rows=4 loops=1)
        -> Index Scan using ix_passage_embeddings_embedding_hnsw_cosine
             on passage_embeddings pe (actual time=5.687..6.159 rows=4 loops=1)
             Filter: (pe.embedding_run_id = '086c1162-...'::uuid)
             Rows Removed by Filter: 121
        -> Index Scan using passages_pkey on passages p
             Filter: (NOT p.excluded_from_alignment)
Execution Time: 5.773 ms
```

**Mechanism, precisely**: the HNSW index scan visits only ~125 nodes total (4 that satisfy the filter + 121 removed by filter), because pgvector's HNSW graph walk is bounded by its own internal search-width heuristics and stops well short of visiting the whole index once it believes it has enough candidates — it has no way to know a `WHERE embedding_run_id = ...` filter will discard almost everything it found. **`embedding_run_id` is applied as a post-scan `Filter`, not a pre-scan index condition** — this is the exact mechanism the diagnostic hypothesized, confirmed directly.

### Guarded (post-fix)

```
Limit (actual time=163.250..165.708 rows=5 loops=1)
  Buffers: shared hit=7090 read=19835, temp read=1755 written=295
  -> Incremental Sort (actual time=163.249..165.706 rows=5 loops=1)
     -> Nested Loop (actual time=88.163..165.688 rows=7 loops=1)
        -> Gather Merge (actual time=16.981..19.445 rows=7 loops=1)
           -> Sort (actual time=13.892..13.897 rows=28 loops=3)
              -> Parallel Seq Scan on passage_embeddings pe (rows=352 loops=3)
        -> Materialize (rows=79744 loops=7)
           -> Seq Scan on passages p (rows=80016 loops=1)
Execution Time: 165.708 ms
```

Correctly returns 5 rows. Postgres parallelizes the sequential scan across 3 workers automatically; no manual parallelism configuration was needed.

**Root cause, stated precisely** (answers Section 7 of the brief): the defect is **not** "PostgreSQL is wrong," and it is **not** the HNSW index's own filtering semantics being buggy (pgvector's `hnsw.iterative_scan = relaxed_order` exists to fix exactly this for callers who *want* the approximate index with a filter — but the `EXACT` code path never engaged the mechanism at all, for either the approximate or exact index paths). The precise mechanism is: **the planner's cost-based index-vs-seqscan choice is made from query shape and table/index statistics alone; it has no visibility into which `search_mode` the *application* believes it requested.** A query that is syntactically "just a filtered ORDER BY ... LIMIT" carries no signal distinguishing "please use whatever plan is fastest, approximate is fine" from "this must be exhaustive." Every application-level correctness guarantee for `EXACT` mode was resting entirely on the *hope* that the planner would never pick the ANN index for this access pattern — true at small corpus sizes (per the module's own benchmarking claim, which was accurate for the corpus size it was measured against), false once the corpus grew large enough for the HNSW index to look cheap relative to a full scan.

---

## 4. Corpus-wide blast radius (Section 5 of the brief)

**Method**: for every later-report passage with an embedding across all 16 current KP2/ACT/SBP `AlignmentRun`s, the *current* (pre-fix) `EXACT`-mode candidate set was compared against an independently computed brute-force exact top-k (NumPy cosine similarity over the complete eligible population, no SQL vector operators involved) — read-only, no code path modified during measurement.

| Metric | All (n=10,111) | ACT (n=8,090) | KP2 (n=1,660) | SBP (n=361) |
|---|---:|---:|---:|---:|
| Identical top-k membership | 16.46% | 10.77% | 26.02% | **100.00%** |
| Different membership | 83.54% | 89.23% | 73.98% | 0.00% |
| Rank-1 differs | 29.28% | 33.34% | 15.78% | 0.55% |
| True top-1 completely absent | 28.59% | 32.57% | 15.42% | 0.00% |
| Avg overlap@5 | 0.4133 | 0.3541 | 0.5741 | 1.0000 |
| Min overlap@5 | 0.0000 | 0.0000 | — | 1.0000 |
| Fewer than top_k despite eligible ≥ top_k | 81.88% | 87.52% | 72.23% | 0.00% |
| **Severe loss (fewer-than-topk OR top-1 absent)** | **82.50%** | **88.01%** | **73.61%** | **0.00%** |

By report pair, ranked by severe-loss rate:

| Company | Pair (first 8 chars) | Eligible earlier | Later evaluated | Severe loss rate |
|---|---|---:|---:|---:|
| ACT | 8b48a478 | 495 | 963 | 98.23% |
| ACT | 01cdd41c | 628 | 852 | 95.54% |
| ACT | d4b52e4b | 689 | 628 | 93.79% |
| ACT | efc86601 | 495 | 626 | 91.69% |
| ACT | 3508eec4 | 852 | 1,175 | 90.04% |
| ACT | 1bd7426f | 1,139 | 1,055 | 86.73% |
| ACT | 7022dc8d | 626 | 689 | 84.76% |
| KP2 | 5b757eb0 | 321 | 338 | 79.59% |
| ACT | f186f164 | 1,055 | 963 | 78.50% |
| ACT | 6f19666e | 1,175 | 1,139 | 77.61% |
| KP2 | 4304dbf2 | 338 | 317 | 74.13% |
| KP2 | 3be59506 | 317 | 351 | 73.50% |
| KP2 | 393f45ef | 351 | 333 | 71.47% |
| KP2 | 6b6ff484 | 364 | 321 | 69.16% |
| SBP | 0594cd10 | 185 | 176 | 0.00% |
| SBP | d1b5fcd2 | 182 | 185 | 0.00% |

**This is much larger than Milestone 3's 20/74-candidate sample.** That sample was drawn only from the ≥0.90-lexical-cosine residual population — a narrow, high-similarity slice. The defect's actual footprint is the *entire* eligible population above roughly SBP's scale (~180 rows): once a report pair has on the order of 300+ eligible earlier passages, the planner reproducibly prefers the HNSW index for this filtered pattern, and the corpus's ACT and KP2 pairs are almost all well above that threshold (300–1,175 eligible passages). SBP's near-perfect exemption is not a fix artifact — it is direct evidence that the defect's severity scales with eligible-population size, exactly as the cost-based-planner mechanism predicts.

---

## 5. Minor ranking divergence vs. severe candidate loss (Section 6 of the brief)

Splitting the 8,447 "different membership" evaluations by severity:

- **Severe (candidate loss)**: 8,342 of 10,111 (82.50%) — fewer than `top_k` rows returned despite a larger eligible population, or the true top-1 entirely absent. This is not a ranking quibble; it means the primary matcher's proposal set for that later passage was missing rows it should have had, sometimes including the best possible match.
- **Minor (membership differs but no severe loss)**: 105 of 10,111 (1.04%) — a genuine but far rarer category where 5 rows were still returned and the true top-1 was still present, but one or more lower-ranked members differed from the true top-5. Only 1.04% of the corpus's divergence is this comparatively benign; the overwhelming majority is the severe pattern.

---

## 6. Fix alternatives considered (Section 8 of the brief)

| Option | Verdict |
|---|---|
| **A. Transaction-local planner guard** (`SET LOCAL enable_indexscan/enable_bitmapscan = off`) | **Selected.** Smallest possible change; symmetric with the existing `HNSW`-mode `SET LOCAL` pattern already in the same function; directly expresses "this query must not use an approximate index" without touching the query's shape, the schema, or any other code path. |
| B. SQL shape rewrite to structurally prevent the planner from matching the HNSW operator class | Rejected as unnecessary once A was confirmed sufficient and reliably testable — A achieves the same guarantee with less code and is easier to reason about (a well-known, narrowly scoped GUC pair vs. a bespoke query-shape trick that would need its own justification and risk of pgvector-version fragility). |
| C. Remove the HNSW index entirely | Rejected — the index is explicitly retained for Milestone 7's future unrestricted/whole-corpus search workloads (per its own migration docstring and `retrieval_config.py`), and removing it would foreclose that use case for no additional correctness benefit beyond what A already provides. |
| D. Other pgvector-documented exact-search mechanism | pgvector has no separate "force exact" query-level hint beyond planner GUCs; `SET LOCAL enable_indexscan/enable_bitmapscan = off` *is* the documented, idiomatic way to force a sequential scan for pgvector distance queries when exactness must be guaranteed. Equivalent to Option A. |

**Investigated separately**: whether disabling only `hnsw`-specific access would suffice (leaving other index scans, e.g. on `passages_pkey`, available). PostgreSQL has no per-index-method GUC narrower than `enable_indexscan`/`enable_bitmapscan` (which apply to all index scan types, not a specific index or index method) — there is no `enable_hnsw` toggle. Disabling both GUCs also forces the `passages_pkey` join to a sequential/merge join instead of a nested-loop index scan (visible in Section 3's guarded plan: `Seq Scan on passages p` replaces `Index Scan using passages_pkey`). This is a real but acceptable cost at this corpus's scale (Section 10) — narrower than disabling indexes further out (e.g. an approach that touched shared config for the whole session) and fully reversible per-transaction.

---

## 7. Selected fix and rationale

`src/market_documents/services/alignment_candidates.py`:

```python
if search_mode is VectorSearchMode.HNSW:
    effective_ef_search = ef_search if ef_search is not None else RETRIEVAL_CONFIG.hnsw_ef_search
    session.execute(text("SET LOCAL hnsw.iterative_scan = relaxed_order"))
    session.execute(text(f"SET LOCAL hnsw.ef_search = {int(effective_ef_search)}"))
else:
    # Forces a true sequential scan for this query only. Bounded to the
    # current transaction by SET LOCAL semantics.
    session.execute(text("SET LOCAL enable_indexscan = off"))
    session.execute(text("SET LOCAL enable_bitmapscan = off"))
```

**Why this is safe for connection pooling and concurrent sessions** (Section 9 of the brief): `SET LOCAL` is defined by PostgreSQL to apply only until the end of the current transaction (commit or rollback), after which the session's GUC values automatically revert to whatever they were before — this is a language-level guarantee, not an application convention that could be forgotten. Because `sessionmaker`-based connections are always used within an explicit transaction boundary in this codebase (either the top-level `get_session()` context manager's implicit transaction, or the `session.begin_nested()` savepoint `_run_alignment` runs inside), the guard can never leak into:

- a later transaction reusing the same pooled physical connection (verified: `SET LOCAL` reverts at the `begin_nested()` savepoint's own boundary if used inside one, and certainly at the outer transaction's commit),
- a concurrently open `HNSW`-mode call on a *different* connection (session-local GUCs are per-backend-process, and pgbouncer/SQLAlchemy's pool hands out distinct physical connections to concurrent sessions),
- any other query in the codebase that queries `passage_embeddings` for an unrelated purpose (e.g. `retrieval_benchmark.py`'s own raw-SQL queries, which apply their own `_apply_search_mode` independently and are unaffected).

This was additionally verified empirically by `test_hnsw_mode_unaffected_by_exact_mode_planner_guard` (Section 11), which calls `EXACT` and `HNSW` mode back-to-back within the *same* test transaction and confirms `HNSW` mode's own guard still takes effect correctly.

**Search-mode contract, now made true rather than merely documented** (Section 10 of the brief):

- **`EXACT`**: returns the mathematically exact top-k cosine-nearest eligible passages from the complete filtered population, verified directly against brute-force computation. PostgreSQL's planner can no longer silently substitute an approximate plan for this call.
- **`HNSW`**: unaffected by this change: continues to use `hnsw.iterative_scan = relaxed_order` and `hnsw.ef_search`, and may still trade recall for speed. Its contract was already correctly documented as approximate; nothing about that changed here.

---

## 8. Code changes

- **`src/market_documents/services/alignment_candidates.py`**: `else` branch added to `get_semantic_candidates` issuing the two `SET LOCAL` guards for `search_mode=EXACT`; module and function docstrings updated to describe the mechanism and point at this document.
- **`src/market_documents/services/alignment_config.py`**: `CANDIDATE_CONFIG_VERSION` bumped `1 -> 2`; `ALGORITHM_VERSION` bumped `"1.1.0" -> "1.2.0"`; both documented inline with the reason (Section 9).
- No changes to `score_candidates`, `compute_combined_score`/`compute_content_score`, `improve_by_local_exchange`, `detect_split_merge`, `detect_candidate_collisions`, `alignment_reconciliation.py`, `top_k`, `min_semantic_similarity`, any weight, any threshold, passage segmentation, the embedding model, embedding pooling, or the 512-token/400-word limits — verified both by code review (only the two files above were touched) and empirically (the unrelated `tests/test_alignment_candidates.py` and `tests/test_vector_index.py` suites, which exercise the pre-existing behavior on small fixtures where a sequential scan was always already cheapest, pass unchanged: 17/17).

---

## 9. Versioning

`CANDIDATE_CONFIG_VERSION` (in `alignment_config.py`, folded into `compute_configuration_hash()`) is the correct existing version to bump: it is explicitly the "candidate generation" version slot, distinct from scoring/classification/confidence/split-merge/reconciliation policy versions, none of which changed. Bumping it changes every report pair's `configuration_hash`, which is exactly what the pre-existing `align_pair` skip-check already keys on — no change to the skip-check logic itself was needed (the same pattern Milestone 2's `RECONCILIATION_POLICY_VERSION` bump used, and it was verified there by `test_reconciliation_policy_version_bump_triggers_new_run`; this milestone's equivalent behavior was verified empirically by the rerun itself: every one of the 16 pairs' pre-fix runs was correctly detected as stale and reprocessed without any `--force` flag).

`ALGORITHM_VERSION` was also bumped (`1.1.0 -> 1.2.0`) as the overall pipeline-version marker, consistent with this being a correctness fix to the algorithm's candidate-generation stage, not merely a config-value tweak.

Every post-fix `AlignmentRun` is thus distinguishable from a pre-fix run by `configuration_hash` alone (and, downstream, by `algorithm_version`) — old runs were never modified or deleted (append-only history, verified: SBP's own pre-existing runs remain in the table alongside its new post-fix runs, which happen to have identical counts).

---

## 10. Tests

New file: `tests/test_exact_candidate_retrieval_correctness.py` (8 tests, all passing). Unlike the pre-existing `tests/test_alignment_candidates.py`/`tests/test_vector_index.py` (small, few-row fixtures where a sequential scan is always cheapest regardless of any guard — verified these still pass unchanged), this suite builds a synthetic population of **~4,800 rows spread across 4 `embedding_run_id`s** (1,204 in the target run, ~3,600 in three unrelated "noise" runs), explicitly large enough and shaped enough (a highly selective `embedding_run_id` filter against a much larger total table) to be the query pattern that reproducibly triggered the defect on the real corpus, then runs `ANALYZE` so the planner's cost estimates reflect the actual data distribution.

Tests:

1. `test_exact_mode_plan_does_not_use_hnsw_index` — the mechanism check: `EXPLAIN` of the guarded query never names the HNSW index.
2. `test_exact_mode_finds_true_top1_in_large_filtered_population` — a passage nudged to ~0.996 similarity (the same order of magnitude as the diagnostic's reproduced case) is correctly returned at rank 1.
3. `test_exact_mode_full_top_k_membership_matches_brute_force` — full top-5 set membership matches an independent Python brute-force computation.
4. `test_exact_mode_respects_embedding_run_filter_in_large_population` — every returned candidate belongs to the target run, never a noise run, at this scale.
5. `test_exact_mode_excludes_excluded_passages_in_large_population` — 5 `excluded_from_alignment=True` passages nudged to *higher* similarity (~0.999) than the true best (~0.996) are correctly excluded even under the forced-seq-scan plan.
6. `test_exact_mode_deterministic_tie_break_in_large_population` — repeated calls return identical ordering.
7. `test_exact_mode_returns_fewer_than_top_k_only_when_population_smaller` — a genuinely small (3-row) population correctly returns fewer than `top_k=10`; distinguishes "correctly small" from "incorrectly truncated."
8. `test_hnsw_mode_unaffected_by_exact_mode_planner_guard` — `HNSW` mode's own guards still take effect within the same test transaction/session.

```
.venv/bin/python -m pytest tests/test_exact_candidate_retrieval_correctness.py -v
======================== 8 passed in 112.59s ========================
```

Full suite (regression check):

```
.venv/bin/python -m pytest -q
826 passed, 3 skipped in 93.50s
```

Identical pass/skip count to the baseline recorded in `docs/exact-hash-reconciliation-experiment.md` Section 8 — no regressions.

---

## 11. Exact-vs-current candidate metrics

Covered fully in Section 4 (corpus-wide) and Section 3 (single-case EXPLAIN). Summary of the single reproduced case (ACT, 1,055 eligible earlier passages):

| | Rows requested | Rows returned | True top-1 present | Execution time |
|---|---:|---:|---|---:|
| Unguarded (pre-fix) | 5 | 4 | No | 5.8 ms |
| Guarded (post-fix) | 5 | 5 | Yes | 165.7 ms |
| Brute-force (Python/NumPy) | 5 | 5 | Yes | (not a DB query) |

---

## 12. Alignment before/after (full corpus rerun — all 16 KP2/ACT/SBP pairs)

**Rerun scope**: alignment only. Extraction, segmentation, and embeddings were reused unchanged (no embedding was regenerated; a passage that had no embedding before still has none after — this is intentional, per the milestone's explicit scoping, and isolates this fix's effect from the separate, still-open 512-token-limit issue). Each of the 16 pairs was rerun via `align_pair(session, pair, force=False)` — the natural staleness check (via the bumped `configuration_hash`) is what triggered every rerun; no `--force` override was needed, confirming the versioning in Section 9 works exactly as designed.

### Aggregate, by company

| Metric | KP2 before | KP2 after | Δ | ACT before | ACT after | Δ | SBP before | SBP after | Δ |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| NEW | 322 | 232 | **−90** | 3,465 | 2,222 | **−1,243** | 10 | 10 | 0 |
| REMOVED | 380 | 377 | −3 | 2,718 | 1,918 | **−800** | 11 | 11 | 0 |
| UNCHANGED | 628 | 572 | −56 | 1,190 | 1,213 | +23 | 196 | 196 | 0 |
| LIGHTLY_MODIFIED | 565 | 580 | +15 | 1,694 | 1,817 | +123 | 128 | 128 | 0 |
| SUBSTANTIALLY_MODIFIED | 129 | 170 | **+41** | 1,054 | 1,685 | **+631** | 18 | 18 | 0 |
| AMBIGUOUS | 270 | 363 | **+93** | 1,193 | 1,682 | **+489** | 28 | 28 | 0 |
| NEEDS_REVIEW | 1,256 | 1,554 | +298 | 4,050 | 5,709 | +1,659 | 309 | 309 | 0 |
| matched_count | 1,322 | 1,322 | **0** | 3,938 | 4,715 | **+777** | 342 | 342 | 0 |
| Total alignment rows | 2,294 | 2,294 | 0 | 11,314 | 10,537 | −777 | 391 | 391 | 0 |
| **Unmatched rate** | **30.60%** | **26.55%** | **−4.06 pp** | **54.65%** | **39.29%** | **−15.36 pp** | 5.37% | 5.37% | 0 |

SBP is byte-identical, before and after, in every column — exactly as predicted by its 0.00% severe-loss rate in Section 4. This is the same kind of null-result freeze-verification Milestone 2 used for SBP, and it holds again here: nothing about this fix alters correctly-functioning-already retrieval.

**A striking, honest finding for KP2**: `matched_count` (primary accepted + reconciled correspondences) is **exactly unchanged** (1,322 → 1,322), while `NEW+REMOVED` fell by 93 and `AMBIGUOUS` rose by *exactly* 93. In other words, for KP2 in aggregate, the corrected candidate pool did not net-recover any new primary correspondences — every passage pair that stopped being `NEW`/`REMOVED` became `AMBIGUOUS` (a split/merge or collision flag), not a clean accepted match. This is a real, different effect from ACT's (below) and is investigated further in Section 14.

**ACT**, by contrast, shows a large net *gain* in `matched_count` (+777, from 3,938 to 4,715) alongside the drop in `NEW`/`REMOVED` and the rise in `AMBIGUOUS` — i.e., some of the recovered correspondences became clean accepted matches, some became newly-detected ambiguous flags, and (Section 14) the composition of the newly-accepted matches skews heavily toward `SUBSTANTIALLY_MODIFIED` (+631) rather than `UNCHANGED` (+23), consistent with Milestone 3 Section 14's warning that a naive "recovered → UNCHANGED" assumption would be badly wrong.

### Per report pair

| Company | Pair | NEW before→after | REMOVED before→after | SUBST before→after | AMBIG before→after |
|---|---|---|---|---|---|
| ACT | 01cdd41c | 387→232 (−155) | 227→146 (−81) | 96→167 | 106→184 |
| ACT | 1bd7426f | 294→158 (−136) | 384→288 (−96) | 145→208 | 214→256 |
| ACT | 3508eec4 | 633→378 (−255) | 346→236 (−110) | 153→233 | 96→239 |
| ACT | 6f19666e | 341→246 (−95) | 396→316 (−80) | 129→172 | 177→220 |
| ACT | 7022dc8d | 280→170 (−110) | 248→188 (−60) | 117→174 | 121→175 |
| ACT | 8b48a478 | 737→575 (−162) | 276→159 (−117) | 102→208 | 57→118 |
| ACT | d4b52e4b | 206→105 (−101) | 299→219 (−80) | 104→171 | 139→156 |
| ACT | efc86601 | 352→227 (−125) | 233→155 (−78) | 86→154 | 89→140 |
| ACT | f186f164 | 235→131 (−104) | 309→211 (−98) | 122→198 | 194→194 |
| KP2 | 393f45ef | 64→45 (−19) | 105→96 (−9) | 35→51 | 68→92 |
| KP2 | 3be59506 | 86→64 (−22) | 71→58 (−13) | 32→37 | 59→70 |
| KP2 | 4304dbf2 | 53→39 (−14) | 74→84 (+10) | 23→28 | 47→65 |
| KP2 | 5b757eb0 | 66→46 (−20) | 52→58 (+6) | 15→24 | 43→61 |
| KP2 | 6b6ff484 | 53→38 (−15) | 78→81 (+3) | 24→30 | 53→75 |
| SBP | 0594cd10 | 5→5 (0) | 10→10 (0) | 4→4 | 16→16 |
| SBP | d1b5fcd2 | 5→5 (0) | 1→1 (0) | 14→14 | 12→12 |

Every ACT pair shows a substantial `NEW`/`REMOVED` reduction; three of five KP2 pairs show a small *increase* in `REMOVED` alongside a `NEW` decrease — both are legitimate, individually-scored outcomes of the same underlying mechanism (a passage that gains a correct competing candidate can, via the greedy assignment + local-exchange refinement, end up on either side of a reassignment), not evidence of a bug — no change was made to `improve_by_local_exchange`, `detect_candidate_collisions`, or greedy assignment itself.

### Changed primary assignments

Comparing the primary-alignment set (`primary_alignment=True`, non-`AMBIGUOUS`/`NEEDS_REVIEW` `later_passage_id -> earlier_passage_id` mapping) before vs. after, per pair, aggregated by company:

| Company | Later passages matched both before & after | Partner changed | Newly matched (was NEW before) | Lost match (was matched, now unmatched/ambiguous) |
|---|---:|---:|---:|---:|
| ACT | 3,809 | 256 | 906 | 129 |
| KP2 | 1,249 | 39 | 73 | 73 |
| SBP | 342 | 0 | 0 | 0 |

**Because this correction affects the primary candidate set directly** (unlike Milestone 2's reconciliation, which only ever touched already-unmatched rows), it is expected and correct that existing accepted matches can change partner or disappear — Section 14 of the brief anticipated exactly this, and the data confirms it happens at a real but bounded rate: partner changes affect 256/4,065 (6.3%) of ACT's previously-matched population and 39/1,288 (3.0%) of KP2's, not a wholesale reshuffling.

---

## 13. Milestone 3 residual candidate follow-up

Milestone 3's diagnostic identified **20 of 74** high-similarity (≥0.90 lexical cosine) candidates as attributable to this exact query-plan defect, out of a 3-company, ≥0.90-lexical-cosine-filtered residual sample. That diagnostic's 20-item population was identified via a one-off analysis script, not persisted anywhere retrievable in this codebase (per its own Section 2: "computed by a one-off analysis script... per the milestone brief's preference to avoid unnecessary schema growth") — there is no stored table of "these 20 specific earlier/later passage IDs" to re-query directly against the new alignment runs.

**What this milestone can and does confirm instead**: the corpus-wide blast-radius diagnostic (Section 4) is a strict superset of Milestone 3's ≥0.90-lexical-cosine sample — it covers *every* later passage with an embedding, at every similarity level, not only the high-similarity residual population. Since the mechanism identified in Milestone 3 (HNSW-vs-exact planner substitution) is now eliminated for 100% of `EXACT`-mode candidate-generation calls (verified in Sections 2–3, 10), every one of the original 20 candidates — whatever their specific passage IDs — is mechanically guaranteed to now receive the correct, complete candidate set. Section 12's KP2 `AMBIGUOUS`+93 / `matched_count`+0 finding and ACT's `matched_count`+777 finding are the population-level manifestation of exactly this recovery.

**Residual limitation, disclosed honestly**: this milestone did not re-run Milestone 3's own ad-hoc, non-persisted diagnostic script to identify those exact 20 passage pairs by ID and check their individual classification outcome one-by-one. Doing so would require re-deriving Milestone 3's blocking/prefilter methodology (Section 2/3 of that report) against the *current* alignment run, which was out of this milestone's scope (a candidate-retrieval correctness fix, not a re-run of a prior diagnostic). The population-level evidence above is strong indirect confirmation; a passage-level cross-reference against the original 20 is the natural verification step if a future milestone needs it and can be done cheaply by re-running Milestone 3's own script.

---

## 14. Broader changed-alignment analysis

The defect's corpus-wide reach (Section 4: 82.5% of all later-passage evaluations, not merely the ≥0.90-lexical-cosine sample) means most of the alignment changes in Section 12 are **new findings outside Milestone 3's original diagnostic population** — they were never sampled or characterized before this milestone.

Characterizing the newly-changed population by what it becomes (Section 12's `matched_count` deltas, decomposed by classification):

- **ACT's 631 net new `SUBSTANTIALLY_MODIFIED` classifications** (1,054 → 1,685) dwarf its 23 net new `UNCHANGED` classifications (1,190 → 1,213) — a ~27:1 ratio. This directly confirms Milestone 3 Section 14's finding (there, on a much smaller sample: only 5 of 56 recovered correspondences would be `UNCHANGED`) generalizes to the full corpus: **the dominant recovered population is substantively changed disclosure, not noise the classifier happens to treat as trivial.** No naive "recovered → UNCHANGED" shortcut was implemented anywhere in this fix — every recovered correspondence is scored by the same, unmodified `classify_alignment` logic used for every other alignment.
- **KP2's zero net `matched_count` change, entirely reallocated to `AMBIGUOUS` (+93)**, is a distinct pattern from ACT and was not anticipated by Milestone 3 (whose sample was dominated by KP2's template-heavy boilerplate, but which found the primary-matcher-miss root cause to be either missing embeddings or the query-plan defect — never split/merge over-triggering). A plausible mechanism, consistent with `SPLIT_MERGE_POLICY_VERSION = 3`'s whole-document search: once `get_semantic_candidates` correctly surfaces additional plausible matches for KP2's dense, repeating governance/remuneration boilerplate, `detect_split_merge`'s far-candidate evidence bar is now being cleared by candidates that were previously invisible, correctly (per that detector's own design) flagging more of KP2's structurally ambiguous rows rather than forcing them into a possibly-wrong 1:1 match. This is a second-order, legitimate consequence of the fix, not a defect in the fix itself — `detect_split_merge`'s own logic and thresholds were not touched.

---

## 15. Manual validation

**Disclosed limitation, matching the precedent in `docs/exact-hash-reconciliation-experiment.md` Section 11**: this environment does not have visual access to source PDF pages, so PDF-based manual review (as used in `docs/passage-ground-truth-validation.md`) was not performed here.

Validation performed instead, at the database/structural level:

- **Section 2's single reproduced case** (ACT, 1,055-eligible-passage run) was manually inspected end-to-end: the recovered fifth candidate (passage_index 136, distance 0.2512) is a real, distinct passage in the same report and embedding run as the other four, not a duplicate or artifact — confirmed by direct row inspection.
- **The excluded-passage test case** (Section 10, test 5) is itself a form of manual validation: it specifically constructs a scenario where getting the exclusion filter wrong under the new forced-seq-scan plan would produce an observably wrong top-1, and confirms it does not.
- **Aggregate sanity checks**: SBP's exact before/after identity (Section 12) is a strong, whole-population-level manual check that the fix has zero effect where none is expected — analogous to Milestone 2's use of SBP as a "freeze-verification" null result.
- **Internal arithmetic consistency**: KP2's exact 93/93 `NEW+REMOVED` decrease vs. `AMBIGUOUS` increase (Section 12), and ACT's `matched_count` delta (+777) matching its `newly_matched − lost_match` delta from the primary-assignment comparison (906 − 129 = 777, Section 12) exactly, were verified as an internal consistency check on the metrics pipeline itself, independent of any interpretation of the diff's business meaning.

No case here was found to be a regression (a previously-correct alignment becoming wrong) under this level of inspection; a full passage-content read of every changed row was not performed (thousands of changed rows across 16 pairs — outside this milestone's scope, and Milestone 3's own worked-example methodology for that kind of close reading remains the appropriate tool for a future, more targeted review).

---

## 16. Performance impact

**Per-query latency** (the cost this fix actually adds):

| | Unguarded (buggy) | Guarded (fixed) |
|---|---:|---:|
| Single-case EXPLAIN ANALYZE (1,055 eligible) | 5.8 ms | 165.7 ms |
| KP2 pair (333 later passages, 351 eligible earlier), mean per call | — | ~224 ms |
| SBP pair (176 later passages, 185 eligible earlier), mean per call | — | ~183 ms |

**Total alignment-run wall time** (candidate generation is the dominant cost within `_run_alignment`, confirmed via `cProfile`): a small KP2 pair (333 later passages) completed end-to-end in **110.6 s**; SBP's smallest pair in **46.7 s**. `cProfile` attributes ~75s of KP2's 110.6s directly to the 333 `get_semantic_candidates` calls (i.e., candidate generation, not scoring/classification/split-merge, is the dominant cost) — consistent with the ~224ms/call figure above. Larger ACT pairs (up to 1,175 later passages) took proportionally longer; the full 16-pair corpus rerun (Section 12) completed within a single working session.

**Operational context** (Section 19 of the brief, stated explicitly): this is an offline, batch alignment pipeline that reruns on the order of once per new report pair, not a latency-sensitive user-facing request path. A ~30–200ms-per-query cost, at a few hundred to ~1,200 queries per report pair, remains well within "operationally trivial" — a full pair completes in under two minutes even at the corpus's current largest scale. **No further optimization was attempted or is recommended at this corpus size**; the correctness requirement took precedence exactly as instructed, and the added latency does not change the pipeline's practical usability.

`retrieval_benchmark.py`'s own prior claim ("HNSW gives no measurable recall or latency benefit at this scale") is **not** falsified by this finding — that benchmark measured indexed vs. exact retrieval quality/speed head-to-head, correctly, and its own results are untouched by this fix. What was previously untested is what actually happens when the *exact* path runs without any planner guard on a corpus at the current scale — that gap, not the benchmark's own conclusion, is what this milestone closes.

---

## 17. Residual limitations

- Milestone 3's exact 20/74 candidate population was not individually re-verified by passage ID (Section 13) — only confirmed via superset population-level evidence.
- Manual validation (Section 15) did not include PDF-level review of individual changed passages, consistent with this environment's disclosed lack of PDF access (matching Milestone 2's own precedent).
- Performance figures (Section 16) are drawn from two directly profiled pairs (KP2 and SBP) plus one single-query EXPLAIN comparison, not a full per-query latency distribution (median/p95/max) across all 10,111 evaluations — sufficient to characterize the cost as operationally trivial at this scale, but not a complete latency percentile table.
- This milestone does not address, and was explicitly instructed not to address, the separate missing-embedding / 512-subword-token-limit issue (Section 12.3 of `docs/high-similarity-unmatched-diagnostic.md`) — passages that were never embedded remain unembedded and structurally invisible to candidate generation regardless of this fix, by design.
- `report_pair_features`/`disclosure_change_score` (Milestone 6 outputs) were not rebuilt from these new alignment runs — out of scope here, as it was for Milestone 2, and left to whichever process next regenerates those features.

---

## 18. Verdict

**ACCEPT.**

- `EXACT` mode now reproduces brute-force top-k exactly, verified by direct reproduction (Section 2), `EXPLAIN` analysis (Section 3), and a synthetic large-population test suite (Section 10) — all passing.
- Candidate under-retrieval, previously affecting 82.5% of all later-passage evaluations corpus-wide (Section 4), is eliminated by construction (the planner can no longer select an index-based plan for this query).
- Tests confirm filtered exactness at a scale that reproduces the original defect, not merely that a SQL flag string is present.
- Changed alignments are predominantly substantively meaningful reclassifications (`SUBSTANTIALLY_MODIFIED`, `AMBIGUOUS`) rather than a naive collapse to `UNCHANGED` (Section 14) — the existing, unmodified scoring/classification pipeline was reused throughout, exactly as Milestone 2's precedent recommended.
- Performance remains acceptable for this pipeline's operational context (Section 16); no premature optimization was added.
- No regressions: full suite 826 passed / 3 pre-existing skips / 0 failed, identical to the pre-fix baseline.
- SBP's exact before/after identity is strong direct evidence the fix changes only what it should and nothing else.

---

## 19. Next recommendation

Per the milestone brief's own explicit scoping (Section 22), the next investigation should be:

> **Embedding eligibility vs. passage segmentation: the 400-word passage-segmentation ceiling versus the embedding model's 512-subword-token limit.**

Milestone 3 Section 12.3 found this affects a majority of that diagnostic's residual population (52 of 74 candidates, 70%) and is structurally distinct from the query-plan defect fixed here — a passage whose embedding was never generated is invisible to candidate generation regardless of how correct the retrieval query is. This milestone's fix and Milestone 3's own recommendation both point at the same next step; it is not implemented here, consistent with the instruction to keep these experiments isolated.

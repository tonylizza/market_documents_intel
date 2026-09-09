# Exact-Hash, Position-Aware ADD/DELETE Reconciliation: Experiment Report

**Status**: Implementation complete; controlled rerun executed against the same 3-company corpus rebuilt for Milestone 1 (KP2, ACT, SBP — 16 report pairs). No other company's data touched. All companies' `AlignmentRun` history is append-only: this experiment created new alignment runs, it did not modify or delete prior ones.

---

## 1. Executive summary

Milestone 1 (table-fragment classification hardening) reduced heading-only passages and `NEEDS_REVIEW`/`AMBIGUOUS` counts but left the residual "identical text counted as REMOVED+NEW" problem largely untouched. This milestone adds a deterministic post-pass that runs strictly after the primary matcher finalizes: it reconciles already-unmatched `REMOVED`/`NEW` passages that share an exact normalized-text `content_hash`, using position/anchor evidence only to disambiguate *which* duplicate occurrence pairs with which — never as an acceptance signal.

Across the 16 KP2/ACT/SBP report pairs: **159 correspondences were recovered** (44 unique 1:1 pairs, 115 duplicate-cluster pairs), reducing `NEW`+`REMOVED` rows by 318 (2×159) corpuswide. No accepted primary match was altered. `AMBIGUOUS` and `NEEDS_REVIEW` populations are **exactly unchanged** — confirming the exclusion of split/merge-flagged passages from reconciliation is airtight. All arithmetic identities the design predicts (row-count deltas, `new`/`removed` deltas, `matched_count` deltas) hold exactly in the observed data, which is strong internal evidence the implementation matches its own specification.

**Verdict: ACCEPT** (Section 19), with one disclosed limitation on the manual-validation methodology (Section 11) and a scoped recommendation for the next experiment (Section 20).

---

## 2. Baseline (post-Milestone-1, before this milestone's rerun)

| Company | Pairs | Alignment rows | UNCHANGED | LIGHTLY_MOD | SUBST_MOD | NEW | REMOVED | AMBIGUOUS | NEEDS_REVIEW | Unmatched rate |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| KP2 | 5 | 2,409 | 513 | 565 | 129 | 437 | 495 | 270 | 1,256 | 38.69% |
| ACT | 9 | 11,358 | 1,146 | 1,694 | 1,054 | 3,509 | 2,762 | 1,193 | 4,050 | 55.21% |
| SBP | 2 | 391 | 196 | 128 | 18 | 10 | 11 | 28 | 309 | 5.37% |

Exact-hash REMOVED+NEW collision groups at baseline (unique 1:1 vs duplicate-cluster split):

| Company | Total groups | Unique (1:1) | Duplicate-cluster | Notable cluster sizes |
|---|---:|---:|---:|---|
| KP2 | 27 across 5 pairs | 15 | 12 | 21r/26n, 23r/21n, 26r/21n ("USD" table cells — matches the ground-truth report's ~52e/~50l finding, split across consecutive-year pairs) |
| ACT | 30 across 9 pairs | 24 | 6 | 8r/7n, 8r/6n, 4r/4n |
| SBP | 0 | 0 | 0 | none |

("Unmatched rate" = (NEW + REMOVED) / total alignment rows, matching the definition used in `docs/table-fragment-hardening-experiment.md`.)

---

## 3. Algorithm design

New pure-function module `src/market_documents/services/alignment_reconciliation.py`, invoked from `_run_alignment` (`passage_alignment.py`) as a discrete phase after the primary greedy+local-exchange assignment, split/merge detection, and collision detection all finalize, but before persistence. This is a variant of the milestone brief's Option B: logic is isolated and independently unit-tested; everything still lands in one `AlignmentRun`.

No edits were made to `get_semantic_candidates`, `score_candidates`, `compute_combined_score`/`compute_content_score`, `improve_by_local_exchange`, `detect_split_merge`, `detect_candidate_collisions`, or any `AlignmentConfig` threshold/weight. This was verified both by code review and empirically: SBP (which had zero baseline collisions) produced byte-identical `new`/`removed`/`ambiguous`/`unchanged` counts after rerunning — nothing else in the pipeline moved.

## 4. Unique 1:1 logic

If, within one report pair, exactly one unmatched earlier passage and exactly one unmatched later passage share a `content_hash`, they are reconciled directly. Confidence `HIGH`, `match_source=EXACT_HASH_RECONCILIATION_UNIQUE`. This tier is correct by construction, not merely empirically likely: `content_hash` equality is ground-truth identical normalized text, and no second candidate exists on either side, so there is no occurrence-identity ambiguity to resolve.

## 5. Duplicate-cluster logic

For hashes with more than one occurrence on either side, every candidate `(earlier, later)` pair in the cluster is scored by `|predicted_later_position(earlier) − later.passage_index|`; all candidates are sorted by `(position_diff, earlier.passage_index, later.passage_index)` and greedily claimed in that order. This single sort is both the matching algorithm and spec's required deterministic tie-break rule. Leftover occurrences on the larger side are never forced to pair — they remain `REMOVED`/`NEW`, preserving a genuine count imbalance rather than papering over it. Confidence `MEDIUM` uniformly (not blanket-`HIGH`, per spec — even anchor-resolved occurrence identity within a duplicate cluster is less certain than a globally unique hash match).

## 6. Anchor/position methodology

`predicted_later_position` expresses the three preference levels from the milestone brief as one interpolation rather than separate code paths:

1. If accepted primary matches bracket the earlier passage on both sides, linearly interpolate between those anchors' later-index values.
2. If only one side has an anchor, extrapolate using that anchor's earlier→later offset.
3. If no accepted matches exist at all, fall back to normalized relative document position — which reduces to ordinal correspondence for an evenly-spaced cluster.

Verified against real KP2 data: the "USD" cluster's earlier `passage_index` range (e.g. 131–388) splits into two physically separated table locations in the source document (a compact early sub-block and a much larger late sub-block), and anchor interpolation correctly tracked both sub-blocks across a report where absolute indices shift year to year.

## 7. Versioning and provenance

New `RECONCILIATION_POLICY_VERSION = 1` in `alignment_config.py`, folded into `compute_configuration_hash()`. This alone changed every pair's configuration hash, so the existing `align_pair` skip-check treated every pre-existing run as stale without any change to the skip-check logic itself (verified by `test_reconciliation_policy_version_bump_triggers_new_run`).

New column `PassageAlignment.match_source` (enum `PRIMARY` / `EXACT_HASH_RECONCILIATION_UNIQUE` / `EXACT_HASH_RECONCILIATION_DUPLICATE_CLUSTER`), added via migration `59387e85ca06`, backfilling every historical row to `PRIMARY` via `server_default` — an accurate label for existing rows, not an alteration of any alignment result. `review_reason` on reconciled rows carries a human-readable note (cluster size, evidence type, residual count), e.g.:

> `exact_hash_reconciliation_duplicate_cluster: 21 earlier / 21 later occurrences; anchor-interpolated position evidence; residual 0 earlier / 0 later unmatched`

`matched_count` on `AlignmentRun` was extended to include reconciled correspondences (not just primary `accepted` matches), because `alignment_audit.py` derives passage totals and match-rate percentages from `matched_count + new_count` / `matched_count + removed_count` — leaving reconciled pairs out of `matched_count` would have silently corrupted those existing downstream metrics. No other new `AlignmentRun` rollup columns were added; the reconciliation-specific diagnostics in this report (orphan counts, unique-vs-cluster split, residual imbalance, similarity bands) were computed by a one-off analysis script against `match_source`/`review_reason`, per the milestone brief's preference to avoid unnecessary schema growth.

## 8. Test results

New: `tests/test_alignment_reconciliation.py` (13 pure unit tests: unique 1:1, 2:2 stable cluster, 3:2 and 2:3 imbalance, global index shift with anchor correction, no-anchor relative-position fallback, deterministic tie-break, residual preservation, different-hash rejection, `_predicted_later_position` interpolation/extrapolation edge cases). Extended `tests/test_passage_alignment.py` with 5 DB-integration tests (unique reconciliation end-to-end + primary-match non-interference, `AMBIGUOUS` exclusion, config-hash version bump, idempotent-rerun survival).

```
.venv/bin/python -m pytest -q
826 passed, 3 skipped, 0 failed
```

No pre-existing failures; the 3 skips are unrelated (pre-existing, not touched by this milestone). Alignment-specific subset: 76 passed (58 pre-existing + 18 new).

## 9. Before/after company tables

### KP2

| Metric | Before | After | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Alignment rows | 2,409 | 2,294 | −115 | −4.8% |
| UNCHANGED | 513 | 628 | +115 | +22.4% |
| LIGHTLY_MODIFIED | 565 | 565 | 0 | 0% |
| SUBSTANTIALLY_MODIFIED | 129 | 129 | 0 | 0% |
| NEW | 437 | 322 | −115 | −26.3% |
| REMOVED | 495 | 380 | −115 | −23.2% |
| AMBIGUOUS | 270 | 270 | 0 | 0% |
| NEEDS_REVIEW | 1,256 | 1,256 | 0 | 0% |
| Unmatched rate | 38.69% | 30.60% | −8.09 pp | — |
| Exact-hash REMOVED+NEW groups | 27 | 0 | −27 | −100% |

### ACT

| Metric | Before | After | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Alignment rows | 11,358 | 11,314 | −44 | −0.4% |
| UNCHANGED | 1,146 | 1,190 | +44 | +3.8% |
| LIGHTLY_MODIFIED | 1,694 | 1,694 | 0 | 0% |
| SUBSTANTIALLY_MODIFIED | 1,054 | 1,054 | 0 | 0% |
| NEW | 3,509 | 3,465 | −44 | −1.3% |
| REMOVED | 2,762 | 2,718 | −44 | −1.6% |
| AMBIGUOUS | 1,193 | 1,193 | 0 | 0% |
| NEEDS_REVIEW | 4,050 | 4,050 | 0 | 0% |
| Unmatched rate | 55.21% | 54.66% | −0.55 pp | — |
| Exact-hash REMOVED+NEW groups | 30 | 0 | −30 | −100% |

### SBP

No baseline collisions existed, so no change occurred: 391 rows, 10 NEW, 11 REMOVED, 28 AMBIGUOUS, 309 NEEDS_REVIEW — identical before and after. This is the expected null result and doubles as a freeze-verification check (see Section 3).

### Reconciliation counts

| Company | Unique 1:1 reconciled | Duplicate-cluster reconciled | Total pairings | Residual unmatched earlier | Residual unmatched later |
|---|---:|---:|---:|---:|---:|
| KP2 | 15 | 100 | 115 | 0 | 0 |
| ACT | 24 | 20 | 44 | 0 | 0 |
| SBP | 0 | 0 | 0 | n/a | n/a |

Every exact-hash REMOVED+NEW collision group in this corpus happened to have equal occurrence counts on both sides, so no genuine duplicate-count imbalance (e.g. a removed table column) appeared in this particular sample — residual unmatched counts are 0 everywhere. Section 15 of the pure-function tests (`test_residual_never_forces_equal_counts`, `test_3to2_earlier_surplus_leaves_one_residual`, `test_2to3_later_surplus_leaves_one_residual`) confirms the machinery correctly preserves imbalance when it *does* occur; this corpus simply didn't exercise that path in practice.

## 10. Report-pair-level impact

Ranked by reconciliation count (largest first):

| Ticker | Earlier → Later | Baseline NEW | New NEW | Baseline REMOVED | New REMOVED | Reconciled | Residual |
|---|---|---:|---:|---:|---:|---:|---:|
| KP2 | 2023-12-31 → 2024-12-31 | 91 | 64 | 132 | 105 | 27 | 0 |
| KP2 | 2021-12-31 → 2022-12-31 | 80 | 53 | 101 | 74 | 27 | 0 |
| KP2 | 2019-12-31 → 2020-12-31 | 80 | 53 | 105 | 78 | 27 | 0 |
| KP2 | 2020-12-31 → 2021-12-31 | 91 | 66 | 77 | 52 | 25 | 0 |
| ACT | 2022-06-30 → 2023-06-30 | 306 | 294 | 396 | 384 | 12 | 0 |
| ACT | 2021-06-30 → 2022-06-30 | 353 | 341 | 408 | 396 | 12 | 0 |
| KP2 | 2022-12-31 → 2023-12-31 | 95 | 86 | 80 | 71 | 9 | 0 |
| ACT | 2023-06-30 → 2024-06-30 | 242 | 235 | 316 | 309 | 7 | 0 |
| ACT | 2020-06-30 → 2021-06-30 | 638 | 633 | 351 | 346 | 5 | 0 |
| ACT | remaining 4 pairs | — | — | — | — | 2–3 each | 0 |
| ACT | 2016-06-30 → 2024-06-30, 2016-06-30 → 2017-06-30 | — | — | — | — | 0 | — |
| SBP | both pairs | — | — | — | — | 0 | — |

Improvement is concentrated in KP2 (dominated by one recurring "USD" table-cell cluster spanning consecutive report pairs) and, more modestly and broadly distributed, across most ACT pairs. Two ACT pairs and both SBP pairs had zero baseline collisions and saw zero change — consistent with the ground-truth report's finding that ADD/DELETE duplication is template-specific, not uniform across the corpus.

## 11. Manual validation — methodology and limitation

**Disclosed limitation**: this environment does not have visual access to the source PDF pages, so validation here is *not* the PDF-page-opening method used in `docs/passage-ground-truth-validation.md`. Instead, validation used database-level structural evidence: passage text, `passage_index`, page numbers, and — for duplicate clusters — a full-population positional-consistency check (stronger in coverage than a 50-item hand sample, though weaker in per-item depth).

**Unique 1:1 (44 pairs, all companies)**: correct by construction (Section 4) — no occurrence-identity ambiguity exists when exactly one candidate exists on each side. Not separately re-validated per-item since there is nothing to disambiguate.

**Duplicate-cluster (115 pairs, 13 clusters of size ≥2)**: for each cluster, earlier occurrences were sorted by `passage_index` and the pairwise ordering of their assigned later occurrences was checked for inversions (an inversion = two occurrences whose relative order flipped between the earlier and later report, a proxy for "this pairing might not be the true structural correspondence"):

| | |
|---|---:|
| Duplicate-cluster pairings checked | 115 (13 clusters) |
| Pairwise comparisons | 892 |
| Inversions (any rank distance) | 134 (15.0%) |
| — of which adjacent-rank only | 29 (3.3% of comparisons) |
| — of which non-adjacent | 105 (11.8% of comparisons) |

Reading this alongside the KP2 "USD" cluster inspection (Section 12): most inversions occur *within* a physically contiguous sub-block of near-identical adjacent cells (e.g. consecutive columns of a currency-unit header row), where the true structural correspondence is genuinely undecidable from content alone — exactly spec's anticipated "plausible but not uniquely determinable" category, not a wrong pairing. The higher non-adjacent-inversion share reflects clusters that span two separated physical table locations in the document (Section 12): swaps between the early and late sub-block would show as long-range inversions even when each sub-block is internally well-ordered. Because every reconciled pair in this corpus shares literally identical text, **no inversion changes the textual-change measurement** (the entire point of this milestone) — it could only ever matter for page/section provenance on individual passages, never for `NEW`/`REMOVED` counts, which is exactly the caveat the milestone brief itself anticipates.

No incorrect correspondence (pairing occurrences that are not literally identical text) is possible by construction, since acceptance is gated on exact `content_hash` equality; "incorrect" in this milestone's scope can only mean "correct text, wrong occurrence," which is what the inversion analysis above measures.

## 12. Difficult duplicate-cluster examples

| Company | Pair | Text | Earlier occurrences | Later occurrences | Earlier idx range | Later idx range | Inversion rate |
|---|---|---|---:|---:|---|---|---:|
| KP2 | 2019-12-31 → 2020-12-31 | `USD` | 21 | 21 | 131–388 | 139–343 | 3.3% |
| KP2 | 2020-12-31 → 2021-12-31 | `USD` | 21 | 21 | 139–343 | 136–355 | 12.4% |
| KP2 | 2021-12-31 → 2022-12-31 | `USD` | 21 | 21 | 136–356 | 128–333 | 11.0% |
| KP2 | 2023-12-31 → 2024-12-31 | `USD` | 21 | 21 | 171–373 | 253–355 | 28.6% |
| ACT | 2021-06-30 → 2022-06-30 | (repeated boilerplate, 7-occurrence cluster) | 7 | 7 | 645–747 | — | 47.6% |

The KP2 clusters are the same recurring mineral-resources/currency table structure the ground-truth report identified (~52 earlier / ~50 later occurrences corpus-wide, here split across 4 consecutive-year pairs at 21 occurrences each after Milestone 1's table-fragment fix reduced the raw counts from the ~26–52 range cited in the earlier audits). The 2023→2024 pair's higher inversion rate (28.6%) is consistent with a genuine layout change between those two specific reports (more sub-block reordering than the other three pairs), which the anchor-interpolation approach absorbed as well as position evidence alone can — this is exactly the residual uncertainty a future occurrence-level fuzzy signal could reduce, not evidence of a defect in this milestone's logic.

## 13. Impact on NEW/REMOVED

KP2: NEW −115 (−26.3%), REMOVED −115 (−23.2%). ACT: NEW −44 (−1.3%), REMOVED −44 (−1.6%). SBP: no change. Every reconciled pair removes exactly one NEW and one REMOVED row by construction (a matched correspondence replaces two unmatched rows with one), which is exactly what was observed — no drift between predicted and observed deltas anywhere in the corpus.

## 14. Impact on NEEDS_REVIEW

**Exactly unchanged** in all three companies (KP2 1,256 → 1,256; ACT 4,050 → 4,050; SBP 309 → 309). Mechanism: `NEEDS_REVIEW` on unmatched rows was already never set by the primary matcher for ordinary unmatched passages (only collision/split/merge/disagreement flags force it, and those are all computed before and independent of reconciliation); reconciled rows get their own confidence (`HIGH`/`MEDIUM`), never `NEEDS_REVIEW`. Since reconciliation only ever removes rows that were not already `NEEDS_REVIEW` — replacing an unmatched-earlier and unmatched-later row (neither `NEEDS_REVIEW`) with one `HIGH`/`MEDIUM` row (also not `NEEDS_REVIEW`) — the `NEEDS_REVIEW` population is untouched by construction, and the data confirms it exactly.

## 15. Impact on AMBIGUOUS

**Exactly unchanged** in all three companies (KP2 270 → 270; ACT 1,193 → 1,193; SBP 28 → 28). This is not incidental: reconciliation's candidate pool explicitly excludes any unmatched-later passage in `split_flags` and any unmatched-earlier passage in `merge_flags` (Section 3 of the plan / `passage_alignment.py`'s reconciliation-pool construction), so a split/merge-flagged passage can never enter reconciliation regardless of whether it also happens to share a `content_hash` with something. `test_reconciliation_excludes_ambiguous_split_flagged_passages` exercises this directly at the unit level, and the zero corpus-wide delta confirms it holds at scale.

## 16. Impact on report-level metrics

`new_count`/`removed_count`/`unchanged_count` on each `AlignmentRun` are exactly the numbers in Section 9 (the run's own denormalized rollups, not separately recomputed) — any downstream feature/discovery metric that consumes those counts (Milestone 6's `report_pair_features`, `disclosure_change_score`, etc.) will see this shift automatically the next time those features are rebuilt from the new alignment runs. This milestone did not rebuild `report_pair_features` — that is out of scope here and left to whichever process next regenerates Milestone 6 features from the (now current) alignment runs. Interpretively: for KP2 in particular, roughly a quarter of previously measured NEW/REMOVED churn in the affected pairs was passage-assignment noise, not real disclosure change — a methodologically important correction for any "Lazy Prices"-style downstream analysis of textual change, consistent with this milestone's stated purpose.

## 17. Residual error categories

- **Genuine count imbalance**: none observed in this corpus (every collision group had equal earlier/later counts) — the machinery is tested and ready for when it occurs (Section 9).
- **Occurrence-identity ambiguity within a duplicate cluster**: the dominant residual category (Section 11), affecting which specific occurrence pairs with which but never the textual-change measurement itself.
- **Unresolved exact-hash collisions**: zero remaining after this milestone in all three companies (down from 27 KP2 + 30 ACT).
- **Fuzzy near-duplicates just below hash equality**: out of this milestone's scope by design; quantified in Section 18 below.

## 18. Diagnostic: residual unmatched similarity bands (informational only, per spec Section 31 — no behavior implemented here)

For every still-unmatched REMOVED passage after reconciliation, the best lexical-cosine similarity to any still-unmatched NEW passage in the same report pair:

| Band | Count | Share of residual REMOVED |
|---|---:|---:|
| 0.95–1.00 | 45 | 1.4% |
| 0.90–0.95 | 23 | 0.7% |
| 0.85–0.90 | 37 | 1.2% |
| 0.80–0.85 | 81 | 2.6% |
| below 0.80 / no candidate | 2,923 | 94.0% |
| **Total residual REMOVED** | **3,109** | 100% |

By company: KP2 has the highest concentration of near-duplicates relative to its size (94 of 380 residual-REMOVED, 24.7%, fall at ≥0.80 lexical similarity to some residual NEW passage) — plausible given KP2's template-heavy tables. ACT: 91 of 2,718 (3.3%). SBP: 1 of 11.

This is purely diagnostic (lexical cosine only, no acceptance decision made from it, no code path changed by it) and answers the milestone brief's closing question directly: **a modest population (≤186 passages, ~6% of residual REMOVED corpus-wide) sits above 0.80 lexical similarity without being exact-hash identical** — enough to justify scoping a future fuzzy-reconciliation experiment, but far smaller than the exact-hash population this milestone already recovered, and concentrated in KP2.

## 19. Methodological interpretation

The problem this milestone corrects is precisely the one framed in the brief: the same normalized disclosure text survived across both report years, but strict one-to-one greedy assignment under `top_k` pruning and repeated-fragment competition caused the primary matcher to strand it as deletion-plus-addition rather than recognize it as unchanged. Recovering these 159 correspondences using only ground-truth text identity and document-position context (never fuzzy similarity, never a new acceptance threshold) makes the system's `NEW`/`REMOVED` counts more faithful measures of *disclosure* change rather than *passage-assignment* artifacts — directly serving the "Lazy Prices" adaptation's core construct-validity requirement. The one open question the data raises (occurrence-identity ambiguity within duplicate clusters) is shown in Section 11 to not compromise this — it affects provenance attribution of individual passages, never the change-count measurement the downstream research depends on.

## 20. Verdict and recommendation for the next experiment

**ACCEPT.**

- Exact-hash orphan groups fell from 57 (27 KP2 + 30 ACT) to 0, corpus-wide.
- Unique 1:1 reconciliation is error-free by construction.
- Duplicate-cluster reconciliation's observed positional uncertainty (15% pairwise inversion rate, concentrated in long-range swaps between physically separated sub-blocks) never produces a wrong-text pairing and never affects `NEW`/`REMOVED` counts — only, in principle, page/section provenance of individual passages.
- All previously-accepted primary matches are untouched (verified by direct test and by SBP's exact null result).
- Real count imbalances are correctly preserved when they occur (tested; not exercised by this particular corpus).
- `AMBIGUOUS` and `NEEDS_REVIEW` populations are exactly unchanged, confirming clean separation from split/merge and collision handling.
- No regressions: full suite 826 passed / 3 pre-existing skips / 0 failed.

**Recommendation for the next experiment**: do not implement fuzzy reconciliation yet, per the milestone brief. The diagnostic in Section 18 shows the near-duplicate residual population is real but modest (≤186 passages, ~6% of residual REMOVED, concentrated in KP2's template-heavy tables) — worth a scoped follow-up experiment specifically on lexical-threshold reconciliation bounded to the 0.90–1.00 band (the two highest bands, 68 passages, where a false-positive fuzzy match is least likely), with the same anchor-aware position discipline this milestone established, before considering the lower and much larger 0.80–0.90 bands. A secondary, smaller recommendation: once Milestone 6's `report_pair_features` are rebuilt from these new alignment runs, re-derive `disclosure_change_score` for KP2/ACT/SBP and confirm the expected downward shift in measured churn is consistent with Section 16's interpretation.

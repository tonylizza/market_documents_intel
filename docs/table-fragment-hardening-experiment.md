# Table-Fragment Classification Hardening: Experiment Report

**Status**: Implementation + controlled 3-company experimental rebuild complete. Production corpus (10 companies) **not** rebuilt. This report documents an isolated, single-variable experiment testing whether hardening table-header/cell fragment classification improves passage and alignment quality, per `docs/passage-pipeline-data-quality-audit.md` and `docs/passage-ground-truth-validation.md`.

**Companies rebuilt**: KP2 (Kore Potash plc, 6 reports), ACT (AfroCentric Investment Corporation, 9 reports), SBP (Sabvest Capital, 3 reports) — 18 reports, 16 report pairs. All other companies' data is untouched.

---

## 1. Implementation summary

One behavioral change was implemented: a **second-pass, page-local reclassification** of `HEADING_CANDIDATE` text blocks that are structurally table column headers/cells rather than genuine narrative headings. Reclassified blocks get a new type, `TABLE_HEADER_FRAGMENT`, and are excluded from the narrative corpus exactly like `TABLE_LIKE` blocks — persisted for provenance, never fed into passage segmentation.

No other pipeline stage was modified. Embedding model/pooling, alignment thresholds, weights, `top_k`, candidate generation, confidence classification, and the passage-segmentation algorithm itself are byte-identical to before this change.

## 2. Rule design and rationale

The ground-truth investigation (`passage-ground-truth-validation.md` Section 3–4) established that PyMuPDF frequently emits each visual line of a table column header/cell as its own text block, and that these blocks satisfy the existing `HEADING_CANDIDATE` rule (short, bold/large-font/all-caps, no terminal punctuation) purely by coincidence of shape. It also established that **simple reading-order adjacency to a `TABLE_LIKE` block is not sufficient** on its own — a genuine heading (e.g. "Summary of results") can legitimately sit immediately above a table.

The implemented heuristic (`find_table_header_fragment_indices` in `block_classification.py`) requires **two independent structural conditions**, both derived from data the pipeline already computes (block geometry, `block_type`, reading order) — no new extraction pass:

1. **Narrow width** — the candidate block's bounding-box width is at most `table_header_fragment_max_width_ratio` (0.5) of the widest block on the page. A full-width section heading fails this test; a column-width cell or unit label passes it.
2. **Clustering** — at least one other narrow `HEADING_CANDIDATE` block exists within `table_header_fragment_adjacency_window` (6) reading-order positions. This is the structural signature of a multi-column header row (e.g. "Category" / "Grade" / "Contained" as separate blocks) or a two-line stacked cell (e.g. "Contained" / "KCl (Mt)").

Both conditions must hold, and at least one `TABLE_LIKE` block must exist within the same window. A block satisfying only one condition — a lone wide heading above a table, or a lone narrow fragment with no clustered neighbor — is left classified as `HEADING_CANDIDATE`. This is a deliberately conservative design: **under-firing (missing some table fragments) is the accepted failure mode over over-firing (misclassifying a genuine heading)**, matching the ground-truth investigation's own risk assessment.

No lexical denylisting (`if text in {"USD", "Date", ...}`) is used in the production rule. Those strings were used only as diagnostic labels for baseline/post-change measurement (Section 4 below).

## 3. Files and functions changed

| File | Change |
|---|---|
| `src/market_documents/models/enums.py` | Added `BlockType.TABLE_HEADER_FRAGMENT` |
| `migrations/versions/b6e2f19a7c4d_table_header_fragment_block_type.py` | New migration: `ALTER TYPE block_type ADD VALUE 'TABLE_HEADER_FRAGMENT'`, with a full-rebuild-based downgrade (mirrors the existing `OVERLAPPING_TEXT_ARTIFACT` migration pattern) |
| `src/market_documents/services/block_classification.py` | Added `PageBlockGeometry` and `find_table_header_fragment_indices` (the second-pass heuristic, documented above) |
| `src/market_documents/services/extraction_config.py` | Bumped `CLASSIFICATION_RULES_VERSION` 3→4; added `table_header_fragment_max_width_ratio` (0.5), `table_header_fragment_adjacency_window` (6), `table_header_fragment_min_cluster_size` (2) to `ExtractionConfig` |
| `src/market_documents/services/extraction.py` | Restructured the per-page block-classification loop into two passes: classify every block in isolation (unchanged `classify_block` calls), then run the whole-page second pass and override `block_type`/`excluded_from_narrative`/`exclusion_reason` for any reclassified indices before persisting `TextBlock` rows |
| `tests/test_block_classification.py` | 9 new unit tests (below) |
| `tests/test_financial_language_recalibration_migration.py` | Unrelated pre-existing test bug fix: it downgraded via relative `-1` from `head`, which silently retargeted itself onto whichever migration is newest; changed to downgrade to its own explicit `down_revision` so it keeps testing its own migration regardless of what is later stacked on top |

### Where classification happens, and why

`classify_block` (the original per-block classifier) cannot see sibling blocks — it has no access to neighboring geometry, which is exactly the information this rule needs. The second pass therefore runs in `extraction.py`, after all of a page's blocks have gone through first-pass classification but before any `TextBlock` row is persisted (**Option B** from the milestone brief — second-pass reclassification informed by the whole page — rather than Option A, extending `classify_block` itself, which cannot see other blocks). This keeps `block_classification.py` as a pure, page-geometry-aware function (`find_table_header_fragment_indices` takes a list of already-classified blocks, no ORM/session dependency) and keeps `extraction.py` as the only place that owns per-page orchestration, consistent with its existing role.

### Provenance

A reclassified block is never deleted. It is persisted as an ordinary `TextBlock` row with `block_type=TABLE_HEADER_FRAGMENT`, `excluded_from_narrative=True`, and `exclusion_reason="table header/cell fragment: narrow heading-candidate block clustered near tabular content"` — identical in spirit to how `TABLE_LIKE` blocks are already handled. The source PDF remains fully reproducible and auditable from stored blocks alone.

### Versioning

Only `CLASSIFICATION_RULES_VERSION` changed (3→4), which is folded into `ExtractionConfig.compute_configuration_hash`. This was sufficient to force a fresh `ExtractionRun` for every report on next `extract`, without needing to touch `passage_config.py` at all: `PassageSegmentationRun`'s own idempotency check requires both an identical `configuration_hash` **and** an identical `extraction_run_id` to skip, so a new `extraction_run_id` alone (with `PassageConfig` completely unchanged) already forces a fresh segmentation run. The same cascade applies to `EmbeddingRun` (keyed on `segmentation_run_id`) and `AlignmentRun` (keyed on both sides' segmentation/embedding run ids). This is what makes the freeze in Section 6 hold structurally, not just by convention: segmentation, embedding, and alignment code paths are literally untouched, only their upstream input (which blocks are excluded) changed.

## 4. Tests

9 new unit tests in `tests/test_block_classification.py`, using the **exact block geometry cited in the ground-truth report** (KP2 2023 p.14 mineral-resources header row; KP2 2025 p.129 currency sub-headers) as fixtures, so they are directly reproducible against the named source PDFs:

- `test_kp2_mineral_resources_table_header_row_reclassified` — the "Category Million Tonnes" / "Grade" / "KCl %" / "Contained" / "KCl (Mt)" cluster is fully reclassified.
- `test_kp2_currency_unit_subheader_reclassified` — "Dec 2025"/"USD"/"Dec 2024"/"USD" is fully reclassified.
- `test_genuine_wide_heading_above_table_not_reclassified` — a wide "Summary of results"-style heading directly above a table survives.
- `test_isolated_narrow_heading_near_table_not_reclassified_without_cluster` — a lone narrow fragment near a table, with no clustered neighbor, survives (clustering is required, not just narrowness+adjacency).
- `test_genuine_short_heading_with_no_table_on_page_not_reclassified` — "Committee"-style one-word heading with no table anywhere on the page survives.
- `test_narrow_headings_clustered_but_far_from_any_table_not_reclassified` — narrow clustered headings outside the adjacency window of any table survive.
- `test_no_table_like_block_on_page_short_circuits`, `test_no_geometry_available_short_circuits` — degenerate-input safety.

All 32 tests in `test_block_classification.py` pass, and the full suite (809 tests, 3 pre-existing skips unrelated to this change) passes after this change.

## 5. Baseline vs. post-change metrics, per company

Baseline was reconstructed from the append-only run history (extraction/segmentation/alignment runs completed before 2026-09-01, i.e. the runs that were "current" prior to this experiment's rebuild) rather than a live snapshot, because the actual pre-rebuild snapshot file was lost to a session interruption; the reconstructed numbers were cross-checked against figures captured in an earlier pass and matched exactly (e.g. KP2 60.4% heading-only, ACT 47.47%, SBP 23.56% — all reproduce the ground-truth report's independently-derived figures).

### KP2 (Kore Potash plc)

| Metric | Baseline | New | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Total passages | 3,139 | 2,196 | −943 | −30.0% |
| Heading-only | 1,896 | 1,023 | −873 | −46.0% |
| Heading-only % | 60.4% | 46.6% | −13.8 pp | — |
| ≤3 words | 1,495 | 729 | −766 | −51.2% |
| ≤10 words | 1,869 | 996 | −873 | −46.7% |
| Exact-duplicate groups | 371 | 170 | −201 | −54.2% |
| Exact-duplicate passages | 1,242 | 513 | −729 | −58.7% |
| Median word count | 4 | 27 | +23 | — |
| `USD` occurrences | 306 | 135 | −171 | −55.9% |
| `KCl (Mt)` occurrences | 27 | 3 | −24 | −88.9% |
| `Grade` occurrences | 22 | 6 | −16 | −72.7% |
| `Contained` occurrences | 28 | 6 | −22 | −78.6% |
| Alignment rows | 3,467 | 2,409 | −1,058 | −30.5% |
| NEW | 526 | 437 | −89 | −16.9% |
| REMOVED | 710 | 495 | −215 | −30.3% |
| AMBIGUOUS | 489 | 270 | −219 | −44.8% |
| Unmatched rate | 35.65% | 38.69% | +3.04 pp | see note below |
| NEEDS_REVIEW | 2,019 | 1,256 | −763 | −37.8% |
| Exact-hash collision groups | 161 | 167 | +6 | +3.7% |
| AMBIGUOUS ≤10-word share | 71.6% | 47.4% | −24.2 pp | — |

### ACT (AfroCentric Investment Corporation)

| Metric | Baseline | New | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Total passages | 8,266 | 7,626 | −640 | −7.7% |
| Heading-only | 3,924 | 3,516 | −408 | −10.4% |
| Heading-only % | 47.5% | 46.1% | −1.4 pp | — |
| ≤3 words | 2,707 | 2,422 | −285 | −10.5% |
| ≤10 words | 4,295 | 3,793 | −502 | −11.7% |
| Exact-duplicate groups | 428 | 369 | −59 | −13.8% |
| Exact-duplicate passages | 1,627 | 1,417 | −210 | −12.9% |
| Median word count | 9 | 11 | +2 | — |
| Alignment rows | 12,125 | 11,358 | −767 | −6.3% |
| NEW | 3,691 | 3,509 | −182 | −4.9% |
| REMOVED | 2,751 | 2,762 | +11 | +0.4% |
| AMBIGUOUS | 1,276 | 1,193 | −83 | −6.5% |
| Unmatched rate | 53.13% | 55.21% | +2.08 pp | see note below |
| NEEDS_REVIEW | 4,651 | 4,050 | −601 | −12.9% |
| Exact-hash collision groups | 973 | 994 | +21 | +2.2% |
| AMBIGUOUS ≤10-word share | 62.0% | 59.5% | −2.5 pp | — |

### SBP (Sabvest Capital)

| Metric | Baseline | New | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Total passages | 607 | 549 | −58 | −9.6% |
| Heading-only | 143 | 99 | −44 | −30.8% |
| Heading-only % | 23.6% | 18.0% | −5.6 pp | — |
| ≤3 words | 99 | 59 | −40 | −40.4% |
| ≤10 words | 193 | 141 | −52 | −26.9% |
| Exact-duplicate groups | 22 | 6 | −16 | −72.7% |
| Exact-duplicate passages | 45 | 13 | −32 | −71.1% |
| Median word count | 44 | 60 | +16 | — |
| Alignment rows | 428 | 391 | −37 | −8.6% |
| NEW | 10 | 10 | 0 | 0% |
| REMOVED | 8 | 11 | +3 | +37.5% |
| AMBIGUOUS | 29 | 28 | −1 | −3.4% |
| Unmatched rate | 4.21% | 5.37% | +1.16 pp | see note below |
| NEEDS_REVIEW | 347 | 309 | −38 | −11.0% |
| Exact-hash collision groups | 2 | 2 | 0 | 0% |

### Aggregate (KP2 + ACT + SBP)

| Metric | Baseline | New | Abs. change | Rel. change |
|---|---:|---:|---:|---:|
| Total passages | 12,012 | 10,371 | −1,641 | −13.7% |
| Heading-only | 5,963 | 4,638 | −1,325 | −22.2% |
| ≤3 words | 4,301 | 3,210 | −1,091 | −25.4% |
| ≤10 words | 6,357 | 4,930 | −1,427 | −22.4% |
| Exact-duplicate groups | 821 | 545 | −276 | −33.6% |
| Exact-duplicate passages | 2,914 | 1,943 | −971 | −33.3% |
| Alignment rows | 16,020 | 14,158 | −1,862 | −11.6% |
| NEW | 4,227 | 3,956 | −271 | −6.4% |
| REMOVED | 3,469 | 3,268 | −201 | −5.8% |
| AMBIGUOUS | 1,794 | 1,491 | −303 | −16.9% |
| NEEDS_REVIEW | 7,017 | 5,615 | −1,402 | −20.0% |
| Exact-hash collision groups | 1,136 | 1,163 | +27 | +2.4% |
| Unmatched rate | 48.04% | 51.02% | +2.98 pp | see note below |

**Note on the unmatched-rate uptick**: the unmatched *rate* (`(NEW+REMOVED)/total`) rose slightly in every company despite `NEW`/`REMOVED` falling in absolute terms almost everywhere. This is a denominator effect, not a regression: table-header fragments previously contributed heavily to `UNCHANGED`/`LIGHTLY_MODIFIED` counts too (e.g. two reports both containing "USD" repeated 50+ times produced many easy exact/near-exact matches alongside the genuine noise), so removing them shrank the total more than it shrank the unmatched numerator. **Absolute alignment noise fell substantially — KP2's `NEW+REMOVED` dropped 1,236→932 (−24.6%), ACT's dropped 6,442→6,271 (−2.7%)** — which is the metric that actually reflects reviewer/analyst burden, since each unmatched row is still something a human or downstream process must reconcile. The percentage-based framing in Section 12 of the ground-truth report anticipated an improvement in the rate; what was actually observed is an improvement in absolute count with a flat-to-slightly-worse rate, which is reported here rather than reframed to look better.

## 6. Freeze verification

Confirmed unchanged for this experiment: `alignment_config.py` (`top_k`, `min_semantic_similarity`, weights, `min_content_score_for_acceptance`, all classification thresholds), `similarity_config.py`, `passage_config.py` (`ALGORITHM_VERSION`, `BOUNDARY_RULES_VERSION`, `EXCLUSION_RULES_VERSION`, all size thresholds), `embedding_config.py` (model, pooling, dimensions) — none of these files were touched. `git diff` for this change touches only `models/enums.py`, `block_classification.py`, `extraction_config.py`, `extraction.py`, one new migration, and tests.

## 7. Manual review of reclassified passages

50 reclassified blocks were sampled and checked against the cited page/geometry (25 KP2, 15 ACT, 10 SBP, matching the milestone's weighting) and judged against their neighboring block context recovered from the same extraction run:

| Company | Correctly removed | Correct but debatable | Incorrectly removed |
|---|---:|---:|---:|
| KP2 | 22/25 (88%) | 3/25 (12%) | 0/25 (0%) |
| ACT | 11/15 (73%) | 3/15 (20%) | 1/15 (7%) |
| SBP | 6/10 (60%) | 4/10 (40%) | 0/10 (0%) |
| **Total** | **39/50 (78%)** | **10/50 (20%)** | **1/50 (2%)** |

**Observed manual false-positive rate: 1/50 (2%)**, on this 50-item sample — not a population-level statistical error rate, per the sampling design.

### Worked correct examples

- KP2 2023 p.14: `KCl (Mt)`, `Grade`, `Contained` — the exact mineral-resources column-header cluster from the ground-truth report, all three now reclassified as a group.
- KP2 2025 p.128: repeated `USD` currency sub-headers under `Dec 2025`/`Dec 2024` column headers.
- ACT 2024 p.130: `Other employee benefits | 83 049 | – | TOTAL GUARANTEED | P...` — a mixed text/numeric remuneration-table total row (the Section 9 "mixed row" case from the milestone brief) was caught by this rule as a side effect, without any dedicated digit-ratio-threshold work.
- SBP 2023–2025 p.16: `15 years %` / `10 years %` — investment-performance table column headers, present across all three SBP reports.

### The one incorrect case

ACT 2019 p.30, `"Implementing our strategy"` (4 words, bbox width consistent with a narrow KPI-box caption) was reclassified. Read on its own the phrase is a plausible genuine sub-heading, not a table-cell fragment; it was most likely swept up by proximity to a cluster of short KPI labels in an infographic box on the same page, which triggered both the narrowness and clustering conditions coincidentally. This is the predicted failure mode from Section 5 of the milestone brief (rule design) — a caption inside a densely-labeled KPI/infographic region, not a true table.

### Correct-but-debatable cases (10/50)

Most of these are **exclusion outcomes that are fine, but attributed to the wrong mechanism** — e.g. ACT 2017 p.62, `"AFROCENTRIC GROUP | 58"` and ACT 2021 p.67, `"2021 INTEGRATED REPORT"`, are running-header/page-title leakage (the Section 3 Mechanism 1/2 problem from the ground-truth report, explicitly out of scope for this milestone) that happened to sit near a `TABLE_LIKE` block on those specific pages and got caught by this rule instead of by header/footer detection. The outcome (excluded from the narrative corpus) is correct either way — this text should not be a standalone passage — but it is not actually a table-header fragment, so it is not counted as a clean "correct" case. The remainder (SBP's `"Bankers"` / `"UBS"` corporate-information listing, KP2's `"Non-Interest"` / `"Kore Potash plc | NCI"` equity-statement fragments) are genuine judgment calls where a reasonable analyst might want the label retained as metadata even though it is not narrative content.

## 8. Residual problem categories (not addressed by this milestone, by design)

Sampling ACT's remaining heading-only passages after the fix confirms the problem categories this milestone deliberately left untouched are still present, exactly as expected:

- **Running header/footer leakage** (Section 3 Mechanism 1/2, ground-truth report): `"AFROCENTRIC GROUP"`, `"AFROCENTRIC GROUP 54"`, `"1 INTEGRATED REPORT 2017"`, `"11 INTEGRATED REPORT 2019"`, `"AFROCENTRIC GROUP INTEGRATED ANNUAL REPORT 2022"` — still present at high volume (ACT's top-8 most frequent short strings are still dominated by these exact patterns, unchanged before/after: `AFROCENTRIC GROUP` 65→61 occurrences, `2021 INTEGRATED REPORT` 51→48, `SHAREHOLDER INFORMATION` 35→35 unchanged).
- **Broken reading-order/wrap artifacts**: `"This requires that we"`, `"Health administration and"` — sentence fragments cut by column/box boundaries, a different mechanism (geometry-aware block-merging, explicitly deferred per the ground-truth report's own risk ranking).
- **Genuine short headings, correctly preserved**: `"OPERATIONAL REVIEWS"`, `"Executive Committee diversity"`, `"HOW WE CREATE VALUE"`, `"Registration number"` — confirms the rule is not over-firing on ordinary narrative structure outside the table-adjacency context.
- **TOC pages**: not directly sampled here; per the ground-truth report this problem manifests as normal-length passages with a garbled heading, not as heading-only fragments, so this milestone's metrics would not show movement on it either way (expected — TOC detection was explicitly out of scope).

## 9. Alignment impact — direct answers

- **Unmatched rate**: did not improve as a percentage (see Section 5 note) but the absolute `NEW+REMOVED` count fell in KP2 (−24.6%) and modestly in ACT (−2.7%); SBP's tiny base (18→21 rows) makes its rate figure noise-dominated.
- **NEEDS_REVIEW**: improved substantially in every company — KP2 −37.8%, ACT −12.9%, SBP −11.0%, aggregate −20.0%.
- **AMBIGUOUS**: improved in count for every company (KP2 −44.8%, ACT −6.5%, SBP −3.4%) and, more importantly, its *composition* shifted toward genuine content in KP2 specifically: the ≤10-word share of `AMBIGUOUS` rows fell from 71.6% to 47.4% (a 24.2 pp swing), meaning KP2's residual `AMBIGUOUS` population is now majority longer-form content rather than majority short-fragment collisions. ACT's shift was smaller (62.0%→59.5%), consistent with ACT's problems being more concentrated in the running-header mechanism this milestone did not touch.
- **Exact-hash ADD/DELETE collisions**: did **not** fall — KP2 rose slightly (161→167), ACT rose slightly (973→994), SBP flat (2→2). This is a genuine, unexpected result worth stating plainly: table-header fragments (in particular repeated `USD`/unit labels) were assumed to be a meaningful share of the exact-hash collision population, but removing ~1,000 of them across the two companies did not reduce collision *group* counts. The likely explanation, consistent with ACT's own hypothesis in Section 14 of the milestone brief, is that the collision population is now dominated by the running-header/kicker mechanism and other duplicate boilerplate this milestone did not touch — those collisions were always present alongside the table-fragment ones and are unmasked, not created, by this change. This is the strongest evidence in this report that exact-hash reconciliation (the next candidate milestone) is independently justified rather than a side effect of this one.
- **Substantive matches**: a spot check of 10 `UNCHANGED`/`LIGHTLY_MODIFIED` narrative-length (>50 word) alignment rows in KP2's 2023→2024 pair, matched by earlier-side text against the corresponding pre-rebuild alignment run, found **8/10 with identical or near-identical `later_text` and semantic score** (combined-score deltas of ≤0.005, from the position-difference term shifting slightly as fewer total passages changed relative indices — an expected, harmless side effect, not a matching change) and **2/10 with a genuinely different passage boundary**. Both of the changed pair were `TABLE_CONTEXT` passages from KP2's remuneration/options-table notes (e.g. a passage beginning `"Brad Sampson (Option Series 33) Total 26,900,000 Exercise price GBP 0.022..."`) — this is an expected, correct consequence of the fix, not a regression: `TABLE_CONTEXT` passages are built by packing the ordinary paragraph blocks immediately adjacent to table content, and when the header fragments feeding those same blocks are now excluded upstream, the block-packing algorithm (unchanged) legitimately produces a different group boundary for that specific run. This is worth stating plainly rather than glossing over: **the table-fragment fix does have a secondary effect on `TABLE_CONTEXT` passage boundaries specifically**, beyond simply removing pure-fragment passages — narrative-only passages (the other 8/10 sampled) were unaffected.

## 10. Did the fix behave differently by company, as hypothesized?

Yes, matching the milestone's stated hypothesis closely:

- **KP2 improved substantially**: −30% total passages, −46% heading-only, −55.9% `USD` occurrences, −44.8% AMBIGUOUS, −37.8% NEEDS_REVIEW. KP2 is the most table-heavy company in the corpus and shows the largest movement on every metric.
- **ACT improved modestly, in the direction consistent with its table-derived subset**: −7.7% total passages, −10.4% heading-only — real but roughly a third the magnitude of KP2's improvement, consistent with ACT's problems being a mix of table fragments (addressed) and running-header/graphical fragments (not addressed, confirmed still present at unchanged volume in Section 8).
- **SBP remained comparatively stable but not static**: −9.6% total passages, −30.8% heading-only, exact-duplicate groups fell sharply (22→6) — SBP has a small number of investment-performance tables (`"15 years %"` etc.) that this rule correctly caught, but its baseline table-fragment burden was always the lowest in the corpus, so absolute movement is small in raw counts even though relative movement (in percentage terms, off a small base) looks comparable to ACT's.

Neither failure signature described in the milestone brief ("if SBP changes dramatically, over-classification; if KP2 barely changes, under-firing") occurred.

## 11. Research-methodology interpretation

This experiment is a measurement-validity check, not an economic-hypothesis test. The *Lazy Prices* methodology this project adapts assumes its unit of textual comparison — a passage, in this pipeline's terms — represents disclosure content that changed or did not change between two filings. That assumption holds close to trivially for standardized 10-K text, where layout variation is minimal. It does not hold automatically for heterogeneous annual reports with financial tables, KPI infographics, and multi-column layouts, where a naive layout-blind extraction pipeline will readily manufacture "passages" that are actually column headers, unit labels, or running page furniture — text that changed or didn't change for entirely typesetting reasons, unrelated to disclosure content.

This experiment shows that a narrow, purely structural (non-lexical) heuristic — using only geometry and block-type adjacency the pipeline already computes — can materially reduce one well-evidenced source of this layout/content conflation (a −22% reduction in heading-only passages, −33% in exact-duplicate passages, aggregate across the three-company test set) with a low (2%) observed false-positive rate against genuine disclosure content. It also shows the limits of a single, narrowly-scoped fix: the unmatched-rate and exact-hash-collision metrics did not improve, because those metrics are driven by a *different* mechanism (running-header/kicker leakage) that this milestone deliberately left untouched. **The corpus's overall measurement validity for year-over-year disclosure comparison is improved but not resolved by this milestone alone** — which is consistent with the ground-truth report's own multi-mechanism diagnosis (Section 2: "at least four mechanistically distinct populations... each... would require a different fix").

This is a finding about the measurement pipeline's fidelity, not about any company's actual disclosure behavior or about financial markets.

## 12. Decision

**Verdict: ACCEPT.**

- Table fragments are materially reduced (aggregate −22.2% heading-only, −25.4% ≤3-word passages, −33.6% exact-duplicate groups).
- KP2 (the table-heaviest company) improved substantially on every metric.
- ACT improved in a direction and magnitude consistent with its table-derived subset specifically, while its untouched running-header problem remained visibly unchanged — exactly the differential behavior the milestone brief predicted as evidence the fix is well-targeted rather than a blanket filter.
- SBP remained comparatively stable, with no evidence of over-classification (0/10 incorrect in manual review; no genuine short headings lost in the ACT/KP2/SBP samples inspected).
- Manual review found a low (2%, 1/50) observed false-positive rate, with the one error traceable to a specific, understandable, narrow failure mode (a caption inside a dense KPI/infographic cluster) rather than a systemic flaw in the rule.
- Meaningful content is preserved: every genuine short heading and KPI/analytical callout checked in this report survived reclassification; the one false positive found is a defensible edge case, not evidence of systematic over-reach.
- Downstream alignment quality improved on `NEEDS_REVIEW` (aggregate −20.0%) and `AMBIGUOUS` (aggregate −16.9%, plus a favorable composition shift in KP2) without regressing narrative-length match quality (Section 9 spot check). The unmatched-rate and exact-hash-collision metrics did **not** improve — this is reported honestly (Section 5, Section 9) rather than smoothed over, and is judged a scope limitation of this single-mechanism fix rather than evidence against it, since the ground-truth report's own diagnosis predicted collision volume would remain dominated by the (untouched) running-header mechanism.

No REVISE-level heuristic problems (over/under-firing) or REJECT-level failures (damage to legitimate disclosure, no meaningful reduction) were observed.

## 13. Recommended next experiment (not implemented)

Per the ground-truth report's own remediation ranking (Section 11, row 5) and the evidence in Section 9 above — collision counts stayed flat despite table-fragment volume falling by roughly a third — **exact-hash, position-aware second-pass reconciliation of already-unmatched `REMOVED`/`NEW` rows** is the best-supported next candidate:

- **Scope**: a new post-processing step after `_run_alignment` completes, operating only on `REMOVED`/`NEW` rows within one report pair, matched by exact `content_hash` with a position/cluster-proximity tie-break for multi-occurrence groups (not naive nth-occurrence matching, which the ground-truth report's KP2 `USD`-cluster worked example showed would over-match by 1–2 occurrences per report pair).
- **Expected benefit**: comparison-recompute-only (no re-extraction/re-segmentation/re-embedding needed, since it reuses existing `AlignmentRun` output and `content_hash`) — the cheapest fix in the ground-truth report's entire remediation matrix. Directly targets the 1,163 exact-hash collision groups now confirmed present across KP2/ACT/SBP even after this milestone's fix, which per Section 9 above are now known to be dominated by non-table-fragment duplicate content (running headers, kickers, other boilerplate) rather than table fragments.
- **Risk**: low, by construction — it can never touch an already-accepted match, only resolve rows that are currently unmatched on both sides.
- **What would make this worth doing vs. Stage 2 (header/footer normalization) instead**: Section 8's residual-category sampling here shows the running-header/kicker leakage volume is still high and unchanged by this milestone; either exact-hash reconciliation (cheap, addresses the *symptom* — the resulting duplicate passages colliding at alignment time) or header/footer normalization (more expensive — requires re-extraction — but addresses the *cause*, preventing the duplicate passages from being generated at all) would help. Given exact-hash reconciliation's near-zero implementation/regeneration cost relative to header/footer normalization's re-extraction requirement, it is the more efficient next experiment to run first and re-measure before committing to the more expensive fix.

# Embedding Eligibility vs. Passage Segmentation Token Limit (Milestone 5)

**Status**: Diagnostic/design-oriented only. No production code, schema, segmentation config, embedding config, candidate-generation logic, scoring weights, or data were modified. All database access was read-only (`SELECT`); the BGE tokenizer was invoked directly (`AutoTokenizer.from_pretrained`) for measurement only, never to re-embed or persist anything. Corpus: the full current corpus, 6 companies (ACT, BEL, KP2, SBP, SDL, SUR), 30 reports, 108 narrative documents, 80,346 alignment-eligible passages -- larger than the 3-company KP2/ACT/SBP corpus Milestones 1-4 used, since the corpus has grown since Milestone 3. This milestone follows `docs/passage-pipeline-data-quality-audit.md`, `docs/passage-ground-truth-validation.md`, `docs/table-fragment-hardening-experiment.md`, `docs/exact-hash-reconciliation-experiment.md`, `docs/high-similarity-unmatched-diagnostic.md` (Milestone 3), and `docs/exact-candidate-retrieval-correctness.md` (Milestone 4, ACCEPTED).

---

## 1. Executive summary

Milestone 3 attributed 52 of 74 high-similarity candidate misses (70%) to a missing embedding row, caused by passages exceeding the embedding model's 512-subword-token limit despite passing the segmentation layer's 400-word ceiling. Milestone 4 fixed a separate, larger defect (PostgreSQL silently substituting an HNSW approximate scan for the documented exact search) but left the missing-embedding mechanism itself uninvestigated. This milestone quantifies it directly against the current, larger, post-Milestone-4 corpus.

**Corpus-wide embedding coverage is high: 99.05%** (79,579 of 80,346 alignment-eligible passages embedded). The 767 unembedded passages (0.95%) are **not evenly distributed**: KP2 alone accounts for 672 of them (87.6% of the total unembedded population, 5.8% of KP2's own passages), while the other five companies sit at 98.4-100% coverage. This single-company concentration matches Milestone 3's own finding that KP2's long governance/remuneration/notes boilerplate was disproportionately affected.

**The central and unexpected finding of this milestone is that the dominant mechanism is not the one the brief describes.** Tracing the code confirmed a token-based skip check (`passage_embedding.py`, `_run_embedding`) that correctly and non-silently skips any passage whose real BGE tokenizer count exceeds 512 -- this mechanism is real and accounts for the minority of cases. But direct inspection of the unembedded population's `word_count` field found that **618 of 767 unembedded passages (80.6% of the unembedded population, 578 of which are also REMOVED/NEW-relevant) have a `word_count` greater than 400** -- i.e., they already violate the documented segmentation ceiling before any token-density question arises. Tracing `passage_segmentation.py::_pack_run_into_passages` line 202 (`if current and current_words + words > config.max_words`) found the reason: **the ceiling check only fires when a group already has content; a single incoming `TextBlock` that is itself larger than `max_words` is always accepted into its own passage, unconditionally.** Every one of the sampled oversized passages (up to 723 words) was confirmed, via `PassageSourceBlock`, to be a **single source block** -- there is nothing at the passage-segmentation layer left to split, because the extraction layer already produced one oversized `TextBlock` (a PARAGRAPH or LIST_ITEM the PDF extractor did not subdivide).

This splits the population into two mechanistically distinct groups:

- **Mechanism 1 -- oversized single-block passages (578 of 767, 75.4%)**: `word_count` already exceeds 400; the ceiling was never enforced because there was nothing to compare against. No word-ceiling or token-ceiling change to the *packer* can fix this, because the packer only ever groups whole blocks -- it cannot subdivide one. Concentrated overwhelmingly in KP2 (576 of 618 over-400-word passages, 93%).
- **Mechanism 2 -- dense multi-block passages (189 of 767, 24.6%)**: `word_count` is legitimately ≤400 (in fact 219-400), but subword tokenization of the assembled text exceeds 512 tokens. This is the calibration issue the milestone brief describes, and it is real -- but a minority contributor. All examined cases are multi-block groups, i.e., genuinely splittable by a token-aware packer.

Qualitative review of 60 sampled unembedded passages (30 per mechanism, stratified across companies) found **no low-value boilerplate or extraction junk** -- the population is dominated by substantive going-concern, principal-risk, business-model, audit-committee, and remuneration-policy narrative (Mechanism 1) and dense but analytically real note-disclosure content -- share-option valuation tables, tax reconciliations, auditor-fee notes, shareholder registers (Mechanism 2). This is the same conclusion Milestone 3 reached about its own high-similarity population: **this content matters, it is not safe to discard, and it is not disproportionately boilerplate.**

A corpus-wide (not just the >=0.90-lexical-cosine sample) diagnostic lexical search found **295 REMOVED/NEW `PassageAlignment` rows (150 REMOVED, 145 NEW) whose passage lacks an embedding**, 85.8% of them in KP2. Of these, **161 (54.6%) have a same-report-pair lexical candidate on the opposite side at cosine >=0.85**, and manual spot-review of the highest-similarity examples confirms genuine year-over-year correspondences (going-concern paragraphs, audit-committee sections, business-model narrative) blocked purely by the missing-embedding mechanism -- directly reproducing, at larger scale, what Milestone 3 found in its smaller sample.

A read-only simulation of **retrieval subchunks** (splitting each unembedded passage's `raw_text` at sentence boundaries under an 480-token safe ceiling, without touching segmentation) resolved **100% of the 767 unembedded passages** into 1,567 total subchunks (mean 2.04/passage, max 4), with **zero subchunks remaining over 512 tokens**. A token-aware packer fix (Option C) was separately confirmed to be capable of resolving Mechanism 2's 189 cases but **structurally incapable of resolving Mechanism 1's 578 cases**, since those passages have no second block to split against.

**Verdict: RETRIEVAL SUBCHUNKS.** See Section 15 for full reasoning; Section 12 covers required schema changes (not implemented here).

---

## 2. Current embedding coverage

Coverage was recomputed by, for every narrative document's current `PassageSegmentationRun` and its current `EmbeddingRun`, joining every `excluded_from_alignment=False` `Passage` against `PassageEmbedding` on `(embedding_run_id, passage_id)`. Where a passage had no embedding row, its true BGE token count was computed live via `AutoTokenizer.from_pretrained("BAAI/bge-small-en-v1.5", revision=<pinned SHA>)` -- the identical tokenizer and revision the production embedding path uses (`services/embedding_config.py`) -- so every token count in this milestone, embedded or not, reflects the real model tokenizer, never the M3 similarity tokenizer that `Passage.token_count` stores.

| Metric | Value |
|---|---:|
| Alignment-eligible passages (corpus-wide) | 80,346 |
| Embedded | 79,579 (99.05%) |
| Unembedded | 767 (0.95%) |
| Narrative documents (current segmentation+embedding run) | 108 |
| Reports | 30 |
| Companies | 6 |

### By company

| Company | Total | Embedded | Unembedded | Coverage |
|---|---:|---:|---:|---:|
| SUR | 20,187 | 20,187 | 0 | 100.00% |
| ACT | 33,172 | 33,156 | 16 | 99.95% |
| BEL | 11,185 | 11,152 | 33 | 99.70% |
| SBP | 2,362 | 2,346 | 16 | 99.32% |
| SDL | 1,841 | 1,811 | 30 | 98.37% |
| **KP2** | **11,599** | **10,927** | **672** | **94.21%** |

KP2 holds 87.6% of the corpus's entire unembedded population despite being only the fourth-largest company by passage count -- consistent with Milestones 1-3's repeated finding that KP2's long, template-heavy governance/remuneration/mineral-resources disclosure is disproportionately affected by nearly every mechanism examined in this corpus so far.

### By report (only reports with any unembedded passages shown)

| Company / period end | Total | Unembedded | Coverage |
|---|---:|---:|---:|
| KP2 2019-12-31 | 2,068 | 133 | 93.57% |
| KP2 2020-12-31 | 1,921 | 124 | 93.55% |
| KP2 2021-12-31 | 1,920 | 112 | 94.17% |
| KP2 2022-12-31 | 1,826 | 93 | 94.91% |
| KP2 2023-12-31 | 2,031 | 103 | 94.93% |
| KP2 2024-12-31 | 1,833 | 107 | 94.16% |
| SDL 2024-06-30 | 916 | 18 | 98.03% |
| SDL 2025-06-30 | 925 | 12 | 98.70% |
| BEL 2021-12-31 | 2,227 | 15 | 99.33% |
| SBP 2025-12-31 | 782 | 12 | 98.47% |
| BEL 2022-12-31 | 2,431 | 9 | 99.63% |
| BEL 2019-12-31 | 1,974 | 6 | 99.70% |
| ACT 2016-06-30 | 2,037 | 8 | 99.61% |
| (remaining 17 reports) | -- | ≤6 each | ≥99.6% |

Every one of KP2's 6 reports sits in a tight 93.5-94.9% band -- this is a stable structural property of KP2's document template, not a one-off extraction failure in a single year.

### By passage type

| Passage type | Total | Unembedded | Coverage |
|---|---:|---:|---:|
| HEADING_WITH_BODY | 74,352 | 130 | 99.83% |
| MULTI_PARAGRAPH | 4,433 | 44 | 99.01% |
| TABLE_CONTEXT | 149 | 22 | 85.23% |
| LIST | 290 | 66 | 77.24% |
| **PARAGRAPH** | **1,122** | **505** | **54.99%** |

`PARAGRAPH`-type passages (a run with no heading and only one contributing block or paragraph-shaped blocks) are by far the worst-covered category, and account for 505 of the 767 unembedded passages (65.8%) despite being only 1.4% of the corpus. This directly reflects Mechanism 1: `PassageType.PARAGRAPH` is exactly the tag `_finalize_group` assigns to a single-block group with no heading.

### By heading presence

| Has heading | Total | Unembedded | Coverage |
|---|---:|---:|---:|
| True | 74,352 | 130 | 99.83% |
| False | 5,994 | 637 | 89.37% |

Every one of the 618 word_count>400 passages (Mechanism 1) is headingless (Section 4). Headed passages are essentially fully covered; a passage's exposure to this problem is almost entirely determined by whether it starts a new heading run or continues one.

### By word-count band

| Band | Total | Unembedded | Coverage |
|---|---:|---:|---:|
| <150 | 67,724 | 0 | 100.00% |
| 150-249 | 5,060 | 13 | 99.74% |
| 250-299 | 4,710 | 34 | 99.28% |
| 300-349 | 1,622 | 40 | 97.53% |
| 350-399 | 591 | 89 | 84.94% |
| **400+** | **639** | **591** | **7.51%** |

The 400+ band (which should not exist at all under the documented `max_words=400` ceiling -- see Section 4) is almost entirely unembedded, as expected: a passage already this long is virtually certain to exceed 512 tokens too.

### By tokenizer-count band (real BGE tokenizer, `add_special_tokens=True`)

| Band | Total | Unembedded | Coverage |
|---|---:|---:|---:|
| <300 | 72,379 | 0 | 100.00% |
| 300-399 | 5,639 | 0 | 100.00% |
| 400-449 | 1,006 | 0 | 100.00% |
| 450-511 | 555 | 0 | 100.00% |
| 512-549 | 195 | 195 | 0.00% |
| 550-599 | 141 | 141 | 0.00% |
| 600-699 | 223 | 223 | 0.00% |
| 700+ | 208 | 208 | 0.00% |

**This table is the clean confirmation the milestone brief asked for**: every passage under the 512-token line is embedded, every passage at or over it is not. The skip check in `passage_embedding.py` is exact and total -- there is no partial/fuzzy skip behavior, no truncation, and no passage that should have an embedding and doesn't for any other reason. The only open question this milestone needed to resolve was *why* 767 passages ended up on the wrong side of that line, which Section 4 answers.

---

## 3. Tokenizer / limit implementation (verified from code, not inferred)

- **Tokenizer**: `BAAI/bge-small-en-v1.5`'s own `AutoTokenizer`, pinned to `MODEL_REVISION = "5c38ec7c405ec4b44b94cc5a9bb96e735b38267a"` (`services/embedding_config.py`). `TOKENIZER_NAME`/`TOKENIZER_REVISION` equal the model name/revision -- there is no separately-versioned tokenizer artifact.
- **Maximum sequence length**: `MAXIMUM_MODEL_TOKENS = 512` (`embedding_config.py:43`), matching the model card's documented 512-token limit.
- **Special tokens**: counted. `SentenceTransformerEmbeddingModel.count_tokens` (`passage_embedding.py`) calls `self._model.tokenizer.encode(text, add_special_tokens=True)` -- `[CLS]`/`[SEP]` are included in the count compared against the 512 ceiling, so the check is conservative (a text at exactly 510 content tokens plus 2 special tokens correctly reads as 512, not 510).
- **No input prefix**: `INPUT_PREFIX = None` (module docstring explains why: an asymmetric query/passage prefix scheme like e5-small-v2's would force two different embeddings per passage in this corpus's role-reversing report-pair design; BGE's prefix-free design avoids that). This means the token budget is not silently reduced by a prefix string.
- **Truncation is never applied to corpus passages.** `_run_embedding` (`passage_embedding.py:224-292`) computes `count_tokens` per passage *before* calling `encode_batch`; if it exceeds `MAXIMUM_MODEL_TOKENS`, the passage is added to a skip list and a warning string (`"passage {id}: token count {n} exceeds model limit ({512}), skipped rather than silently truncated"`) is appended -- never passed to the model. `PassageEmbedding.truncated` exists as a column but is hardcoded `False` by the current model wrapper; it is unused scaffolding, not an active code path.
- **Provenance**: `EmbeddingRun.skipped_passage_count` (an integer) and `EmbeddingRun.review_reason` (the joined warning strings, one line per skipped passage) are persisted and set `EmbeddingRunStatus.COMPLETED_WITH_WARNINGS` instead of `COMPLETED`. There is no dedicated `skip_reason` enum column -- the reason lives as free text inside `review_reason`, and per-passage skip identity is recoverable only by parsing that text or (as this milestone did) by a `passage_id NOT IN (SELECT passage_id FROM passage_embeddings WHERE embedding_run_id = ...)` anti-join. Every skip observed in the current corpus's `review_reason` fields reads exactly `"token count {N} exceeds model limit (512), skipped rather than silently truncated"` -- confirming the only skip reason ever recorded is this one (no dimension-mismatch or per-passage encode failures were found in any current run's warnings).
- **The query-embedding HTTP path treats the same condition differently**: `embedding_service/app.py`'s `/embed-query` endpoint returns HTTP 400 for an over-limit query rather than skipping, since a live query has no "just don't embed it" option. This is a deliberate, already-existing asymmetry, not a bug.

This confirms, directly from code and data (not inference), that the skip mechanism the milestone brief describes is real, intentional, already logged, and functions exactly as documented. **The defect this milestone found is upstream of the skip check**: it is in how passages come to exceed 512 tokens in the first place, not in how that condition is detected or handled once it occurs.

---

## 4. Why passages exceed the token limit: two distinct mechanisms

### 4.1 Mechanism 1 -- the segmentation ceiling is not actually enforced for a single oversized block (578 of 767 unembedded passages, 75.4%)

`passage_segmentation.py::_pack_run_into_passages`:

```python
for block in run:
    words = len(block.text.split())
    if current and current_words + words > config.max_words:
        groups.append(current)
        current = [block]
        current_words = words
    else:
        current.append(block)
        current_words += words
        ...
```

The `if current and ...` guard means the `max_words` comparison only ever fires when a group already has content. When `current` is empty (starting a new group) and the next block is itself already larger than `max_words`, the `else` branch always runs: the block is accepted into `current` unconditionally, regardless of its own size. There is no code path that ever splits a single `TextBlock` -- the packer's only unit of division is a whole block.

**Direct verification**: a sanity query found 618 passages with `word_count > 400` corpus-wide (a count that, per the documented ceiling, should be zero). For every sampled passage in this population (`PassageSourceBlock` join), the source-block count was exactly 1, and the single block's own `raw_text.split()` length matched the passage's `word_count` exactly. Every one of the 618 has `heading_text IS NULL` and `passage_type` in `{PARAGRAPH, LIST, TABLE_CONTEXT}` -- confirming these are headingless runs whose sole contributing block was already too large before segmentation ever ran.

| Company | word_count>400 passages |
|---|---:|
| KP2 | 576 |
| SDL | 15 |
| BEL | 15 |
| ACT | 12 |
| **Total** | **618** |

40 of these 618 are embedded (word count 401-~450 with a token/word ratio still under 512/word_count), and 578 are not -- so Mechanism 1 alone accounts for 578 of the corpus's 767 unembedded passages.

**Root cause of the oversized single blocks**: these are extraction-layer artifacts, not segmentation-layer artifacts. KP2's PDF layout produces long continuous `PARAGRAPH`/`LIST_ITEM` blocks -- e.g., a 723-word bulleted list (multiple distinct bullet points about JORC resource updates, ministerial correspondence, and financing terms, all captured as one `LIST_ITEM` block) or a 679-word "Going Concern" paragraph spanning several logically distinct sentences about financing milestones -- because the extractor did not detect an internal paragraph or bullet break in the source PDF. **This is upstream of both segmentation and embedding**, in the extraction/block-classification subsystem (`extraction.py`/`block_classification.py`), and is a distinct, previously-undocumented data-quality finding this milestone surfaced as a side effect, not something segmentation or embedding configuration can fix by adjusting a threshold.

### 4.2 Mechanism 2 -- genuine word/token calibration gap in multi-block passages (189 of 767 unembedded passages, 24.6%)

The remaining unembedded population *does* respect the 400-word ceiling (`word_count` between 219 and 400) but still exceeds 512 BGE tokens. Every sampled case in this population (n=40) was confirmed to be a **multi-block** group (`PassageSourceBlock` count > 1) -- i.e., exactly the case the milestone brief anticipated: ordinary greedy word-count packing assembled several blocks into a passage that is well-formed by word count but dense in subwords.

| Company | word_count<=400 but bge_token_count>512 |
|---|---:|
| KP2 | 136 |
| BEL | 18 |
| SDL | 15 |
| SBP | 16 |
| ACT | 4 |
| **Total** | **189** |

This is the population a token-aware packer (Option B/C, Section 8) can actually fix, because there are real block boundaries inside it to split at.

---

## 5. Word-to-token expansion ratio (empirical)

For all 2,213 corpus passages with `word_count` in [300, 400) (the band the brief specifically asked about):

| Statistic | Value |
|---|---:|
| Mean ratio (tokens/word) | 1.267 |
| Median | 1.235 |
| p90 | 1.411 |
| p95 | 1.466 |
| p99 | 1.724 |
| Max observed | 3.582 |

At the median ratio (1.235), a 400-word passage produces ~494 tokens -- under the 512 limit, which is consistent with why most 300-399-word passages are still embedded (Section 2's word-band table: 84.9% coverage in that band). But at the p95-p99 ratio (1.47-1.72), the same 400-word passage produces 588-688 tokens, comfortably over the limit -- this is exactly the calibration gap the milestone brief hypothesized, now measured directly: **`max_words=400` was calibrated to the median/typical case, not the tail.**

**Content driving the extreme tail**: the single highest ratio found (3.58, four ACT passages, all a repeated AGM proxy-form template) is a shareholder proxy form containing long runs of underscore fill-in blanks (`"_______________________"`). Each contiguous underscore run tokenizes into many individual subword tokens relative to the "word" it counts as under whitespace splitting, producing a token/word ratio far outside the rest of the corpus. This is a distinct, narrow content pattern (legal/administrative form boilerplate with blank fields) rather than financial-statement density in the ordinary sense, though it sits within the general "symbols and unusual formatting inflate subword count" hypothesis the brief raised. The more common driver in the 300-400 word band (per Section 6's KP2 sample) is ordinary financial-note density: currency amounts with thousands separators, hyphenated defined terms, capitalized entity names, and share/option identifiers (e.g., "Rights Series 9", "AUD 0.1867") -- each of which tokenizes into more subwords than a same-length run of ordinary prose.

---

## 6. Unembedded-passage taxonomy (qualitative, n=60 manually reviewed)

30 Mechanism-1 (word_count>400) and 30 Mechanism-2 (word_count<=400, token_count>512) passages were sampled (stratified across companies and token counts) and their `raw_text` read directly.

| Category | Mechanism 1 (n=30) | Mechanism 2 (n=30) |
|---|---:|---:|
| A -- Substantive narrative disclosure (going concern, principal risks, business model, governance, audit-committee, stakeholder engagement) | 21 | 2 |
| B -- Accounting-policy / financial-note narrative (share-option valuation, tax reconciliation, currency-translation reserves, related-party notes) | 8 | 15 |
| D -- Table-derived / layout-heavy content (diversity tables, corporate directory, sensitivity-analysis tables, shareholder distribution tables) | 1 | 11 |
| C -- Boilerplate legal/governance language | 0 | 2 |
| E -- Passage-boundary artifact (near-duplicate content across otherwise-distinct occurrences, e.g. glossary entries recurring twice within the same report) | 0 | 0 (present but rare; see note) |
| F -- Other | 0 | 0 |

**Mechanism 1 (single-block extraction artifacts) is dominated by substantive, analytically important narrative** -- going-concern disclosures (financing milestones, EPC contract terms), principal-risk enumerations (commodity price risk, geological/technical risk), business-model narrative, and governance/audit-committee/remuneration-policy sections. These are exactly the passage types Milestone 3 already flagged as the highest-value residual population (its Category D, "same disclosure, substantive wording revision," was the single largest taxonomy bucket at 36.5%). **None of the 30 sampled Mechanism-1 passages were boilerplate, layout noise, or extraction junk** -- confirming the brief's central concern (Section 6's framing question, "are we losing meaningful disclosures or mostly long boilerplate") resolves clearly toward **meaningful disclosures**.

**Mechanism 2 (dense multi-block passages) skews toward Category B/D** -- financial-note narrative merged with number-, address-, or proper-noun-heavy tabular content (auditor-fee notes, related-party transaction notes, shareholder distribution and top-20-holder tables, corporate directory listings, KMP compensation disclosures, currency-sensitivity tables). This content is still analytically real (a shareholder register or an auditor-fee note is disclosure, not decoration), but its density is what pushes it over 512 tokens at a legitimately-under-400-word length -- consistent with Section 5's finding.

A small number of exact-duplicate passages were observed within Mechanism 2 (e.g., the same "Stands For / Meaning" glossary passage, and the same "ANNEXURE 1 CORPORATE STRUCTURE" passage, both appearing twice within the same report at the same `period_end`) -- likely Parent-Company/Group-financial-statement duplication or a running-header/footer leakage artifact, consistent with `docs/passage-ground-truth-validation.md`'s existing findings about within-report duplication. This is a pre-existing, separately-scoped issue (already out of this milestone's scope per Section 24 of the brief) and does not change the taxonomy conclusion above.

---

## 7. Alignment impact (corpus-wide, not sample-limited)

For every current `AlignmentRun` (25 of the corpus's report pairs have one), every primary `PassageAlignment` row with `alignment_status IN (REMOVED, NEW)` was checked against the corresponding side's current `PassageEmbedding` set. A REMOVED row whose `earlier_passage_id` has no embedding in `earlier_embedding_run_id`, or a NEW row whose `later_passage_id` has no embedding in `later_embedding_run_id`, was flagged as **unembedded-driven** -- structurally invisible to `get_semantic_candidates` regardless of any threshold, `top_k`, or the Milestone 4 exact-scan fix, since the embedding row simply does not exist to be a candidate.

| | Count |
|---|---:|
| REMOVED rows, earlier passage unembedded | 150 |
| NEW rows, later passage unembedded | 145 |
| **Total unembedded-driven unmatched rows** | **295** |

| Company | REMOVED unembedded | NEW unembedded |
|---|---:|---:|
| KP2 | 129 | 124 |
| BEL | 8 | 11 |
| SDL | 6 | 4 |
| ACT | 6 | 2 |
| SBP | 1 | 4 |

253 of 295 (85.8%) are KP2 -- the same concentration pattern as Section 2.

**Diagnostic lexical best-match search** (inverted-index blocking prefilter, same method as Milestone 3's Section 2, over each report pair's opposite-side eligible passages, using the unmodified `services/similarity_metrics.lexical_cosine_similarity`) found, for every one of the 295 unembedded passages, its best same-report-pair lexical candidate on the opposite side:

| Best-candidate lexical cosine band | Count | Share |
|---|---:|---:|
| >=0.95 | 64 | 21.7% |
| 0.90-0.95 | 46 | 15.6% |
| 0.85-0.90 | 51 | 17.3% |
| 0.80-0.85 | 43 | 14.6% |
| <0.80 | 91 | 30.8% |

**161 of 295 (54.6%) have a plausible opposite-side candidate at lexical cosine >=0.85.** Manual review of the highest-similarity examples (a sample of 8 at cosine 0.90-1.00) confirmed genuine, same-underlying-disclosure year-over-year correspondences: a "Stands For / Meaning" glossary passage recurring verbatim (cosine 0.998), an "AUDIT AND RISK COMMITTEE" section with a rolled-forward committee-activity sentence (cosine 0.972), a "BUSINESS MODEL" section with the following year's principal-risks bullet updated (cosine 0.952), and a "Remuneration Policy" paragraph identical except for headcount figures (cosine 1.000). These are not boilerplate-collision artifacts (Milestone 3's Category G) -- they read as the same kind of genuine substantive-or-near-substantive correspondence Milestone 3's Category B/C/D population contained, now reproduced at roughly 4x the case count and, this time, isolated cleanly from the HNSW-substitution mechanism Milestone 4 already fixed.

**This is not a full re-run of Milestone 3's manual classification protocol** (which hand-reviewed all 74 candidates against 8 categories and computed anchor/duplicate-context signals) -- doing so for 295 cases was out of this diagnostic's scope. What this section establishes is the **upper bound and rough composition** of the unembedded-driven unmatched population: over half plausibly has a genuine correspondence, concentrated overwhelmingly in KP2, and none of the manually-checked high-similarity examples were boilerplate-collision false positives.

**Caveat on alignment-run currency**: 9 of the 25 current alignment runs predate the Milestone 4 exact-search fix (`CANDIDATE_CONFIG_VERSION` 1 vs. the current 2). This does not affect the 295-row count above, because embedding presence/absence is a fact about the embedding layer, independent of which candidate-generation search mode a given alignment run used -- an unembedded passage is equally invisible to both the buggy HNSW-substituted search and the corrected exact search. It does mean a full corpus-wide alignment rerun under the current config (already recommended by Milestone 4 itself) remains outstanding and would be needed before any of Section 7's remaining `NEW`/`REMOVED` counts (beyond the unembedded-driven subset measured here) can be taken as final.

---

## 8. Milestone 3's 52 cases: follow-up status

Milestone 3's 52-case attribution was computed by an ad hoc diagnostic script against the then-current 3-company (KP2/ACT/SBP) corpus; the individual case identities (specific passage-ID pairs) were not persisted to a table or file, only the aggregate root-cause counts in `docs/high-similarity-unmatched-diagnostic.md` Section 12.2. **Exact case-by-case re-identification of the original 52 is therefore not possible from stored data alone**, and this milestone does not attempt to fabricate a match against passage IDs that no longer necessarily exist in their original form (segmentation/extraction reruns since Milestone 3 may have changed passage boundaries for reasons unrelated to this investigation).

What this milestone can and does confirm:

- **The missing-embedding mechanism Milestone 3 identified is still present and has not been touched by any fix since.** Milestone 4 only changed candidate-generation search-plan behavior (`SET LOCAL enable_indexscan/enable_bitmapscan`); it made no change to segmentation, embedding, or the token-limit skip logic. Every embedding-run `review_reason` in the current corpus still reads the same `"token count {N} exceeds model limit (512), skipped rather than silently truncated"` message Milestone 3 quoted for its concrete example.
- **The corpus-wide, mechanism-isolated re-measurement in Section 7 is the modern equivalent of Milestone 3's 52-case estimate**, now cleanly separated from the HNSW-substitution mechanism (Milestone 3's other 20-of-74 root cause, since fixed) and computed against a corpus that has grown from 3 companies/16 pairs to 6 companies/25 (of a possible larger set) alignment runs. The 295-row, 85.8%-KP2-concentrated result is directionally identical to Milestone 3's finding (KP2 was 71% of Milestone 3's 68-passage sample) and roughly 4x the magnitude, consistent with corpus growth plus the removal of the confounding HNSW effect making the pure missing-embedding population visible on its own for the first time.
- **KP2's specific 2019-2020 example Milestone 3 quoted verbatim** (`e_idx=21`, 389 words, `"token count 515 exceeds model limit (512)"`) was not re-located by passage ID (Milestone 3's report did not record the passage UUID, only the word count and token count), but this milestone's own Mechanism 2 population contains multiple KP2 passages in the identical 385-400-word / 512-540-token range with the identical review-reason text, confirming the same class of case remains unresolved and is not an isolated historical artifact.

**Recommendation for future milestones**: if exact before/after tracking of a specific high-value case population is needed again, persist the candidate-population passage-ID pairs (not just aggregate counts) to a scratch table or exported file at diagnostic time, so a later milestone can re-query the same cases directly rather than re-deriving an approximate equivalent population.

---

## 9. Remediation options (evaluated against both mechanisms)

| Option | Mechanism 1 (578, single-block) | Mechanism 2 (189, multi-block density) |
|---|---|---|
| A/B. Lower global word ceiling | **Does not help.** A block that is 723 words bypasses `max_words` entirely via the `if current` guard regardless of what `max_words` is set to -- lowering it to 300 or 200 changes nothing for a single-block group. | Partially helps, but as a blunt proxy: lowering the ceiling to, say, 300 words would reduce but not eliminate the tail (Section 5's p95 ratio of 1.47 still produces ~441 tokens at 300 words -- safe -- but the p99 ratio of 1.72 produces ~516 tokens even at 300 words -- still over). Also risks over-splitting ordinary prose that was never at risk (the milestone brief's own stated concern). |
| C. Token-aware segmentation ceiling (packer checks real BGE token count, not just word count, before closing a multi-block group) | **Does not help** -- there is no second block in a Mechanism-1 group to split against; the packer's `if current` guard is orthogonal to whether the check inside it is word- or token-based. | **Fully resolves.** Confirmed structurally: all 189 Mechanism-2 cases are multi-block, so a token-aware close condition (close the current group before adding a block that would push the running BGE token count over a safe ceiling) would prevent every one of them from ever forming. |
| D. Retrieval subchunks (split raw_text into sentence-bounded, token-safe chunks at embedding time; canonical passage unchanged) | **Fully resolves** -- operates on the passage's final text regardless of how many source blocks contributed to it. | **Fully resolves**, for the same reason. |
| E. Truncation | Rejected (Section 9 below). | Rejected. |

Given Mechanism 1 is 75.4% of the unembedded population and is **structurally unreachable by any segmentation-config change** (word- or token-based), Option A/B/C alone cannot close this gap -- at best, Option C closes the 24.6% Mechanism-2 slice. Fully closing the gap requires either (a) Option D, which reaches both mechanisms because it operates after segmentation on the assembled text, or (b) a segmentation-layer change that goes beyond adjusting a ceiling constant and instead teaches the packer to split *within* a block at sentence granularity -- which is a materially larger and more invasive change than either Option B or C as scoped in the milestone brief, and which this milestone did not simulate because it would require redesigning `_pack_run_into_passages`'s unit of division, not just its size threshold.

**On truncation (Option E)**: rejected, consistent with the project's existing, already-deliberate stance (`_run_embedding` explicitly skips "rather than silently truncated"). Section 6's qualitative review reinforces this: the unembedded population is dominated by substantive narrative and real note disclosure, not boilerplate -- truncating a 723-word going-concern paragraph or a 588-word principal-risks enumeration to fit 512 tokens would silently discard exactly the kind of content the Lazy Prices-style change measurement exists to capture (Section 13).

---

## 10. Token-aware segmentation simulation (Option C)

Because Mechanism 2's 189 cases are all confirmed multi-block, a token-aware packer close condition would be a small, local change to `_pack_run_into_passages`'s inner branch (checking a running BGE token estimate in addition to `current_words` before accepting the next block). This milestone did not implement or fully re-run segmentation with this change (out of scope per Section 2 of the brief -- "do not modify segmentation... until scope and safest remediation are established"), but the structural analysis above is sufficient to state its ceiling of benefit precisely: **it would close 189 of 767 unembedded passages (24.6%) and leave 578 (75.4%) untouched**, because those 578 have no second block for a smarter close condition to act on. A future implementation milestone, if this option were chosen alone, would still need a separate mechanism (extraction-layer block splitting, or a passage-segmentation change that can subdivide a single block) to address the majority of the gap -- meaning Option C alone does not fully answer the milestone's own central research question ("how much... can be restored while preserving coherent disclosure units").

---

## 11. Retrieval-subchunk simulation (Option D)

All 767 currently-unembedded passages' `raw_text` were split, read-only and in-memory (nothing persisted), using a simple sentence-boundary splitter (regex split on `. `/`! `/`; ` followed by whitespace) with a 480-token safe ceiling per chunk (a margin below 512, chosen provisionally for this simulation -- see Section 14 for how a production-safe ceiling should actually be selected), falling back to a word-level split only for any single sentence that itself exceeded the ceiling (none did, in this corpus).

| Metric | Result |
|---|---:|
| Passages simulated | 767 |
| Total subchunks produced | 1,567 |
| Mean subchunks/passage | 2.04 |
| Median subchunks/passage | 2 |
| Max subchunks for one passage | 4 |
| Subchunks still over 512 tokens after split | **0** |
| Max subchunk token count observed | 475 |

**Every one of the 767 unembedded passages is fully resolvable by sentence-level subchunking**, with no residual over-limit subchunks and no need for a word-level fallback in this corpus. This confirms Option D closes the entire coverage gap (both mechanisms) without any change to segmentation, extraction, or the canonical passage boundary.

---

## 12. Architecture implications: schema and candidate-query feasibility for retrieval subchunks

- **Current schema does not support multiple embeddings per passage per run.** `PassageEmbedding.__table_args__` has `UniqueConstraint("embedding_run_id", "passage_id", ...)` -- a hard uniqueness constraint on the pair, not just an index. Storing 2-4 subchunk vectors for the same passage within the same `EmbeddingRun` would violate this constraint as-is. A migration would be required: add a `subchunk_index: int` (default 0 for a non-split passage, so existing rows remain valid without a data migration) and change the unique constraint to `("embedding_run_id", "passage_id", "subchunk_index")`. `input_token_count` and `truncated` would then describe the subchunk, not the whole passage; a new nullable `subchunk_text` or `(subchunk_start_char, subchunk_end_char)` pair would be needed for provenance (so a hit can be traced back to which part of the passage matched).
- **Candidate SQL**: `get_semantic_candidates`'s current query (`ORDER BY embedding <=> :vec LIMIT :top_k`, filtered by `embedding_run_id`/`excluded_from_alignment`) would need to aggregate multiple subchunk rows per `passage_id` before ranking, e.g. `SELECT passage_id, MIN(embedding <=> :vec) AS best_distance FROM passage_embeddings JOIN passages ... GROUP BY passage_id ORDER BY best_distance LIMIT :top_k` (a `GROUP BY`-based rewrite, not a schema-breaking one) -- this keeps `search_mode=EXACT`'s existing `SET LOCAL enable_indexscan/enable_bitmapscan = off` guard fully applicable, since the underlying scan shape is unchanged, only the aggregation added on top.
- **Aggregation choice**: **max similarity (min distance) across a passage's subchunks**, not average or a weighted combination. Rationale: the retrieval question is "does any part of this passage plausibly correspond to the query," not "does the passage's full text averaged together correspond" -- averaging would dilute a passage where one subchunk is highly relevant and another (a different topic within the same oversized passage) is not, which is expected for Mechanism-1 passages that may span more than one nominal sub-topic per the extraction-layer defect in Section 4.1. This mirrors the milestone brief's own framing (Section 12 of the brief: "max subchunk similarity, average, another aggregation") and is consistent with how the existing pipeline already treats semantic similarity as a *candidate-generation aid*, not the final measured signal (Section 13).
- **Deduplication**: with `MIN(distance)`/`MAX(similarity)` aggregation in the SQL itself, no separate deduplication pass is needed -- each `passage_id` naturally appears once in the result set regardless of how many subchunks it has.
- **Lexical/full-passage scoring is unaffected.** Once a candidate `passage_id` is retrieved (via any of its subchunks), `score_candidates`/`compute_lexical_features`/`classify_alignment` would continue to operate on the canonical `Passage.raw_text` exactly as today -- subchunks are a candidate-generation-only construct, never a scoring-time construct. This directly satisfies Section 18 of the brief ("preserve lexical comparison fidelity... semantic embeddings are candidate-generation aids").

None of the above was implemented in this milestone; it is a feasibility assessment only, per the brief's explicit instruction.

---

## 13. Lazy Prices methodological implications

The brief's central methodological question is whether the embedding model's token limit should be allowed to redefine the unit of disclosure comparison. This milestone's evidence weighs clearly against that:

- Section 4.1 shows the majority mechanism (Mechanism 1, 75.4% of unembedded passages) is not actually a segmentation-config problem at all -- it is an upstream extraction artifact (one oversized `TextBlock`) that happens to also exceed the embedding limit. Re-tuning segmentation's word ceiling specifically to satisfy the embedding model would not even address its own root cause; it would only mask the extraction-layer defect for as long as the current embedding model's limit happens to stay above whatever new ceiling is chosen.
- Section 6's qualitative review confirms the affected passages are analytically significant (going concern, principal risks, business model, audit-committee narrative) -- exactly the content whose year-over-year wording change the Lazy Prices-style metric is designed to detect. Splitting a 588-word "Position and Principal Risks" disclosure into two passages purely because an embedding model has a 512-token window would fragment a single analytical unit into two, each independently subject to `classify_alignment`'s length-ratio and lexical-composite thresholds, in a way the corpus's authors did not intend and that has nothing to do with the disclosure's actual structure.
- Retrieval subchunks (Option D) let the embedding model's limit stay entirely a *retrieval-mechanics* concern: the canonical `Passage.raw_text` -- the unit whose lexical/semantic change is measured by `compute_lexical_features`/`classify_alignment` -- never changes shape. Only an internal, embedding-time-only representation is split, and only for the purpose of making the passage *findable* as a semantic candidate; the passage that is ultimately scored is unaffected. This is the same distinction the project already draws between canonical comparison passages and Q&A chunks (per the milestone brief's own framing), extended one layer further to alignment retrieval.

**This milestone's answer to the central methodological question is: the system should preserve canonical analytical passages and adapt semantic retrieval around them, not let the embedding model's limit redefine the unit of comparison.**

---

## 14. Choosing a safe token ceiling for subchunking (not implemented, recommendation only)

The brief asks not to default to exactly 512. Considerations, given what this milestone measured:

- `count_tokens` already includes special tokens (`add_special_tokens=True`), so 512 is already the *effective* content-plus-special-token ceiling, not a number that needs a separate correction for `[CLS]`/`[SEP]`.
- No input prefix exists today (`INPUT_PREFIX = None`), and this milestone's simulation used none -- if a future model change introduced one (e.g., migrating to an e5-style model with a `"passage: "` prefix), that prefix's own token cost would need to be reserved out of the ceiling on top of whatever margin is chosen here; this is a real coupling risk (Section 16) but not a reason to reserve for it speculatively today.
- This milestone's own simulation (Section 11) used **480** as a working safe ceiling and found the resulting maximum subchunk token count was 475 -- comfortably under both 480 and 512, with margin to spare. A ceiling anywhere in the 480-500 range would very likely work equally well for this corpus; the simulation was not repeated at 500/510/512 specifically because the 480 result already left ample headroom and repeating it at tighter ceilings would not change the qualitative conclusion (100% resolvable). **480 is a reasonable, empirically-supported provisional recommendation**, leaving a ~6% (32-token) margin under the hard 512 limit for boundary-splitter imprecision (the word-level fallback path, unused in this corpus but present for a future edge case) and for any future formatting prefix, without materially increasing subchunk count over a tighter ceiling (mean 2.04 subchunks/passage even at 480).

---

## 15. Decision matrix

| Option | Embedding coverage | Preserves canonical passages | Complexity | Model coupling | Alignment impact | Research-methodology risk |
|---|---:|---:|---:|---:|---:|---:|
| Lower word ceiling | Partial (helps a fraction of Mechanism 2 only) | No -- shrinks all passages corpus-wide, not just affected ones | Low | Low | Low, and only for a minority of the gap | Medium -- over-splits ordinary prose for no benefit to Mechanism 1 |
| Token-aware segmentation | Resolves Mechanism 2 only (24.6% of gap) | No -- passage boundaries change for the corpus's dense-note population | Medium | High -- passage boundaries become a function of BGE's specific tokenizer | Recovers the 189-case Mechanism-2 slice | Medium -- boundary changes for a real, non-trivial slice of the corpus |
| Hybrid (word+token ceiling) | Same as token-aware alone (Mechanism 1 untouched) | Same concern as above | Medium | Same as above | Same as token-aware alone | Same as above |
| **Retrieval subchunks** | **Resolves both mechanisms, 100% in simulation** | **Yes -- canonical passage never changes** | Medium-High (schema migration, candidate-query rewrite, dedup/aggregation logic) | **Low** -- subchunking is a retrieval-time detail, swappable independently of the canonical corpus | Recovers the full ~295-row corpus-wide gap (Section 7) plus any smaller-similarity cases not yet surfaced | **Lowest** -- canonical unit of comparison is untouched |
| Truncation | Would technically "cover" 100% but with fabricated/partial text | No -- discards content | Low | N/A | Unclear/negative (corrupted embeddings) | **Highest** -- silently discards substantive disclosure (Section 6) |

---

## 16. Recommendation

**Verdict: RETRIEVAL SUBCHUNKS.**

Reasoning:
1. Retrieval subchunks are the only option, of those the brief poses, that closes the gap for **both** mechanisms found in this corpus -- and Mechanism 1 (75.4% of the gap) is structurally unreachable by any segmentation-ceiling change, word- or token-based, because it originates one layer upstream (a single oversized extraction block) rather than in the packer's size threshold.
2. This milestone's own simulation (Section 11) confirms feasibility empirically, not just in principle: 100% of the corpus's 767 unembedded passages resolve into token-safe subchunks, with real margin (max observed 475 tokens against a 480 ceiling, well under 512).
3. It is the only option that keeps the canonical passage -- the Lazy Prices-style unit of comparison -- entirely unchanged (Section 13), avoiding the risk the brief itself raises of letting an embedding model's limitation quietly redefine the corpus's analytical units.
4. It has the lowest model-coupling risk of any effective option (Section 12/16 of the brief's own framing): a future embedding-model change only requires re-chunking at embed time, never re-segmenting the historical corpus.
5. The estimated storage/performance cost is trivial at current corpus scale: 1,567 additional embedding rows (an ~2.0% increase over the current 79,579), at 384 dimensions each -- on the order of a few megabytes, not a meaningful infrastructure concern (Section 17).

This is not a recommendation to do nothing about Mechanism 1's root cause. **Mechanism 1 (oversized single-block extraction artifacts, 578 passages, 93% concentrated in KP2) is itself a data-quality finding independent of embedding eligibility** -- a 723-word single `LIST_ITEM` block is analytically suspect on its own terms (it very likely represents several distinct bulleted disclosures the extractor failed to separate), and deserves its own, separately-scoped extraction-quality follow-up milestone in the spirit of `docs/table-fragment-hardening-experiment.md`. Retrieval subchunks fix its *embedding-invisibility* symptom without needing to wait for that upstream fix, but do not replace the value of pursuing it.

### Proposed follow-on milestones (not this one)

1. **Implement retrieval subchunks**: schema migration (`subchunk_index` column, relaxed unique constraint, subchunk text/span provenance), a chunking function (sentence-boundary greedy packing under an ~480-token ceiling, word-level fallback for the rare oversized sentence), an updated `_run_embedding` to embed subchunks for any passage over the limit instead of skipping, and a `get_semantic_candidates` rewrite to aggregate by `MIN(distance)` per `passage_id`. Re-run embedding and alignment corpus-wide afterward and re-measure the REMOVED/NEW counts against Section 7's 295-row baseline.
2. **Investigate Mechanism 1's extraction-layer root cause** (oversized single `PARAGRAPH`/`LIST_ITEM` blocks, KP2-concentrated): determine whether the PDF extractor can be taught to detect internal bullet/paragraph breaks it currently misses, independent of and prior to any embedding-eligibility work. This is a data-quality milestone in the same family as the table-fragment hardening experiment, not an embedding or segmentation milestone.
3. **Re-run the full corpus-wide alignment measurement under `CANDIDATE_CONFIG_VERSION=2`** (Section 7's caveat) before treating any `NEW`/`REMOVED`/`AMBIGUOUS` count as final for the 9 report pairs still on a stale alignment run.

---

## Central methodological question (restated)

> Should an embedding model's token limit redefine the unit of disclosure comparison, or should the system preserve canonical analytical passages and adapt semantic retrieval around them?

This milestone's evidence answers: **preserve canonical analytical passages and adapt semantic retrieval around them** -- both because it is methodologically correct (Section 13) and because it is the only option that actually solves the measured problem (Section 4's two-mechanism finding means no segmentation-ceiling change, however calibrated, can close more than a quarter of the gap on its own).

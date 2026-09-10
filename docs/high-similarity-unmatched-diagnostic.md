# Residual High-Similarity ADD/DELETE Diagnostic (Milestone 3)

**Status**: Diagnostic/research only. No production code, schema, thresholds, candidate generation, scoring weights, assignment logic, reconciliation logic, or data were modified. All database access was read-only (`SELECT`, plus session-scoped `SET LOCAL` planner flags used only to diagnose a query-plan issue -- never committed, never touched production sessions). Corpus: the same 3-company, 16-report-pair KP2/ACT/SBP set rebuilt for Milestones 1 and 2 (Kore Potash, AfroCentric Investment Corporation, Sabvest Capital). No other company's data touched. This milestone follows `docs/passage-pipeline-data-quality-audit.md`, `docs/passage-ground-truth-validation.md`, `docs/table-fragment-hardening-experiment.md`, and `docs/exact-hash-reconciliation-experiment.md` (Milestones 1-2, both **ACCEPTED**).

---

## 1. Executive summary

Milestone 2's closing diagnostic (`docs/exact-hash-reconciliation-experiment.md` Section 18) estimated roughly 68 residual REMOVED passages sitting at 0.90-1.00 lexical-cosine similarity to some residual NEW passage, informational-only, no acceptance decision made. This milestone recomputes that population directly from the current (post-Milestone-2) corpus with a fuller signal set -- lexical cosine, Jaccard, edit similarity, semantic similarity (where computable), heading similarity, length ratio, position difference, duplicate-hash context, and neighboring-anchor support -- and manually classifies every candidate.

**Recomputed population: 68 unique residual REMOVED passages** have a same-report-pair residual NEW passage at lexical cosine similarity in [0.90, 1.00) (matching Milestone 2's 68-passage estimate almost exactly), expanding to **74 candidate pairs** once up to 3 plausible partners per REMOVED passage are considered (to surface duplicate-context ambiguity). Of these 74, manual review found:

- **56 (76%) are genuinely the same underlying disclosure unit** (Q1 = Yes), spread across the full similarity distribution down to 0.90 -- similarity alone never cleanly separates true from false candidates, confirming the milestone brief's expectation that a bare threshold would not be defensible on its own.
- **17 (23%) are structurally ambiguous** (Q1 = Ambiguous) -- overwhelmingly (13 of 17) exact-duplicate boilerplate/kicker fragments (`"IC IC"`, `"PERFORMANCE PERFORMANCE"`) where occurrence-level correspondence cannot be determined from content alone, the same category Milestone 2 already characterized for its exact-hash duplicate clusters.
- **1 (1%) is a genuine false candidate** (Q1 = No) -- two different enumerated-list disclosures that happen to share boilerplate scaffolding.

Critically, **of the 56 true correspondences, only 5 (9%) would classify as UNCHANGED** under the current methodology's own `classify_alignment` logic; 22 (39%) would be LIGHTLY_MODIFIED, 22 (39%) SUBSTANTIALLY_MODIFIED, and 7 (13%) are themselves structurally ambiguous (passage-boundary shifts) and would likely remain flagged rather than cleanly resolve to a 1:1 correspondence. **A future recovery pass that silently converted every recovered correspondence to UNCHANGED would misclassify roughly 90% of the true positives found here** -- this is the central empirical confirmation of the methodological concern framed in Section 1 of the task brief.

The most consequential finding of this milestone is **not** about matching thresholds at all: root-cause analysis of *why* the primary matcher missed these 56+ true correspondences found that **none** trace to the content-score acceptance gate or to genuine greedy-assignment competition. Instead:
- **52 of 74 (70%)** trace to a **missing embedding row** -- one side's passage exceeds the embedding model's 512-subword-token limit (word-count segmentation caps at 400 words, but subword tokenization of dense financial/legal prose regularly exceeds 512 tokens well before that), so the passage was silently skipped during embedding and is structurally invisible to semantic candidate generation, independent of any threshold.
- **20 of 74 (27%)** trace to a **previously undocumented database query-plan defect**: `get_semantic_candidates`'s "exact" cosine search (`search_mode=EXACT`, the production default) is, in practice, silently executed by PostgreSQL's planner via the pre-existing HNSW approximate index rather than a sequential scan, because nothing in the EXACT code path disables index-scan selection. For a `WHERE embedding_run_id = ... AND excluded_from_alignment = false`-filtered query, this can return as few as 2 candidate rows when the true candidate pool has 1,000+, silently dropping the genuinely-best match. Forcing `SET LOCAL enable_indexscan = off` in a diagnostic session reproduces the correct, expected top-5 result every time this was checked. **This is a correctness bug independent of any matching-algorithm threshold**, and its likely corpus-wide impact is almost certainly larger than the 74-candidate sample studied here.
- Only **2 of 74 (3%)** trace to genuine `top_k=5` pruning that survives an exact re-query.

**Verdict: STOP** on fuzzy correspondence recovery as a matching-algorithm change. The true-positive rate (76%) looks superficially attractive, but (a) the dominant root causes are infrastructure defects, not matching-threshold gaps -- fixing them is orthogonal to and cheaper than any fuzzy-reconciliation logic, and should happen first; and (b) even after fixing them, safely operationalizing "same disclosure, different classification" (as opposed to "same disclosure, therefore UNCHANGED") is not yet reduced to a rule this diagnostic can respons­ibly recommend implementing. See Section 15/16/18 for the reasoning and the two concrete, narrower next steps this milestone does recommend.

---

## 2. Candidate population

Starting point: the current (post-Milestone-2) `AlignmentRun` for each of the 16 KP2/ACT/SBP report pairs, restricted to rows with `alignment_status IN ('REMOVED', 'NEW')` and `primary_alignment = True` (i.e., the same residual population Milestone 2's Section 18 diagnostic measured, after exact-hash reconciliation has already removed every exact-duplicate collision).

| Company | Report pairs | Residual REMOVED | Residual NEW |
|---|---:|---:|---:|
| KP2 | 5 | 380 | 322 |
| ACT | 9 | 2,718 | 3,465 |
| SBP | 2 | 11 | 10 |
| **Total** | **16** | **3,109** | **3,797** |

(These match `docs/exact-hash-reconciliation-experiment.md` Section 9's post-reconciliation counts exactly, confirming no drift in the corpus between milestones.)

**Candidate generation method** (documented prefilter, per Section 3 of the task brief): computing full pairwise lexical cosine similarity for all REMOVED x NEW combinations within a report pair is quadratic (up to ~2,718 x 3,465 ≈ 9.4M comparisons for ACT alone) and unnecessary at this similarity range. An inverted-index blocking prefilter was used: for each report pair, tokens with document frequency above 25% of the NEW-side population were treated as too common to be discriminating and excluded from the index; for each REMOVED passage, the 8 NEW passages sharing the most indexed tokens were retained as candidates, and full `lexical_cosine_similarity`/`jaccard_similarity`/`edit_similarity` (all from `services/similarity_metrics.py`, unmodified) were computed only for those. This is a recall-oriented, not precision-oriented, prefilter -- it can only ever miss a true near-duplicate that shares no discriminating token with its match (implausible above 0.90 cosine similarity, since bag-of-words cosine at that level requires substantial token overlap by construction) -- and was validated by cross-checking that it reproduced Milestone 2's independently-computed 68-passage estimate almost exactly (see Section 3).

**Full signal set computed per candidate**: `lexical_cosine_similarity`, `jaccard_similarity` (bigram), `edit_similarity` (token-level Levenshtein), `lexical_composite` (mean of the three), `semantic_similarity` (via `embedding_cosine_similarity`, where both sides' embeddings exist), `heading_similarity`, `length_ratio`, `position_difference`, earlier/later `passage_index`, earlier/later page numbers, earlier/later headings, `content_hash` occurrence counts on each side (duplicate-context), and neighboring accepted-alignment anchor support (nearest accepted primary match on each side of the candidate, bracketing test). All via the application's own `passage_alignment.py`/`similarity_metrics.py`/`alignment_candidates.py` functions, called read-only, never modified.

**Result**: 74 candidate pairs across **68 unique REMOVED passages** at lexical cosine >= 0.90 (up to 3 highest-cosine NEW candidates retained per REMOVED passage, to surface duplicate-context ambiguity rather than silently picking one). This closely reproduces Milestone 2's informational 68-passage estimate (Section 18 of `docs/exact-hash-reconciliation-experiment.md`), computed independently and via a different code path -- strong cross-validation that both diagnostics are measuring the same real population, not an artifact of either script.

| Company | Unique REMOVED passages w/ candidate >=0.90 | Candidate pairs (top-3) |
|---|---:|---:|
| KP2 | 48 | 48 |
| ACT | 19 | 25 |
| SBP | 1 | 1 |
| **Total** | **68** | **74** |

All 74 candidates (not a sample) were manually reviewed, per Section 5 of the task brief ("prefer full review over sampling" -- 74 is well within the ~50-100 full-review range).

---

## 3. Similarity-band distribution

Bucketed by best lexical cosine similarity per unique REMOVED passage (n=68, comparable methodology to Milestone 2's Section 18 table):

| Band | Count | Report-pair count represented | Company distribution |
|---|---:|---:|---|
| 0.99-<1.00 | 16 | 6 | ACT 13, KP2 3 |
| 0.97-<0.99 | 11 | 6 | KP2 8, ACT 3 |
| 0.95-<0.97 | 18 | 8 | KP2 13, ACT 4, SBP 1 |
| 0.90-<0.95 | 23 | 9 | KP2 19, ACT 4 |
| **Total** | **68** | 16 (all pairs) | KP2 48 (71%), ACT 19 (28%), SBP 1 (1%) |

Candidate quality (true-vs-false rate, Section 5) does **not** fall sharply as similarity decreases across these bands -- see Section 5's table. What *does* vary sharply by band is **composition**: the 0.99-1.00 band is dominated by exact-duplicate-kicker ambiguity (13 of 22 candidate rows in that band are the `"IC IC"`/`"PERFORMANCE PERFORMANCE"` duplicate-fragment pattern), while every band from 0.97 downward is dominated by genuine substantive wording changes (Category D, Section 4). Median passage length rises with the true-correspondence share: the ambiguous/false population is concentrated in very short (<20-word) duplicated fragments, while the true-correspondence population is concentrated in long (200+-word) narrative and note-disclosure passages (Section 10).

KP2 contributes 71% of the candidate population despite being the smallest company by report-pair count (5 of 16 pairs) -- consistent with Milestones 1-2's repeated finding that KP2's long, template-heavy governance/remuneration/mineral-resources boilerplate is disproportionately affected by every mechanism examined in this corpus so far.

---

## 4. Manual/ground-truth taxonomy

All 74 candidates classified into exactly one category (Section 6 of the task brief):

| Category | Count | Share |
|---|---:|---:|
| D -- Same disclosure, substantive wording revision | 27 | 36.5% |
| G -- Repeated boilerplate/duplicate false candidate | 13 | 17.6% |
| B -- Mechanical annual rollover | 11 | 14.9% |
| E -- Structural passage-boundary shift | 9 | 12.2% |
| A -- Cosmetic/formatting-only difference | 5 | 6.8% |
| C -- Same disclosure, minor wording revision | 5 | 6.8% |
| H -- Same topic, different disclosure | 3 | 4.1% |
| I -- Extraction/layout artifact | 1 | 1.4% |
| F -- Split/merge-shaped correspondence | 0 | 0% |
| J -- Other | 0 | 0% |
| **Total** | **74** | 100% |

**Category D (substantive wording revision) is the single largest category at 36.5%** -- this is the headline taxonomy finding. The residual high-similarity population is not, as might be assumed, dominated by trivial cosmetic noise: it is dominated by passages that *changed in a way that matters* (new disclosure content, changed figures, changed personnel, changed policy language) while remaining lexically close enough to their prior-year counterpart to sit above 0.90 cosine similarity. This directly motivates Section 15's discussion: any recovery mechanism must preserve, not erase, this signal.

**Category G (13, all short duplicated fragments like `"IC IC"`/`"PERFORMANCE PERFORMANCE"`)** is entirely concentrated in ACT's 2023->2024 pair (12 of 13) plus one ACT 2017->2018 instance, and is mechanistically distinct from Milestone 2's exact-hash duplicate clusters: these are **not** exact-hash duplicates (the earlier occurrence is a doubled token, e.g. `"IC IC"`, the later is a single token, e.g. `"IC"`), so Milestone 2's reconciliation correctly left them alone. Inspection is consistent with the ground-truth report's `OVERLAPPING_TEXT_ARTIFACT`/extraction-artifact findings (Section 3 of `docs/passage-ground-truth-validation.md`): these two-word-doubled kicker labels most likely reflect a single underlying capitals-icon label (`IC` = Intellectual Capital, `PERFORMANCE` a section-eyebrow kicker) rendered twice by an overlapping-text extraction artifact, matched against ordinary single-occurrence instances of the same kicker elsewhere in the document -- structurally undecidable which specific occurrence corresponds to which, exactly the pattern Milestone 2 Section 11 already documented for its own duplicate clusters.

---

## 5. True-vs-false correspondence rates (Section 9 of the task brief)

| Similarity band | True same-disclosure (Q1=Yes) | False candidate (Q1=No) | Ambiguous (Q1=Ambiguous) |
|---|---:|---:|---:|
| 0.99-1.00 | 9 (41%) | 0 (0%) | 13 (59%) |
| 0.97-0.99 | 11 (100%) | 0 (0%) | 0 (0%) |
| 0.95-0.97 | 17 (94%) | 0 (0%) | 1 (6%) |
| 0.90-0.95 | 19 (83%) | 1 (4%) | 3 (13%) |
| **Total** | **56 (76%)** | **1 (1%)** | **17 (23%)** |

**This table is the clearest answer this milestone can give to "would a simple threshold ever be defensible": no.** The 0.99-1.00 band -- intuitively the "safest" band -- has the *lowest* true-correspondence rate (41%) of the four, entirely because it is where the ACT duplicate-kicker artifacts concentrate (all 13 ambiguous candidates in the whole population sit in this top band, since exact/near-exact token repetition is what produces cosine ~1.0 in the first place). The 0.97-0.99 band, one notch lower, is 100% true correspondence. **Lexical similarity alone is not monotonic with correspondence confidence in this corpus** -- a naive "similarity >= X" rule would perform *worse* at higher X specifically because it walks straight into the duplicate-fragment population, confirming the task brief's instruction not to assume a threshold would be safe.

The single false candidate (#59, KP2, 0.90-0.95 band) is a "principal risks" bullet list matched against a differently-enumerated "section 172 statement" factor list -- both recur in similar structural contexts (numbered/bulleted enumerations inside the same "REVIEW OF OPERATIONS AND STRATEGIC REPORT (CONT)" heading family) with enough shared boilerplate scaffolding to reach 0.937 lexical cosine despite being genuinely different disclosures.

---

## 6. Diff examples

Per Section 8 of the task brief, in the style of the original worked examples (a sentiment-shift example and a mechanical-rollover example):

### Sentiment/content-shift example (Category D, KP2, 2019-12-31 -> 2020-12-31, e_idx=55 / l_idx=56, lexical cosine 0.952)

> **Earlier**: "...• change in potash commodity prices and market conditions; The operations of the Group are conducted in ROC..."
>
> **Later**: "...On 14 December 2020, the Company reported receipt of correspondence received from the Minister of Mines expressing dissa[tisfaction]... Kola Potash project. Since then, [the] Company continued to communicate constructively..."

Near-identical surrounding sentence structure (same "Business Model" section, same paragraph position, `heading_similarity` unavailable but `position_difference`=0.006, both-side anchor support agrees) masks a substantive change: a generic market-risk bullet is replaced with a specific, negatively-framed disclosure about ministerial correspondence expressing dissatisfaction with the project -- exactly the kind of scalar-similarity-hides-material-difference case the task brief anticipates. Lexical cosine (0.952) alone gives no hint of this; only reading the diff does.

### Mechanical rollover, trivial (Category B, ACT, 2021-06-30 -> 2022-06-30, e_idx=1085 / l_idx=906, lexical cosine 0.960, semantic 0.992)

> **Earlier**: "...COVID-19 pandemic developments... we will continue to closely monitor developments around COVID-19. Although the intention is to hold the AGM as scheduled on Thursday, 11 November 2021..."
>
> **Later**: "...Covid-19 pandemic developments... we will continue to closely monitor developments around COVID-19. Although the intention is to hold the AGM as scheduled on Thursday, 10 November 2022,..."

A boilerplate forward-looking COVID paragraph recurs nearly verbatim year over year with the AGM date/year rolled forward and a capitalization style change (`COVID-19` -> `Covid-19`). Both similarity scores are high and both would correctly classify as LIGHTLY_MODIFIED under the current methodology (semantic 0.992 clears the LIGHTLY_MODIFIED gate at 0.85 but the date/punctuation changes keep lexical composite below the UNCHANGED gate) -- an example where near-1.0 scalar similarity *does* correspond to genuinely low-information change.

### Mechanical rollover, value-bearing (Category B, KP2, 2020-12-31 -> 2021-12-31, e_idx=291 / l_idx=300, lexical cosine 0.965)

> **Earlier**: "USD Opening balance -) -) (18,415,577) (15,310,945) Currency translation differences arising during the year -) -) 11,321,754 (3,104,632) Closing balance -) -) (7,093,823) (18,415,577)..."
>
> **Later**: "USD Opening balance -) -) (7,093,823) (18,415,577) Currency translation differences arising during the year -) -) (11,529,680) 11,321,754 Closing balance -) -) (18,623,503) (7,093,823)..."

Same table template, same row labels, consecutive-year figures rolled forward one column -- structurally identical to the trivial COVID example above, but here **the changed tokens are the entire substance of the disclosure** (a currency-translation-reserve roll-forward): the foreign-currency reserve balance moved from a $7.1m to an $18.6m closing deficit. This is the task brief's explicit warning made concrete: "do not automatically treat all year changes as trivial." A rule that discounted Category B uniformly would silently erase a genuine, material year-over-year financial change here while correctly discounting the COVID example above -- the two cases are lexically and structurally almost indistinguishable from each other, yet analytically opposite.

### Cosmetic-only, invisible to exact-hash reconciliation (Category A, KP2, 2019-12-31 -> 2020-12-31, e_idx=120 / l_idx=128, lexical cosine 1.0000, edit/jaccard 1.0000)

> **Earlier**: "...align director and executive objectives with, shareholder and business objectives..."
> **Later**: "...align director and executive objectives with shareholder and business objectives..." (comma removed)

Token-for-token identical (tokenizer discards punctuation, so `lexical_cosine`/`jaccard`/`edit_similarity` all read exactly 1.0), yet `content_hash` differs because it is computed over NFKC-normalized *text*, punctuation included. **This is the mechanistic reason a meaningful slice of this milestone's population sits just below Milestone 2's exact-hash reconciliation net**: a single comma, a bullet-glyph substitution (`»` vs `•`, seen in a second Category A example at ACT e552/l529), or a hyphenation-character variant is enough to defeat exact-hash matching while being completely invisible to every lexical similarity metric the pipeline computes. This is a distinct, narrower, and much lower-risk phenomenon than general fuzzy reconciliation (see Section 18, Option G).

---

## 7. Signal analysis

Comparing true (Q1=Yes, n=56) vs. ambiguous/false (Q1!=Yes, n=18) candidates on each signal:

| Signal | True median | Ambiguous/false median | Discriminating? |
|---|---:|---:|---|
| Lexical cosine | 0.958 | 1.000 | **No** -- ambiguous is *higher* (duplicate-fragment artifact) |
| Jaccard | 0.87 | 0.0 or 1.0 (bimodal) | Weak -- short duplicated fragments produce Jaccard=0 (no shared bigrams at 1-2 words) |
| Edit similarity | 0.87 | 0.5 or 1.0 (bimodal) | Weak, same bimodality |
| Length ratio | 0.94 | 0.50 (duplicate-fragment cases) or 1.0 | **Yes** for the dominant false-candidate pattern -- 12 of 13 Category G candidates have length_ratio=0.50 (a 2-token vs 1-token pair) |
| Position difference | 0.019 | 0.25 (duplicate-fragment cases) or 0.02 | **Yes** for Category G -- the doubled-kicker instances sit ~0.25 document-relative-position away from their matched single instance, because they are different occurrences of a repeating template element, not the same relocated passage |
| Anchor support | both-side-agree: 91% of true | both-side-agree: 41% of Category G | **Yes**, strong (Section 8) |
| Duplicate context | unique-both: 100% of true | duplicate-side: 76% of ambiguous | **Yes**, very strong (Section 9) |

**The single most discriminating combination found**: `length_ratio >= 0.85 AND (earlier_hash_count == 1 AND later_hash_count == 1)` -- i.e., near-equal-length passages that are each individually unique (not part of a within-report duplicate cluster). Applied to this population, that combination is satisfied by 56 of 56 true candidates and by only 1 of 18 ambiguous/false candidates (the single false-candidate case, #59, which has unique hash counts on both sides but fails on content grounds the combination cannot see -- a reminder that even the best signal combination found here is not perfect). This is consistent with, and a natural generalization of, Milestone 2's own duplicate-cluster-vs-unique-1:1 distinction: **uniqueness of occurrence remains the strongest single piece of evidence this pipeline has ever found for safe correspondence, in both milestones.**

Lexical/Jaccard/edit similarity alone, and position difference alone, are each individually **not** reliable discriminators in this population -- consistent with Section 5's finding that raw similarity is not monotonic with correspondence confidence.

---

## 8. Anchor analysis

For every candidate, the nearest accepted primary alignment on each side of the pair (by `passage_index`) was checked for bracketing agreement (does the predicted-later-position implied by the two nearest accepted anchors fall near the candidate's actual later `passage_index`, within a small slack tolerance):

| Anchor support | True (Q1=Yes) | Ambiguous (Q1=Ambiguous) | False (Q1=No) |
|---|---:|---:|---:|
| Both-side bracket agrees | 53 (95%) | 6 (35%) | 0 |
| Both-side bracket disagrees | 3 (5%) | 11 (65%) | 1 (100%) |
| One-side anchor / no anchor | 0 | 0 | 0 |

**This is the single cleanest signal found in this milestone.** 95% of genuine correspondences are bracketed by agreeing accepted neighbors on both sides (the A<->A' and C<->C' pattern from the milestone brief's own worked example), while 65% of ambiguous candidates and the one false candidate show disagreeing brackets. The three true-correspondence exceptions to the "agrees" pattern are all large-scale document relocations (e.g. candidate #32, a boilerplate "Reporting suite" paragraph relocated from near the end to near the start of the report, `position_difference`=0.93) -- exactly the scenario `compute_content_score`'s deliberate exclusion of position from the acceptance gate already protects against for the primary matcher (per `docs/passage-pipeline-data-quality-audit.md` Section 3.4's "Pending legislative amendments" precedent) -- and for which anchor bracketing is not expected to hold by construction, since the passage is not near its neighbors' new positions at all.

This corroborates the milestone brief's expectation directly: **anchor-aware evidence is likely the safest available signal for any future recovery mechanism**, more so than any lexical/semantic/length signal examined in Section 7.

---

## 9. Duplicate-context analysis

| Duplicate context | True (Q1=Yes) | Ambiguous (Q1=Ambiguous) | False (Q1=No) |
|---|---:|---:|---:|
| Unique in both reports | 56 (100%) | 4 (24%) | 1 (100%) |
| Duplicated on at least one side | 0 (0%) | 13 (76%) | 0 (0%) |

**Every single true correspondence in this population is unique-hash on both sides.** Every Category G (duplicate-boilerplate) ambiguous candidate is, definitionally, duplicated on at least one side. This is as close to a clean separator as this diagnostic found for the *ambiguous* half of the population specifically -- it does not discriminate the one false candidate (which happens to be unique-hash on both sides but is still a different disclosure), so duplicate-context alone is necessary-but-not-sufficient evidence, exactly mirroring Milestone 2's own finding that duplicate clusters are the dominant source of residual ambiguity. **A fuzzy rule that is safe on unique passages would very plausibly be unsafe if applied uniformly to duplicate-heavy passages** -- this population reconfirms that distinction rather than complicating it.

---

## 10. Passage-length analysis

| Length band | True (Q1=Yes) | Ambiguous (Q1=Ambiguous) | False (Q1=No) |
|---|---:|---:|---:|
| <20 words | 0 | 13 | 0 |
| 20-49 words | 5 | 0 | 0 |
| 50-99 words | 1 | 0 | 0 |
| 100-199 words | 1 | 0 | 0 |
| 200+ words | 49 | 4 | 1 |

**Every single sub-20-word candidate in this population is ambiguous (all 13 are the Category G duplicate-kicker pattern).** No true correspondence and no false candidate falls in that band. This is a strong, population-specific finding: at lexical cosine >= 0.90, a very short (<20-word) candidate pair in this corpus is essentially always a duplicate-fragment artifact, never a genuine correspondence and never (in this sample) a genuinely different-but-similar disclosure. The 200+-word band, unsurprisingly, dominates the true-correspondence population (KP2's long governance/remuneration/notes boilerplate) but is not perfectly clean (4 ambiguous, 1 false candidate also live there) -- so length alone, like every other single signal examined, is necessary-but-not-sufficient. **A future recovery mechanism should very plausibly be length-sensitive** (e.g., require >=20 words as a floor before even considering fuzzy recovery), consistent with `docs/passage-ground-truth-validation.md` Section 9's independent finding that word count is "a necessary signal... but not remotely a sufficient one" for a completely different problem (heading-only classification) in this same corpus.

---

## 11. Semantic-vs-lexical analysis

Semantic similarity was computable for only 22 of 74 candidates (the remainder hit the missing-embedding root cause documented in Section 12) -- itself an important, if incidental, finding: **the population this milestone studies is disproportionately drawn from passages the semantic layer cannot see at all.** Where available:

| Pattern | Count | Example |
|---|---:|---|
| Both high (semantic >=0.90, lexical >=0.90) | 14 | ACT e552/l529 (Category A, sem 0.996, lex 1.000) -- strong, safe-looking candidate |
| High lexical, lower/moderate semantic | 7 | ACT `"IC IC"`/`"IC"` cluster (sem ~0.97, lex 1.000) -- template-overlap pattern, all Category G/ambiguous |
| High semantic, lower lexical | 1 | ACT e737/l699 (Category I, sem 0.896, lex 0.915, `heading_similarity`=0.0) -- running-header-leakage artifact contaminating only the heading field |
| Both moderate | 0 | none in this >=0.90-lexical-filtered population by construction |

The "high lexical, lower semantic" pattern here is instructive precisely because it does **not** match the general "template overlap/numbers/fragments" caution from the task brief in the way expected: these are the Category G duplicate-kicker cases, where the *lexical* signal is artificially perfect (near-identical short token sequences) but the *semantic* signal, while still fairly high (0.94-0.97), correctly reflects that these are separate document occurrences of a template element rather than a literal fresh-eyes stronger signal. Semantic similarity is not privileged in this analysis (per the task brief's instruction) -- in this specific population it behaves as a **mild corroborating signal, not a stronger one than lexical cosine**, and its unavailability for 70% of candidates (Section 12) is a larger practical limitation than any signal-interaction pattern found.

---

## 12. Primary-matcher miss root causes

For every one of the 74 candidates, `get_semantic_candidates` and `score_candidates` (the application's own, unmodified functions) were re-invoked read-only to determine exactly why the earlier passage was not proposed to, or not claimed by, the later passage in the actual persisted alignment run. This surfaced a finding well outside this milestone's original scope, which is reported here because it materially changes the interpretation of every other section above.

### 12.1 A database query-plan defect, not a matching-algorithm limitation

`alignment_candidates.py`'s module docstring states plainly: "Defaults to exact cosine distance (`<=>`), not the HNSW index... real-corpus benchmarking found the HNSW index gives no measurable recall or latency benefit at this scale." This is true of the *application code's intent* -- `search_mode=EXACT` never issues the `SET LOCAL hnsw.*` statements that `search_mode=HNSW` does. It is **not** true of what PostgreSQL actually executes: an HNSW index (`ix_passage_embeddings_embedding_hnsw_cosine`) exists on `passage_embeddings.embedding`, and for an `ORDER BY embedding <=> :vec LIMIT :top_k` query with an additional `WHERE embedding_run_id = ... AND excluded_from_alignment = false` filter, PostgreSQL's planner is free to choose that index over a sequential scan whenever it estimates it as cheaper -- and, verified directly via `EXPLAIN` on this corpus, it does so for the exact query pattern `get_semantic_candidates` issues.

Because the WHERE filter is applied *after* the HNSW scan visits a bounded set of approximate-nearest candidate nodes (not before), a highly selective filter can cause the query to silently return far fewer rows than the true candidate pool -- in one directly reproduced case (ACT, e_idx=552/l_idx=529, the Category A "HUMAN RIGHTS AND COMMUNITY DEVELOPMENT" example from Section 6), the production-pattern query returned only **2** candidate rows total (best similarity 0.758) against an earlier-side pool of 1,055 eligible, embedded passages, silently omitting the true best match at similarity 0.996. Re-running the identical query with `SET LOCAL enable_indexscan = off; SET LOCAL enable_bitmapscan = off` (forcing a true sequential/exact scan, in a read-only diagnostic session only) correctly returned the expected top-5, with the true match at rank 1. The module's own HNSW-mode docstring even anticipates this exact failure mode ("a filtered HNSW scan can return fewer than top_k rows even when more exist") -- but describes it only for `search_mode=HNSW`, not recognizing that the same risk applies to the undefended `search_mode=EXACT` default whenever the HNSW index exists in the same database.

This is a genuine correctness defect in candidate retrieval, independent of `top_k`, `min_semantic_similarity`, any scoring weight, or the greedy-assignment algorithm -- and, because it depends only on the query shape and the presence of the HNSW index (both true for every alignment run in this corpus), **its likely impact is corpus-wide, not limited to this milestone's 74-candidate sample.** No production code was changed to investigate or confirm this; it is reported as a finding, not fixed, per this milestone's diagnostic-only scope.

### 12.2 Corrected root-cause table (re-queried under forced exact scan)

| Primary miss mechanism | Count | % of 74 |
|---|---:|---:|
| Missing embedding (later passage exceeds 512-subword-token model limit) | 47 | 63.5% |
| Missing embedding (earlier passage exceeds limit) | 5 | 6.8% |
| HNSW-planner-substitution candidate loss (Section 12.1) | 20 | 27.0% |
| Genuine `top_k=5` pruning (confirmed under forced exact scan) | 2 | 2.7% |
| Below semantic floor | 0 | 0% |
| Failed content-score acceptance gate | 0 | 0% |
| Lost greedy-assignment competition | 0 | 0% |
| Duplicate collision | 0 (handled separately -- see Section 4's Category G) | -- |

**Zero of the 74 candidates trace to the acceptance-threshold or the greedy-assignment mechanism.** Every miss in this population is a candidate-generation-side failure: the true match was either never embedded at all, or was embedded but never actually retrieved due to the planner defect, or (rarely, 3% of cases) was retrieved but ranked outside the top 5 by a legitimately closer competitor. This is the single most important finding for deciding what kind of fix, if any, is worth pursuing (Section 16): **not a recovery pass bolted onto the existing pipeline, and not a threshold change, but two narrow, structural fixes to candidate generation itself** (Section 16).

### 12.3 Missing-embedding mechanism in detail

Verified directly against one concrete case (KP2, e_idx=21 of the 2019->2020 pair, 389 words): the passage's segmentation run has 351 eligible (`excluded_from_alignment=False`) passages, of which only 321 have an embedding row; the corresponding `EmbeddingRun.review_reason` records `"token count 515 exceeds model limit (512), skipped rather than silently truncated"` -- an intentional, already-logged design choice in `passage_embedding.py` (never a silent failure), but one whose *consequence* for alignment (structural invisibility to every downstream candidate-generation step, regardless of any threshold) does not appear to have been previously connected to the residual REMOVED/NEW population in `docs/passage-pipeline-data-quality-audit.md`'s Section 4.1 mechanism inventory (which lists `excluded_from_alignment` passages as invisible to matching, but a passage skipped only from *embedding* -- not `excluded_from_alignment` -- is a distinct, previously undocumented variant of the same problem). KP2's remuneration/governance/mineral-resources boilerplate passages, already identified as unusually long and dense in Milestones 1-2, are disproportionately affected: the 400-word passage-segmentation ceiling (`passage_config.py`'s `max_words`) does not prevent this, because subword tokenization of dense financial/legal prose (numbers, hyphenated terms, defined-capital-term phrases) routinely produces more model tokens than words -- the segmentation ceiling and the embedding model's token ceiling are not calibrated against each other.

---

## 13. Estimated recoverable population

Of the 56 candidates judged the same underlying disclosure unit (Section 5), all 56 map to 56 distinct REMOVED passages and 56 distinct NEW passages (no duplication within the recoverable set -- confirmed directly), so the theoretical maximum recovery, if every human-confirmed correspondence in this diagnostic were correctly paired:

| Company | Recoverable pairs | Reduction in REMOVED | Reduction in NEW | Residual REMOVED after | Residual NEW after | Unmatched-rate change |
|---|---:|---:|---:|---:|---:|---:|
| KP2 | 44 | 380 -> 336 (-11.6%) | 322 -> 278 (-13.7%) | 336 | 278 | ~30.6% -> ~27.3% |
| ACT | 11 | 2,718 -> 2,707 (-0.4%) | 3,465 -> 3,454 (-0.3%) | 2,707 | 3,454 | ~54.66% -> ~54.5% |
| SBP | 1 | 11 -> 10 (-9.1%) | 10 -> 9 (-10.0%) | 10 | 9 | ~5.37% -> ~4.9% |
| **Total** | **56** | **3,109 -> 3,053 (-1.8%)** | **3,797 -> 3,741 (-1.5%)** | 3,053 | 3,741 | -- |

**The benefit is modest in aggregate and concentrated almost entirely in KP2.** Recovering every true correspondence found in this diagnostic reduces KP2's unmatched rate by roughly 3.3 percentage points, but barely moves ACT's (0.16 points) -- consistent with KP2's outsized contribution to the underlying candidate population (Section 3) and, per Section 12, its outsized exposure to the missing-embedding mechanism specifically. **This is an upper bound derived from a >=0.90-lexical-cosine-filtered sample; it is not evidence about the much larger sub-0.90 residual population** (2,923+ REMOVED passages per Milestone 2's Section 18), which this milestone did not investigate and which the task brief explicitly scoped out.

---

## 14. Report-level metric impact

Reclassifying the 56 recoverable correspondences by what they would become under the *current, unmodified* `classify_alignment` logic (Section 15 discusses why this reuse matters) rather than collapsing them all to UNCHANGED:

| Outcome if recovered | Count | Share of 56 |
|---|---:|---:|
| UNCHANGED | 5 | 8.9% |
| LIGHTLY_MODIFIED | 22 | 39.3% |
| SUBSTANTIALLY_MODIFIED | 22 | 39.3% |
| Structurally ambiguous (boundary-shift, Category E) | 7 | 12.5% |

Feature-level impact per pair, diagnostically: for each of the 49 clean 1:1 recoveries (56 minus the 7 structural-boundary cases, which would likely remain flagged rather than resolve cleanly), the correct report-level delta is **NEW -1, REMOVED -1, and (UNCHANGED | LIGHTLY_MODIFIED | SUBSTANTIALLY_MODIFIED) +1** depending on the individual pair's own semantic/lexical/length scores -- never a blanket "two changes disappear." Applied in aggregate to this diagnostic's 49 clean recoveries: `UNCHANGED +5`, `LIGHTLY_MODIFIED +22`, `SUBSTANTIALLY_MODIFIED +22`, `NEW -49`, `REMOVED -49`. **The 44% of recoveries that would land as SUBSTANTIALLY_MODIFIED is the methodologically important number here**: nearly half of what looks, from a raw REMOVED+NEW count, like pure noise reduction is in fact newly-surfaced, correctly-typed *measured change* -- disclosure-change signal the current REMOVED/NEW framing was already partially capturing (as two separate, uncorrelated line items) but not correctly characterizing as a single evolving disclosure. This is exactly the "REMOVED+NEW -> recovered correspondence -> normal pairwise scoring/classification" path Section 1 of the task brief describes as the desired behavior, evaluated empirically rather than assumed.

---

## 15. Preserving the Lazy Prices research objective

For Categories C and D specifically (32 of the 56 true correspondences, 57%): recovering these as correspondences and running them through the **existing, unmodified** `compute_lexical_features` -> `lexical_composite` -> `classify_alignment` -> `assess_confidence` pipeline (exactly as Milestone 2's own reconciled rows already do for exact-hash matches, per `_run_alignment`'s reconciled-pair block in `passage_alignment.py`) would correctly preserve their textual-change signal: 22 of 27 Category D candidates (81%) would classify as SUBSTANTIALLY_MODIFIED and the remainder as LIGHTLY_MODIFIED, never UNCHANGED, because their underlying semantic/lexical scores (where computable) and length ratios genuinely reflect the wording changes documented in Section 6. **No second definition of "modified" needs to be invented** -- the existing classification functions, evaluated on the recovered pair's own text (not on a fabricated similarity score), already produce the analytically correct answer for every Category C/D case examined. This directly answers Section 15's core question: reuse, not reinvention, is both possible and sufficient for this population.

The risk this milestone's data actually surfaces is not "the classifier would get it wrong" -- it is **"a naive recovery rule that skipped the classification step and defaulted recovered pairs to UNCHANGED would get 51 of 56 cases wrong"** (Section 5's 56 true correspondences, only 5 of which are genuinely UNCHANGED). This is the empirical confirmation, not just the conceptual risk, that Section 1 of the task brief was concerned about.

---

## 16. Future intervention comparison

| Option | Expected benefit (this population) | Risk | Interpretability | Cost | Research-validity impact |
|---|---|---|---|---|---|
| A. Second-pass high-similarity correspondence recovery | 56 pairs recoverable (Section 13), concentrated in KP2 | Medium -- 13 of 74 candidates are duplicate-fragment ambiguity a naive rule would mismatch | Medium -- needs the full signal combination from Section 7, not a bare threshold | Medium -- new reconciliation-style module, tests, migration for provenance | Positive if built correctly (Section 15); negative if collapsed to UNCHANGED |
| B. Increase `top_k` | None observed -- 0 of 74 misses trace to genuine top_k pruning beyond 5 in this population (Section 12.2's 2 cases) | Low, but low expected benefit for this specific problem | High | Low (one config value) | Negligible for this population |
| C. Lexical rescue candidates (very-high-lexical passages enter the candidate set even if semantic retrieval missed them) | Would recover the 20 HNSW-planner-substitution cases (Section 12.1) as a side effect, but treats the symptom, not the cause | Medium -- widens candidate generation beyond its documented semantic-first design | Medium | Low-Medium | Positive, but see Option G below for a more targeted fix to the same 20 cases |
| D. Anchor-aware unmatched recovery (bracketed by accepted neighbors only) | Would safely cover 53 of 56 true correspondences (95% anchor-agreement rate, Section 8) while naturally excluding 65% of the ambiguous population | **Lowest of the fuzzy options** -- anchor agreement was this milestone's single cleanest discriminator | High -- same audit story as Milestone 2's duplicate-cluster anchor interpolation | Medium -- directly extends Milestone 2's own `_predicted_later_position` machinery | Positive, most defensible of the fuzzy options examined |
| E. Duplicate-aware assignment improvements (better candidate competition instead of a post-pass) | Would not address this population -- 0 of 74 misses trace to assignment competition (Section 12.2) | N/A for this problem | -- | -- | Not applicable here |
| F. No change (population too small/risky) | -- | None | -- | None | Preserves current conservative posture |
| **G. Fix candidate-generation infrastructure directly** (verify/force exact scan for `search_mode=EXACT`; raise or diagnose the embedding token-limit interaction with `max_words`) | **Would recover most of 72 of 74 candidates' root cause (Section 12.2) with zero change to any matching threshold, weight, or algorithm** | **Lowest of every option** -- this is a correctness fix, not a new acceptance rule | Highest -- restores the documented, already-intended behavior | **Lowest** -- a query-plan/index-usage fix and a token-limit/segmentation-calibration check, not new matching logic | **Positive and foundational** -- every other option's benefit estimate is itself computed against a corpus whose candidate generation is confirmed to be silently lossy |

Option G is not one of the six options named in the original milestone brief, but the root-cause data in Section 12 makes it the option this diagnostic can recommend with the most confidence, and it should be resolved (as its own, separately scoped, non-diagnostic milestone) before evaluating whether Option A or D are worth building at all -- their apparent 56-pair benefit is measured against a candidate-generation layer already known to be dropping candidates for reasons unrelated to any matching threshold.

---

## 17. Recommendation

**Verdict: STOP** on implementing fuzzy correspondence recovery (Options A/C/D) as the next milestone.

Reasoning:
1. The true-positive rate (76%) is real and the anchor-agreement signal (95% for true correspondences) is the strongest this pipeline's diagnostics have found for any fuzzy-adjacent signal to date -- but **0% of the misses in this specific, most-favorable population trace to the matching algorithm itself** (Section 12.2). Building fuzzy-reconciliation logic now would be optimizing the wrong layer.
2. **90% of a naive "recovered -> UNCHANGED" rule's outputs would be wrong** (Section 14) -- correctly reusing `classify_alignment` is necessary, not optional, and this diagnostic did not have the scope to validate that reuse against a large, independently-labeled ground truth (56 hand-classified pairs is not enough to certify a production rule).
3. 23% of the candidate population (17 of 74) is structurally ambiguous duplicate-boilerplate, and any automatic rule broad enough to catch the 56 true correspondences risks also catching some of these -- the single false candidate found (#59, Section 5) demonstrates the failure mode is real, if rare, even after every signal in Section 7 is combined.
4. The aggregate benefit, even in the idealized maximum-recovery scenario (Section 13), is modest (-1.8% REMOVED corpus-wide) and concentrated in one company (KP2, 79% of the recoverable pairs) -- not obviously worth the interpretability and research-validity risk of a new acceptance mechanism at this time.

**This is not a recommendation to do nothing.** Two concrete, narrower next steps are directly supported by this milestone's data and are lower-risk than any fuzzy-matching option:

- **Investigate and fix the candidate-generation query-plan defect (Section 12.1)** as its own, tightly-scoped milestone, *before* revisiting fuzzy reconciliation. This is a correctness bug, not a threshold decision -- confirm its corpus-wide extent (this milestone sampled only the >=0.90-lexical-cosine, 3-company residual population; the true blast radius across all 10 companies and the full similarity range is unmeasured), then apply the minimal fix (e.g., an explicit planner hint or `SET LOCAL` guard around `search_mode=EXACT`'s query, or dropping the HNSW index if it provides no benefit per the module's own benchmarking claim) and re-measure `NEW`/`REMOVED`/`AMBIGUOUS` counts corpus-wide. This is the single highest-value, lowest-risk action this diagnostic surfaced.
- **Investigate the embedding token-limit interaction with passage segmentation (Section 12.3)** as a smaller follow-on: quantify corpus-wide how many eligible passages are silently unembedded due to exceeding the 512-subword-token model limit, and whether `passage_config.py`'s `max_words=400` should be recalibrated against the embedding model's actual tokenizer (not just its own word-count heuristic) to reduce this gap -- a segmentation-config question, not a matching-algorithm question, and out of this milestone's own scope to resolve here.

Only after both are fixed and the residual REMOVED/NEW population is re-measured would a future milestone be positioned to re-evaluate Option D (anchor-aware unmatched recovery) on a candidate-generation layer known to be working as documented -- at which point the exact rule family worth testing, per Section 7/8's findings, would be: **unique-hash-on-both-sides AND both-side accepted-anchor bracket agreement AND passage length >= 20 words**, evaluated against `classify_alignment`'s existing output rather than defaulted to UNCHANGED.

# Milestone 7 — Human-Labeled Construct Validation

**Status: PILOT-LABELED (NON-INDEPENDENT) — TRUE INDEPENDENT HUMAN LABELING STILL PENDING**

**Read this before trusting anything in Sections 12+:** the labels behind the results below were produced by Claude (this same AI system, across seven parallel review passes), not by an independent human reviewer. Every labeled row carries `reviewer_id = "claude-pilot-not-independent"` for exactly this reason. The milestone brief (Sections 30-31) is explicit that gold-truth labels must come from an independent human, precisely because using an LLM to grade a pipeline that itself leans on embeddings and lexical scoring is not an independent check — agreement (or disagreement) between the two could reflect shared blind spots rather than real correctness. This pilot exists only because a real reviewer was not available and the alternative was no signal at all; it is a diagnostic, not a substitute. A verdict of `VALIDATED — PROCEED` should **not** be drawn from this pilot alone — see Section 14 (Final Verdict) below for what actually changes once a real reviewer's labels arrive.

Original artifacts (`validation/human_validation_cases_blinded.csv`, `validation/passage_quality_review_sample.csv`) are unchanged and still the correct starting point for real human labeling. The pilot's labels live in a separate set of `*_piloted.csv` files so the two are never confused.

Per the milestone brief: the core passage extraction / segmentation / embedding / candidate-generation / alignment pipeline is **frozen** as of `docs/oversized-passage-retrieval-subchunks-experiment.md` Section 20 (ACCEPT AND FREEZE). Nothing in this milestone modifies that pipeline. This report and its associated code only read the corpus and assemble/score a human-review sample.

---

## 1. Current-run resolution (data-integrity rule, Section 2)

Every query in this milestone resolves "current" through the same production chain other current-run consumers use, never a naive join or `MAX(created_at)`:

- **Extraction run**: `get_current_extraction_run(session, report_id)` (`services/extraction.py`) — most recent `ExtractionRun` with `status IN (COMPLETED, COMPLETED_WITH_WARNINGS)`, ordered by `completed_at DESC`.
- **Narrative document**: `get_narrative_document(session, report_id)` — the `NarrativeDocument` belonging to that current `ExtractionRun` (one-to-one).
- **Segmentation run**: `get_current_segmentation_run(session, narrative_document_id)` (`services/passage_segmentation.py`) — same COMPLETED/COMPLETED_WITH_WARNINGS + `completed_at DESC` pattern, keyed off the *current* narrative document, not off every historical one.
- **Embedding run**: `get_current_embedding_run(session, segmentation_run_id)` (`services/passage_embedding.py`) — same pattern, keyed off the current segmentation run.
- **Alignment run**: `get_current_alignment_run(session, report_pair_id)` / `get_current_alignment_runs_by_pair(session, report_pair_ids)` (`services/passage_alignment.py`) — same pattern, keyed off `ReportPair`.

This milestone's sampler (`services/human_validation_sampling.py`) calls `get_current_alignment_runs_by_pair` directly (the same helper `services/review_sample.py`'s `pairs review-sample` CLI command already uses in production), and resolves every passage's population through the `earlier_segmentation_run_id`/`later_segmentation_run_id` actually pinned on that current `AlignmentRun` — not a fresh, potentially-stale re-derivation. This mirrors the corrected resolution chain documented in `docs/oversized-passage-retrieval-subchunks-experiment.md` Section 8.1, which found that a naive `Report -> NarrativeDocument` join overcounts eligible passages by roughly 4x (80,346 vs. the corrected ~21,016) because several reports have more than one `NarrativeDocument` generation from repeated extraction attempts, and nothing deletes superseded runs.

## 2. Population counts

Cross-checked against `AlignmentStatus`-bucketed counts across every current `PassageAlignment` row (`primary_alignment = True`) corpus-wide, resolved via the chain above:

| Bucket | Available in current corpus |
| --- | ---: |
| UNCHANGED | 3,094 |
| LIGHTLY_MODIFIED | 4,456 |
| SUBSTANTIALLY_MODIFIED | 3,599 |
| NEW | 4,503 |
| REMOVED | 4,389 |
| AMBIGUOUS / difficult structural | 13,681 |

(Printed directly by `market-documents validation build-sample` for the run that produced the current `validation/human_validation_cases.csv`, seed `20260910`.) These are well above the Section 6 targets for every bucket (all six sampled buckets hit their exact target: 60/60/60/50/50/20 = 300 total), so no target needed to be reduced. Note AMBIGUOUS/NEW/REMOVED/LIGHTLY_MODIFIED populations dwarf UNCHANGED, consistent with the corpus containing far more matched-with-change and unmatched passages than exact matches — see Section 5 for the realized company mix (all 6 companies represented: ACT 91, BEL 55, KP2 49, SBP 39, SUR 35, SDL 31 rows in the 300-case sample).

## 3. Company coverage

All 6 companies present in the frozen corpus (`ACT`, `BEL`, `KP2`, `SBP`, `SDL`, `SUR` — 30 reports, 25 report pairs; see `docs/oversized-passage-retrieval-subchunks-experiment.md` Section 9) are eligible for sampling. `KP2`, `ACT`, `SBP` (the milestone's minimum-required set) are all included. Company mix within each sampled bucket is diversified by the sampling scheme below, not forced to an exact quota (some companies have far smaller corpora, e.g. KP2/SBP/SDL vs. ACT/BEL/SUR) — see the sample CSV's `company` column for the realized distribution.

## 4. Sampling design (Sections 4, 6, 7)

Implemented in `src/market_documents/services/human_validation_sampling.py::build_validation_sample`, exposed via `market-documents validation build-sample`. Deterministic seed: **`20260910`** (the date this sample was first frozen), passed as `DEFAULT_SEED`.

Target counts (Section 6), all met from availability:

| Bucket | Target |
| --- | ---: |
| UNCHANGED | 60 |
| LIGHTLY_MODIFIED | 60 |
| SUBSTANTIALLY_MODIFIED | 60 |
| NEW | 50 |
| REMOVED | 50 |
| AMBIGUOUS / difficult structural | 20 |
| **Total** | **300** |

The AMBIGUOUS/difficult pool (Section 4's "difficult cases," Section 9 Q2's `STRUCTURAL_SPLIT_MERGE` construct) is broader than `AlignmentStatus.AMBIGUOUS` alone: it also includes any alignment with `confidence == NEEDS_REVIEW` or `alignment_type IN (ONE_TO_TWO, TWO_TO_ONE)`, deduplicated. A case selected into this pool may also appear in one of the three matched-status pools (an alignment can be both, e.g., LIGHTLY_MODIFIED and NEEDS_REVIEW) — this mirrors the existing `review_sample.py` precedent that "an alignment can appear in more than one category."

**Stratification procedure** (exact, reproducible):

1. For each bucket, group its available alignments by `AlignmentConfidence` (HIGH/MEDIUM/LOW/NEEDS_REVIEW).
2. Allocate the bucket's target count across confidence groups via a square-root-weighted largest-remainder method: `quota[g] ∝ sqrt(available[g])`, floored, empty groups get zero, remainder distributed by largest fractional part. This gives every non-empty confidence stratum representation (Section 7) without letting the single largest stratum dominate the sample the way pure proportional allocation would.
3. Within each confidence group, candidates are further grouped by `(company_ticker, length_bucket)` where `length_bucket` is `SHORT` (<60 words), `MEDIUM` (60–200), `LONG` (>200), taken from the later passage for matched/NEW cases and the earlier passage for REMOVED cases.
4. Each `(company, length_bucket)` group is shuffled with `random.Random(seed)` after a stable sort by database ID (so the shuffle itself is reproducible), then the quota is filled by round-robin draw across groups — spreading the sample across company and passage length rather than concentrating in whichever company/length combination happens to be largest in the corpus.

This is a direct extension of the `review_sample.py` precedent (seeded `random.Random`, stable pre-shuffle sort, deterministic quotas) to the milestone's confidence/company/length stratification requirements.

**Passage-type stratification**: not separately quota'd — `passage_type` is recorded on every case for post-hoc reporting (Section 3.4 construct A) rather than driving sample composition, since forcing simultaneous quotas across confidence x company x length x passage_type would fragment groups too small to fill reliably at this sample size. The realized `passage_type` mix can be read directly off the CSV.

## 5. Passage-quality subset (Section 11)

Implemented in `services/human_validation_quality_sample.py`, exposed via `market-documents validation build-quality-sample`. Independently draws ~100 individual passages (not pairs) from the same current-run-resolved population, diversified by `(company, passage_type)` with the same round-robin scheme as above, seed `20260910`. Written to `validation/passage_quality_review_sample.csv`.

## 6. Human-review packet contents (Section 8, 10, 12)

`validation/human_validation_cases.csv` (full, internal — never share outside the team; contains system fields) and `validation/human_validation_cases_blinded.csv` (reviewer-facing — omits every `system_*` field) both contain one row per case, with:

- Company, earlier/later report period-end dates, and PDF path (`data/raw/<TICKER>/<year>/annual_report.pdf`, per `Report.local_path`) and page number(s) for source-grounding (Section 12).
- Earlier/later passage heading, page range, and full text.
- Immediately preceding/following passage (truncated to 300 chars) in each report, for structural context (Section 8's "optional contextual passages"), keyed by `(segmentation_run_id, passage_index ± 1)` in the current segmentation run.
- For NEW/REMOVED cases only: three independently-computed diagnostic alternatives from the opposite report (`opposite_top_lexical_*`, `opposite_top_semantic_*`, `opposite_nearest_positional_*`) — the highest word-overlap match, the highest embedding-cosine match (via the same `get_semantic_candidates` retrieval function candidate generation uses, called at `top_k=1`, covering both canonical embeddings and Milestone-6 retrieval subchunks for oversized passages), and the positionally nearest passage by relative document position. None of these is labeled as the system's chosen candidate (Section 10's blinding requirement).
- Blank `human_correspondence` / `human_change` / `human_significance` / `human_unmatched_label` / `reviewer_id` / `notes` columns for the reviewer to fill in.

The blinded export omits `system_alignment_status`, `system_alignment_type`, `system_confidence`, and every similarity score — the reviewer never sees these (Section 8, Section 13). The full CSV retains them for post-labeling analysis only.

## 7. Labeling guide

`docs/human-validation-labeling-guide.md` defines every label value (Q1 correspondence, Q2 change magnitude, Q3 analytical significance, Q4 unmatched validity, passage-quality categories) with worked examples, per Section 32.

## 8. Multi-reviewer design (Section 14)

The CSV schema already supports this: `reviewer_id` is a free-text column on every row. The intended process:

1. Reviewer 1 labels all 300 rows of `human_validation_cases_blinded.csv`, entering `R1` in `reviewer_id`.
2. If a second reviewer is available, they independently label a 75–100-case overlap subset (a fixed random subset of `case_id`s, not communicated to Reviewer 1's labels) into a **separate copy** of the file, entering `R2`.
3. `market-documents validation analyze` and `services/human_validation_analysis.inter_rater_reliability` (Cohen's kappa for correspondence, quadratic-weighted kappa for ordinal change severity) then run on the two files matched by `case_id`.

**No second reviewer is available during this milestone.** Per Section 14/30, this report does not fabricate inter-rater results. The schema and analysis code (`inter_rater_reliability`, `cohens_kappa`, `weighted_kappa` in `services/human_validation_analysis.py`, unit-tested in `tests/test_human_validation_analysis.py`) are ready to run the moment a second reviewer's labels exist.

## 9. Analysis code (ready, not yet run against real labels)

`src/market_documents/services/human_validation_analysis.py`, exposed via `market-documents validation analyze <labeled_csv>`, implements every metric the milestone specifies, all pure functions over CSV rows (no LLM involvement, per Section 30):

- Section 16: correspondence precision, overall and by confidence/company/etc.
- Section 17: NEW/REMOVED validity (no-correspondence precision, missed-correspondence rate, structural-split-merge rate, uncertain rate).
- Section 18: 3-level change confusion matrix, exact agreement, within-one-category agreement, quadratic-weighted kappa.
- Section 19: binary changed-vs-unchanged accuracy/precision/recall/F1/confusion matrix.
- Section 20: ordered-change Spearman correlation and mean absolute category difference.
- Section 21: Spearman correlation and per-category means for each continuous similarity metric (semantic, lexical cosine, Jaccard, edit similarity, combined score) against human-rated change intensity.
- Section 15: Cohen's kappa (correspondence) and quadratic-weighted kappa (ordinal change severity) for inter-rater reliability, once a second reviewer exists.

None of scipy/sklearn/pandas is a project dependency (`pyproject.toml`), so kappa and Spearman are implemented from closed-form definitions rather than adding a new dependency for this milestone alone; both are unit-tested against known cases (perfect agreement, chance-level agreement, ties) in `tests/test_human_validation_analysis.py`.

## 10. Predeclared acceptance criteria (Section 26, recorded before any labeling)

| Construct | Target |
| --- | --- |
| HIGH-confidence correspondence precision | ≥95% |
| Overall accepted-alignment correspondence precision | ≥90% |
| NEW/REMOVED validity (genuinely unmatched) | ≥85% |
| Binary changed-vs-unchanged agreement | ≥85% |
| 3-level severity exact agreement | ≥70% |
| 3-level severity within-one-category agreement | ≥90% |
| Report-level rank validity (document-level, Section 22–24, separate follow-on effort) | Spearman \|ρ\| ≥0.5 in the theoretically correct direction |

These are fixed now, before any human label exists, per Section 26's "do not choose thresholds after seeing the results."

## 11. What still needs to happen (Section 31)

Human labeling cannot be completed autonomously in this session — per Section 30, an LLM must not generate the gold labels. The blinded dataset, labeling guide, and analysis code are ready. Outstanding steps for the user:

1. Open `validation/human_validation_cases_blinded.csv` (a spreadsheet is sufficient — 300 rows) alongside `docs/human-validation-labeling-guide.md`.
2. Label each row's `human_correspondence` / `human_change` / `human_significance` (matched-status rows) or `human_unmatched_label` (NEW/REMOVED rows), filling in `reviewer_id` (e.g., `R1`) and optional `notes`.
3. Separately label `validation/passage_quality_review_sample.csv`'s `quality_rating` column (~100 rows) using the Part 3 categories in the labeling guide.
4. For uncertain/structural/NEW-REMOVED-disagreement cases, consult the source PDF at `earlier_report_pdf_path`/`later_report_pdf_path`, page `earlier_page`/`later_page` (Section 12).
5. Run `market-documents validation analyze validation/human_validation_cases_blinded.csv --output validation/metrics.json` once labeling is complete.
6. Return the labeled CSV(s) so this report's Sections 5 (Results), disagreement analysis (Section 25), and final verdict (Section 34) can be completed.

Document-level validation (Sections 22–24: ~10–15 human-rated report pairs vs. report-level system metrics) and the corresponding rank-correlation analysis are a separate, smaller labeling task not yet built — flagged here as outstanding, to be added once passage-level labeling is under way, since it requires its own qualitative-rating packet (one rating per report pair, not per passage). It was not attempted in the pilot pass either.

---

## 12. Pilot results (non-independent — read the status banner above before using these)

All 300 cases and the 100-passage quality subset were labeled by Claude across seven parallel review passes (one per bucket), following `docs/human-validation-labeling-guide.md` exactly, working only from the blinded columns (no system fields visible). Labels were merged with `scripts/merge_pilot_labels.py` into `validation/human_validation_cases_piloted.csv` / `_blinded_piloted.csv` / `passage_quality_review_sample_piloted.csv`, verified programmatically (all 300/100 case_ids present exactly once, correct schema). Metrics computed via `market-documents validation analyze validation/human_validation_cases_piloted.csv`, raw output at `validation/pilot_metrics.json`.

### Against the predeclared criteria (Section 10)

| Construct | Target | Pilot result | vs. target |
| --- | --- | ---: | :---: |
| HIGH-confidence correspondence precision | ≥95% | 94.4% (34/36) | just below |
| Overall correspondence precision | ≥90% | 83.0% (166/200) | below |
| NEW validity (genuinely unmatched) | ≥85% | 48.0% (24/50) | well below |
| REMOVED validity (genuinely unmatched) | ≥85% | 54.0% (27/50) | well below |
| Binary changed-vs-unchanged agreement | ≥85% | 79.4% (accuracy) | below |
| 3-level severity exact agreement | ≥70% | 57.4% | below |
| 3-level severity within-one-category | ≥90% | 94.3% | **meets** |
| Report-level rank validity | \|ρ\|≥0.5 | not measured (Section 22-24 task not built) | n/a |

Only one of seven measurable criteria clears its bar. The severity metric passing "within-one-category" while missing "exact agreement" is expected — Section 18 anticipated this distinction is inherently more subjective — but the magnitude of the NEW/REMOVED and overall-correspondence shortfalls is large enough that pilot-labeling noise alone is an unlikely full explanation.

### By confidence (correspondence precision)

| Confidence | n | Precision |
| --- | ---: | ---: |
| HIGH | 36 | 94.4% |
| MEDIUM | 13 | 84.6% |
| LOW | 14 | 64.3% |
| NEEDS_REVIEW | 137 | 81.8% |

Confidence is *directionally* calibrated (HIGH > MEDIUM > NEEDS_REVIEW > LOW is close to monotonic, HIGH clearly the best), but NEEDS_REVIEW makes up the overwhelming majority of the matched sample (137/200 — see Section 4's note on UNCHANGED's confidence skew) and its precision (81.8%) isn't dramatically worse than NEEDS_REVIEW's supposed-to-be-better MEDIUM tier (84.6%), suggesting confidence separates HIGH from everything else more than it separates the three lower tiers from each other.

### By company (correspondence precision)

ACT 80.8%, BEL 90.0%, KP2 79.4%, SBP 85.7%, SDL 82.6%, SUR 78.3% — no single company is dramatically worse than the rest (all in a 78–90% band); this does not look like a one-template problem.

### NEW/REMOVED breakdown

| | NEW (n=50) | REMOVED (n=50) |
| --- | ---: | ---: |
| NO_CORRESPONDENCE (system call confirmed) | 48% | 54% |
| CORRESPONDENCE_EXISTS (likely missed match) | 38% | 38% |
| STRUCTURAL_SPLIT_MERGE | 4% | 4% |
| UNCERTAIN | 10% | 4% |

38% "likely missed match" on both sides is the single largest finding in this pilot. The pilot passes' notes name specific, checkable candidates for every one of these (19 NEW + 19 REMOVED cases) — see the `notes` column of `validation/human_validation_cases_piloted.csv` filtered to `human_unmatched_label == "CORRESPONDENCE_EXISTS"`. A recurring pattern across the named cases: recurring/boilerplate disclosures (financial-risk notes, AGM resolution language, director bios, accounting-policy intros) that reappear near-verbatim in the adjacent report but apparently fell outside the pipeline's matching threshold or lost out to a stronger competing candidate.

### Change classification

3-level confusion matrix (rows = human, columns = system; n=141 human-confirmed-corresponding matched cases):

| Human ↓ / System → | UNCHANGED | LIGHTLY_MODIFIED | SUBSTANTIALLY_MODIFIED |
| --- | ---: | ---: | ---: |
| EFFECTIVELY_UNCHANGED | 51 | 10 | 8 |
| MINOR | 11 | 18 | 4 |
| SUBSTANTIAL | 0 | 27 | 12 |

Exact agreement 57.4%, within-one-category 94.3%, weighted kappa 0.53 (moderate). Binary changed-vs-unchanged: accuracy 79.4%, precision 77.2%, recall 84.7%, F1 80.8%. The system's LIGHTLY_MODIFIED column is the main source of disagreement — it absorbs 10 human-EFFECTIVELY_UNCHANGED cases and 27 human-SUBSTANTIAL cases, i.e., LIGHTLY_MODIFIED functions less like a distinct middle category and more like a catch-all the other two categories both leak into.

### Continuous metrics vs. human-rated change (Section 21)

All five metrics correlate in the expected direction (more human-rated change → lower similarity): edit similarity has the strongest correlation (Spearman ρ=-0.73), followed by lexical cosine (ρ=-0.66) and Jaccard (ρ=-0.64); semantic similarity is the weakest (ρ=-0.54) and has the smallest separation between categories (0.96 EFFECTIVELY_UNCHANGED vs. 0.89 SUBSTANTIAL — a narrow band compared to edit similarity's 0.90 vs. 0.36). This is consistent with embeddings capturing topical similarity more than fine-grained wording change, which is expected behavior for a semantic model rather than a defect.

### Passage quality (100-passage subset)

COHERENT_SUBSTANTIVE 51%, COHERENT_STRUCTURAL 14% (65% acceptable), MIXED_POOR_BOUNDARY 19%, TABLE_ARTIFACT 12%, EXTRACTION_ARTIFACT 4% (35% showing some quality problem). This is a materially higher artifact rate than the small-sample impression in `docs/oversized-passage-retrieval-subchunks-experiment.md` (which checked far fewer cases) — consistent with, and a plausible root cause behind, the correspondence and classification shortfalls above: a passage that is a table fragment, a cut-off list, or two concatenated topics is inherently harder to match or classify correctly regardless of how good the embedding/lexical scoring logic is.

## 13. Disagreement investigation (Section 25)

Automated keyword pass over the `notes` column across all 300 labeled cases (`grep`-style pattern match, not a rigorous classification — a cross-check, not a primary result):

| Likely cause (from reviewer notes) | Cases mentioning it |
| --- | ---: |
| Table/layout content leaking into narrative text | 52 |
| Recurring boilerplate / near-verbatim rollover | 25 |
| Extraction artifact (garbled/fragmentary text) | 22 |
| Structural split/merge (passage boundary crosses disclosure boundary) | 21 |
| Same heading, different specific topic underneath | 16 |
| Large (non-adjacent-year) report gap | 5 |

Additionally: 25/300 cases were labeled `STRUCTURAL_AMBIGUOUS` for change magnitude, and 29 matched-bucket cases (UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED/AMBIGUOUS) were labeled `human_correspondence = NO` despite the system asserting a match.

Reading across all seven pilot passes' own summaries, three concrete, recurring causes account for most of the disagreement:

1. **Passage-boundary quality** (table leakage, cut-off lists, concatenated unrelated sections — Section 12's 35% quality-subset artifact rate) is the most frequently cited issue and plausibly underlies a large share of both the correspondence misses and the STRUCTURAL_AMBIGUOUS change-magnitude calls: a passage that is itself a poor unit is hard to match or classify well no matter how good the downstream scoring is. This traces to **passage segmentation**, not the frozen alignment/candidate-generation logic being evaluated most directly.
2. **NEW/REMOVED candidate-generation coverage**: 38% of both NEW and REMOVED cases had a plausible same-disclosure candidate in the opposite report (often recurring boilerplate — financial-risk notes, AGM language, accounting-policy intros, director bios) that the system did not match. This is squarely inside the alignment/matching logic under test, not a segmentation artifact — 25/38 (NEW) and comparable REMOVED cases were flagged with a *lexical* candidate as the likely miss, which is notable since lexical similarity is comparatively cheap to detect; whether this reflects an acceptance-threshold or ranking issue in the frozen candidate-generation/scoring logic is a specific, checkable question, not a general "the pipeline is bad" finding.
3. **LIGHTLY_MODIFIED as a catch-all category**: the confusion matrix shows LIGHTLY_MODIFIED absorbing cases from both neighboring categories rather than cleanly separating them (Section 12). Some of this is the expected subjectivity the brief calls out (Section 18) between MINOR and SUBSTANTIAL; the sheer size of the leak (37/78 non-diagonal LIGHTLY_MODIFIED cells) suggests more than ordinary subjectivity, though disentangling "genuine classification-threshold issue" from "structural-boundary noise already captured under cause 1" would need the specific cases re-examined by an independent reviewer.

One structural observation, not a defect: 5 cases in the pilot spanned unusually large report gaps (one pairing was 2016→2024, an 8-year span for one company), flagged independently by two different pilot passes. `ReportPair.gap_months` and the existing `irregular_gap_pair` review category (`services/review_sample.py`) already track this condition, so it is a known, monitored corpus characteristic, not a new discovery — but it's worth confirming this reflects genuinely missing intermediate-year reports for that company rather than a pairing defect, since an 8-year gap changes what "correspondence" should even mean for boilerplate/legal content.

## 14. Final verdict

**This pilot cannot issue Section 34's official verdict — that requires the independent human labeling this pilot explicitly is not.** What it can responsibly say:

**If these numbers hold up under independent review, this would not be `VALIDATED — PROCEED`.** Five of seven measurable predeclared criteria fell short, two of them by a wide margin (NEW/REMOVED validity ~48-54% against an 85% target — in the range Section 27 names as a *critical*-severity example, "NEW/REMOVED mostly false"). That is not the "modest imperfection" pattern Section 28 says should be waved through to the next milestone.

At the same time, this is **not** a clean case for `REOPEN PIPELINE — SPECIFIC CRITICAL DEFECT` either, because the disagreement investigation above (Section 13) points at least partly upstream, to **passage-segmentation boundary quality**, rather than exclusively at the frozen alignment logic itself — and Section 27 is explicit that only critical failures should reopen the *core* pipeline. The NEW/REMOVED miss rate specifically, though, does implicate the alignment/candidate-generation logic more directly (cause 2 above) and is the strongest single candidate for a genuine, nameable defect if independent review confirms it.

**My honest recommendation, given I can't issue the real verdict:** treat this milestone as **NOT YET VALIDATED**, and prioritize a real independent reviewer's time on the highest-value subset rather than all 300 rows — specifically:
- the 38 NEW/REMOVED cases this pilot flagged `CORRESPONDENCE_EXISTS` (concrete, checkable, and the biggest predeclared-criteria miss),
- the 100-passage quality subset (fast to review, and resolves whether the 35% artifact rate is real or a pilot-labeling quirk),
- a random 30-40 case cross-check of the matched buckets to sanity-check the 83% overall correspondence figure.

That's a few hours, not the full afternoon a from-scratch 300-case review would take, and it would tell you within a reasonable estimate whether this pilot's negative read is right — which is the actual decision-relevant question before committing to either "proceed to Lazy Prices analysis" or "reopen the pipeline."

## 15. Root-cause diagnostic (code/data investigation, not more labeling)

Following up on Section 13's disagreement analysis, three specific NEW-bucket pilot flags were traced directly against the live database (`scripts/diagnose_new_removed_misses.py`, read-only, no pipeline or data changes) to determine exactly where a plausible match was lost. This is evidence, not opinion — every number below was recomputed live from the current corpus.

**Finding 1 — a confirmed top-k recall miss (M7-NEW-0011, ACT).** The NEW passage ("Response and mitigating actions to preserve value... NHI... NDoH...") has a genuine same-topic candidate in the earlier report ("OUTLOOK... impending conclusion of the health market inquiry and the next stage of NHI..."). Recomputing its true cosine similarity against the *current* embedding run gives **0.741** — comfortably above `min_semantic_similarity` (0.50, the floor that would exclude it from consideration entirely) but **below all five of the passages that actually filled the top-5** (0.752-0.789). The candidate was excluded purely by `top_k=5` being too narrow for this later passage, not by any acceptance threshold or scoring logic. This is a clean, mechanical explanation for at least one class of the pilot's "lexical candidate exists but system missed it" pattern: **candidate generation is semantic-retrieval-only** (`alignment_candidates.get_semantic_candidates`) — lexical similarity has no role in *which* candidates are even considered, only in scoring/gating ones that already cleared the embedding-based top-k cut. A genuinely-corresponding passage that an embedding model ranks 6th instead of 5th-or-better is invisible to the rest of the pipeline no matter how strong its lexical overlap is.

**Finding 2 — a confirmed one-to-one / duplicate-boilerplate collision (SDL corpus).** The earlier passage "Environmental Responsibility and Stewardship... Southern Palladium entrenches principles of environment..." is the correctly-retrieved #1 semantic candidate (similarity 0.93) for *two different* later passages in the same report pair. The system awarded it to the stronger match (`combined_score` 0.928, classified LIGHTLY_MODIFIED) and left the weaker relationship (`content_score` 0.617 — still above the 0.45 acceptance gate) unmatched. This is the system doing exactly what its one-to-one assignment is designed to do, not obviously a bug — but it confirms, concretely, that recurring/duplicated section content (the same boilerplate paragraph type appearing more than once) can produce an "orphan" side that surfaces as NEW/REMOVED even when a real, scoreable correspondence exists elsewhere. This is exactly the situation `alignment_config.py`'s own docstring already names and defers: *"attempt constrained one-to-two/two-to-one acceptance is deferred."* Not a new discovery — a live, quantified instance of a known, already-documented limitation.

**Finding 3 — the pilot pass itself contains labeling errors.** Investigating the case initially thought to correspond to Finding 2 (M7-NEW-0027) surfaced a direct contradiction: the pilot's note describes the flagged passage as an "Environmental/health & safety paragraph... near word-for-word identical" to its candidates, but the case's actual `later_text` (verified straight from the CSV) is about establishing an exploration project's office base ("The Khomanani Centre on the Eerstegeluk farm...") — a different topic entirely. The system's NEW call for that specific passage is very likely *correct*; the "Environmental Responsibility" passage it superficially resembles by embedding was, per Finding 2, legitimately claimed by a stronger match elsewhere in the same report pair. **This means the pilot's notes/labels are not fully reliable at the level of individual cases** — likely a batch-processing mix-up during one of the seven parallel review passes, not a systematic pattern found elsewhere, but real all the same. The pilot's 38-case "likely missed correspondence" figure (Section 12) should be read as directionally informative, not as a precise count — an independent reviewer re-checking those 38 specific cases (not all 300) is the fastest way to get a trustworthy number.

**What this changes about Section 14's recommendation:** the two confirmed findings above are real, specific, and actionable without needing more human judgment — they're architecture facts, not opinions. Finding 1 (top-k too narrow) is a candidate-generation *recall* question that could plausibly be evaluated further by re-running `get_semantic_candidates` at a larger `top_k` (e.g. 10-15) across the full NEW/REMOVED population and checking how many additional near-hits it would surface — a measurement task, still consistent with the milestone's "measure, don't fix" rule, and worth doing before deciding whether this is a "material but bounded" issue (Section 27) or something closer to critical. Finding 2 confirms a known, already-scoped limitation rather than a new defect. Finding 3 is a data-quality caveat on the pilot itself, reinforcing that a real reviewer re-checking the flagged subset (not the full 300) remains the right next step, exactly as Section 14 recommended.

---

*Sections 12-15 report the non-independent AI pilot pass and a follow-up code/data diagnostic only. The milestone's official Section 34 verdict remains open until an independent human reviewer labels at minimum the priority subset named in Section 14, ideally the full `validation/human_validation_cases_blinded.csv`.*

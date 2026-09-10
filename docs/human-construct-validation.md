# Milestone 7 — Human-Labeled Construct Validation

**Status: PENDING HUMAN LABELING**

This report covers the validation *design* and the artifacts generated so far. Sections 5 onward (results, verdict) will be filled in once a human reviewer has labeled `validation/human_validation_cases_blinded.csv` (and, if a second reviewer is available, the overlap subset).

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

Document-level validation (Sections 22–24: ~10–15 human-rated report pairs vs. report-level system metrics) and the corresponding rank-correlation analysis are a separate, smaller labeling task not yet built — flagged here as outstanding, to be added once passage-level labeling is under way, since it requires its own qualitative-rating packet (one rating per report pair, not per passage).

---

*This report will be updated with Sections 5 (Results by construct), disagreement analysis (Section 25), and the final verdict (Section 34: VALIDATED — PROCEED / VALIDATED WITH LIMITATIONS / REOPEN PIPELINE — SPECIFIC CRITICAL DEFECT / NOT VALIDATED) once human labels exist.*

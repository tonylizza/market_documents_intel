# Track 7C.1b — Canonical Hierarchy Integration

Status: implementation complete. Not a new research experiment; not 7C.2. Scope: one principled
correction to `schedule_localization.py`'s boundary algorithm -- schedule boundaries must respect
document hierarchy (Document -> Schedule -> Semantic units/subsections) instead of treating every
`HEADING_CANDIDATE` as an equally valid section boundary -- using the canonical structural/style
evidence Track 7C.1a captured but never wired in.

## 1. Problem being corrected

Track 7C.1a (`docs/7c1a-canonical-source-representation.md`) established that canonical extraction
captures per-span font size/style/geometry, and that real corpus evidence (ACT 2021) shows this
evidence cleanly separates genuine top-level section headings (~62-65pt) from internal CFO-review
subsection headings (~11-14pt) -- but it deliberately left `schedule_localization.py`'s boundary
algorithm unmodified. `localize_schedule`'s `_end_page_for` still ended a span at the next
`HEADING_CANDIDATE` of *any* kind, so:

- ACT 2021's `FINANCIAL_PERFORMANCE` schedule resolved to a single page (pp.61-61), truncated by
  the first internal subsection heading it encountered.
- BEL 2019's schedule was truncated by chart-title heading-candidates on the page immediately after
  the real heading, even though they are not section boundaries.
- BEL 2020's schedule ended one page before the Gross Margin paragraph 7C.1a confirmed canonical
  extraction now preserves in full.

7C.1b's job: audit what canonical evidence is already reachable, add the smallest reusable
mechanism to ask "is this heading-candidate plausibly a top-level structural section heading in
*this* document?", and use that to gate `_end_page_for`'s termination check -- nothing else.

## 2. Structural-level logic

New pure module: `src/market_documents/services/heading_structure.py` ::
`assess_heading_structure(headings, anchor_font_sizes=())` -> `dict[heading_id,
HeadingStructuralAssessment]` (`is_top_level: bool`, `confidence: HIGH|MEDIUM|LOW`, `is_toc_entry:
bool`, `evidence: tuple[str, ...]`). No LLM/VLM; fully deterministic.

Three independent, document-relative signals, applied in this order per heading:

1. **Table-of-contents pattern** (generic, no font needed): a heading-candidate is a TOC entry if
   its own page carries 3+ heading-candidates each ending in a short run of digits (a page-number
   suffix, with or without dot leaders) and it is one of them. TOC entries are excluded from being
   matched as the schedule's own heading *and* from ever terminating a span.
2. **Paired/grouped same-page labels** (word-set overlap, not a font check): two heading-candidates
   on the same page sharing 2+ words with at least 50% overlap (e.g. BEL's "2019 External Revenue
   Analysis - Geographic" / "2018 External Revenue Analysis - Geographic", which share every word
   *except* the leading year -- a prefix-only check misses this) are both demoted, regardless of
   font tier. This is applied unconditionally, before the font check: font-size clustering across
   an entire ~100+ page annual report can be a smooth, gradual spectrum with no clean gap near a
   real chart title's size (see the BEL 2020 case in the caveats below), so waiting for the font
   tier to also agree would silently miss exactly the cases this signal exists for.
3. **Document-relative font-size tiering**, anchored to the schedule's own matched heading(s):
   `localize_schedule` computes every heading-candidate matching the schedule's configured
   vocabulary *before* any TOC filtering, and passes their font sizes in as `anchor_font_sizes`.
   Font sizes are grouped into clusters by relative gap (a cluster boundary exists wherever the
   next size down is under 75% of the current cluster's smallest member -- relative, never an
   absolute point value). The top tier is the **first cluster (largest-first) that contains one of
   the anchors** -- i.e. the tier the report's own recognized section heading actually belongs to,
   not simply the single largest cluster in the whole document. This distinction matters: the
   largest font-size cluster in a real annual report is not reliably a section heading at all (see
   caveats) -- a cover-page title or an isolated single-page marketing insert can be larger than
   every genuine section heading. Without anchors (a standalone caller), falls back to the largest
   cluster whose members span at least 2 distinct pages, a weaker generic outlier filter.

When no font-size separation can be established at all (single tier, or no font data), every
heading defaults to `is_top_level=True, confidence=LOW` -- i.e. the module changes nothing for that
document, which is exactly `localize_schedule`'s pre-7C.1b behavior. This is what makes the fix
regression-safe by construction rather than by a special case: a report with no structural evidence
is bounded exactly as it always was.

`schedule_localization.localize_schedule`'s `_end_page_for` was changed by exactly one added
clause: a later boundary candidate only ends the span if `structural[h.id].is_top_level` in
addition to the existing "later page" / "not `<heading> continued`" / "not a 3+-times-repeated
banner" conditions. `HeadingBlock` gained three new optional fields (`font_size`, `is_bold`,
`block_width_ratio`, all defaulting to `None`) to carry this evidence.

## 3. Files changed

New:
- `src/market_documents/services/heading_structure.py`
- `tests/test_heading_structure.py`
- `docs/7c1b-canonical-hierarchy-integration.md` (this file)

Modified:
- `src/market_documents/services/schedule_localization.py` -- `HeadingBlock` gains
  `font_size`/`is_bold`/`block_width_ratio` (optional, default `None`); `localize_schedule`
  computes vocabulary matches before TOC filtering (for structural anchors), calls
  `assess_heading_structure`, and gates `_end_page_for` on `is_top_level`; `_run_localization`
  prefers a report's current successful `CanonicalExtractionRun` (via `source_adapter`) over legacy
  `TextBlock` when one exists, since canonical spans carry richer font/geometry evidence than
  flattened `TextBlock` rows -- falls back to legacy `TextBlock` unchanged otherwise (`TextBlock`
  does carry a flattened `font_size`/`is_bold`, so even the fallback has some structural evidence,
  just less precise than canonical).
- `src/market_documents/services/source_adapter.py` -- `ClassifiedBlock` gains
  `font_size`/`is_bold`/`block_width_ratio`; `classify_source_pages` populates them from data it
  already computes for classification; `build_heading_blocks` threads them into `HeadingBlock`.
- `src/market_documents/services/schedule_config.py` -- `ALGORITHM_VERSION` bumped `1.0.4` ->
  `1.1.0` (forces every cached `ScheduleLocalizationRun` to be recomputed).
- `tests/test_schedule_localization.py` -- regression tests added (below); existing tests
  unmodified and still pass unchanged (they construct `HeadingBlock` with no font data, which is
  exactly the "no structural evidence" default path).

Untouched: `services/semantic_unit_extraction.py` (unmodified, per the task's explicit scope --
see caveats), `services/block_classification.py`, `services/header_footer_detection.py`, the legacy
extraction pipeline, publishing, and the web app.

## 4. Tests added

`tests/test_heading_structure.py` (9 tests, pure, no DB):
- Large font tier is top-level, small tier is not (2 top-level headings across pages, so the tier
  is a genuine recurring one, not a one-off).
- The same relative pattern classifies identically at two different absolute point scales (proves
  no hard-coded ACT threshold).
- Paired same-page titles are demoted even with no font separation.
- Paired titles differing in their *leading* word (the real BEL case) are still caught by word-set
  overlap, not a prefix check.
- Paired titles demoted even when font separation genuinely exists elsewhere in the document.
- No font evidence at all -> defaults to top-level (regression safety).
- Table-of-contents listing entries flagged and demoted; the real heading elsewhere is not.
- Anchor font sizes select the *matched heading's* tier, not simply the largest cluster (the
  cover-title-outlier case).
- Single heading with no siblings defaults to top-level.

`tests/test_schedule_localization.py` (+7 tests, pure, no DB):
- Internal subsection heading does not terminate the parent schedule.
- Chart title does not terminate the parent schedule.
- The next genuine top-level heading still terminates the schedule.
- The hierarchy fix behaves identically at a non-ACT point scale (no hard-coded threshold).
- A table-of-contents entry is not matched as the primary heading.
- A report with no font evidence at all localizes identically to before 7C.1b (explicit regression
  fixture, using the exact pre-existing `test_exact_match_...` case).

All pre-existing 7C.1/7C.1a tests are unmodified and pass unchanged.

```
.venv/bin/python -m pytest tests/test_heading_structure.py tests/test_schedule_localization.py -q
# 21 passed
.venv/bin/python -m pytest tests/ -q
# 923+ passed, 0 failed (full suite, no regressions anywhere)
```

## 5. ACT 2021 result

Before 7C.1b (canonical source, unmodified algorithm, per the 7C.1a smoke test): `FINANCIAL_PERFORMANCE`
resolved to pp.61-61, truncated by the first internal subsection heading.

After 7C.1b: **pp.61-105**, `FOUND_PRIMARY_AND_SUPPORTING`. All of the internal CFO-review
subsection headings ("Depreciation/amortisation", "IFRS 16 (leases) net effect", "Healthcare
Services Financial Performance", "Capital management", "In conclusion") are demoted (font ~11-14pt,
outside the anchored top tier ~59-138pt) and no longer terminate the span. The span is correctly
terminated at "REMUNERATION REPORT" (p.106, font 76.49pt, in the top tier), the next genuine
top-level section. The `cfo_conclusion` `HEADED_NARRATIVE_UNIT` (start heading "In conclusion",
`NEXT_HEADING` boundary strategy, unmodified) now **resolves**: `units status ACT` reports
`cfo_conclusion=RESOLVED`. This unlocks the already-built unit extractor exactly as intended --
correcting the parent schedule boundary was the only change needed.

## 6. BEL 2019 result

Before: pp.36-36, truncated by the two "External Revenue Analysis" chart-title heading-candidates
on p.37 (their own font tier is ambiguous against the rest of the document, so this needed the
word-overlap signal, not font alone).

After: **pp.36-39**, `FOUND_PRIMARY_AND_SUPPORTING`. Both chart titles are demoted (shared-word
overlap on the same page) and no longer terminate the span. `gross_margin` **resolves**
(`units status BEL` reports `gross_margin=RESOLVED`).

## 7. BEL 2020 result

Before: pp.38-38 (per the 7C.1a smoke test), one page short of the Gross Margin paragraph 7C.1a
confirmed canonical extraction preserves in full (p.39).

After: **pp.38-40**, `FOUND_PRIMARY_AND_SUPPORTING` -- the schedule now correctly includes page 39.
However, `gross_margin` still reports `UNRESOLVED` (`start heading 'Gross Margin' not found`). This
is **not** a schedule-boundary problem -- it is a distinct, narrower issue in
`semantic_unit_extraction.py`'s existing (unmodified) heading-detection: canonical extraction's
block segmentation merges more of the preceding paragraph onto the same block than legacy
`TextBlock` extraction did, so "Gross margin" appears as a run-in phrase *in the middle* of a
`PARAGRAPH` block's text (after an unrelated sentence about Zimbabwe operations), not as a prefix
at the block's start. `extract_unit`'s `_heading_prefix_match` only matches a heading anchored at
the very start of a block (`^\s*heading\b`), by design (see that function's docstring), so it
correctly does not match here. Per the task's explicit instruction not to modify
`semantic_unit_extraction.py` unless a trivial adapter defect is found -- this is not a trivial
defect, it is a real limitation of the existing run-in-prefix heuristic meeting a different block
segmentation than it was validated against -- this is reported, not chased. See caveats.

## 8. Regression case result (BEL 2021 and BEL 2022)

BEL 2021 (the previously-working year): **pp.38-40**, `FOUND_PRIMARY_AND_SUPPORTING`,
`gross_margin=RESOLVED` -- byte-for-byte identical to the pre-7C.1b baseline. BEL 2022, also
previously correct, is likewise unchanged: pp.40-43, `gross_margin=RESOLVED`. The hierarchy fix
does not regress either known-good case.

## 9. Unresolved caveats

1. **BEL 2020 `gross_margin` remains UNRESOLVED** (see Section 7) -- a semantic-unit-extraction
   heading-detection gap exposed by canonical extraction's different block segmentation, not a
   schedule-boundary problem. Out of scope for 7C.1b by the task's own instruction; flagged for a
   future semantic-unit-extraction task, not fixed here.
2. **Font-size clustering across a whole ~100+ page annual report is not always a clean two-tier
   split.** BEL's own heading-candidate font sizes form a smooth, gradual spectrum from ~18pt down
   to ~7pt with no single sharp gap (unlike ACT's dramatic ~5x jump). Anchoring the top tier to the
   schedule's own matched heading (Section 2, signal 3) handles this correctly *for the matched
   heading's own termination candidates* by finding whichever cluster the real heading belongs to,
   but it does not attempt to build a general-purpose heading-level ontology (H1/H2/H3) for the
   whole document -- that is explicitly out of scope (see the task's "do not add more ad hoc
   schedule heuristics" instruction). The word-overlap signal (Section 2, signal 2) exists
   specifically to catch same-page paired labels independent of this limitation, and was load-
   bearing for both the BEL 2019 and BEL 2020 fixes.
3. **A single outlier font-size cluster (a cover-page title, or an isolated single-page marketing
   insert) can still be the single *largest* cluster in a document.** The anchor-based selection
   (Section 2, signal 3) correctly skips these when a vocabulary-matched anchor is available (the
   normal case), and the page-span fallback (>=2 distinct pages) provides a weaker generic guard
   when no anchor exists at all -- but a caller with no anchor and an outlier spanning exactly 2
   pages could still misclassify it. Not observed in any of the four motivating cases; noted as a
   known edge case of the fallback path, not the primary (anchored) path this task's cases exercise.
4. **Runs against other ACT/BEL years changed as a side effect** (e.g. ACT 2018 moved from
   pp.3-4 to pp.30-30) since `_run_localization` now prefers canonical source data wherever a
   `CanonicalExtractionRun` exists, and the boundary algorithm itself changed. Per the task's scope
   ("only the specific report-years needed... not corpus-wide perfection"), these were not
   individually verified against source PDFs -- only the four designated motivating cases (ACT
   2021, BEL 2019, BEL 2020, BEL 2021) and the BEL 2022 regression spot-check were.

## 10. Final verdict

**PASS WITH DOCUMENTED CAVEAT -- FOUNDATION READY FOR 7C.2**

Three of the four target cases pass end-to-end (schedule boundary corrected *and* the downstream
semantic unit resolves): ACT 2021 `cfo_conclusion`, BEL 2019 `gross_margin`, and the BEL
2021/2022 regression check (no regression on the previously-working case). The fourth (BEL 2020)
has its schedule boundary corrected exactly as intended -- the Gross Margin page is now included,
proving the hierarchy fix itself works generally, not just for ACT -- but a separate, narrower,
pre-existing limitation in the unmodified semantic-unit extractor's heading-detection prevents the
unit from resolving. That limitation is outside 7C.1b's scope by the task's own instruction and is
reported here, not patched. The core, principled correction this task set out to make -- schedule
boundaries respect document hierarchy instead of treating every `HEADING_CANDIDATE` as an equally
valid boundary -- is demonstrated working on real corpus data across two issuers, using
document-relative signals with no absolute or issuer-specific thresholds, per the explicit stop
condition: this is not the start of another 7C.1 remediation cycle, it is the foundation 7C.2 can
now build on.

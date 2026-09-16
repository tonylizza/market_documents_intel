# Track 7C.1a — Canonical PDF Source Representation

Status: implementation complete. Not a new research experiment; not 7C.2 (alignment), which was
not started. Scope: fix the *source representation* the 7C.1 replacement pipeline reads from,
without redesigning schedule localization or semantic-unit extraction, without adding alignment
or comparison of any kind, and without chasing every ACT/BEL year to a passing result.

## 1. Why 7C.1a was needed

The 7C.1 real-corpus acceptance run (`docs/implementation/track-7c1-acceptance.md`) established
that the 7C.1 schedule/semantic-unit architecture itself is viable, but exposed a recurring
anti-pattern: legacy `TextBlock` limitation → add heuristic → another report exposes another
limitation → add another heuristic. Two concrete findings forced the stop:

1. **BEL 2020**: the Gross Margin paragraph is present in the source PDF and directly readable by
   PyMuPDF, but the persisted legacy `TextBlock` rows omit essentially all of it — only the
   trailing word "Gross margin" survives, fused onto the preceding paragraph (acceptance report
   §2.4).
2. **ACT**: the legacy `TextBlock` layer marks many internal CFO-review subsection headings as
   `HEADING_CANDIDATE`, but carries no font-size, heading-level, or hierarchy signal to
   distinguish a genuine schedule boundary from an internal subsection heading (acceptance report
   §4.3) — a materially larger, structural problem, not a narrowly-scopable bug.

The decision (recorded in this task's brief): keep the 7C.1 foundation, stop treating legacy
`TextBlock` as the canonical source for the replacement pipeline, and build a source-faithful
representation directly from the raw PDF instead.

## 2. Legacy extraction limitations observed (audit)

`services/pdf_extraction.py::extract_page` reads PyMuPDF's `page.get_text("dict")` — the richest
form PyMuPDF offers — but immediately flattens it: per block, line/span text is joined, span font
sizes are averaged into one `font_size`, span bold flags are majority-voted into one `is_bold`,
and font *name* is discarded entirely. `services/extraction.py::_run_extraction` then persists
exactly one `TextBlock` row per kept block (`models/extraction.py`), with no line or span
granularity, no font name, and no per-span geometry. Nothing is dropped by conscious policy at
that stage — the flattening is simply lossy by construction, which is how the BEL 2020 paragraph
loss (a body paragraph, not obviously a fragment) and the ACT hierarchy gap (no font signal below
one number per block) both trace back to the same root cause: text and structure collapse into a
single row before anything downstream can see the original evidence.

The extraction-representation bake-off (`docs/experiments/annual-report-extraction-representation-bakeoff.md`)
had already found this independently: blocks alone fix visual-order defects (e.g. BEL's heading
blocks emitted last in raw order), but dict/spans — font name and size — are what's needed to
tell a genuine sub-heading from a repeated running header or an internal subsection heading, and
that information was never being kept. It also confirmed a global y-sort of blocks is unsafe
(corrupts multi-column layouts), so canonical extraction preserves native PyMuPDF order
throughout, never re-sorting.

`Report.local_path` (`models/report.py`) is a plain, reliable filesystem path, already reused
as-is by `services/pdf_access.py::open_for_extraction` — no new path-resolution logic was needed.

## 3. Canonical source schema

Five new tables, additive only, mirroring the `ExtractionRun`/`Page`/`TextBlock` Run/Result
pattern (`models/pdf_source.py`):

```
CanonicalExtractionRun (report_id, extractor_name/version, configuration_hash,
                         status, started_at/completed_at, error_message,
                         expected/processed_page_count)
  -> CanonicalPage (canonical_run_id, report_id, page_number, width, height)
    -> CanonicalBlock (page_id, block_order, native_type, bbox, raw_text)
      -> CanonicalLine (block_id, line_order, bbox)
        -> CanonicalSpan (line_id, span_order, text, bbox,
                           font_name, font_size, font_flags, is_bold, color)
```

`block_order`/`line_order`/`span_order` are PyMuPDF's own emission order, persisted verbatim —
never re-sorted by y-coordinate. `native_type` is PyMuPDF's raw block type (0 = text, 1 = image);
image blocks are persisted for bbox/order completeness with no line/span children. No cleaning,
filtering, or classification happens at this layer: empty spans, short spans, and apparent page
furniture are all persisted exactly as PyMuPDF reports them. `"current successful run"` is a
query-time rule (`services.canonical_extraction.get_current_canonical_run`), never a stored flag,
matching every other Run/Result pair in the codebase.

## 4. Source adapter design

`services/source_adapter.py` gives 7C.1 (`schedule_localization.py`, `semantic_unit_extraction.py`)
a way to consume canonical data without either service's pure algorithms or persisted models
changing at all:

- `SourcePage`/`SourceBlock`/`SourceLine`/`SourceSpan` — plain, ORM-free dataclasses, loaded once
  from the database via `load_source_pages`.
- `classify_source_pages` reshapes canonical blocks into the exact `pdf_extraction.ExtractedPage`/
  `ExtractedBlock` shape the legacy pipeline already classifies, then calls
  `block_classification.classify_block` and `header_footer_detection.detect_header_footer_blocks`
  **unchanged** — the same rules, on richer, lossless input, not a second classification
  heuristic. This was a deliberate choice: 7C.1a's job is to fix the *source*, not to invent a
  parallel interpretation of it.
- `build_heading_blocks`/`build_unit_blocks` produce `HeadingBlock`/`UnitBlock` lists — the exact
  same dataclasses `schedule_localization.localize_schedule` and
  `semantic_unit_extraction.extract_unit` already accept. Both pure functions run **completely
  unmodified**; only the data feeding them changed source.

## 5. Files changed

New:
- `src/market_documents/models/pdf_source.py`
- `src/market_documents/services/pdf_source_extraction.py` (pure extraction, mirrors `pdf_extraction.py`)
- `src/market_documents/services/canonical_extraction.py` (run orchestration, mirrors `extraction.py`)
- `src/market_documents/services/source_adapter.py`
- `src/market_documents/cli/canonical_source.py` (`canonical extract`/`canonical status`)
- `migrations/versions/a1f6c9e2d4b7_canonical_pdf_source_schema.py`
- `tests/test_pdf_source_extraction.py`, `tests/test_canonical_extraction_service.py`,
  `tests/test_source_adapter.py`, `tests/test_canonical_extraction_migration.py`

Modified (additive only):
- `src/market_documents/models/enums.py` — `CanonicalExtractionStatus`
- `src/market_documents/models/__init__.py` — new exports
- `src/market_documents/cli/main.py` — registers `canonical` CLI group

Untouched: `services/extraction.py`, `services/pdf_extraction.py`, `services/block_classification.py`
(reused, not modified), `models/extraction.py`, `services/schedule_localization.py`,
`services/semantic_unit_extraction.py`, and every other file in the legacy pipeline.

## 6. Migration

`a1f6c9e2d4b7` (`down_revision = 5c74ac77a25e`), additive only: creates
`canonical_extraction_runs`, `canonical_pages`, `canonical_blocks`, `canonical_lines`,
`canonical_spans`, plus their indexes and the `canonical_extraction_status` enum. Verified
against the local dev database: `alembic upgrade head` applied cleanly; the downgrade/upgrade
round trip is covered by `tests/test_canonical_extraction_migration.py` (removes only the 7C.1a
tables, leaves `schedule_localization_runs`, `semantic_units`, `text_blocks`, `reports` and every
other table untouched).

## 7. Tests

20 tests added, all passing against a real PostgreSQL test database:

- `test_pdf_source_extraction.py` (9): page-number/geometry, native block order (not y-sorted,
  including an explicit "lower block inserted first" case), bbox preservation, line/span
  hierarchy, exact span text, font size/bold metadata, short/empty content retained, and a
  no-loss regression comparing canonical span text against PyMuPDF's own raw `get_text("text")`
  output word-for-word.
- `test_canonical_extraction_service.py` (5): run completes and persists the full hierarchy
  (verified by reconstructing block text purely from persisted spans), idempotent skip without
  `force`, `force` creates a new run, `get_current_canonical_run` returns the latest completed
  run, and an explicit check that canonical extraction never reads or writes
  `ExtractionRun`/`Page`/`TextBlock`.
- `test_source_adapter.py` (4): loads pages without touching legacy tables, classification
  correctly identifies heading candidates from canonical data, and both
  `schedule_localization.localize_schedule` and `semantic_unit_extraction.extract_unit` — the
  unmodified 7C.1 pure algorithms — run successfully against adapter-built `HeadingBlock`/
  `UnitBlock` lists with no `TextBlock` involved anywhere in the test.
- `test_canonical_extraction_migration.py` (2): tables/enum created; downgrade/upgrade round trip
  clean.

```
.venv/bin/python -m pytest tests/test_pdf_source_extraction.py tests/test_canonical_extraction_service.py \
    tests/test_source_adapter.py tests/test_canonical_extraction_migration.py -q
# 20 passed
```

One implementation correction made during testing, not a scope change: the first persistence
draft flushed the session after every single block/line/span row, which is impractically slow
against real ~70-150 page reports (thousands of spans). Since `UUIDPkMixin.id` is a Python-side
default (`uuid.uuid4`), ids are now assigned explicitly before insert and each page's full
row set is batched into one `add_all`/flush — correctness is unchanged (covered by the same
tests), only the write pattern is different.

## 8. BEL 2020 smoke-test result

Canonical extraction completed for BEL 2020 (72 pages). The Gross Margin paragraph — entirely
missing from persisted `TextBlock` per the acceptance report — is present in full, verbatim, on
page 39, block order 2, reconstructed from 17 spans:

```
span: font=CenturyGothic-Bold size=8.0 bold=True   text='Gross margin'
span: font=CenturyGothic      size=8.0 bold=False  text='The gross margin is dependent on the product and geographic '
...
span: font=CenturyGothic      size=8.0 bold=False  text='18,4% compared with 18,5% in the prior year. '
```

This confirms the source-fidelity fix directly: the exact anchor sentence the BEL 2020
`gross_margin` semantic unit needs (`"...18,4% compared with 18,5% in the prior year."`) is now
available at the source layer, with the sub-heading distinguishable from body text by both bold
flag and font name (`CenturyGothic-Bold` vs `CenturyGothic`) — signal that never existed on the
legacy `TextBlock` row for this page at all.

**Re-running 7C.1 against this source (optional Section 8 smoke test, unmodified algorithms):**
`localize_schedule` still resolves the FINANCIAL_PERFORMANCE schedule to pp.38–38 (identical
result to the legacy run), so `extract_unit` for `gross_margin` still reports "start heading not
found" — the paragraph lives on page 39, one page past the schedule instance's own boundary.
This is a **different, narrower problem than the one 7C.1a set out to fix**: the source text is no
longer lost (confirmed above), but the unmodified boundary algorithm in `schedule_localization.py`
still truncates the schedule instance one page early for BEL 2020, for reasons unrelated to source
fidelity. Per the task's explicit stop condition, this is reported, not chased further in this
task.

## 9. ACT structural-signal smoke-test result

Canonical extraction completed for ACT 2021 (134 pages). Every `HEADING_CANDIDATE` block on pages
60–66 (the CFO's review section) now carries per-span font size, distinguishing two clearly
separable clusters:

| Text | Font size | Role |
|---|---|---|
| "OUR PERFORMANCE" | 64.7 | Section-start heading |
| "CFO'S REVIEW" | 62.2 | Section-start heading |
| "Depreciation/amortisation" | 11.4 | Internal subsection |
| "IFRS 16 (leases) net effect" | 11.4 | Internal subsection |
| "Healthcare Services Financial Performance" | 12.0 | Internal subsection |
| "Capital management" | 12.0 | Internal subsection |
| "In conclusion" | 12.0 | Internal subsection (the unit's own start heading) |
| "CFO's review continued" | 14.0 | Continuation banner |

Distinct font sizes observed: `[7.0, 8.5, 11.4, 12.0, 14.0, 62.2, 64.7]` — real section-boundary
headings sit roughly 5× larger than every internal subsection heading in this sample. This is
exactly the structural signal the acceptance report identified as missing (§4.3: "`TextBlock`
carries no font-size, heading-level, or hierarchy signal that would let it" distinguish a
subsection heading from a schedule boundary) — it is now present and trivially separable on this
page range. No attempt was made to build a font-size-based boundary rule in this task (explicit
stop condition); this is reported as available evidence for a future 7C.1 boundary-algorithm
revision, not implemented here.

**Re-running localization (optional Section 8 smoke test, unmodified algorithm):** `localize_schedule`
still resolves ACT 2021's FINANCIAL_PERFORMANCE schedule to a single page (pp.61–61), identical to
the legacy result reported in the acceptance run — expected, since the boundary algorithm itself
was intentionally left unmodified in this task.

## 10. Impact on 7C.1

- **Fixed at the source layer**: BEL 2020's Gross Margin paragraph is no longer lost — any future
  boundary-algorithm work has real text to reconstruct from.
- **New evidence available, not yet used**: ACT's font-size clustering is now visible and
  persisted, giving a concrete, checkable signal a future boundary revision could use to
  distinguish schedule boundaries from subsection headings — without needing new PDF re-parsing
  logic, since it's already captured.
- **Not fixed by this task, by design**: the `localize_schedule` boundary algorithm in
  `schedule_localization.py` is unmodified. Both smoke-test localizations above match their
  legacy-era results, because the algorithm consuming the (now-richer) source hasn't changed.
  Improving it is future 7C.1 boundary-algorithm work, not 7C.1a.
- **Legacy pipeline**: completely untouched — `services/extraction.py`, `pdf_extraction.py`,
  `block_classification.py`, and every legacy model are unmodified and continue to run exactly as
  before. `TextBlock`/`Page` and `CanonicalBlock`/`CanonicalPage` now exist side by side for the
  same reports, exactly as specified.

## 11. Final verdict

**PASS WITH DOCUMENTED CAVEAT**

The canonical source representation is source-faithful and verified lossless on both flagged
failure cases: BEL 2020's previously-missing paragraph is fully present with font/style metadata,
and ACT's previously-invisible heading-hierarchy signal is now captured and cleanly separable.
The adapter lets 7C.1's existing, unmodified pure algorithms consume this representation directly
(demonstrated by both automated tests and the real-corpus smoke test), with no legacy table
touched or modified.

The caveat: fixing the source representation did not, by itself, fix BEL 2020 or ACT 2021's
end-to-end localization/extraction results, because the boundary algorithm that turns headings
into schedule/unit page ranges was deliberately left unmodified in this task. That is expected and
correct given the task's explicit stop condition ("do not continue adding schedule-boundary
heuristics," "do not begin 7C.2") — the foundation this task was asked to build (a non-lossy,
richly-structured source layer, with an adapter proven to work against 7C.1's real algorithms) is
in place and ready for that follow-up work, not a repeat of the heuristic-patching loop this task
was created to stop.

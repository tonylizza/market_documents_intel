# Track 7C.4: Structured-Table Comparison

## 1. Scope

7C.4 implements the `STRUCTURED_COMPARISON_PREFERRED` modality that 7C.3 declared but never
executed. It reconstructs exactly two validated ACT table families --
`ned_remuneration_policy_table` and `total_remuneration_outcomes` -- from the canonical PDF layer
(7C.1a) into first-class `table -> rows -> columns -> cells -> footnotes` structures, aligns them
across adjacent-year `ReportPair`s, and emits explicit structured value-change events. A table is
never flattened to prose and compared lexically: row × column × value × footnote relationships are
preserved throughout, per the milestone's core instruction and the research doc
(`docs/experiments/annual-report-structured-table-comparison.md`) that validated the method.

Out of scope, per the milestone's own "hard stop": any other ACT table family, BEL, chart
extraction, LLM/VLM parsing, materiality scoring, or publishing.

**Architectural decision**: 7C.4 does not route through `SemanticUnit`/`SemanticUnitAlignment`/
`AnalyticalDecision`. Those models assume a heading string identical every year
(`semantic_unit_extraction._matches_heading` does literal substring matching); both table headings
embed the fiscal year and drift in case ("Non-executive Directors' 2020 remuneration" vs.
"NON-EXECUTIVE DIRECTORS' 2023 REMUNERATION"). 7C.4 is instead a parallel track reading only
`CanonicalBlock` (7C.1a) -- never `SemanticUnit`, `Passage`, or `PassageAlignment` -- with each
table family's own year-agnostic heading regex playing the localization role directly. It also does
**not** depend on schedule localization: REMUNERATION was never configured in 7C.1 (only
FINANCIAL_PERFORMANCE is), and adding it there would mean reopening 7C.1's own mechanism, which the
milestone explicitly forbids. `AnalyticalMode.STRUCTURED_COMPARISON_PREFERRED` is still reused, as a
fixed tag on `StructuredTable`, sourced from `TableFamilyConfig` -- this is how 7C.4 "uses the 7C.3
analytical mode" without touching `AnalyticalDecision`.

## 2. Structured data model

`src/market_documents/models/structured_table.py` (migration
`migrations/versions/db8ee3ff6003_structured_table_comparison_schema.py`):

Reconstruction: `StructuredTableExtractionRun` (pins `CanonicalExtractionRun`) ->
`StructuredTable` (one per report per table family) -> `StructuredTableColumn` /
`StructuredTableRow` -> `StructuredTableCell` (unique `(row, column)`, enforcing "no cell in two
places" as a DB constraint) and `StructuredTableFootnote` (table-level, with optional scoping to a
row/column/cell).

Comparison: `StructuredTableAlignmentRun` (pins both source `StructuredTableExtractionRun`s) ->
`StructuredRowAlignment` / `StructuredColumnAlignment` -> `StructuredValueChangeEvent`.

Every Run follows the established idempotency convention exactly (`algorithm_version`,
`configuration_hash`, query-time "current successful" resolver, `force` rerun, `begin_nested()`
transactional worker, `FAILED`/`COMPLETED_WITH_WARNINGS` status split) -- see
`services.structured_table_reconstruction.run_table_reconstruction` and
`services.structured_table_comparison.run_table_comparison`.

## 3. Reconstruction strategy

`services/structured_table_config.py` defines a `TableFamilyConfig` per family: a year-agnostic
heading regex, `row_identity_type` (ROLE or PERSON), and a fixed `column_schema` (semantic keys,
group labels, year offsets, restated flags) -- column *meaning* is a configuration decision, not
parsed from drifting header text, per the milestone's "column identity must be semantic, not
positional only" instruction.

`services/structured_table_reconstruction.py` implements the row-block methodology the research doc
validated: `CanonicalBlock.raw_text` groups one table row per block, row-major, in native order. The
parser:

- Locates the heading block via the family's regex, then walks subsequent blocks on the **same
  page only** (all 10 validated table-years fit one page; crossing a page boundary is out of scope,
  matching the research doc's own untested caveat).
- Splits each block into label lines and value lines (value lines match a South-African
  thousand-space-grouped number, `–`, `"Waived fee"`, or `"N/A"`); a label followed by zero values
  is a category (e.g. "Main Board (annualised retainer fee)"), one or more values makes it a row.
  Consecutive zero-value label lines are joined (a category can wrap across two PDF lines).
- Tokenizes value lines with a single regex pass, splitting glued multi-value lines
  (`"2 400 000 10 209 360"` -> two numbers) and detecting a footnote-marker digit glued to a number
  with no space (`"1 148 9041"` -> `"1 148 904"` + marker `"1"`).
- Recognizes a `TOTAL`-labelled row as the terminal row for `total_remuneration_outcomes`, and
  guards against a purely-numeric misfired label (a real corpus case: a column-header year-fragment
  block inside the table's own region) by requiring every genuine row label to contain a letter.
- Collects footnotes in a separate pass (bounded to within ~200pt of the last row), independent of
  where row-scanning stopped -- a real corpus case (2024 `total_remuneration_outcomes`) interposes
  an unrelated "STI performance outcomes" narrative section between the `TOTAL` row and its own
  footnote.
- Excludes ACT's own running header/footer ("AFROCENTRIC GROUP...", "...INTEGRATED REPORT...") by
  literal substring match -- intentionally company-scoped, per the milestone's "family-configured,
  not universal" instruction.

Three further real-corpus hazards, found and fixed during validation against the actual ACT PDFs
(not just the research doc's paraphrased examples):

1. **2024 `total_remuneration_outcomes`'s landscape-oriented page** emits its row-data blocks
   *before* the heading block in native PyMuPDF order. Fixed by widening the candidate filter
   (region-based, not "block_order > heading's") while keeping native `block_order` as the sort
   key -- never switching to a y-position sort, which was tried and reverted because it corrupts a
   *different* real page (2024's NED table, a genuine two-column layout where a category label's
   y0 can be marginally greater than its own row-data block's y0).
2. A single-line footnote (marker and text on the same PDF line, unlike every other footnoted case
   in this corpus) required broadening the footnote-line pattern.
3. `\x07` (a PDF rendering artifact around one footnote marker) is not whitespace by Python's
   `str.strip()`/`\s` semantics and leaked into footnote text; stripped explicitly.

## 4. Row identity

`ned_remuneration_policy_table`: role-based, `category::role`. Cosmetic drift is normalized before
comparison (not at the raw `source_label`/`category_label` level, which stay verbatim for
provenance): "Chairperson"/"Chairman" collapse to one canonical role (confirmed the same committee
seat across the real corpus); a trailing parenthetical fee-basis qualifier ("(per meeting)" vs.
"(per annum)", "(annualised retainer fee)" vs. "(annualised retainer fee*)") is stripped from the
category; a leading footnote-marker asterisk (2023's `*ICT STEERING COMMITTEE...`, uniquely glued to
the front of the category rather than the role) is stripped; and one explicit, source-confirmed
category alias ("Subsidiary board/committee" -> "Subsidiary board", the research doc's own
acknowledged 2024 rename) is applied.

`total_remuneration_outcomes`: person-based, the normalized name alone -- deliberately **never**
category-qualified. A real corpus case justifies this: the 2023 page's column-header fragments sit
close enough to the row data that this parser's category-carry state can pick up a spurious category
just before the real rows, which would silently break every person's cross-year match if category
were part of the identity.

## 5. Comparability model

Row alignment (`services.structured_table_comparison.align_rows`): exact match on normalized
identity. Present only earlier -> `REMOVED`; only later -> `ADDED`; both sides -> `MATCHED`, unless
the later side's current-year (non-restated) cells are all nil/missing while the earlier side has
real values, in which case `COMPARATIVE_ONLY` (the transition-year departure pattern). No succession
inference: a departure and a new hire in the same table-year are always two separate `REMOVED`/
`ADDED` edges, never merged.

Column alignment: match on `normalized_key` -- but a `(normalized_key, is_restated)` pair, since a
metric's current-year and prior-year-restated columns share the same key by design. `MATCHED` by
default with `DIRECTLY_COMPARABLE`; a small explicit `ColumnSchemaChange` table
(`structured_table_config.py`) flags the one known case (STI -> "STI and Retention Awards", first
affecting the 2023 report) as `PARTIALLY_COMPARABLE_SCHEMA_CHANGED` -- alignment and comparability
are persisted as two separate fields, since the column stays `MATCHED` in position/key even as its
composition changes.

## 6. Footnote model

`StructuredTableFootnote` preserves the exact marker, text, page, and source `CanonicalBlock`, with
optional scoping to a row/column/cell. Multiple footnotes concatenated in one PDF block (a real
2020 `total_remuneration_outcomes` case) are split correctly.

## 7. Value-change events

`classify_value_change` (pure) covers every `StructuredValueChangeEventType`: ordinary
increase/decrease/unchanged with `absolute_change`/`pct_change`; zero/nil/missing transitions with
both fields left `NULL`; `SCHEMA_CHANGED` and `COMPARATIVE_ONLY` rows/columns suppress the ordinary
diff entirely rather than fabricating a percentage across a non-comparable transition.

## 8. Tests

`tests/test_structured_table_config.py` (9 tests, pure): configuration hash determinism, year-
agnostic heading matching, schema-change year-window logic.

`tests/test_structured_table_reconstruction.py` (17 tests, pure): fixtures are literal
`CanonicalBlock.raw_text` values taken directly from the real ACT 2020 pages (not paraphrased) --
row/column/cell reconstruction, nil/waived/zero/missing/N-A distinction, footnote-marker splitting,
glued-value/glued-marker tokenization, the two real-corpus hazard fixes.

`tests/test_structured_table_comparison.py` (18 tests, pure): row MATCHED/ADDED/REMOVED/
COMPARATIVE_ONLY, succession never merged, column MATCHED + PARTIALLY_COMPARABLE_SCHEMA_CHANGED, the
current/restated column-identity collision fix, every value-change event type, pct_change
NULL-suppression.

`tests/test_structured_table_services.py` (8 tests, DB-backed): full
`CanonicalBlock -> StructuredTable -> rows/columns/cells -> StructuredTableAlignmentRun ->
StructuredRowAlignment/StructuredValueChangeEvent` integration; ineligibility gates; idempotent
rerun + `force`; no `SemanticUnit`/`Passage` import dependency.

Full suite: **1023 passed, 3 skipped, 0 failed** (`.venv/bin/python -m pytest -q`), including this
milestone's 52 new tests, with zero regressions to any earlier track.

## 9. ACT real-corpus results

`units structure ACT --table-family ned_remuneration_policy_table` /
`--table-family total_remuneration_outcomes`, full 2016-2024 corpus:

| Year | NED rows | NED footnotes | Outcomes rows | Outcomes footnotes |
|---|---|---|---|---|
| 2016-2018 | not found (table doesn't exist yet) | -- | not found | -- |
| 2019 | not found | -- | 6 | 2 |
| 2020 | 17 | 1 | 5 | 2 |
| 2021 | 15 | 2 | 5 | 0 |
| 2022 | 18 | 1 | 5 | 0 |
| 2023 | 17 | 1 | 5 | 0 |
| 2024 | 18 | 1 | 4 (1 spurious header row correctly dropped, noted `MINOR_CORRECTION_NEEDED`) | 1 |

All reconstructions `CLEAN` except 2024 `total_remuneration_outcomes`
(`MINOR_CORRECTION_NEEDED` -- a numeric-only column-header fragment inside the table's own region
was correctly recognized as non-alphabetic and skipped rather than persisted as a spurious row).

`units compare-structured ACT --table-family ...`, all adjacent pairs:

**NED table** row events exactly match the research doc's Section 7.1 table: 2020->2021
`REMOVED`=3 (Subsidiary board Chairman/Member absent 2021, ICT Steerco Chairperson absent),
`ADDED`=1 (Lead Independent Director, new 2021); 2021->2022 `ADDED`=3 (Subsidiary board rows and ICT
Steerco Chairperson return); 2022->2023 `MATCHED`=17, `REMOVED`=1 (ICT Steerco Chairperson absent
again); 2023->2024 `MATCHED`=17, `ADDED`=1 (Special ad hoc board/committee row, new 2024). Value
changes for the Main Board Chairman fee line reproduce the research doc's Section 9 series exactly:
1 329 240 -> 1 375 763 -> 1 445 849 -> 1 445 849 -> 1 503 683 -> 1 578 867 (2020-2024).

**Outcomes table**: 2020->2021 and 2021->2022 fully `MATCHED` (5/5 rows); 2022->2023 `MATCHED`=3
(Banderker, Boonzaaier, TOTAL), `COMPARATIVE_ONLY`=2 (W Britz, S Mmakau -- current-year dash, prior
comparative retained); 2023->2024 `MATCHED`=3, `REMOVED`=2 (Britz/Mmakau fully gone), `ADDED`=1
(G van Wyk) -- exactly the three-stage departure pattern and CEO succession the research doc
documents in Sections 7.2/10. H Boonzaaier's `total_remuneration` percentage changes reproduce the
research doc's Section 9 table exactly: +6.1%, -0.5%, +39.2%, -47.5% across the four transitions.

## 10. Parity with research ground truth

Every numeric value, row event, and percentage change checked above reproduces the research doc's
documented figures exactly. Two real-corpus findings **diverge** from the research doc, resolved in
favor of direct verification against the actual PDFs (the same discipline 7C.1/7C.3 applied to their
own prior-research corrections):

- The research doc's Section 7.1 table lists `Subsidiary board :: Chairman/Member` as present
  (`P`) in all five years 2020-2024. The real 2021 ACT NED table has **no** "Subsidiary board"
  category at all -- confirmed by a direct full-text search of the real 2021 PDF, not just the
  reconstructed table. Section 7.1's own `ADDED (2021)` events (Lead Independent Director) are
  otherwise fully consistent with this correction.
- The research doc's Section 2 inventory does not identify a footnote on the 2023
  `total_remuneration_outcomes` page; direct reading of the real page confirms none exists there
  (the STI/Retention Awards explanation it describes sits on a different, out-of-scope
  `individual_remuneration_outcomes` page).

## 11. Caveats

- A table row spanning a page break is untested (no table-year in the validated corpus has one),
  matching the research doc's own stated gap.
- `SUCCESSION_INFERRED` (linking a `REMOVED` + `ADDED` pair as a probable succession, e.g.
  Banderker -> van Wyk) is explicitly deferred to a future entity layer, per the milestone's own
  instruction.
- The `_FOOTNOTE_MAX_Y_GAP` bound (200pt) is a real-corpus-calibrated heuristic (resolves a genuine
  false-positive footnote match from an unrelated scorecard table further down the 2023 page), not
  a value derived from the source PDF's own structure.
- ACT's running-header/footer exclusion is intentionally company-specific text matching, consistent
  with this milestone's family-configured (not universal) scope.

## 12. Final verdict

**PASS -- READY FOR 7C.5**

Both validated ACT table families reconstruct source-faithfully from `CanonicalBlock`, align by
row/column across every adjacent-year pair without collapsing nil/missing/schema-change states, and
trace every row/column/cell/footnote back to canonical source provenance. Reconstructed values and
row/column alignment events reproduce the research doc's documented ground truth exactly, including
the exact percentage-change series for two independent metrics (NED Chairman fee, Boonzaaier total
remuneration). Real-corpus validation surfaced and fixed several genuine hazards not visible in the
research doc's paraphrased examples (landscape page-layout block ordering, a two-column NED layout,
glued footnote markers, a spurious numeric header row, an unrelated scorecard table false-positiving
as a footnote) -- the same kind of real-corpus correction pass every prior 7C track required. The
full test suite passes with zero regressions to any earlier track.

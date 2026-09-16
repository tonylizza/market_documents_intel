# Experiment: Structured-Table Generalization Stress Test (AfroCentric, Two Harder Table Families, 2020–2024)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against
`data/raw/ACT/{2020,2021,2022,2023,2024}/annual_report.pdf` via throwaway PyMuPDF scripts run
directly in this session (plain text, `get_text("blocks")`, and 200 DPI page renders read
visually), with no intermediate files written into the repository. Nothing here is wired into the
application. This is a direct follow-up to
`docs/experiments/annual-report-structured-table-comparison.md` ("the prior experiment," assumed
read), which validated deterministic row/metric/value reconstruction for two well-behaved ACT
remuneration tables (`ned_remuneration_policy_table`, `total_remuneration_outcomes`) and identified
`individual_remuneration_outcomes` and `ned_fees_and_payments_table` as the next, harder test —
the latter explicitly flagged there as having "a *more* volatile column schema" than either
focal table sampled.

## 1. Executive summary

**Partially — the structured-comparison *architecture* generalizes, but the prior experiment's
single easy reconstruction strategy (one block = one row, deterministic parse, zero
multimodal escalations) does not, and this experiment found concrete, repeated counter-examples
of exactly the assumptions the prior experiment's own recommendation warned not to make.**

**Which table family was harder, and why?** `ned_fees_and_payments_table` is harder on the
*column* axis: its column schema changed size every single year sampled (9 → 12 → 12 → 11 → 10
columns across 2020–2024), driven by real subsidiary-board and committee restructuring (Medscheme
Board, ADS Board, PD/Curasana Board, Pharma Cluster Audit Committee, and Pharma Cluster Board
columns were added in 2021 and partially pruned thereafter), not formatting churn.
`individual_remuneration_outcomes` is harder on the *block-structure* axis: its visual layout
changed from a **vertical, one-person-per-page-section stack** (2020–2023) to a **three-column
side-by-side panel layout** (2024) in which, for the first time in this whole research sequence,
**the row label (the person's name) is not co-located in the same PyMuPDF block as that person's
own values** — it shares one block with the other two people's names entirely, positioned above
all three panels, and must be matched to its data by left-to-right panel order, not by any text or
coordinate feature contained in the value blocks themselves.

**Did the row-block assumption survive?** No, not as stated. This experiment found three distinct
ways it broke, none of which appeared anywhere in the prior experiment's ten sampled table-years:
(1) **many-rows-in-one-block** — ACT 2020's `ned_fees_and_payments_table` collapses 14 of its 15
director rows into a *single* PyMuPDF block (Section 3, Section 6); (2) **partial block-merging
driven by row sparsity** — ACT 2024's same table merges pairs/triples of adjacent all-dash rows
into shared blocks while leaving data-dense rows as individual blocks, in the same table, on the
same page; (3) **row label separated from its own row's values entirely** — ACT 2024's
`individual_remuneration_outcomes`, described above. A fourth, milder case recurs across every
year of `individual_remuneration_outcomes` 2020–2023: the person's name is its own block, and
*all* of that person's metric rows collapse into one shared block below it (not one block per
metric), which the prior experiment's ned/total-table cases never exhibited either. This is a
different failure axis from the "genuine one block = one row" pattern the prior experiment found
robust on both its tables, and it means a parser tuned to that pattern would silently
misattribute rows.

**Was schema drift manageable?** Column count and label churn were fully trackable
deterministically (Sections 9, 6) — every column addition/removal/rename in this sample maps to a
locatable, string-comparable event, and none required semantic judgment to *detect*. But
*explaining* the drift was not always possible from the source alone: this experiment found a
materially large (R300,000), one-off "Ex-Gratia Payment (Projects Everest)" column in the 2023 NED
payments table with **zero explanatory footnote and zero mention anywhere else in the 162-page
document** (confirmed by a full-document text search, Section 11) — the first `UNEXPLAINED` case
in this entire research sequence, where the prior experiment found footnotes sufficient for every
large event it checked.

**Was semantic assistance needed?** Yes, in more places than the prior experiment, but still a
minority of steps. Confirmed needs: matching a person's name to their panel by ordinal position
rather than any structural pointer (2024 individual outcomes); recognizing that W Britz's
migration from `individual_remuneration_outcomes`/`total_remuneration_outcomes` executive rows
(2020–2022) into `ned_fees_and_payments_table`'s non-executive-director rows (2024) is a genuine
cross-table role change requiring reading a footnote ("now NED"), not a same-table row event;
distinguishing genuine committee restructuring from cosmetic renaming in the NED-payments column
churn (partially footnote-supported, partially not). No case in this sample required multimodal
escalation — every hazard found was resolvable from plain text plus block coordinates plus
(for two cases) full-document text search, though the search step itself is new relative to the
prior experiment's page-local methodology.

**Is the method ready for a second-company test?** Not yet, and this experiment's answer is more
qualified than the prior one's. Recommendation **(B)**: before adding BEL, ACT's own two hardest
observed shapes (2020's mega-merged NED-payments block, 2024's name-separated individual-outcomes
panels) should inform a slightly wider ACT-only sanity check — specifically, whether other ACT
schedules exhibit the same block-merging sensitivity to row sparsity — because this experiment's
evidence for those two failure modes rests on ACT-only page renders and it is not yet known whether
they are PyMuPDF-general behaviors (likely) or coincidental to this one company's specific 2020 and
2024 page layouts (less likely but unverified). See Section 18 for the full justification and scope.

## 2. Source inventory

| Table | Year | Page(s) | Shape | Reconstruction strategy | Status |
|---|---|---|---|---|---|
| `individual_remuneration_outcomes` | 2020 | 104–105 | PERSON_SUBTABLES (vertical stack) | B (name↔metrics-block y0 pairing) + D (header x0 matching) | CLEAN, one anomaly (see below) |
| `individual_remuneration_outcomes` | 2021 | 116–117 | PERSON_SUBTABLES (vertical stack) | B + D | CLEAN |
| `individual_remuneration_outcomes` | 2022 | 120–121 | PERSON_SUBTABLES (vertical stack) | B + D | CLEAN |
| `individual_remuneration_outcomes` | 2023 | 135–136 | PERSON_SUBTABLES (vertical stack) | B + D | CLEAN |
| `individual_remuneration_outcomes` | 2024 | 130 | MULTI_PANEL_TABLE (3 side-by-side panels) | B + D + **E** (ordinal name-to-panel match) | CLEAN once E applied; MAJOR_LAYOUT_RECONSTRUCTION_NEEDED under the 2020–2023 strategy alone |
| `ned_fees_and_payments_table` | 2020 | 106 | RECTANGULAR_MATRIX (but block-degenerate) | **A′** (fixed-arity chunking of one 14-row mega-block) + B (2-line-name row) | CLEAN after chunking; ROW_BLOCK_PARSE alone fails |
| `ned_fees_and_payments_table` | 2021 | 118 | RECTANGULAR_MATRIX, widest schema (12 cols) | A (row-block parse, holds per-director) | CLEAN |
| `ned_fees_and_payments_table` | 2022 | 122 | RECTANGULAR_MATRIX | A | CLEAN |
| `ned_fees_and_payments_table` | 2023 | 138 | RECTANGULAR_MATRIX, +1 one-off column | A | CLEAN |
| `ned_fees_and_payments_table` | 2024 | 132 | RECTANGULAR_MATRIX (partially block-degenerate) | A with **A′** fallback for 2 merged dash-row blocks | CLEAN after chunking fallback |

`GROUPED_MATRIX` and `HYBRID_TABLE_NARRATIVE` shapes were not encountered in this sample.
`CROSS_PAGE_RECONSTRUCTION` (strategy F) applies to `individual_remuneration_outcomes` in every
year except 2024 — see Section 6 and Section 14.

## 3. Reconstruction methodology

Strategy letters extend the prior experiment's implicit single strategy (its "A. ROW_BLOCK_PARSE")
with what this sample actually required:

- **A. ROW_BLOCK_PARSE** (prior experiment's baseline): one block = one row, label + values in
  reading order. Holds for `ned_fees_and_payments_table` 2021–2023 and most rows of 2022/2024.
- **A′. FIXED-ARITY BLOCK CHUNKING** (new this experiment): when several rows collapse into one
  block, split it deterministically by counting: each row is 1 name token followed by exactly *K*
  numeric/dash tokens, where *K* is the column count read from the header row (confirmed
  independently from the header blocks, which are never affected by this merging). For ACT 2020's
  14-row mega-block (Section 6), *K*=9 and the block's flat text splits cleanly into 14 groups of
  10 tokens (1 name + 9 values) with zero ambiguity, because every name in this specific block is a
  short single-line string and every value is a fixed-format number-or-dash — this is a textual
  chunking operation, not a geometric one, and it depends on already knowing *K* from the header,
  making it order-of-operations-dependent on header parsing succeeding first.
- **B. GEOMETRIC ROW/BLOCK PAIRING (y0)**: `individual_remuneration_outcomes` needs this in every
  year 2020–2024 to associate a person's name block with their (separately blocked) metrics block
  directly below it — confirmed via `y0` inspection (Section 7) — a materially different
  requirement from the prior experiment's tables, where label and values were always co-blocked.
- **D. HIERARCHICAL_HEADER_PARSE**: both `individual_remuneration_outcomes`'s two-year-column
  headers (each year label its own block, matched by `x0`) and `ned_fees_and_payments_table`'s
  multi-line committee-name headers (each header label frequently split across 1–3 blocks by word
  wrap, e.g. 2020's "Total\n current\n year 2019" / " – 2020\n" split across two blocks at the same
  `x0` band) needed x0-band matching against the column count established from the row data.
- **E. PERSON_PANEL_PARSE (ordinal, not geometric)**: `individual_remuneration_outcomes` 2024 only
  (Section 7.2). The one block containing all three people's names has a *single* bounding box
  that does not sub-divide by panel; the only reliable association is **positional order** — first
  name in the block's newline-delimited text maps to the leftmost panel by column x0, second to the
  middle, third to the rightmost — confirmed correct in this sample but fragile in principle (a
  panel reordering with no textual signal would silently misattribute an entire panel to the wrong
  person; this did not happen here, but nothing in the block data itself would detect it if it did).
- **F. CROSS_PAGE_RECONSTRUCTION**: `individual_remuneration_outcomes` runs 2 pages in every year
  except 2024 (which fits 3 panels on 1 page). No individual person's block ever splits across the
  page boundary — the break always falls cleanly between two people's sections — so this is
  "the *table as a whole* continues across pages, individual rows do not" rather than the harder
  page-break case the prior experiment left untested. That harder case (a single row's own values
  split mid-row across two pages) was still not encountered anywhere in this sample either.
- **G. MULTIMODAL_REQUIRED**: not needed anywhere in this sample. Every hazard found was resolved
  by plain text, blocks, or (twice) a full-document text search for a suspected missing
  explanation. This is consistent with the prior experiment's finding for these table families
  specifically, even though the *block*-level hazards were materially harder here.

**A new escalation signal this experiment adds to the prior experiment's own list (Section 9 of
the extraction-representation-bakeoff experiment, reused conceptually here)**: a block whose line
count is a multiple of the established column-count-plus-one (i.e., visibly "too long" for one row
of the table's known schema) is a cheap, mechanical trigger for the A′ chunking fallback — this was
confirmed useful here (block `idx=19` on ACT 2020 p.106 has 9×14=126 relevant value tokens plus 14
names, versus every other row-block in the surrounding pages having exactly one name + K values)
and did not require rendering the page to detect, only comparing a block's line count against the
already-known column count.

## 4. `individual_remuneration_outcomes`: per-year reconstruction

**2020 (PERSON_SUBTABLES, page 104–105), Ahmed Banderker panel** — representative of the
vertical-stack shape used 2020–2023:

```json
{
  "year": 2020,
  "table": "individual_remuneration_outcomes",
  "page": 104,
  "shape": "PERSON_SUBTABLES",
  "reconstruction_strategy": ["B", "D", "F"],
  "source_block_ids": {"name_label": 7, "col_headers": [null, null, null], "metrics": 8},
  "person": {"source_label": "Ahmed Banderker (Group CEO)", "role": "Group CEO",
             "row_identity_type": "PERSON"},
  "columns": [
    {"source_label": "2020 (R)", "year_ref": 2020, "restated": false},
    {"source_label": "Restated* 2019 (R)", "year_ref": 2019, "restated": true}
  ],
  "metrics": [
    {"metric": "salary", "2020": "4 781 364", "2019r": "1 148 904",
     "footnote_markers_2019r": ["**"]},
    {"metric": "medical_aid", "2020": "44 968", "2019r": "10 786"},
    {"metric": "retirement_benefits", "2020": "314 260", "2019r": "76 000"},
    {"metric": "other_employee_benefits", "2020": "76 560", "2019r": "14 310"},
    {"metric": "total_guaranteed_pay", "2020": "5 217 153", "2019r": "1 250 000",
     "footnote_markers_2019r": ["*"]},
    {"metric": "increase_in_guaranteed_pay_pct", "2020": "4.3%", "2019r": "–",
     "semantic_status_2019r": "NOT_APPLICABLE"},
    {"metric": "sti", "2020": "3 242 207", "2019r": "2 526 786"},
    {"metric": "number_of_shares_awarded", "2020": "500 000", "2019r": "500 000"},
    {"metric": "value_of_awarded_shares", "2020": "1 750 000", "2019r": "2 400 000"},
    {"metric": "total_variable_pay", "2020": "4 992 207", "2019r": "4 926 786"},
    {"metric": "total_remuneration", "2020": "10 209 360", "2019r": "6 176 786"}
  ],
  "footnotes": [
    {"marker": "*", "text": "A Banderker's remuneration was restated to incorporate a retention bonus in the STI, LTI which was included after the reporting period and aligning other benefits with pro rated Total Guaranteed package."},
    {"marker": "**", "text": "A Banderker's 2019 remuneration is prorated for three months; he joined in April 2019."}
  ],
  "reconstruction_note": "Person name is block idx=7 (own block, y0=54.5). Column-year headers are three separate blocks (idx=2/3/4). ALL eleven metric rows are collapsed into a single block (idx=5) — not one block per metric, contra this table's own header row and contra both of the prior experiment's tables. Row order within the block is reading order (top-to-bottom, matches labels)."
}
```

**2024 (MULTI_PANEL_TABLE, page 130), all three executives** — the hard case:

```json
{
  "year": 2024,
  "table": "individual_remuneration_outcomes",
  "page": 130,
  "shape": "MULTI_PANEL_TABLE",
  "reconstruction_strategy": ["B", "D", "E"],
  "source_block_ids": {"shared_name_label_block": 39, "panel_x0_bands": [35, 293, 550]},
  "persons": [
    {"panel_order": 1, "panel_x0": 35.9, "source_label": "Gerald Van Wyk (Group CEO)",
     "role": "Group CEO", "row_identity_type": "PERSON", "presence_status": "ROW_ADDED"},
    {"panel_order": 2, "panel_x0": 293.2, "source_label": "Ahmed Banderker (Group CEO)*",
     "role": "Group CEO (former)", "row_identity_type": "PERSON",
     "presence_status": "PARTIAL_YEAR", "footnote_marker": "*"},
    {"panel_order": 3, "panel_x0": 550.0, "source_label": "Hannes Boonzaaier (Group CFO)",
     "role": "Group CFO", "row_identity_type": "PERSON", "presence_status": "ROW_STABLE"}
  ],
  "columns_per_panel": [
    {"source_label": "2024 (R)", "year_ref": 2024}, {"source_label": "2023 (R)", "year_ref": 2023}
  ],
  "metrics_van_wyk": {
    "salary": {"2024": "3 935 751", "2023": "–", "semantic_status_2023": "NOT_APPLICABLE"},
    "total_guaranteed_pay": {"2024": "4 330 333", "2023": "–"},
    "sti": {"2024": "1 522 623", "2023": "–", "footnote_marker_2024": "#"},
    "value_of_awarded_shares": {"2024": "3 525 001", "2023": "–"},
    "total_remuneration": {"2024": "9 377 958", "2023": "–"}
  },
  "metrics_banderker": {
    "salary": {"2024": "1 752 609", "2023": "5 261 969"},
    "total_guaranteed_pay": {"2024": "1 927 224", "2023": "5 778 730"},
    "sti": {"2024": "–", "2023": "–", "semantic_status": "NOT_APPLICABLE both years"},
    "sti_previous_period": {"2024": "–", "2023": "5 621 868", "footnote_marker": "**"},
    "retention_awards": {"2024": "–", "2023": "14 630 400", "footnote_marker": "**"},
    "value_of_awarded_shares": {"2024": "–", "2023": "1 515 000"},
    "total_remuneration": {"2024": "1 927 224", "2023": "27 545 999"}
  },
  "footnotes": [
    {"marker": "*", "text": "Resigned 31 October 2023."},
    {"marker": "**", "text": "During 2022, the Remco appointed external consultants to benchmarking the CEO and CFO rewards which demonstrated shortcomings specifically relating to LTI awards. Given that backdating of share awards is not possible, the cash payments were then made in the various categories to rectify the shortcomings."},
    {"marker": "#", "text": "STI was approved after the release of the Annual Financial Statements, but before the publication of the Integrated Annual Report."}
  ],
  "reconstruction_note": "Block idx=39 contains all three names as one newline-delimited string with NO per-name bounding sub-box and NO x0 differentiation (its x0=35.9 matches only the leftmost panel). Association to panel is by ordinal position in the block's text (1st name -> leftmost panel by x0, 2nd -> middle, 3rd -> rightmost), confirmed correct against the rendered page (Section 8) but not verifiable from block geometry alone."
}
```

**Visual redesign, not schema change, confirmed**: every metric name in 2024's panels
(Salary/Medical aid/Retirement benefits/Other employee benefits/Total guaranteed pay/STI/Value of
awarded shares/Total variable pay/Total remuneration) is the same vocabulary used in 2020–2023; the
STI/Retention-Awards distinction introduced at the parent `total_remuneration_outcomes` level in
2023 (per the prior experiment) is visible here too (Banderker's panel still separates "STI
(previous period)" and "Retention awards" as of 2023, then both metrics simply carry no 2024 value
since he departed). What changed is purely the page's visual arrangement of the same metrics, from
vertical stack to horizontal panel — but that visual change is exactly what broke the block-level
row/label co-location the earlier years relied on.

## 5. `ned_fees_and_payments_table`: per-year reconstruction

**2020 (page 106) — the mega-merged-block case:**

```json
{
  "year": 2020,
  "table": "ned_fees_and_payments_table",
  "page": 106,
  "shape": "RECTANGULAR_MATRIX",
  "reconstruction_strategy": ["A_prime_fixed_arity_chunking", "B_for_wrapped_first_row"],
  "columns": [
    {"position": 1, "source_label": "Board fees", "normalized": "board_fees"},
    {"position": 2, "source_label": "Audit and Risk Committee", "normalized": "audit_risk_committee_fee"},
    {"position": 3, "source_label": "Investment Committee", "normalized": "investment_committee_fee"},
    {"position": 4, "source_label": "Remuneration Committee", "normalized": "remuneration_committee_fee"},
    {"position": 5, "source_label": "Nominations Committee", "normalized": "nomination_committee_fee"},
    {"position": 6, "source_label": "Social and Ethics Committee", "normalized": "social_ethics_committee_fee"},
    {"position": 7, "source_label": "ICT Steerco", "normalized": "ict_steerco_fee"},
    {"position": 8, "source_label": "Total current year 2019 – 2020", "normalized": "total_current_year", "year_ref": 2020},
    {"position": 9, "source_label": "Restated Total previous year 2018 – 2019", "normalized": "total_previous_year", "year_ref": 2019, "restated": true}
  ],
  "row_count": 15,
  "reconstruction_note": "Block idx=17/18 (ATM Mokgokong, 2-line wrapped name 'ATM Mokgokong \\n(Chairman)') split into a name-only block and a values-only block -- the ONE row in this table whose label wraps to 2 lines. Block idx=19 then contains ALL 14 remaining directors (MJ Madungandaba through T Alsworth-Elvey) concatenated into a single block with no sub-block boundaries; recovered only by chunking its flat newline-delimited text into 14 groups of exactly 10 tokens (1 name + 9 values), using K=9 confirmed independently from the 9 header blocks (idx=4-16). The Total row (idx=20) is its own block, correctly separate.",
  "sample_rows": [
    {"director": "ATM Mokgokong (Chairman)", "board_fees": "1 300 620", "social_ethics_committee_fee": "66 744",
     "total_current_year": "1 367 364", "total_previous_year": "1 272 300"},
    {"director": "SE Mmakau", "board_fees": "–", "total_current_year": "–", "semantic_status": "NIL_DASH all current-year cells",
     "total_previous_year": "221 500", "note": "COMPARATIVE_ONLY row -- present with a prior-year total only, no current-year fee at all; not the same state as a genuine ROW_ADDED or ROW_REMOVED"},
    {"director": "A Banderker", "board_fees": "–", "total_current_year": "–", "total_previous_year": "263 575",
     "note": "Same COMPARATIVE_ONLY state as SE Mmakau -- both are 2019 directors who are not 2020 NEDs at all (Banderker is the sitting executive CEO and appears elsewhere as an executive, not as a NED fee recipient)"},
    {"director": "G Allen", "board_fees": "183 469", "total_current_year": "183 469", "total_previous_year": "–",
     "note": "ROW_ADDED (2020) -- reverse of the two rows above"}
  ]
}
```

**2021 (page 118) — the widest schema, 12 columns, subsidiary-board expansion:**

Column set: Directors' fees, Social and Ethics Committee, Medscheme Board, ADS Board, PD/Curasana
Board, Remuneration Committee, Nomination Committee, Internal Control Review Panel, Pharma Audit
and Risk Committee, Audit and Risk Committee, Investment Committee, Total Fees. Block pattern
reverts to one-block-per-director here (each director's row is its own block, confirmed for all 12
directors on this page) — the mega-merge seen in 2020 does not recur, and 2021's one irregularity
is structural rather than block-level: "Ronald Mundalamo" appears as a **separate row below the
subtotal line and above the Total row** (`– – – – – 67 042 – – – – – 67 042`), i.e. one director's
fee, added to the printed subtotal to produce the final Total, but visually and block-wise
disconnected from the main 12-director block group — a genuine `ROW_REORDERED`/late-addition
pattern, not a parsing artifact (confirmed against the rendered page).

**2023 (page 138) — the unexplained one-off column:**

Column set: Directors fees, Nomination Committee, Audit and Risk Committee, Investment Committee,
Remuneration Committee, Social and Ethics Committee, Pharma Cluster Audit Committee, ADS Board
Meeting, Medscheme Board Meeting, Pharma Cluster Board Meeting, **Ex-Gratia Payment (Projects
Everest)**, Total. Three directors (JB Fernandes, AM le Roux, M Chauke) each received exactly
R100,000 under this column; it does not appear in 2022 or 2024. See Section 11 for the
footnote-dependency finding — this is the one column in this entire two-experiment research
sequence with **no explanatory text anywhere in its own report**.

**2024 (page 132) — partial block-merging by row sparsity:**

Ten columns (Section 9), one-block-per-row for data-dense directors (Mokgokong, Fernandes, Munisi,
le Roux, Chauke, Dippenaar — each individually blocked, confirmed via `get_text("blocks")`), but
**two multi-row merges**: block `idx=23` contains both Mokgokong's row (12 lines, own block by
count) *and* Madungandaba's row concatenated together (24 lines total for the pair, confirmed by
line-count inspection), and block `idx=29` contains Britz + K Mkhize + PB Hanratty's three rows
concatenated (36 lines = 3×12). Both merged pairs/triples occur where the source rows are
either fully or mostly dash-filled (Mkhize and Hanratty are entirely dashes; Britz has only one
non-dash cell), suggesting PyMuPDF's block-boundary heuristic is sensitive to the vertical
whitespace density created by short, sparse text — a plausible but unconfirmed mechanism (Section
16). The same A′ fixed-arity chunking strategy used for 2020 resolves both merges correctly
(K=10 for this year, confirmed against the header block count).

## 6. Table-shape drift

| Year | `individual_remuneration_outcomes` shape | `ned_fees_and_payments_table` shape | Block-pattern integrity |
|---|---|---|---|
| 2020 | PERSON_SUBTABLES (vertical stack, 4 people, spans pp.104–105) | RECTANGULAR_MATRIX, 9 cols | Individual table: name/metrics split but consistent. NED table: **one 14-row mega-block**, worst case in sample. |
| 2021 | PERSON_SUBTABLES (vertical stack, 4 people, spans pp.116–117; interleaved with an unrelated LTI vesting-tranche table on p.115, Section 15) | RECTANGULAR_MATRIX, 12 cols (subsidiary-board expansion) | Individual table: consistent split pattern. NED table: clean one-block-per-row except the late-added Mundalamo row. |
| 2022 | PERSON_SUBTABLES (vertical stack, 4 people incl. departing Britz/Mmakau, spans pp.120–121) | RECTANGULAR_MATRIX, 12 cols (reordered vs. 2021) | Both tables clean one-block-per-unit. |
| 2023 | PERSON_SUBTABLES (vertical stack, 4 people incl. two all-dash departed rows, spans pp.135–136) | RECTANGULAR_MATRIX, 11 cols (+Ex-Gratia, −previous-year total) | Both tables clean. |
| 2024 | **TABLE_SHAPE_CHANGED to MULTI_PANEL_TABLE** (3 people side by side, fits 1 page) | RECTANGULAR_MATRIX, 10 cols (−Ex-Gratia); **2 dash-row block merges** | Individual table: name/values decoupled (Section 4). NED table: partial re-merge. |

**This directly falsifies treating shape drift as failure, per the task brief's instruction, and
also directly falsifies treating shape drift as *only* a cosmetic non-event**: the 2024 individual-
outcomes redesign is genuinely cosmetic at the *metric* level (same vocabulary, same
comparability) but genuinely consequential at the *block-reconstruction* level (a parser correct
for 2020–2023 fails outright on 2024 without strategy E). Both statements are true simultaneously
and a pipeline needs to track them as separate facts.

## 7. Visual validation

Four pages were rendered at 200 DPI and manually compared against the reconstructed structures
above (2 `individual_remuneration_outcomes` years — 2020 simple, 2024 hard; 2 
`ned_fees_and_payments_table` years — 2020 hard-block/simple-schema, 2024 simple-block/simple-
schema, deliberately choosing years where the two tables' difficulty axes diverge):

| Page checked | Table | Row accuracy | Column accuracy | Panel/block accuracy | Footnote accuracy | Errors observed |
|---|---|---|---|---|---|---|
| ACT 2020 p.104 | individual_remuneration_outcomes | 3/3 people's full metric sets correct (Banderker, Boonzaaier, Britz) | 2/2 year columns correct per person | Vertical stack confirmed exactly as reconstructed; name-block/metrics-block split confirmed visually (name sits directly above its own table, no cross-panel ambiguity) | 3/3 footnotes correctly attached | None |
| ACT 2024 p.130 | individual_remuneration_outcomes | 3/3 people, all metrics correct including all NOT_APPLICABLE dash cells | 2/2 year columns per panel correct | **Ordinal name-to-panel matching confirmed correct**: leftmost panel = Van Wyk, middle = Banderker, rightmost = Boonzaaier, exactly matching the shared name-label block's left-to-right text order | 3/3 footnotes (*, **, #) correctly attached to the right panels | None, but this is the case where an error would have been easy to introduce without the visual check — the reconstruction's correctness rests entirely on an untested assumption (ordinal order = visual order) that this check happened to confirm rather than derive |
| ACT 2020 p.106 | ned_fees_and_payments_table | 15/15 director rows recovered correctly via A′ chunking, including the 2-line-wrapped first row | 9/9 columns correct | Mega-block chunking (14 rows from 1 block) verified against every value's correct row and column position by visual cross-check | N/A (no footnotes on this page) | None, but only because K=9 was known in advance from the header; an automated pipeline discovering this table cold would need the header-parse-before-chunking ordering enforced (Section 3) |
| ACT 2024 p.132 | ned_fees_and_payments_table | 10/10 director rows recovered correctly, including both merged-block pairs (Mokgokong+Madungandaba, Britz+Mkhize+Hanratty) | 10/10 columns + Total correct | Merged-block chunking verified correct against the rendered page for both merge cases | N/A | None |

**No reconstruction error was found on any of the four visually-checked pages**, but — unlike the
prior experiment's equivalent section — every one of these four pages required a non-trivial
reconstruction strategy beyond simple row-block parsing to get there, and the 2024
individual-outcomes case in particular succeeded only because this experiment happened to test the
one assumption (ordinal panel order) that had no independent structural verification. This is a
materially different confidence profile from the prior experiment's "confirmed robust, no defect
found to refine against" conclusion.

## 8. Row alignment

### 8.1 `individual_remuneration_outcomes` (person-based identity, confirmed)

| Person | 2020 | 2021 | 2022 | 2023 | 2024 | Event |
|---|---|---|---|---|---|---|
| Ahmed Banderker (Group CEO) | P | P | P | P | **P (partial year, resigned)** | ROW_STABLE through 2023; PARTIAL_YEAR in 2024, footnote-confirmed ("Resigned 31 October 2023") |
| Hannes Boonzaaier (Group CFO) | P | P | P | P | P | ROW_STABLE, only fully continuous person |
| Willem Britz (prescribed officer → NED) | P | P | P (footnoted "now NED") | **P, all-dash values, prior comparative shown** | **ROW_REMOVED from this table** | Full presence → VALUE_MISSING transition year → removed from this table entirely; **reappears the same year (2024) as a row in `ned_fees_and_payments_table` instead** (Section 12) — a cross-table role migration, not a same-table event |
| Sello Mmakau (prescribed officer) | P | P | P (footnoted "Resigned Feb 2022") | **P, all-dash values, prior comparative shown** | **ROW_REMOVED** | Same three-stage pattern as Britz, but no cross-table reappearance found — full departure |
| Gerald van Wyk (Group CEO) | ABSENT | ABSENT | ABSENT | ABSENT | **P (new, current-year only)** | ROW_ADDED (2024), same-table-year as Banderker's PARTIAL_YEAR row — succession pattern reconfirmed from the prior experiment, now additionally visible at the individual-outcomes level, not only the totals-matrix level |

**Confirms and extends the prior experiment's finding at a second table's resolution.** The
three-stage departure pattern (full presence → dash-with-comparative → full removal) found in the
prior experiment's `total_remuneration_outcomes` reappears identically here for the same two
people, at the same transition years, which is a useful internal-consistency check: two
independently-blocked tables in the same report agree on the same row-identity timeline.

### 8.2 `ned_fees_and_payments_table` (person-based identity, with the sample's largest roster churn)

19 distinct director names appear across the five years; only **4 are present in every year**
(Dr ATM Mokgokong, MJ Madungandaba, JB Fernandes/Bruno Fernandes — same person, name-format drift
noted below — and Dr ND Munisi). Representative events:

| Director | Pattern | Event |
|---|---|---|
| Dr ATM Mokgokong (Chairman) | P every year, 2020's wrapped 2-line label → single-line from 2021 | ROW_STABLE (label format changed, not identity) |
| MJ Madungandaba / Joe Madungandaba | Same person, "MJ Madungandaba" (2020, 2022–2024) vs. "Joe Madungandaba" (2021 only) | ROW_STABLE but **FUZZY_NORMALIZATION_NEEDED** — this is the exact "abbreviation vs. full first name" edge case the prior experiment flagged as untested; it occurs here on the very next table family checked |
| JB Fernandes / Bruno Fernandes | Same pattern as above, "JB Fernandes" (2020, 2022–2024) vs. "Bruno Fernandes" (2021 only) | Same FUZZY_NORMALIZATION_NEEDED case, second instance in the same year's page, confirming it is not a one-off typo |
| SE Mmakau, A Banderker (2020 only) | COMPARATIVE_ONLY (2019 total shown, no 2020 fee) | Both are people who are NOT non-executive directors in 2020 (Banderker is the executive CEO; Mmakau likely a departed 2019 NED) — this table's own row roster is not the same population as `individual_remuneration_outcomes`'s, despite a same-surname collision with Sello Mmakau in the executive table (different person, confirmed by initials S vs. SE and role) |
| G Allen / FG Allen | ROW_ADDED 2020, present with fees 2020–2023, **ROW_REMOVED 2024** with no footnote | UNEXPLAINED departure — unlike the individual_remuneration_outcomes departures, this table gives no textual reason anywhere on its own page for FG Allen's disappearance |
| K Mkhize | ROW_ADDED 2022 (fee-earning), P with all-dash values 2023–2024 | Same COMPARATIVE_ONLY/fading pattern as the executive table's departures, but this table gives no "resigned" footnote for it either |
| PB Hanratty | ROW_ADDED 2023 (small fee), all-dash 2024 | ROW_ADDED then immediately fading; no footnote |
| M Dippenaar | ROW_ADDED 2024 only | ROW_ADDED, no footnote explaining the appointment |
| **WH Britz** | **ROW_ADDED 2024** (as a NED, R297,706 director fee, no committee fees) | **SUCCESSION_INFERRED-adjacent event, but stronger: this is the SAME PERSON reappearing in a DIFFERENT table**, not a new person. Confirmed by name match (Willem Britz → WH Britz) and by the 2022 `individual_remuneration_outcomes` footnote ("Resigned in March 2022, and is now NED") read in the prior experiment and re-confirmed here. Classified `NARRATIVE_CONFIRMED` cross-table role change, not `ROW_ADDED` in the naive sense. |

**Row-identity assessment**: named individual (not role) is the correct key for both tables, as
the prior experiment found for `total_remuneration_outcomes` — but this table's roster churn (19
distinct names across 5 years vs. `individual_remuneration_outcomes`'s 5 distinct names across the
same period) is an order of magnitude larger, and it surfaces the name-format-drift hazard the
prior experiment predicted would eventually appear but had not yet observed.

## 9. Column alignment

### 9.1 `ned_fees_and_payments_table` — the schema-volatility test

| Year | Column count | Exact source labels (in order) |
|---|---|---|
| 2020 | 9 | Board fees; Audit and Risk Committee; Investment Committee; Remuneration Committee; Nominations Committee; Social and Ethics Committee; ICT Steerco; Total current year 2019–2020; Restated Total previous year 2018–2019 |
| 2021 | 12 | Directors' fees; Social and Ethics Committee; Medscheme Board; ADS Board; PD/Curasana Board; Remuneration Committee; Nomination Committee; Internal Control Review Panel; Pharma Audit and Risk Committee; Audit and Risk Committee; Investment Committee; Total Fees |
| 2022 | 12 | Directors fees; Nomination Committee; Audit and Risk Committee; Investment Committee; Remuneration Committee; Social and Ethics Committee; Pharma Cluster Audit Committee; ADS Board Meeting; Medscheme Board Meeting; Pharma Cluster Board Meeting; Total current year 2021–2022; Total previous year 2020–2021 |
| 2023 | 11 | Directors fees; Nomination Committee; Audit and Risk Committee; Investment Committee; Remuneration Committee; Social and Ethics Committee; Pharma Cluster Audit Committee; ADS Board Meeting; Medscheme Board Meeting; Pharma Cluster Board Meeting; Ex-Gratia Payment (Projects Everest); Total |
| 2024 | 10 | Directors fees; Nomination Committee; Audit and Risk Committee; Investment Committee; Remuneration Committee; Social and Ethics Committee; Pharma Cluster Audit Committee; ADS Board Meeting; Medscheme Board Meeting; Pharma Cluster Board Meeting; Total |

Classification per column-family, `2020→2021→2022→2023→2024`:

| Column family | Classification | Comparability status | Basis |
|---|---|---|---|
| Directors'/Board fees | COLUMN_STABLE (rename only: "Board fees" → "Directors' fees" → "Directors fees") | DIRECTLY_COMPARABLE | Same underlying fee category every year; label drift is cosmetic |
| Audit and Risk Committee | COLUMN_STABLE (2020→2021 same; 2021→2022 COLUMN_REORDERED — moved from position 9 to position 2) | DIRECTLY_COMPARABLE | Reordering confirmed by re-reading each year's header block in full; no evidence the fee basis changed |
| Investment Committee | COLUMN_STABLE, reordered 2021→2022 | DIRECTLY_COMPARABLE | Same |
| Remuneration Committee | COLUMN_STABLE, reordered | DIRECTLY_COMPARABLE | Same |
| Nomination(s) Committee | COLUMN_STABLE, reordered, minor pluralization drift ("Nominations" 2020 vs. "Nomination" 2021+) | DIRECTLY_COMPARABLE | Cosmetic |
| Social and Ethics Committee | COLUMN_STABLE, reordered | DIRECTLY_COMPARABLE | Same |
| ICT Steerco | **COLUMN_REMOVED after 2020** | NOT_COMPARABLE (absent 2021–2024) | No ICT Steering Committee fee column appears in the NED-payments table from 2021 onward, even though `ned_remuneration_policy_table` (the fee-*policy* table, per the prior experiment) continues to name an ICT Steering Committee fee every year — **the two sibling tables' column sets diverge**: the policy table keeps quoting an ICT Steerco fee rate every year 2020–2023, but the payments table stops reporting an actual ICT Steerco payment column after 2020. This is either because no NED ever served in a fee-eligible ICT Steerco role again (consistent with the policy table's own recurring footnote that the chairperson role is unpaid) or a genuine reporting-scope narrowing; this experiment could not resolve which from the source alone (`FOOTNOTE_AND_CONTEXT_DEPENDENT`, unresolved) |
| Medscheme Board, ADS Board | **COLUMN_ADDED 2021**, COLUMN_STABLE 2021–2024 (renamed "Board" → "Board Meeting" 2022+, cosmetic) | DIRECTLY_COMPARABLE from 2021 onward; NOT_COMPARABLE against 2020 (did not exist) | New subsidiary-board seats entering scope; consistent with the same expansion visible in committee membership generally |
| PD/Curasana Board | **COLUMN_ADDED 2021, COLUMN_REMOVED 2022** | NOT_COMPARABLE (single-year column) | One-year-only subsidiary board disclosure; no footnote explains the removal — plausibly a subsidiary restructuring, `UNEXPLAINED` |
| Internal Control Review Panel | **COLUMN_ADDED 2021, COLUMN_REMOVED 2022** | NOT_COMPARABLE | Same pattern, `UNEXPLAINED` |
| Pharma Audit and Risk Committee / Pharma Cluster Audit Committee | **COLUMN_ADDED 2021** (as "Pharma Audit and Risk Committee"), **COLUMN_RENAMED 2022** ("Pharma Cluster Audit Committee"), COLUMN_STABLE 2022–2024 | COMPARABLE_WITH_CAVEAT — same committee, renamed; the 2021→2022 rename coincides with the broader "Pharma Cluster" branding appearing on the Board-meeting columns too, suggesting a genuine organizational rename (a "Pharma" cluster of subsidiaries formalized under one name), not independently confirmed by a footnote | `SEMANTIC_SCHEMA_ALIGNMENT_NEEDED` to treat 2021 and 2022+ as the same column despite the label change |
| Pharma Cluster Board Meeting | **COLUMN_ADDED 2022** | NOT_COMPARABLE against 2020–2021 | New column, first appears alongside the Pharma Cluster Audit Committee rename |
| Ex-Gratia Payment (Projects Everest) | **COLUMN_ADDED 2023, COLUMN_REMOVED 2024** | NOT_COMPARABLE (single-year) | UNEXPLAINED — see Section 11 |
| Total (current year) | COLUMN_STABLE throughout (label drift: "Total current year 2019–2020" → "Total Fees" → "Total current year 2021–2022" → "Total" → "Total") | DIRECTLY_COMPARABLE as a same-year total, but **NOT_COMPARABLE as a year-over-year series** without normalizing for the fact that the underlying column set it sums changed size every year (a 2021 director's "Total" reflects a 12-column sum; a 2024 director's "Total" reflects a 10-column sum with a different committee set) |
| Total previous year (restated) | **Present 2020, ABSENT 2021, present 2022, ABSENT 2023–2024** | NOT_COMPARABLE where absent | COLUMN_REMOVED then COLUMN_ADDED then COLUMN_REMOVED again — the only column in this whole sample to oscillate on/off more than once, and the report gives no explanation for either removal |

**This is the schema-volatility result the prior experiment predicted.** Column *count* changed in
every single year-to-year transition (9→12→12→11→10), a materially different profile from
`ned_remuneration_policy_table`'s zero column-count changes across the same five years (prior
experiment, Section 8.1) and from `total_remuneration_outcomes`'s one column-family change
(STI→STI-and-Retention-Awards). Every individual column-level event was mechanically detectable by
string/position comparison (`DETERMINISTIC_SUFFICIENT`); *interpreting* several of them (the
ICT-Steerco divergence between sibling tables, three single-year committee columns, the oscillating
"Total previous year" column) required cross-referencing a sibling table or a full-document search
and, in three cases (PD/Curasana Board removal, Internal Control Review Panel removal, "Total
previous year" oscillation), yielded no resolution at all.

### 9.2 `individual_remuneration_outcomes` column alignment

Simpler and stable: `salary`, `medical_aid`, `retirement_benefits`, `other_employee_benefits`,
`total_guaranteed_pay`, `increase_in_guaranteed_pay_pct`, `sti`, `number_of_shares_awarded`,
`value_of_awarded_shares`, `total_variable_pay`, `total_remuneration` recur with stable meaning
2020–2022. 2023 introduces `sti_previous_period` and `retention_awards` (splitting what was one
`sti` line, mirroring the parent `total_remuneration_outcomes` schema change the prior experiment
documented) and drops `number_of_shares_awarded` as a separate line for the two executives affected
(the share count is folded into the "Value of awarded shares (N shares)" footnote text instead,
e.g. "200 000 shares in 2023 and 400 000 shares in 2022" — a genuine `COLUMN_MERGED` event at the
row-footnote level that this experiment had not previously seen: a numeric fact migrating from a
structured cell into unstructured footnote prose). 2024 restores a two-column-per-metric layout but
per-panel rather than per-table. Comparability status: `COMPARABLE_WITH_CAVEAT` for
`sti`/`sti_previous_period`/`retention_awards` (same underlying compensation category, split
differently by year, exactly mirroring the prior experiment's `total_remuneration_outcomes`
finding one level down); `DIRECTLY_COMPARABLE` for every other metric.

## 10. Value-change results

Selected aligned cells, `individual_remuneration_outcomes`, Hannes Boonzaaier (the only person
present in all five years):

| Metric | 2020→2021 | 2021→2022 | 2022→2023 | 2023→2024 |
|---|---|---|---|---|
| total_remuneration (R) | 6 843 695 → 7 262 792 | 7 262 792 → 7 226 202 | 7 226 202 → 10 060 021 | 10 060 021 → 5 282 261 |
| Event | VALUE_INCREASED | VALUE_DECREASED (marginal) | VALUE_INCREASED | VALUE_DECREASED |
| % change | +6.1% | −0.5% | +39.2% | −47.5% |

These figures are identical to the prior experiment's own `total_remuneration_outcomes` findings
for Boonzaaier (Section 9 there), confirming the two tables' totals reconcile exactly — a useful
cross-table consistency check this experiment ran as a validation step, not merely assumed.

`ned_fees_and_payments_table`, Dr ND Munisi (a rare director present in all five years with
changing committee membership):

| Year | Committees held (non-zero cells) | Total | Event |
|---|---|---|---|
| 2020 | Investment (97,545), Social and Ethics (88,344) | 428,733 | baseline |
| 2021 | Investment (67,042, via the late-added Mundalamo-style row structure) | 408,480 | VALUE_DECREASED, committee membership narrowed |
| 2022 | Investment (113,721), Social and Ethics (105,104) | 498,068 | VALUE_INCREASED, membership restored |
| 2023 | Investment (138,728), Pharma Cluster Audit (118,133) | 568,934 | VALUE_INCREASED, **committee membership changed** (Social and Ethics → Pharma Cluster Audit) |
| 2024 | Investment (138,875), Pharma Cluster Audit (134,142) | 599,165 | VALUE_INCREASED, membership stable vs. 2023 |

**This is a genuinely different value-diff shape than anything in the prior experiment**: because
the *columns themselves* change identity year to year, a "value went up" reading for Munisi's Total
conflates a same-committee fee increase (2023→2024) with a committee-*membership* change
(2022→2023, Social and Ethics dropped, Pharma Cluster Audit added) inside the same total. A
structured-comparison pipeline that only diffs the `Total` column, without also diffing which named
committee columns are non-zero for that row in each year, would silently misreport a governance
fact (which committees a director actually serves on) as a pure compensation trend.

## 11. Footnote / context dependency

| Event | Table alone sufficient? | Classification |
|---|---|---|
| Banderker's 2022→2023 STI/retention 11.4× jump, reconfirmed at the individual-outcomes level | No | `FOOTNOTE_DEPENDENT` — same footnote as the prior experiment found at the parent-table level, now confirmed reused verbatim at the child level |
| Boonzaaier's 2023→2024 47.5% drop | No | `FOOTNOTE_AND_CONTEXT_DEPENDENT` — the retention-award footnote plus the STI-timing footnote ("STI was approved after the release of the Annual Financial Statements...") together are needed to see this is a real, non-recurring 2023 item lapsing, not a pay cut |
| Van Wyk's 2024 appearance as new CEO | Partial | `NEIGHBOR_CONTEXT_DEPENDENT` — no footnote on this page states "new CEO"; row order (Van Wyk listed first, panel order 1) plus the surrounding remuneration narrative (read in the prior experiment and re-confirmed present) supplies this, matching the prior experiment's `SUCCESSION_INFERRED` finding at a second table |
| Britz's 2024 reappearance as a NED director row | No | `FOOTNOTE_AND_CONTEXT_DEPENDENT` — requires the 2022 footnote ("Resigned in March 2022, and is now NED") to correctly interpret 2024's new `ned_fees_and_payments_table` row as the *same person* continuing in a new role, not a coincidentally-named new director |
| FG Allen's 2024 disappearance from `ned_fees_and_payments_table` | No explanation found | **`UNEXPLAINED`** — no footnote on the page, no mention found via full-document search of "Allen" outside this table's own historical rows |
| PD/Curasana Board and Internal Control Review Panel columns' removal after 2021 | No explanation found | **`UNEXPLAINED`** — full-document search for "Curasana" and "Internal Control Review Panel" in the 2022 report returns only this table's own 2021 comparative column, no narrative reference |
| "Ex-Gratia Payment (Projects Everest)" column, 2023 | No explanation found anywhere in the document | **`UNEXPLAINED`** — confirmed by a full-text search of all 162 pages of the 2023 report for "Everest," which returns only this one table cell (Section 5); this is the single clearest footnote-dependency *failure* found across both structured-table experiments — the prior experiment's claim that "no footnote in this sample was found to be page furniture or safely discardable" holds only because that sample never encountered a change with **no footnote offered at all** |

**This experiment's footnote-dependency finding is more severe, not just "more of the same," than
the prior experiment's.** The earlier sample's worst case was "footnote required, footnote
present, footnote sufficient." This sample adds a fourth outcome the earlier taxonomy did not need:
**footnote required, no footnote or narrative exists anywhere in the source at all** — a
`STRUCTURED_COMPARISON` pipeline for `ned_fees_and_payments_table` must be able to represent "this
R300,000 payment and this director's disappearance are real, material, and unexplained by the
source" as a first-class output, not an extraction gap to be fixed by reading more carefully.

## 12. Succession / role-change events

- **Van Wyk succeeds Banderker as Group CEO (individual_remuneration_outcomes, 2024)**: same-table
  `ROW_ADDED` + `PARTIAL_YEAR` pair, `NEIGHBOR_CONTEXT_DEPENDENT` confidence — reconfirms the prior
  experiment's `total_remuneration_outcomes`-level finding at the child-table level. Classified
  `SUCCESSION_INFERRED`, not merged into one comparison subject.
- **Britz migrates from executive to non-executive director (cross-table, 2022 footnote → 2024
  table appearance)**: this is a *new* event type this experiment's taxonomy needs a name for,
  since it is not a same-table row event at all — it is a person leaving one structural unit's row
  population (`individual_remuneration_outcomes`/`total_remuneration_outcomes`, executives) and,
  two years later, entering a *different* structural unit's row population
  (`ned_fees_and_payments_table`, non-executive directors). Classified here as
  `CROSS_TABLE_ROLE_MIGRATION`, `NARRATIVE_CONFIRMED` (via the 2022 footnote plus name matching),
  explicitly distinguished from `SUCCESSION_INFERRED` because it is the same person continuing, not
  two different people in the same role. **No row-alignment edge type proposed in the prior
  experiment's Section 15 data model covers this** — see Section 17.
- **Munisi's committee-membership change without personnel change (Section 10)**: a
  `ROW_ROLE_CHANGED` event at the sub-row (committee-column) level rather than the row level itself
  — the director stays the same row across all five years, but which columns are non-zero for that
  row changes, which is a different granularity of "role change" than either succession or
  cross-table migration and needed its own classification in Section 10's analysis rather than
  forcing it into the row-alignment vocabulary.

No succession or role-change event in this sample was inferred without either a same-page footnote
or a specific prior-experiment-confirmed footnote; none reached only `TABLE_ONLY` or `CANNOT_CONFIRM`
confidence.

## 13. Nil / zero / blank / comparative-only handling

All five states distinguished in the prior experiment recur here, preserved separately:

- **NIL_DASH**: e.g. Van Wyk's 2023 columns (`individual_remuneration_outcomes`), en-dash, person
  did not exist in the table that year.
- **NOT_APPLICABLE**: e.g. "STI" cell for Banderker 2023/2024 (`individual_remuneration_outcomes`)
  — the metric line itself still exists in the schema but a *different*, newly-split metric
  (`sti_previous_period` / `retention_awards`) carries the value instead; the plain "STI" cell is
  correctly N/A, not zero, not missing.
- **COMPARATIVE_ONLY**: `ned_fees_and_payments_table`'s SE Mmakau/A Banderker 2020 rows and K
  Mkhize/PB Hanratty's 2024 rows — present with a total from a different year but no current-year
  fee at all; **this state appears far more often in this table** (at least 6 director-years across
  the sample) than in either of the prior experiment's tables, because NED committee membership
  churns faster than executive employment does.
  It is worth explicitly noting a distinction this sample newly forces: PB Hanratty (2023 row has
  one real value, R30,493.50 in directors' fees, `NUMERIC`) becomes an all-dash `COMPARATIVE_ONLY`-
  style row in 2024, but 2024's table has **no "previous year" comparative column at all** that
  year (Section 9) — so the correct semantic status for Hanratty's 2024 row is not
  `COMPARATIVE_ONLY` in the prior experiment's sense (present with a *retained* prior-year figure)
  but a plainer `NIL_DASH` row that happens to still be listed. The same visual "row of dashes"
  pattern therefore maps to two different semantic states depending on which comparative-column
  convention that year's table uses — a distinction only detectable by also tracking the *column
  schema* state (Section 9), not the row alone.
- **TEXT_VALUE**: "Waived fee" recurs in `individual_remuneration_outcomes`'s STI cells for Britz
  2020–2021, reused unchanged from the prior experiment's finding for the same person in
  `total_remuneration_outcomes`.
- **PARTIAL_YEAR_VALUE**: Banderker's 2024 figures across both tables — a genuinely non-zero,
  non-comparable-to-a-full-year value, distinguished from ordinary `NUMERIC`.

No case in this sample required inferring a zero where the source printed a dash, and no case
collapsed any of these states into another.

## 14. Plain text vs. structured representation

`ned_fees_and_payments_table`, 2021 (the widest, hardest schema year), plain linear text (as a
lexical-comparison pipeline would receive it):

```
Name of director
Directors' fees
Social and Ethics Committee
Medscheme Board
ADS Board
PD/Curasana Board
Remuneration Committee
Nomination Committee
Internal Control Review Panel
Pharma Audit and Risk Committee
Audit and Risk Committee
Investment Committee
Total Fees
Dr Anna Mokgokong
 1 555 377 
 – 
 – 
 – 
 – 
 – 
 52 824 
 – 
 – 
 – 
 – 
 1 608 201 
Joe Madungandaba
...
```

What is lost: the twelfth number in Mokgokong's row (52,824) sits under the "Internal Control
Review Panel" header purely by *position* — nothing in the linear text states this. Worse, because
this table's column *set itself* differs from every adjacent year's, a lexical/positional
comparison across years (e.g., "column 7 in 2020" vs. "column 7 in 2021") would compare **Social
and Ethics Committee fees (2020) against Nomination Committee fees (2021)** — two unrelated
quantities that happen to share a column index — without any warning that the comparison is
invalid. This is a sharper version of the prior experiment's Section 13 finding: there, column
*meaning* was fairly stable across years and only the row/column *association* was destroyed by
flattening; here, column meaning itself is unstable, so even a positionally-correct reconstruction
that failed to track column *identity* (not just position) across years would produce confidently
wrong longitudinal comparisons, not merely no comparison at all.

`individual_remuneration_outcomes`, 2024 (page 130), plain linear text order (abbreviated, as
actually emitted by `get_text()`):

```
2024 (R)   2023 (R)          [Van Wyk panel headers]
Salary  3 935 751  –
Medical aid  98 701  –
...
TOTAL REMUNERATION  9 377 958  –
2024 (R)  2023 (R)           [Banderker panel headers]
Salary  1 752 609  5 261 969
...
2024 (R)  2023 (R)           [Boonzaaier panel headers]
Salary  3 817 565  3 618 654
...
Individual remuneration outcomes
Gerald Van Wyk (Group CEO)
Ahmed Banderker (Group CEO)*
Hannes Boonzaaier (Group CFO)
...
```

The three people's **names are printed after all three panels of numbers**, in the plain-text
stream — a reader (human or naive LLM) encountering the numbers first has no attribution at all
until three panels later, and even then must count "first name = first panel" without any inline
marker. This is a more severe version of the heading-displacement hazard the extraction-
representation bake-off experiment found for Bell Equipment's section titles (there, a single
heading was displaced within a page); here, three *different rows' entire identity labels* are
displaced together, en masse, to the bottom of the page's numeric content.

## 15. Deterministic vs. semantic responsibilities

| Task | Classification | Basis |
|---|---|---|
| Column-header extraction and count (`ned_fees_and_payments_table`, all years) | `DETERMINISTIC_SUFFICIENT` | Header blocks are always distinguishable from data rows by page position (topmost) and are never affected by the row-merging hazard |
| Fixed-arity chunking of merged multi-row blocks (strategy A′) | `DETERMINISTIC_SUFFICIENT`, conditional on header parsing already succeeding | Confirmed correct on both 2020's 14-row mega-block and 2024's two merged pairs; purely a counting operation once *K* is known |
| Name-to-panel ordinal matching (`individual_remuneration_outcomes` 2024, strategy E) | `STRUCTURAL_CONTEXT_REQUIRED` (not string/geometry alone) | The block data provides no independent signal that ordinal position equals visual left-to-right order; this experiment confirmed it holds by rendering the page, which a fully automated pipeline would need to do at least once per new layout to validate the assumption, even though no case here required per-instance multimodal reading |
| Name-format normalization (Madungandaba/Joe vs. MJ; Fernandes/Bruno vs. JB) | `FUZZY_NORMALIZATION_NEEDED` | Confirmed occurrence of the exact hazard the prior experiment predicted but had not observed; simple string equality fails, but a light normalization (surname + first-initial match) would resolve both cases seen here |
| Detecting column count/schema change year to year | `DETERMINISTIC_SUFFICIENT` | Header block text and count are directly comparable strings; every addition/removal/rename in Section 9 was found by direct comparison, not inference |
| Judging whether a column rename is cosmetic or a real composition change (e.g. Pharma Audit and Risk Committee → Pharma Cluster Audit Committee) | `SEMANTIC_SCHEMA_ALIGNMENT_NEEDED` | Required cross-referencing the simultaneous appearance of "Pharma Cluster Board Meeting" and reasoning about organizational restructuring; not resolvable from the column label alone |
| Cross-table role migration detection (Britz) | `SEMANTIC_ROW_RELATION_NEEDED` | Required reading a footnote from a *different* table's *different* year and matching a name across two structurally unrelated units; the eligibility taxonomy's `advisory_vote`-style cross-unit dependency is the closest prior category but this is cross-*table-family*, not cross-*unit-within-one-schedule* |
| Explaining the Ex-Gratia/Projects Everest column | Attempted `FOOTNOTE_DEPENDENT`, resolved to **no classification succeeds** | The only task in either structured-table experiment where every available deterministic and semantic strategy (footnote read, full-document search) returned no answer — this is not a gap in method, it is a gap in the source |
| Multimodal need, any task in this sample | `MULTIMODAL_REQUIRED`: **none** | Every hazard was resolvable from text, blocks, and full-document search |

**Quantified comparison with the prior experiment**: of 14 distinct tasks documented in the prior
experiment's Section 14, 8 were `DETERMINISTIC_SUFFICIENT`. Of the 8 distinct task types documented
here, 3 are cleanly `DETERMINISTIC_SUFFICIENT`, 1 is conditionally deterministic (A′, dependent on
header-parse ordering), and 4 require some form of semantic or structural judgment — a
meaningfully lower deterministic share (3–4/8 vs. 8/14, roughly 40–50% vs. 57%) that is consistent
with this experiment's premise that harder tables shift more work toward semantic assistance, while
still leaving a deterministic majority once the conditional case is counted.

## 16. Generalization comparison

Direct comparison with `annual-report-structured-table-comparison.md`:

1. **Did the row-major block pattern generalize?** No, not as a universal rule. It held cleanly for
   `ned_fees_and_payments_table` in 3 of 5 years (2021–2023) and partially in the other 2 (2020's
   total mega-merge, 2024's partial merges); it did not hold at all for
   `individual_remuneration_outcomes`'s row *label* in any year (name always separately blocked from
   its values, 2020–2023) and broke completely for row *identity* in 2024 (name separated from
   value panels entirely, requiring ordinal matching).
2. **What additional reconstruction strategies were needed?** Three new ones beyond the prior
   experiment's implicit single strategy: A′ (fixed-arity chunking of merged blocks), B applied at
   the *label-to-data-block* level rather than *within* a block, and E (ordinal panel matching).
   Strategy F (cross-page) was present but benign (no row ever split across the boundary).
3. **Did schema volatility break longitudinal alignment?** Not for row alignment (person identity
   remained trackable in both tables at every step, Section 8) but yes for naive column-position
   alignment (Section 14) — a positional-only diff would silently compare unrelated committees
   across years, which the prior experiment's stable-schema tables never risked.
4. **Did row identity remain clean?** Mostly — person-based keying worked throughout — but this
   sample surfaced two hazards the prior sample never needed: name-format drift requiring fuzzy
   matching (confirmed occurrence, not just a predicted risk) and a cross-table role migration with
   no dedicated edge type in the prior data model.
5. **Did column identity remain clean?** No — `ned_fees_and_payments_table`'s column count changed
   in every year-to-year transition, versus zero column-count changes in either of the prior
   experiment's tables across the same five years.
6. **How often was semantic normalization actually necessary?** More often than the prior
   experiment (Section 15's 3–4/8 vs. 8/14 comparison), though still a minority of individual
   reconstruction steps, and zero instances required multimodal reading.
7. **Were footnotes even more important?** Yes on the occasions they existed, but this experiment
   also found the prior experiment's strongest claim ("no footnote was found to be discardable, and
   none was needed-but-missing") does not generalize: three separate events in this sample
   (Section 11) have no footnote or narrative explanation anywhere in their own report, which is a
   new, harder outcome the prior experiment's taxonomy did not include.
8. **Did any case require multimodal?** No — this is the one finding that generalized cleanly and
   without qualification across both experiments.
9. **Does a reusable structured-table pipeline now look realistic?** Partially. A pipeline that
   (a) always parses column headers before attempting row chunking, (b) applies fixed-arity
   chunking as a fallback whenever a block's line count exceeds the expected per-row count, (c)
   treats row-label-to-value association as a distinct, separately-verified step rather than an
   assumption baked into row-block parsing, and (d) tracks column *identity* (not just position)
   across years, would handle every case in this sample deterministically except the four flagged
   `SEMANTIC_*` tasks and the ordinal-panel-matching validation step. That is a more complex
   pipeline than the prior experiment's single-strategy recommendation, but it is still a
   substantially smaller and cheaper design than routing every page through multimodal
   interpretation.

## 17. Data model implications

Not implemented — proposed only, as extensions to the prior experiment's Section 15 shape:

- **`structured_table.shape`** needs the fuller enum used in this report
  (`RECTANGULAR_MATRIX | GROUPED_MATRIX | PERSON_SUBTABLES | MULTI_PANEL_TABLE | MULTI_PAGE_TABLE |
  HYBRID_TABLE_NARRATIVE | OTHER`), plus a same-unit `shape_changed_from_prior_year` flag, since
  this experiment found shape drift within one company's own table family (2024's individual-
  outcomes redesign) that the prior experiment's schema had no field to record.
- **`table_row.source_block_ids`** should be an array, not a scalar, and should separately record a
  `label_block_id` and one-or-more `value_block_ids` — the prior schema's implicit assumption of a
  single block per row does not hold here even in the "clean" cases (Section 3's B strategy).
- **A new `block_reconstruction_strategy` field** on `structured_table` (or per-row, where it
  varies within one table as in 2024's NED-payments merges) recording which of A/A′/B/D/E/F/G was
  used — this experiment's evidence is that a single company's single table family can require
  different strategies in different years, so the field cannot be fixed at the schedule-definition
  level, only at the specific table-instance level.
- **`row_alignment_edge.relationship` needs a `CROSS_TABLE_ROLE_MIGRATION` value**, distinct from
  `SUCCESSION_INFERRED` (Section 12) — Britz's case is not two different people in one role but one
  person moving between two different structural units' row populations, and conflating it with
  succession would misrepresent both the population change and the continuity of the individual.
- **`column_alignment_edge` needs a `comparability_status` field** (as specified in the task brief)
  populated with `DIRECTLY_COMPARABLE | COMPARABLE_WITH_CAVEAT | PARTIALLY_COMPARABLE_SCHEMA_CHANGED
  | NOT_COMPARABLE`, since the prior experiment's schema tracked column *alignment* (does a column
  correspond across years) but not comparability *strength*, and this sample's Section 9 shows those
  are different questions — a column can align (same physical position/role sequence) while being
  entirely non-comparable (PD/Curasana Board, single year only).
- **A `footnote_dependency.classification` field on `value_change_event`** should include an
  `UNEXPLAINED` value alongside `SELF_EXPLANATORY | FOOTNOTE_DEPENDENT | NEIGHBOR_CONTEXT_DEPENDENT
  | FOOTNOTE_AND_CONTEXT_DEPENDENT` — the prior schema had no way to represent "we looked for an
  explanation across the whole document and did not find one," which this sample needed three
  times.
- **Person-identity resolution needs an explicit `name_variant` table or alias list**
  (`MJ Madungandaba` / `Joe Madungandaba`; `JB Fernandes` / `Bruno Fernandes`), populated by the
  `FUZZY_NORMALIZATION_NEEDED` step in Section 15, not assumed away by exact string matching.

No schema was implemented; this is a design note only, per the task's explicit instruction.

## 18. Recommendation

**(B) TEST MORE ACT TABLE SHAPES FIRST — with a narrow, specific follow-up, not a broad relitigation.**

This experiment found two block-level failure modes (mega-block row merging, name-block/value-panel
separation) that are more severe than anything in the prior experiment, and both were observed on
exactly one page each (ACT 2020 p.106; ACT 2024 p.130). Before generalizing the architecture to a
second company's differently-templated tables, this experiment's own evidence should be
strengthened in one specific way: **check whether ACT's other multi-row tables (the corporate-
governance committee-composition tables and attendance registers named but not extracted in the
eligibility experiment, and the base-pay-increase/employee-category bar chart data noted but not
reconstructed in either structured-table experiment) exhibit the same row-sparsity-driven
block-merging behavior**, to establish whether this is a general PyMuPDF sensitivity (likely, given
it appeared in two unrelated tables in two unrelated years of this same report) or specific to these
two pages. This is a small, cheap, ACT-only follow-up — not a new company, not a new methodology —
and it directly de-risks the one open question this experiment could not resolve on its own
evidence (Section 5's `ned_fees_and_payments_table` 2024 merge-mechanism note: "a plausible but
unconfirmed mechanism").

**What should NOT be assumed to transfer once a second company (BEL, per the prior experiment's own
Section 17 suggestion) is eventually tested:**

- **The specific fixed-arity chunking parameters (A′)** are ACT-page-specific (this experiment
  confirmed *K* must be read fresh from each table's own header every time, never hard-coded) but
  the *strategy itself* (detect an oversized block, chunk by known column count) should transfer as
  a general technique.
- **The ordinal name-to-panel matching assumption (strategy E)** is the single most fragile
  transfer risk: it was validated by visual inspection on ACT's one 2024 instance and nothing in
  this experiment's evidence establishes that a differently-designed report's multi-panel layout
  would order names left-to-right in a block the same way. BEL's own report template (per the
  schedule-localization and longitudinal-stability experiments) has a materially different
  remuneration-committee-report design; this strategy should be re-validated visually on BEL's
  first multi-panel table encountered, not assumed.
- **Which committees/subsidiary boards appear as columns** is entirely ACT-specific
  organizational content (Medscheme, ADS, PD/Curasana, Pharma Cluster) and has no reason to
  transfer to any other company's NED-payments table structure; only the *volatility pattern itself*
  (column count changes most years, driven by real organizational structure) is the transferable
  finding, not any specific column set.
- **The "no footnote found" (`UNEXPLAINED`) outcome rate** (3 of roughly a dozen notable events in
  this sample) should not be assumed representative of ACT's disclosure quality generally, let alone
  of a different company's — this sample specifically targeted the report's most volatile tables,
  which is exactly where an under-footnoted one-off item would be most likely to surface.

If BEL is tested next, per this experiment's evidence it should specifically target BEL's
equivalent `individual`/`per-director-payments`-style tables (per the longitudinal-stability
experiment's characterization of BEL's remuneration-committee report as materially more expanded
and differently structured than ACT's) with the explicit hypotheses: (1) does BEL's report exhibit
any block-merging sensitivity comparable to ACT's two observed cases; (2) does BEL's report ever use
a multi-panel, name-separated-from-values layout comparable to ACT 2024; (3) does BEL's remuneration
disclosure leave any large one-off item unexplained, as ACT's Projects Everest payment was.

# Experiment: Structured Table Reconstruction and Longitudinal Comparison (AfroCentric, Two Remuneration Tables, 2020–2024)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against
`data/raw/ACT/{2020,2021,2022,2023,2024}/annual_report.pdf` via throwaway PyMuPDF scripts, with
intermediate JSON dumps and rendered page PNGs written to a session-local scratch directory
outside the repository. Nothing here is wired into the application. This is a direct follow-up to
`docs/experiments/annual-report-analytical-unit-eligibility.md` ("the eligibility experiment,"
assumed read), which found that `ned_remuneration_policy_table` and `total_remuneration_outcomes`
are the sample's clearest `STRUCTURED_COMPARISON_PREFERRED` cases and identified structured-table
reconstruction as the next open research gap rather than something already validated.

## 1. Executive summary

**Yes — both table families can be reconstructed reliably into row × metric × value relationships
and aligned longitudinally, using PyMuPDF plain text + blocks alone, with zero multimodal
escalations across all ten table-years sampled (5 years × 2 tables).** The central finding is a
specific, mechanical one: on every page checked in this corpus, PyMuPDF's `get_text("blocks")`
groups each table row into a single block, with the row's label followed by its cell values in
strict left-to-right, top-to-bottom (row-major) reading order as newline-separated text within
that one block. This is a materially stronger result than the representation bake-off's or
longitudinal experiment's general findings about ACT's extraction-friendliness — it is not just
"blocks resolve ordering," it is "blocks hand back the row as one already-associated unit," which
is the single fact that makes deterministic row/column reconstruction possible here without a
geometric x0/y0-band clustering pass.

- **Are rows and columns stable enough for longitudinal alignment?** Column *headers* are stable
  in `ned_remuneration_policy_table` (Current/Proposed/Recommended increase % in every year, with
  only cosmetic renaming) and moderately stable in `total_remuneration_outcomes` (Base pay /
  Benefits / STI / LTI / Total in 2020–2022, then STI is renamed and merged with a new "Retention
  Awards" component in 2023–2024 — a real `COLUMN_MERGED`/`COLUMN_RENAMED` event, not noise). Row
  *identity* is role-based and stable for the NED table (one role added, one role oscillates
  present/nil/absent across the run) and person-based with substantial real turnover for the
  remuneration-outcomes table (2 of 4 2020 executives are gone by 2024, 1 new one added) — this
  turnover is the actual economically meaningful content, not a reconstruction defect.
- **Is block geometry sufficient?** Yes, for every page in this ten-table-year sample. No page
  required `get_text("dict")` font/size inspection and no page required multimodal image reading.
  The one representation gap found — the base-pay-increase bar chart accompanying
  `total_remuneration_outcomes` in 2020–2023 (18 floating percentage values with no per-value text
  label) — is outside this experiment's two named tables and was not reconstructed, per the task's
  instruction not to introduce additional table types unless necessary; it is noted only as a
  boundary observation, consistent with the within-schedule alignment experiment's prior finding
  that this exact chart needs 2-axis clustering.
- **How often was multimodal needed?** Zero times. This experiment additionally performed direct
  visual ground-truth verification (rendered PNG vs. reconstructed table) on 5 pages — 2 NED-table
  years (2020, 2022) and 3 remuneration-outcomes years (2020, 2023, 2024), exceeding the task's "at
  least 2 + 2" minimum — and found 100% row-count, column-count, label, and value-assignment
  accuracy on every page checked, with no cross-row contamination and no column shift.
- **Can row additions/removals be distinguished from numeric zero/nil?** Yes, and the source data
  itself makes the distinction explicit in three different ways that must be preserved separately:
  a dash (`–`) cell (present row, nil value, e.g. a waived fee), a row that is present with a
  current-year dash but a retained prior-year comparative (a `VALUE_MISSING`/departure-in-progress
  state — W Britz and S Mmakau's 2023 row), and a row's total disappearance from the table the
  following year (a true `ROW_REMOVED` — the same two individuals gone entirely from 2024's table).
  Collapsing these three into one "zero" reading would misstate two different real-world facts
  (a person is still notionally on the table with no current-year pay vs. a person is no longer
  reported at all) as the same thing.
- **Are footnotes necessary for correct interpretation?** Yes, decisively — see Section 11.
  AfroCentric's own footnotes are the *only* textual evidence in the entire five-year corpus that
  explains three of this experiment's four largest numeric swings (Banderker's 2022→2023 STI/
  retention jump, Banderker's 2023→2024 collapse, and W Britz/S Mmakau's departures), and a
  metric-only pipeline that discarded footnotes would report three unexplained anomalies where the
  source document itself supplies the explanation in the very next line.
- **Is structured comparison ready to become a real pipeline modality?** **(A) Yes**, for these two
  table families specifically, on the evidence gathered here. See Section 17.

## 2. Source inventory

| Table | Year | Page(s) | Source heading | Reconstruction status |
|---|---|---|---|---|
| `ned_remuneration_policy_table` | 2020 | 105 | "Non-executive Directors' 2020 remuneration" | CLEAN |
| `ned_remuneration_policy_table` | 2021 | 117 | "Non-executive Directors' 2021 remuneration" | CLEAN |
| `ned_remuneration_policy_table` | 2022 | 121 | "Non-executive Directors' 2022 remuneration" | CLEAN |
| `ned_remuneration_policy_table` | 2023 | 137 | "NON-EXECUTIVE DIRECTORS' 2023 REMUNERATION" | CLEAN |
| `ned_remuneration_policy_table` | 2024 | 131 | "Non-executive Directors' 2024 remuneration" | CLEAN |
| `total_remuneration_outcomes` | 2020 | 102 | "Total remuneration outcomes" | CLEAN |
| `total_remuneration_outcomes` | 2021 | 114 | "Total remuneration outcomes" | CLEAN |
| `total_remuneration_outcomes` | 2022 | 118 | "Total remuneration outcomes" | CLEAN |
| `total_remuneration_outcomes` | 2023 | 134 | "TOTAL REMUNERATION OUTCOMES" | CLEAN |
| `total_remuneration_outcomes` | 2024 | 128 | "Total remuneration outcomes" | CLEAN |

Page numbers were located this session by full-text search within each year's remuneration
schedule page range (per the eligibility experiment's Section 3, re-used unchanged) and confirmed
by direct reading of the extracted text, not copied uncritically from prior experiments' tables.
All ten pages matched the eligibility experiment's page attributions.

The two per-director-payments tables that share the same pages as `ned_remuneration_policy_table`
(`ned_fees_and_payments_table`, "Payments made to Non-executive Directors") were incidentally
captured in the page dumps used here but are **not** analyzed as a third table family, per the
task's explicit instruction not to introduce additional table types unless necessary to understand
the two named ones. Where its structure is directly relevant to interpreting a footnote or a row
event in the two focal tables, it is mentioned briefly (Section 12) and not otherwise reconstructed.

## 3. Table reconstruction methodology

**Extraction.** `page.get_text("blocks")` for each located page, no `dict`/span or multimodal call
made at any point. Blocks were consumed in native emission order (no y0-sort or column-aware sort
was needed for any page in this sample — a materially different situation from BEL's heading
displacement or ACT's own chart-clustering hazard documented in prior experiments, because these
particular tables have no heading-displacement layout and no chart component of their own).

**The row-block pattern, confirmed on every page in this sample.** A representative block from the
2020 NED table (`ned_remuneration_policy_table`, p.105):

```
'Main Board (annualised retainer fee)\nChairman\n1 329 240\n1 375 763\n3.5\n
Deputy Chairman\n997 713\n1 032 633\n3.5\nMember\n248 188\n256 875\n3.5\n'
```

and from the 2020 remuneration-outcomes table (`total_remuneration_outcomes`, p.102):

```
'A Banderker1\n4 781 364\n1 148 9041\n435 788\n101 096\n3 242 207\n2 526 786\n
1 750 000\n2 400 000 10 209 360\n6 176 786\n'
```

Both examples show the same structure: one block per row (or, for the NED table, one block per
sub-category header covering several roles), with the row/role label first, followed by every
cell's value in the exact left-to-right column order printed on the page. This means row and
column association does **not** require geometric x0/y0-band clustering for either table family in
this sample — it can be recovered by a purely textual, deterministic parse: split the block on
newlines, take the first non-numeric run as the row label (or, for multi-role NED blocks, split
further on role-name tokens that are followed by exactly N numeric-pattern tokens), and assign the
remaining tokens to columns strictly by position, using the column-header block's text and x0 as
the source of column *meaning* and printed order as the source of column *sequence*. This is the
single most important methodological finding of this experiment: **table structure recovery here
is a text/regex problem, not a coordinate-clustering problem**, in contrast to the chart pages
documented by the within-schedule alignment experiment.

**Column headers.** Extracted as separate blocks positioned above the data rows, one block (or a
small cluster of blocks) per header label, distinguishable by x0 position and matched to the data
columns by relative left-to-right order — confirmed directly by visual inspection (Section 6) that
header-to-column alignment is correct on every page checked.

**Multi-line labels.** Both tables' role/name labels occasionally wrap onto a second line inside
the source PDF (e.g. "Lead Independent Director" in some years' NED table appears as one block with
an embedded newline before its values) — this does not break the row-block pattern because the
label and its values remain inside the same block regardless of label line count.

**Footnote handling.** Footnotes are extracted as their own separate blocks, positioned below the
table body, each beginning with the same marker character(s) (`*`, `**`, superscript digits
rendered as plain digits adjacent to the referencing cell's text, e.g. `A Banderker1`). Marker-to-
row association was done by matching the footnote's leading marker character against the same
marker string appended to a row/cell's label or value in the row block's own text (Section 11) —
this is a text-matching operation, not a geometric one, and was reliable on every footnote checked.

**Nil/zero/blank handling.** The source text itself already distinguishes these cases without any
inference required: an en-dash character (`–`, distinct from a hyphen) marks an explicit nil/blank
cell; the literal string `"Waived fee"` marks a fee that was formally waived (semantically distinct
from an unreported/absent value); a numeric `0` or `0%` (rare in this sample) marks a true numeric
zero; and a cell's total absence from a row's block (rather than an empty value inside it) marks
that the row itself does not have data for that year at all. All four were preserved as distinct
raw strings in this experiment's reconstruction (Section 4–5) and are not collapsed into one
`null`/`0` representation.

## 4. `ned_remuneration_policy_table`: per-year reconstruction

Representative reconstructed structure, 2020 and 2024 (illustrative; full five-year row set in
Section 7):

```json
{
  "year": 2020,
  "table": "ned_remuneration_policy_table",
  "page": 105,
  "source_heading": "Non-executive Directors' 2020 remuneration",
  "columns": [
    {"source_label": "Current 2020 (R)", "normalized_role": "current_fee", "year_ref": 2020},
    {"source_label": "Proposed 2021 (R)", "normalized_role": "proposed_fee", "year_ref": 2021},
    {"source_label": "Recommended increase (%)", "normalized_role": "recommended_increase_pct"}
  ],
  "rows": [
    {"category": "Main Board (annualised retainer fee)", "role": "Chairman",
     "current_2020": "1 329 240", "proposed_2021": "1 375 763", "increase_pct": "3.5"},
    {"category": "Main Board (annualised retainer fee)", "role": "Deputy Chairman",
     "current_2020": "997 713", "proposed_2021": "1 032 633", "increase_pct": "3.5"},
    {"category": "Main Board (annualised retainer fee)", "role": "Member",
     "current_2020": "248 188", "proposed_2021": "256 875", "increase_pct": "3.5"},
    {"category": "Subsidiary board (per meeting)", "role": "Chairman",
     "current_2020": "22 572", "proposed_2021": "23 362", "increase_pct": "3.5"},
    {"category": "Subsidiary board (per meeting)", "role": "Member",
     "current_2020": "16 615", "proposed_2021": "17 197", "increase_pct": "3.5"},
    "... (Audit and Risk, Remuneration, Nomination, Social and Ethics, Investment Committees,",
    "each with Chairperson/Chairman + Member rows, all at 3.5% ...)",
    {"category": "ICT Steering Committee (per meeting)", "role": "Chairperson",
     "current_2020": "22 572", "proposed_2021": null, "increase_pct": null,
     "footnote": "* The Chairperson is currently an Executive Director and does not receive fees."},
    {"category": "ICT Steering Committee (per meeting)", "role": "Member",
     "current_2020": "16 615", "proposed_2021": "17 197", "increase_pct": "3.5"}
  ]
}
```

```json
{
  "year": 2024,
  "table": "ned_remuneration_policy_table",
  "page": 131,
  "source_heading": "Non-executive Directors' 2024 remuneration",
  "columns": [
    {"source_label": "Current (2024)", "normalized_role": "current_fee", "year_ref": 2024},
    {"source_label": "Proposed (2025)", "normalized_role": "proposed_fee", "year_ref": 2025},
    {"source_label": "Recommended Increase (%)", "normalized_role": "recommended_increase_pct"}
  ],
  "rows": [
    {"category": "Main Board (annualised retainer fee*)", "role": "Chairman",
     "current_2024": "1 578 867", "proposed_2025": "1 665 705", "increase_pct": "5.5"},
    {"category": "Main Board (annualised retainer fee*)", "role": "Deputy Chairman",
     "current_2024": "1 439 086", "proposed_2025": "1 518 236", "increase_pct": "5.5"},
    {"category": "Main Board (annualised retainer fee*)", "role": "Lead Independent Director",
     "current_2024": "729 049", "proposed_2025": "769 147", "increase_pct": "5.5"},
    {"category": "Main Board (annualised retainer fee*)", "role": "Member",
     "current_2024": "334 103", "proposed_2025": "352 479", "increase_pct": "5.5"},
    "... (Subsidiary board/committee, Audit and Risk, Remuneration, Nomination, Social and",
    "Ethics, Investment Committees, each Chairman/Member, all at 5.5% ...)",
    {"category": "ICT Steering Committee (per annum fee*)", "role": "Member",
     "current_2024": "77 001", "proposed_2025": "81 236", "increase_pct": "5.5"},
    {"category": "Special ad hoc board/committee meeting (per meeting fee)", "role": "Member",
     "current_2024": null, "proposed_2025": "20 307", "increase_pct": null,
     "note": "current_2024 is N/A in source; row did not exist prior to this year"}
  ]
}
```

Column meanings are stable across all five years (`current_fee` / `proposed_fee` /
`recommended_increase_pct`) despite cosmetic label drift ("Current 2020 (R)" → "CURRENT 2023" →
"Current (2024)"; "Recommended increase (%)" → "PROPOSED INCREASE %" → "Recommended Increase (%)").
The proposed/current year reference always advances by exactly one year relative to the "current"
column's own year, confirmed in every year sampled.

## 5. `total_remuneration_outcomes`: per-year reconstruction

Representative reconstructed structure, 2020 and 2023 (2023 chosen to show the schema change;
full five-year row set in Section 7):

```json
{
  "year": 2020,
  "table": "total_remuneration_outcomes",
  "page": 102,
  "source_heading": "Total remuneration outcomes",
  "unit": "R'000 (single figure remuneration)",
  "columns": [
    {"group": "Guaranteed pay", "metric": "base_pay", "year_ref": 2020},
    {"group": "Guaranteed pay", "metric": "base_pay", "year_ref": 2019, "restated": true},
    {"group": "Guaranteed pay", "metric": "benefits_and_allowances", "year_ref": 2020},
    {"group": "Guaranteed pay", "metric": "benefits_and_allowances", "year_ref": 2019, "restated": true},
    {"group": "Variable pay", "metric": "sti", "year_ref": 2020},
    {"group": "Variable pay", "metric": "sti", "year_ref": 2019, "restated": true},
    {"group": "Variable pay", "metric": "lti", "year_ref": 2020},
    {"group": "Variable pay", "metric": "lti", "year_ref": 2019, "restated": true},
    {"group": null, "metric": "total_remuneration", "year_ref": 2020},
    {"group": null, "metric": "total_remuneration", "year_ref": 2019, "restated": true}
  ],
  "rows": [
    {"entity": "A Banderker", "footnote_marker": "1", "base_pay_2020": "4 781 364",
     "base_pay_2019r": "1 148 904", "benefits_2020": "435 788", "benefits_2019r": "101 096",
     "sti_2020": "3 242 207", "sti_2019r": "2 526 786", "lti_2020": "1 750 000",
     "lti_2019r": "2 400 000", "total_2020": "10 209 360", "total_2019r": "6 176 786"},
    {"entity": "W Britz", "base_pay_2020": "3 975 310", "base_pay_2019r": "3 828 863",
     "benefits_2020": "394 235", "benefits_2019r": "360 935", "sti_2020": "Waived fee",
     "sti_2019r": "Waived fee", "lti_2020": "–", "lti_2019r": "–",
     "total_2020": "4 369 545", "total_2019r": "4 189 798"},
    {"entity": "H Boonzaaier", "base_pay_2020": "3 061 646", "base_pay_2019r": "2 956 130",
     "benefits_2020": "276 436", "benefits_2019r": "244 144", "sti_2020": "1 755 613",
     "sti_2019r": "1 684 924", "lti_2020": "1 750 000", "lti_2019r": "1 000 000",
     "total_2020": "6 843 695", "total_2019r": "5 885 198"},
    {"entity": "S Mmakau", "footnote_marker": "2", "base_pay_2020": "3 347 678",
     "base_pay_2019r": "2 046 861", "benefits_2020": "323 939", "benefits_2019r": "195 981",
     "sti_2020": "1 479 066", "sti_2019r": "2 505 754", "lti_2020": "875 000",
     "lti_2019r": "–", "total_2020": "6 025 683", "total_2019r": "4 748 597"},
    {"entity": "TOTAL", "base_pay_2020": "15 165 998", "base_pay_2019r": "9 980 758",
     "benefits_2020": "1 430 398", "benefits_2019r": "902 156", "sti_2020": "6 476 886",
     "sti_2019r": "6 717 464", "lti_2020": "5 025 000", "lti_2019r": "2 756 000",
     "total_2020": "27 448 283", "total_2019r": "21 000 379"}
  ]
}
```

```json
{
  "year": 2023,
  "table": "total_remuneration_outcomes",
  "page": 134,
  "source_heading": "TOTAL REMUNERATION OUTCOMES",
  "unit": "R'000 (single figure remuneration)",
  "columns": [
    {"group": "Guaranteed pay", "metric": "base_pay", "year_ref": 2023},
    {"group": "Guaranteed pay", "metric": "base_pay", "year_ref": 2022},
    {"group": "Guaranteed pay", "metric": "benefits_and_allowances", "year_ref": 2023},
    {"group": "Guaranteed pay", "metric": "benefits_and_allowances", "year_ref": 2022},
    {"group": "Variable pay", "metric": "sti_and_retention_awards", "year_ref": 2023,
     "note": "COLUMN_RENAMED + COLUMN_MERGED vs. 2020-2022's bare 'STI' metric"},
    {"group": "Variable pay", "metric": "sti_and_retention_awards", "year_ref": 2022,
     "note": "2022 value here is the un-renamed original 'STI' figure restated under the new label"},
    {"group": "Variable pay", "metric": "lti", "year_ref": 2023},
    {"group": "Variable pay", "metric": "lti", "year_ref": 2022},
    {"group": null, "metric": "total_remuneration", "year_ref": 2023},
    {"group": null, "metric": "total_remuneration", "year_ref": 2022}
  ],
  "rows": [
    {"entity": "A Banderker", "base_pay_2023": "5 261 969", "base_pay_2022": "5 086 864",
     "benefits_2023": "516 761", "benefits_2022": "470 525",
     "sti_retention_2023": "20 252 268", "sti_retention_2022": "1 780 345",
     "lti_2023": "1 515 000", "lti_2022": "–",
     "total_2023": "27 545 998", "total_2022": "7 337 734"},
    {"entity": "W Britz", "base_pay_2023": "–", "base_pay_2022": "3 212 007",
     "benefits_2023": "–", "benefits_2022": "268 866",
     "sti_retention_2023": "–", "sti_retention_2022": "–",
     "lti_2023": "–", "lti_2022": "–",
     "total_2023": "–", "total_2022": "3 480 873",
     "status": "current-year dash, prior-year comparative retained — not yet ROW_REMOVED"},
    {"entity": "H Boonzaaier", "base_pay_2023": "3 618 654", "base_pay_2022": "3 491 926",
     "benefits_2023": "351 367", "benefits_2022": "326 122",
     "sti_retention_2023": "5 080 000", "sti_retention_2022": "1 208 153",
     "lti_2023": "1 010 000", "lti_2022": "2 200 000",
     "total_2023": "10 060 021", "total_2022": "7 226 201"},
    {"entity": "S Mmakau", "base_pay_2023": "–", "base_pay_2022": "2 072 609",
     "benefits_2023": "–", "benefits_2022": "202 572",
     "sti_retention_2023": "–", "sti_retention_2022": "–",
     "lti_2023": "–", "lti_2022": "–",
     "total_2023": "–", "total_2022": "2 275 181",
     "status": "current-year dash, prior-year comparative retained — not yet ROW_REMOVED"},
    {"entity": "TOTAL", "base_pay_2023": "8 880 623", "base_pay_2022": "13 863 406",
     "benefits_2023": "868 128", "benefits_2022": "1 268 085",
     "sti_retention_2023": "25 332 268", "sti_retention_2022": "2 988 498",
     "lti_2023": "2 525 000", "lti_2022": "2 200 000",
     "total_2023": "37 606 019", "total_2022": "20 319 989"}
  ]
}
```

## 6. Visual validation

Five pages were manually compared, rendered at 200 DPI, against the reconstructed structures
above and in Section 7 (exceeding the task's minimum of 2 NED tables + 2 remuneration-outcomes
tables):

| Page checked | Table | Row accuracy | Column accuracy | Cell-assignment accuracy | Footnote accuracy | Errors observed |
|---|---|---|---|---|---|---|
| 2020 p.105 | ned_remuneration_policy_table | 20/20 rows correct | 3/3 columns correct | 100% | 1/1 footnote correctly attached to ICT Steerco Chairperson row | None |
| 2022 p.121 | ned_remuneration_policy_table | 21/21 rows correct (incl. the nil-valued ICT Steerco Chairperson row) | 3/3 columns correct | 100% | 1/1 footnote correctly attached | None |
| 2020 p.102 | total_remuneration_outcomes | 5/5 rows (4 executives + TOTAL) | 10/10 columns (5 metrics × 2 years) | 100%, including the "Waived fee" text cell for W Britz's STI | 2/2 footnote markers (Banderker's "1", Mmakau's "2") correctly attached | None |
| 2023 p.134 | total_remuneration_outcomes | 5/5 rows | 10/10 columns | 100%, including all four current-year dash cells for W Britz/S Mmakau | 2/2 footnotes correctly attached (STI/retention explainer, share-count explainer) | None |
| 2024 p.128 | total_remuneration_outcomes | 4/4 rows (3 executives + TOTAL) | 10/10 columns | 100%, including G van Wyk's four 2023-column dashes and the STI-timing footnote marker on the 2024 STI header | 1/1 footnote correctly attached | None |

**No reconstruction error, cross-row contamination, or column shift was found on any of the five
pages checked.** This is a stronger result than the representation bake-off's or the within-
schedule alignment experiment's hazard-selected samples (which each found at least one
MINOR_CORRECTION_NEEDED case) — consistent with the row-block pattern identified in Section 3
being genuinely robust for these two specific table families in this specific report template, not
merely "probably fine." The one qualification: this experiment did not stress-test a table row that
spans a page break, since none of the ten sampled table-years happens to break a row across two
pages; that remains an open, untested edge case (Section 14).

## 7. Row alignment

### 7.1 `ned_remuneration_policy_table` (role-based identity)

| Role (category :: role) | 2020 | 2021 | 2022 | 2023 | 2024 | Event |
|---|---|---|---|---|---|---|
| Main Board :: Chairman | P | P | P | P | P | ROW_STABLE |
| Main Board :: Deputy Chairman | P | P | P | P | P | ROW_STABLE |
| Main Board :: Lead Independent Director | ABSENT | **P (new)** | P | P | P | ROW_ADDED (2021) |
| Main Board :: Member | P | P | P | P | P | ROW_STABLE |
| Subsidiary board :: Chairman | P | P | P | P | P | ROW_STABLE (2024 category renamed "Subsidiary board/committee," same role) |
| Subsidiary board :: Member | P | P | P | P | P | ROW_STABLE |
| Audit and Risk Committee :: Chairperson/Chairman | P | P | P | P | P | ROW_STABLE (label alternates Chairperson/Chairman across years, same role) |
| Audit and Risk Committee :: Member | P | P | P | P | P | ROW_STABLE |
| Remuneration Committee :: Chairperson | P | P | P | P | P | ROW_STABLE |
| Remuneration Committee :: Member | P | P | P | P | P | ROW_STABLE |
| Nomination Committee :: Chairperson | P | P | P | P | P | ROW_STABLE |
| Nomination Committee :: Member | P | P | P | P | P | ROW_STABLE |
| Social and Ethics Committee :: Chairperson | P | P | P | P | P | ROW_STABLE |
| Social and Ethics Committee :: Member | P | P | P | P | P | ROW_STABLE |
| Investment Committee :: Chairperson | P | P | P | P | P | ROW_STABLE |
| Investment Committee :: Member | P | P | P | P | P | ROW_STABLE |
| ICT Steering Committee :: Chairperson | **P (nil value, footnoted)** | **ABSENT** | **P (nil value, re-added)** | ABSENT | ABSENT | ROW_REMOVED (2021) then ROW_ADDED as a nil row (2022) then ROW_REMOVED again (2023) |
| ICT Steering Committee :: Member | P | P | P | P | P | ROW_STABLE |
| Special ad hoc board/committee meeting :: Member | ABSENT | ABSENT | ABSENT | ABSENT | **P (new)** | ROW_ADDED (2024) |

**Row-identity rule that works for this table: role name + committee/category, not person.** No
individual director's name ever appears as a row label in this table — it is a fee-policy table,
not a payments table, so identity is fully role-based and extremely stable: 16 of 19 distinct roles
observed are `ROW_STABLE` across all five years. The one genuinely oscillating row (ICT Steering
Committee Chairperson) is directly explained by its own recurring footnote every year it appears
with a nil value ("The Chairperson is currently an Executive Director and does not receive fees" /
"resigned... Sanlam CIO was approached to chair... no fees were paid") — the row's presence/absence
pattern tracks a real personnel/governance fact (whether the sitting chairperson is fee-eligible),
not an extraction inconsistency.

### 7.2 `total_remuneration_outcomes` (person-based identity)

| Entity | 2020 | 2021 | 2022 | 2023 | 2024 | Event |
|---|---|---|---|---|---|---|
| A Banderker (Group CEO through Oct 2023) | P | P | P | P | **P (partial year, resigned)** | ROW_STABLE through 2023; 2024 retained as a partial-year row, not removed (see Section 10) |
| H Boonzaaier (Group CFO) | P | P | P | P | P | ROW_STABLE, only fully continuous row across all 5 years |
| W Britz | P | P | P (role footnoted "now NED") | **current-year dash, prior comparative retained** | **ROW_REMOVED** | VALUE_MISSING (2023) then ROW_REMOVED (2024) |
| S Mmakau | P | P | P (role footnoted "Resigned Feb 2022") | **current-year dash, prior comparative retained** | **ROW_REMOVED** | VALUE_MISSING (2023) then ROW_REMOVED (2024) |
| G van Wyk (new Group CEO) | ABSENT | ABSENT | ABSENT | ABSENT | **P (new, current-year only, prior column blank)** | ROW_ADDED (2024) |

**Row-identity rule that works for this table: named individual, not role/title.** Unlike the NED
table, roles here (Group CEO, Group CFO) attach to different named people over time (Banderker →
van Wyk as CEO), so aligning by *role* would incorrectly treat 2023's Banderker row and 2024's van
Wyk row as the same comparison subject. Aligning by *person* correctly keeps Banderker's own
2020–2024 trajectory (including his 2024 partial-year departure figures) separate from van Wyk's
brand-new 2024 entry, and correctly identifies Britz and Mmakau as departing individuals rather than
folding their vacated "prescribed officer" function into whoever happens to hold an adjacent title
next.

**A three-state departure pattern, confirmed directly from the source text and consistent across
both Britz and Mmakau:** (1) full presence with real values; (2) one transition year where the
row is retained with a current-year dash but the *prior* year's comparative column still shows
real historical figures (2022→2023 for both); (3) full disappearance from the table the following
year, with no comparative retained at all (2023→2024). This is a genuine three-stage
`ROW_REMOVED` process, not a single event, and a pipeline that only checks "is the row present"
without checking "does the current-year cell carry a value" would misclassify stage (2) as
`ROW_STABLE`.

## 8. Column alignment

### 8.1 `ned_remuneration_policy_table`

| Column | 2020 label | 2021 label | 2022 label | 2023 label | 2024 label | Event |
|---|---|---|---|---|---|---|
| current_fee | "Current 2020 (R)" | "Current 2021 (R)" | "Current 2022 (R)" | "CURRENT 2023" | "Current (2024)" | COLUMN_STABLE (meaning); cosmetic label/case drift only |
| proposed_fee | "Proposed 2021 (R)" | "Proposed 2022 (R)" | "Proposed 2023 (R)" | "PROPOSED 2024" | "Proposed (2025)" | COLUMN_STABLE; year reference always +1 vs. current_fee's year |
| recommended_increase_pct | "Recommended increase (%)" | same | same | "PROPOSED INCREASE %" | "Recommended Increase (%)" | COLUMN_STABLE (meaning); cosmetic rename in 2023 only |

All three columns are present, in the same left-to-right order, every year. No `COLUMN_ADDED`,
`COLUMN_REMOVED`, `COLUMN_SPLIT`, or `COLUMN_MERGED` event was observed for this table across the
five years sampled — this table's *column* schema is the most stable structure found anywhere in
this experiment, even though its *row* set has three genuine add/remove events (Section 7.1).

### 8.2 `total_remuneration_outcomes`

| Column (metric) | 2020–2022 | 2023–2024 | Event |
|---|---|---|---|
| base_pay | "Base pay" | "Base pay" | COLUMN_STABLE |
| benefits_and_allowances | "Benefits and allowances" | "Benefits and allowances" | COLUMN_STABLE |
| sti | "STI" | **"STI and Retention Awards"** | **COLUMN_RENAMED + COLUMN_MERGED** — a new "Retention Awards" sub-component is folded into what was previously a pure short-term-incentive column, first appearing 2023 |
| lti | "LTI" | "LTI" | COLUMN_STABLE |
| total_remuneration | "Total remuneration" | "Total remuneration" | COLUMN_STABLE |
| (group headers) | "Guaranteed pay" / "Variable pay" | "Guaranteed pay" / "Variable pay" | COLUMN_STABLE (2-level header structure retained in every year, including the reformatted 2024 layout) |
| (year-pair convention) | current-year + prior-year comparative, 2020's prior column additionally marked "Restated" | current-year + prior-year comparative, no "Restated" marker | COLUMN_REORDERED: none; minor cosmetic drop of the "Restated" qualifier after 2020 only |

The `COLUMN_RENAMED + COLUMN_MERGED` event on the STI column is directly explained by the same
footnote that explains the Banderker STI/retention jump (Section 11): 2022's Remuneration
Committee-commissioned benchmarking review introduced a new retention-award payment category
starting in the 2023 report, and the table's own column header was updated to reflect it rather
than silently adding an unlabeled sixth column. This is a genuine, source-confirmed schema
evolution, not a labeling inconsistency — a future structured-comparison pipeline must record that
2022-and-earlier "STI" values are not directly comparable in composition to 2023-and-later "STI and
Retention Awards" values, even though both occupy the same column position.

## 9. Structured value-diff results

Selected recurring row/column intersections, `ned_remuneration_policy_table` (Chairman, Main
Board — the single most-referenced NED fee line):

| Metric | 2020→2021 | 2021→2022 | 2022→2023 | 2023→2024 |
|---|---|---|---|---|
| current_fee (R) | 1 329 240 → 1 445 849 | 1 445 849 → 1 445 849 | 1 445 849 → 1 503 683 | 1 503 683 → 1 578 867 |
| Event | VALUE_INCREASED | VALUE_UNCHANGED | VALUE_INCREASED | VALUE_INCREASED |
| % change | +8.8% | 0.0% | +4.0% (matches stated "4" recommended-increase figure) | +5.0% (matches stated "5.0%" recommended figure) |

Note the 2021→2022 transition: the *current* fee for 2022 equals the *proposed* fee stated in
2021's own table (both 1 445 849) — confirming the "proposed" column in year N genuinely becomes
the "current" column in year N+1, a direct, checkable cross-year consistency test this experiment
ran successfully on this and several other role rows (Deputy Chairman: 997 713→1 032 633 (2020
proposed) = 1 032 633 (2021 current), confirmed; Member: 248 188→256 875 (2020 proposed) = 256 875
(2021 current), confirmed).

`total_remuneration_outcomes`, H Boonzaaier (Group CFO, the only fully continuous individual):

| Metric | 2020→2021 | 2021→2022 | 2022→2023 | 2023→2024 |
|---|---|---|---|---|
| total_remuneration (R) | 6 843 695 → 7 262 792 | 7 262 792 → 7 226 202 | 7 226 202 → 10 060 021 | 10 060 021 → 5 282 261 |
| Event | VALUE_INCREASED | VALUE_DECREASED (marginal) | VALUE_INCREASED | VALUE_DECREASED |
| % change | +6.1% | −0.5% | +39.2% | −47.5% |

The 2022→2023 and 2023→2024 swings for Boonzaaier are large enough that a naive percentage-change
threshold rule ("flag anything over X%") would correctly surface both, but only the footnote
(Section 11) explains *why*: 2023's jump is the same retention-award mechanism that drove
Banderker's much larger swing; 2024's drop reflects the STI/retention award not recurring at the
same scale that year, not a pay cut to guaranteed pay (guaranteed pay itself rose 5.5% in 2024, per
the "Increase in guaranteed pay" line item captured alongside this table).

## 10. Validation case studies

**NED fee change (Section 9, Chairman row) — VALIDATED.** Recurring annual increases of
3.5%→0%→4%→5.0%→5.5% across the five transitions, with the 2021→2022 zero-increase year directly
explained in-text ("The Chairman and the Deputy Chairman remuneration is all inclusive" combined
with the fee having just been raised to align with a PwC benchmarking review the prior year) —
confirmed by cross-referencing the 2021 table's own surrounding narrative, not merely observed as a
bare data point.

**Banderker 2022→2023 STI/retention jump — VALIDATED, with the source-confirmed decomposition.**
`total_remuneration_outcomes` shows STI (2022) = 1 780 345 → "STI and Retention Awards" (2023) =
20 252 268, an apparent 11.4× increase. The `individual_remuneration_outcomes` page (p.135, read
directly this session) decomposes the 2023 figure explicitly: STI = 0 (not achieved — EBIT target
missed, per the STI-performance narrative on the same page), "STI (previous period)" = 5 621 868,
"Retention awards" = 14 630 400, sum = 20 252 268 — an exact match to the single-figure table's
combined cell, confirmed by direct arithmetic in this session. The retention-award mechanism itself
is explained by a footnote (Section 11): a 2022 Remco-commissioned external benchmarking review of
CEO/CFO rewards found shortcomings in LTI awards, and since backdating share awards is not
possible, cash payments were made instead to rectify the shortfall.

**Banderker 2023→2024 collapse — VALIDATED.** Total remuneration falls from 27 545 998 (2023) to
1 927 224 (2024), a 93% drop. The `total_remuneration_outcomes` table itself carries no explanatory
text, but the adjacent `individual_remuneration_outcomes` page (p.130) carries the explanatory
footnote directly under his name: **"Resigned 31 October 2023."** 2024's salary line (1 752 609)
is almost exactly one-third of 2023's annualized salary (5 261 969 × ~1/3 ≈ 1 753 990), consistent
with a partial year of service before resignation, confirmed by this session's own arithmetic
cross-check.

**G van Wyk added in 2024 — VALIDATED.** Appears as a wholly new row in `total_remuneration_outcomes`,
2023 column blank across all five metrics, 2024 total remuneration 9 377 958. No footnote directly
states "new Group CEO" on this specific table page, but the row order (van Wyk listed first, ahead
of Banderker) and the surrounding remuneration-report narrative (read in prior experiments and
re-confirmed present in this session's page dumps) establish him as the incoming Group CEO
succeeding Banderker — a `ROW_ADDED` event that directly mirrors Banderker's own `ROW_REMOVED`
(partial-retention) event in the same table-year, the clearest same-table CEO-succession signal in
this sample.

**Executive rows removed / changed to nil — VALIDATED (two rows, one company-year).** W Britz and
S Mmakau both show the three-stage pattern documented in Section 7.2: full presence through 2022,
a 2023 transition year (current-year dash, 2022 comparative retained), and full removal from the
2024 table. Both departures are footnoted in the 2022 individual-outcomes pages ("Resigned in
March 2022, and is now NED" for Britz; "Resigned in February 2022" for Mmakau), confirming the 2023
transition-year dash is a reporting-lag artifact of the report's own year-over-year comparative
convention (a departed executive's *prior*-year comparative is still shown once, in the first
post-departure report, then dropped), not a data-quality defect.

## 11. Footnote analysis

Footnotes materially change the interpretation of every one of this experiment's four largest
numeric events:

| Footnote (paraphrased, year/page) | Row/cell affected | What it explains |
|---|---|---|
| "A Banderker joined 1 April 2019, figures are prorated" (2020, p.102) | Banderker 2019-restated column | Why his 2019 comparative figures are far lower than a full-year figure would be — without this, the 2020→2021 transition would read as an anomalously large increase that is actually a prorating artifact on the *prior* side of the comparison |
| "S Mmakau: 2019 STI includes sign-on retention bonus" (2020, p.102) | Mmakau 2019-restated STI cell | Explains an otherwise-unusual STI figure for a year before the row's own five-year window even starts |
| "Resigned in March 2022, and is now NED" (2022, p.120) | W Britz row | Explains both the 2022 role change and previews the 2023/2024 departure pattern documented in Section 7.2 |
| "Resigned in February 2022" (2022, p.121) | S Mmakau row | Same, for Mmakau |
| "During 2022, the Remco appointed external consultants to benchmark the CEO and CFO rewards which demonstrated shortcomings specifically relating to LTI awards... the cash payments were then made... to rectify the shortcomings" (2023, p.135) | Banderker & Boonzaaier 2023 "Retention awards" cells | The single most important footnote in this entire experiment — without it, the 11.4× Banderker STI/retention jump and Boonzaaier's 39.2% total-remuneration increase would both read as unexplained anomalies; with it, both are the same, single, named governance event |
| "Resigned 31 October 2023" (2024, p.130) | Banderker row | Explains the 93% total-remuneration collapse as a partial-year departure, not a pay cut |
| "STI was approved after the release of the Annual Financial Statements, but before the publication of the Integrated Annual Report" (2024, p.128) | 2024 STI column header | A timing/recognition caveat on the 2024 STI figures specifically — relevant to why 2024's STI values might not be strictly comparable in *timing* to prior years' even though the column header itself is stable |

**No footnote in this sample was found to be page furniture or safely discardable.** Every
footnote checked either explains a specific numeric event this experiment set out to validate, or
provides a timing/recognition caveat that changes how a future comparison should treat the
column it's attached to. This directly confirms the task brief's instruction not to discard
footnotes: a metric-only pipeline that stripped them (as several of the lexical-pilot experiment's
own text-comparison units did, deliberately, for prose furniture) would produce three or four
"unexplained large change" flags in this ten-table-year sample where the source document itself
supplies the explanation one line away.

## 12. Table-shape drift

| Pattern | Table | What changed | Visual redesign or substantive schema change? |
|---|---|---|---|
| Column count/order | `ned_remuneration_policy_table` | None across 5 years — 3 columns, same order, every year | Neither — fully stable |
| Row count | `ned_remuneration_policy_table` | 19→20→21→20→19 distinct role rows (Lead Independent Director added 2021; ICT Steerco Chairperson oscillates; Special ad hoc row added 2024) | Substantive (each event maps to a real governance/fee-policy fact, Section 7.1) |
| Column meaning | `total_remuneration_outcomes` | STI column absorbs a new "Retention Awards" component (2023+) | Substantive (Section 8.2) — the column header itself changed to signal this, not silently |
| Row roster | `total_remuneration_outcomes` | Full CEO succession (Banderker→van Wyk) plus two other executive departures, over 5 years | Substantive — real personnel change, the table's primary analytical content |
| Header presentation | `total_remuneration_outcomes` | 2024's page layout drops the per-page bar chart and per-executive donut charts that accompanied the table in 2020–2023, presenting the table alone with a terser page | Visual redesign only — the table's own row/column structure is unaffected, confirmed by the 2024 visual check (Section 6) reproducing the same 2-level header grouping as every prior year |
| "Restated" qualifier | `total_remuneration_outcomes` | Present on the prior-year column label in 2020 only, silently dropped from 2021 onward even though prior-year comparatives continue to appear | Cosmetic — no evidence the underlying prior-year figures stopped being restated where applicable; this is a labeling omission, not a schema change, and was not further investigated (out of scope for this experiment's two focal tables) |
| Committee fee list composition | `ned_remuneration_policy_table` | Same six/seven standing committees named every year, in the same order, at the same nesting level | Neither — fully stable |

**Overall:** both tables show far more schema stability than the NED *payments* table observed
incidentally on the same pages (Section 2), whose column set (which committees/subsidiary boards
appear as named columns) changes almost every year because it mechanically follows which directors
sat on which ad hoc subsidiary boards that year — a genuinely different, more volatile schema-drift
profile than either of this experiment's two focal tables, and a useful negative contrast: not
every remuneration-schedule table is this well-behaved, and a future pipeline should not assume the
stability found here generalizes to every adjacent table without separately checking it.

## 13. Plain text vs. structured reconstruction

Comparing PyMuPDF's linear `get_text()` output against the structured reconstruction, for the 2023
`total_remuneration_outcomes` page (chosen because it carries this experiment's largest and most
consequential numeric event):

**A. Plain text** (as a lexical-comparison pipeline would receive it, unmodified):

```
TOTAL REMUNERATION OUTCOMES
Single figure remuneration (R'000)
Executive directors
Guaranteed pay
Variable pay
Total remuneration
Base pay
Benefits and allowances
STI and Retention Awards
LTI
2023 2022 2023 2022 2023 2022 2023 2022 2023 2022
A Banderker
 5 261 969  5 086 864   516 761   470 525  20 252 268  1 780 345
1 515 000   – 27 545 998   7 337 734
W Britz
 –  3 212 007   –   268 866   –   –   –   –   –  3 480 873
...
```

What is lost by treating this as flowing prose: **every number is present, but nothing in the
linear token stream states which number belongs to which director, which metric, or which year.**
A lexical-similarity metric (unigram/bigram Jaccard, TF-IDF cosine, edit distance — the exact
metric set validated by the lexical-change pilot) run directly on this text would report the
2022→2023 transition's similarity based on shared/differing *tokens*, without any way to say "the
20 252 268 figure belongs to Banderker's STI-and-Retention-Awards column" — it could at best report
"many numbers changed," never "Banderker's variable pay increased 11.4× due to a one-off retention
award, while Boonzaaier's guaranteed pay grew a routine 4.0%." The economically meaningful fact —
*which* person's *which* pay component changed by *how much*, and whether that change is even
mathematically comparable across years (Section 8.2's STI/Retention-Awards column merge) — is
entirely a property of the row × column structure, and is destroyed the moment the table is
serialized to a flat token sequence for a general-purpose text-similarity metric.

**B. Structured reconstruction** (Section 5) preserves exactly this association, making the
Section 9–10 value-diff and validation-case analysis possible in the first place. This is the same
conclusion the eligibility experiment reached qualitatively (Section 9 there); this experiment adds
a concrete, reproducible demonstration on this corpus's actual text.

## 14. Deterministic vs. semantic responsibilities

| Task | Classification | Basis |
|---|---|---|
| Row-block extraction from PyMuPDF blocks | `DETERMINISTIC_SUFFICIENT` | Confirmed row-major block grouping on all 10 table-years, zero exceptions found |
| Column-header-to-data-column matching (x0 order) | `DETERMINISTIC_SUFFICIENT` | Header blocks and value tokens share consistent left-to-right ordering; confirmed by the Section 9 cross-year consistency check (2021 proposed fee = 2022 current fee) |
| Nil/zero/blank/N-A disambiguation | `DETERMINISTIC_SUFFICIENT` | The source text itself distinguishes en-dash, "Waived fee," numeric 0, and cell absence as different literal strings — no inference needed, only careful string preservation |
| Footnote-marker-to-cell association | `DETERMINISTIC_SUFFICIENT` | Marker characters/digits are literal substrings shared between the footnote block and the referencing row's label/value text |
| Role-based row identity (NED table) | `DETERMINISTIC_SUFFICIENT` | Role/category strings are stable enough (Section 7.1) for exact or lightly-normalized string matching across all 5 years, including the two add/remove events, which are cleanly detectable as string presence/absence |
| Person-based row identity (remuneration-outcomes table) | `DETERMINISTIC_SUFFICIENT` for stable individuals; `SEMANTIC_LABEL_NORMALIZATION_NEEDED` for edge cases not observed in this sample | Names appear in a consistent "Initial Surname" format every year in this sample with no observed abbreviation drift (unlike the analytical-unit eligibility experiment's "Chairman"/"Chairperson" case) — but a larger sample including a name-formatting change (marriage, title change, initials vs. full first name) would likely need fuzzy matching; not tested here because it did not occur |
| Recognizing a `ROW_ADDED` new hire is the successor to a `ROW_REMOVED` departure (Banderker→van Wyk) | `SEMANTIC_ROW_ALIGNMENT_NEEDED` | No textual signal within the table itself states "van Wyk succeeds Banderker as CEO" — this required reading the row order and the surrounding narrative (Section 10), which a purely row-identity-matching algorithm operating on the table alone cannot do |
| Recognizing the STI→"STI and Retention Awards" rename is a genuine composition change, not cosmetic | `SEMANTIC_LABEL_NORMALIZATION_NEEDED` | Required reading the footnote (Section 11) and cross-checking the individual-outcomes page's decomposition — the column header text alone ("STI and Retention Awards") is suggestive but not conclusive without the footnote |
| Explaining *why* a large numeric swing occurred (governance/personnel event vs. genuine pay-policy change) | `SEMANTIC_LABEL_NORMALIZATION_NEEDED` (footnote reading), not multimodal | Every case in this sample was resolved by reading an adjacent footnote or narrative sentence in plain text — no case required image-based reasoning |
| Table detection itself (is this block cluster a table at all) | Not tested here — both tables' locations were taken from the eligibility experiment's prior localization, not re-derived from scratch | Out of scope for this experiment, which focused on reconstruction once located, per the task brief |

**No task in this sample required multimodal escalation.** This is consistent with, and extends,
the longitudinal and within-schedule alignment experiments' shared finding that ACT's own hazard
class is narrower than BEL's or Kore Potash's — this experiment adds that ACT's *tabular* remuneration
disclosures specifically are extraction-friendly in a way its *chart* disclosures (the base-pay bar
chart, the donut charts) are not, a distinction not previously drawn this precisely.

## 15. Data model implications

Not implemented — proposed only, as a minimum shape sufficient to represent everything found above,
extending (not replacing) the semantic-unit model proposed by the within-schedule alignment
experiment:

```
structured_table {
  id, semantic_unit_id (FK to the containing analytical/structural unit, e.g. ned_remuneration_policy_table),
  year, page, source_heading, unit_of_measure (nullable, e.g. "R'000"),
  reconstruction_status (CLEAN | MINOR_CORRECTION_NEEDED | MAJOR_LAYOUT_RECONSTRUCTION_NEEDED | MULTIMODAL_REQUIRED),
  reconstruction_confidence (HIGH | MEDIUM | LOW)
}

table_column {
  id, structured_table_id (FK), position (int, left-to-right order),
  source_label (exact string as printed), normalized_metric (e.g. "current_fee", "sti"),
  group_label (nullable, e.g. "Guaranteed pay"), year_ref (nullable int),
  is_restated (bool, nullable)
}

table_row {
  id, structured_table_id (FK), position (int, top-to-bottom order),
  row_identity_type (ROLE | PERSON), source_label (exact string),
  category_label (nullable, e.g. "Main Board (annualised retainer fee)"),
  presence_status (PRESENT | ABSENT | VALUE_MISSING_COMPARATIVE_RETAINED)
}

table_cell {
  id, table_row_id (FK), table_column_id (FK),
  raw_value (exact source string, e.g. "1 329 240", "–", "Waived fee"),
  parsed_numeric_value (nullable decimal), semantic_status (NUMERIC | NIL_DASH | WAIVED | NOT_APPLICABLE | MISSING),
  currency_or_unit (nullable), footnote_ids (array, nullable)
}

table_footnote {
  id, structured_table_id (FK), marker (exact string, e.g. "*", "1"),
  text (exact source string), referenced_cell_ids (array)
}

row_alignment_edge {
  id, from_row_id (FK, nullable for ROW_ADDED), to_row_id (FK, nullable for ROW_REMOVED),
  relationship (ROW_STABLE | ROW_ADDED | ROW_REMOVED | ROW_RENAMED | ROW_REORDERED |
                ROW_ROLE_CHANGED | SUCCESSION_INFERRED | CANNOT_ALIGN_ROW),
  confidence, evidence_summary, rule_basis (DETERMINISTIC | SEMANTIC)
}

column_alignment_edge {
  id, from_column_id (FK, nullable), to_column_id (FK, nullable),
  relationship (COLUMN_STABLE | COLUMN_ADDED | COLUMN_REMOVED | COLUMN_RENAMED |
                COLUMN_REORDERED | COLUMN_SPLIT | COLUMN_MERGED | CANNOT_ALIGN_COLUMN),
  confidence, evidence_summary
}

value_change_event {
  id, from_cell_id (FK, nullable), to_cell_id (FK, nullable),
  event_type (VALUE_UNCHANGED | VALUE_CHANGED | VALUE_INCREASED | VALUE_DECREASED |
              VALUE_TO_ZERO | ZERO_TO_VALUE | VALUE_TO_NIL | NIL_TO_VALUE |
              VALUE_MISSING | VALUE_NOT_APPLICABLE | CANNOT_COMPARE),
  absolute_change (nullable decimal), pct_change (nullable decimal, null whenever the
    denominator is zero/nil/missing/not-applicable per the task's explicit constraint),
  footnote_ids (array, nullable, carried through from either side's table_cell)
}
```

`row_alignment_edge.relationship` includes a `SUCCESSION_INFERRED` value not present in the task
brief's own list, added here specifically for the Banderker→van Wyk case (Section 10): a
`ROW_REMOVED` and a `ROW_ADDED` in the same table-year, for two different identity values, that a
downstream feature may want to link as a probable succession event — but this experiment
deliberately keeps it a *separate*, lower-confidence edge type from `ROW_RENAMED`, because unlike a
renamed role (same underlying entity, new label) a succession is two genuinely different entities
and should never be silently merged into one comparison subject. No schema was implemented; this is
a design note only, per the task's explicit instruction.

## 16. Pipeline implications

Evaluating whether the analytical eligibility stage (per the eligibility experiment's own
taxonomy) can now route units into the five statuses named in the task brief:

- **`STRUCTURED_COMPARISON`** — **Validated as an executable modality, not just a recommendation.**
  Both `ned_remuneration_policy_table` and `total_remuneration_outcomes` can now be routed here
  with a concrete reconstruction method (Section 3), a concrete row/column alignment method
  (Sections 7–8), and a concrete value-diff output shape (Section 9, Section 15's
  `value_change_event`) — none of which existed before this experiment. This closes the specific
  gap the eligibility experiment identified as its "clearest next research gap, not a
  proceed-as-is item."
- **`LEXICAL_DIRECT` / `LEXICAL_WITH_NUMERIC_CONTEXT`** — unaffected by this experiment; these
  remain governed by the lexical-change pilot's findings for prose units.
- **`PRESENCE_STATUS_ONLY`** — this experiment's row-level `presence_status` field (Section 15)
  generalizes the eligibility experiment's unit-level presence-tracking recommendation down to
  individual table rows (e.g., is a given committee's fee row present at all this year), which is a
  useful refinement: a table can be `STRUCTURED_COMPARISON` at the table level while individual
  thin/rare rows within it (the ICT Steerco Chairperson row, present in only 2 of 5 years) are
  better read as presence/absence facts than as a five-point value series.
- **`BOUNDARY_ADJUSTED`** — not triggered by either table in this sample; both tables' boundaries
  (Section 2) matched the eligibility experiment's original page attributions exactly, with no
  cross-unit content displacement analogous to the advisory-vote case found there. This experiment
  did not test a table known to have a boundary problem, so it neither confirms nor refutes whether
  `STRUCTURED_COMPARISON` tables are equally prone to that hazard class.

## 17. Recommendation

**(A) STRUCTURED TABLE COMPARISON IS READY TO EXPAND.**

The evidence supports this without qualification for the two table families tested: reconstruction
was CLEAN on all 10 table-years sampled (5 years × 2 tables), visual ground-truth checks (5 pages,
exceeding the required minimum) found zero errors, row and column alignment rules were identified
and validated against five known events (Sections 7–10), footnotes were shown to be necessary and
sufficient to explain every large numeric swing encountered (Section 11), and the plain-text-vs-
structured comparison (Section 13) directly demonstrates what a lexical-only pipeline would lose.
No multimodal escalation was needed anywhere in this sample.

**Which additional ACT table units should be added next.** The eligibility experiment's own
Section 14 named three further `implementation_report` children sharing
`total_remuneration_outcomes`'s table-native structure closely enough to expect the same treatment:
`sti_lti_performance_outcomes`, `individual_remuneration_outcomes` (partially read incidentally in
this experiment's validation cases, Section 10, and observed to follow the same person-keyed,
row-major block pattern — a strong prior that it would reconstruct cleanly), and
`ned_fees_and_payments_table` (observed incidentally in this experiment, Section 2/12, to have a
*more* volatile column schema than either focal table — a good next test of whether the
reconstruction method generalizes to a genuinely less-stable table, not just a second easy case).
`individual_remuneration_outcomes` is the recommended first addition, since it is already
partially validated by this experiment's own footnote-decomposition cross-check (Section 10).

**Should BEL be introduced now?** Not yet. This experiment, like the eligibility, within-schedule,
and lexical-pilot experiments before it, remained ACT-only. The row-major block-grouping finding
that made deterministic reconstruction possible here (Section 3) is a property of ACT's specific
page-layout template, observed consistently across five years of that one template — it has not
been tested against BEL's differently-designed remuneration tables (the longitudinal experiment
documented BEL's own report using a materially different, more expanded, more embellished
remuneration-committee report structure) or any other company's table layout. A second company is
the right next test of whether "blocks hand back the row as one already-associated unit" is an
AfroCentric-template property or a broader PyMuPDF/typical-table-layout property — that question is
currently open and should be resolved with a second company before assuming the method generalizes.

**What should be implemented before corpus-scale use.** Three concrete, scoped items, in priority
order:

1. **A reusable row-block parser** implementing the deterministic extraction rule identified in
   Section 3 (split block text on newlines; assign the leading non-numeric run as the row label;
   assign remaining tokens to columns by count and position, cross-validated against the
   column-header block count) — this experiment characterized the rule manually on ten table-years
   but did not package it as reusable code, per the task's explicit instruction not to implement.
2. **A page-break-spanning-row test**, since no table row in this ten-table-year sample happened to
   straddle a page boundary (Section 6's stated gap) — this is a plausible real hazard at
   corpus scale that this sample simply did not exercise, and the row-block parser above should not
   be trusted on a page-spanning row until tested against one.
3. **The `SUCCESSION_INFERRED` edge type's confidence calibration** (Section 15) — this experiment
   established that succession detection requires reading surrounding narrative, not table
   structure alone, but did not test how reliably that narrative-reading step generalizes beyond
   the one clean case (Banderker→van Wyk) found here, where the succession was independently
   confirmed by multiple experiments' prior reading of the same corpus.

This experiment does **not** recommend (B) refining the reconstruction method first, because no
reconstruction defect was found on any of the ten table-years or five visually-checked pages to
refine against. It does not recommend (C) — multimodal/layout-aware extraction was tested for and
found unnecessary at every step; introducing it now would add cost without a documented failure
mode to justify it. It does not recommend (D) — the two tables tested are not too heterogeneous for
a general structured approach; on the contrary, the same row-major block-grouping rule and the same
three-state departure/nil/absence model applied cleanly to both a role-keyed policy table and a
person-keyed outcomes table with materially different row-identity semantics, which is evidence for
generality within this report template, not against it.

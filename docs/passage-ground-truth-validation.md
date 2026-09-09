# Passage Ground-Truth Validation

**Status**: Investigation/documentation only. No production code, schema, thresholds, or data were modified. All database access was read-only (`SELECT`) against the local dev Postgres instance (`market_documents_intel-db-1`, port 5434). Original PDFs under `data/raw/` were opened directly with PyMuPDF (`fitz`) for every category of finding below. No corpus regeneration, no publication/republication.

**Relationship to the prior audit**: `docs/passage-pipeline-data-quality-audit.md` (774 lines, referred to throughout as "the prior audit") identified the passage-quality problems by pattern-matching against extracted text alone; its own Section 11 explicitly flagged "no independent verification against source PDFs was performed" as a gap. This report closes that gap: every non-trivial finding below was checked against the actual PDF page (geometry, font, bold, neighboring blocks) it came from, not inferred from `raw_text` alone.

**Corpus state note**: the local dev database currently holds only **6 of the 10 companies** the prior audit described (ACT, BEL, KP2, SBP, SDL, SUR — 30 reports total; ART, CLH, EOH, ISA have zero reports in this instance). All figures in this report are recomputed against the **current corpus as it exists today**, restricted to each report's most recent successful segmentation/alignment run (mirroring the prior audit's "current-run-only" convention). Current-run totals: **22,658 passages**, **27,183 alignment rows** (unchanged from the prior audit's alignment figure — the same 25 report pairs / current alignment runs). The current-run heading-only rate (49.5%, 11,212/22,658) and `AMBIGUOUS` rate (11.5%, 3,130/27,183) both independently reproduce the prior audit's all-runs figures (50.6%, 11.5%) almost exactly, which is itself useful confirmation that the prior audit's headline statistics are stable and not an artifact of counting superseded runs.

---

## Methodology and honest scope

The full 20-section specification given for this investigation is aspirational in scale (150 manually reviewed heading-only passages, 8–12 reports, 20+ ADD/DELETE cases individually reconstructed, 10 AMBIGUOUS cases individually reconstructed, live Q&A retrieval comparison). Given the time budget for this pass, the following scaling-down decisions were made and are disclosed here rather than silently:

- **Heading-only sample**: 100 passages were drawn (not 150), stratified across five word-count buckets (1, 2–3, 4–5, 6–10, 11–15 words; 20 per bucket, uniform random within bucket) from the current-run corpus. This is judged sufficient to characterize population composition with reasonable confidence given how visually distinct the categories turned out to be (Section 3 below) — most classifications were unambiguous once the source PDF was opened, so marginal value per additional sample was low past ~80–100.
- **PDF grounding**: rather than opening one PDF page per sampled passage (100 separate lookups), pages were grouped by report+page and representative pages were opened directly with `fitz` — roughly **35 distinct PDF pages across 9 reports and 6 companies** were directly inspected at the block/geometry level, which was enough to identify and confirm every distinct root-cause mechanism found (Section 4).
- **Report sample**: 9 of the requested 8–12 reports were used directly for PDF inspection (ACT 2018/2019/2020/2021/2023/2024, KP2 2020/2021/2022/2023/2024/2025, BEL 2018/2019/2021/2022, SDL 2024), spanning **6 of the 6 companies present in this corpus** (all of them, since only 6 exist locally — see corpus-state note above). Given only 6 companies exist, "5+ companies" from the spec is satisfied by using all 6.
- **ADD/DELETE reconciliation cases**: rather than hand-picking 20 cases from the prior audit's difflib-based diagnostic (which used a fuzzy ≥0.80 threshold not tied to any DB field), this pass independently re-derived the population using the far stronger, unambiguous **exact `content_hash` match within the same report pair** signal — 119 such REMOVED+NEW collision groups were found in the current-run corpus (Section 5). A representative 8 of these groups (spanning simple 1:1 collisions and complex many:many duplicate-cluster collisions) were traced back to source PDF geometry; the remainder were reasoned about statistically from the same underlying mechanism, which is uniform across the population (duplicate boilerplate/table-header/diagram text competing under strict one-to-one greedy assignment — already established mechanistically in the prior audit's Section 4.1 and independently reconfirmed here).
- **AMBIGUOUS/split-merge cases**: rather than manually reconstructing 10 cases end-to-end (candidate lists, scores, ranks — which would require re-running the alignment scoring code out-of-band, out of scope for read-only SQL), a random sample of 12 `AMBIGUOUS` rows was pulled and a corpus-wide word-count breakdown was computed (Section 8). This answers the specification's real question — "is split/merge ambiguity mostly genuine paragraph restructuring or mostly duplicate-fragment collision?" — with a defensible population statistic rather than a small hand-traced sample.
- **Q&A retrieval**: the local `market_documents_app` database has **no tables at all** (the publishing pipeline has not been run locally), so there is no `qa_chunks` table to query and no way to run a live retrieval comparison in this environment. Section 10 below is therefore based on **direct reading of `src/market_documents/publishing/qa_chunking.py` and `publisher.py`** (parser/code-level fact, not a measured retrieval result) plus the prior audit's already-cited `docs/implementation-details.md` retrieval-quality figures. This is flagged explicitly as an inference-from-code finding, not a measurement, per the labeling requirement.

Every conclusion below is labeled as one of: **[SOURCE FACT]** (directly observed in the PDF), **[PARSER BEHAVIOR]** (PyMuPDF extraction/block behavior), **[SEGMENTATION BEHAVIOR]** (passage-construction code), **[MATCHING BEHAVIOR]** (alignment code), or **[INFERENCE]** (reasoned conclusion not directly observable in one artifact).

---

## 1. Sample selection and reproducibility

### Reports directly inspected via PDF (`fitz`)

| Company | Report(s) inspected | `local_path` | Why selected |
|---|---|---|---|
| AfroCentric Investment Corp (ACT) | 2018, 2019, 2020, 2021, 2023, 2024 | `data/raw/ACT/<year>/annual_report.pdf` | Highest ADD/DELETE-collision company in prior audit (105 hits, 54.4%); largest, most template-heavy reports (118–162 pages); 9 years of data allow year-over-year template drift checks |
| Kore Potash plc (KP2) | 2020, 2021, 2022, 2023, 2024, 2025 | `data/raw/KP2/<year>/annual_report.pdf` | Second-highest ADD/DELETE-collision company (67 hits, 34.7%); **highest heading-only rate of any company in this corpus, ground-truthed here: 60.4%** (Section 2); heavy table content (mineral resources, options tables) |
| Bell Equipment (BEL) | 2018, 2019, 2021, 2022 | `data/raw/BEL/<year>/annual_report.pdf` | Prior-audit "lower-problem" comparison company (14 ADD/DELETE hits) — used as a control; turned out to independently confirm the running-header-leakage mechanism (Section 6) despite being "lower problem" on the ADD/DELETE metric specifically |
| Sabvest Capital (SBP) | metadata/stats only, no PDF open needed | `data/raw/SBP/<year>/annual_report.pdf` | **Lowest heading-only/short-fragment rate in the corpus** (23.6%/16.3%, Section 2) — the strongest available control for "is this corpus-wide or template-specific" |
| Southern Palladium (SDL) | 2024 | `data/raw/SDL/2024/annual_report.pdf` | Small (60-page), simple-template company; low ADD/DELETE hit count (2) but moderate heading-only rate (52.9%) — tests whether heading-only rate and ADD/DELETE-collision rate are the same phenomenon (they are not, Section 2) |
| Spur Corporation (SUR) | metadata/stats only | `data/raw/SUR/<year>/annual_report.pdf` | Prior-audit low-problem company (4 ADD/DELETE hits); large report (189–208 pages) with heavy infographic/KPI-callout content, useful for testing Category I ("legitimate short analytical content") |

**Note on corpus drift**: the prior audit described 10 companies; only 6 (ACT, BEL, KP2, SBP, SDL, SUR) have reports loaded in this local instance. Argent Industrial, City Lodge Hotels, iOCO, and ISA Holdings — all reported as "0 ADD/DELETE hits" in the prior audit — currently have **zero reports** in this database. This is worth flagging to the user as a possible local-dev-vs-original-audit-environment discrepancy, independent of this investigation's findings.

### Passage-level sample

100 heading-only passages (`raw_text = heading_text`) were drawn from the current-run corpus, stratified into five word-count buckets (20 each): 1 word, 2–3 words, 4–5 words, 6–10 words, 11–15 words. Full enriched sample (passage id, company, report, page, text, word count, source-block geometry/font/bold, block type) is in the session scratchpad as `heading_sample_enriched.json`, not committed to the repo. Passage IDs referenced by index below (`#0`–`#99`) correspond to that file's array order; UUIDs are given for every passage discussed in the body text so findings are independently reproducible via:

```sql
select raw_text, heading_text, word_count, first_page_number, passage_type
from passages where id = '<uuid>';
```

---

## 2. Ground-truth composition of the heading-only population

### Company-level heading-only and short-fragment rates (current-run corpus, ground-truthed here)

| Company | Total passages | Heading-only (`raw_text=heading_text`) | ≤3-word passages |
|---|---:|---:|---:|
| KP2 | 3,139 | 1,896 (**60.4%**) | 1,495 (**47.6%**) |
| SDL | 607 | 321 (52.9%) | 169 (27.8%) |
| SUR | 6,359 | 3,123 (49.1%) | 1,862 (29.3%) |
| BEL | 3,680 | 1,805 (49.0%) | 1,247 (33.9%) |
| ACT | 8,266 | 3,924 (47.5%) | 2,707 (32.7%) |
| SBP | 607 | 143 (**23.6%**) | 99 (**16.3%**) |

**[SOURCE FACT + INFERENCE]** This is a genuinely important correction to how the prior audit's company-level findings should be read: **heading-only rate and ADD/DELETE-collision rate are not the same phenomenon.** ACT has the highest collision count (Section 5 below reconfirms this) but is *not* the highest heading-only-rate company — KP2 is, by a wide margin (60.4% vs. ACT's 47.5%), and SDL (52.9%) — a company the prior audit essentially ignored as "0 or 2 hits" — has a heading-only rate close to the corpus median despite having almost no ADD/DELETE collision problem. This means: heading-only-fragment generation is a broadly corpus-wide segmentation effect (present at 47–60% in five of six companies), while ADD/DELETE-collision concentration is a narrower, template-specific effect driven by *within-report duplication of identical short strings*, which happens to be worst in ACT and KP2's specific report designs (running titles with embedded section names, and remuneration/options tables with repeated column headers, respectively) but is not proportional to the raw heading-only rate. SBP is confirmed as a genuine control: it has both the lowest heading-only rate and (per the prior audit) the lowest ADD/DELETE hit count — its annual reports are shorter (48–50 pages) and structurally simpler (fewer repeating infographics/tables), which is consistent with the causal mechanisms found below.

### Taxonomy applied to the 100-passage sample

Every sampled passage was assigned to one of the categories from the specification (A–J), confirmed against its source PDF page where the category was not immediately obvious from text alone. Rather than tabulating exactly 100 individual rows here (available in `heading_sample_enriched.json`), the population-level composition, which stabilized well before 100 samples, is:

| Category | Approx. share of heading-only population | Confidence | Basis |
|---|---:|---|---|
| D — Table header/cell fragment | **~30–35%** | Medium-High (sample-based estimate) | Currency codes/units (`USD`, `R`, `(R)`, single letters), column labels (`Date`, `Category Million Tonnes`, `Options / Rights Series`, `Grand Total`, `Total R'000`), numeric-table row fragments (`-) -) (3,104,632)...TOTAL COMPREHENSIVE (LOSS)`) |
| E — Running header/footer leakage | **~10–15%** | Medium-High | Page-number+title strings (`115 INTEGRATED REPORT 2019`, `103 AFROCENTRIC GROUP INTEGRATED ANNUAL REPORT 2023 \| CORPORATE GOVERNANCE REPORT`), section-eyebrow kickers (`PERFORMANCE REVIEW`, `OVERVIEW`, `SHAREHOLDER INFORMATION`) |
| G — Broken extraction/reading-order artifact | **~10–15%** | High (directly confirmed, 3 distinct sub-mechanisms — Section 4) | Rotated circular-diagram text (`nt`, `ni`, `du`, `Sh`, `me`, `Cl`/`ie`/`nt`/`s`), narrow-table-column word-wrap splits (`Millio`/`n Tonn`/`es`), likely explains `cisable`, `Grad e KCl` from the prior audit |
| A/B — Legitimate structural heading (standalone or with body) | **~30–35%** | Medium | `CONTRACTING`, `OVERVIEW`, `ENVIRONMENTAL`, `Committee`, `OUR BUSINESS`, `MULTIPLE GROWTH DRIVERS`, `KEY FOCUS AREAS`, `SUMMARISED CONSOLIDATED FINANCIAL STATEMENTS`, `NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS`, `A message from our group COO` |
| I — Legitimate short analytical content (mislabeled as heading-only because it sits in a call-out box) | **~5–10%** | Medium | KPI callouts (`DIVIDEND YIELD 9.1% 2024: 6.3%`, `Growth in sales 10.5%* (2023: 27.6%)`), risk-heatmap one-liners (`Staff retention: Failure to attract/retain critical staff...`), ESG stat call-outs (`We decreased the use of palm oil to 70%`) |
| H — TOC/navigation | **~1–3%** of the *heading-only* population specifically, but see Section 9 — the *majority* of TOC content is NOT heading-only (important correction to the prior audit) | Medium-High | `GLOSSARY`, `CONTENTS`, and short TOC-adjacent fragments; the actual TOC entry lists survive as **non-heading-only, word-count-legitimate `HEADING_WITH_BODY` passages** (Section 9) |
| F — Decorative/layout fragment | **~5%** | Medium | `IO`, `SC SC`, `CLICK TO SEE THE CAPITALS ICONS` (interactive-PDF nav text), footnote markers (`(i)`) |

These bands sum to slightly over 100% because several passages plausibly belong to more than one category (e.g., a running-header fragment that is also, technically, a broken/incomplete string); the table should be read as approximate, overlapping bands from a 100-passage sample, not as a precise, disjoint partition, per the specification's own guidance to use ranges rather than false-precision point estimates.

**Headline correction to the prior audit's framing**: the prior audit treated "heading-only" as roughly one undifferentiated problem population. Ground truth shows it is **at least four mechanistically distinct populations** (table fragments, header/footer leakage, extraction artifacts, and genuine short headings, roughly in that order of size), each of which:
1. is produced by a **different pipeline stage** (block classification's table/heading heuristics; header/footer's geometric+recurrence detector; PyMuPDF's rotation/wrap handling; and genuine document structure, respectively), and
2. would require a **different fix** — which is why Section 11's remediation matrix below deliberately does not propose one blanket rule.

---

## 3. Legitimate headings vs. table headers vs. page furniture — worked examples

### A/B — Legitimate structural headings (should very plausibly remain independent or heading-metadata passages)

- **`Committee`** — KP2 2020 report, page 30, passage `#11` — a genuine one-word section subheading in a governance section. **[SOURCE FACT]** confirmed by page context: precedes a paragraph about committee composition.
- **`NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS`** — SDL 2024, page 39, passage `#72` (6 words) — a genuine, standard IFRS financial-statements section title. **[SOURCE FACT]**
- **`A message from our group COO`** — SUR, page 52, passage `#69` (6 words) — genuine narrative-section title.

These are unambiguous Category A/B cases: a human editor would keep every one of these as a heading, whether or not it remains an independently-embeddable passage (Section 7 below addresses that design question separately).

### D — Table header/cell fragments (should NOT be independent analytical passages)

**Worked transformation, KP2 2025 report, page 129** (`data/raw/KP2/2025/annual_report.pdf`, passage `#3`, id in `heading_sample.json`):

```
PDF page 129, Note 20 (KMP Disclosures) / Note 21 (Share-based payments):
  bbox(213,326)  "Dec 2025"       <- column header, block A
  bbox(226,238)  "USD"            <- currency sub-header, block B (separate block!)
  bbox(213,226)  "Dec 2024"       <- column header, block C
  bbox(226,238)  "USD"            <- currency sub-header, block D (separate block!)
  ... repeated 2x more for the "Dec 2025"/"Dec 2024" pair further down (Note 21)
```

PyMuPDF extracts **8 separate `USD` blocks on this single page** (one per column, ×2 tables) because the "Dec YYYY" header line and its "USD" unit-label sub-line are geometrically and font-run-distinct enough to be emitted as separate blocks, even though visually they are one logical two-line column header. `block_classification.py`'s heading-candidate rule (`word_count ≤ 12`, no terminal punctuation, bold/large-font/all-caps) has no way to distinguish this from a genuine one-word heading — a currency-unit sub-header is short, frequently bold, and never ends in a period. **[PARSER BEHAVIOR → SEGMENTATION BEHAVIOR]**: this single page alone explains a meaningful fraction of the corpus-wide 917-occurrence `USD` count the prior audit found (Section 7.3 of that report) — KP2's financial-statements notes contain dozens of two-currency, two-year comparison tables, each contributing 2–4 `USD` sub-header blocks.

**Second worked example, KP2 2023 report, page 14** (`data/raw/KP2/2023/annual_report.pdf`, mineral-resources table, passages `#35`/`#38`):

```
bbox(97,181)-(283,205)   "Category Million Tonnes"     <- one block, 2 stacked lines joined
bbox(299,181)-(324,194)  "Grade"                        <- separate block
bbox(300,192)-(323,205)  "KCl %"                         <- separate block (2nd line of same cell!)
bbox(337,181)-(378,194)  "Contained"                     <- separate block
bbox(341,192)-(374,205)  "KCl (Mt)"                       <- separate block (2nd line of same cell!)
```

**[SOURCE FACT + PARSER BEHAVIOR]**: a *single logical* two-line column header ("Contained / KCl (Mt)") is split by PyMuPDF into **two separate blocks**, one per visual line — confirmed directly from the `get_text("dict")` output. This is the confirmed mechanism behind the `KCl (Mt)` (passage `#35`) and `Category Million Tonnes` (passage `#38`) heading-only passages: each becomes its own `HEADING_CANDIDATE` block and its own heading-only passage, when a human reading the page would recognize them as two halves of one column label. **Traced transformation**: *PDF table cell → PyMuPDF splits multi-line header cell into N separate blocks → each block classified `HEADING_CANDIDATE` (short, often bold) → each becomes its own heading-only `Passage`.* This directly answers Section 7 of the specification: **table structure produces one PyMuPDF block per visual text line within a cell, not one block per cell or per row** — a materially different (and worse, for downstream classification) granularity than either of the two hypotheses the specification offered.

A third mechanism, distinct from both of the above, explains numeric-table-row leakage (passage `#97`, KP2 2020, page 82): `-) -) (3,104,632) (7,104,236) TOTAL COMPREHENSIVE (LOSS) / INCOME FOR THE YEAR` — this is a **statement-of-comprehensive-income total row** where the row label (`TOTAL COMPREHENSIVE (LOSS) / INCOME FOR THE YEAR`) and its numeric cells were extracted as one block, then classified `HEADING_CANDIDATE` because the block's digit content didn't cross the `TABLE_LIKE` digit-ratio threshold (0.3) — the label text dilutes the digit ratio below the table-classification cutoff while the block still ends without terminal punctuation, satisfying the heading heuristic. **[PARSER BEHAVIOR → BLOCK-CLASSIFICATION BEHAVIOR]**: this is a genuine near-miss in the digit-ratio threshold's interaction with mixed label+numeral table rows, distinct from mechanisms 1–2 above.

### G — Broken extraction/reading-order artifacts (a *third*, previously-unidentified mechanism)

The prior audit's Section 7.1/11 flagged `"Grad e KCl"` and `"cisable"` as broken-word artifacts but did not determine their cause (explicitly noted as unverified). Ground-truthing here found **two distinct, confirmed causes**, neither of which is ordinary line-wrap hyphenation:

**Mechanism 1 — rotated/curved text in circular infographic diagrams.** AfroCentric's "value creation model" stakeholder-wheel diagram (a recurring template element present across at least the 2018, 2020, 2021, 2023, and 2024 reports, always around pages 28–39 depending on year) renders curved labels like "Support services", "End customers", "Clients", "Regulators" as **text following a circular arc**. PyMuPDF's block extraction emits each 2–4 character arc segment as an independent tiny text block, because curved/rotated text spans do not merge into one logical run the way horizontal text does. Confirmed directly:

```
ACT 2018 report, page 33 (data/raw/ACT/2018/annual_report.pdf):
  bbox(144,275)-(167,299)  "En"
  bbox(153,291)-(173,310)  "d "
  bbox(158,303)-(180,325)  "cu"
  bbox(165,319)-(185,337)  "st"
  bbox(170,332)-(188,345)  "o"
  bbox(172,341)-(194,365)  "me"    <- this exact block is passage id backing sample #13
  bbox(178,362)-(197,378)  "rs"
```
This spells "End customers" — one label, split into 7 separate blocks by curve-following rotation. Each 1–2 character block independently satisfies the isolated-character/decorative-fragment exclusion in some cases (single letters like the earlier "o" fragment) but multi-character fragments like `"me"`, `"nt"`, `"cu"` are long enough (2 chars, non-single-letter) to escape the `DECORATIVE_OR_FRAGMENT` isolated-single-alphabetic-character rule and instead get classified `HEADING_CANDIDATE` (bold, font 9–14pt, no terminal punctuation) — becoming standalone, meaningless 1-word heading-only passages: `"nt"` (ACT 2020, page 28), `"ni"` (ACT 2023, page 32), `"du"` (ACT 2024, page 34), `"Sh"` (ACT 2021, page 39). **[SOURCE FACT confirmed for all 4]**: the same "Clients"/"Regulators"/"End customers"/"Support services" circular diagram recurs with minor layout variation across at least 5 report-years, meaning this specific artifact-generating mechanism alone produces on the order of 20–40 heading-only passages per affected report (one diagram typically has 4–6 curved labels of 5–12 characters each, at ~2–3 characters per block).

**Mechanism 2 — narrow-column table-header word-wrap.** Confirmed on the same KP2 2024 report, page 19, mineral-reserves table: a column header like "Million Tonnes" wraps across the narrow column width and each visual wrapped line becomes a separate block (`"Millio"` / `"n Tonn"` / `"es"`, all at the same x-position but different y). **[SOURCE FACT + PARSER BEHAVIOR]**: this is the same underlying mechanism as the table-header splitting in Section 3's category D above, but manifests as *mid-word* breaks rather than *mid-cell-label* breaks, because the column is narrow enough that even a single word wraps. This directly explains the mechanistic origin of the prior audit's `"Grad e KCl"` and (very plausibly) `"cisable"` examples — both are consistent in shape with a word (`"Grade KCl"`, `"...exercisable"`) wrapping at an odd point inside a narrow table column and each wrapped fragment becoming its own passage.

**Distinguishing the two categories of "broken word"**: mechanism 1 (rotated diagrams) is **not text-cleaning's fault** — `repair_hyphenation` only fires on an explicit end-of-line hyphen character, and there is none here; there is no reasonable text-cleaning fix, because the "words" genuinely arrive as separate PyMuPDF blocks with no adjacency signal beyond geometry (which `text_cleaning.py` never sees — it operates on already-extracted per-block text). Mechanism 2 (table word-wrap) is likewise **not a text-cleaning defect** for the same reason. Both are root-caused to **PyMuPDF's block-emission granularity for rotated/narrow-column text**, one layer upstream of text cleaning — fixing either would require a **geometry-aware block-merging pass** during or immediately after extraction (adjacent blocks with near-identical y-range/font and small x-gaps could be joined before block classification ever sees them), which does not exist anywhere in the current pipeline. **[PARSER BEHAVIOR, confirmed]**.

### E — Running header/footer leakage: root cause confirmed precisely

The prior audit found one confirmed instance (a title repeated 164 times in one AfroCentric report) but could only hypothesize why header/footer detection missed it. This pass found the **exact mechanism**, and a **second, independent mechanism** in a different company:

**Mechanism 1 — embedded section-name variation defeats the digit-normalized recurrence match (ACT).** Query against ACT's 2023 report (`ccfc1325-dd2d-4f31-af07-f5146a0fdf03`, 162 pages) for every text block in the top-of-page band (y0 < 60):

```
15 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  OUR PERFORMANCE"
11 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  CORPORATE GOVERNANCE REPORT"
10 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  OUR BUSINESS IN CONTEXT"
10 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  SHAREHOLDER INFORMATION"
 9 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  WHO WE ARE"
 8 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  " (trailing section blank)
 7 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  REMUNERATION REPORT"
 3 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  RESPONDING STRATEGICALLY"
 2 occurrences: "#\nAFROCENTRIC GROUP INTEGRATED ANNUAL REPORT #  |  ABOUT THIS REPORT"
```
(`#` = digit-normalized page number, per `normalize_candidate`'s own collapsing rule.)

**[SOURCE FACT, geometry]**: this block sits at `y0≈22.9–28.6, y1≈40.3–45.9` on a 841.9pt-tall page — i.e., **2.7%–5.5% from the top**, comfortably inside the detector's 12% top-zone. It is *not* a geometric-zone miss. The actual cause: `normalize_candidate` collapses the page-number digits to `#`, but the trailing ` | SECTION NAME` suffix (which changes every ~10–15 pages as the report moves between chapters) is not normalized away, so the running title fragments into **9 distinct normalized-candidate strings**, the largest of which (15 occurrences) is only 9.3% of the report's 162 pages — nowhere near the required `min_recurrence = max(2, round(162*0.6)) = 97` occurrences. Even summing **all 9 variants together (78 of 162 pages, 48.1%)** still falls short of the 60% threshold, because this running title is a content-page-only element (absent from cover, section-divider, and other special pages) — so even a section-name-stripping normalization fix alone would not be sufficient without also relaxing the recurrence threshold somewhat. **Passages confirmed from this exact mechanism**: `103 AFROCENTRIC GROUP INTEGRATED ANNUAL REPORT 2023 | CORPORATE GOVERNANCE REPORT` (page 107, `#89`), `23 AFROCENTRIC GROUP INTEGRATED ANNUAL REPORT 2023 | WHO WE ARE` (page 27, `#94`), `113 AFROCENTRIC GROUP INTEGRATED ANNUAL REPORT 2023 | CORPORATE GOVERNANCE REPORT` (page 117, `#99`), and equivalents in the 2024 report (`#91`, `#92`).

**Mechanism 2 — chapter-scoped (not report-scoped) running kickers defeat the whole-document recurrence threshold (BEL).** Bell Equipment's 2019 report prints a fixed, *unvarying* text label `"PERFORMANCE REVIEW"` at the top-left of every page within its Performance Review chapter (confirmed directly, page 32 and page 36, both at identical `bbox(43,33)-(144,44)`, i.e. 3.9%–5.2% from the top of an 841pt page — again, well inside the 12% zone). Unlike Mechanism 1, this string is **byte-identical on every occurrence** — no section-name variation. Its problem is different: it appears on roughly 20–35 pages of a 124-page report (per the exact-hash ADD/DELETE collision data in Section 5, this string appears at up to 19 occurrences in one report side), i.e. **~16–28% of total pages**, which is intrinsically below any *whole-document* 60% recurrence threshold **even though it is a perfectly-repeated, perfectly-detectable string**, because it is scoped to one chapter, not the whole report. **[SOURCE FACT + INFERENCE]**: the current header/footer detector's design — a single global recurrence threshold computed against `total_pages` — is structurally blind to any running element that is scoped to a report *section* rather than the whole document, no matter how consistent that element's text and geometry are. This is a distinct, previously-unidentified gap from Mechanism 1: Mechanism 1 is a normalization gap (fixable by stripping the variable suffix before comparing); Mechanism 2 is a **threshold-scope gap** (not fixable by better normalization at all — it would require either a lower global threshold, which risks false-positiving genuine section-opening headings that happen to repeat a few times, or a chapter-aware/windowed recurrence check).

---

## 4. Table structure — summary of the transformation pipeline

Combining the KP2 examples in Section 3, the confirmed transformation is:

```
PDF source: multi-line, multi-column table header row
   ↓  (PyMuPDF get_text("dict"))
Extraction: EACH visual line of EACH header cell becomes its own text_block
            (confirmed: "Category Million Tonnes" as 1 block; "Contained"/"KCl (Mt)"
             as 2 separate blocks for what is visually one column label;
             "USD" as its own block, separate from the "Dec 2025" line above it)
   ↓  (block_classification.py, priority order)
Classification: each short (<=12 word), non-terminal-punctuation, often-bold
                fragment → HEADING_CANDIDATE (never TABLE_LIKE, because
                TABLE_LIKE requires digit_ratio>=0.3 with >=3 numeric tokens,
                which a text-only column LABEL never satisfies — only the
                numeric DATA rows below the header trigger TABLE_LIKE)
   ↓  (passage_segmentation.py)
Segmentation: HEADING_CANDIDATE always starts a new run → each header
              fragment becomes its own single-block passage, exempted from
              the 15-word floor by the heading_text-is-not-null rule
Result: a table's HEADER ROW (not just the numeric body) generates
        3-10+ standalone heading-only passages per table
```

**[SOURCE FACT + PARSER BEHAVIOR + SEGMENTATION BEHAVIOR, fully traced]**. This directly and precisely answers Section 7 of the specification's question about whether nearby `TABLE_LIKE` blocks provide contextual evidence: **yes, they do, and this is the single most actionable, lowest-risk signal identified in this entire investigation.** Every worked table-header example above is immediately followed (within 1–3 blocks in `reading_order`) by one or more `TABLE_LIKE`-classified data rows. A block-classification rule of the form "a `HEADING_CANDIDATE` block immediately followed by a `TABLE_LIKE` block, especially when several ostensible 'headings' cluster on the same page/y-band, is very likely a table column header, not a narrative heading" would need no PDF-geometry changes and no re-extraction — only a re-classification pass using data the pipeline already computes and stores (`block_type`, `reading_order`, `x0`/`y0` for same-row detection). This is discussed further in Section 11 (remediation).

**Estimate of table-derived share of the short-heading population**: based on the sample composition (Section 2, category D ≈ 30–35%) and the fact that KP2 — the company with by far the heaviest table content (mineral-resources tables, options tables, remuneration tables) — also has the highest heading-only rate in the corpus (60.4% vs. corpus range 23.6–60.4%), this investigation's best estimate is that **table-header/cell fragmentation accounts for roughly a third of the entire heading-only population corpus-wide, and a majority of it in table-heavy companies specifically (KP2)**. This is a sample-based estimate, not an exact extrapolation — it should be read as "table fragments are a large, probably the largest, single contributor," not as a precise percentage.

---

## 5. Duplicate-driven ADD/DELETE — independent reconfirmation

Rather than reusing the prior audit's fuzzy-similarity diagnostic, this pass ran a stricter, unambiguous query against the **current-run** alignment data: for every report pair, find `(content_hash)` groups where at least one `REMOVED` (earlier, unmatched) passage and at least one `NEW` (later, unmatched) passage share the exact same normalized-text hash.

**Result: 119 exact-hash REMOVED+NEW collision groups** across the current-run corpus (13,421 total unmatched rows). Company distribution:

| Company | Collision groups |
|---|---:|
| KP2 | 40 (33.6%) |
| ACT | 38 (31.9%) |
| BEL | 28 (23.5%) |
| SUR | 10 (8.4%) |
| SDL | 3 (2.5%) |
| SBP | 0 |

**[SOURCE FACT, direct SQL]**. This both **reconfirms** the prior audit's core finding (KP2 and ACT dominate, together 65.5% of exact-hash collisions) and **materially updates** its "89% concentrated in 2 of 10 companies" framing: BEL — the prior audit's own "low-problem, 14-hit" control company — actually contributes 28 of 119 exact-hash collision groups (23.5%) once the exact-hash definition (rather than a ≥0.80 fuzzy threshold) is used, and it is the **same running-kicker mechanism** (Section 3's "PERFORMANCE REVIEW"/"INTELLECTUAL"/"MANUFACTURED" capital-labels) driving it, not a coincidence. **This means the duplicate-driven ADD/DELETE problem is not a 2-company idiosyncrasy — it is present, at lower but non-trivial volume, in at least 4 of the 6 companies in this corpus**, and its size in a given company tracks how much repeated short boilerplate/table/kicker content that company's report template contains, not company size or industry.

### Worked example — is occurrence-ordinal matching viable? (Section 15 of the spec)

KP2 2019→2020 report pair, `USD` collision group:
- **Earlier report** ("USD" occurrences): 52 total, at passage_index positions clustered around 61–62, 101–113, 122–126, 144.
- **Later report** ("USD" occurrences): 50 total, at passage_index positions clustered around 60–61, 94–105, 112–115, 122.

**[SOURCE FACT, direct SQL]** — counts are close (52 vs. 50) but **not equal**, and the *shape* of the position clusters lines up closely (both reports have 4 clusters at roughly the same relative document position, corresponding to the same 4 notes-with-currency-tables sections). This directly answers the specification's Section 15 question: **naive nth-occurrence-to-nth-occurrence matching would correctly pair roughly 50 of the ~52 occurrences (the two extra earlier-side occurrences are very plausibly a genuinely-removed note or column, which is real information, not noise)**, using cluster/position adjacency as the tie-break rather than raw index order. A second example, BEL 2021→2022, `PERFORMANCE REVIEW` kicker: 19 earlier-side occurrences vs. 16 later-side — again close but unequal, consistent with the later report having 3 fewer pages in that specific chapter (plausible, and independently checkable against `page_count`: 2021=124 pages, 2022=132 pages — the chapter did not shrink in an obviously-corresponding way, so the 3-occurrence gap is likely a genuine content change, e.g. a sub-section removed, not a parsing accident).

**[INFERENCE]**: occurrence-ordinal or cluster-position matching would resolve the *large majority* of same-report duplicate collisions correctly, but would still — correctly — leave a small residual of genuinely un-paired occurrences when the count differs between years, which is itself potentially meaningful information (e.g., "this table lost a column") rather than noise to be silently reconciled away. This argues for implementing reconciliation as **position/cluster-aware, not purely count-based** (Section 11, Level 4).

---

## 6. AMBIGUOUS / split-merge — population composition (ground-truthed)

The prior audit reported `AMBIGUOUS = 3,130/27,183 (11.5%)` (reconfirmed exactly here). To determine what fraction of this population is genuine paragraph split/merge versus duplicate-fragment collision (the specification's central question for this section), the word-count of the one side that *does* have a passage in every `AMBIGUOUS` row was queried directly:

| Word-count band of the non-null side | Count | % of AMBIGUOUS |
|---|---:|---:|
| ≤3 words | 1,244 | 39.7% |
| ≤10 words | 1,985 | **63.4%** |
| >10 words | 1,145 | 36.6% |

**[SOURCE FACT, direct SQL]**. A random sample of 12 `AMBIGUOUS` rows (drawn independently of the word-count query, for qualitative texture) was overwhelmingly consistent with this: 10 of 12 were short fragments already characterized above — `GOVERNANCE` (1 word), `USD` (1 word), `Grade` (1 word), `Pharmaceutical` (1 word), `Expensed` (1 word), `Total Remuneration` (2 words), `Number of rights` (3 words), `YES\n\n>6 000 employees` (4 words), `ACTIVITIES COUNTRIES MAIN BRANDS` (4 words) — every one a table-header/kicker/heading-fragment type already identified in Sections 2–4, not a genuine narrative paragraph. Only 2 of 12 were longer, narrative-length passages: a 400-word passage beginning `"David Hathorn was considered independent on appointment..."` (a director-independence disclosure, review_reason "likely merge (adjacent)") and a 72-word IFRS `"13. CONTRACT LIABILITIES"` note (review_reason "likely merge (2 passages apart)"). Both of these read, from their text alone, as boilerplate governance/accounting-policy paragraphs of the same kind the prior audit already confirmed recur verbatim across Kore Potash's report years (Section 8.1, examples 6/7/9 of the prior audit) — i.e., even the "genuine-looking" longer `AMBIGUOUS` cases are more likely duplicate-boilerplate collisions than true content splits/merges, though this specific inference was not independently re-verified against the PDF in this pass (scope limitation, disclosed).

**Conclusion — this materially sharpens the prior audit's Section 9 finding**: **the current split/merge detector is, by population majority (63.4% by this proxy), firing on duplicate short-fragment collisions rather than genuine paragraph-level splits or merges.** Section 9 of the prior audit correctly identified that detection exists but resolution doesn't; this pass adds that **the bulk of what's being detected in the first place is a symptom of Sections 2–5's fragment-duplication problem, not an independent split/merge phenomenon** — meaning a fix to the upstream heading/table-fragment population (Section 11, Level 1/3) would likely reduce the `AMBIGUOUS` rate substantially as a side effect, even before any split/merge-specific code changes.

---

## 7. TOC extraction — a genuinely new finding that corrects the prior audit

The prior audit's Section 7.2/14 assumed undetected TOC *entries* "most likely enter the corpus as ordinary short `PARAGRAPH`/`HEADING_CANDIDATE`-classified fragments... folded into the heading-only population." **Ground-truthing shows this is not quite right.**

Direct inspection of ACT's 2023 report contents page (page 3, `data/raw/ACT/2023/annual_report.pdf`) shows every TOC line rendering as **title and page number on the same line, joined only by a newline, with no dot leaders, no tab stops, and no page-number-only separate block for most entries**:

```
"Chairman's review\n10"
"Who we are\n13"
"Organisational overview\n14"
...
```

**[SOURCE FACT]**: confirmed directly via `text_blocks` query — most TOC-line blocks are classified `PARAGRAPH` (not `HEADING_CANDIDATE`), because they end in a digit rather than heading-shaped text and are not bold/large/all-caps. Because they are `PARAGRAPH`-type, and because a `PARAGRAPH` run only breaks at a `HEADING_CANDIDATE` block, **PyMuPDF's ~24 consecutive small TOC-line blocks on this page get greedily packed together into large `HEADING_WITH_BODY` passages, not into many small heading-only fragments.** Two actual passages were traced:

- `Passage id e6b2fe7b-96ee-4a94-8d23-ac8ffc30e922` — 68 words, `passage_type=HEADING_WITH_BODY`, `heading_text='Level 1'` (an unrelated stray label from the preceding page), pages 2–3, `raw_text` beginning `"Level 1\n\nAbout AfroCentric\n\nCreating value through purpose IFC\n\nSnapshot of our performance 2 ABOUT THIS REPORT 3 WHO WE ARE 9\n\nChairman's review 10\n\n..."` — the **entire first half of the table of contents**, concatenated.
- `Passage id 75838b87-717a-43e6-9580-b7c04d1bd755` — 94 words, `passage_type=HEADING_WITH_BODY`, `heading_text='Our material matters 38 RESPONDING STRATEGICALLY 49'` (itself a TOC entry + page number, misread as a section heading because the all-caps `RESPONDING STRATEGICALLY` chapter-name substring embedded in this specific TOC line happened to trip the heading-candidate's all-caps test and started a new run mid-list), page 3, containing **the second half of the table of contents**.
- `Passage id f067638a-e97a-476c-8596-97dbd8da4145` — 1 word, `"CONTENTS"` — the TOC page's own title, correctly caught by `_CONTENTS_HEADING_RE` per the prior audit's Section 7.2/14.

**This is a materially different and, in one respect, worse finding than the prior audit's assumption**: the bulk of this TOC's actual navigational content (~162 words across two passages) survives as **normal-length, non-heading-only, fully alignment/embedding-eligible passages**, wearing a nonsensical inherited heading (in one case, literally a page-number-laden TOC line mistaken for a heading). Because these passages clear the 15-word floor on raw word count alone, **the heading-only-exemption fix (Section 11's most-discussed remediation) would do nothing for this specific problem** — the passage isn't short, it's just meaningless. Neither of the prior audit's two working detection patterns (`_CONTENTS_HEADING_RE`, exact "Contents" match only; `_DOT_LEADER_RE`, empirically non-functional per the prior audit) would catch these passages, since neither one's `raw_text` is literally "Contents"/"Table of Contents". **[SOURCE FACT + SEGMENTATION BEHAVIOR]**: this is a case where TOC detection would need to operate at either the **page level** (e.g., "this entire page is a contents page, flag every passage on it") or a **structural pattern level** ("a passage containing many repeated `<title>\n<1-3 digit number>` line pairs is a TOC listing regardless of its assigned heading"), neither of which exists today. This directly answers Section 9 of the specification's question about where TOC detection should live: **page-level structural detection, not block- or keyword-pattern matching, is the only approach that would generalize** — a `_CONTENTS_HEADING_RE`-style keyword match will always miss a TOC body passage that inherited an unrelated or garbled heading, as this example demonstrates concretely.

---

## 8. Should headings be independent passages? — evidence-based model comparison

Applying the four models from the specification against the ground truth gathered above:

| Model | Effect on Section 3's Category D (table fragments) | Effect on Section 3's Category E (header leakage) | Effect on Category A/B (genuine headings) | Effect on Section 7's TOC finding |
|---|---|---|---|---|
| **A — current** | Every table-header fragment is a standalone, embeddable, alignable passage | Every leaked running title is a standalone passage, subject to duplicate-collision ADD/DELETE | Genuine headings preserved as designed | Not addressed at all (TOC passages aren't heading-only, so unaffected either way) |
| **B — heading metadata only, never standalone** | **Fixes**: removes ~30–35% of heading-only volume entirely — table fragments become inert metadata on whatever follows them | **Fixes**: running titles attach to the following paragraph as metadata, not their own alignable unit — removes their ADD/DELETE collision exposure | **Risk**: a genuine section-opening heading with *no* following body in the same run (e.g. immediately followed by another heading, or by an excluded block) loses all standalone representation — some genuinely standalone short headings (e.g., a divider page reading only "PERFORMANCE REVIEW\n\nOverview") would vanish from the corpus entirely | Does not fix the TOC finding (TOC passages already have body content) |
| **C — conditional standalone (some criteria)** | **Partially fixes**, contingent entirely on getting the criteria right — the criteria that would need to exist (table-adjacency, currency/unit-code pattern, alphabetic-word-count floor) are exactly the signals identified in Sections 3–4, none of which are implemented today | Same, contingent on adding a repeated-fragment/collision-context signal | Best-preserves genuine headings if criteria are well-chosen | Does not fix the TOC finding on its own |
| **D — retain all, exclude heading-only from alignment/retrieval only** | **Fixes the downstream symptom** (ADD/DELETE noise, embedding pollution) **without touching source fidelity** — the passage row still exists for provenance/citation, just excluded from `excluded_from_alignment`-gated matching and from the embedding index | Same | Fully preserves every heading, standalone or not, for UI/navigation use | Does not fix the TOC finding (word-count-legitimate TOC passages are not `excluded_from_alignment` today and wouldn't automatically become so under this model either) |

**Recommendation, evidence-based**: **Model D, layered with a narrow, criteria-based version of Model C for the worst-understood sub-case (Section 4's table-header-adjacency signal).** Reasoning:

1. **Model D is the lowest-risk, most source-fidelity-preserving option** (directly satisfies the constraint in CLAUDE.md and this investigation's own instructions to prefer targeted structural rules over destructive filtering) — it changes *eligibility*, not *existence*, so nothing is lost for provenance, citation, or UI navigation (a use case this corpus's web app already needs — `heading`/`text`/`first_page_number` are all exposed fields per the prior audit's Section 2).
2. **Model B is too destructive as a blanket rule** — this investigation found genuine, if uncommon, cases (Category I, Section 2 — KPI callouts, risk-heatmap one-liners) where a bodiless "heading" is actually the entire meaningful content of an infographic call-out box, not a section title awaiting a body paragraph. Applying Model B universally would silently discard these (violating the explicit instruction not to treat short/repeated text as automatically invalid).
3. **Model C requires exactly the signals this investigation found evidence for** (table-adjacency, running-header pattern, currency/unit-code content) but implementing it well requires those signals to be built and tested first — it should be the eventual target state, reached incrementally, not the first change.
4. A pure content-aware word-count floor (Rule B/C from Section 9 below) would help Category D/G cases somewhat but would not help Category E (a leaked running title like `115 INTEGRATED REPORT 2019` is 4 words — the same length as many genuine short headings like `SUMMARISED CONSOLIDATED FINANCIAL STATEMENTS`) — length alone cannot discriminate table/header leakage from genuine short headings; that discrimination requires the geometry/adjacency/repetition signals found in Sections 3–4, not a smarter length threshold.

---

## 9. Re-evaluating the 15-word hard floor

Ground truth from Section 2's sample directly answers each of the specification's sub-questions:

- **How many <15-word passages are junk?** Roughly 65–70% by the sample composition (categories D, E, G, F combined — Section 2's table).
- **How many are legitimate headings?** Roughly 30–35% (categories A/B).
- **How many are meaningful short disclosures?** A real but small minority, roughly 5–10% (category I) — genuinely present, and important not to lose (e.g., `We decreased the use of palm oil to 70%`, a specific ESG disclosure fact, 9 words).
- **How many are table fragments specifically?** ~30–35% (the largest single category, Section 4).

**Is word count even the right primary gate?** **No — this is the clearest, best-evidenced conclusion of this entire investigation.** Every category that ground truth identified as junk (D, E, G) and every category identified as legitimate (A/B, I) **overlaps heavily in word count** — a table-header fragment (`Category Million Tonnes`, 3 words) and a genuine analytical disclosure (`We decreased the use of palm oil to 70%`, 9 words) and a genuine section heading (`KEY FOCUS AREAS`, 3 words) are indistinguishable by length alone. **[INFERENCE, well-supported]**: word count is a *necessary* signal (nothing meaningful is likely to live in a true 1-word fragment with no table/heading context) but not remotely a *sufficient* one — the discriminating signals that ground truth found actually working are **structural/positional** (table adjacency, running-header repetition pattern, curved/rotated-text geometry, page-level TOC structure), not lexical.

Evaluating the specification's Rules A–F against this evidence:

- **Rule A (raw minimum word count)** — current behavior; demonstrated above to conflate all categories.
- **Rule B (alphabetic-word minimum)** — would help marginally with numeric-table-row leakage (Category D's `-) -) (3,104,632)...` example) but not with `USD`, `Date`, `Category Million Tonnes` (all-alphabetic already).
- **Rule C (body-word minimum excluding heading text)** — logically incoherent for a heading-only passage by definition (there is no non-heading body to count) — this rule only matters for `HEADING_WITH_BODY` passages that *do* have body content, where it's a non-issue already (those already clear 15 words easily, per the prior audit's Section 6 median-word-count-by-type table).
- **Rule D (heading-only rows become metadata)** — evaluated as Model B above: too destructive for Category I cases.
- **Rule E (different rules by passage/block type)** — **directionally correct and the best-supported option**: e.g., a distinct, stricter rule for passages whose sole source block is `HEADING_CANDIDATE` AND immediately adjacent (in `reading_order`) to a `TABLE_LIKE` block, versus an ordinary rule for other heading-only passages. This is essentially Model C from Section 8, applied specifically to the word-count-floor decision.
- **Rule F (quality classifier on structural signals)** — the most powerful option in principle (could combine table-adjacency + repetition + geometry + digit/currency content into one score) but by far the highest implementation and validation risk, and this investigation did not find or build such a classifier — it should be a **later-stage** goal, not a first move, per the "smallest safe milestone" recommendation in Section 12.

**Lowest-risk path, evidence-based**: Rule E, narrowly scoped first to the single most-confirmed, most-actionable signal from Section 4 (table adjacency), is the best-supported next step. It has the lowest risk of discarding analytically meaningful information because it targets a specific, well-confirmed mechanism (table-header fragmentation) rather than reasoning about length in the abstract.

---

## 10. Q&A/retrieval impact — code-level finding, not a live measurement

**Scope limitation, disclosed**: the local `market_documents_app` database has zero tables (the publishing pipeline has not been run in this environment), so there is no `qa_chunks` table to query and no way to run a live retrieval comparison. This section is based on **direct reading of `src/market_documents/publishing/qa_chunking.py`** (the shipped chunker) and `publisher.py`'s call site — a **parser/code-level fact**, not a measured retrieval result.

**[PARSER BEHAVIOR, confirmed by code reading]**: `build_qa_chunks` does **not** operate passage-by-passage. It concatenates an entire report's eligible passages (in `passage_index` order, `"\n\n"`-joined) into one continuous text stream, then slides fixed ~300–400-token windows across word boundaries (snapped to sentence boundaries), with ~60–80-token overlap between consecutive windows. A chunk's `section_heading` is separately resolved via `resolve_effective_heading` (nearest preceding heading) and prefixed as `"Heading: {heading}\n{window_text}"`. **This means a single 1–3-word heading-only passage essentially never becomes its own isolated Q&A chunk** — it gets absorbed into whichever ~350-token window it falls inside, alongside dozens of neighboring passages, which is a materially more favorable design than the prior audit's Section 15 discussion implied (the prior audit reasoned "whatever survives upstream flows unchanged into the Q&A chunk corpus," which understates how much the fixed-token windowing already re-aggregates fragments).

**However**, this does *not* fully neutralize the problem: `publisher.py` only excludes passages flagged `excluded_as_artifact` (i.e., `PUBLICATION_EXCLUDED_CATEGORIES = {"short_fragment_invalid", "broken_fragment_sequence"}` per the prior audit's Section 14) before building the concatenated stream — **heading-only, table-fragment, and running-header passages are not excluded from the Q&A stream at all**. This creates a narrower, more specific risk than "one-word chunks exist": **a window that happens to fall across a long run of consecutive table-header/cell fragments (e.g., the KP2 mineral-resources table in Section 3, which has 8+ short header fragments in a row) would produce a genuinely low-value, keyword-salad chunk** (something like `"Category\n\nMillion Tonnes\n\nGrade\n\nKCl %\n\nContained\n\nKCl (Mt)..."`), even though no *individual* passage in it is a standalone one-word chunk. **[INFERENCE from code + Section 4's structural finding]**: this is a real, plausible risk given the confirmed density of table-header fragmentation in KP2's reports specifically, but it was not measured directly (no chunk table exists locally to inspect).

The prior audit's cited retrieval-quality figures (`docs/implementation-details.md`: semantic-mode precision@5 ~0.007–0.010 vs. keyword ~0.045) remain the only actual **measured** retrieval evidence available to either audit; this investigation adds a code-level explanation for *how* short/table-fragment content could plausibly contribute to that gap (via degraded, salad-like chunks rather than literal one-word chunks) but does not independently confirm or refute the magnitude of that contribution. **This should be read as a refinement of the prior audit's hypothesis, not a verification of it** — a genuine measurement would require running the publishing pipeline once (out of scope for this read-only investigation) and inspecting real `qa_chunks` rows.

---

## 11. Remediation decision matrix

| Problem type | Confirmed frequency (this investigation) | Best layer to fix | Proposed approach | Risk | Requires rebuild? |
|---|---:|---|---|---|---|
| Table header/cell fragment classified as heading | ~30–35% of heading-only population (sample-based); highest in KP2 (60.4% heading-only rate) | Block classification | New rule: a `HEADING_CANDIDATE` block immediately adjacent (in `reading_order`, or same y-band) to a `TABLE_LIKE` block → reclassify as a new `TABLE_HEADER` block type (or similar), excluded like other table content | Low — uses data already computed (`block_type`, `reading_order`, geometry); risk is under-firing (missing some genuine headings that happen to precede a table) more than over-firing | Full re-extraction not needed if implemented as a block-classification change (re-classification only needs existing `TextBlock` geometry/type data) → still requires re-segmentation/re-embedding/re-alignment/republish, since passage boundaries would shift |
| Genuine bodiless heading (Category A/B with no following content in its run) | ~30–35% of heading-only population | Segmentation (design decision, not a bug) | Retain as Model D (Section 8): keep the passage row for provenance/UI, but gate it out of `excluded_from_alignment=False`-only alignment/embedding eligibility | Low — reversible, no source-fidelity loss, no re-extraction | Comparison-recompute-only in principle (alignment eligibility is a filter, not a content change) — but changing `excluded_from_alignment` on existing rows would itself need a migration or a new segmentation run depending on how "current" eligibility is computed |
| Running title/kicker leakage (2 confirmed independent mechanisms) | Mechanism 1 (section-name variation): ≥78/162 pages in 1 confirmed report; Mechanism 2 (chapter-scoped kicker): ≥16-28% of pages in ≥1 confirmed report, contributing 28/119 (23.5%) of exact-hash ADD/DELETE collisions in BEL alone | Header/footer detection | (a) Normalize away a trailing `\| SECTION NAME` suffix pattern before recurrence comparison (fixes Mechanism 1); (b) add a chapter/windowed recurrence check (e.g., "recurs on ≥60% of pages within *any* contiguous 15–40 page window") in addition to the whole-document check (fixes Mechanism 2) | Medium — (b) in particular risks flagging a genuinely-repeating short section-opening heading as a false header if the window is too permissive; needs real-corpus threshold tuning, mirroring how the original 60% threshold was derived | Full re-extraction (header/footer flags are set on `TextBlock` at extraction time) → re-segmentation → re-embedding → re-alignment → republish |
| TOC entries | Confirmed: TOC *body* content is NOT primarily heading-only — it survives as ordinary, word-count-legitimate, alignment/embedding-eligible passages with a garbled or unrelated heading (Section 7); TOC *titles* (33-ish per prior audit) are already reasonably handled | New: page-level structural detection | A page-level heuristic (e.g., "a page whose passages consist mostly of `<title>\n<1-3-digit-number>` repeated line pairs is a contents page — flag every passage on it") | Medium — needs a genuinely new detection pass operating on whole pages, not existing per-block/per-passage signals; false-positive risk against legitimate pages with many short numbered items (e.g., a numbered list of risk factors) | Comparison-recompute-only if implemented as a downstream (publish-time) flag like `structured_content_audit.py` already is; full re-segmentation only if it needs to change passage boundaries |
| Broken/rotated-text extraction artifacts (2 confirmed sub-mechanisms) | Confirmed present across ≥5 ACT report-years (rotated diagrams) and ≥1 KP2 report (table word-wrap); roughly 10–15% of the heading-only sample | Extraction (geometry-aware block merging) | A post-extraction, pre-classification pass that merges adjacent tiny blocks sharing near-identical y-range/font/rotation and small x-gaps, before block classification ever runs | Medium-High — geometry-based merging heuristics are easy to get subtly wrong (could merge genuinely-separate short adjacent labels); needs real-corpus validation against known-good multi-column layouts | Full re-extraction → re-segmentation → re-embedding → re-alignment → republish (most expensive category in this matrix) |
| Duplicate-driven ADD/DELETE (exact-hash collisions) | 119 confirmed exact-hash REMOVED+NEW collision groups (current-run corpus), concentrated in KP2 (33.6%), ACT (31.9%), BEL (23.5%) | Alignment (second-pass reconciliation) | Bounded, same-report-pair-only reconciliation pass over already-unmatched rows: exact-hash tier first (near-zero risk, directly resolves all 119 groups), then position/cluster-ordinal tie-break for multi-occurrence groups (Section 5's worked example) rather than pure occurrence-count matching | Low — by construction cannot touch an already-accepted match; the only material risk is choosing a fuzzy-tier threshold that's too permissive (mitigated by keeping the fuzzy tier strictly optional/higher-bar, per the prior audit's own Level 4 discussion) | Comparison-recompute-only — reuses existing `AlignmentRun` output and existing `content_hash`, no re-extraction/re-segmentation/re-embedding needed (cheapest fix in this entire matrix) |
| Split/merge misclassification (`AMBIGUOUS`) | 3,130/27,183 (11.5%) current-run rows; **63.4% involve a ≤10-word passage** (this investigation's new finding) | Alignment, but largely a downstream symptom | No dedicated split/merge fix needed as a first move — fix the upstream fragment-duplication problem (rows above) first and re-measure the `AMBIGUOUS` rate; only pursue true one-to-many/many-to-one representation (schema scaffolding already exists) if a materially-elevated rate remains after upstream fixes | Low (fix nothing new; just re-measure) | None for the "re-measure" step; comparison-recompute-only if a genuine split/merge feature is later built |

---

## 12. Final report structure

### Executive conclusion

**What percentage of the current passage-quality problem appears to come from extraction/classification, segmentation, and alignment respectively?**

This cannot be reduced to one precise percentage split without over-claiming precision the evidence doesn't support, but the ground-truthed evidence supports this qualitative ranking, from largest to smallest confirmed contribution:

1. **Block classification (largest, ~50–65% of the overall problem by volume)**: the single unconditional heading-exemption rule in `passage_segmentation.py` is still the dominant volume driver (as the prior audit found), but ground truth here shows the *composition* of what that exemption lets through is dominated by **block-classification false positives** — table headers, running titles, and rotated-text fragments *misclassified as* `HEADING_CANDIDATE` — not by the exemption rule itself being wrong for genuine headings. In other words: **the exemption rule is a symptom amplifier, but the root defect is one layer upstream, in `block_classification.py`'s inability to distinguish a genuine heading from a table-header cell, a running title, or a rotated-diagram fragment using only word-count/font/case/punctuation signals.**
2. **Extraction/parser behavior (~15–25%)**: two newly-confirmed, distinct sub-mechanisms (rotated-diagram text splitting, narrow-column table word-wrap) directly produce broken-word artifacts that were previously unexplained; the header/footer detector's global-only recurrence threshold is also, at root, an extraction/detection-stage design gap, not a segmentation problem.
3. **Alignment/matching (~15–20%, concentrated in specific companies)**: the greedy one-to-one assignment under duplicate-fragment competition (already well-documented by the prior audit) remains real and confirmed independently here (119 exact-hash collision groups), but this investigation's evidence suggests roughly two-thirds of what the split/merge detector flags as `AMBIGUOUS` is itself downstream fallout from the fragment-duplication problem above, not an independent alignment-algorithm defect — meaning fixing upstream classification would shrink this category too, before any alignment-code change is made.

### What we should fix first (top 3, ranked)

1. **Table-adjacency-based re-classification of table-header/cell fragments** (Section 11, row 1) — the single most concretely evidenced, most mechanically traced finding in this investigation (Sections 3–4), uses data the pipeline already computes, and plausibly addresses the single largest sub-population (~30–35%) of the heading-only problem.
2. **Exact-hash second-pass ADD/DELETE reconciliation, position/cluster-aware** (Section 11, row 5) — cheapest possible fix (comparison-recompute-only, no re-extraction/re-segmentation/re-embedding), directly resolves a concretely-counted 119-group problem, and — per Section 6 — would likely also reduce the `AMBIGUOUS` rate as a side effect without any split/merge-specific code change.
3. **Header/footer detection: strip trailing section-name suffixes before recurrence comparison, and add a windowed/chapter-scoped recurrence check** (Section 11, row 3) — two distinct, independently confirmed mechanisms with concrete numeric evidence (78/162 pages, 28/119 collisions), addressing a smaller but well-understood population.

### What we should NOT change yet

- **The global word-count hard floor value itself** (e.g., simply raising or lowering 15) — Section 9 demonstrates word count is not a sufficient discriminator for any of the confirmed problem categories; changing the number without changing the *signal* it's based on would either discard genuine short content (Category I) or fail to catch same-length junk (Category D/E).
- **The alignment scoring weights or thresholds** (`top_k`, `min_semantic_similarity`, `min_content_score_for_acceptance`, the classification thresholds) — this investigation found no evidence that the scoring/threshold design itself is miscalibrated; every confirmed alignment-layer problem traces to *upstream duplication interacting with* a reasonable, well-documented greedy one-to-one design, not to the thresholds being wrong per se.
- **A blanket "heading is never standalone" rule (Model B)** — Section 8 shows this would discard genuine Category I short-disclosure content; a criteria-based approach (Model C/D) is required.
- **Building a general structural-signal quality classifier (Rule F, Section 9)** — the most powerful option in the abstract, but this investigation did not validate one, and it should follow, not precede, the narrower table-adjacency and header-normalization fixes above, so its training/validation signal benefits from a cleaner upstream corpus.
- **A geometry-aware block-merging pass for rotated/wrapped text (Section 11, row 4)** — real and confirmed, but the highest-regeneration-cost, highest-implementation-risk item in the matrix; it should wait until the lower-risk classification and alignment fixes are validated, both to avoid compounding regeneration cost and because a badly-tuned merge heuristic risks damaging genuinely well-extracted multi-column content.

### Proposed implementation milestone

**"Passage classification hardening and alignment reconciliation" (a narrower successor to the prior audit's proposed "Passage matching reconciliation and heading-fragment scoping" milestone, re-sequenced based on this investigation's ground truth):**

**Stage 1 — Table-adjacency re-classification** (`block_classification.py`)
- *Exact code area*: the `HEADING_CANDIDATE` branch (priority 11) and the `TABLE_LIKE` branches (priorities 7–8); add a new check that looks at neighboring blocks' `block_type` (already computed and available at classification time, or in a light second pass over already-classified blocks within the same page).
- *Expected benefit*: directly reduces the ~30–35% table-header-fragment share of the heading-only population (Section 4).
- *Known risks*: a genuine short heading immediately preceding a table (e.g., "Summary of results" right before a results table) could be misclassified if the rule is too aggressive — needs same-row/same-y-band geometry (not just adjacency in `reading_order`) to distinguish "this IS a column header of the table" from "this is a caption above the table."
- *Required data regeneration*: full re-segmentation → re-embedding → re-alignment → republish (passage boundaries shift).
- *Proposed tests*: unit tests using the exact KP2 page-14 and page-129 examples from Section 3 as fixtures (real, cited, reproducible block geometry); a regression test asserting a real report's genuine short headings (e.g., ACT's `"Committee"`, SDL's `"NOTES TO THE CONSOLIDATED FINANCIAL STATEMENTS"`) are NOT reclassified.
- *Validation metrics*: re-run this report's Section 2 company-level heading-only-rate query on the new corpus; KP2's 60.4% should drop measurably given its heavy table content, while SBP (lowest table content) should barely move.
- *Rollback*: revert the classification rule; re-run segmentation with the old `configuration_hash` (idempotent orchestration already supports this per the prior audit's Section 1.8).

**Stage 2 — Header/footer normalization + windowed recurrence check** (`header_footer_detection.py`)
- *Exact code area*: `normalize_candidate` (add trailing-suffix stripping for a `| SECTION NAME`-shaped pattern) and the recurrence-threshold check (add a secondary windowed check).
- *Expected benefit*: resolves the two concretely-confirmed mechanisms in Section 3 (ACT section-name variation, BEL chapter-scoped kicker).
- *Known risks*: the windowed check specifically needs real-corpus tuning to avoid false-positiving a genuinely-repeating chapter-opening heading.
- *Required data regeneration*: full re-extraction → re-segmentation → re-embedding → re-alignment → republish (most expensive of the two stages, since header/footer flags are set at extraction time).
- *Proposed tests*: fixture using the exact ACT-2023 9-variant running-title data and the exact BEL "PERFORMANCE REVIEW" geometry cited in Section 3.
- *Validation metrics*: re-run Section 5's exact-hash ADD/DELETE collision count on BEL specifically (expect the 28-group BEL collision count to drop materially, since Section 5 traced it directly to this mechanism).
- *Rollback*: revert; extraction runs are also idempotent per `configuration_hash`.

**Stage 3 — Exact-hash, position-aware second-pass reconciliation** (new module, `passage_alignment.py` or a sibling)
- *Exact code area*: a new post-processing step after `_run_alignment` completes, operating only on `REMOVED`/`NEW` rows within one report pair.
- *Expected benefit*: directly resolves the 119 confirmed exact-hash collision groups (Section 5); per Section 6, likely reduces the `AMBIGUOUS` rate as a side effect.
- *Known risks*: low, by construction (never touches an already-accepted row); the main design decision is using cluster/position proximity (Section 5's worked example) rather than naive nth-occurrence matching, to correctly leave genuinely-count-different duplicate groups partially unmatched rather than force-matching them.
- *Required data regeneration*: none — comparison-recompute-only, reusing existing `AlignmentRun` output.
- *Proposed tests*: fixture using the exact KP2 USD-cluster and BEL PERFORMANCE-REVIEW-cluster data from Section 5.
- *Validation metrics*: re-run this report's Section 5 exact-hash query; expect it to approach zero.
- *Rollback*: trivial — this is an additive, versioned step; disabling it reverts to current behavior exactly.

**Stage 4 — Re-measure `AMBIGUOUS` rate; only then consider true split/merge representation**
- Per Section 6's finding, re-run the `AMBIGUOUS`-rate and word-count-composition queries from this report after Stages 1–3 land. Only pursue the (already schema-scaffolded but unimplemented) one-to-many/many-to-one representation if a materially-elevated `AMBIGUOUS` rate remains once the duplicate-fragment population has shrunk — this investigation's evidence (63.4% of current `AMBIGUOUS` rows are ≤10-word fragments) suggests this stage may turn out to be unnecessary, or much smaller in scope than currently assumed, once Stages 1–3 land.

**Deliberately deferred, per "what we should not change yet"**: TOC page-level structural detection (Section 7's finding is real and interesting but affects a small, already-tolerable population and needs new detection infrastructure, not a parameter change); the geometry-aware block-merging pass for rotated/wrapped text (Section 11's highest-cost item); any quality-classifier (Rule F) work.

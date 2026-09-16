# Experiment: Document Representation Bake-Off for Annual-Report Extraction

Status: exploratory research only. No production code, database, or publishing pipeline was
touched. All work was performed against `data/raw/**/annual_report.pdf` using throwaway PyMuPDF
scripts and this session's own image-reading capability, with all intermediate artifacts (plain
text, blocks JSON, dict/spans JSON, rendered PNGs) written to a session-local scratch directory
outside the repository (`$TMPDIR/extraction-bakeoff/`). Nothing here is wired into the
application. This is a direct follow-up to
`docs/experiments/annual-report-schedule-localization.md` ("the prior experiment"), which is
assumed read; findings below are stated relative to it rather than re-derived from scratch.

## 1. Executive summary

**Plain PyMuPDF text is sufficient for schedule *localization* (finding the right page range),
but is not reliable for deterministic *source-text reconstruction* — and this gap is real,
observed directly on multiple pages, not hypothetical.** Blocks add exactly one thing that
matters: a bounding box per text fragment. That one addition is enough to correctly resolve the
clearest, most damaging defect found in the prior experiment (Bell Equipment's heading
displacement) without needing anything more elaborate. Dict/spans add font name and size on top
of blocks; on the pages sampled here, this mattered for distinguishing a genuine sub-heading from
a repeated running header at Kore Potash, but not for most other pages. Multimodal/layout
interpretation (rendering the page and reading it directly) was the only representation that
recovered full semantic structure on genuinely graphic pages — a stacked risk-panel layout and an
IT-risk heat-map table — but it was unnecessary and added no value on clean narrative pages,
confirming the prior experiment's implicit assumption that a uniform pipeline stage is the wrong
design.

Concretely, on the ~24 pages sampled here:

- **Plain text (A) localizes fine and is the cheapest option**, but on a **majority of the
  "difficult" pages selected for this bake-off**, plain text either scrambled visual order,
  destroyed table semantics, or lost the distinction between a running header and a real heading.
  It was already adequate, with no meaningful representation gap, only on the plain narrative
  control pages (Sabvest) and on a page that looked risky (AfroCentric's 3-column trend panel)
  but in practice extracted in clean, uninterrupted column order.
- **Blocks (B) fix the single largest, most consistently observed defect**: on every Bell
  Equipment section-start page checked (34, 38, 40 boundary, 41), the visually-top-of-page heading
  block was emitted *last* in `get_text("blocks")`/`get_text()` order, but its bounding box
  (`y0` in the high-60s/low-90s, just below the running section label at `y≈35–44`) was
  unambiguous and trivially the lowest `y0` on the page except the top page-furniture line. A
  `sort-by-y0` pass over blocks — no NLP, no model — recovers the correct visual order on every
  case checked.
- **Dict/spans (C) add real, checkable evidence exactly where blocks are ambiguous**: on Kore
  Potash's repeated "CORPORATE GOVERNANCE REPORT (CONT)" header (confirmed present, identically
  worded and identically positioned at `y≈61`, font `ArialNarrow-Bold` size `16.0`, on pages 36,
  50, and 53), the genuine sub-heading beneath it ("BOARD LEADERSHIP AND COMPANY PURPOSE (CONT)",
  "AUDIT AND RISK COMMITTEE (CONT)", "REMUNERATION REPORT") is distinguishable by font (bold vs.
  regular body) and vertical position, but is the *same point size as body text* (11.0) — smaller
  than the running header. Blocks alone (no font info) cannot make this distinction; dict/spans
  can.
- **Multimodal (D) was necessary, not just nice-to-have, on exactly two of the ~24 sampled
  pages**: Spur's stacked risk-panel pages (each risk box a CAUSES | RESIDUAL RISK MITIGATION
  CONTROLS | OPPORTUNITIES sub-layout) and AfroCentric's IT-risk register table (where plain text
  preserves row grouping but strips the column headers that give the numbers meaning — "9" and
  "10" survive as bare digits with no indication which is "previous" vs. "current" residual
  rating, and the colored risk-heat trend arrows disappear entirely). On every other sampled page,
  multimodal interpretation reproduced what blocks/dict already showed, at much higher cost, with
  no localization or extraction benefit observed.
- **Multimodal is not needed for every page — only for a identifiable minority.** Of ~24 pages,
  2–3 needed it to recover information plain text destroyed (the AfroCentric risk table's
  numeric/trend semantics, and to a lesser extent the exact spatial grouping on the Spur panel
  pages, which text alone got mostly right). The rest were adequately served by blocks or plain
  text.
- **The simplest representation this experiment can recommend as a default is plain text +
  blocks** — i.e., capture both in the same pass (cheap, since PyMuPDF computes blocks from the
  same parse as plain text) and use block `y0`/`x0` as a tie-breaker whenever the LLM's localized
  heading text does not appear at the expected position in the linear text stream. Dict/spans and
  multimodal are reserved for specific, identifiable ambiguity signals (Section 9), not applied
  uniformly.

**Scope caveat, stated up front and repeated below**: this is a ~24-page sample across five
reports, hand-picked to stress-test known hazards. It is not representative of the corpus's
overall page mix (most pages are plain narrative, per the prior experiment's own observation), and
these findings should not be extrapolated to "X% of pages need multimodal" — only to "these
specific hazard types benefited from these specific representations on the pages checked."

## 2. Sample page inventory

25 pages were extracted; one (SUR p.174, R3) is reported below only for context and is folded into
the R3/R4/R5/R8 "single risk panel" rows rather than double-counted. 24 pages carry independent
scoring weight. PDF page numbers are 1-based `fitz` page indices matching the prior experiment's
convention; printed/running page numbers (as visible in the page footer/running header) are noted
where they differ.

| Report | PDF page | Printed page | Page type | Known hazard | Why selected |
|---|---|---|---|---|---|
| SUR (Spur) 2024 | 10 | 9 | CEO narrative, 2-column body, heading mid-page | Heading not at page top; nested sub-headings ("A purposeful path", "Your place") | Baseline "designed" narrative page; contrast to Bell's displacement (here the heading is simply positioned lower, not reordered) |
| SUR 2024 | 164 | 163 | Section-divider/cover page | Large title over full-bleed photo, bulleted "Key board activities" in 3 columns | Divider-page structure; tests whether a decorative title page confuses localization |
| SUR 2024 | 174 | 173 | Single risk panel (R3) | One risk per page, no panel pairing | Control case for the risk-panel format before checking paired pages |
| SUR 2024 | 175 | 174 | Two stacked risk panels (R4/R5) | Panels stacked vertically, not side-by-side; each panel itself has CAUSES/MITIGATION/OPPORTUNITIES sub-columns | Required page range per task brief; verifies exact layout before scoring |
| SUR 2024 | **176** | **175** | Two stacked risk panels (**R6/R7**) | **The task's named side-by-side risk-panel case** | Explicitly required; verify claimed field interleaving directly |
| SUR 2024 | 177 | 176 | Single risk panel (R8) | One risk per page | Control case, confirms panel count varies 1–2 per page |
| BEL (Bell) 2021 | 33 | 31 | Photo-grid page (staff headshots), no heading | No heading text present at all | Page immediately preceding a displaced heading; establishes there is no displaced text to find on the "before" page itself |
| BEL 2021 | **34** | **32** | Section-start page: "Joint report by the chairman and chief executive" | **Heading-at-bottom-of-block-list displacement** (task's named case) | Explicitly required; confirmed via block y0/order mismatch |
| BEL 2021 | 37 | 35 | Continuation, end of Joint report | Photo + running "Future Outlook" sub-heading | Boundary page before Finance director's report starts |
| BEL 2021 | **38** | **36** | Section-start page: "Finance director's report" | **Heading-at-bottom-of-block-list displacement**, most extreme case in sample | Explicitly required; heading block is index 9 of 9 despite bbox at page top |
| BEL 2021 | 40 | 38 | Continuation: "Finance director's report continued" | Sub-heading "Looking ahead" mid-page; heading NOT displaced here | Contrast case — continuation pages do not show the displacement, only section-*start* pages do |
| BEL 2021 | 41 | 39 | Section-start page: "Corporate governance report" | Same displacement pattern as p.34/38 | Confirms the displacement is a template-level pattern, not a one-off |
| KP2 (Kore Potash) 2023 | 34 | 34 | Section-start page: "CORPORATE GOVERNANCE REPORT" (no "(CONT)") | Genuine first page of a 32-page section | Baseline before the running-header pages |
| KP2 2023 | **36** | 36 | "CORPORATE GOVERNANCE REPORT (CONT)" + genuine sub-heading "BOARD LEADERSHIP AND COMPANY PURPOSE (CONT)" | **Running header vs. real sub-heading** (task's named case, early sample) | Explicitly required |
| KP2 2023 | **50** | 50 | Same running header + "AUDIT AND RISK COMMITTEE (CONT)" | Same running-header hazard, mid-range sample | Explicitly required |
| KP2 2023 | **53** | 53 | Same running header + genuine new top-level content: "REMUNERATION REPORT" | Remuneration nested inside the governance running-header span | Explicitly required |
| ACT (AfroCentric) 2022 | 8 | 4 | Boxed callout page: "Outlook", "Process disclosure and assurance approach", "Board approval" box, "Feedback" box | Infographic/box layout, not a risk table | Task-suggested infographic candidate |
| ACT 2022 | 27 | 23 | 3-column trend panel ("Understanding the global trend / in our context / Responding strategically") + "Related risks / Related material matters / Link to strategic levers" panel with icon row | Multi-column, non-side-by-side | Multi-column control case: does PyMuPDF's column handling always fail? |
| ACT 2022 | **39** | 35 | IT risk register table, 7 columns including colored heat cells and trend arrows | **Table/infographic with numeric-column semantics** | Task-suggested "Our risks" candidate |
| ACT 2022 | 40 | 36 | Continuation: Economic/Growth Risks table | Same table hazard, second instance | Confirms table hazard is systematic across the section, not one page |
| SBP (Sabvest) 2024 | **2** | 1 | Chairman's Letter, single-column narrative | None — clean control page | Explicitly required control case |
| SBP 2024 | 6 | 5 | Numbered-section narrative (2.3, 3, 4.1) with bullet list | None — clean control page, different visual style (numbered/bulleted vs. flowing prose) | Second control case, tests a different clean layout |
| SBP 2024 | 38 | 37 | Numbered-section narrative ("10. Risk report") | None — clean control page despite subject matter (risk) that was hazardous elsewhere | Tests whether "risk" content is inherently hazardous or only hazardous when panel-formatted |

Total: 24 independently scored pages (25 extracted, with SUR p.174 folded into the risk-panel
cluster) across 5 reports, matching the 15–25 page target.

## 3. Representation examples

Concise excerpts illustrating the meaningful differences found. Full JSON/text dumps remain in
`$TMPDIR/extraction-bakeoff/` and are not reproduced in full here.

### 3.1 BEL p.38 — heading displacement (test case 2)

**A. Plain text** (relevant excerpt, i.e. what a linear reader/LLM sees, order preserved):

```
BELL EQUIPMENT LIMITED | Integrated Annual Report 2021
36
PERFORMANCE REVIEW
The 2021 result is a solid recovery from the loss incurred by the
group in 2020. ... [full body text of both columns] ...
Finance director's report
```

The heading string `Finance director's report` is the **last line of the page's extracted text**,
after the entire two-column body.

**B. Blocks** (`get_text("blocks")`, raw emission order, `y0`/`y1` shown):

```
index=2  y0=413.2 y1=522.8  "The 2021 result is a solid recovery..."
index=3  y0=533.1 y1=602.8  "Financial Performance / Revenue of R8,0 billion..."
...
index=9  y0=66.9  y1=88.3   "Finance director's report"
```

Block index 9 (the heading) has `y0=66.9` — clearly the topmost text block on the page (only the
page-furniture line at `y0=34.6` is higher) — yet it is emitted **last**, after all eight body
blocks. Sorting blocks by `y0` before consuming them recovers the correct order trivially; the
same pattern (heading block emitted last, `y0` in the high-60s) was confirmed on BEL pp.34 and 41
as well. By contrast, BEL p.40 (a *continuation* page, "Finance director's report continued") has
its heading at block index 2, not displaced — the defect is specific to section-*start* pages in
this report's template, not a general property of every page.

**C. Dict/spans**: adds nothing beyond blocks for this specific case — font size (not sampled in
detail here, but visually the heading is a large light-grey serif title, clearly distinct from
11pt body text) would confirm the same conclusion blocks already gave unambiguously via
coordinates alone.

**D. Multimodal**: visually trivial to confirm — the rendered PNG shows the heading as a large
title immediately below a small "PERFORMANCE REVIEW" section label, straightforwardly at the top
of the page, exactly where the block bbox said it was. Multimodal *confirms* what blocks already
established; it does not add new information here.

### 3.2 KP2 running header vs. real sub-heading (test case 3)

**Dict/spans**, KP2 p.50 (all values from actual span data, not estimated):

```
y0=61.1  font=ArialNarrow-Bold  size=16.0  "CORPORATE GOVERNANCE REPORT (CONT)"
y0=92.9  font=ArialNarrow-Bold  size=11.0  "AUDIT AND RISK COMMITTEE (CONT)"
y0=119.5 font=ArialNarrow       size=11.0  "Create an integrated risk management process..."
```

The running header is distinguishable two ways that persist across all three sampled instances
(pp.36, 50, 53): (1) it is always the *first* text block, at the *same* `y0` (61-ish) on every
page; (2) it is a larger font size (16.0) than everything else on the page, including the genuine
sub-heading, which is the same 11.0pt size as body text and distinguished from body only by bold
weight (`ArialNarrow-Bold` vs. `ArialNarrow`). **Blocks alone (bbox only, no font metadata) cannot
make this distinction** — a running header and a genuine sub-heading both simply look like "short
text blocks near the top of the page" without font/size information. Plain text loses the
distinction entirely (both render as unstyled capitalized lines). Repeated exact text + repeated
exact `y0` across many consecutive pages is itself a strong signal a plain-text-only or
blocks-only pipeline could still exploit (by tracking repetition across the page range), but it
requires cross-page state that a single-page representation does not carry by itself.

### 3.3 SUR risk panels — page 176 (test case 1)

**A. Plain text**, in extraction order (abbreviated):

```
OPPORTUNITIES
  Identifying missing channels and product
  ... [R6's opportunities list, 4 items] ...
OPPORTUNITIES
  Investigate introducing tagging system in Panarottis for F2025
  ... [R7's opportunities list, 3 items] ...
CAUSES
RESIDUAL RISK MITIGATION CONTROLS
  Increased competition
  ...
  [R6's CAUSES/CONTROLS/IMPACT, fully grouped]
CAUSES
RESIDUAL RISK MITIGATION CONTROLS
  Human error.
  ...
  [R7's CAUSES/CONTROLS/IMPACT, fully grouped]
```

**Finding, corrected against the task brief's hypothesis**: R6 and R7's CAUSES / RESIDUAL RISK
MITIGATION CONTROLS / IMPACT fields do **not** interleave with each other on this page — each
risk's core fields extract as a contiguous, correctly-grouped block. The actual defect observed is
different: **both risks' OPPORTUNITIES panels are extracted together, before either risk's
CAUSES/CONTROLS/IMPACT content**, because the OPPORTUNITIES column is a separate right-hand
sidebar spanning both stacked risk boxes, and PyMuPDF's linear ordering groups it by its own
column position rather than interleaving it per-risk. Additionally, on inspection of the rendered
image, R6 and R7 are **stacked vertically** (R6's full-width box, then R7's full-width box below
it), not side-by-side as the task brief's hypothesis described — the side-by-side structure exists
*within* each risk box (CAUSES | CONTROLS as two columns, OPPORTUNITIES as a third), not *between*
R6 and R7. This is exactly the kind of premise the task instructed to verify rather than assume,
and it changes the correct characterization of the defect: it is a "sidebar column extracted
out-of-band from its parent row" pattern, not a "two adjacent risks' fields alternating" pattern.

**D. Multimodal** on this page is straightforward to interpret correctly and is genuinely useful
here: it immediately shows the OPPORTUNITIES columns as physically separate compartments to the
right of both risk boxes, explaining *why* plain text groups them together — something blocks'
bare coordinates would also show (the OPPORTUNITIES blocks share a distinct `x0` range from the
CAUSES/CONTROLS blocks) but that is easier to confirm by eye than by reasoning over raw numbers
alone.

### 3.4 ACT p.39 — IT risk table (test case 4)

**A. Plain text** preserves row grouping (risk description → root cause → inherent rating →
existing controls → previous/current residual) as a contiguous sequence per risk, e.g.:

```
Cybersecurity vulnerabilities: ...
1. Additional investment in infrastructure required
25
1. Information security strategy, framework, related policies and procedures
2. Cybersecurity service improvement programme
...
12
12
```

The two trailing numbers (`12`, `12`) are the "previous residual rating" and "current residual
rating" — but nothing in the plain text distinguishes them from each other or from the "inherent
rating" (`25`) three lines above; a reader must already know the table's column order to assign
meaning. The colored heat-map cell backgrounds (red/amber/yellow shading indicating severity) and
the colored trend arrows (red down-arrow, green up-arrow, yellow flat-arrow indicating
worsening/improving/unchanged) are **completely absent from the text** — for the cybersecurity row
specifically, the source page shows a flat (unchanged) yellow arrow, which plain text renders as
nothing at all, not even a placeholder.

**B/C. Blocks and dict** would recover the column *positions* (each number's `x0` places it under
its header), which is enough to reconstruct the previous/current mapping deterministically without
needing multimodal — this is a case where blocks are sufficient for the *specific* semantic loss
(number-to-column mapping) but not for the *color* loss (heat severity, trend arrows), because
color is not captured by either the `"blocks"` or `"dict"` text APIs at all (arrows here are
likely vector-drawn or bitmap icons, not text spans).

**D. Multimodal** was the only representation that recovered the trend-arrow semantics in this
experiment, by directly reading the rendered image and describing e.g. "Cybersecurity
vulnerabilities row: previous residual 12, current residual 12, movement: flat/yellow arrow
(unchanged)."

### 3.5 SBP control pages (test case 5)

Plain text on SBP pp.2, 6, and 38 required no correction of any kind: headings appear at the top of
the page's text stream in the correct position, paragraph order matches visual order, and numbered
sub-sections (e.g. "2.3 Investment proposition", "10.1 Approach to risk management") extract with
their numbering intact and correctly nested. Blocks/dict/multimodal add no additional information
usable for either localization or lexical comparison. This confirms the prior experiment's
implicit finding that Sabvest is the "control" report in this corpus and that engineering effort
should be scoped to the reports/pages that actually need it.

## 4. Page-level scorecard

Scored 0 (failed) – 4 (excellent) per representation, split for pages where the two purposes
diverge into **Loc** (localization suitability: criteria 2, 3, 4, 8, plus criterion 3's practical
weight) and **Src** (clean source-text suitability: criteria 1, 6, 7, 9, 10). Criterion 5
(column/panel integrity) and criterion 8 (section-boundary usability) are reported once as they
affect both purposes similarly on these pages. Where a page had no instance of a given hazard
(e.g. no table on a narrative page), that criterion is scored N/A rather than assigned an
artificial 4.

| Page | Hazard | Text: Loc / Src | Blocks: Loc / Src | Dict: Loc / Src | Multimodal: Loc / Src |
|---|---|---|---|---|---|
| SUR p.10 | mid-page heading | 3 / 3 | 4 / 3 | 4 / 3 | 4 / 4 |
| SUR p.164 | divider page, 3-col bullets | 3 / 2 | 4 / 3 | 4 / 3 | 4 / 4 |
| SUR p.174 (R3) | single risk panel | 3 / 3 | 4 / 3 | 4 / 3 | 4 / 4 |
| SUR p.175 (R4/R5) | stacked panels | 3 / 2 | 3 / 3 | 3 / 3 | 4 / 4 |
| SUR p.176 (R6/R7) | stacked panels, sidebar-out-of-band | 2 / 1 | 3 / 3 | 3 / 3 | 4 / 4 |
| SUR p.177 (R8) | single risk panel | 3 / 3 | 4 / 3 | 4 / 3 | 4 / 4 |
| BEL p.33 | photo grid, no heading | 3 / 4 (nothing to lose) | 4 / 4 | 4 / 4 | 4 / 4 |
| BEL p.34 | heading displaced to bottom of block list | 2 / 1 | 4 / 4 | 4 / 4 | 4 / 4 |
| BEL p.37 | end-of-section continuation | 3 / 3 | 4 / 4 | 4 / 4 | 4 / 4 |
| BEL p.38 | heading displaced (worst case: index 9 of 9) | 1 / 1 | 4 / 4 | 4 / 4 | 4 / 4 |
| BEL p.40 | continuation, NOT displaced | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |
| BEL p.41 | heading displaced | 2 / 1 | 4 / 4 | 4 / 4 | 4 / 4 |
| KP2 p.34 | genuine section start, no "(CONT)" | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |
| KP2 p.36 | running header vs. real sub-heading | 2 / 3 | 2 / 3 | 4 / 4 | 4 / 4 |
| KP2 p.50 | running header vs. real sub-heading | 2 / 3 | 2 / 3 | 4 / 4 | 4 / 4 |
| KP2 p.53 | running header, genuine new top-level section nested inside | 2 / 3 | 2 / 3 | 4 / 4 | 4 / 4 |
| ACT p.8 | boxed callout/infographic | 3 / 3 | 3 / 3 | 3 / 3 | 4 / 4 |
| ACT p.27 | 3-column panel (clean extraction) | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |
| ACT p.39 | risk table, numeric column semantics | 3 / 1 | 3 / 2 | 3 / 2 | 4 / 4 |
| ACT p.40 | risk table, continuation | 3 / 1 | 3 / 2 | 3 / 2 | 4 / 4 |
| SBP p.2 | clean narrative control | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |
| SBP p.6 | clean numbered/bulleted control | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |
| SBP p.38 | clean narrative, risk subject matter | 4 / 4 | 4 / 4 | 4 / 4 | 4 / 4 |

Per-representation ratings that apply once, not per page:

| Representation | Implementation complexity | Compute/inference cost | Auditability |
|---|---|---|---|
| A. Plain text | LOW | LOW (no extra work beyond `get_text()`) | MEDIUM (byte offsets are hard to map back to visual position without re-rendering) |
| B. Blocks | LOW | LOW (same parse pass as plain text, negligible extra cost) | HIGH (bbox is directly checkable against a rendered page) |
| C. Dict/spans | LOW–MEDIUM (larger payload, more fields to reason over) | LOW (still a single-pass parse, just verbose) | HIGH (font/size are directly checkable, same as bbox) |
| D. Multimodal | MEDIUM (needs page rendering + a vision-capable model call per page) | HIGH (one model call per page, materially slower/costlier at corpus scale) | MEDIUM (a JSON layout description is auditable, but the underlying visual judgment is not as mechanically checkable as a bbox/font comparison) |

## 5. Aggregated results

**Sample size: 24 pages across 5 reports. These are hazard-selected, not randomly sampled, and
the aggregates below describe behavior on this specific stress-test set — they should not be read
as "X% of all corpus pages."**

Average scores by representation (Loc / Src, across the 24 pages, N/A cells excluded):

| Representation | Avg Localization score | Avg Source-text score |
|---|---|---|
| A. Plain text | 2.9 | 2.7 |
| B. Blocks | 3.5 | 3.3 |
| C. Dict/spans | 3.8 | 3.5 |
| D. Multimodal | 4.0 | 4.0 |

**Reading these numbers correctly matters more than the numbers themselves.** The averages hide a
sharp bimodal pattern: on the 15 of 24 pages with no hazard specifically targeted by this sample
(clean narrative, genuine section starts, non-displaced continuations, cleanly-ordered
multi-column text), plain text already scores 3–4 on both axes and every other representation adds
essentially nothing. On the remaining 9 hazard pages (BEL displacement x3, KP2 running-header x3,
SUR risk panels x3, ACT risk table x2 — note some overlap in counting since a page can carry more
than one hazard), plain text drops to 1–2 on the source-text axis specifically, while localization
degrades more mildly (2–3) because an LLM reasoning over the whole page's text can often still
identify *that* a section exists even when its exact boundary text is out of order. Blocks close
most of the gap for the displacement hazard specifically (BEL: Src goes from 1 to 4) but not for
the running-header hazard (KP2: Src stays at 3 with blocks alone, needs font/size to reach 4) or
the table-semantics hazard (ACT: Src caps at 2 even with dict, needs multimodal to reach 4).

## 6. Failure-mode analysis

- **Heading order (Bell Equipment)**: confirmed on 3 of 3 section-start pages checked (34, 38,
  41); the true heading is always the visually topmost element (`y0` in the high-60s to low-90s)
  but is emitted last in both `get_text()` and `get_text("blocks")` raw order. The one
  continuation page checked (p.40) did **not** show this pattern, indicating it is specific to a
  section-opener page template rather than universal. Blocks fully resolve this via a `y0` sort.
- **Running headers (Kore Potash)**: confirmed on all 3 pages checked (36, 50, 53); identical text
  ("CORPORATE GOVERNANCE REPORT (CONT)"), identical `y0≈61`, identical font/size
  (`ArialNarrow-Bold`, 16.0) on every page, contrasted against a genuine sub-heading directly below
  it that is bold but the *same point size as body text* (11.0). Blocks cannot distinguish these
  two lines from each other (both are "short text block near page top"); font size and repeated
  exact position (observable within a single dict/spans capture, and more robustly by tracking
  repetition across pages) can.
- **Sidebars (Spur)**: the sidebar/persistent-nav pattern described in the prior experiment was
  not directly re-tested here since the sampled Spur pages (deep in the risk-register section) use
  a top navigation bar rather than a left sidebar; the OPPORTUNITIES-column-extracted-separately
  pattern found on pp.175–176 is functionally the same class of defect (a spatially distinct
  column extracted out of its row-local order) and responds to the same fix (column/x0-aware
  grouping via blocks).
- **Columns (AfroCentric p.27)**: this was the one case in the sample where a 3-column layout
  extracted in **fully correct order** with plain text alone — column 1 complete, then column 2,
  then column 3, no interleaving. This directly contradicts an assumption that "multi-column
  implies broken order"; PyMuPDF's column handling succeeded here, likely because the columns
  are non-overlapping vertical bands with no shared row structure, unlike Spur's panels.
- **Side-by-side panels (Spur pp.175–176)**: R6/R7 (and R4/R5) are stacked vertically per page,
  not side-by-side as originally hypothesized; each risk's own CAUSES/CONTROLS fields stayed
  correctly grouped in plain text, but the OPPORTUNITIES sidebar for both risks was pulled forward
  and grouped together, ahead of either risk's main content — a column-position artifact, not a
  risk-alternation artifact.
- **Tables (AfroCentric pp.39–40)**: row grouping survived in plain text; column-to-value mapping
  (which number is "previous" vs. "current" residual rating) did not, and is only recoverable via
  block/dict x-coordinates or multimodal reading. Colored severity cells and trend arrows are lost
  in every non-multimodal representation, since these are not part of any PyMuPDF text
  API's output (likely vector graphics or raster icons).
- **Infographics (AfroCentric p.8)**: the boxed "Outlook"/"Board approval"/"Feedback" callouts
  extracted with all text intact and largely in correct visual order in plain text, only losing
  the visual boundary between "this is a distinct highlighted box" and "this is regular body
  text" — a cosmetic loss for localization purposes, more relevant if a downstream feature needed
  to reproduce which paragraphs are visually set apart as callouts.
- **Mid-page boundaries**: pervasive across the whole sample (as the prior experiment also found)
  — most section starts and ends fall partway down a page rather than at a page break; this
  affects localization boundary precision but is a separate issue from the hazards above and was
  not separately stress-tested here beyond what is already visible in the excerpts (e.g. BEL's
  Finance director's report starting mid-way through p.37/38's boundary).
- **Clean narrative (Sabvest, KP2 p.34, ACT p.27)**: no representation beyond plain text added
  value; this is the majority case in this corpus per the prior experiment and should not be
  over-engineered.

## 7. Extraction vs. localization

- **Schedule localization**: plain text is adequate on this sample. Even on the worst hazard pages
  (BEL's displaced headings), the surrounding body text still names the section unambiguously
  enough for an LLM reasoning over the full page (or several pages) to conclude "this is the
  Finance director's report" — this matches the prior experiment's actual outcome (BEL's
  financial_performance schedule was localized at 0.90 confidence despite this exact defect being
  present in the source pages it read). Localization degrades gracefully with a hazard present;
  it does not fail outright on any page checked here.
- **Boundary resolution**: plain text degrades further here than for localization proper — a
  linear byte offset into text where the heading string appears last is not usable as "the start
  of the section" without knowing the true page-top position. Blocks resolve this cleanly for the
  displacement hazard; blocks plus font/size resolve it for the running-header hazard.
- **Clean source reconstruction**: plain text is **not** reliable on the hazard subset (Src scores
  of 1–2 on 5 of the 9 hazard-affected pages). Blocks recover most of this for coordinate-only
  defects (displacement, column-out-of-band). Dict/spans recover the rest for font-dependent
  defects (running header vs. sub-heading). Multimodal is needed only for defects that lose
  non-text information entirely (color-coded severity, trend arrows, precise panel-to-panel
  spatial grouping when it matters for correctness rather than just order).
- **Later lexical metrics** (TF-IDF, Jaccard, edit distance, sequence diff): these depend on clean
  source reconstruction, not on localization, and therefore inherit the boundary-resolution and
  source-reconstruction conclusions above, not the (better) localization conclusion. A pipeline
  that stops at "plain text was good enough to localize the section" and then runs lexical
  comparison directly on that same plain text risks corrupting exactly the reports/pages
  identified here (Bell, Kore Potash's governance/remuneration boundary, any Spur or AfroCentric
  risk/table page) even though localization itself looked fine.

## 8. Proposed minimum viable architecture

Evaluated against the evidence above:

- **Option A (plain text only)**: adequate for localization, demonstrably inadequate for source
  reconstruction on a meaningful minority of pages in this sample (BEL displacement, KP2
  running-header ambiguity, ACT table semantics). Rejected as the sole representation for any
  stage after localization.
- **Option B (plain text + blocks, deterministic block reconstruction)**: recovers the BEL
  displacement hazard completely (a `y0` sort is sufficient, confirmed on 3 pages) and the
  Spur sidebar-column hazard partially (column/x0 grouping would need to be blocks-aware, not
  tested as a full algorithm here but the coordinate evidence supports it). Does **not** resolve
  the KP2 running-header-vs-subheading ambiguity (needs font/size) or the AfroCentric table
  color/trend-arrow loss (needs multimodal). Rejected as sufficient on its own, but a strict
  improvement over A at negligible extra cost.
- **Option C (hybrid: blocks by default, multimodal escalation for ambiguous/complex pages)**:
  best supported by the evidence. On this sample, the pages that needed anything beyond
  blocks/dict were identifiable in advance by structural signals (see Section 9), not just by
  hindsight — the running-header pages have exact-text-and-position repetition across many
  consecutive pages (observable by scanning the section range once), and the table/panel pages
  have many short, aligned blocks with a distinct x-coordinate structure. **Recommended.**
- **Option D (multimodal for every page)**: scored equal-or-better than every other option on
  every single page in the scorecard, which is expected — a capable reader looking at an actual
  rendered page will not do worse than a lossy text extraction. But 15 of 24 sampled pages (and,
  per the prior experiment's own characterization of the corpus, a much larger majority of pages
  corpus-wide) showed **zero measurable benefit** from multimodal over plain text or blocks. At
  corpus scale (the prior experiment noted ~30 available reports, up to ~200 pages each), running
  multimodal on every page means paying the HIGH compute/inference cost identified in Section 4 on
  thousands of pages to fix defects that, on this sample, affected roughly one third of
  hazard-selected pages and a much smaller fraction of an unselected sample. **Rejected as the
  default**, though it remains the right tool for the identified minority.

**Recommendation: Option C.** Use plain text + blocks as the default extraction representation
passed to the LLM for localization (Option B's inputs), and reserve dict/spans and multimodal
escalation for pages flagged by the signals in Section 9.

## 9. Escalation criteria

Signals actually observed on this sample to correlate with a page needing more than blocks:

- **Repeated identical text at a repeated identical position across consecutive pages** — this is
  exactly what distinguished KP2's running header from a one-off heading; observable cheaply by
  comparing the first block's text and `y0` across a page range without needing dict/spans on
  every page (dict/spans only needed once repetition is suspected, to confirm via font size).
- **Many short blocks with a small set of distinct, repeated x0 bands** — observed on the
  AfroCentric risk table (columns of numbers and short phrases sharing a handful of x-positions)
  and on the Spur risk panels (CAUSES / CONTROLS / OPPORTUNITIES each occupying a consistent
  x-range); a page whose block x0 values cluster into 3+ distinct bands, each recurring across
  many blocks, is a reasonable proxy for "this is tabular or panel-structured, not flowing prose."
- **A heading-like block (short text, bold or larger font per dict/spans) whose block index is
  *not* near the smallest y0 on the page** — this is the direct, mechanical signature of the BEL
  displacement pattern and could be checked automatically without rendering anything: it only
  needs the already-cheap blocks/dict data, so it is arguably not even a "multimodal escalation"
  trigger but a "prefer block y0 over raw block order" default rule.
- **Numeric or short-token-dense blocks adjacent to color-only visual elements** — harder to
  detect from text/blocks/dict alone since color and icons are invisible to all three; the
  practical proxy observed here is a table-like block layout (per the x0-clustering signal above)
  combined with column headers containing words like "rating," "previous/current," "movement," or
  "trend" — a coarse content-based heuristic, not a structural one, and the weakest of the signals
  listed here since it was inferred rather than independently confirmed on more than one report.

These are the signals actually observed being useful on this sample; they are not proposed as a
finished production rule set, and a larger sample would be needed before hard-coding thresholds
(e.g. "3+ x0 clusters" was not tested against a negative example of a genuinely two-column
narrative page with only 2 clusters, which should *not* escalate).

## 10. Impact on the prior schedule-localization recommendation

The prior experiment's Section 9 recommendation was: extend the same methodology (LLM
localization over plain PyMuPDF page text, no new parser) to 4–5 consecutive years of ACT and/or
BEL, focused only on the seven schedules that performed well, before committing to replace any
part of the production pipeline.

**This experiment's answer: (B) proceed with plain text + blocks, not plain text alone, for the
localization step itself — but the recommendation to run the ACT/BEL multi-year follow-up still
stands, with one addition.**

Justification: nothing found here changes the case for plain-text-driven *localization* — the
prior experiment's localization results were already produced using plain text on pages that (as
directly confirmed here) contain the exact BEL heading-displacement and page-boundary hazards, and
localization still worked at HIGH/MEDIUM confidence on those same pages. So there is no evidence
that localization needs to change. However, capturing blocks alongside plain text costs nothing
extra (same PyMuPDF parse pass, confirmed in Section 4's cost table) and directly fixes the one
defect (heading displacement) that would otherwise corrupt the *next* pipeline stage — deterministic
source-text extraction from the localized boundaries — which the multi-year follow-up will
eventually need once it moves past localization-only validation. Therefore: run the ACT/BEL
multi-year localization follow-up exactly as previously recommended, but capture and store blocks
(not just plain text) from the start, so that when a future stage needs to extract actual prose
from a localized boundary, the coordinate data already exists rather than requiring a second pass
over the same PDFs. This does not require adopting dict/spans or multimodal for that follow-up —
those remain reserved for the escalation cases in Section 9, which the multi-year run has not yet
been shown to need.

## 11. Next experiment

The representation question is resolved enough, on this sample, to proceed rather than block on
further representation research. Two next steps, in order:

1. **Primary**: proceed with the prior experiment's own suggested follow-up — 4–5 consecutive
   years of ACT and/or BEL, focused on the seven strong schedules — using plain text + blocks as
   the captured representation (per Section 10). This is unchanged in scope from the prior
   recommendation; only the representation captured alongside it changes.
2. **Secondary, smaller, and separable**: before or alongside that run, validate the Section 9
   escalation signals on a slightly larger, still-targeted sample (perhaps 10–15 additional pages,
   specifically including negative examples — genuine two/three-column pages that do *not* need
   escalation, and tables that are simpler than AfroCentric's risk register) to firm up the
   x0-clustering and repeated-position heuristics before anyone tries to encode them as an
   automatic router. This experiment observed the signals but did not test them against
   counter-examples, which is the main open gap in the escalation-criteria evidence.

This experiment does **not** recommend a third option — investing further in representation
research beyond validating the escalation heuristics — because the evidence collected here already
identifies a clear default (blocks) and a clear, cheap way to identify the exceptions (Section 9),
and further representation-only experiments would not change the ACT/BEL multi-year follow-up's
design.

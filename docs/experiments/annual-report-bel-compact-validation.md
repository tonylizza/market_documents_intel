# Experiment: Compact Cross-Issuer Validation on Bell Equipment (BEL)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. No corpus was republished. All extraction was performed against
`data/raw/BEL/{2018,2019,2020,2021,2022}/annual_report.pdf` via throwaway PyMuPDF scripts, with
intermediate text dumps and metric outputs written to a session-local scratch directory outside
the repository. This is a compact validation, not a new deep-dive: it assumes the architecture and
findings of the eight prior experiment docs in `docs/experiments/` (schedule localization,
extraction-representation bake-off, longitudinal schedule stability, within-schedule alignment,
lexical-change pilot, analytical-unit eligibility, structured-table comparison, structured-table
generalization) and does not re-litigate them. It reuses their established metric set, status
vocabulary (ADDED/RENAMED/MOVED/SPLIT/RESTRUCTURED/MERGED/EXTERNALIZED), and comparison-type
taxonomy (LEXICAL_ONLY, LEXICAL_WITH_NUMERIC_CONTEXT, STRUCTURED_COMPARISON_PREFERRED,
PRESENCE_STATUS_ONLY) without modification.

## 1. Executive summary

**Yes — the architecture validated on AfroCentric (ACT) transfers to Bell Equipment (BEL) with no
new architectural layer, no new ontology, no new metric family, and no new comparison modality.**

- **Prose path**: worked cleanly. A recurring, well-bounded, substantive semantic unit (the "Gross
  Margin" paragraph inside BEL's "Finance director's report," part of the `financial_performance`
  schedule) exists and is heading-anchored in every one of the five sampled years (2018–2022). It
  localizes, reconstructs, and aligns across years using exactly the prior experiments' methods
  (heading match, PyMuPDF plain text + blocks). One real, non-trivial source-reconstruction defect
  was found and corrected (see Section 3) — this is exactly the "manageable correction" class of
  issue the prior experiments anticipated, not a new failure mode.
- **Structured-table path**: worked cleanly. BEL's "Inherent risks / Risk mitigation factors"
  register (part of the `material_risks` schedule, nested inside "Strategic overview and risk
  management") reconstructs into a stable row (named risk) x two-column (inherent-risk text,
  mitigation-factors text) structure in every one of the five sampled years, using plain text +
  blocks with no font/dict inspection and no multimodal escalation. Real row-level content events
  (ADDED, RENAMED, SPLIT/RESTRUCTURED) were recovered and are fully representable with the existing
  status vocabulary from the longitudinal and within-schedule-alignment experiments.
- **Multimodal**: not needed anywhere in this validation. Every hazard encountered (heading
  displacement, a chart intervening between a narrative paragraph and its next heading, unlabeled
  vs. numbered risk rows) was resolved with plain text + blocks, consistent with every prior
  experiment's finding that BEL-class hazards are structural/positional, not visual/color-coded.
- **New architectural concepts required**: none. The one thing this validation needed that a naive
  implementation would have missed — anchoring a prose unit's end boundary on a recurring closing
  *sentence* rather than the next heading, because a chart can sit between them — is a refinement
  of unit-boundary detection already anticipated by the extraction-representation bake-off's own
  finding that charts inject extraction noise; it is not a new concept.
- **Is the project ready for implementation?** Yes. See Section 7.

## 2. Sample

- **Company**: Bell Equipment Limited (BEL).
- **Years**: 2018, 2019, 2020, 2021, 2022 — the requested range; all five years have usable PDFs
  at `data/raw/BEL/<year>/annual_report.pdf` (no substitution needed). This is the same five-year
  window used in the longitudinal-schedule-stability experiment, re-used here rather than
  re-selected.
- **Chosen prose disclosure**: the "Gross Margin" narrative sub-unit inside BEL's "Finance
  director's report" (`financial_performance` schedule — rated MOST STABLE for BEL by the
  longitudinal experiment, and explicitly not the fused/weak `leadership_narrative` schedule the
  brief flagged as a poor prose candidate for this company).
- **Chosen table disclosure**: BEL's "Inherent risks / Risk mitigation factors" register
  (`material_risks` schedule, nested inside "Strategic overview and risk management" every year —
  the schedule the schedule-localization and longitudinal experiments already identified as
  present, if unevenly labeled, in all five BEL years).

## 3. Prose validation

**Localization.** The `financial_performance` schedule ("Finance director's report") is present in
every sampled year, always as a heading-anchored, standalone section, exactly as the schedule-
localization and longitudinal-stability experiments already established. This validation did not
re-derive localization; it confirms the prior finding still holds on 2018–2022 and drills one level
further, into a named sub-unit.

**Source-faithful reconstruction.** Within the schedule, "Gross Margin" (capitalization varies:
"GROSS MARGIN" 2018, "Gross Margin"/"Gross margin" 2019–2022) is a recurring, exactly-headed
sub-unit in all five years — heading-string matching alone is sufficient to locate it, no semantic
reasoning required. A naive boundary rule (from this heading to the next heading, "Other operating
income") was tried first and **failed** on one year: in 2019, a bar chart's axis labels and
percentage figures ("2019 External Revenue Analysis - Geographic," region names, percentages) sit
between the narrative paragraph and the next heading and were swept into the "unit," corrupting
word counts and lexical scores. This reproduces, on a new company, the extraction-representation
bake-off's general finding that charts inject non-narrative noise into plain-text extraction. The
fix required no new representation: the unit's real boundary is its own recurring closing sentence
("...compared with X% in the prior year."), present in every year, and anchoring on it instead of
on the next heading recovers the correct paragraph in all five years — a manageable, deterministic
correction, not a structural blocker. One further wrinkle: the 2022 PDF wraps "prior" and "year"
across a line break ("...in the prior \nyear."), so the boundary regex had to tolerate embedded
whitespace — a routine PDF line-wrap issue, not a new hazard class.

**Cross-year alignment.** Trivial: the heading "Gross Margin" (case-insensitive) matches in all
five years with no fuzzy or semantic matching needed.

**Lexical metric sanity check.** Using the exact metric set from the lexical-change pilot (TF-IDF
cosine, unigram Jaccard, bigram Jaccard, rapidfuzz edit similarity, `difflib` sequence ratio, word
count) on the four adjacent-year transitions:

| Transition | Word count | TF-IDF cosine | Unigram Jaccard | Bigram Jaccard | Edit sim. | Seq. ratio |
|---|---|---:|---:|---:|---:|---:|
| 2018→2019 | 64→47 (−26.6%) | 0.752 | 0.481 | 0.351 | 0.760 | 0.480 |
| 2019→2020 | 47→127 (+170.2%) | 0.695 | 0.308 | 0.215 | 0.508 | 0.387 |
| 2020→2021 | 127→139 (+9.4%) | 0.720 | 0.259 | 0.142 | 0.586 | 0.188 |
| 2021→2022 | 139→101 (−27.3%) | 0.748 | 0.306 | 0.202 | 0.621 | 0.311 |

The metrics behave sensibly and match a manual reading of the underlying text: every transition
shares a stable boilerplate opening sentence ("The gross margin is dependent on the product and
geographic mix of sales, market conditions and exchange rates."), which keeps TF-IDF cosine
moderate-to-high (0.70–0.75) across all transitions regardless of how much the substantive
commentary changed, while bigram Jaccard drops much further (0.14–0.35) because the substantive
sentences that follow the boilerplate opener are reworded every year. The largest word-count swing
(2019→2020, +170%) correctly corresponds to the year Bell's finance director gives its most
detailed year-specific explanation (COVID-19 demand shock, foreign-currency losses on the Rand,
IFRS 15 refund-liability effects) — a real, substantively different disclosure, not an extraction
artifact. This is the same qualitative pattern (stable boilerplate framing + moderate-to-high
TF-IDF + lower bigram Jaccard) the lexical-change pilot found on ACT's short, template-heavy units,
confirming the metrics' behavior is company-agnostic on this class of unit rather than an ACT-only
result.

**Manual validation.** Raw extracted text around the unit was read directly for all five years
(2018, 2019, 2020, 2021, 2022 — exceeding the minimum of two), both before and after the boundary
fix; the corrected reconstruction matches the source PDF's paragraph content exactly in every year
checked (verified by reading the surrounding `get_text()` output alongside the block dump).
**Result: PASS.**

## 4. Table validation

**Source representation and reconstruction method.** `page.get_text("blocks")` alone, no
`dict`/span font inspection and no multimodal rendering, on every page checked (12 pages across the
five years). The register follows a consistent two-column block pattern in every year: a
left-column block (x0≈43–52) whose first line is the risk's name followed immediately by its
descriptive text, and one or more right-column blocks (x0≈248–302) holding the bullet-point
mitigation factors, at matching or nearby y0. Row identity is recovered from the left-column
block's first line (a short, title-case or all-caps risk name); column identity is recovered from
the recurring header block ("Inherent risks" / "Risk mitigation factors") plus each block's x0
band. This is a different low-level pattern from ACT's numeric remuneration tables (one block =
one row with newline-separated numeric cells) — here, one block-pair (left description + right
bullet list) = one row, and the "cell values" are prose/bullets rather than numbers — but it is
recovered with the identical tool (`get_text("blocks")`) and the identical governing principle
(x0-band column identity, y0-proximity row grouping) that the structured-table-comparison
experiment established on ACT. No new parsing framework was needed.

**Row/column alignment across years, with representative value-change events observed directly
(not assumed from prior docs):**

- **Stable core rows** (present, same name or a trivial capitalization/numbering change, every
  year): Competitor risk, Currency risk, Strategic alliance partners and key supplier relations
  risk, Political risks in the countries in which the group operates, Cyclical nature of the
  construction and mining equipment industry, Regulatory risk, Human capital, Global
  competitiveness, Niche product dependence, Lack of transformation — 10 of the original 2018 rows
  persist through 2022 with mitigation-bullet text revised nearly every year (e.g. Currency risk's
  mitigation bullets shift from "A group treasury policy is in place and a review of this policy
  by management and the board has been undertaken" (2018) to the shorter "A group treasury policy
  is in place." (2020+) — a real de-emphasis, not an extraction gap).
- **RENAMED row**: "Information Technology" (2018) → "Information Security and Digital
  disruption"/"Digital disruption" + "Cyber security" (2019 onward) — same underlying risk concept,
  relabeled and its mitigation bullets expanded to name cybersecurity explicitly, matching the
  RENAMED status already used for ACT's within-schedule units.
- **ADDED rows**: "Business Continuity due to power supply" and "Business continuity risk due to
  COVID-19" are both already present by 2019 (not first in 2020 as the schedule-localization
  experiment's summary implied for a different year window — directly confirmed here by full-text
  search, and consistent with this project's domain rule that publication date differs from period
  end: BEL's 2019 finance director's report is explicitly dated May 2020, after COVID-19 had
  already emerged, so the 2019-labeled report legitimately carries 2020-era risk content).
  "Business continuity due to supply chain failure" and "Climate change and environmental" are
  ADDED by 2020, both genuinely new named rows with no 2018 antecedent.
- **SPLIT + RESTRUCTURED + RENAMED event (2020→2021)**: the single unlabeled, undifferentiated
  15-row "Inherent risks" list of 2018–2020 is restructured into two explicitly numbered lists from
  2021 onward — a 12-item "KEY RISKS" list (the original core operating/commercial risks) and a
  separate 4-item "MATERIAL MATTERS" list (COVID-19, environmental, power supply, supply chain
  failure) — matching the schedule-localization experiment's independent finding that BEL's
  `material_risks` and `material_matters_operating_environment` schedules share one combined parent
  heading with no page break between them. This is a genuine schema-drift event, fully
  representable with the existing RESTRUCTURED/RENAMED/SPLIT vocabulary; it required no new event
  type.

**Footnotes**: none present in this specific table family (unlike ACT's remuneration tables); not
applicable here.

**Manual validation.** Full block dumps (y0/x0/first-line) were read directly for 2018 (pages
22–24), 2020 (pages 22–27), 2021 (pages 22–27), and 2022 (pages 20–24) — four year-instances,
exceeding the minimum of two — and cross-checked against the row/column reconstruction above;
row count, row order, and left/right column assignment matched the source text in every page
checked, with no cross-row contamination observed. **Result: PASS.**

## 5. ACT vs. BEL

| Dimension | ACT | BEL |
|---|---|---|
| Extraction difficulty | Low; plain text mostly clean, no heading displacement. | Moderate; the known heading-displacement quirk (title at bottom of the *previous* page's block list) recurs at every section start across all five years — but blocks (`y0` sort) resolve it exactly as the extraction-representation bake-off and longitudinal experiment already found, with zero new fixes needed here. |
| Semantic stability | Very high; 2022 governance redesign is the only major schema event across five years. | High but different in kind: BEL's schema stays structurally static (no MOVED events observed anywhere, per the longitudinal experiment) but its *labeling* churns more (unlabeled → numbered risk lists in 2021; fused leadership narrative every year, never splitting into CEO/Chair voices). |
| Table reconstruction difficulty | Low; numeric remuneration tables extract as one-block-per-row with newline-separated numeric cells. | Low, but structurally different; BEL's risk register extracts as a two-block-per-row pattern (description block + bullet-list block) rather than ACT's single-block-per-row numeric pattern. Recovery still needs only blocks, no dict/multimodal — same tool, different deterministic parse. |
| Issuer-specific handling required | A regex/heuristic for the numeric row-block pattern (established in the structured-table-comparison experiment). | A regex/heuristic for the closing-sentence prose boundary (this experiment) and for the two-column risk-block pattern (this experiment). Both are small, deterministic, company-specific parsing rules — exactly the kind of variation the task brief anticipated and explicitly said should not fail the architecture. |

No new taxonomy, metric, or comparison modality was introduced for either company; both companies'
issuer-specific quirks are absorbed as parsing-rule variations within the same four-stage pipeline
(localize → reconstruct → align → compare).

## 6. Blockers

None. Every hazard encountered (chart-interrupted prose boundary, two-block-per-row table layout,
unlabeled-to-numbered row renaming) was resolved deterministically with plain text + blocks and is
representable with the existing schedule/unit status vocabulary. No page in this validation
required `dict`/span font inspection or multimodal image reading.

## 7. Implementation decision

**B. PASS WITH MINOR IMPLEMENTATION CAVEATS**

No further research experiment is required before implementation.

Implementation caveats to carry into the build:

1. **Prose unit boundaries should anchor on a recurring closing/opening sentence pattern when
   available, not solely on "next heading."** BEL's Gross Margin unit demonstrated that a chart can
   sit between a narrative unit's real end and its next heading; the same charts-interrupt-prose
   hazard was already known from the extraction-representation bake-off but had not previously been
   observed to corrupt a *prose lexical-comparison* unit's boundary specifically — build the
   boundary-detection logic to prefer a stable in-unit anchor phrase when the schedule/unit
   definition has one, falling back to next-heading only when no such anchor exists.
2. **Table row-block patterns are not uniform across companies and should not be hard-coded to
   ACT's single-block-per-row numeric pattern.** BEL's risk register requires a two-block-per-row
   (description + bullet list) parse. The row/column reconstruction stage should be written against
   the general principle (x0-band = column, y0-proximity = row grouping) rather than against the
   specific block-count-per-row shape observed on ACT.
3. **Row identity for unlabeled-to-numbered transitions needs text-based (not purely positional)
   matching.** BEL's risk rows go from unlabeled prose titles (2018–2020) to numbered prose titles
   ("1. Competitor risk," 2021–2022) — deterministic row alignment across this transition requires
   stripping leading numbering tokens before matching risk names, a small but necessary
   normalization step to add to the alignment stage.
4. **PDF line-wrap tolerance.** Boundary-anchor regexes must tolerate embedded newlines/whitespace
   within a phrase (observed splitting "prior" and "year" across a line in the 2022 PDF); any
   phrase-anchored boundary rule should be built with whitespace-tolerant matching from the start
   rather than as a follow-up fix.

These are implementation-level parsing details, not open research questions — the architecture
itself (localize → reconstruct → align → compare, with lexical/structured/mixed/presence-only
comparison-type selection) is validated as transferable to a second issuer with a structurally
different report template.

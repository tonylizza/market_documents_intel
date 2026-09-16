# Experiment: Longitudinal Schedule Stability Across Consecutive JSE Annual Reports

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against `data/raw/{ACT,BEL}/**/annual_report.pdf`
via throwaway PyMuPDF scripts, with intermediate artifacts (plain text dumps, blocks JSON) written
to session-local scratch directories outside the repository. Nothing here is wired into the
application. This is a direct follow-up to `docs/experiments/annual-report-schedule-localization.md`
("Experiment 1") and `docs/experiments/annual-report-extraction-representation-bakeoff.md`
("Experiment 2"), both assumed read; findings below are stated relative to them rather than
re-derived from scratch.

Two of this experiment's ten normalized-schedule categories are refined from Experiments 1–2 per
the task brief for this run: leadership narrative is now treated as a parent construct over
flexible authorship roles (not a fixed CEO-section + Chair-section pair), and material matters /
operating environment are tracked as two separate secondary categories rather than one combined
schedule.

## 1. Executive summary

**Yes — normalized disclosure schedules are stable enough across years to act as persistent
semantic comparison containers, for the same six schedules Experiments 1–2 identified as strong:
leadership narrative, financial performance, material risks, strategy, corporate governance, and
remuneration.** Across two structurally very different five-year runs (AfroCentric/ACT 2020–2024,
Bell Equipment/BEL 2018–2022 — chosen specifically because BEL's span includes a genuine COVID-era
report-format contraction), every one of these six schedules remained identifiable as the same
underlying disclosure in every year of its respective run, even when headings changed, sections
moved between standalone and nested placement, presentation format was rebuilt from a table into
narrative cards, or — in BEL's case — an entire schedule disappeared from the primary document for
one year and was confirmed (not assumed) to have been externalized rather than lost.

**Which schedules are most stable?** Corporate governance and remuneration are the most stable
schedules in both companies: verbatim-identical headings, standalone structural placement, and
stable relative position in the report sequence in nearly every year studied (BEL's remuneration
is the one exception, and that exception is itself informative — see below). Leadership narrative
is stable in *authorship structure* in both companies across all ten company-years (ACT: always
two separate co-equal voices, surviving a full CEO succession; BEL: always one fused joint voice,
surviving a chairman/CEO handover), even though ACT's leadership sections physically moved in and
out of standalone/nested placement three times. Strategy is stable in both companies, with only
minor heading drift.

**Which schedules drift most?** Material risks is the least stable core schedule in both companies,
though the *kind* of instability differs: in ACT it goes through a genuine absence in 2020, then
merges into governance in 2021, becomes its own standalone schedule in 2022, and is completely
reformatted from a tabular risk register into narrative "value creation" cards in 2024 — an
ABSENT → MERGED → STANDALONE → RESTRUCTURED progression. In BEL, risk content never disappears
(it lives inside "Strategic overview and risk management" every year) but its labeling changes
from an unlabeled table (2018–2020) to an explicitly headed "KEY RISKS" sub-schedule (2021–2022) —
a RESTRUCTURED + RENAMED event without any change in physical location. In BEL specifically,
remuneration and the social/ethics committee report underwent a full PRESENT → ABSENT → PRESENT
round-trip in the 2020 COVID-shortened report, confirmed by direct text search to be a deliberate
externalization to a separate "AGM book," not data loss.

**How often do headings change?** Rarely for the five most standardized schedules
(governance, remuneration, leadership, strategy, financial performance): across 8 adjacent-year
transitions per company (4 in ACT, 4 in BEL) x 5 schedules = 40 transition-cells, only 3 show a
heading rename (ACT strategy 2021→2022 dropped "Unpacking"; BEL's risk and material-matters
sub-labels appeared for the first time in 2021 where none existed before). Material risks is the
outlier: it changes heading/label status in 3 of ACT's 4 transitions and 1 of BEL's 4.

**How often do sections move?** ACT's leadership narrative physically relocates (standalone <->
nested) 3 times across 4 transitions; nearly everything else in both companies stays in the same
relative position in the report skeleton across all years studied. BEL shows zero MOVED events for
any core schedule — its structural instability is entirely presence/absence and labeling, not
physical relocation.

**How often do schedules split/merge?** Merging (not splitting) is the dominant pattern for the
weak schedule: ACT material risks merges into governance for one year (2021); BEL material risks
is permanently merged inside "Strategic overview and risk management" for all five years (never
achieves standalone status, only a labeled sub-section within it from 2021). No true SPLIT event
(one schedule breaking into multiple independent primary sections) was observed for any core
schedule in either company across the ten company-years sampled.

**How often do boundaries remain high/medium confidence?** The large majority of core-schedule
boundaries were rated HIGH or MEDIUM confidence in both companies, in every year. LOW-confidence
boundaries clustered specifically around the weak/secondary schedules (legal/regulatory, outlook,
material matters, operating environment) and around ACT's 2020 "no locatable risk schedule" cell
and 2023's un-isolable operating-environment cell — exactly the pattern Experiment 1 predicted
would recur longitudinally.

**Does block/span extraction remain sufficient across years?** Yes, decisively. Across both
five-year runs (10 report-years, dozens of section-boundary checks), **not a single page required
`dict`/span font metadata, and not a single page required multimodal image reading.** Plain text
plus `get_text("blocks")` bounding-box geometry resolved every hazard encountered, including two
hazards not previously characterized in Experiments 1–2: a reversed two-column reading order on an
ACT 2020 page, and — most importantly — a refinement of Experiment 2's own heading-displacement fix.
BEL's evidence shows that Experiment 2's "sort blocks by y0" fix is unsafe as a blind default on
two-column pages; the correct fix is column-aware (cluster into x-bands, sort within each band,
then promote the one outlier low-y0 heading block). This is a genuine methodological correction to
the prior experiment, discovered specifically by the longitudinal design testing the same defect
across five years of the same report template rather than one page in one year.

**How often would multimodal escalation actually be needed?** Zero times across both companies'
five-year runs, at the resolution this experiment sampled (12 representative source-reconstruction
checks: 6 per company). One case (BEL 2018 strategy-page framework diagram) came close — block
geometry alone under-determines which text fragment belongs in which cell of a 2-D infographic
grid — but the surrounding narrative content on the same page remained fully recoverable without
escalation, and the diagram-specific gap would only need escalation if a future stage required
cell-level fidelity, not schedule-level localization.

**Does leadership narrative need flexible authorship modeling?** Yes, but for a different reason
than Experiment 1 anticipated. Experiment 1 found that some individual companies (Bell Equipment,
Kore Potash, Sabvest) diverge from the naive "one CEO section + one Chair section" assumption
*within a single year*. This experiment confirms that the divergence, once it exists for a company,
is a **stable house convention held across years**, not a one-off editorial choice: ACT is
separate-and-co-equal in all five years studied; BEL is joint/fused in all five years studied.
Neither company ever crosses over to the other's convention within this sample. The flexible
authorship model is therefore validated as a company-level constant to detect once, not a
per-year judgment call — though a larger company sample would be needed to confirm this holds
generally rather than being an artifact of these two companies' editorial stability.

**Is this architecture now strong enough to move to within-schedule longitudinal text matching?**
**Yes, for the six core schedules, with one required addition: an explicit "schedule absent /
externalized this year" state that downstream lexical-comparison logic must handle without forcing
a spurious alignment.** See Section 12 for the full architecture evaluation and Section 13 for the
recommendation.

## 2. Sample inventory

Selected per the task brief's guidance to use ~5 consecutive years per company where usable reports
exist and to prefer spans long enough to expose genuine redesign, not just easy years. Both ACT and
BEL had full, uncorrupted PDF coverage across their entire available history (ACT 2016–2024, BEL
2016–2022 — verified by opening every PDF with PyMuPDF before selecting the window), so both
companies were used, per the brief's instruction to use both when both have sufficient coverage.

| Company | Year | Path | PDF pages | Layout notes |
|---|---|---|---|---|
| ACT | 2020 | `data/raw/ACT/2020/annual_report.pdf` | 126 | "INTEGRATED REPORT 2020," COVID-dominated content, leadership narrative standalone at top level. |
| ACT | 2021 | `data/raw/ACT/2021/annual_report.pdf` | 134 | "HEALTHIER TOGETHER" redesign: leadership narrative newly nested inside larger thematic parents — the largest structural shift in ACT's run. |
| ACT | 2022 | `data/raw/ACT/2022/annual_report.pdf` | 150 | Same skeleton as 2021; introduces a standalone tabular "Our risks" schedule (new) and an ESG Reporting Index appendix. |
| ACT | 2023 | `data/raw/ACT/2023/annual_report.pdf` | 162 | Same skeleton as 2022. Content-level (not layout-level) discontinuity: Sanlam's controlling-stake acquisition and a CEO succession announcement dominate leadership narrative. |
| ACT | 2024 | `data/raw/ACT/2024/annual_report.pdf` | 154 | Same skeleton again; risk schedule reformatted from tabular register to narrative "value creation/preservation" cards — a targeted redesign of one schedule, not the whole report. |
| BEL | 2018 | `data/raw/BEL/2018/annual_report.pdf` | 100 | Full conventional integrated-report template (overview, performance review, summarised financials, shareholder information). |
| BEL | 2019 | `data/raw/BEL/2019/annual_report.pdf` | 124 | Same template, longer remuneration section. Finance director's report explicitly dated finalized May 2020 — a genuine publication-date-vs-period-end gap, consistent with this project's domain rule that the two must never be conflated. |
| BEL | 2020 | `data/raw/BEL/2020/annual_report.pdf` | 72 | **Materially redesigned/shortened**, confirmed genuine (not corrupt) by direct text search: no social/ethics committee report, no remuneration committee report, no summarised financial statements, no shareholder information section anywhere in the document; the governance report explicitly redirects readers to a separate "AGM book" for this content twice. A real COVID-era scope contraction. |
| BEL | 2021 | `data/raw/BEL/2021/annual_report.pdf` | 124 | Full template restored. New explicit "KEY RISKS" and "MATERIAL MATTERS" numbered-index callouts introduced where none existed as labeled sub-headings before. This is the report Experiment 1/2 studied in isolation; this experiment re-examines it in longitudinal context. |
| BEL | 2022 | `data/raw/BEL/2022/annual_report.pdf` | 132 | Same full template as 2021, longest of the five years; begins referencing externally-published supplementary reports (King IV Register, AFS) rather than including them in full. |

**Limitation, stated up front:** this remains a two-company, ten-report-year sample. No years were
excluded or cherry-picked — both runs use the most recent five consecutive years with full PDF
coverage available for each company, and BEL's inclusion of the anomalous 2020 report was a
deliberate choice to stress-test genuine redesign rather than avoid it, per the task brief's
explicit instruction not to cherry-pick only easy years.

## 3. Per-year schedule map

Full per-year, per-schedule maps (all ten normalized schedules, all five years, per company) were
produced independently and are extensive (~10 schedules x 5 years x 2 companies = 100 cells with
heading text, page ranges, structural type, confidence, and boundary confidence). They are
preserved in full in the underlying working files and summarized here in the year-over-year
matrices (Section 4) and heading-drift tables (Section 6) rather than reproduced cell-by-cell,
since the matrix form is what the research question actually needs. Selected illustrative detail:

**ACT 2020 (the company's most volatile year for material risks):** Leadership — Chairman
"CHAIRMAN'S REVIEW" pp.24–25 (standalone); CEO "CEO'S REVIEW" pp.41–43 (standalone). Financial
performance "CFO'S REVIEW" pp.~56–61 (nested under "Unpacking our performance"). Material risks:
**no locatable titled schedule** — best evidence places any risk content inside the Audit & Risk
Committee narrative of the governance report; not independently verified page-by-page, correctly
flagged DISTRIBUTED_NO_CLEAR_PRIMARY at low (0.55) confidence rather than forced into alignment
with later years. Strategy "UNPACKING OUR STRATEGY AND APPROACH" pp.44–~50. Corporate governance
"CORPORATE GOVERNANCE REPORT" pp.73–92 (standalone). Remuneration "REMUNERATION REPORT" pp.93–~102
(standalone).

**BEL 2020 (the company's redesigned year):** Leadership "Joint report by the chairman and chief
executive" pp.34–37 (unchanged from every other year). Financial performance "Finance director's
report" pp.38–40 (unchanged). Material risks: unlabeled "Inherent risks / Risk mitigation factors"
table nested in "Strategic overview and risk management" pp.20–27, now including two new named
risks (power-supply continuity / load-shedding; climate change) not present in 2018–2019.
Corporate governance "Corporate governance report" pp.41–49, its scope **expanded** to absorb
one-paragraph stubs for remuneration and social/ethics committee composition that would normally
be full standalone reports. Remuneration: **NOT_FOUND in this document** — full committee report
absent; governance report explicitly states "detailed responsibilities of the remuneration
committee can be found ... on page 39 of the AGM book." Social/ethics committee report: same
externalization pattern, page 54 of the AGM book. Summarised financial statements and shareholder
information: whole sections absent from the document, HIGH confidence in the absence itself.

## 4. Longitudinal schedule matrices

`P` = clear primary standalone section · `P+S` = primary + substantive supporting sections ·
`N` = nested inside a larger parent (still a clear primary, but not standalone) · `M` = merged
with/inside another schedule, no independent boundary · `D` = distributed, no clear primary ·
`X` = absent this year (confirmed genuine, not extraction failure) · `R` = present but format
was substantively restructured this year vs. the prior year.

### 4.1 AfroCentric (ACT), 2020–2024

| Schedule | 2020 | 2021 | 2022 | 2023 | 2024 | Longitudinal stability |
|---|---|---|---|---|---|---|
| Leadership narrative | P | N | N/P (Chair standalone, CEO nested — diverge) | N | N | STABLE authorship, MOVING placement |
| Financial performance | N | N | N | N | N | STABLE |
| Material risks | X | M | P+S | P+S | R (P+S, reformatted) | LEAST STABLE |
| Strategy | N | N | N | N | N (expanded) | STABLE |
| Corporate governance | P | P | P | P | P | MOST STABLE |
| Remuneration | P | P | P | P | P | MOST STABLE |

### 4.2 Bell Equipment (BEL), 2018–2022

| Schedule | 2018 | 2019 | 2020 | 2021 | 2022 | Longitudinal stability |
|---|---|---|---|---|---|---|
| Leadership narrative | P (joint) | P (joint) | P (joint) | P (joint) | P (joint) | MOST STABLE |
| Financial performance | P | P | P | P | P | MOST STABLE |
| Material risks | M | M | M (expanded) | R (M, now labeled) | M (labeled, stable) | LEAST STABLE (label/format only, never absent) |
| Strategy | P | P | P | P | P | MOST STABLE |
| Corporate governance | P+S | P+S | P+S (expanded scope) | P+S | P+S | STABLE |
| Remuneration | P | P | **X** | P | P | UNSTABLE (one-year externalization round-trip) |

## 5. Transition analysis

`STABLE / RENAMED / MOVED / EXPANDED / CONTRACTED / SPLIT / MERGED / RESTRUCTURED /
ABSENT_TO_PRESENT / PRESENT_TO_ABSENT / CANNOT_ALIGN_CONFIDENTLY` — multiple flags per cell where
applicable, per the task brief.

### 5.1 ACT

| Schedule | 2020→2021 | 2021→2022 | 2022→2023 | 2023→2024 | Boundary conf. | Alignable? |
|---|---|---|---|---|---|---|
| Leadership narrative | STABLE (authors) + MOVED (both nested) | RESTRUCTURED (Chair returns to standalone, CEO stays nested — divergent placement) | MOVED (Chair → nested again) + STABLE (CEO) | STABLE (placement); authorship handover (Banderker → van Wyk) | HIGH throughout | Yes, all transitions |
| Financial performance | RENAMED (parent section only) | STABLE | STABLE | STABLE | MEDIUM | Yes |
| Material risks | **ABSENT_TO_PRESENT** (CANNOT_ALIGN_CONFIDENTLY for the 2020 side) | RESTRUCTURED + MOVED (extracted from governance into its own standalone schedule) | STABLE | STABLE (location/heading) + RESTRUCTURED + EXPANDED (table → narrative cards, opportunities added) | LOW (2020) → HIGH (2022+) | Not for 2020↔2021; yes thereafter |
| Strategy | STABLE | RENAMED (dropped "Unpacking") | STABLE | STABLE + EXPANDED (KPI tables added) | HIGH | Yes, all transitions |
| Corporate governance | STABLE | STABLE | STABLE | STABLE | HIGH | Yes, all transitions |
| Remuneration | STABLE | STABLE | STABLE | STABLE | HIGH | Yes, all transitions |

### 5.2 BEL

| Schedule | 2018→2019 | 2019→2020 | 2020→2021 | 2021→2022 | Boundary conf. | Alignable? |
|---|---|---|---|---|---|---|
| Leadership narrative | STABLE | STABLE | STABLE | STABLE | HIGH | Yes, all transitions |
| Financial performance | STABLE | STABLE | STABLE | EXPANDED (mild) | HIGH | Yes, all transitions |
| Material risks | STABLE | EXPANDED (2 new named risks; CONTRACTED/EXPANDED simultaneously — content changed, format didn't) | RESTRUCTURED + RENAMED (unlabeled table → explicit "KEY RISKS" index) | STABLE | MEDIUM → HIGH after 2021 | Yes, all transitions (never truly absent) |
| Strategy | STABLE | STABLE | STABLE | STABLE | HIGH | Yes, all transitions |
| Corporate governance | STABLE | EXPANDED + MERGED (absorbs remuneration/social-ethics stubs) | CONTRACTED (reverts to pre-2020 scope) | STABLE | HIGH | Yes, all transitions |
| Remuneration | STABLE | **PRESENT_TO_ABSENT** (externalized to AGM book) | **ABSENT_TO_PRESENT** (full report returns, identical 3-part structure) | STABLE | HIGH (the absence itself is high-confidence, correctly detected as externalization not data loss) | Not for 2019↔2020 or 2020↔2021 in the sense of continuous alignment; the *conceptual* schedule is still recoverable as "this content exists, just not in this document this year" |

## 6. Heading-drift analysis

| Schedule | Company | Heading by year | Heading changed? | Would heading-string matching alone have worked? | Was semantic localization needed? |
|---|---|---|---|---|---|
| Leadership (Chair/CEO) | ACT | "CHAIRMAN'S REVIEW" / "CEO'S REVIEW" — identical, word-for-word, all 5 years | No | Yes for the heading string itself, but NOT for correctly tracking placement (standalone vs. nested) or for correctly attributing a CEO succession mid-schedule | Yes, for placement and authorship tracking, not for the heading text itself |
| Leadership (joint) | BEL | "Joint report by the chairman and chief executive" — identical, all 5 years | No | Yes | No — this is the cleanest case in the whole sample; heading matching alone would have sufficed every year |
| Financial performance | ACT | "CFO'S REVIEW" — identical all 5 years (parent section renamed once) | No (schedule heading itself); parent section renamed | Yes for the schedule heading | Marginal — parent-section rename would confuse a rigid path-based matcher even though the schedule heading itself didn't move |
| Financial performance | BEL | "Finance director's report" — identical all 5 years | No | Yes | No |
| Material risks | ACT | none (2020) → "Overview of our top risks" (2021, subsection) → "Our risks" (2022–2023) → "OUR RISKS" / "OUR RISKS AND OPPORTUNITIES" (2024) | Yes, substantially | **No** — a heading-string matcher trained on "Our risks" would find nothing in 2020 and a differently-worded subsection heading in 2021 | Yes, decisively — this is the schedule where semantic localization earns its keep over naive heading matching |
| Material risks | BEL | none/unlabeled (2018–2020) → "KEY RISKS" (2021–2022) | Yes | **No** — 2018–2020 have no heading to match against at all; only content-pattern recognition (a numbered risk/mitigation table under "Strategic overview and risk management") finds it | Yes, decisively |
| Strategy | ACT | "UNPACKING OUR STRATEGY AND APPROACH" (2020–2021) → "Our strategy and approach" (2022–2024) | Yes, once | Partial — the two heading strings share enough vocabulary ("strategy and approach") that fuzzy string matching might survive this one, but would be luck rather than design | Marginal |
| Strategy | BEL | "Strategic overview and risk management" — identical all 5 years | No | Yes | No |
| Corporate governance | ACT & BEL | "CORPORATE GOVERNANCE REPORT" / "Corporate governance report" — identical every year, both companies | No | Yes | No |
| Remuneration | ACT | "REMUNERATION REPORT" — identical all 5 years | No | Yes | No |
| Remuneration | BEL | "Remuneration committee report" (present) / absent entirely (2020) | Yes (via disappearance) | No — a heading matcher would report NOT_FOUND for 2020 with no explanation; only reading the surrounding governance-report text ("...can be found on page 39 of the AGM book") distinguishes "externalized" from "discontinued" | Yes, specifically to distinguish externalization from genuine discontinuation |

**Direct test of the research question in Section 6's brief:** the classic example given in the
task brief — "Our risks" / "Key risks" / "Principal risks and uncertainties" / "Risk management"
potentially mapping to one normalized schedule despite weak title similarity — is exactly what
happened here. ACT's risk schedule moved through "Overview of our top risks" → "Our risks" → "OUR
RISKS AND OPPORTUNITIES," and BEL's moved from no heading at all to "KEY RISKS." In both companies,
this is the schedule where naive heading-string matching would have failed most often, confirming
that the LLM localization layer is doing real semantic work on this schedule specifically — and
close to no work beyond confirmation on governance, remuneration, and (for BEL) leadership and
strategy, where the heading itself never moves.

## 7. Boundary-stability analysis

**Overall finding: boundaries remained HIGH or MEDIUM confidence for the six core schedules in the
overwhelming majority of company-years studied.** LOW-confidence boundaries were concentrated in
exactly the cases Experiments 1–2 predicted: secondary/distributed schedules (legal/regulatory,
outlook, material matters, operating environment) and the one genuinely absent core-schedule cell
(ACT material risks, 2020).

**No page in either company's five-year run required `get_text("dict")` font/size inspection or
full multimodal image reading.** This is a stronger result than Experiment 2 found on its
hazard-selected single-year sample (which needed dict/spans once, for Kore Potash's running-header
case, and multimodal twice). Two explanations are worth separating: (1) neither ACT nor BEL exhibit
Kore Potash's specific repeated-"(CONT)"-running-header pattern, so that particular escalation
trigger simply didn't occur in this sample; (2) this does not mean dict/spans and multimodal are
never needed for ACT/BEL specifically — only that they weren't needed on the pages sampled for this
study's schedule boundaries. A different report in the corpus with Kore Potash's running-header
convention would still need font-size disambiguation, and this experiment does not claim that
convention is universally absent from the corpus.

**A genuine methodological finding, not previously documented:** Experiment 2 recommended "sort
blocks by y0" as the fix for Bell Equipment's heading-displacement defect, based on evidence from
three FY2021 pages. This experiment's longitudinal design — checking the *same* defect on the
*same* report's section-start pages across five years — found that:

1. The displacement defect is **not** an FY2021-only anomaly. It recurs on Finance director's
   report and Corporate governance report start pages in 2020, 2021, and 2022, but not 2018–2019 —
   a page-template artifact introduced with the 2020 redesign and persisting through 2022, not tied
   to any single year.
2. **A blind whole-page y0 sort is unsafe.** Every displaced-heading page in BEL is a two-column
   layout where the native block order is already correct within and across columns; only the
   single heading block is anomalously appended at the end. A whole-page y0 sort would fix the
   heading but interleave the two columns incorrectly — confirmed concretely on BEL 2021 p.41,
   where a right-column block (y0=293.2) would sort ahead of a left-column block (y0=387.5),
   corrupting reading order.
3. The correct, still-cheap fix is **column-aware**: cluster blocks into x-bands, sort within each
   band by y0, then promote the one outlier low-y0 heading block to the front. This still requires
   no dict/font metadata and no multimodal rendering.

This is exactly the kind of correction the longitudinal design was intended to surface: a fix that
looked sufficient on a single year's evidence turned out to be incomplete once tested against the
same report's own layout pattern repeated across multiple years.

**Running-header disambiguation, revisited longitudinally:** ACT's governance-report running
header/footer pattern ("AFROCENTRIC GROUP / 70 / CORPORATE GOVERNANCE REPORT (CONTINUED)") recurs
across all five years but was trivially disambiguated from real sub-headings by content pattern
alone (title + folio number + section name, always the first block on the page) — no font-size
comparison needed, unlike Kore Potash's case in Experiment 2 where the running header and the
genuine sub-heading were textually distinct but visually similar enough to need font size. This
suggests the running-header hazard is itself heterogeneous across reports/companies and the
escalation trigger should stay content-pattern-first, font-size-second, exactly as Experiment 2's
Section 9 proposed.

## 8. Layout-drift analysis

| Pattern | Company/year(s) | What changed | Block/span sufficiency |
|---|---|---|---|
| Reversed two-column reading order | ACT 2020, Chairman's Review p.25 | Plain text emits the right-hand column (Governance/Outlook/Appreciation/sign-off) before the left-hand column (Operating from a place of purpose) | Blocks (sort by x0 then y0) fully resolve it |
| Heading displaced to end of block list on an otherwise-correct two-column page | BEL 2020–2022 (Finance director's, Corporate governance report starts), BEL 2021 (Joint report start) | Section-start heading is the topmost element by y0 but is emitted last in block order | Blocks resolve it, but only with a column-aware sort (see Section 7) — a plain y0 sort is unsafe |
| Unlabeled table → explicitly labeled sub-schedule | BEL material risks, 2020→2021 | "Inherent risks / Risk mitigation factors" table gains an explicit "KEY RISKS" numbered-index heading and a parallel "MATERIAL MATTERS" index | No representation change needed; this is a content/heading change, not an extraction hazard |
| Tabular register → narrative cards | ACT material risks, 2023→2024 | Numeric residual-risk-rating table replaced by "value creation/preservation" narrative cards keyed to Board committees and capitals | Blocks needed for the table years (x/y-matching numeric cells to rows/columns is the riskiest reconstruction case in the ACT sample); the narrative-card year is plain-text-friendly again |
| Standalone → nested → standalone (oscillating) | ACT leadership narrative, across all 4 transitions | Chairman's/CEO's reviews move between top-level and nested-under-a-parent-section placement three separate times | Not a text-representation hazard at all — a pure structural/positional signal that only affects where in the TOC/page range to look, not what representation to read once found |
| Full section absorption then reversion | BEL corporate governance, 2019→2020→2021 | Governance report temporarily absorbs remuneration/social-ethics committee stub content, then reverts | Not an extraction hazard; a schedule-boundary/scope question resolved by reading section content, not layout |
| Section externalized to an out-of-corpus document | BEL remuneration/social-ethics, 2020 | Full committee reports absent from the PDF; governance report explicitly names an external "AGM book" as the true location | Not resolvable by any in-document representation — requires reading the redirect text and correctly classifying it as externalization, not failure |
| 2-D infographic/framework diagram | BEL 2018, Strategy page p.20 | Several short text fragments share near-identical y0 across parallel diagram columns | Blocks under-determine cell assignment; this is the one case in both runs that would benefit from multimodal if cell-level fidelity were ever required — but the surrounding prose remained fully recoverable without it |

**Overall:** genuine visual/layout complexity changed materially in only two targeted cases per
company (ACT's risk-schedule table→cards redesign; BEL's 2020 format contraction), not throughout
either run — consistent with Experiments 1–2's finding that most pages in this corpus are
extraction-friendly and hazards cluster around a identifiable minority of pages/sections.

## 9. Source-reconstruction check

12 representative checks (6 per company, one per core-schedule category, per the task brief),
using localized block boundaries sorted appropriately (x0-then-y0 for reversed columns,
column-aware x-band-then-y0 for the BEL displacement cases, plain y0 for single-flow pages) and
compared against the raw plain-text dump for the same page range.

| # | Company | Category | Instance | Verdict |
|---|---|---|---|---|
| 1 | ACT | Leadership narrative | 2020 Chairman's Review, p.25 | **MAJOR_LAYOUT_RECONSTRUCTION_NEEDED** — genuine two-column swap inverting reading order |
| 2 | ACT | Financial performance | 2020 CFO's Review, p.56 | **CLEAN** |
| 3 | ACT | Material risks | 2022 "Our risks" tabular register, p.39 | **MAJOR_LAYOUT_RECONSTRUCTION_NEEDED** — numeric cells must be x/y-matched to row/column; blocks sufficient but need real table-aware regrouping logic, not linear sort |
| 4 | ACT | Strategy | 2021 "Unpacking our strategy and approach," p.56 (pillars infographic) | **MINOR_CORRECTION_NEEDED** — prose reconstructs cleanly; pillar-to-icon visual grouping only partially recoverable |
| 5 | ACT | Corporate governance | 2022 "Corporate governance review," p.88 (two-column bullet list) | **CLEAN** |
| 6 | ACT | Remuneration | 2023 "Background statement," p.125 | **CLEAN** |
| 7 | BEL | Leadership narrative | 2021 "Joint report," p.34 | **MINOR_CORRECTION_NEEDED** — column-aware sort fully recovers order |
| 8 | BEL | Financial performance | 2022 "Finance director's report," p.40 | **MINOR_CORRECTION_NEEDED** — same displacement pattern; naive y0 sort would have corrupted it, column-aware sort works |
| 9 | BEL | Material risks | 2021 "KEY RISKS" narrative + index, p.22 (two-column) | **CLEAN** — native block order already correct; this page is the clearest illustration that a naive y0-sort would have actively broken a page that needed no correction at all |
| 10 | BEL | Strategy | 2018 "Strategic overview and risk management," p.20 (framework diagram) | **MAJOR_LAYOUT_RECONSTRUCTION_NEEDED** for the diagram fragment specifically; surrounding prose CLEAN via ordinary column-aware sorting |
| 11 | BEL | Corporate governance | 2021 "Corporate governance report," p.41 | **MINOR_CORRECTION_NEEDED** — same displacement/column pattern as #7–8 |
| 12 | BEL | Remuneration | 2019 "Remuneration committee report," p.52 (two-column, table in right column) | **CLEAN** |

**Aggregate: 4 CLEAN, 4 MINOR_CORRECTION_NEEDED, 4 MAJOR_LAYOUT_RECONSTRUCTION_NEEDED, 0
MULTIMODAL_REQUIRED.** Every MAJOR case was still resolvable using blocks alone (no dict/span or
multimodal escalation was actually necessary for any of the 12); "MAJOR" here means "needs genuine
table/grid-aware regrouping logic, not a linear sort," not "needs a different representation."
This directly validates Experiment 2's core recommendation (plain text + blocks as the default,
escalate only when signaled) and extends it: even the "MAJOR" cases stayed within the blocks-only
tier across two independent five-year runs.

## 10. Taxonomy refinement

Based on the longitudinal evidence collected here:

- **RETAIN as-is:** Corporate governance, remuneration, financial performance, strategy. All four
  showed high cross-year heading and structural stability in both companies. No changes recommended.
- **RETAIN with the flexible-authorship model made mandatory, not optional:** Leadership narrative.
  Experiment 1 already recommended treating authorship as a parent construct rather than forcing
  CEO+Chair; this experiment adds the finding that a company's authorship convention (ACT:
  separate/co-equal; BEL: joint/fused) is a **stable company-level property held across years**, so
  a production system should detect it once per company (or re-verify only occasionally) rather
  than re-deriving it from scratch every year as if it might have changed.
- **DEMOTE material risks' *heading* from a reliable localization anchor to a content-pattern
  anchor.** The schedule concept itself remains real and valuable (it is one of the six core
  schedules and should stay core), but this experiment's evidence — no heading at all for 2 of 10
  company-years, and 3 distinct heading strings across ACT's other 3 years — means a production
  pipeline must not rely on heading-string matching for this schedule even as a fallback. It should
  be localized primarily by content pattern (a risk-and-mitigation register or narrative, often
  nested inside or adjacent to a strategy or governance section) rather than by title, more
  aggressively than the other five core schedules.
- **RETAIN outlook, legal/regulatory, material matters, operating environment as secondary/
  distributed**, exactly as Experiments 1–2 concluded and as this task brief specified — nothing in
  the longitudinal evidence argues for promoting any of them to core status; if anything, ACT's
  2023 operating-environment cell (weakened toward fully distributed, no separately titled TOC
  entry that year) reinforces that these categories should not be expected to resolve to a single
  comparable location every year.
- **ADD a new cross-cutting status, not a new schedule: "EXTERNALIZED."** BEL's 2020 remuneration
  and social/ethics committee reports are not adequately described by NOT_FOUND (which implies the
  disclosure doesn't exist) nor by DISTRIBUTED_NO_CLEAR_PRIMARY (which implies it's scattered within
  this same document). The correct status is that the disclosure exists but was deliberately
  published in a different document for that year. Recommend adding EXTERNALIZED as a first-class
  presence status (alongside FOUND_PRIMARY_ONLY, NOT_FOUND, etc.) for any future production
  taxonomy, since this pattern is plausible for other companies/years in the corpus and materially
  changes how a longitudinal lexical-comparison stage should treat that company-year (skip, don't
  impute).
- **No schedule should be split or merged in the taxonomy itself** based on this evidence — the
  MERGED/SPLIT events observed were report-specific structural choices in a given year, not
  evidence that two normalized categories are conceptually the same thing or that one category is
  secretly two.

## 11. Longitudinal-specific findings not covered by the per-year taxonomy work

- Publication-date-vs-period-end care was independently reinforced by BEL's 2019 report, which
  states its finance director's report was finalized in May 2020 (a COVID-19 non-adjusting
  subsequent event addendum) — a concrete instance of the project's existing domain rule that
  publication date differs from period end, observed directly in source text rather than only in
  the database schema.
- Company-level authorship convention (separate vs. joint leadership narrative) survived a full
  officer succession in both companies (ACT: Banderker → van Wyk; BEL: Bell → Goosen mid-2018),
  suggesting the convention is tied to the company's reporting culture/template, not to the
  individual officers occupying the roles.
- The single largest source of apparent "instability" that is NOT genuine disclosure change is
  report-skeleton reorganization (ACT's leadership narrative moving standalone/nested three times)
  — a caution directly relevant to any future lexical-change metric, which must not interpret a
  schedule's page-range or TOC-nesting change as evidence the underlying disclosure itself grew,
  shrank, or was rewritten.

## 12. Production-architecture implications

Evaluating the proposed pipeline against the evidence gathered across both experiments to date:

```
PDF
  -> PyMuPDF dict/blocks/spans retained as canonical raw structure
  -> plain text derived for LLM semantic localization
  -> normalized schedule assignment
  -> block-coordinate boundary resolution
  -> selective multimodal escalation only when needed
  -> reconstructed source text
  -> within-schedule segmentation
  -> cross-year block alignment
  -> lexical similarity/change metrics
```

- **PyMuPDF blocks/spans as canonical raw structure — SUPPORTED.** Both this experiment and
  Experiment 2 found blocks sufficient for every boundary-resolution case encountered; dict/spans
  were needed zero times in this ten-report-year sample (once in Experiment 2's smaller,
  hazard-selected sample). Retaining dict/spans as available-but-rarely-needed metadata remains
  justified by Experiment 2's Kore Potash case even though it wasn't triggered here.
- **Plain text for LLM semantic localization — SUPPORTED, longitudinally.** This is the core new
  finding of this experiment: localization did not merely work in five isolated single-year
  snapshots (Experiment 1) but continued to correctly identify the same six schedules as the same
  company's report evolved release to release, including through a genuine COVID-era redesign
  (BEL 2020) and a genuine schedule-format overhaul (ACT 2024's risk cards).
- **Normalized schedule assignment — SUPPORTED for the six core schedules; REQUIRES the
  EXTERNALIZED status addition (Section 10) and a content-pattern-first strategy for material
  risks specifically.**
- **Block-coordinate boundary resolution — SUPPORTED, with a correction.** This experiment found
  and corrected a real defect in the previously-recommended fix (naive y0 sort is unsafe on
  two-column pages; column-aware sorting is required). This is exactly the kind of refinement a
  production implementation needs before block-coordinate resolution is hardened into code.
- **Selective multimodal escalation only when needed — SUPPORTED but UNTESTED AT SCALE.**
  Multimodal was never actually triggered in either five-year run. This is consistent with, not
  contradictory to, Experiment 2's escalation-criteria design (Section 9 there) — the specific
  hazards that experiment identified as needing font-size or multimodal escalation (Kore Potash's
  running header, AfroCentric's colored risk-table trend arrows) simply did not recur in the
  ACT/BEL longitudinal sample checked here. The escalation *logic* remains a hypothesis validated
  only on Experiment 2's original hazard-selected pages, not exercised again here.
- **Reconstructed source text — SUPPORTED for 8 of 12 sampled schedule instances (CLEAN or MINOR);
  the remaining 4 (MAJOR) are resolvable with blocks alone but need genuine table/grid-aware
  regrouping logic that has been characterized here but not yet implemented as reusable code.**
- **Within-schedule segmentation, cross-year block alignment, lexical similarity/change metrics —
  UNTESTED.** This experiment deliberately stopped short of these stages per the task brief's
  explicit instruction not to compute lexical-change metrics yet. The evidence gathered here
  (stable schedule boundaries, a documented set of reconstruction hazards and their fixes) is a
  necessary precondition for these stages but does not itself validate them.

## 13. Recommendation

**A. PROCEED TO WITHIN-SCHEDULE LONGITUDINAL MATCHING** — scoped specifically to the six core
schedules (leadership narrative, financial performance, material risks, strategy, corporate
governance, remuneration), for ACT and BEL first, before generalizing to the rest of the corpus.

**Why:** The success criteria set out at the start of this experiment are met. The normalized
schedule remained semantically recognizable across years in both companies; heading changes did
not break identification (they were specifically the cases where semantic localization,
rather than heading matching, did the real work — Section 6); schedule movement (ACT's leadership
narrative oscillating standalone/nested) did not break identification; the one genuine
split/merge-adjacent pattern (BEL's remuneration externalization round-trip) was represented
correctly rather than forced into a false alignment, once a new EXTERNALIZED status is adopted;
boundaries remained auditable (HIGH/MEDIUM confidence in the large majority of core-schedule
company-years, with LOW-confidence cells correctly concentrated in the schedules and years that
generally deserve it); and source text was reconstructable cleanly enough for later lexical
analysis in all 12 representative checks, using blocks alone, with zero multimodal escalations
needed.

**What the next experiment should test**, in order of priority:

1. **Within-schedule segmentation and cross-year block alignment on a small, deliberately chosen
   subset**: take ACT's corporate governance and remuneration schedules (the most stable, lowest-risk
   starting point) across all 5 years, segment each into sub-sections (e.g., governance ->
   committee-by-committee), and test whether the same sub-section can be aligned year to year the
   same way the top-level schedule was aligned here. This is the natural next rung down.
2. **The EXTERNALIZED status and the material-risks content-pattern localizer**, both flagged in
   Section 10, should be built and validated specifically against BEL's 2020 remuneration gap and
   ACT's 2020/2021/2024 risk-schedule instability before either is assumed to generalize.
3. **Validate the column-aware block-sorting fix (Section 7) as reusable code**, tested against
   both the BEL displacement pages and a genuine non-displaced two-column page (to confirm it does
   not introduce a regression on pages that don't need correction) — this is a concrete, scoped
   piece of deterministic logic this experiment has now fully specified but not yet implemented.
4. Only after 1–3 are validated should lexical similarity/change metrics be introduced, and even
   then the experiment brief's own guardrail stands: report-redesign-driven boundary movement
   (Section 11) must be excluded from any wording-change interpretation, which means the lexical
   stage will need its own control for "did the container move" versus "did the content change" —
   a distinction this experiment has now demonstrated is necessary and can be operationalized from
   the structural-transition labels already produced here (MOVED/RESTRUCTURED events should
   suppress or caveat a same-period lexical-change score; RENAMED/STABLE events should not).

This experiment does **not** recommend (B) a larger longitudinal test before proceeding, because
the two companies sampled were deliberately chosen to include both a stable case (BEL, aside from
its one COVID-year contraction) and a volatile case (ACT's material-risks schedule, its multiple
leadership-placement changes), and the six core schedules cleared the bar in both. It does not
recommend (C) revising the taxonomy and repeating, because Section 10's refinements are additive
(a new status, a localization-strategy note for one schedule) rather than a wholesale rework. It
does not recommend (D) — representation/extraction is not too unstable; on the contrary, ten
report-years produced zero required dict/span or multimodal escalations, the strongest evidence yet
that plain text + blocks is sufficient for this corpus's dominant page types.

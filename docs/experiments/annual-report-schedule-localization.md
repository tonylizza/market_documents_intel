# Experiment: LLM-Based Schedule Localization for JSE Annual Reports

Status: exploratory proof of concept. No production pipeline, database, or published data was
touched. All analysis was performed against `data/raw/**/annual_report.pdf` via PyMuPDF text
dumps in a session scratch directory; nothing here is wired into the application.

## 1. Executive summary

**Yes, this appears viable as a replacement for a meaningful share of the current
passage-parsing rule engineering — but only for a subset of the ten normalized schedules, and
only as a *localization* layer, not a full substitute for deterministic extraction.**

Across five structurally very different JSE-listed annual/integrated reports (a glossy
franchise-retail integrated report, two conventional King-IV integrated reports, a UK
Companies-Act-style AIM/ASX/JSE mining-exploration report, and a compact investment-holding
report), an LLM working from plain per-page PyMuPDF text was able to:

- Correctly identify that "CEO Review", "Chairman's Review", "Financial Performance",
  "Material Risks", "Strategy", "Corporate Governance", and "Remuneration" are *real, recurring
  conceptual categories* that different reports realize under different headings, different
  page counts, and different degrees of concentration — without being given exact heading
  strings to match.
- Correctly recognize when a schedule genuinely does **not** exist in a report's own terms
  (e.g. Kore Potash has no individually authored CEO or Chair narrative at all — only a jointly
  signed Board "Strategic Report" — and no heading anywhere in the document contains the word
  "Outlook" or "Prospects") rather than forcing a match.
- Distinguish primary vs. supporting disclosure, and flag when a schedule's most *material*
  content actually lives outside its nominal home section (e.g. Spur's largest single litigation
  item is disclosed inside "Financial performance," not inside "Compliance and Safety").
- Recover exact heading text, page ranges, and start/end boundary evidence with enough
  precision to be auditable, in the majority of cases at HIGH or MEDIUM confidence.

**Were the normalized schedules recognizable across companies?** Yes, for 7 of 10 — CEO review,
chair review, financial performance, material risks, strategy, corporate governance, and
remuneration were recognizable (sometimes present, sometimes genuinely absent) using the same
conceptual definitions across all five companies, despite four different heading vocabularies
and two entirely different regulatory-report conventions (King IV integrated report vs. UK
Companies Act Strategic Report).

**Which schedules were easiest?** `corporate_governance`, `remuneration`, and `material_risks`
had a clear, well-bounded primary section in **all five** reports — these are apparently the
most standardized disclosures in this corpus regardless of company size, sector, or listing
convention. `chair_review`, `financial_performance`, and `strategy` had a clear primary in 4 of
5.

**Which were most ambiguous?** `legal_regulatory` was the weakest schedule by a wide margin:
only 2 of 5 reports had anything resembling a primary section, and even those were thin
(Sabvest: a single share-dealing policy page; Kore Potash: a two-sentence contingent-liability
note) or contested (Bell Equipment's "Legal and regulatory environment" subsection is two
paragraphs while the year's most material legal facts sit in the CEO/Chair joint narrative
instead). `outlook` was similarly weak — only 2 of 5 had a locatable primary, both very short,
and 3 of 5 were genuinely distributed with no anchor heading at all. `material_matters` /
`operating_environment` was mixed in a more interesting way: it is not that the concept is
missing, but that the two sub-concepts frequently do **not** coincide — AfroCentric and Bell
Equipment each have exactly one of "External environment" / "Material matters" as a distinct
section but not both consistently, and Sabvest has an "Operational environment" section but no
separate materiality section at all.

**How often was there a clear canonical section?** Across all 50 schedule/report cells, 27 were
`FOUND_PRIMARY_ONLY`, 9 were `FOUND_PRIMARY_AND_SUPPORTING`, 12 were
`DISTRIBUTED_NO_CLEAR_PRIMARY`, and 2 were `NOT_FOUND` (both `ceo_review`/`chair_review` for
Kore Potash). No cell was `NOT_APPLICABLE`. So a clear primary existed 36/50 times (72%),
concentrated heavily in governance, remuneration, and risk; distribution/absence concentrated
heavily in outlook and legal/regulatory.

**How often was information substantially distributed?** In 12 of 50 cells, and disproportionately
in the two schedules noted above (`legal_regulatory`: 3/5; `outlook`: 3/5) plus
`material_matters_operating_environment` (2/5) and the two Kore Potash `NOT_FOUND` narrative
schedules, which reflect a genuinely different report-authorship convention rather than
localization failure.

**Were boundaries generally identifiable?** Yes, for primary sections: most were rated HIGH or
MEDIUM boundary confidence, anchored to exact heading text and either a clean page-top start
plus a mid-page or page-top end, or an explicit "continued" labeling convention. LOW-confidence
boundaries clustered around (a) sections sharing one heading with an adjacent, differently-scoped
topic (Bell Equipment's combined "Strategic overview and risk management"), (b) sections nested
inside a much larger section under a repeated running header (Kore Potash's 32-page "CORPORATE
GOVERNANCE REPORT (CONT)"), and (c) single-sentence sections squeezed between two others on one
page (Sabvest's "7. Prospects").

**What failure modes appeared?**
1. **Reading-order corruption from page design**, not from multi-column prose per se — Spur's
   sidebar navigation labels are repeated on every page and pollute naive heading search; its
   section *titles* are frequently extracted at the bottom of the page they title rather than
   the top, because of z-order/layout placement, not text flow. Bell Equipment shows an
   analogous quirk (headings displaced to the bottom of the *previous* page's extraction).
2. **Repeated running headers masquerading as new sections** — "(CONT)" suffixes recurring
   across 20–32 consecutive pages (Kore Potash governance, Bell Equipment's performance-review
   nav captions) create false positive section boundaries for any heading-matching approach that
   does not distinguish a running header from a genuine sub-heading.
3. **Shared headings covering two different schedules** — Bell Equipment's single "Strategic
   overview and risk management" heading covers both `strategy` and `material_risks` content
   with no internal sub-heading marking the transition; the report's own "MATERIAL MATTERS" list
   is formatted identically to and immediately abuts "KEY RISKS" with no page break.
2. **Two-column/side-by-side panel interleaving** — Spur's risk-register pages present risks in
   pairs of side-by-side panels; PyMuPDF's linear extraction alternates between fields of two
   different risks rather than completing one risk before the next.
4. **Genuine source-document defects** — Sabvest's PDF mislabels one heading "6.10" where it
   should read "6.11" (confirmed a document typo, not an extraction artifact) — a reminder that
   ground truth itself is not always internally consistent.
5. **Authorship-convention mismatch with the taxonomy's implicit assumptions** — the taxonomy
   assumes distinct CEO and Chair voices exist; in 2 of 5 reports they are fused (Bell Equipment:
   one jointly authored narrative) or entirely different in form (Kore Potash: UK Strategic
   Report convention with no individual officer narrative; Sabvest: the Chairman's Letter
   effectively absorbs the CEO-review role, leaving the CEO's own voice to two paragraphs of
   "Commentary and conclusion").

## 2. Sample inventory

`data/raw` contains six ticker directories (`ACT`, `BEL`, `KP2`, `SBP`, `SDL`, `SUR`), each with
one `<year>/annual_report.pdf`. `SBP`'s 2016–2022 subdirectories exist but are empty (those
years' downloads failed as non-PDF content per `data/report_manifest.csv`); usable PDFs exist for
`SBP` 2023–2025 only. Company full names and years were cross-checked against
`data/all_metadata.csv` and `data/report_manifest.csv`.

The five selected reports, chosen to maximize company diversity, sector diversity, size
diversity, and structural/design diversity within the available corpus:

| # | Company | Ticker | Year | Path | PDF pages | Structure / layout | Reason selected |
|---|---|---|---|---|---|---|---|
| 1 | Spur Corporation Limited | SUR | 2024 | `data/raw/SUR/2024/annual_report.pdf` | 208 | Heavily designed magazine-style "integrated report" with a persistent 9-group sidebar nav repeated on every page, pull-quotes, icon-driven material-issue index, and a real 54-entry PDF bookmark tree. Restaurant/franchise retail sector. | The highly designed/free-form end of the spectrum; largest report in the sample; richest TOC. |
| 2 | AfroCentric Investment Corporation Limited | ACT | 2022 | `data/raw/ACT/2022/annual_report.pdf` | 150 | Single-column narrative "Integrated Annual Report" with dense infographic/heat-map pages, no embedded PDF bookmarks, but a reliable printed table of contents. Healthcare/investment-holding sector. | Different sector (healthcare holding) and no bookmarks, forcing pure text-based heading discovery. |
| 3 | Bell Equipment Limited | BEL | 2021 | `data/raw/BEL/2021/annual_report.pdf` | 124 | Conventional single-column, text-heavy integrated report with a joint chairman/CEO narrative (not two separate reviews) and a heading-extraction-order quirk (titles displaced to page bottoms). Industrial/heavy-equipment manufacturing sector. | The "relatively conventional" comparison point; industrial manufacturing sector not otherwise represented; surfaces a co-authored CEO/Chair narrative as a taxonomy stress case. |
| 4 | Kore Potash plc | KP2 | 2023 (FY2022) | `data/raw/KP2/2023/annual_report.pdf` | 117 | UK Companies Act 2006 / AIM style report (dual/triple-listed AIM/ASX/JSE), not a King-IV integrated report; pre-revenue potash-exploration company; real PDF bookmarks with 77 entries. | Deliberately the most structurally different report available — a pre-revenue explorer under a different disclosure regime, expected (and confirmed) to lack several schedules entirely. Mining sector. |
| 5 | Sabvest Capital Limited | SBP | 2024 | `data/raw/SBP/2024/annual_report.pdf` | 50 | Compact, plain, numbered-section (1–17 plus 3 annexures) integrated report for a small investment holding company (~9 employees). No embedded PDF bookmarks. | The shortest and plainest report available; investment-holding sector; tests whether the taxonomy over-fits to larger, more elaborate reports. |

**Limitation:** the raw corpus itself is small (only six companies with usable PDFs, most with a
single year of coverage in the 2023–2025 window). The sample therefore favors distinct companies
over distinct years of the same company — cross-year structural drift within one company was not
tested here and would need a follow-up experiment (e.g. ACT or BEL across several of their 2016–2024
years, since those two companies have the longest available runs). `SDL` (Southern Palladium,
60 pages) was excluded only to keep the sample at five while maximizing sector spread; it would
be a reasonable sixth report in a larger run.

## 3. Per-report schedule map

Full per-report analyses (overall structure notes, summary tables, detailed boundary write-ups,
and machine-readable JSON) were produced independently for each report and are reproduced in
full below. `start_page`/`end_page` are PDF page indices (1-based) unless noted; printed/running
page numbers are given in the source write-ups where they differ from the PDF index.

### 3.1 Spur Corporation Limited (SUR) — FY2024

Overall structure: a 9-group sidebar-navigation design repeated on every page; section titles are
frequently extracted out of visual order (at the bottom of the page they title, or interleaved
with body text) due to graphic placement, not multi-column prose. Running footer = PDF page index
− 1 (verified). No standalone Material Risks or Outlook chapter; the real risk register is nested
inside Governance.

| Normalized schedule | Status | Actual heading | Primary page range | Supporting page ranges | Confidence | Notes |
|---|---|---|---|---|---|---|
| CEO Review | FOUND_PRIMARY_ONLY | "A Message from our CEO" | 10–11 | — | 0.90 | Clean, contiguous; CEO named (Val Nichas). |
| Chair Review | FOUND_PRIMARY_ONLY | "Introduction from our Chairman" | 7–9 | — | 0.90 | Includes a "Looking forward" outlook subsection. |
| Financial Performance | FOUND_PRIMARY_ONLY | "Financial performance" | 97–98 | — | 0.85 | CFO-voiced; also embeds contingent-liability/legal and audit disclosures. |
| Material Risks | FOUND_PRIMARY_ONLY | "Key group risks" (R1–R8) | 173–177 | 3 (icon index), 33 (risk matrix) | 0.80 | Substantive per-risk cause/mitigation/impact tables, nested in Governance. |
| Strategy | FOUND_PRIMARY_ONLY | "Our strategy and business model" (+ sub-areas) | 17–31 | — | 0.75 | One long contiguous block; internal sub-boundaries not precisely separable. |
| Outlook | DISTRIBUTED_NO_CLEAR_PRIMARY | "Looking forward" (chair); forward statements (CEO) | 9; 10–11 | 8, 97–99 | 0.55 | No standalone Outlook section. |
| Corporate Governance | FOUND_PRIMARY_ONLY | "GOVERNANCE REVIEW" | 164–184 | — | 0.85 | 21-page section; risk register carved out separately. |
| Remuneration | FOUND_PRIMARY_AND_SUPPORTING | "Remuneration POLICY" / "Remuneration REPORT" | 107–136 | — | 0.90 | Two contiguous sub-sections treated as one schedule. |
| Legal / Regulatory | DISTRIBUTED_NO_CLEAR_PRIMARY | "COMPLIANCE AND SAFETY" | 185–187 | 98 (contingent liability/litigation), 8 (chair) | 0.65 | Largest litigation item (GPS Food Group arbitration) sits in Financial performance, not Compliance and Safety. |
| Material Matters / Env. | DISTRIBUTED_NO_CLEAR_PRIMARY | "Determining our material matters" (process) | 5 | 3, 7–8, 10 | 0.55 | No dedicated Material Matters or Operating Environment chapter; narrative lives inside Leadership Messages. |

**Notable boundary case — material_risks.** Risks are presented in side-by-side panel pairs on
shared pages (e.g. R6/R7 share PDF page 176); PyMuPDF's linear text extraction alternates between
two risks' "CAUSES" / "RESIDUAL RISK MITIGATION CONTROLS" / "IMPACT" fields rather than completing
one risk before the next — the clearest example in the sample of two-column layout corrupting
naive top-to-bottom reading order even though the section itself is unambiguous and well-headed.

**Notable boundary case — legal_regulatory.** This is the sample's clearest instance of a
well-headed "closest primary" section (Compliance and Safety) still being the *wrong* answer for
completeness: the report's single most material legal disclosure (a R95.8m–R167.0m arbitration)
is told entirely within Financial performance's "Contingent liability" paragraph, two sections
away from where a reader (or a naive keyword matcher) would look.

### 3.2 AfroCentric Investment Corporation Limited (ACT) — FY2022

Overall structure: single-column narrative with infographic/heat-map pages that fragment in
extraction; no PDF bookmarks but a reliable printed TOC (PDF page = printed page + 4). Notably,
the report explicitly self-documents (in a boxed "Outlook" explainer on page 8) that its own
outlook content is deliberately spread across seven named sections.

| Normalized schedule | Status | Actual heading | Primary page range | Supporting page ranges | Confidence | Notes |
|---|---|---|---|---|---|---|
| CEO Review | FOUND_PRIMARY_ONLY | "CEO'S REVIEW" | 50–53 | — | 0.95 | Signed Ahmed Banderker, Group CEO; contains internal Outlook subsection. |
| Chair Review | FOUND_PRIMARY_ONLY | "CHAIRMAN'S REVIEW" | 10–11 | — | 0.95 | Signed Dr Anna Mokgokong, Chairman. |
| Financial Performance | FOUND_PRIMARY_ONLY | "CFO'S REVIEW" | 60–65 | 66–70 (data tables, not narrative) | 0.90 | Signed Hannes Boonzaaier, Group CFO. |
| Material Risks | FOUND_PRIMARY_ONLY | "Our risks" | 38–41 | — | 0.90 | King IV/COSO/ISO 31000-aligned; risk register + heat map. |
| Strategy | FOUND_PRIMARY_ONLY | "Our strategy and approach" | 54–58 | — | 0.85 | Strategic pillars, KPI table, capital trade-offs. |
| Outlook | DISTRIBUTED_NO_CLEAR_PRIMARY | "Outlook" subsections (chair & CEO reviews) | 11; 52–53 | Explicit self-declared list of 7 sections (p.8) | 0.80 | Report itself states outlook is deliberately distributed. |
| Corporate Governance | FOUND_PRIMARY_ONLY | "CORPORATE GOVERNANCE REPORT/REVIEW" | 87–108 | — | 0.95 | King IV-aligned; board, committees, IT governance, ethics. |
| Remuneration | FOUND_PRIMARY_ONLY | "REMUNERATION REPORT" | 109–122 | — | 0.95 | Policy, implementation, advisory votes. |
| Legal / Regulatory | DISTRIBUTED_NO_CLEAR_PRIMARY | material matter "5. Legal, regulatory..." + governance compliance subsection | 44; 106–108 | — | 0.70 | No dedicated litigation section; both locations report a clean/no-incidents position. |
| Material Matters / Env. | FOUND_PRIMARY_AND_SUPPORTING | "External environment" **and** "Our material matters" (kept distinct) | 26–30; 42–48 | Our stakeholders (31–36) sits between them | 0.90 | Two genuinely separate, separately paginated sections — not collapsed. |

**Notable boundary case — outlook.** AfroCentric is the only report in the sample that
*explicitly documents its own distribution strategy* for a schedule: a front-matter boxed
callout literally titled "Outlook" states "Outlook information can be found throughout this
report" and names the seven sections (Chairman's review, External environment, Material matters,
CEO's review, Strategy, Our performance, CFO's review) that carry it. This is strong direct
evidence that `DISTRIBUTED_NO_CLEAR_PRIMARY` is sometimes not a localization failure but the
report's own intentional design.

**Notable boundary case — material_matters_operating_environment.** "External environment"
(pp.26–30) and "Our material matters" (pp.42–48) are five pages apart, separated by an
intervening "Our stakeholders" section, each with its own TOC entry and its own internal
structure (macro trend cards vs. a numbered materiality-assessed list) — a clean confirmation
that these two normalized-schedule sub-concepts are not interchangeable and should not be
collapsed, exactly as the task brief anticipated.

### 3.3 Bell Equipment Limited (BEL) — FY2021

Overall structure: conventional single-column report, reliable printed TOC (PDF page = printed
page + 2), no bookmarks. A distinctive extraction-order artifact recurs throughout: section
titles are extracted at the *bottom* of the page they title rather than the top. The chairman
and CEO write one **joint** narrative report rather than two separate reviews.

| Normalized schedule | Status | Actual heading | Primary page range | Supporting page ranges | Confidence | Notes |
|---|---|---|---|---|---|---|
| CEO Review | FOUND_PRIMARY_ONLY (co-located) | "Joint report by the chairman and chief executive" | 34–37 | — | 0.55 | No CEO-only narrative exists. |
| Chair Review | FOUND_PRIMARY_ONLY (co-located) | Same section as CEO review | 34–37 | — | 0.55 | No chairman-only narrative exists. |
| Financial Performance | FOUND_PRIMARY_AND_SUPPORTING | "Finance director's report" | 38–40 | "Financial" subsection in Joint report, p.35 | 0.90 | Clear 3-page CFO-style narrative. |
| Material Risks | FOUND_PRIMARY_AND_SUPPORTING | "KEY RISKS" (within combined heading) | 22–26 | "Risk Management" in governance report, p.48 | 0.85 | Two-column risk/mitigation table; immediately abuts Material Matters, no page break. |
| Strategy | FOUND_PRIMARY_ONLY | "Strategic overview and risk management" (vision/objectives) | 20–21 | — | 0.75 | Shares one heading with material_risks; strategy content is table-formatted. |
| Outlook | FOUND_PRIMARY_AND_SUPPORTING | "Future Outlook" (Joint report) | 37 | "Looking ahead" (FD report), p.40 | 0.85 | Two distinct mid-page sub-headings, both substantive. |
| Corporate Governance | FOUND_PRIMARY_ONLY | "Corporate governance report" | 41–49 | — | 0.90 | 9 pages; board/committee structure, King IV, ethics. |
| Remuneration | FOUND_PRIMARY_ONLY | "Remuneration committee report" | 53–66 | — | 0.95 | 4 numbered sub-sections; signed board approval. |
| Legal / Regulatory | FOUND_PRIMARY_AND_SUPPORTING | "Legal and regulatory environment" (within governance) | 49 | FSCA/JSE investigation disclosures (Joint report, 36–37); APDP content (83–84) | 0.65 | Named subsection is 2 paragraphs; the year's most material legal facts are told in the Joint report instead. |
| Material Matters / Env. | FOUND_PRIMARY_ONLY | "MATERIAL MATTERS" (within combined heading) | 26–27 | Materiality process (front matter, pp.2–3) | 0.80 | No distinct "Operating Environment" section exists anywhere (confirmed by keyword search) — genuinely absent, not collapsed. |

**Notable boundary case — joint CEO/Chair report.** Bell Equipment is the clearest stress test of
the taxonomy's implicit one-officer-per-schedule assumption: `ceo_review` and `chair_review`
resolve to the *identical* page span because the company simply does not produce two separate
narratives. The LLM correctly identified this rather than arbitrarily splitting the joint text or
inflating confidence — both schedules were scored at a reduced 0.55 to reflect that the match is
real but imperfect against the schedule's definition.

**Notable boundary case — extraction-order quirk.** Every major section title in this report
("Joint report by the chairman and chief executive," "Finance director's report," "Corporate
governance report," "Social, ethics and transformation committee report") is extracted by
PyMuPDF at the bottom of the page it titles, immediately before the next page marker — a
one-page displacement trap for any heading detector that assumes titles appear at the top of
their own page.

### 3.4 Kore Potash plc (KP2) — FY2022 (labeled Annual Report 2022, filed 2023)

Overall structure: a UK Companies Act 2006 / AIM-style report for a pre-revenue potash explorer —
structurally the most different report in the sample. Real PDF bookmarks are broadly reliable.
Clean single-column layout with no design-driven reading-order corruption, but a 32-page
"CORPORATE GOVERNANCE REPORT (CONT)" running header creates its own ambiguity.

| Normalized schedule | Status | Actual heading | Primary page range | Supporting page ranges | Confidence | Notes |
|---|---|---|---|---|---|---|
| CEO Review | **NOT_FOUND** | — | — | pp.7–23 (joint Board narrative) | 0.05 | No individually authored CEO narrative exists anywhere. |
| Chair Review | **NOT_FOUND** | — | — | pp.7–23 (joint Board narrative) | 0.05 | No individually authored Chair narrative exists anywhere. |
| Financial Performance | DISTRIBUTED_NO_CLEAR_PRIMARY | "SUMMARY OF FINANCIALS" (bullets) | 8 | 24 (Operating Results), 24–25 & 31–32 (Going Concern) | 0.55 | Bullet-point/liquidity-focused; no CFO narrative — consistent with pre-revenue status. |
| Material Risks | FOUND_PRIMARY_ONLY | "POSITION AND PRINCIPAL RISKS" | 17–19 | 49–50 (Audit & Risk Committee) | 0.85 | Clear risk-by-risk section with mitigations. |
| Strategy | DISTRIBUTED_NO_CLEAR_PRIMARY | "BUSINESS MODEL" (1 paragraph) | 17 | 12 (KPIs), 35 (Governance Code response) | 0.35 | No dedicated strategic-pillars section. |
| Outlook | DISTRIBUTED_NO_CLEAR_PRIMARY | "Viability Assessment" | 12–13 | 10 (Next Steps), 31–32 (Going Concern) | 0.50 | No "Outlook"/"Prospects" heading exists anywhere (confirmed by full-text search). |
| Corporate Governance | FOUND_PRIMARY_ONLY | "CORPORATE GOVERNANCE REPORT" | 34–65 | — | 0.90 | UK Code-structured; Remuneration nested inside as a sub-section. |
| Remuneration | FOUND_PRIMARY_ONLY | "REMUNERATION REPORT" | 53–62 | 51–52 (Remuneration & Nomination Committee) | 0.85 | Nested inside governance under the same running header. |
| Legal / Regulatory | FOUND_PRIMARY_ONLY | "NOTE 23: CONTINGENT LIABILITIES" | 113 | 31 (boilerplate negative statement) | 0.40 | Only substantive item: a two-sentence unfair-dismissal claim. |
| Material Matters / Env. | DISTRIBUTED_NO_CLEAR_PRIMARY | none dedicated | — | 7–8, 17–19, 11–12 | 0.40 | Market/country/climate context folded entirely into Principal Risks. |

**Notable boundary case — ceo_review/chair_review NOT_FOUND.** This is the sample's cleanest
negative result and arguably its most valuable evidence: the "REVIEW OF OPERATIONS AND STRATEGIC
REPORT" (pp.7–23) is explicitly presented in the collective voice of "The Board of Directors" and
jointly signed by both the Non-Executive Chairman and CEO on the same signature block — this is a
different *disclosure regime* (UK Companies Act s.414A/s.172 Strategic Report), not a missing or
mis-extracted section. The LLM correctly declined to force either schedule onto this joint
narrative.

**Notable boundary case — outlook, genuinely absent heading.** A full-text search across all 117
pages confirmed zero occurrences of "Outlook" or "Prospects" as headings anywhere in the
document — the strongest possible evidence (short of manual page-by-page reading, which was also
done) that this is a true absence rather than a localization miss.

### 3.5 Sabvest Capital Limited (SBP) — FY2024

Overall structure: a compact 50-page numbered-section report (1–17 plus 3 annexures) for a small
investment holding company. No PDF bookmarks. The Chairman's Letter effectively absorbs the
CEO-review role.

| Normalized schedule | Status | Actual heading | Primary page range | Supporting page ranges | Confidence | Notes |
|---|---|---|---|---|---|---|
| CEO Review | DISTRIBUTED_NO_CLEAR_PRIMARY | (none dedicated) | — | 5 (attribution line), 42–43 ("17. Commentary and conclusion") | 0.35 | Chairman's Letter fills the narrative role instead. |
| Chair Review | FOUND_PRIMARY_ONLY | "CHAIRMAN'S LETTER TO SHAREHOLDERS" | 2–3 | — | 0.97 | Full standalone narrative; unambiguous. |
| Financial Performance | FOUND_PRIMARY_AND_SUPPORTING | "6.5 Commentary on the 2024 Financial Results" | 16 | 16–17 (growth/resources), 18–25 (per-investee narrative) | 0.85 | Short explicit primary; extensive supporting detail. |
| Material Risks | FOUND_PRIMARY_ONLY | "10. Risk report" | 38–39 | — | 0.90 | Explicit graded risk watch list table. |
| Strategy | FOUND_PRIMARY_AND_SUPPORTING | "4. Strategies, business model and performance indicators" | 6–7 | 45–47 (Annexure 2: Investment Policy) | 0.93 | Clear bulleted strategic pillars. |
| Outlook | FOUND_PRIMARY_ONLY | "7. Prospects" | 25 | Chairman's Letter (near-duplicate wording), p.2 | 0.55 | Genuine heading, but content is one sentence. |
| Corporate Governance | FOUND_PRIMARY_ONLY | "9. Corporate governance" | 27–38 | — | 0.95 | Longest schedule in the document; King IV Principle-by-Principle. |
| Remuneration | FOUND_PRIMARY_ONLY | "11. Remuneration report" | 38–42 | — | 0.95 | Full policy + per-director implementation table. |
| Legal / Regulatory | DISTRIBUTED_NO_CLEAR_PRIMARY | "Principle 13" + "12. Code of share dealing" | — | 36, 43 | 0.40 | No dedicated legal/regulatory section; embedded in governance. |
| Material Matters / Env. | FOUND_PRIMARY_ONLY (environment only) | "3. Operational environment" | 6 | — | 0.60 | "Material matters" as a distinct concept is genuinely NOT_FOUND — only a generic one-sentence assurance statement exists. |

**Notable boundary case — ceo_review absorbed by chair_review.** Unlike Bell Equipment (a fused
joint report) or Kore Potash (no individual narrative at all), Sabvest shows a third pattern: two
formally separate roles exist, but the CEO's own contribution is reduced to a one-sentence
authorship attribution ("The report is presented on behalf of the Board by the Chief Executive
Officer") plus a two-paragraph closing note that explicitly defers back to the Prospects section
rather than restating it — the substantive "performance narrative" work is done entirely by the
Chairman's Letter. This is a third distinct failure mode for the CEO/Chair pairing, alongside
Bell Equipment's fusion and Kore Potash's absence.

## 4. Machine-readable representation

Each per-report analysis produced a JSON object in the following shape (schema matches the task
brief). Full JSON for all five reports:

<details>
<summary>SUR 2024</summary>

```json
{
  "company": "SUR",
  "company_name": "Spur Corporation Limited",
  "year": 2024,
  "document": "data/raw/SUR/2024/annual_report.pdf",
  "schedules": [
    {"schedule": "ceo_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "A Message from our CEO", "start_page": 10, "end_page": 11, "start_text": "Val — 'We envision a future where everyone has a place at the table.'", "end_before_text": "OUR OPERATIONS (divider page)"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "HIGH", "reasoning_summary": "Clean two-page CEO narrative (Val Nichas), signed."},
    {"schedule": "chair_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Introduction from our Chairman", "start_page": 7, "end_page": 9, "start_text": "Mike — 'The group is well positioned for further growth and transformation...'", "end_before_text": "A Message from our CEO"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "MEDIUM", "reasoning_summary": "Three-page chairman narrative (Mike Bosman) including a 'Looking forward' outlook passage; heading extracted out of visual order."},
    {"schedule": "financial_performance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Financial performance", "start_page": 97, "end_page": 98, "start_text": "Cristina — 'A good trading performance led to continued solid growth...'", "end_before_text": "Operational performance"}, "supporting": [], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "CFO-voiced narrative also embedding contingent-liability/litigation and audit disclosures."},
    {"schedule": "material_risks", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Key group risks (R1-R8)", "start_page": 173, "end_page": 177, "start_text": "Key group risks / R1 ... CAUSES / RESIDUAL RISK MITIGATION CONTROLS / IMPACT", "end_before_text": "King IV™ application register"}, "supporting": [{"heading": "Our key Risks (icon index)", "start_page": 3, "end_page": 3}, {"heading": "risk/material-impact matrix", "start_page": 33, "end_page": 33}], "confidence": 0.80, "boundary_confidence": "MEDIUM", "reasoning_summary": "Per-risk cause/mitigation/impact tables, nested inside Governance; two risks per page interleave in extraction order."},
    {"schedule": "strategy", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Our strategy and business model", "start_page": 17, "end_page": 31, "start_text": "Our strategy and business model", "end_before_text": "OUR PURPOSE (divider page)"}, "supporting": [], "confidence": 0.75, "boundary_confidence": "LOW", "reasoning_summary": "15-page contiguous strategy nav-group; internal sub-boundaries not precisely separable."},
    {"schedule": "outlook", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "Looking forward (chair)", "start_page": 9, "end_page": 9}, {"heading": "A Message from our CEO (F2025 statements)", "start_page": 10, "end_page": 11}, {"heading": "Chairman macro-economic commentary", "start_page": 8, "end_page": 8}], "confidence": 0.55, "boundary_confidence": "LOW", "reasoning_summary": "No standalone Outlook section; forward-looking commentary is embedded mid-page in leadership narratives."},
    {"schedule": "corporate_governance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "GOVERNANCE REVIEW", "start_page": 164, "end_page": 184, "start_text": "GOVERNANCE REVIEW / Introduction", "end_before_text": "COMPLIANCE AND SAFETY"}, "supporting": [], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "21-page section; embedded risk register reported separately."},
    {"schedule": "remuneration", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "Remuneration POLICY / Remuneration REPORT", "start_page": 107, "end_page": 136, "start_text": "Remuneration POLICY / Glossary", "end_before_text": "SUPPLEMENTARY REVIEWS (divider page)"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "HIGH", "reasoning_summary": "Two contiguous sub-sections treated as one schedule."},
    {"schedule": "legal_regulatory", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": {"heading": "COMPLIANCE AND SAFETY", "start_page": 185, "end_page": 187, "start_text": "COMPLIANCE AND SAFETY / Introduction", "end_before_text": "GUIDANCE DOCUMENTS (divider page)"}, "supporting": [{"heading": "Contingent liability / audit (within Financial performance)", "start_page": 98, "end_page": 98}, {"heading": "Current legislative developments (chair review)", "start_page": 8, "end_page": 8}], "confidence": 0.65, "boundary_confidence": "MEDIUM", "reasoning_summary": "Most material litigation item is disclosed in financial_performance, not Compliance and Safety."},
    {"schedule": "material_matters_operating_environment", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": {"heading": "Determining our material matters", "start_page": 5, "end_page": 5, "start_text": "Determining our material matters", "end_before_text": "Leadership messages (divider page)"}, "supporting": [{"heading": "Our material issues (MI1-MI6 icon index)", "start_page": 3, "end_page": 3}, {"heading": "Chairman macro/operating-environment narrative", "start_page": 7, "end_page": 8}, {"heading": "CEO socio-political context", "start_page": 10, "end_page": 10}], "confidence": 0.55, "boundary_confidence": "LOW", "reasoning_summary": "No dedicated Material Matters or Operating Environment chapter; process description only in front matter."}
  ]
}
```

</details>

<details>
<summary>ACT 2022</summary>

```json
{
  "company": "ACT",
  "company_name": "AfroCentric Investment Corporation Limited",
  "year": 2022,
  "document": "data/raw/ACT/2022/annual_report.pdf",
  "schedules": [
    {"schedule": "ceo_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CEO'S REVIEW", "start_page": 50, "end_page": 53, "start_text": "In August 2019, the NHI Bill was tabled in parliament.", "end_before_text": "Our strategy and approach"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "HIGH", "reasoning_summary": "First-person narrative signed by Ahmed Banderker, Group CEO."},
    {"schedule": "chair_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CHAIRMAN'S REVIEW", "start_page": 10, "end_page": 11, "start_text": "Looking back over the turmoil of the past few years", "end_before_text": "Who we are (organisational overview)"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "HIGH", "reasoning_summary": "First-person narrative signed by Dr Anna Mokgokong, Chairman."},
    {"schedule": "financial_performance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CFO'S REVIEW", "start_page": 60, "end_page": 65, "start_text": "The 2022 financial year has been the year of two halves", "end_before_text": "Results at a glance"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "MEDIUM", "reasoning_summary": "Narrative MD&A signed by Hannes Boonzaaier, Group CFO."},
    {"schedule": "material_risks", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Our risks", "start_page": 38, "end_page": 41, "start_text": "Our robust risk management approach supports our strategy's implementation", "end_before_text": "Our material matters"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "MEDIUM", "reasoning_summary": "King IV/COSO/ISO 31000-aligned ERM framework and categorised risk register."},
    {"schedule": "strategy", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Our strategy and approach", "start_page": 54, "end_page": 58, "start_text": "Our strategy informs our business model for sustained value creation", "end_before_text": "OUR PERFORMANCE (divider)"}, "supporting": [], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "Strategic pillars, KPI table, capital trade-offs."},
    {"schedule": "outlook", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "Outlook (Chairman's review)", "start_page": 11, "end_page": 11}, {"heading": "Outlook (CEO's review)", "start_page": 52, "end_page": 53}], "confidence": 0.80, "boundary_confidence": "LOW", "reasoning_summary": "Report explicitly states outlook is distributed across seven named sections (p.8)."},
    {"schedule": "corporate_governance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CORPORATE GOVERNANCE REPORT / REVIEW", "start_page": 87, "end_page": 108, "start_text": "The AfroCentric Board embraces its responsibility...", "end_before_text": "REMUNERATION REPORT (divider)"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "MEDIUM", "reasoning_summary": "King IV-aligned; board, committees, IT governance, ethics/compliance."},
    {"schedule": "remuneration", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "REMUNERATION REPORT", "start_page": 109, "end_page": 122, "start_text": "On behalf of the Remuneration Committee...", "end_before_text": "SHAREHOLDER INFORMATION (divider)"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "HIGH", "reasoning_summary": "Policy, LTI plan, implementation report, advisory votes."},
    {"schedule": "legal_regulatory", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "5. Legal, regulatory and compliance management (material matter)", "start_page": 44, "end_page": 44}, {"heading": "Ethical behaviour / Conflicts of interest (governance report)", "start_page": 106, "end_page": 108}], "confidence": 0.70, "boundary_confidence": "LOW", "reasoning_summary": "No dedicated litigation section; both locations report a clean/no-incidents position."},
    {"schedule": "material_matters_operating_environment", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "External environment", "start_page": 26, "end_page": 30, "start_text": "Trends impacting the healthcare context in South Africa", "end_before_text": "OUR STAKEHOLDERS"}, "supporting": [{"heading": "Our material matters", "start_page": 42, "end_page": 48}], "confidence": 0.90, "boundary_confidence": "MEDIUM", "reasoning_summary": "Two distinct, separately paginated sections, not collapsed."}
  ]
}
```

</details>

<details>
<summary>BEL 2021</summary>

```json
{
  "company": "BEL",
  "company_name": "Bell Equipment Limited",
  "year": 2021,
  "document": "data/raw/BEL/2021/annual_report.pdf",
  "schedules": [
    {"schedule": "ceo_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Joint report by the chairman and chief executive", "start_page": 34, "end_page": 37, "start_text": "Bell Equipment ended the 2021 financial year positioned considerably stronger than the previous year.", "end_before_text": "Finance director's report"}, "supporting": [], "confidence": 0.55, "boundary_confidence": "MEDIUM", "reasoning_summary": "No CEO-only narrative exists; joint report with the chairman."},
    {"schedule": "chair_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Joint report by the chairman and chief executive", "start_page": 34, "end_page": 37, "start_text": "Bell Equipment ended the 2021 financial year positioned considerably stronger than the previous year.", "end_before_text": "Finance director's report"}, "supporting": [], "confidence": 0.55, "boundary_confidence": "MEDIUM", "reasoning_summary": "Same section as ceo_review; no chairman-only narrative exists."},
    {"schedule": "financial_performance", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "Finance director's report", "start_page": 38, "end_page": 40, "start_text": "The 2021 result is a solid recovery from the loss incurred by the group in 2020.", "end_before_text": "Corporate governance report"}, "supporting": [{"heading": "Financial (within Joint report)", "start_page": 35, "end_page": 35}], "confidence": 0.90, "boundary_confidence": "HIGH", "reasoning_summary": "Three-page CFO-style report bracketed by clear 'continued' labels."},
    {"schedule": "material_risks", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "KEY RISKS (within Strategic overview and risk management)", "start_page": 22, "end_page": 26, "start_text": "KEY RISKS / 1. Competitor risk", "end_before_text": "MATERIAL MATTERS / 1. COVID-19"}, "supporting": [{"heading": "Risk Management (within Corporate governance report)", "start_page": 48, "end_page": 48}], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "12 numbered risks with mitigations; immediately abuts differently-scoped Material Matters list."},
    {"schedule": "strategy", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Strategic overview and risk management (vision/objectives)", "start_page": 20, "end_page": 21, "start_text": "OUR VISION / Bell Equipment's vision is to be the global ADT specialist...", "end_before_text": "KEY RISKS / 1. Competitor risk"}, "supporting": [], "confidence": 0.75, "boundary_confidence": "MEDIUM", "reasoning_summary": "Vision, objectives, six capitals, strategy-map table; shares heading with risk section."},
    {"schedule": "outlook", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "Future Outlook (Joint report)", "start_page": 37, "end_page": 37, "start_text": "Our Russian business represents a small portion of our global business", "end_before_text": "Dividends"}, "supporting": [{"heading": "Looking ahead (Finance director's report)", "start_page": 40, "end_page": 40}], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "Two explicit forward-looking passages, both mid-page sub-headings."},
    {"schedule": "corporate_governance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Corporate governance report", "start_page": 41, "end_page": 49, "start_text": "The directors are ultimately responsible for ensuring compliance...", "end_before_text": "Social, ethics and transformation committee report"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "HIGH", "reasoning_summary": "9-page section: board/committee structure, King IV, ethics, internal controls, legal sub-topics."},
    {"schedule": "remuneration", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "Remuneration committee report", "start_page": 53, "end_page": 66, "start_text": "SECTION 1: committee governance...", "end_before_text": "Stakeholder relations report"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "HIGH", "reasoning_summary": "14-page, 4-part report ending in signed board approval."},
    {"schedule": "legal_regulatory", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "Legal and regulatory environment (within Corporate governance report)", "start_page": 49, "end_page": 49, "start_text": "The Bell Equipment group takes very seriously its compliance with all regulatory obligations.", "end_before_text": "Engagement with stakeholders"}, "supporting": [{"heading": "FSCA/JSE investigation disclosures (Joint report)", "start_page": 36, "end_page": 37}, {"heading": "APDP/AIS regulatory scheme compliance", "start_page": 83, "end_page": 84}], "confidence": 0.65, "boundary_confidence": "LOW", "reasoning_summary": "Named subsection is two paragraphs; the year's most material legal facts are recounted in the Joint report instead."},
    {"schedule": "material_matters_operating_environment", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "MATERIAL MATTERS (within Strategic overview and risk management)", "start_page": 26, "end_page": 27, "start_text": "MATERIAL MATTERS / 1. COVID-19", "end_before_text": "Global corporate structure"}, "supporting": [{"heading": "Materiality process (front matter)", "start_page": 2, "end_page": 3}], "confidence": 0.80, "boundary_confidence": "MEDIUM", "reasoning_summary": "4-item Material Matters list; no separate Operating Environment section exists anywhere, confirmed by keyword search."}
  ]
}
```

</details>

<details>
<summary>KP2 2023</summary>

```json
{
  "company": "KP2",
  "company_name": "Kore Potash plc",
  "year": 2023,
  "document": "data/raw/KP2/2023/annual_report.pdf",
  "schedules": [
    {"schedule": "ceo_review", "status": "NOT_FOUND", "primary": null, "supporting": [{"heading": "REVIEW OF OPERATIONS AND STRATEGIC REPORT (joint Board narrative)", "start_page": 7, "end_page": 23, "start_text": "The Board of Directors of Kore Potash is pleased to present its review...", "end_before_text": "joint Chairman + CEO signature block"}], "confidence": 0.05, "boundary_confidence": "N/A", "reasoning_summary": "No individually authored CEO narrative exists; the CEO co-signs a jointly-authored Board Strategic Report."},
    {"schedule": "chair_review", "status": "NOT_FOUND", "primary": null, "supporting": [{"heading": "REVIEW OF OPERATIONS AND STRATEGIC REPORT (joint Board narrative)", "start_page": 7, "end_page": 23}], "confidence": 0.05, "boundary_confidence": "N/A", "reasoning_summary": "No individually authored Chairman narrative exists; only co-signs the joint report."},
    {"schedule": "financial_performance", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": {"heading": "SUMMARY OF FINANCIALS", "start_page": 8, "end_page": 8, "start_text": "SUMMARY OF FINANCIALS", "end_before_text": "CORPORATE ACTIVITIES"}, "supporting": [{"heading": "Operating Results", "start_page": 24, "end_page": 24}, {"heading": "Going Concern / Going Concern (Cont)", "start_page": 24, "end_page": 25}, {"heading": "Going Concern / Going Concern (Cont)", "start_page": 31, "end_page": 32}], "confidence": 0.55, "boundary_confidence": "MEDIUM", "reasoning_summary": "Thin, bullet-point, liquidity-focused; no CFO narrative, consistent with a pre-revenue explorer."},
    {"schedule": "material_risks", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "POSITION AND PRINCIPAL RISKS", "start_page": 17, "end_page": 19, "start_text": "POSITION AND PRINCIPAL RISKS", "end_before_text": "DIRECTORS' SECTION 172 STATEMENT"}, "supporting": [{"heading": "Audit and Risk Committee (risk framework)", "start_page": 49, "end_page": 50}], "confidence": 0.85, "boundary_confidence": "HIGH", "reasoning_summary": "Bulleted risk-by-risk section with mitigations for 7 risk categories."},
    {"schedule": "strategy", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": {"heading": "BUSINESS MODEL", "start_page": 17, "end_page": 17, "start_text": "BUSINESS MODEL", "end_before_text": "POSITION AND PRINCIPAL RISKS"}, "supporting": [{"heading": "Key Performance Indicators", "start_page": 12, "end_page": 12}, {"heading": "UK Corporate Governance Code Provision 1 response", "start_page": 35, "end_page": 35}], "confidence": 0.35, "boundary_confidence": "LOW", "reasoning_summary": "Only a 3-sentence paragraph names strategy explicitly; no dedicated strategic-pillars section."},
    {"schedule": "outlook", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": {"heading": "Viability Assessment / Viability Assessment (Cont)", "start_page": 12, "end_page": 13, "start_text": "Viability Assessment", "end_before_text": "Tenement Details and Ownership"}, "supporting": [{"heading": "Next Steps", "start_page": 10, "end_page": 10}, {"heading": "Going Concern / Going Concern (Cont)", "start_page": 31, "end_page": 32}], "confidence": 0.50, "boundary_confidence": "MEDIUM", "reasoning_summary": "No 'Outlook' or 'Prospects' heading exists anywhere (confirmed by full-text search)."},
    {"schedule": "corporate_governance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CORPORATE GOVERNANCE REPORT", "start_page": 34, "end_page": 65, "start_text": "CORPORATE GOVERNANCE REPORT / INTRODUCTION", "end_before_text": "INDEPENDENT AUDITOR'S REPORT"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "LOW", "reasoning_summary": "32-page UK Code-structured section with a repeated '(CONT)' running header; Remuneration Report nested inside."},
    {"schedule": "remuneration", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "REMUNERATION REPORT", "start_page": 53, "end_page": 62, "start_text": "REMUNERATION REPORT", "end_before_text": "OTHER CORPORATE GOVERNANCE MATTERS"}, "supporting": [{"heading": "REMUNERATION AND NOMINATION COMMITTEE", "start_page": 51, "end_page": 52}], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "Detailed KMP remuneration/options tables; nested inside Corporate Governance Report under the same running header."},
    {"schedule": "legal_regulatory", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "NOTE 23: CONTINGENT LIABILITIES", "start_page": 113, "end_page": 113, "start_text": "NOTE 23: CONTINGENT LIABILITIES", "end_before_text": "ASX ADDITIONAL INFORMATION (UNAUDITED)"}, "supporting": [{"heading": "Proceedings on Behalf of Group (boilerplate)", "start_page": 31, "end_page": 31}], "confidence": 0.40, "boundary_confidence": "HIGH", "reasoning_summary": "Only substantive legal item is a two-sentence unfair-dismissal claim disclosure."},
    {"schedule": "material_matters_operating_environment", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "REVIEW OF OPERATIONS AND STRATEGIC REPORT (market context)", "start_page": 7, "end_page": 7}, {"heading": "POSITION AND PRINCIPAL RISKS (commodity price / country risk)", "start_page": 17, "end_page": 19}, {"heading": "Impact on Climate Change", "start_page": 11, "end_page": 12}], "confidence": 0.40, "boundary_confidence": "LOW", "reasoning_summary": "No dedicated Material Matters or Operating Environment heading; content folded entirely into Principal Risks."}
  ]
}
```

</details>

<details>
<summary>SBP 2024</summary>

```json
{
  "company": "SBP",
  "company_name": "Sabvest Capital Limited",
  "year": 2024,
  "document": "data/raw/SBP/2024/annual_report.pdf",
  "schedules": [
    {"schedule": "ceo_review", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "Report profile (attribution line)", "start_page": 5, "end_page": 5}, {"heading": "17. Commentary and conclusion", "start_page": 42, "end_page": 43}], "confidence": 0.35, "boundary_confidence": "LOW", "reasoning_summary": "No dedicated CEO review; the chairman's letter fills that narrative role, CEO's voice limited to a brief closing note."},
    {"schedule": "chair_review", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "CHAIRMAN'S LETTER TO SHAREHOLDERS", "start_page": 2, "end_page": 3, "start_text": "CHAIRMAN'S LETTER TO SHAREHOLDERS / Overview", "end_before_text": "CONTENTS"}, "supporting": [], "confidence": 0.97, "boundary_confidence": "HIGH", "reasoning_summary": "Complete standalone chairman narrative covering performance, governance, shareholders, ethics."},
    {"schedule": "financial_performance", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "6.5 Commentary on the 2024 Financial Results", "start_page": 16, "end_page": 16, "start_text": "6.5 Commentary on the 2024 Financial Results", "end_before_text": "6.6 Growth metrics"}, "supporting": [{"heading": "6.6/6.7 Growth metrics/Financial resources", "start_page": 16, "end_page": 17}, {"heading": "6.10/6.11 Performance of investments", "start_page": 18, "end_page": 25}], "confidence": 0.85, "boundary_confidence": "MEDIUM", "reasoning_summary": "Explicit narrative MD&A distinct from surrounding valuation tables; extended by per-investee commentary."},
    {"schedule": "material_risks", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "10. Risk report", "start_page": 38, "end_page": 39, "start_text": "10. Risk report / 10.1 Approach to risk management", "end_before_text": "11. Remuneration report"}, "supporting": [], "confidence": 0.90, "boundary_confidence": "MEDIUM", "reasoning_summary": "Includes a graded risk watch list table with residual risk ratings."},
    {"schedule": "strategy", "status": "FOUND_PRIMARY_AND_SUPPORTING", "primary": {"heading": "4. Strategies, business model and performance indicators", "start_page": 6, "end_page": 7, "start_text": "4. Strategies, business model and performance indicators", "end_before_text": "5. Investment holdings"}, "supporting": [{"heading": "ANNEXURE 2: Investment Policy", "start_page": 45, "end_page": 47}], "confidence": 0.93, "boundary_confidence": "MEDIUM", "reasoning_summary": "Explicit bulleted strategic pillars; Annexure 2 is a longer formal restatement."},
    {"schedule": "outlook", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "7. Prospects", "start_page": 25, "end_page": 25, "start_text": "7. Prospects / Sabcap expects satisfactory performances...", "end_before_text": "8. Governance and sustainability"}, "supporting": [{"heading": "Chairman's Letter, 'Medium-term performance'", "start_page": 2, "end_page": 2}], "confidence": 0.55, "boundary_confidence": "LOW", "reasoning_summary": "Explicitly headed Prospects section, but content is a single sentence."},
    {"schedule": "corporate_governance", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "9. Corporate governance", "start_page": 27, "end_page": 38, "start_text": "9. Corporate governance", "end_before_text": "10. Risk report"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "HIGH", "reasoning_summary": "Longest schedule in the document: King IV Principle-by-Principle plus committee attendance tables."},
    {"schedule": "remuneration", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "11. Remuneration report", "start_page": 38, "end_page": 42, "start_text": "11. Remuneration report / 11.1 Background", "end_before_text": "12. Code of share dealing"}, "supporting": [], "confidence": 0.95, "boundary_confidence": "MEDIUM", "reasoning_summary": "Full policy plus per-director implementation table with footnotes spanning a page boundary."},
    {"schedule": "legal_regulatory", "status": "DISTRIBUTED_NO_CLEAR_PRIMARY", "primary": null, "supporting": [{"heading": "Principle 13 (compliance with applicable laws)", "start_page": 36, "end_page": 36}, {"heading": "12. Code of share dealing", "start_page": 43, "end_page": 43}], "confidence": 0.40, "boundary_confidence": "LOW", "reasoning_summary": "No section whose primary purpose is legal/regulatory/litigation disclosure; embedded in governance and a narrow share-dealing section."},
    {"schedule": "material_matters_operating_environment", "status": "FOUND_PRIMARY_ONLY", "primary": {"heading": "3. Operational environment", "start_page": 6, "end_page": 6, "start_text": "3. Operational environment", "end_before_text": "4. Strategies, business model and performance indicators"}, "supporting": [], "confidence": 0.60, "boundary_confidence": "LOW", "reasoning_summary": "Only the 'operating environment' half is present as a distinct section; 'material matters' in the stakeholder-materiality sense is NOT_FOUND."}
  ]
}
```

</details>

## 5. Cross-report comparison

`P` = clear primary section · `P+S` = primary + substantive supporting sections · `D` =
distributed, no clear primary · `N` = not found · `NA` = not applicable.

| Schedule | SUR 2024 | ACT 2022 | BEL 2021 | KP2 2023 | SBP 2024 | Primary found |
|---|---|---|---|---|---|---|
| CEO Review | P | P | P (co-authored) | N | D | 3/5 |
| Chair Review | P | P | P (co-authored) | N | P | 4/5 |
| Financial Performance | P | P | P+S | D | P+S | 4/5 |
| Material Risks | P | P | P+S | P | P | **5/5** |
| Strategy | P | P | P | D | P+S | 4/5 |
| Outlook | D | D | P+S | D | P (thin) | 2/5 |
| Corporate Governance | P | P | P | P | P | **5/5** |
| Remuneration | P+S | P | P | P | P | **5/5** |
| Legal / Regulatory | D | D | P+S (weak) | P (thin) | D | 2/5 |
| Material Matters / Env. | D | P+S (2 distinct) | P (env. only) | D | P (env. only) | 3/5 |

**Patterns.**

- `corporate_governance`, `remuneration`, and `material_risks` are the only three schedules with
  a locatable primary in every report in the sample, regardless of company size (50–208 pages),
  sector, or disclosure regime (King IV vs. UK Companies Act). These appear to be the most
  standardized parts of the corpus and the best near-term candidates for a schedule-localization
  prototype.
- `legal_regulatory` and `outlook` are the weakest, both by primary-found count (2/5 each) and by
  the quality of the "primary" that was found — in 3 of the 4 cases scored `P`/`P+S` for these two
  schedules, the agent itself flagged the primary as thin, short, or missing the year's most
  material content. This is a structural property of how these reports are written (SA and UK
  disclosure conventions do not require a single consolidated "Outlook" or "Legal Matters"
  chapter the way they require a Remuneration Report), not a localization weakness.
- `ceo_review`/`chair_review` show the taxonomy's clearest assumption mismatch: the underlying
  concept ("what did leadership say about the year") is recognizable in all five reports, but it
  maps onto four different *structural* patterns — two separate narratives (SUR, ACT), one fused
  joint narrative (BEL), one narrative dominated by a single officer with the other reduced to a
  sign-off (SBP: chair dominates), and no individual narrative at all (KP2: UK collective Board
  voice). A downstream schema needs to represent "CEO/Chair narrative" as a flexible
  one-or-two-section construct rather than assuming exactly one section per officer.
- `material_matters_operating_environment` confirms the task brief's warning not to collapse the
  two sub-concepts: only ACT has both as separate, well-developed sections; BEL and SBP each have
  only one of the two (material matters only / operating environment only, respectively); SUR and
  KP2 have neither as a dedicated section. Treating this as a single normalized schedule likely
  under-serves downstream analysis — it may be worth splitting into two schedules in a future
  iteration.

## 6. Boundary quality assessment

Aggregated boundary-confidence ratings across all 36 `FOUND_PRIMARY*` cells (the only cells where
a boundary rating is meaningful):

- **HIGH**: 8 cells — typically self-contained sections with an explicit start heading, a signed
  sign-off or explicit closing statement, and a clean transition into a differently-named next
  section (e.g. ACT's CEO/Chair/Remuneration sections; SUR's remuneration; BEL's remuneration and
  governance; SBP's chair review and governance).
- **MEDIUM**: 19 cells — the majority. Common causes of the MEDIUM downgrade: (a) mid-page start
  or end with no visual/textual separator from the adjacent section (very common — roughly two
  thirds of all sections in the sample start or end partway down a page, since these reports do
  not reliably start new sections at page tops); (b) a section embedded inside a much larger
  parent section sharing the parent's running header (BEL's Key Risks within "Strategic overview
  and risk management"; KP2's Remuneration Report within "CORPORATE GOVERNANCE REPORT (CONT)");
  (c) repeated nav-caption or "continued" text recurring on every page of a long span, requiring
  the actual heading/body text (not the nav caption) to pin the true sub-boundary.
- **LOW**: 8 cells — concentrated in three specific situations: (1) a schedule sharing one
  heading with an entirely different schedule and no internal separator at all (SUR's strategy
  block, whose five sub-areas cannot be individually bounded from text alone; KP2's 32-page
  governance section, whose "(CONT)" header repeats without exception); (2) a genuinely tiny
  section squeezed between two others on a single page (SBP's "7. Prospects," one sentence,
  bounded on both sides mid-page); (3) legal/regulatory sections whose nominal boundary is short
  but whose substantive content is known (from other evidence in the same report) to live
  elsewhere (BEL, SUR).

**Specific boundary hazards observed, mapped to the task brief's checklist:**

- *Sections beginning/ending mid-page*: the dominant pattern in this corpus — the large majority
  of sections in all five reports start or end partway down a page rather than at a page
  boundary. Any downstream extractor must treat "start of section" as a text offset within a
  page, not just a page number.
- *Sections continuing across pages*: routine and generally well-marked via explicit "...
  continued" labels (ACT, BEL, KP2) or unbroken narrative flow (SUR, SBP) — this was the
  least-problematic hazard category.
- *Multiple similarly-named headings*: the primary source of LOW confidence — "(CONT)" suffixes
  (KP2, BEL's nav captions), and headings that are near-duplicates in different sections (BEL's
  "Looking ahead" vs. "Future Outlook"; SUR's identical nav-caption pair "Financial performance" /
  "Operational performance" recurring on ~15 consecutive pages regardless of actual page content).
- *Layouts where columns disrupt extraction order*: confirmed directly in one case (SUR's
  side-by-side risk panels, R6/R7 sharing a page) and suspected but not confirmed elsewhere;
  overall less disruptive than expected given the task brief's emphasis, likely because four of
  five reports use single-column body text even when the overall page design is graphic-heavy.
- *Tables/graphics embedded in the disclosure*: routine and usually harmless to *locating* a
  section (risk tables, remuneration tables, heat maps all extract as recognizable-if-jumbled
  text within the correct page range) but harmful to *extracting clean prose* from within a
  section — this is a second-order problem for a later extraction stage, not for localization.
- *Repeated page headers mistaken for section headings*: the single most consistent hazard across
  all five reports — every report has some form of running header/footer/sidebar-nav that repeats
  a section or sub-section name on every page of a span, and in three of five reports (SUR, KP2,
  BEL) this repetition was explicitly identified as the top boundary-confidence risk.

## 7. Proposed extraction architecture — evaluated against the experiment

The originally proposed pipeline was:

```
PDF -> basic layout/text extraction -> identifiable page/block objects -> LLM schedule
localization -> saved schedule boundaries -> deterministic extraction of original source blocks
-> within-schedule segmentation -> cross-year matching -> lexical change metrics
```

**This is broadly supported, with two adjustments suggested by what was actually observed:**

1. **"Basic layout/text extraction -> page/block objects" is necessary but not sufficient as
   currently scoped.** Plain PyMuPDF `get_text()` per page (what this experiment used) was
   *enough for the LLM to succeed* at localization, because the LLM could reason past reading-order
   corruption using context (e.g. recognizing a caption despite being extracted out of order). It
   would **not** be enough for the "deterministic extraction of original source blocks" step
   later in the pipeline, because several of the exact failure modes found here (headings
   displaced to page bottoms, nav captions repeating identically to real headings, two risk
   panels interleaving on one page) would corrupt a naive block-offset-based extractor even after
   the LLM has correctly identified the right page range. At minimum, block-level extraction
   (`page.get_text("dict")` or `"blocks"`, giving each text block its own bounding box) should be
   captured alongside the plain text passed to the LLM, so that the boundary the LLM identifies
   (a heading string) can be resolved to a specific block/coordinate rather than a byte offset
   into a linear text stream that may not reflect visual order.
2. **The LLM output itself should carry more than boundaries — it should carry a
   boundary-confidence flag and a "type of ambiguity" tag**, because this experiment's most
   useful signal for downstream engineering was not the boundary itself but *why* a boundary was
   uncertain (shared heading, running-header repetition, embedded in a larger section, thin
   content). A pipeline that discards this metadata after localization would lose the information
   needed to decide, e.g., whether to trust `material_risks` boundaries (mostly HIGH/MEDIUM) but
   route `legal_regulatory` boundaries (mostly LOW, and frequently incomplete even at their best)
   to a human reviewer or a different extraction strategy entirely.

The later pipeline stages were **not tested** by this experiment and should not be assumed
correct on this evidence alone:
- "Within-schedule segmentation," "cross-year matching," and "lexical change metrics" all depend
  on schedule boundaries being reproducible enough across years to compare — this experiment used
  one year per company and cannot speak to whether, e.g., Spur's "Our strategy and business
  model" section keeps the same shape and page range from FY2023 to FY2025. That is the most
  important open question for a larger follow-up experiment (same-company, multi-year sample).
- The experiment also did not test cost/latency/consistency of running this at the corpus's real
  scale (~30 currently-available reports, up to ~200 pages each): five reports required five
  independent ~120K-200K-token analysis passes; a production version would need a cheaper,
  narrower per-report call (e.g. one call per report rather than one call that also writes a full
  audit narrative) to be practical at scale.

## 8. Comparison with the current passage-first pipeline

| Problem in the current approach | Would schedule localization help? | Basis |
|---|---|---|
| Header-only passages | **Likely yes** | A schedule boundary anchored to real heading text plus body content should not fire on a bare heading with no following prose — the LLM in this experiment consistently required substantive content, not just a heading match, before scoring `FOUND`. |
| Very short fragments | **Partially** | Helps for fragments caused by mis-segmented passages within a real section, but not for schedules that are *genuinely* short in the source (SBP's one-sentence "Prospects"; KP2's two-sentence contingent-liability note) — those are real content, not parsing artifacts, and would still need to be handled as legitimately thin. |
| Table-of-contents noise | **Yes** | The task brief's instruction to treat TOC/bookmarks as a prior rather than ground truth was validated directly — bookmark page numbers were observed to be off by one in places (KP2), and the LLM cross-checked bookmark claims against actual page content rather than trusting them, exactly the behavior needed to avoid TOC-noise passages. |
| Reading-order problems | **Partially** | The LLM successfully *located* sections despite reading-order corruption (nav captions interleaved with body text, captions at page bottoms, two-column risk panels), but this experiment did not attempt *clean extraction* of prose from those same corrupted regions — reading-order problems inside a correctly-located section boundary remain a real downstream problem that schedule localization does not by itself solve. |
| False deletion/addition pairs (year-over-year) | **Untested, plausibly yes** | Not evaluated in this single-year-per-company experiment, but the mechanism is right in principle: if a section is identified by a normalized schedule label rather than by exact heading-string matching, a heading rename between years (e.g. "Our risks" -> "Risk management") should no longer register as a full section deletion+addition. Requires the multi-year follow-up noted in section 7. |
| Sections moving between years | **Likely yes, same caveat as above** | Same reasoning — normalized-schedule matching is heading-text-independent by design, which is the entire point of this approach relative to positional/heading-string rules. Needs the multi-year test to confirm. |
| Arbitrary passage boundaries | **Yes, for the schedule level** | Schedule-level boundaries in this experiment were consistently anchored to real document structure (headings, signatures, adjacent-section transitions) rather than arbitrary token/page windows — a clear improvement at the schedule granularity. Passage-level boundaries *within* a schedule are a separate, still-unsolved problem ("within-schedule segmentation" in the proposed architecture, not attempted here). |
| Company-specific parsing rules | **Yes, for locating schedules** | This is the core promise validated by the experiment: the same ten schedule definitions, with no company-specific heading lists, correctly handled four very different heading vocabularies and two different disclosure-regime conventions (King IV vs. UK Companies Act) without bespoke rules. |

**What this would explicitly NOT solve, based on direct evidence from the experiment:**
- It does not make thin/absent disclosure appear where the source document genuinely lacks it
  (2/5 reports have no individual CEO or Chair voice at all for KP2; `legal_regulatory` and
  `outlook` are structurally thin across most of the sample) — some downstream "no data" results
  are a property of the source, not a pipeline defect to fix.
- It does not, by itself, produce clean extractable prose from a correctly located section —
  tables, embedded graphics, and reading-order corruption within a section boundary still need a
  separate, likely still partly rule-based, block-to-text reconciliation step.
- It does not resolve the case where a schedule's real content lives predominantly outside its
  nominal section (Spur's litigation in `financial_performance` rather than
  `legal_regulatory`) — an LLM can *flag* this (and did, in this experiment), but a downstream
  system consuming only "the legal_regulatory boundary" would still miss the substantive
  disclosure unless it also consumes the cross-references the LLM recorded.

## 9. Recommendation

**B. MIXED — run a larger experiment before implementation**, with a specific, narrower next
step rather than a full corpus run.

Seven of the ten schedules (`ceo_review`, `chair_review`, `financial_performance`,
`material_risks`, `strategy`, `corporate_governance`, `remuneration`) showed strong, auditable,
company-independent localization performance and would likely support a small prototype today.
Three (`outlook`, `legal_regulatory`, `material_matters_operating_environment`) showed enough
structural ambiguity — and, in `legal_regulatory`'s case, enough evidence that the "canonical
section" premise itself may not hold for this schedule across most of the corpus — that treating
all ten uniformly in a first implementation would likely produce a worse experience for those
three than the existing pipeline's known failure modes.

The single most important gap is **not** localization quality within one year — it is that this
experiment used one year per company and therefore cannot speak to the property the whole
downstream use case depends on: **do a report's schedule boundaries stay identifiable enough,
year over year, for the same company, to support cross-year matching and lexical change
metrics?** ACT and BEL both have 7–9 years of available reports in this repository and are the
obvious candidates for that follow-up: run the same ten-schedule localization across, say, 4–5
consecutive years of one or two companies and check whether `corporate_governance`,
`remuneration`, and `material_risks` (the three schedules that were reliable here) stay reliable
across years, and whether the schedule that heading-changes the most between years is one this
experiment already flagged as unreliable within a single year.

Recommended next step, concretely: extend this same methodology (LLM localization over plain
PyMuPDF page text, no new parser) to 4–5 consecutive years of ACT and/or BEL, focused only on the
seven schedules that performed well here, before committing to replace any part of the production
pipeline.

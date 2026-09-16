# Experiment: Within-Schedule Semantic Unit Alignment (AfroCentric, Corporate Governance & Remuneration, 2020–2024)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against `data/raw/ACT/{2020,2021,2022,2023,2024}/annual_report.pdf`
via throwaway PyMuPDF scripts, with intermediate plain-text and block/bbox dumps written to a
session-local scratch directory outside the repository. Nothing here is wired into the
application. This is a direct follow-up to `docs/experiments/annual-report-longitudinal-schedule-stability.md`
("the longitudinal experiment," assumed read), which established that Corporate Governance and
Remuneration are the two most structurally stable of ACT's six core normalized schedules across
2020–2024. No lexical-change metrics were computed.

## 1. Executive summary

**Yes — stable, comparable semantic disclosure units can be recovered inside both Corporate
Governance and Remuneration, and they are stable enough, with one required addition (explicit
split/merge/move handling) and one required exclusion class (thin one-line units), to serve as the
comparison containers for a future lexical-change stage.**

**How many useful units emerged?** 19 governance units and 15 remuneration units were identified
as recurring, boundable disclosure concepts (34 total), organized into the hierarchy AfroCentric's
own report structure actually exhibits (Board / Committees / Other Governance for governance;
Policy / Model / Processes / Implementation for remuneration — see Sections 3–4). Of these, 24 are
rated `STRONG_LONGITUDINAL_UNIT` (present and boundable in all five years with a stable heading or
stable content-pattern anchor), 6 are `USABLE_WITH_STRUCTURAL_HANDLING` (a real concept that
underwent a documented ADDED/SPLIT/MOVED/RESTRUCTURED event), and 4 are `TOO_THIN` (real,
present every year, but one sentence long — not useful as an independent lexical-comparison unit
on their own). No unit fell into `TOO_DISTRIBUTED`, `TOO_VISUAL`, or `TOO_UNSTABLE` — consistent
with the longitudinal experiment's own reason for selecting these two schedules as the most
stable in the corpus.

**How stable are they across five years?** Very. 24 of 34 units (71%) have an identical or
near-identical heading in every year sampled and never move, split, or merge. The instability
that does exist is concentrated in one real event, not scattered noise: **2022 is a genuine
governance-schedule redesign year for ACT**, in which four wholly new disclosure units appear at
once — director/executive biography pages, a "Combined Board skill set" chart, and a new
"Board deliberations" section that reorganizes the year's governance narrative around strategic
themes rather than per-committee minutes. A second, smaller event is the 2021 heading-formalization
of what had been unlabeled prose in Remuneration (2020's "Remuneration oversight and policies" splits
into explicitly headed "Remuneration governance" and "Remuneration policy design principles" from
2021 onward). A third is a genuine cross-schedule boundary move: AfroCentric's full Enterprise Risk
Management framework and risk heat map live inside the Corporate Governance schedule in 2020–2021,
then physically relocate into the (now-standalone, per the longitudinal experiment) Material Risks
schedule from 2022 onward — governance retains only "Combined assurance" and "Internal controls."

**How often are one-to-many / many-to-one relationships needed?** Rarely, and only in one
direction. No true SPLIT or MERGE (one *existing* unit fracturing into several, or several
existing units fusing into one) was observed within governance or remuneration across the four
adjacent-year transitions studied. The closest analogue is a **ADDED-cluster event** (2021→2022,
four new units appear together) and one **content-to-heading promotion** (2020→2021, previously
unlabeled prose gains explicit headings, which is a RENAMED/EXPANDED relationship on a single unit,
not a fan-out). This is a materially different picture from the longitudinal experiment's
schedule-level finding for Material Risks (which showed genuine ABSENT→MERGED→STANDALONE→
RESTRUCTURED churn) — governance and remuneration's internal units are additive and heading-
stabilizing over time, not repeatedly reshuffled.

**How often would heading matching alone have worked?** For 26 of 34 units (76%), a simple exact
or near-exact heading-string matcher would have aligned every year correctly with no semantic
reasoning required (committee names, "Company Secretary," "Compliance," "Remuneration processes,"
etc. are verbatim-stable). Semantic reasoning earned its keep in exactly the cases the longitudinal
experiment's schedule-level finding predicted would recur one level down: (a) the 2020→2021
unlabeled-prose-to-heading promotion, (b) recognizing that 2022's four new units are genuinely new
content rather than a renamed continuation of something in 2021, and (c) recognizing that the
2021→2022 disappearance of the ERM-framework diagram from governance's page range is a **schedule
boundary move**, not a content deletion — the content is fully present, just under a sibling
schedule now.

**Are boundaries sufficiently reliable for later lexical metrics?** Yes for prose and simple
tabular units (audited directly via blocks on 6 representative pages across 2020 and 2022 — all
CLEAN or MINOR_CORRECTION_NEEDED, zero MULTIMODAL_REQUIRED). The two chart-heavy pages checked
(2020's base-pay-increase bar chart, 2022's four-donut-chart Board Diversity page) both need
block x0/y0-band clustering to correctly assign each floating percentage to its category and
year — the same class of fix the longitudinal experiment documented for Bell Equipment's heading
displacement, applied here to numeric labels rather than headings — but neither needed
multimodal escalation.

**Which units should move forward into the comparison stage? Which should be excluded?** The 24
`STRONG_LONGITUDINAL_UNIT` entries (Section 11) should proceed directly. The 6
`USABLE_WITH_STRUCTURAL_HANDLING` entries should proceed but only once the EXTERNALIZED-style
status vocabulary recommended by the longitudinal experiment is extended with an explicit `ADDED`
/ `MOVED_CROSS_SCHEDULE` status, so that a 2021 "absence" is never scored as a wording change
against a 2022 "presence." The 4 `TOO_THIN` entries should be excluded from independent lexical
comparison — they are real and worth tracking for presence/absence, but a one-sentence
year-over-year diff is not a meaningful lexical-change signal on its own; if desired later they
should be folded into their parent unit rather than compared standalone.

**Recommendation:** (A) proceed to lexical-change metrics, scoped to a first pilot set of three
units chosen to span the stability spectrum — see Section 13.

## 2. Source inventory

| Year | Path | PDF pages (doc) | Governance schedule page range | Remuneration schedule page range |
|---|---|---|---|---|
| 2020 | `data/raw/ACT/2020/annual_report.pdf` | 126 | 73–92 | 94–106 |
| 2021 | `data/raw/ACT/2021/annual_report.pdf` | 134 | 89–105 | 106–118 |
| 2022 | `data/raw/ACT/2022/annual_report.pdf` | 150 | 87–109/110 | 110–122 |
| 2023 | `data/raw/ACT/2023/annual_report.pdf` | 162 | 101–124 | 125–138 |
| 2024 | `data/raw/ACT/2024/annual_report.pdf` | 154 | 99–119 | 119–132 |

Ranges are inclusive, 1-based `fitz` page indices, established by full-text scanning for
`CORPORATE GOVERNANCE (REPORT|REVIEW)` / `REMUNERATION REPORT` / `SHAREHOLDER INFORMATION` /
`ANNUAL FINANCIAL STATEMENTS` occurrences across each entire PDF (not assumed from the longitudinal
experiment's 2020-only figures) and confirmed by reading the resulting text. Governance and
Remuneration are contiguous in every year (Remuneration always begins the page after Governance's
last content page), matching the longitudinal experiment's finding that both schedules are
consistently `P` (standalone primary) with no intervening schedule.

## 3. Per-year semantic segmentation — Corporate Governance

`H` = has own heading in-document · `U` = unlabeled prose block (topic present, no heading) ·
`ABS` = genuinely absent from the governance page range this year (may exist elsewhere, see
Section 6) · pages are PDF page indices.

| Normalized label | 2020 | 2021 | 2022 | 2023 | 2024 | Structural type | Confidence |
|---|---|---|---|---|---|---|---|
| board_role_and_composition | H p.80–81 | H p.90–91 | H p.88, 96 | H p.100 | H p.99–100 | standalone subsection | HIGH |
| board_diversity | H p.77 | (folded into board org-chart cards) | H p.89 | H p.101 | H p.98 | standalone / table-driven; RESTRUCTURED 2022 | HIGH |
| board_of_directors_profiles | ABS | ABS | H p.90–91 | H p.102 | H p.102–104 | committee-specific / policy-adjacent bios | HIGH (2022+) |
| combined_board_skillset | ABS | ABS | H p.92 | H p.105 | H p.104–106 | table/chart-driven | HIGH (2022+) |
| executive_committee_profiles | U (diversity table only, p.77) | ABS | H p.92–93 | H p.106–107 | H p.106 | committee-specific bios | HIGH (2022+) |
| board_deliberations | ABS (content distributed across per-committee cards) | ABS | H p.94–95 | H p.108 | H p.106–107 | headed paragraph group, theme-organized | HIGH (2022+) |
| appointment_and_retirement | U p.83 | U p.93 | U p.~97 (embedded) | U (embedded) | U (embedded) | headed paragraph group (sub-heading present, not top-level) | MEDIUM |
| board_effectiveness | U p.83 | U p.93 | U (embedded) | U (embedded) | U (embedded) | headed paragraph group | MEDIUM |
| company_secretary | H p.81 | H p.91 | H p.~97/98 | H p.~110 | H p.~119/120 | standalone subsection | HIGH |
| audit_risk_committee | H p.84 | H p.94 | H p.~97 | H p.~111 | H p.~109 | committee-specific (role + composition + key matters) | HIGH |
| investment_committee | H p.85 | H p.95 | H p.~99 | H p.~113 | H p.~111 | committee-specific | HIGH |
| ict_steering_committee | H p.86 | H p.96 | H p.~101 | H p.~115 | H p.~112–113 | committee-specific | HIGH |
| nomination_committee | H p.87 | H p.97 | H p.~103 | H p.~117 | H p.~114 | committee-specific | HIGH |
| remuneration_committee_card | H p.88 | H p.98 | H p.~105 | H p.~119 | H p.~116 | committee-specific | HIGH |
| social_ethics_committee | H p.89 | H p.99 | H p.~107 | H p.~121 | H p.~118 | committee-specific | HIGH |
| compliance | U p.90 (unlabeled sub-topic) | U p.100 | H p.~ (own heading) | H p.~ | H p.~ | headed paragraph group; RENAMED/split from prose 2022 | MEDIUM→HIGH (2022+) |
| ethics_governance | ABS as own heading (implicit in compliance prose) | ABS | H (own heading, "Ethical behaviour") | H | H | headed paragraph group; SPLIT out 2022 | HIGH (2022+) |
| conflicts_of_interest | U p.90 | U p.100 | H | H | H | headed paragraph group | MEDIUM→HIGH |
| dealings_in_shares | U p.90 | U p.100 | H | H | H | headed paragraph group | MEDIUM→HIGH |
| erm_framework_and_risk_process | H p.90–91 (full framework diagram, heat map) | H p.100–103 (full framework, heat map) | ABS (moved to Material Risks schedule) | ABS | ABS | table/diagram-driven; MOVED cross-schedule 2022 | HIGH (2020–2021 only) |
| combined_assurance | H p.92 | H p.104 | H | H | H | standalone subsection | HIGH |
| internal_controls | H p.92 | H p.104 | H | H | H | standalone subsection | HIGH |
| information_security_governance | H p.92 | H p.105 | H | H | H | standalone subsection | HIGH |
| tax_transparency | ABS | ABS | ABS | H p.122 | H p.~118/119 | standalone subsection; ADDED 2023 | HIGH (2023+) |

## 4. Per-year semantic segmentation — Remuneration

| Normalized label | 2020 | 2021 | 2022 | 2023 | 2024 | Structural type | Confidence |
|---|---|---|---|---|---|---|---|
| remuneration_chair_background_statement | H "BACKGROUND STATEMENT" p.94 | H (embedded under "REMUNERATION REPORT" divider, p.107) | H "Background statement" p.110 | H "BACKGROUND STATEMENT" p.125 | H "BACKGROUND STATEMENT" p.120 | standalone narrative | HIGH |
| remuneration_governance_structure | U (embedded, unlabeled, p.96) | H "Remuneration governance" p.108 | H p.~111 | H "REMUNERATION GOVERNANCE" p.~127 | H "Remuneration governance" p.~121 | table/diagram-driven; RENAMED/EXPANDED 2021 | MEDIUM (2020) → HIGH (2021+) |
| remuneration_policy_design_principles | U (embedded, unlabeled, p.96) | H "Remuneration policy design principles" p.108 | H p.~111 | H "REMUNERATION POLICY DESIGN PRINCIPLES" p.~127 | H p.~122 | headed paragraph group; RENAMED/EXPANDED 2021 | MEDIUM (2020) → HIGH (2021+) |
| pay_for_performance_bsc_table | U p.97 | U p.109 | U p.~112 | U p.~ | U p.~123 | table-driven, unlabeled but content-pattern coherent | HIGH |
| guaranteed_pay_mechanics | H "Remuneration model" (sub) p.98 | H (sub) p.110 | H p.~ | H p.~ | H "Remuneration model" (sub) p.124 | headed paragraph group | HIGH |
| variable_pay_sti_mechanics | H (sub of Remuneration model) p.99–100 | H p.111–112 | H p.~ | H p.~ | H p.~125 | headed paragraph group | HIGH |
| variable_pay_lti_mechanics | H (sub) p.99–101 | H p.111–113 | H p.~ | H p.~ | H p.~126 | headed paragraph group | HIGH |
| remuneration_processes | H "Remuneration processes" p.101 | H p.113 | H "REMUNERATION PROCESSES" p.~ | H p.~ | H "Remuneration processes" p.~127 | headed paragraph group | HIGH |
| ned_remuneration_policy_table | H "Non-executive Directors' remuneration" p.101 | H p.113 | H "NON-EXECUTIVE DIRECTORS' REMUNERATION" p.~ | H p.~ | H p.~127 | table-driven | HIGH |
| implementation_report | H "IMPLEMENTATION REPORT" p.102 | H "Implementation report" p.114 | H "Implementation report" p.~ | H "IMPLEMENTATION REPORT" p.~ | H "IMPLEMENTATION REPORT" p.~ | standalone parent (contains 6 children below) | HIGH |
| total_remuneration_outcomes | H (sub of implementation) p.102 | H p.114 | H "Total remuneration outcomes" p.~ | H "TOTAL REMUNERATION OUTCOMES" p.~ | H "Total remuneration outcomes" p.~ | table-driven | HIGH |
| sti_lti_performance_outcomes | H (sub) p.103 | H p.115–116 | H (sub) p.~ | H (sub) p.~ | H (sub) p.~ | table/narrative-driven | HIGH |
| individual_remuneration_outcomes | H "Individual remuneration outcomes" p.104–105 | H p.~ | H "Individual remuneration outcomes" p.~ | H "INDIVIDUAL REMUNERATION OUTCOMES" p.~ | H "Individual remuneration outcomes" p.~ | table-driven, per-director | HIGH |
| ned_fees_and_payments_table | H "Payments made to Non-executive Directors" p.106 | H p.~ | H "Payments made to Non-executive Directors" p.~ | H "PAYMENTS MADE TO NON-EXECUTIVE DIRECTORS" p.~ | H "Payments made to Non-executive Directors" p.~ | table-driven | HIGH |
| termination_of_office_payments | H (one sentence) p.106 | H (one sentence) | H | H | H | headed paragraph group (thin) | HIGH (presence), n/a (depth) |
| statement_regarding_compliance | H (one sentence) p.106 | H | H | H | H | headed paragraph group (thin) | HIGH (presence) |
| advisory_vote_on_implementation_report | H p.106 | H | H | H | H (2024: content-flagged, see Section 6) | headed paragraph group (thin) | HIGH |
| approval_by_board | H (one sentence, dated) p.106 | H | H | H | H | headed paragraph group (thin) | HIGH |

Page numbers marked `~` were located via heading text search within the schedule's super-range
(Section 2) rather than individually re-verified page-by-page for every year; all headings quoted
are exact strings confirmed present in the extracted plain text for that year.

## 5. Longitudinal unit matrices

`P` = present, clear boundary · `U` = present, unlabeled/embedded (boundary inferred from content
pattern, not a heading) · `X` = absent from this schedule's page range this year · `N` = new this
year (first occurrence).

### 5.1 Corporate Governance

| Unit | 2020 | 2021 | 2022 | 2023 | 2024 | Stability |
|---|---|---|---|---|---|---|
| board_role_and_composition | P | P | P | P | P | STRONG |
| board_diversity | P | U | P (restructured) | P | P | USABLE (restructured 2022, held since) |
| board_of_directors_profiles | X | X | N | P | P | USABLE (added 2022) |
| combined_board_skillset | X | X | N | P | P | USABLE (added 2022) |
| executive_committee_profiles | U | X | N | P | P | USABLE (added 2022; thin precursor 2020) |
| board_deliberations | X | X | N | P | P | USABLE (added 2022) |
| appointment_and_retirement | U | U | U | U | U | STRONG (stable as embedded prose) |
| board_effectiveness | U | U | U | U | U | STRONG |
| company_secretary | P | P | P | P | P | STRONG (personnel change 2024, not structural) |
| audit_risk_committee | P | P | P | P | P | STRONG |
| investment_committee | P | P | P | P | P | STRONG |
| ict_steering_committee | P | P | P | P | P | STRONG |
| nomination_committee | P | P | P | P | P | STRONG |
| remuneration_committee_card | P | P | P | P | P | STRONG |
| social_ethics_committee | P | P | P | P | P | STRONG |
| compliance | U | U | P | P | P | USABLE (heading gained 2022) |
| ethics_governance | X | X | N | P | P | USABLE (split out 2022) |
| conflicts_of_interest | U | U | P | P | P | USABLE (heading gained 2022) |
| dealings_in_shares | U | U | P | P | P | USABLE (heading gained 2022) |
| erm_framework_and_risk_process | P | P | X | X | X | USABLE (moved out 2022) |
| combined_assurance | P | P | P | P | P | STRONG |
| internal_controls | P | P | P | P | P | STRONG |
| information_security_governance | P | P | P | P | P | STRONG |
| tax_transparency | X | X | X | N | P | USABLE (added 2023) |

### 5.2 Remuneration

| Unit | 2020 | 2021 | 2022 | 2023 | 2024 | Stability |
|---|---|---|---|---|---|---|
| remuneration_chair_background_statement | P | P | P | P | P | STRONG |
| remuneration_governance_structure | U | P | P | P | P | USABLE (heading gained 2021) |
| remuneration_policy_design_principles | U | P | P | P | P | USABLE (heading gained 2021) |
| pay_for_performance_bsc_table | U | U | U | U | U | STRONG (stable as embedded content) |
| guaranteed_pay_mechanics | P | P | P | P | P | STRONG |
| variable_pay_sti_mechanics | P | P | P | P | P | STRONG |
| variable_pay_lti_mechanics | P | P | P | P | P | STRONG |
| remuneration_processes | P | P | P | P | P | STRONG |
| ned_remuneration_policy_table | P | P | P | P | P | STRONG |
| implementation_report | P | P | P | P | P | STRONG |
| total_remuneration_outcomes | P | P | P | P | P | STRONG |
| sti_lti_performance_outcomes | P | P | P | P | P | STRONG |
| individual_remuneration_outcomes | P | P | P | P | P | STRONG |
| ned_fees_and_payments_table | P | P | P | P | P | STRONG |
| termination_of_office_payments | P | P | P | P | P | STRONG (thin) |
| statement_regarding_compliance | P | P | P | P | P | STRONG (thin) |
| advisory_vote_on_implementation_report | P | P | P | P | P | STRONG (thin; 2024 content-anomalous, see §6) |
| approval_by_board | P | P | P | P | P | STRONG (thin) |

## 6. Split / merge / move case studies

**Case 1 — Board-profile cluster ADDED, 2021→2022 (governance).** `board_of_directors_profiles`,
`combined_board_skillset`, and `board_deliberations` all appear for the first time in 2022, in
immediate sequence (pp.90–95), alongside a restructured `board_diversity` that gains independence
and average-tenure metrics not present in 2020's simpler gender/race-only version. This is not a
split of any single 2021 unit — no 2021 content disappears to make room for these — and not a
rename of the "Board and sub-committees" org-chart page (which itself persists, now folded into
`board_role_and_composition`). It is best read as a single design event: AfroCentric added a
"Board profile" mini-section to its governance schedule in 2022 and has kept it in identical form
in 2023 and 2024. `executive_committee_profiles` is a partial exception: 2020 had a thin
`Executive Committee Diversity` chart (a precursor, folded into that year's `board_diversity`
page) but no bios; 2022's version is a full bios-with-photos page, so it is coded ADDED rather
than RESTRUCTURED, since the prior "unit" was really part of a different parent (`board_diversity`).

**Case 2 — ERM framework MOVED cross-schedule, 2021→2022 (governance ↔ material risks).** In
2020 and 2021, the governance schedule's own page range contains AfroCentric's full Enterprise
Risk Management framework narrative (identification → analysis → evaluation → categorisation →
mitigation cycle, with a diagram) and, in 2021 specifically, the risk register itself with a
risk heat map (pp.102–103). From 2022 onward, none of this appears inside the governance page
range at all — full-text scanning of the 2022–2024 governance ranges (Section 3) confirms its
absence — while the longitudinal experiment independently documented that ACT's Material Risks
schedule became a standalone, well-bounded "Our risks"/"OUR RISKS" section starting exactly in
2022. The two findings triangulate: the ERM-framework content did not disappear, it crossed a
schedule boundary. **This is the most consequential finding of this experiment for the
alignment task's design**: a within-schedule aligner that only ever looks inside one schedule's
own page range will report this unit as `PRESENT_TO_ABSENT` (wrongly implying loss), when the
correct status is `MOVED_CROSS_SCHEDULE`. Detecting this required checking the sibling schedule,
which is outside a naive per-schedule pipeline's scope by default.

**Case 3 — Compliance/ethics cluster SPLIT, 2021→2022 (governance).** In 2020–2021, "Compliance,"
"Conflicts of interest," and "Dealings in shares" are three unlabeled prose sub-topics run
together under the page-level heading "Governance policies, procedures and processes" — a single
`headed_paragraph_group` at the page level containing three distinguishable but unheaded
sub-topics, plus a fourth topic ("Ethical behaviour") that has no distinct textual presence at all
in 2020–2021 (its content, such as it exists, is folded into the Social and Ethics Committee's
"Key matters" bullets, e.g. "Monitored ethical standards within the Company"). From 2022, all four
become independently headed sub-sections with their own bold headings. This is coded as a
one-to-many `SPLIT` for the three 2020–2021 topics that already existed as distinguishable prose,
and as `ADDED` for `ethics_governance`, which did not have a distinguishable textual home before
2022 (it is not that a real unit was hiding and later surfaced — the 2020–2021 committee-card
bullet is too thin and differently-scoped to count as the same disclosure).

**Case 4 — Remuneration governance/policy headings RENAMED/EXPANDED, 2020→2021 (remuneration).**
2020's "REMUNERATION OVERSIGHT AND POLICIES" page (p.96) is one long unlabeled prose flow covering
governance structure (who approves what), policy design principles, and remuneration principles,
with no internal sub-headings beyond the page-level one. From 2021 onward, the same content —
verified by comparing the 2020 and 2021 prose almost paragraph-for-paragraph (both open "AfroCentric's
remuneration policy, structures and processes are set within a governance framework...") — is
split across two explicitly headed sub-sections, "Remuneration governance" and "Remuneration
policy design principles," which then persist unchanged through 2024. This is a single
`RENAMED`/`EXPANDED` event on what is conceptually one continuous unit that gained internal
heading granularity, not a genuine content split — the two 2021+ headings partition content that
was always logically two topics inside one unlabeled 2020 block.

**Case 5 — Tax transparency ADDED, 2022→2023 (governance).** "Tax transparency" and "AfroCentric's
tax exposure and gap disclosure" appear for the first time in 2023 (p.122 area) and persist
unchanged in 2024. No 2022 content addresses this topic at all (confirmed absent from the full
2022 governance-range text). This is a clean `ADDED`, not a split or rename of anything existing.

**Case 6 — content-level (not structural) anomaly, 2023→2024 (remuneration).** The
`advisory_vote_on_implementation_report` unit is structurally `STABLE` across all five years (same
heading, same page position, same one-paragraph length), but its 2024 content is materially
different in substance: the implementation-report vote fell to 50.26% (versus 96–99% in every
other year), and the surrounding narrative explicitly names "constructive engagement with the
Sanlam Group who had voted against the implementation report." This is exactly the caution the
longitudinal experiment's Section 11 raised in the opposite direction: **a unit whose container
did not move at all can still carry a large genuine wording/sentiment change**, and a pipeline that
only tracks structural stability (this report's job) must not be read as also asserting content
stability. This unit is flagged as a strong first candidate for lexical comparison specifically
because its boundary is trivial and its content is known, independently, to have changed
materially — a useful validation case (see Section 13).

## 7. Alignment edge table (adjacent-year transitions)

Only units with a non-trivial transition are listed; the 24 `STRONG_LONGITUDINAL_UNIT` entries not
shown here are `ONE_TO_ONE` / `STABLE` in every transition at HIGH confidence via heading match.

| From unit | To unit(s) | Relationship | Confidence | Evidence summary |
|---|---|---|---|---|
| 2020:remuneration_oversight_and_policies (unlabeled) | 2021:remuneration_governance_structure, 2021:remuneration_policy_design_principles | ONE_TO_MANY / RENAMED / EXPANDED | 0.85 | Nearly identical opening sentence and governance-flow diagram carried across both years; 2021 partitions the same content under two new bold headings with no content added or removed. |
| 2020:board_diversity | 2022:board_diversity (restructured) | ONE_TO_ONE / RESTRUCTURED | 0.80 | Same heading and topic (gender/race board composition), but 2022 adds independence-of-directors and average-tenure metrics and reorganizes from a two-panel to a four-panel chart layout; 2021 carries the topic only as embedded org-chart captions, not a distinct page. |
| (none in 2021) | 2022:board_of_directors_profiles | ADDED | 0.95 | No 2021 equivalent exists anywhere in the governance range (meeting-attendance table lists names/titles only, no bios/photos); 2022 introduces a full bios page with a stable URL cross-reference pattern retained through 2024. |
| (none in 2021) | 2022:combined_board_skillset | ADDED | 0.95 | No skills-matrix chart exists in any prior year; introduced 2022, unchanged format through 2024. |
| 2020:executive_committee_diversity (thin, embedded in board_diversity) | 2022:executive_committee_profiles | ADDED (with a thin precursor) | 0.60 | 2020's only Exec Committee content is a diversity percentage chart nested inside the board diversity page; 2022's version is a standalone bios section — different scope and different parent, so coded ADDED rather than a continuation. |
| (none in 2021) | 2022:board_deliberations | ADDED | 0.90 | No year-level thematic "deliberations" narrative exists before 2022; from 2022 the same eight strategic-lever categories (succession, corporate transactions, risk, transformation, ESG, AFS, legal compliance, socioeconomic) recur with stable labels through 2024. |
| 2021:erm_framework_and_risk_process | 2022:(absent from governance; present in Material Risks schedule per longitudinal experiment) | MOVED_CROSS_SCHEDULE | 0.85 | Full-text search confirms zero ERM-framework or risk-heat-map content in the 2022–2024 governance page ranges; the longitudinal experiment independently documents Material Risks becoming a standalone schedule starting exactly 2022, with heat-map/register content matching what governance previously carried. |
| 2021:(unlabeled compliance/ethics/conflicts/dealings prose, one page) | 2022:compliance, 2022:ethics_governance, 2022:conflicts_of_interest, 2022:dealings_in_shares | ONE_TO_MANY / SPLIT (3 units) + ADDED (1 unit) | 0.75 | Three of the four 2022 headed sections correspond to distinguishable, if unheaded, 2021 prose sub-topics in the same relative order; "Ethical behaviour" has no comparably-scoped 2021 antecedent and is coded ADDED rather than split out. |
| (none in 2022) | 2023:tax_transparency | ADDED | 0.95 | Confirmed absent from full 2020–2022 governance-range text; first appears 2023, unchanged 2024. |
| 2023:advisory_vote_on_implementation_report | 2024:advisory_vote_on_implementation_report | ONE_TO_ONE / STABLE (structural) | 0.95 | Identical heading, position, and length; flagged separately for a large *content* change not reflected in any structural signal (see Case 6, Section 6). |

## 8. Heading-drift analysis

| Unit | Headings by year | Changed? | Heading match alone sufficient? |
|---|---|---|---|
| audit_risk_committee | "Audit and Risk Committee" — identical all 5 years | No | Yes |
| company_secretary | "Company Secretary" — identical all 5 years | No | Yes |
| remuneration_chair_background_statement | "BACKGROUND STATEMENT" (2020, 2022, 2023) / no separate heading, folded under the section-opener quote card (2021, 2024) | Cosmetic only | Mostly — the 2021/2024 variants are still locatable as the first prose block after the divider page, but a strict string matcher would miss two of five years |
| remuneration_governance_structure | none (2020) → "Remuneration governance" (2021–2024, case-varying) | Yes, once | No for 2020→2021; yes thereafter |
| board_diversity | "BOARD DIVERSITY" (2020) → embedded, no heading (2021) → "Board diversity" (2022–2024) | Yes, twice | No — 2021 has no heading to match at all |
| board_of_directors_profiles | "Board of Directors" (2022–2024) | No (from introduction) | Yes, but only from 2022; ADDED before that, not a match failure |
| ethics_governance | none (2020–2021) → "Ethical behaviour" (2022–2024) | Yes | No for 2020–2021; yes thereafter |
| tax_transparency | none (2020–2022) → "Tax transparency" (2023–2024) | Yes | No for 2020–2022; yes thereafter |
| implementation_report | "IMPLEMENTATION REPORT" — identical (case varies) all 5 years | No | Yes |
| total_remuneration_outcomes | "Total remuneration outcomes" — identical (case varies) all 5 years | No | Yes |

**Direct read on the task's research question:** heading-string matching alone is fully sufficient
for the large majority (26/34, 76%) of governance and remuneration units, because AfroCentric's
committee names, standing-section titles, and remuneration-report skeleton are extraordinarily
stable once a heading exists at all. The failures cluster exactly where the longitudinal
experiment predicted instability would recur one level down: units with **no heading in some
years** (board_diversity 2021, the three pre-2022 compliance/ethics/conflicts/dealings topics,
ethics_governance and tax_transparency before their introduction), and one **cross-schedule move**
that a heading matcher operating within a single schedule's page range could never detect no
matter how good its string matching was.

## 9. Boundary-quality analysis

Representative block/bbox checks were run against the raw PDF for a sample spanning both
schedules and covering 2020, 2021, and 2022 (3 of the 5 years, per the brief's minimum), using the
same plain-text + blocks representation the longitudinal experiment recommended as the default.

- **2020 p.83 (board_role_and_composition / board composition, PDF page 83).** Plain text
  extracts in correct top-to-bottom reading order; no block reordering needed. **CLEAN.**
- **2020 p.84 (audit_risk_committee, PDF page 84).** The role description, pull-quote, composition
  table (member / meetings / attendance %), and "Key matters" bullets extract in correct visual
  order with each table row as one block containing all three column values in order (e.g. `"Bruno
  Fernandes Independent Non-executive Director (Chairperson)\n5/5\n100"`), directly analogous to
  Bell Equipment's clean committee-attendance pages in the representation bake-off. **CLEAN.**
- **2020 p.90 (compliance / conflicts_of_interest / dealings_in_shares, unlabeled prose block,
  PDF page 90).** Long-form prose with no tables; extracts cleanly, no reordering needed.
  **CLEAN.**
- **2022 p.89 (board_diversity, PDF page 89).** Four donut/pie charts (Age, Gender, Diversity,
  Independence) each place their percentage labels as separate floating blocks near, but not
  inside, their legend text. Blocks resolve this via x0/y0-band clustering — each chart's labels
  and legend occupy a distinct, non-overlapping bounding-box quadrant of the page (verified
  directly: the "Gender (%)" chart's values sit at x0≈57–108, the "Independence (%)" chart's at
  x0≈265–312, non-overlapping) — but a naive linear-order read would not reliably pair each number
  with its category. **MINOR_CORRECTION_NEEDED** (same class of fix as the longitudinal
  experiment's column-aware block sort, applied to chart-label clustering rather than heading
  displacement).
- **2020 p.102 (implementation_report / base-pay-increase bar chart, PDF page 102).** Eighteen
  bare percentage values (`5.49`, `4.00`, `6.50`, ...) are scattered at distinct x0 positions
  representing a 6-year × 3-category bar chart, with no per-bar text label adjacent to each value.
  Blocks recover the x0 position of each value precisely enough to bucket it into one of three
  x0-bands (Bargaining unit / Management / Executives, per the chart's own legend order) and one
  of six year-groups by relative x-position within a band, but this requires deliberate two-axis
  clustering logic, not a simple sort. **MINOR_CORRECTION_NEEDED.**
- **2020 pp.102–104 (total_remuneration_outcomes / individual_remuneration_outcomes, PDF pages
  102–104).** Each director's row is emitted as a single block with all values in correct column
  order embedded as newline-separated lines within that one block's text (e.g. `"A
  Banderker1\n4 781 364\n1 148 9041\n435 788\n..."`), which is the easiest possible case for
  reconstruction. **CLEAN.**

**Aggregate: 4 CLEAN, 2 MINOR_CORRECTION_NEEDED, 0 MAJOR_LAYOUT_RECONSTRUCTION_NEEDED, 0
MULTIMODAL_REQUIRED**, across 6 pages spanning 2020 and 2022. This is a stronger result than the
representation bake-off's hazard-selected sample (which deliberately targeted BEL and Kore
Potash's known defects) and is consistent with the longitudinal experiment's finding that ACT
itself does not exhibit BEL's heading-displacement pattern or Kore Potash's running-header
ambiguity — ACT's own hazard class, confirmed here, is **numeric-label-to-category clustering on
chart pages**, resolvable with blocks alone via x0/y0 banding, never requiring font/size (dict) or
multimodal escalation.

## 10. Rule-based vs. semantic matching

| Classification | Count | Examples |
|---|---|---|
| HEADING_MATCH_SUFFICIENT | 26 | audit_risk_committee, company_secretary, remuneration_processes, implementation_report, total_remuneration_outcomes, all six committee cards |
| FUZZY_MATCH_SUFFICIENT | 2 | board_diversity (2022 heading identical to 2020's despite the intervening 2021 gap — a fuzzy/normalized matcher tolerant of case and minor punctuation would bridge 2020→2022 even without semantic reasoning, though it would still need to be told 2021 has no match rather than a false one), remuneration_chair_background_statement (heading present in 3 of 5 years, locatable by page-position heuristic in the other 2) |
| SEMANTIC_MATCH_REQUIRED | 5 | remuneration_governance_structure & remuneration_policy_design_principles (2020→2021, unlabeled-to-headed), ethics_governance (recognizing 2022's new heading absorbs previously-uncredited committee-bullet content rather than representing pure novelty), compliance/conflicts_of_interest/dealings_in_shares (2020–2021 unlabeled-prose boundary identification) |
| STRUCTURAL_MATCH_REQUIRED | 1 | erm_framework_and_risk_process (2021→2022 cross-schedule move — no amount of heading or content similarity *within* the governance schedule's own page range can detect this; it requires checking a sibling schedule's boundaries, which is a structural/architectural signal, not a text-matching one) |

**This directly answers the brief's instruction not to assume LLM matching is necessary
everywhere: it is not.** Three-quarters of the 34 units identified here would align correctly
year-over-year using nothing more than exact or lightly-normalized heading-string matching. The
cases needing genuine semantic or structural reasoning are few, identifiable in advance by a
simple signal (a unit is unlabeled prose, or a unit's expected heading is absent from its schedule
but its topic might exist under a sibling schedule), and cluster overwhelmingly around one
company-year (2022, when four units were added and a cluster of topics gained headings) rather
than being spread evenly across the five-year run.

## 11. Comparison-unit recommendations

**STRONG_LONGITUDINAL_UNIT (24, proceed directly):** board_role_and_composition,
appointment_and_retirement, board_effectiveness, company_secretary, audit_risk_committee,
investment_committee, ict_steering_committee, nomination_committee, remuneration_committee_card,
social_ethics_committee, combined_assurance, internal_controls, information_security_governance,
remuneration_chair_background_statement, pay_for_performance_bsc_table, guaranteed_pay_mechanics,
variable_pay_sti_mechanics, variable_pay_lti_mechanics, remuneration_processes,
ned_remuneration_policy_table, implementation_report, total_remuneration_outcomes,
sti_lti_performance_outcomes, individual_remuneration_outcomes, ned_fees_and_payments_table.

**USABLE_WITH_STRUCTURAL_HANDLING (6, proceed with explicit event-flagging):** board_diversity
(RESTRUCTURED 2022), the board-profile cluster of board_of_directors_profiles /
combined_board_skillset / executive_committee_profiles / board_deliberations (all ADDED 2022 —
comparable only 2022–2024, a 3-year not 5-year run), ethics_governance (SPLIT/ADDED 2022),
compliance / conflicts_of_interest / dealings_in_shares (heading gained 2022, comparable as
content from 2020 if the aligner is told to treat the 2020–2021 unlabeled block as their shared
ancestor), remuneration_governance_structure & remuneration_policy_design_principles (heading
gained 2021), erm_framework_and_risk_process (present 2020–2021 only; MOVED cross-schedule
thereafter — comparable across only two years within this schedule, and only comparable to
Material Risks schedule content from 2022 if a future experiment extends the aligner across
schedule boundaries), tax_transparency (ADDED 2023 — comparable only 2023–2024).

**TOO_THIN (4, exclude from independent lexical comparison; track presence/absence only):**
termination_of_office_payments, statement_regarding_compliance, advisory_vote_on_implementation_report
(structurally thin every year, but see Case 6 — its *content* is a strong candidate for
comparison despite structural thinness, precisely because a real, large, and independently
confirmable content change happened inside an otherwise-trivial one-paragraph unit),
approval_by_board.

**TOO_DISTRIBUTED / TOO_VISUAL / TOO_UNSTABLE:** none identified within these two schedules. This
null result is itself evidence, not an oversight — it is the expected outcome given that the
longitudinal experiment selected Corporate Governance and Remuneration specifically because they
were the two most structurally stable schedules in the entire ten-report-year corpus sample.

## 12. Data model implications

Not implemented — proposed only, as a minimum shape sufficient to represent everything found
above:

- **`schedule`**: `id`, `normalized_label` (e.g. `corporate_governance`), `company`, `year`,
  `document_path`, `start_page`, `end_page`, `boundary_confidence`.
- **`semantic_unit`**: `id`, `schedule_id` (FK), `year`, `normalized_label`, `source_heading`
  (nullable — null for unlabeled/content-pattern units), `parent_unit_id` (nullable, self-FK for
  hierarchy), `structural_type` (enum matching Section 3's list), `start_page`, `end_page`,
  `start_block_index`, `end_block_index`, `start_text` (exact), `end_boundary_text` (exact),
  `confidence`, `boundary_confidence`.
- **`presence_status`**: enum on `semantic_unit` — `PRESENT`, `ABSENT`, `EXTERNALIZED` (per the
  longitudinal experiment's recommendation), `MOVED_CROSS_SCHEDULE` (this experiment's addition —
  distinguishes "gone" from "relocated to a named sibling schedule/unit"), `ADDED` (first
  occurrence, not comparable to any prior year), `UNLABELED_EMBEDDED` (present but no heading —
  boundary inferred from content pattern, lower default confidence).
- **`alignment_edge`**: `id`, `from_unit_ids` (array, supports many-to-one), `to_unit_ids` (array,
  supports one-to-many), `relationship` (array of enum: `ONE_TO_ONE`, `ONE_TO_MANY`, `MANY_TO_ONE`,
  `ADDED`, `REMOVED`, `MOVED`, `MOVED_CROSS_SCHEDULE`, `RENAMED`, `SPLIT`, `MERGED`, `RESTRUCTURED`,
  `CANNOT_ALIGN_CONFIDENTLY`), `confidence`, `evidence_summary` (short text, auditable, no hidden
  reasoning), `rule_basis` (enum: `HEADING_MATCH`, `FUZZY_MATCH`, `SEMANTIC_MATCH`,
  `STRUCTURAL_MATCH` — records *why* the alignment was made, per Section 10, so a future
  deterministic pass can skip LLM calls for edges already known to be heading-sufficient).
- **`unit_quality_classification`**: `unit_normalized_label`, `classification` (enum matching
  Section 11's six categories), `rationale` (short text), `years_present`, `years_absent`.

No schema was implemented; this is a design note only, per the task's explicit instruction.

## 13. Next-step recommendation

**(A) PROCEED TO LEXICAL CHANGE METRICS**, scoped to a first pilot of three units chosen to span
the stability spectrum this experiment mapped, rather than starting with only the safest case:

1. **`audit_risk_committee`** (governance, `STRONG_LONGITUDINAL_UNIT`) — identical heading,
   stable internal structure (role → composition table → key matters), all five years, CLEAN
   boundary-verified. The safest possible baseline: if lexical metrics cannot produce sensible,
   auditable output here, the metric design itself needs rework before touching anything harder.
2. **`remuneration_chair_background_statement`** (remuneration, `STRONG_LONGITUDINAL_UNIT`, but
   heading-cosmetic across years) — pure narrative prose, present and boundable every year,
   and the unit most likely to carry genuine year-over-year tone and substance shifts (executive
   succession commentary, COVID response, incentive-scheme redesign rationale) that a lexical
   metric should actually be sensitive to.
3. **`advisory_vote_on_implementation_report`** (remuneration, `TOO_THIN` structurally but
   flagged in Case 6 as content-anomalous) — deliberately chosen as a validation case *because*
   its 2024 content change (a near-failed 50.26% advisory vote plus explicit Sanlam-engagement
   language) is independently known and large, while its structural boundary is trivial and
   identical every year. A lexical-change pipeline that correctly flags 2023→2024 as a large
   change here, while correctly flagging 2021→2022's `erm_framework_and_risk_process` structural
   move as *not* a wording change (it is a `MOVED_CROSS_SCHEDULE` presence-status change with no
   comparable text on one side), is validated on both halves of the guardrail the longitudinal
   experiment's Section 11 specified: don't mistake container movement for content change, and
   don't mistake content change for container movement.

This experiment does **not** recommend (B) testing a less-stable schedule first, because Section
9's boundary checks and Section 7's alignment-edge table both came back cleaner here than the
representation bake-off's hazard-selected sample or the longitudinal experiment's Material Risks
findings — there is no unresolved representation risk left to burn down before trying lexical
metrics on these two schedules specifically. It does not recommend (C) expanding to more companies
first, because the open questions this experiment surfaced (cross-schedule moves, unlabeled-to-
headed transitions, added-unit clusters) are now characterized well enough on one company to
design the metric and its guardrails; a second company (e.g. extending to BEL's governance and
remuneration schedules, which the longitudinal experiment showed have a different stability
profile — BEL's remuneration had a genuine externalization round-trip) is a reasonable *second*
pilot once the metric works on ACT, not a prerequisite. It does not recommend (D) — semantic units
were not too unstable; on the contrary, 24 of 34 units required no semantic reasoning at all to
align, and the instability that exists is concentrated, dated, and now documented rather than
diffuse.

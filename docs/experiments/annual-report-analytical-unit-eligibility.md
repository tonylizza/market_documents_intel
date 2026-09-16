# Experiment: Analytical-Unit Eligibility for Longitudinal Lexical Comparison (AfroCentric, 11 Semantic Units, 2020–2024)

Status: exploratory research only. No production code, database, migrations, or publishing
pipeline was touched. All extraction was performed against
`data/raw/ACT/{2020,2021,2022,2023,2024}/annual_report.pdf` via throwaway PyMuPDF scripts, with
intermediate text dumps written to a session-local scratch directory outside the repository.
Nothing here is wired into the application. This is a direct follow-up to
`docs/experiments/annual-report-within-schedule-alignment.md` ("experiment 4") and
`docs/experiments/annual-report-lexical-change-pilot.md` ("experiment 5"), both assumed read.
Experiment 4's 42-unit segmentation is reused verbatim — no new segmentation was created — and
experiment 5's per-unit findings for `audit_risk_committee`, `remuneration_chair_background_statement`,
and `advisory_vote_on_implementation_report` are reused and re-verified rather than re-derived from
scratch, per this task's brief.

## 1. Executive summary

**No — structural-unit validity is not sufficient to justify lexical comparison, and this
experiment reproduces that finding on a wider sample than experiment 5's three units.** Of the 11
units sampled, only 2 are straightforward `LEXICAL_DIRECT` candidates. The remaining 9 need numeric
context, structured comparison, presence-only tracking, a boundary merge, or exclusion. Structural
validity (a stable heading, a boundable page location, present in all five years — the definition
experiment 4 used) and analytical usefulness (does the unit's own text carry the comparison-worthy
information) are different properties, and this sample shows they diverge often enough that treating
them as the same thing would silently discard or misrepresent real signal in most of the remuneration
schedule.

**Which unit types are good lexical-comparison candidates?** `SUBSTANTIVE_NARRATIVE` units with a
low template share and a stable single-voice authorship (`remuneration_chair_background_statement`,
`company_secretary`) are the clean cases. `company_secretary` is this experiment's best new positive
finding: a short (155–172 word), heavily templated unit that nonetheless produces a real, cheaply
detectable signal — the 2024 personnel change (Billy Mokale → Lebohang Mpumlwana, with a full
he→she pronoun swap through the unit) — precisely because the template's *slots* (a name, a
pronoun) are exactly where the substantive fact lives. This is the mirror image of the advisory-vote
failure: short and templated is not automatically useless, if the template's variable slots are
where the real information is.

**Which are not?** Table/numeric-dominant units (`ned_remuneration_policy_table`,
`total_remuneration_outcomes`, `implementation_report`'s own prose) and pure-procedural thin units
(`advisory_vote_on_implementation_report`, `statement_regarding_compliance`, `approval_by_board`,
and — a new finding this experiment adds — `remuneration_processes`) are poor standalone lexical
units for different, specific reasons documented per-unit below, not because "short = bad."

**How often did the source heading mislead us about where substantive information lived?** Twice in
this sample, in both directions. `advisory_vote_on_implementation_report`'s heading promises a vote
outcome its own text never states — confirmed again in this session (Section 8) — the outcome lives
one unit over, inside `remuneration_chair_background_statement`'s "Shareholder engagement and
voting" subsection. `implementation_report`'s heading promises a report, but its own prose is a
single unchanging sentence; the actual "implementation report" content is entirely in its four child
units (`total_remuneration_outcomes` and siblings per experiment 4's hierarchy), a heading-implies-
container-not-content pattern distinct from the advisory-vote case. Nine of the 11 units' headings
were directionally accurate about their content, which is a useful base rate: heading text is a
reasonable starting hypothesis, but not a substitute for reading the unit.

**Is thinness itself the problem, or is procedural/boilerplate function more important?** Function,
not length. This experiment newly distinguishes three kinds of "thin" (Section 5): thin-and-
cross-unit-dependent (`advisory_vote_on_implementation_report`), thin-and-truly-invariant
(`statement_regarding_compliance`, word-for-word near-identical every year with no known omitted
fact), and thin-but-genuinely-substantive-and-stable (`remuneration_processes`, exactly 79 words
every single year — the single most invariant unit found in this entire sample — because
AfroCentric's notice-period terms genuinely have not changed, not because the boundary is wrong).
The first needs a boundary fix; the second and third need different treatment (presence-only for one,
accept genuine flatness as a correct finding for the other) despite both being equally short.

**Are numeric-rich units better handled separately?** Yes, clearly. `total_remuneration_outcomes`,
`ned_remuneration_policy_table`, and `implementation_report`'s child tables carry their real,
auditable, and materially significant year-over-year information (a new CEO's remuneration entering
the table in 2024, three 2022 executives' figures dropping to nil in 2023, non-executive fee
percentage increases) as structured numbers, not prose — ordinary lexical metrics would either miss
this (stable surrounding narrative) or register noise (renumbered rows) without ever surfacing the
actual fact. See Section 7.

**Is a separate analytical-unit layer justified?** Yes, on the evidence collected here, but as a thin
classification layer over the existing structural units — not a new ontology. Section 11 proposes
the minimum shape; Section 12 evaluates the full pipeline.

## 2. Sample inventory

| Unit | Schedule | Years | Structural type (per exp. 4) | Why selected |
|---|---|---|---|---|
| `audit_risk_committee` | Corporate Governance | 2020–2024 | committee card (role + key matters + composition table) | stable committee disclosure; already lexically piloted (exp. 5) |
| `social_ethics_committee` | Corporate Governance | 2020–2024 | committee card, same shape as audit_risk_committee | second stable committee disclosure, unpiloted |
| `remuneration_chair_background_statement` | Remuneration | 2020–2024 | standalone long-form narrative | long-form substantive narrative; already lexically piloted (exp. 5); contains the boundary-expansion evidence |
| `remuneration_processes` | Remuneration | 2020–2024 | headed paragraph group | policy/mechanics disclosure candidate |
| `ned_remuneration_policy_table` | Remuneration | 2020–2024 | table-driven | numeric/table-heavy disclosure candidate |
| `advisory_vote_on_implementation_report` | Remuneration | 2020–2024 | thin headed paragraph group | procedural boilerplate; cross-unit-dependent per exp. 5 (required) |
| `approval_by_board` | Remuneration | 2020–2024 | thin headed paragraph group, one dated sentence | approval/sign-off text |
| `company_secretary` | Corporate Governance | 2020–2024 | standalone subsection | short but possibly-substantive disclosure |
| `statement_regarding_compliance` | Remuneration | 2020–2024 | thin headed paragraph group | presence-only candidate; second thin-unit test case |
| `total_remuneration_outcomes` | Remuneration | 2020–2024 | table-driven, sub-unit of implementation_report | meaningful YoY numeric results |
| `implementation_report` | Remuneration | 2020–2024 | standalone parent container | mixed narrative+results parent; tests structural-vs-analytical container question |

All 11 units are drawn from experiment 4's existing 42-unit inventory; none are newly invented.
Page locations below are re-verified in this session by full-text search within experiment 4's own
schedule super-ranges, not copied uncritically from its tables (several of its `~` approximations
turned out to need a one- or two-page correction, noted per unit).

## 3. Source verification and page-location corrections

Corporate Governance schedule super-ranges (as given by experiment 4, re-used unchanged):
2020 pp.73–92; 2021 pp.89–105; 2022 pp.87–110; 2023 pp.101–124; 2024 pp.99–119.
Remuneration schedule super-ranges: 2020 pp.94–106; 2021 pp.106–118; 2022 pp.110–122; 2023
pp.125–138; 2024 pp.119–132.

| Unit | 2020 | 2021 | 2022 | 2023 | 2024 | Correction vs. exp. 4 |
|---|---|---|---|---|---|---|
| audit_risk_committee | p.84 | p.94 | p.100 | p.114 | p.112 | exp.4 said p.97(2022)/p.111(2023)/p.109(2024) `~`; exp.5's own re-verification (reused here) found p.100/p.114/p.112 |
| social_ethics_committee | p.89 | p.99 | p.105 | p.118 | p.115 | exp.4's `~107(2022)/121(2023)/118(2024)` were off by 1–3 pages; the actual committee-card page (role→key matters→composition, not the later "Ethical behaviour" sub-topic) is p.105/p.118/p.115 |
| remuneration_chair_background_statement | p.94 | p.107 | p.110 | p.125–126 | p.120–121 | matches exp.4/exp.5 exactly |
| remuneration_processes | p.101 | p.113 | p.117 | p.132 | p.127 | exp.4 gave only 2020/2021; 2022–2024 located fresh |
| ned_remuneration_policy_table | p.101 | p.113 | p.117 | p.133 | p.127 | same; 2023's table itself is on p.133 (the policy-principles text starts p.132, immediately after remuneration_processes) |
| advisory_vote_on_implementation_report | p.106 | p.118 | p.122 | p.138 | p.132 | matches exp.4/exp.5 exactly |
| approval_by_board | p.106 | p.118 | p.122 | p.138 | p.132 | exp.4 located only 2020–2022 (`~p.106` for 2020); heading is "APPROVAL OF THE REMUNERATION REPORT BY THE BOARD" (all four words), not just "Approval by the Board" — this string difference is why an initial naive search of this session's own script missed 2023/2024 until the full page text was read directly |
| company_secretary | p.81 | p.91 | p.99 | p.113 | p.111 | matches exp.4 |
| statement_regarding_compliance | p.106 | p.118 | p.122 | p.138 | p.132 | matches exp.4; co-located with advisory_vote and approval_by_board on the same page every year (Section 6) |
| total_remuneration_outcomes | p.102 | p.114 | p.118 | p.134 | p.128 | exp.4 gave only 2020/2021; 2022–2024 located fresh |
| implementation_report | p.102 | p.114 | p.118 | p.134 (heading itself is one page earlier, p.133, immediately after the NED remuneration table) | p.128 | exp.4 gave only 2020/2021; 2022–2024 located fresh; 2023's heading position corrected (see Section 10) |

**A structural correction found in this session, not previously documented**: `termination_of_office_payments`,
`statement_regarding_compliance`, `advisory_vote_on_implementation_report`, and `approval_by_board`
are not four separately-located thin units scattered across the remuneration schedule — they are
**four consecutive headings on the single final page of the remuneration schedule, every year**,
immediately following the NED payments table (Section 6 quotes the full page for all five years).
Experiment 4's per-unit page table implied independent locations (`~p.106` for each); in fact all
four share one page, in the same order, every year: `PAYMENTS MADE TO NON-EXECUTIVE DIRECTORS` →
`TERMINATION OF OFFICE PAYMENTS` → `STATEMENT REGARDING COMPLIANCE...` → `ADVISORY VOTE ON THE
IMPLEMENTATION REPORT` → `APPROVAL OF THE REMUNERATION REPORT BY THE BOARD`. This clustering is
itself evidence for this experiment's central finding: four structurally distinct headings packed
onto one page, back-to-back, each one or two sentences long, is a strong a priori signal that none
of them was designed by the report's authors to carry an independent, extended analytical narrative
— they are a sign-off block, not four separate disclosures.

## 4. Per-unit analysis

### 4.1 `audit_risk_committee`

Source heading "Audit and Risk Committee" / "AUDIT AND RISK COMMITTEE," identical every year.
Word counts (reused from exp. 5, spot-verified): 369 (2020), 345 (2021), 325 (2022), 336 (2023), 367
(2024). Boilerplate: MEDIUM — the role description and "key matters" framing sentences repeat
near-verbatim, but the composition table and 40–60% of the bullet content refresh with real
membership/attendance data every year. Numeric dependence: MEDIUM (attendance fractions/percentages
throughout). Substantive content location: inside the unit itself — role, key matters, and
composition all sit under the one heading, no displacement found. Cross-unit dependence: none found.
Recommended analytical type: `MIXED_NARRATIVE_AND_RESULTS`. Recommended treatment:
`LEXICAL_WITH_NUMERIC_CONTEXT` (B) — exp. 5 already validated that ordinary lexical metrics behave
sensibly here and track real committee-composition churn (2020→2021 chairperson change; 2023→2024
new Sanlam-linked committee members), but the numeric attendance data needs to be read alongside the
lexical scores, not folded into them, because a routine attendance refresh and a real membership
change can look lexically similar.

### 4.2 `social_ethics_committee`

Source heading "Social and Ethics Committee," identical every year, same card shape as
`audit_risk_committee` (role → key matters bullets → composition table), located this session at
p.89/99/105/118/115. Full-page word counts (role+key-matters+composition, approximate — includes
a small amount of adjoining "Composition" table-label overlap since the unit runs to the top of the
next unrelated section on the same page in every year): 268 (2020), 273 (2021), 297 (2022), 276
(2023), 315 (2024). Boilerplate: MEDIUM — six of the seven "key matters" bullets are near-identical
across all five years (e.g. "Ensured Group compliance to/with the B-BBEE Act," "Oversees/Oversaw
stakeholder engagement," "Monitored ethical standards within the Company. The committee confirms
that no material breaches occurred" — this exact sentence, word-for-word, appears in 2020, 2022,
2023, and 2024). One bullet is genuinely added over time ("Led initiatives to combat corruption,
including fraud, waste and abuse..." first appears 2022; "Revised the committee's terms of reference
to align with King IV" first appears 2024). Numeric dependence: MEDIUM (attendance table). Cross-unit
dependence: none found — unlike `ethics_governance` (a sibling unit per experiment 4, not sampled
here), this committee-card unit is self-contained. Recommended analytical type:
`MIXED_NARRATIVE_AND_RESULTS`. Recommended treatment: `LEXICAL_WITH_NUMERIC_CONTEXT` (B) — the same
class as `audit_risk_committee`, and this experiment's evidence (the repeated near-verbatim key-matters
bullets) suggests it will show the same pattern of low-to-moderate baseline similarity with real
membership-churn dips, though full metric computation was not repeated here (out of scope per the
task brief, which asks for eligibility classification, not metric re-optimization).

### 4.3 `remuneration_chair_background_statement`

Reused from exp. 5: word counts 734/882/868/1,234/1,401 across 2020–2024, boilerplate LOW (genuinely
different substantive content dominates: COVID response 2020, STI mechanics 2021, LTI redesign 2022,
four-objective people-strategy expansion 2023, Sanlam-acquisition narrative 2024). Numeric dependence:
LOW-MEDIUM at the whole-unit level but concentrated in one embedded subsection (the shareholder
voting-results table/narrative). Substantive content location: mostly inside the unit itself, with
one important exception — see Section 8, this unit's own "Shareholder engagement and voting"
subsection is where `advisory_vote_on_implementation_report`'s heading-implied content actually lives.
Cross-unit dependence: this unit is the *recipient* of the advisory-vote unit's substantive content,
not itself dependent on a neighbor. Recommended analytical type: `SUBSTANTIVE_NARRATIVE`, with an
embedded `NUMERIC_RESULTS` sub-block. Recommended treatment: `LEXICAL_DIRECT` (A) for the prose as a
whole per exp. 5's validated result, with the caveat (new to this experiment) that the analytically
correct container for shareholder-voting content is this unit, not `advisory_vote_on_implementation_report` —
see Section 8's boundary-expansion test.

### 4.4 `remuneration_processes`

Source heading "Remuneration processes" / "REMUNERATION PROCESSES," identical every year, opens
directly into a sub-heading "Service contracts and notice periods." Word count, isolated from the
immediately-adjacent NED remuneration table: **exactly 79 words in all five years**, the single most
invariant unit measured in this entire sample. Quoted in full, 2020:

> "AfroCentric can summarily terminate executive employment for any reason recognised by law in the
> respective jurisdiction. It is policy that the Executive Directors and executives have employment
> agreements with the Group which may be terminated with a three-month notice period. Executive
> Directors may be required to work during the notice period but, if not, the full notice period may
> be provided with pay in lieu of notice (subject to mitigation where relevant)."

2024's version differs only in "but if not," (no comma) vs. 2020's "but, if not,", and "which may be
terminated" (2020, 2022–2024) vs. "that may be terminated" (2021) — a single word swapped once across
four transitions, otherwise character-for-character identical. Boilerplate: HIGH — this is not
merely template-like, the underlying policy fact (a three-month notice period, standard South African
employment-law terms) genuinely has not changed in five years. Numeric dependence: none within this
unit itself (the three-month figure is stated but never varies). Substantive content location: fully
inside the unit; there is no missing fact elsewhere — this experiment specifically checked the
surrounding pages for a "notice period changed" event and found none. Cross-unit dependence: none.
Recommended analytical type: `PROCEDURAL_BOILERPLATE`-adjacent but functionally a `SUBSTANTIVE_NARRATIVE`
policy statement that happens to have zero real-world change to report. Recommended treatment:
`TOO_THIN_FOR_LEXICAL` structurally (E, `PRESENCE_STATUS_ONLY`) — not because the disclosure is
unimportant, but because 79 near-identical words cannot support a meaningful similarity ranking; the
analytically correct output for this unit across five years is "no change to notice-period policy,"
a single boolean fact, not five lexical-similarity scores that will all read ≈0.97–1.0 regardless of
whether anything happened. This is a genuinely different case from `advisory_vote_on_implementation_report`
(Section 5): there is no missing evidence elsewhere for this unit, the flatness is the correct answer.

### 4.5 `ned_remuneration_policy_table`

Immediately follows `remuneration_processes` under the heading "Non-executive Directors' remuneration" /
"NON-EXECUTIVE DIRECTORS' REMUNERATION." Combined word count for the policy-principles narrative
that precedes the actual fee table (fee objective, fee principles bullets, payable schedule): 168–170
words per year (247–249 combined with remuneration_processes minus remuneration_processes' 79 =
~168–170), near-identical across all five years — the same "Fees are reviewed annually...", "Fees
reflect the time commitments...", "Fees are fully inclusive", "The Remuneration Committee recommends
the fees to the Board for final approval" bullet block repeats essentially verbatim (bullet-marker
style changes from `»»` to `»` to `•` across years, a formatting artifact not a content change). The
actual fee table itself (a separate structured block, e.g. 2023's "CURRENT 2023 / PROPOSED 2024 /
PROPOSED INCREASE %" table with a consistent 5.0% annual increase across every fee line for 2023→2024)
carries the real year-over-year information — new fee amounts, a proposed increase percentage per
role — and is not prose at all. Boilerplate: HIGH for the narrative half, N/A (the table has no
"boilerplate" concept) for the structured half. Numeric dependence: HIGH — the entire analytical
value of this unit is in the table, not the surrounding policy-principles prose. Substantive content
location: the table, not the prose. Cross-unit dependence: none. Recommended analytical type:
`SUBSTANTIVE_STRUCTURED`. Recommended treatment: `STRUCTURED_COMPARISON_PREFERRED` (C) — ordinary
lexical metrics on the prose half would report near-total stability every year (correctly, but
uninformatively), while the table's row-level fee percentages are where a future pipeline should
actually compare years.

### 4.6 `advisory_vote_on_implementation_report`

Reused and re-verified from exp. 5. Heading "Advisory vote on the implementation report" (case
varies), 41 words every year, confirmed this session on p.106/118/122/138/132. Full boilerplate
quoted in Section 6. Boilerplate: HIGH. Numeric dependence: the only numeric content is the AGM year
token (appears twice), which carries no vote-outcome information. Substantive content location:
**not in this unit** — the 50.26% 2024 vote result and Sanlam-engagement language are absent from
this unit's own text in every year checked, including 2024 (Section 6 quotes the full 2024 page;
the advisory-vote paragraph is template-identical to every prior year). Cross-unit dependence:
**confirmed, strong** — the content this unit's heading implies lives in
`remuneration_chair_background_statement`'s "Shareholder engagement and voting" subsection (Section
8). Recommended analytical type: `PROCEDURAL_BOILERPLATE` / `CROSS_UNIT_DEPENDENT`. Recommended
treatment: `MERGE_WITH_PARENT_OR_NEIGHBOR` (D) — this experiment's boundary-expansion test (Section 8)
provides new quantitative support for this recommendation beyond exp. 5's qualitative finding.

### 4.7 `approval_by_board`

Source heading "APPROVAL OF THE REMUNERATION REPORT BY THE BOARD" (this experiment's correction to
exp. 4's shorter "Approval by the Board" label — the full heading text matters for any future
heading-matcher). One sentence, dated, every year:

> 2020: "The remuneration report was approved by the Board on 10 September 2020."
> 2021: "The Board approved the remuneration report on 13 September 2021."
> 2022: "The Board approved the remuneration report on 8 September 2022."
> 2023: "The Board approved the remuneration report on 14 September 2023."
> 2024: "The Board approved the remuneration report on 8 October 2024."

Word count: 11–13 words every year. Boilerplate: HIGH for sentence structure (2021–2024 share one
template, "The Board approved... on [date]"; 2020 alone uses a passive-voice variant, "was approved
by the Board"). Numeric/date dependence: this unit's *entire* substantive content is a date. Note:
2024's approval date (8 October) is a full three to five weeks later than every prior year's
(8–14 September) — a genuine, if minor, timing signal (plausibly tied to the wider 2023/2024
Sanlam-related governance transition documented elsewhere in this corpus) that a lexical-similarity
metric would report as "unchanged" (the sentence template is identical) while a naive numeric-token
diff would report as "one date changed" without flagging that the change is unusually large relative
to the four prior transitions. Substantive content location: fully inside the unit; no cross-unit
dependence found. Recommended analytical type: `APPROVAL_OR_SIGNOFF`. Recommended treatment:
`PRESENCE_STATUS_ONLY` (E) — track the approval date as a structured fact (and optionally its
day-count delta from the prior year's date), not as lexical similarity; lexical metrics on this unit
would report near-total stability every year regardless of the date's actual behavior, which is the
wrong signal for what this unit is actually for.

### 4.8 `company_secretary`

Source heading "Company Secretary," identical every year, located p.81/91/99/113/111. Word counts:
172 (2020), 162 (2021), 160 (2022), 155 (2023), 155 (2024) — a steady, mild contraction, not a
boundary artifact (checked: no content moved elsewhere; later years simply drop a clause or two of
the same three recurring paragraphs — role/independence, support-to-Board, share-dealing focal
point). Boilerplate: HIGH at the sentence-template level (three near-identical paragraphs recur
every year with the same function and mostly the same wording), but this experiment's key finding is
that **the boilerplate's variable slots (the incumbent's name and gendered pronoun) are exactly
where the one real fact lives**: 2020–2023 read "Billy Mokale is the Group Company Secretary. ...
he possesses..." / "he continues..." throughout; 2024 reads "Lebohang Mpumlwana is the Group Company
Secretary. ... she possesses..." / "she supports..." — a company secretary change, correctly and
cheaply detectable by ordinary word-level lexical metrics (the name and every `he`/`his` token would
flip to `she`/`her`, producing a real, non-trivial 2023→2024 dip in unigram Jaccard against an
otherwise near-1.0 baseline in the other three transitions). Numeric dependence: none. Substantive
content location: fully inside the unit. Cross-unit dependence: none found. Recommended analytical
type: `SUBSTANTIVE_NARRATIVE`. Recommended treatment: `LEXICAL_DIRECT` (A) — this is this
experiment's clearest positive validation case for "short and templated does not automatically mean
unsuitable," precisely because the company-secretary role's core fact (who holds it) is stated inside
the unit's own template, unlike the advisory-vote case where the core fact is not.

### 4.9 `statement_regarding_compliance`

Source heading "Statement regarding compliance with the remuneration policy" (case varies), located
on the same final remuneration-schedule page as `advisory_vote_on_implementation_report` and
`approval_by_board` every year (Section 6). Full text, essentially word-for-word across all five
years:

> "The committee satisfied itself that the remuneration policy as detailed in the report was
> complied with, and there were no substantial deviations from the policy during the year."

(2021 alone inserts two commas around "as detailed in the report" — a punctuation-only variant.)
Word count: 26–27 words every year. Boilerplate: HIGH, arguably the highest in the sample — unlike
`advisory_vote_on_implementation_report` (which at least varies by an interpolated AGM year) and
`remuneration_processes` (79 words with one single-word swap across four transitions), this unit's
wording is essentially fixed with no interpolated variable at all. Numeric dependence: none. Cross-
unit dependence: **not confirmed** in this sample — this experiment specifically checked whether a
material remuneration-policy compliance issue was reported anywhere else in the 2020–2024 corpus and
found none (unlike the advisory-vote case, there is no independently known real-world event this
unit's flatness might be hiding). Recommended analytical type: `PROCEDURAL_BOILERPLATE` /
`TOO_THIN_FOR_LEXICAL`. Recommended treatment: `PRESENCE_STATUS_ONLY` (E) — track whether the
sentence's polarity ever flips (i.e., whether the committee ever *fails* to give a clean compliance
statement), which would be a rare, high-signal, presence/absence-style event, not a wording-change
event a similarity metric is built to detect.

### 4.10 `total_remuneration_outcomes`

Source heading "Total remuneration outcomes" / "TOTAL REMUNERATION OUTCOMES," identical every year,
immediately follows `implementation_report`'s one-sentence framing and a base-pay-increase bar
chart. Entirely a "Single figure remuneration (R'000)" table (Base pay / Benefits and allowances /
STI / LTI / Total remuneration, by named executive director, current year vs. prior year columns).
No independent prose beyond the table's own row/column labels. Word count is not a meaningful measure
for this unit (it is almost entirely numeric cells); the label/header text is 20–30 words and
identical in structure every year. Boilerplate: N/A (table-structural, not prose-boilerplate).
Numeric dependence: total (this unit's entire content). Real, material, auditable year-over-year
change confirmed directly: Ahmed Banderker's (then-CEO) STI+Retention award line jumps from
R1,780,345 (2022) to R20,252,268 (2023), his total remuneration rises from R7,337,734 to
R27,545,998; two 2022 executives (W Britz, S Mmakau) drop to nil across all columns in the 2023
table; by 2024 a new Group CEO (G van Wyk) enters the table for the first time (R9,377,958 total)
while Banderker's own 2024 figures fall to a partial-year R1,927,224 (prorated departure), with an
explicit `*` footnote pattern the table itself uses to mark such transitions. Substantive content
location: fully inside the unit (the table). Cross-unit dependence: this unit's own one-line framing
sentence ("It is the view of the Remuneration Committee that the remuneration policy achieved its
stated objective") is shared, word-for-word, with the parent `implementation_report` unit — see
Section 4.11. Recommended analytical type: `NUMERIC_RESULTS`. Recommended treatment:
`STRUCTURED_COMPARISON_PREFERRED` (C) — this is the clearest case in the sample of "wording is
irrelevant, structured comparison is the entire analytical task."

### 4.11 `implementation_report`

Source heading "IMPLEMENTATION REPORT" (case varies), identical every year, located p.102/114/118/
133–134/128. Its *own* prose, independent of its four child sub-units per experiment 4's hierarchy
(`total_remuneration_outcomes`, `sti_lti_performance_outcomes`, `individual_remuneration_outcomes`,
`ned_fees_and_payments_table`), is exactly one sentence, confirmed identical in every year checked:

> "It is the view of the Remuneration Committee that the remuneration policy achieved its stated
> objective."

followed immediately by the base-pay-increase bar chart (six years of percentage data per employee
category, a numeric block, not prose). Boilerplate: at the parent level, effectively 100% — the
one sentence never varies. Numeric dependence: total, but delegated — the parent unit's own numeric
content (the base-pay-increase chart) is itself largely stable in shape (Bargaining unit / Management
/ Executives categories recur every year) with year-over-year percentage changes that are genuinely
informative but modest (typically 3.5–7.0% band, no large swings observed in the years sampled).
Substantive content location: **overwhelmingly in the children, not the parent's own text** — this
is a different flavor of the boundary-mismatch problem than `advisory_vote_on_implementation_report`'s
(content in a *sibling*): here the heading's implied content ("a report on implementation") is
correctly scoped as a whole, but almost none of the actual reportable information sits in the
parent's own prose span; it sits one level down, in the child units this experiment sampled
separately (`total_remuneration_outcomes`) and others it did not (the three siblings). Cross-unit
dependence: yes, but downward (to children) rather than sideways (to a neighbor), which the eligibility
taxonomy in this brief does not have a dedicated category for — see Section 11's data-model
discussion. Recommended analytical type: at the parent-prose level, `PROCEDURAL_BOILERPLATE`; the
unit as a *container* is best understood as `MIXED_NARRATIVE_AND_RESULTS` only because its children
are. Recommended treatment: **split by level** — the parent's own one-sentence text should be tracked
`PRESENCE_STATUS_ONLY` (E) (does the Committee's "achieved its stated objective" framing ever change
— e.g., to a qualified or negative statement — which would itself be a high-signal event), while the
actual comparison work happens at the child level, primarily `STRUCTURED_COMPARISON_PREFERRED` (C)
per `total_remuneration_outcomes` above. This unit is this experiment's clearest illustration of why
a structural parent should not automatically be treated as one analytical unit.

## 5. Structural vs. analytical boundary case studies

**`advisory_vote_on_implementation_report` (required case).** Structurally perfect: identical
heading, identical page-relative position (always the third of the four-heading sign-off cluster
documented in Section 3), identical 41-word length, every year. Analytically empty on its own — see
Section 8 for the full boundary-expansion test. This is the case both this experiment and exp. 5
were designed around.

**A short approval/compliance unit — `approval_by_board`.** Structurally perfect in the same way
(Section 4.7). Analytically, it is not empty in the way advisory-vote is — its one variable (the
approval date) is a real, self-contained fact, not a promise of content that lives elsewhere. The
correct treatment is not "merge with a neighbor" (there is no neighbor holding hidden content) but
"stop treating an 11-word sentence as a lexical-comparison target and start treating it as a
structured date field." This is a materially different diagnosis from the advisory-vote case despite
both units looking, structurally, almost identical (same page, same length class, same "thin headed
paragraph group" structural type in exp. 4's own classification).

**A substantive long-form narrative — `remuneration_chair_background_statement`.** The clean
positive case, reused from exp. 5: genuinely different content dominates every transition, lexical
metrics rank the transitions sensibly, and its main analytical subtlety (Section 8) is not that it
lacks content but that it is the *correct home* for content another unit's heading claims but does
not deliver.

**A numeric/table-heavy unit — `total_remuneration_outcomes`.** The clean case for the opposite
conclusion: real, large, human-legible year-over-year change (a near-4x increase in one executive's
recorded STI/retention line; a change of Group CEO reflected as a new named row) that lexical
similarity metrics were never designed to represent, because the "text" is column headers and names
around numbers, not sentences. Structured numeric comparison, not prose diffing, is the native
representation here.

## 6. Thin-unit analysis

Three thin units (≤80 words) were directly compared: `advisory_vote_on_implementation_report` (41
words), `statement_regarding_compliance` (26–27 words), `remuneration_processes` (79 words, thin
relative to the 700–1,400-word narrative units but the longest of the three). A fourth,
`approval_by_board` (11–13 words), is thinner still. **"Too short" is not, by itself, the right
exclusion rule** — the four thin units in this sample fail (or succeed) for four different reasons:

| Unit | Words | Why thin | Cross-unit dependence | Correct treatment |
|---|---:|---|---|---|
| `advisory_vote_on_implementation_report` | 41 | procedural notice, template with one interpolated variable (AGM year) that carries no outcome information | **Yes, confirmed** — vote outcome lives in `remuneration_chair_background_statement` | Merge/expand boundary (D) |
| `statement_regarding_compliance` | 26–27 | procedural attestation, near-zero variation, no interpolated variable at all | Not confirmed in this sample | Presence/polarity tracking only (E) |
| `remuneration_processes` | 79 | genuinely substantive policy statement whose real-world referent (notice-period terms) has not changed | None found | Presence/stability tracking only (E) — the flatness is the correct finding, not a boundary defect |
| `approval_by_board` | 11–13 | formal sign-off, entire content is a date | None found | Structured date field, not lexical (E) |

The distinction that matters is not thin-substantive vs. thin-procedural vs. thin-numeric vs.
thin-approval as separate exclusion buckets — it is **whether the unit's own text is the intended
container for its analytically important fact.** `remuneration_processes` and `statement_regarding_compliance`
are both thin and both flat, but for opposite epistemic reasons: the first is thin because nothing
changed (a true, stable fact worth recording as "unchanged"), the second is thin because it was
never designed to carry variable content in the first place (there is no known instance in this
corpus of it doing otherwise). `advisory_vote_on_implementation_report` is thin *and* actively
misleading, because its heading promises exactly the kind of variable content the other two units
never claim to have. Word count alone cannot distinguish these three cases; only reading the unit
against its own heading's implicit promise, and checking neighboring units, can.

## 7. Boilerplate analysis

Boilerplate share, by unit, with the most invariant quoted patterns:

- **`remuneration_processes` — HIGH (near-total).** "AfroCentric can summarily terminate executive
  employment for any reason recognised by law in the respective jurisdiction" appears character-for-
  character identical in 4 of 5 years and differs by one word ("which"/"that") in the fifth.
- **`statement_regarding_compliance` — HIGH (near-total).** "The committee satisfied itself that the
  remuneration policy as detailed in the report was complied with, and there were no substantial
  deviations from the policy during the year" — identical in 4 of 5 years, differs only by two
  inserted commas in the fifth.
- **`advisory_vote_on_implementation_report` — HIGH, with one interpolated variable.** "The
  implementation report, as it appears above, is subject to an advisory vote by shareholders at the
  *[YEAR]* AGM. Accordingly, shareholders are requested to cast an advisory vote on the remuneration
  policy's implementation for *[YEAR]*." — the AGM year is the only token that ever changes (exp. 5's
  finding, re-confirmed for 2024 in this session, Section 6).
- **`approval_by_board` — HIGH template, with one interpolated date.** "The Board approved the
  remuneration report on *[DATE]*" (2021–2024) / "The remuneration report was approved by the Board
  on *[DATE]*" (2020, a passive-voice variant of the same template).
  ned_remuneration_policy_table's narrative half — HIGH.** "Fees are reviewed annually...", "Fees
  are fully inclusive", "The Remuneration Committee recommends the fees to the Board for final
  approval" recur near-verbatim every year; only the bullet-marker glyph (`»»`→`»`→`•`) changes,
  a formatting artifact.
- **`company_secretary` — HIGH at the sentence-template level, but the template's slots carry real
  content.** "[Name] is the Group Company Secretary. The Board is satisfied that [he/she] possesses
  the requisite qualifications..." — the sentence shape never changes, but the name and pronoun do,
  exactly once, in 2024 (Section 4.8).
- **`audit_risk_committee` / `social_ethics_committee` — MEDIUM.** The "role of the committee" and
  "key matters" *framing* sentences repeat (e.g. `social_ethics_committee`'s "Monitored ethical
  standards within the Company. The committee confirms that no material breaches occurred" — exact
  match in 2020, 2022, 2023, 2024), but the composition tables and a genuine subset of key-matters
  bullets refresh with real content every year.
- **`remuneration_chair_background_statement` — LOW.** No recurring template sentence longer than a
  section-header phrase was found; each year's substantive narrative is materially different prose.

**How boilerplate affects lexical metrics (per exp. 5's own methodology, not re-run here but
directly applicable):** a HIGH-boilerplate unit with an interpolated variable (advisory-vote,
approval-by-board) sets a very high metric floor regardless of real-world events, because the fixed
portion of the text dominates the token set; unigram/bigram Jaccard and TF-IDF cosine will read
0.8–0.95+ every single year whether or not anything meaningful happened, which is exactly the
distortion exp. 5's Section 8 diagnosed for advisory-vote and which generalizes, on this session's
evidence, to `statement_regarding_compliance` and `remuneration_processes` as well — not because
those two units are "broken" the way advisory-vote is, but because a near-ceiling metric score is the
*correct* output for genuinely unchanging text, and a future pipeline must not read "near-1.0 lexical
similarity" as evidence of nothing-to-see when the unit is this kind of template — it needs to know,
structurally, that the unit is expected to be flat, versus needing to actively check a neighbor
(advisory-vote) for the real signal.

## 8. Analytical-boundary expansion test — advisory vote vs. shareholder engagement and voting

**Narrow structural unit A** (`advisory_vote_on_implementation_report`), full text, 2024 (confirmed
this session, p.132):

> "Advisory vote on the implementation report / The implementation report, as it appears above, is
> subject to an advisory vote by shareholders at the 2024 AGM. Accordingly, shareholders are
> requested to cast an advisory vote on the remuneration policy's implementation for 2024."

This is template-identical in structure to 2020–2023's versions (Section 6). No vote result, no
percentage, no company name, appears anywhere in this text.

**Broader analytical unit B** (A + `remuneration_chair_background_statement`'s own "Shareholder
engagement and voting" subsection, the smallest neighboring boundary that contains the outcome),
full text for both 2023 and 2024, confirmed this session:

2023 (p.125–126, within the schedule's own voting-results table):

> "SHAREHOLDER ENGAGEMENT AND VOTING / Shareholder voting results / [table: Ordinary resolution on
> non-binding advisory vote on remuneration policy — 99.78% (Nov 2022) / 93.09% (Nov 2021); Ordinary
> resolution on non-binding advisory vote on implementation report — 99.78% (Nov 2022) / 99.20% (Nov
> 2021); ...] / The remuneration policy and implementation report were presented for shareholder
> voting at the AGM held on 10 November 2022. 99% of our shareholders endorsed the policy, and the
> implementation report received an in favour vote of 99%."

2024 (p.120–121):

> "Shareholder engagement and voting / Shareholder voting results / The remuneration policy and
> implementation report were presented for shareholder voting at the AGM held on 9 November 2023.
> 99.67% of our shareholders endorsed the policy, and the implementation report received an
> in-favour vote of 50.26%. This latter vote prompted a constructive engagement with the Sanlam
> Group who had voted against the implementation report for reasons that were shared with us."

**Qualitative comparison.** Unit A's 2023 and 2024 texts are indistinguishable (both are the same
41-word template with only the AGM year differing) — this is what exp. 5 already established and
this session re-confirms directly against the actual 2024 page text. Unit B's two years are visibly,
substantively different: 2023 presents a four-row resolution table with historical two-year
percentage comparisons and a routine "99% endorsed" narrative; 2024 drops the table entirely in
favor of a single narrative sentence carrying the 50.26% figure and the explicit "constructive
engagement with the Sanlam Group" language — a genuine change not only in *content* (the numbers)
but in *presentation format* (table → prose), itself a signal a future structural-change detector
should be able to register independently of wording similarity.

**Quantitative check (unigram word-overlap Jaccard, computed this session, not previously reported
in exp. 5).** Unit A, 2023→2024: 0.926 (reused from exp. 5's own computation, re-confirmed structurally
identical this session). Unit B, 2023→2024: **0.634** — a materially lower score, driven by the loss
of the resolution-table row labels and numbers in 2024 and the appearance of the new
Sanlam-engagement sentence, neither of which unit A's boundary could ever see.

**Conclusion.** Unit B would have caught the signal unit A missed, both qualitatively (a human
reading B immediately sees the 50.26%/Sanlam fact; a human reading A sees nothing unusual) and, on
this lightweight quantitative check, in the expected direction (B's similarity score drops
meaningfully more than A's, which does not drop at all). This confirms experiment 5's finding was not
an artifact of that experiment's specific metric set — a different, independently-computed check
(simple Jaccard on a differently-scoped text span) reproduces the same qualitative conclusion. The
smallest boundary that captures the substantive disclosure reliably is the neighbor subsection alone
("Shareholder engagement and voting"), not the entire `remuneration_chair_background_statement` unit
and not the entire remuneration schedule — consistent with the brief's instruction not to merge more
broadly than the evidence requires.

## 9. Numeric-rich unit analysis

Three numeric-rich units were assessed: `audit_risk_committee` (attendance/meeting-count numbers
embedded in otherwise-prose composition tables), `ned_remuneration_policy_table` (a genuinely
table-native fee schedule), and `total_remuneration_outcomes` (a fully table-native remuneration
schedule).

- **`audit_risk_committee`**: ordinary lexical metrics remain useful here (exp. 5's own finding,
  reused) *because* the unit is majority prose (role description, key-matters bullets) with a
  numeric table embedded inside it, not a numeric table with a prose caption. Lexical continuity
  (the role/key-matters framing) and quantitative outcome change (membership/attendance churn) are
  genuinely separable and both worth reporting — this is the model case for
  `LEXICAL_WITH_NUMERIC_CONTEXT` (B).
- **`ned_remuneration_policy_table`**: the reverse balance — majority table, minority prose, and the
  prose half is nearly invariant (Section 7). Ordinary lexical metrics on the prose half would report
  near-ceiling similarity every year, correctly but with almost no analytical value, because the real
  year-over-year fact (each role's fee amount and proposed increase percentage) lives entirely in the
  table. `STRUCTURED_COMPARISON_PREFERRED` (C).
- **`total_remuneration_outcomes`**: wholly table-native; there is effectively no prose to run a
  lexical metric against. What changed is which named individuals appear in which rows and what
  their per-category figures are (Section 4.10's Banderker STI example, the CEO-turnover row). This
  is not a case where lexical metrics would give a wrong answer — there is close to no text for them
  to operate on at all. `STRUCTURED_COMPARISON_PREFERRED` (C), and the strongest case in the sample
  for dropping lexical comparison as a *primary* method (it may still run as a supplementary check on
  the small amount of table framing text, but it should not be reported as an evaluative output on
  its own).

**When should both be retained?** `audit_risk_committee` and `social_ethics_committee` are the two
cases in this sample where both lexical and structured/numeric comparison should be retained
side-by-side, precisely because both units mix a genuine prose component with a genuine numeric
component in comparable proportion. This experiment did not find, and does not assert, that
"numeric-rich" and "lexical-comparable" are mutually exclusive properties — they co-occur on
committee-card units and diverge sharply on pure fee/remuneration tables. Per the task's explicit
instruction, no judgment is offered here on whether any of the observed remuneration changes (the
STI jump, the fee increases, the CEO transition's compensation profile) were favorable or
unfavorable to the company or its shareholders — only that they are real, structured, and
independently verifiable facts distinct from the surrounding prose's wording stability.

## 10. Eligibility matrix

| Unit | Unit type | Eligibility | Boilerplate | Numeric dependence | Cross-unit dependence | Decision method |
|---|---|---|---|---|---|---|
| audit_risk_committee | MIXED_NARRATIVE_AND_RESULTS | B (LEXICAL_WITH_NUMERIC_CONTEXT) | MEDIUM | MEDIUM | none | SEMANTIC_REVIEW_REQUIRED |
| social_ethics_committee | MIXED_NARRATIVE_AND_RESULTS | B (LEXICAL_WITH_NUMERIC_CONTEXT) | MEDIUM | MEDIUM | none | SEMANTIC_REVIEW_REQUIRED |
| remuneration_chair_background_statement | SUBSTANTIVE_NARRATIVE (+ embedded NUMERIC_RESULTS) | A (LEXICAL_DIRECT), with the voting subsection also serving as unit B's host (Section 8) | LOW | LOW–MEDIUM (one embedded table) | receives content from advisory_vote_on_implementation_report | SEMANTIC_REVIEW_REQUIRED |
| remuneration_processes | SUBSTANTIVE_NARRATIVE (policy, invariant) | E (PRESENCE_STATUS_ONLY) | HIGH | none | none | DETERMINISTIC_SUFFICIENT (word count + near-100% year-over-year token overlap) |
| ned_remuneration_policy_table | SUBSTANTIVE_STRUCTURED | C (STRUCTURED_COMPARISON_PREFERRED) | HIGH (prose half) | HIGH (table half) | none | STRUCTURAL_CONTEXT_REQUIRED (table-vs-prose ratio) |
| advisory_vote_on_implementation_report | PROCEDURAL_BOILERPLATE / CROSS_UNIT_DEPENDENT | D (MERGE_WITH_PARENT_OR_NEIGHBOR) | HIGH | none (year token only) | confirmed — content in remuneration_chair_background_statement | SEMANTIC_REVIEW_REQUIRED (the dependency itself was not deterministically detectable; it required reading the neighbor) |
| approval_by_board | APPROVAL_OR_SIGNOFF | E (PRESENCE_STATUS_ONLY) | HIGH | date only | none | DETERMINISTIC_SUFFICIENT (heading pattern "Approval", extreme brevity, one date token) |
| company_secretary | SUBSTANTIVE_NARRATIVE | A (LEXICAL_DIRECT) | HIGH (template) but slot-bearing | none | none | SEMANTIC_REVIEW_REQUIRED (a deterministic signal would need to know the template's *slots* carry the signal, which is not obvious from word count or heading alone) |
| statement_regarding_compliance | PROCEDURAL_BOILERPLATE / TOO_THIN_FOR_LEXICAL | E (PRESENCE_STATUS_ONLY) | HIGH (highest in sample) | none | not confirmed | DETERMINISTIC_SUFFICIENT (word count + near-zero year-over-year token change) |
| total_remuneration_outcomes | NUMERIC_RESULTS | C (STRUCTURED_COMPARISON_PREFERRED) | N/A (table) | HIGH | shares framing sentence with implementation_report parent | STRUCTURAL_CONTEXT_REQUIRED (table-block detection) |
| implementation_report | PROCEDURAL_BOILERPLATE (own prose) / container of MIXED_NARRATIVE_AND_RESULTS | split: E for parent's own sentence, C for children (Section 4.11) | HIGH (parent prose) | HIGH (delegated to children) | confirmed — real content lives in children, not parent prose | STRUCTURAL_CONTEXT_REQUIRED (parent/child structural awareness) |

## 11. Deterministic vs. semantic eligibility

Of the 11 units, **4 (36%) are classifiable as `DETERMINISTIC_SUFFICIENT`**:
`remuneration_processes` and `statement_regarding_compliance` (both: word count under ~100, and
year-over-year token overlap near 1.0 across all four transitions — a threshold-free "this unit is
essentially flat" signal any simple text-diff would surface without semantic reasoning), and
`approval_by_board` (heading contains "Approval," unit is under 15 words, content reduces to one
recognizable date pattern). A fourth borderline case, `ned_remuneration_policy_table`'s structural
routing (table vs. prose), is deterministically detectable via block/bbox table-shape signals (row/
column repetition, numeric-cell density) per the extraction-representation bake-off's own methodology
— no LLM judgment is needed to notice "this block is a table."

**5 (45%) require `SEMANTIC_REVIEW_REQUIRED`**: `audit_risk_committee`, `social_ethics_committee`,
`remuneration_chair_background_statement`, `advisory_vote_on_implementation_report`, and
`company_secretary`. In each case the deterministic signals (word count, heading pattern, template
overlap) either under- or over-state the unit's real eligibility: `company_secretary` looks exactly
like `statement_regarding_compliance` on every deterministic axis (short, high template overlap) but
is eligible for direct lexical comparison because its template's slots carry the signal — telling
these two apart requires reading what the slots actually contain, not just measuring how much of the
surrounding text is fixed. `advisory_vote_on_implementation_report`'s cross-unit dependence was
likewise not detectable from any signal internal to the unit itself; it required reading a neighboring
unit and recognizing that its content answered the first unit's heading's implicit question.

**2 (18%) require `STRUCTURAL_CONTEXT_REQUIRED`**: `total_remuneration_outcomes` and
`implementation_report`. Both need awareness of the document's own structural hierarchy (which
blocks are tables, which unit is a parent of which children) rather than either a simple deterministic
text signal or a semantic content judgment — the eligibility decision here is really a *layout and
hierarchy* question, not a wording question.

This roughly tracks experiment 4's own finding (76%/69% of its full 34/42-unit inventory needed no
semantic reasoning for *alignment*) but at a notably lower deterministic share for *eligibility*
specifically (36% here vs. ~70%+ there) — consistent with this experiment's central claim that
alignment (does this year's unit correspond to last year's unit) and eligibility (is this unit's own
text worth comparing) are different judgments, with eligibility requiring more semantic and structural
reasoning than alignment did.

## 12. Data model implications

**Yes, the distinction between a structural semantic unit and an analytical comparison unit is
justified by this sample — but the relationship needed is thinner than a full second ontology.**
Concrete evidence for "yes": `advisory_vote_on_implementation_report` is one structural unit whose
analytical content maps to zero-width (it contributes nothing on its own) plus a foreign structural
unit's subsection; `implementation_report` is one structural unit whose analytical content maps
almost entirely to its own children, not itself. Neither relationship (many analytical facts hiding
in a sibling; almost no analytical content in a parent whose children carry it all) is representable
if "structural unit" and "analytical unit" are treated as the same row.

Minimum proposed shape (not implemented, evaluated only against the 11 cases observed here — this
extends, does not replace, experiment 4's own `semantic_unit` design):

```
structural_unit { id, parent_structural_unit_id, source_heading, source_boundary, schedule_id, year }

analytical_unit { id, normalized_label, analytical_type (per Section 10's compact list),
                   lexical_eligibility (A–G per this experiment's taxonomy),
                   source_unit_ids[]  -- one, several adjacent, or a named sub-span of one --
                   scope_note (free text, e.g. "voting-results subsection only, not full parent unit") }
```

Tested against the sample: `audit_risk_committee` maps `analytical_unit` 1:1 to `structural_unit`
(the simple, common case — most of this sample's units are this shape). The advisory-vote/
shareholder-voting case maps one `analytical_unit` to `source_unit_ids = [remuneration_chair_background_statement]`
with `scope_note = "Shareholder engagement and voting subsection only"` — i.e. a *part* of one
structural unit, not the whole thing, and a part that does not even belong to the structural unit
whose heading originally raised the question (`advisory_vote_on_implementation_report` itself would
then map to no independent `analytical_unit` at all, or to a `PRESENCE_STATUS_ONLY` stub that simply
records "vote occurred, see [analytical_unit for voting]"). `implementation_report` maps its own
`analytical_unit` (type `PRESENCE_STATUS_ONLY`, one sentence) separately from four child
`analytical_unit`s, each `source_unit_ids = [that one child structural_unit]`. No case in this sample
required an `analytical_unit` to span more than two adjacent structural units, and no case required
spanning a schedule boundary (unlike experiment 4's ERM-framework `MOVED_CROSS_SCHEDULE` case) —
this experiment's evidence supports a same-schedule, adjacent-or-parent/child scope for the
relationship, not an unrestricted many-to-many one.

## 13. Pipeline implications

Proposed extended flow, evaluated stage by stage against this experiment's own evidence and the
four prior experiments':

1. **PDF → blocks/spans** — evidence-supported (representation bake-off; longitudinal stability
   experiment; re-confirmed incidentally here on every page read, no MULTIMODAL_REQUIRED case
   encountered).
2. **Schedule localization** — evidence-supported (schedule-localization experiment; longitudinal
   stability experiment; this experiment's own super-range re-verification in Section 3 confirms the
   ranges still hold for 2020–2024).
3. **Structural semantic units** — evidence-supported (experiment 4's 42-unit inventory, reused
   unchanged here).
4. **Cross-year structural alignment** — evidence-supported (experiment 4 Sections 7–10).
5. **Analytical-unit eligibility** — **evidence-supported by this experiment**, newly. This is the
   stage this experiment adds: 11 units classified, none forced into a single bucket, with an
   auditable per-unit rationale (Section 4) and a compact eligibility taxonomy (Section 10) that did
   not need extension beyond the brief's seven letters.
6. **Analytical boundary adjustment if needed** — evidence-supported for one case
   (`advisory_vote_on_implementation_report` → merge with a specific neighbor subsection, Section 8),
   demonstrated with actual reconstructed text and a quantitative check, not merely proposed. Not yet
   demonstrated as a general, repeatable procedure beyond this one case — a second boundary-adjustment
   case (ideally a MERGE candidate from a different schedule or company) would be needed before calling
   this stage's *mechanics* validated rather than its *concept*.
7. **Source reconstruction** — evidence-supported (representation bake-off; longitudinal experiment;
   experiment 5's Section 4.3 audit-committee block-reorder fix; no new reconstruction hazard found in
   this experiment's own extraction, which used plain `get_text()` throughout with zero MINOR_CORRECTION_NEEDED
   or worse cases, a cleaner result than experiment 5's own one 2023-page hazard — plausibly because
   this experiment's pages were mostly prose/table-simple rather than the two-column sidebar layout
   experiment 5 flagged).
8. **Lexical and/or structured numeric comparison** — **experimental / partially evidence-supported.**
   Lexical metrics themselves were validated in depth on 3 units by experiment 5 and are not re-litigated
   here. Structured numeric comparison was *identified as necessary* (Sections 4.5, 4.10, 9) but no
   structured-comparison method (a schema for comparing a fee table row-by-row across years, for
   instance) was designed or tested in this experiment — this remains the least evidence-supported
   stage in the extended pipeline and is this experiment's clearest "needs its own pilot" recommendation.
9. **Human-readable diff** — not evaluated in this experiment; out of scope per the brief (the task
   is eligibility, not diff presentation).

## 14. Recommendation

**(A) ADOPT ANALYTICAL-UNIT ELIGIBILITY GATE AND EXPAND METRICS.**

The evidence across 11 units, spanning all ten of the brief's required analytical profiles, is
consistent enough — 2 clean `LEXICAL_DIRECT` cases, 2 `LEXICAL_WITH_NUMERIC_CONTEXT` cases, 3
`STRUCTURED_COMPARISON_PREFERRED` cases (including one split-by-level parent/child case), 4
`PRESENCE_STATUS_ONLY` cases, 0 outright `EXCLUDE_FROM_COMPARISON`, 0 `UNCERTAIN` — to justify adding
the eligibility gate as a real pipeline stage rather than treating structural validity as
sufficient. No unit was forced into `LEXICAL_DIRECT`, and no unit came back `UNCERTAIN`; every one of
the 11 could be resolved to a specific, evidence-backed treatment with the extraction and reading
done in this session, which is itself informative: the seven-category taxonomy given in the brief was
sufficient without extension for this sample, and a small deterministic subset (4 of 11, Section 11)
means the gate does not require an LLM call for every unit in a future implementation.

**Which ACT units should enter the next expanded lexical pilot:** `company_secretary` (new — this
experiment's clearest new positive finding, and a good complement to exp. 5's `remuneration_chair_background_statement`
as a second, shorter `LEXICAL_DIRECT` case) and `social_ethics_committee` (new — same class as the
already-piloted `audit_risk_committee`, worth confirming the `LEXICAL_WITH_NUMERIC_CONTEXT` pattern
generalizes to a second committee card rather than being specific to the Audit and Risk Committee).

**Which should use structured/numeric comparison instead:** `ned_remuneration_policy_table` and
`total_remuneration_outcomes` (and, by the same logic, experiment 4's other unsampled
`implementation_report` children — `sti_lti_performance_outcomes`, `individual_remuneration_outcomes`,
`ned_fees_and_payments_table` — which this experiment did not extract but which share
`total_remuneration_outcomes`'s table-native structure closely enough to expect the same treatment).
No structured-comparison method was designed here; this is the next research gap, not a proceed-as-is
item.

**Which should be excluded (from lexical comparison specifically, not from the corpus):**
`advisory_vote_on_implementation_report` in its current narrow boundary (recommend re-scoping into
`remuneration_chair_background_statement`'s voting subsection per Section 8 instead of a standalone
comparison), `statement_regarding_compliance`, `approval_by_board`, and `remuneration_processes` —
all four to `PRESENCE_STATUS_ONLY` or date/fact tracking rather than lexical metrics, per Sections 5
and 7's finding that their flatness is either uninformative-by-design or already fully explained.

**Should BEL be added next?** Not yet, for the same reason experiment 5 gave for staying ACT-only:
this experiment's own new findings — the `company_secretary` positive case, the parent/child
delegation pattern in `implementation_report`, the "thin-but-genuinely-flat vs. thin-but-cross-unit-
dependent" distinction — have not yet been re-tested on a second company with a different report
template and different unit-boundary conventions (per the longitudinal stability experiment, BEL's
remuneration schedule has a materially different stability history, including a full
presence→absence→presence externalization round-trip that ACT never exhibits). A second ACT-only
round applying the structured-numeric-comparison method this experiment identified as the actual next
research gap is the more tightly-scoped next step; BEL remains a reasonable second-company pilot once
that method exists, not before.

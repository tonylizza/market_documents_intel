# Track 7D.5a: Corpus-Wide Remaining-Schedule Feasibility Screen

## 0. Scope note

This is a **reconnaissance-only** track. No schedule was implemented. No
production file was changed: `schedule_localization.py`, `schedule_config.py`,
`semantic_unit_config.py`, `analytical_eligibility.py`,
`coverage_registry.py`, and `cutover_config.py` are all untouched by this
track. The only artifact produced is this document and a temporary,
non-production research script, `scripts/research_7d5a_heading_inventory.py`,
retained under `scripts/` per this track's own scope note allowing research
scripts to be kept under an appropriate path.

7D.5 (docs/7d5-corpus-wide-material-risks-expansion.md) established that
schedule localization succeeding is not sufficient evidence that a schedule
is worth implementing -- content shape and semantic-unit stability matter as
much as heading matching. This track applies that same discipline to the
seven still-unevaluated normalized schedules: CEO_REVIEW, CHAIR_REVIEW,
STRATEGY, OUTLOOK, LEGAL_REGULATORY, MATERIAL_MATTERS, OPERATING_ENVIRONMENT.

## 1. Corpus inventory

Same six issuers, same report-year counts as every prior 7D track:

| ticker | report years |
|---|---|
| ACT | 9 (2016-2024) |
| BEL | 7 (2016-2022) |
| KP2 | 6 (2020-2025) |
| SBP | 3 (2023-2025) |
| SDL | 2 (2024-2025) |
| SUR | 3 (2023-2025) |

Total: 30 report years, all seven candidate schedules screened against every
one.

## 2. Methodology

A read-only research script
(`scripts/research_7d5a_heading_inventory.py`) was written that:

1. For each report, loads the current successful canonical-extraction run
   (Track 7C.1a) and runs it through the exact same
   `source_adapter.classify_source_pages` / `source_adapter.build_heading_blocks`
   pipeline `schedule_localization.py` itself uses -- no separate,
   divergent heuristic.
2. Falls back to legacy `TextBlock` rows with `block_type ==
   HEADING_CANDIDATE` only when a report has no canonical extraction run,
   mirroring 7D.5's own stated method.
3. Matches every heading-candidate's text against seven broad,
   deliberately over-inclusive keyword families (one per candidate
   schedule) -- recall over precision, since every hit is reviewed by eye
   below, not auto-classified into a schedule.
4. Prints every hit with ticker, year, source (`canonical` vs
   `legacy_textblock`), page number, and full heading text.

**Real-corpus canonical-extraction coverage gap found incidentally**: only
ACT and BEL have a completed canonical-extraction run for every report year
in this corpus today. KP2, SBP, SDL, and SUR fall back to legacy `TextBlock`
for all their years. This does not block this screen (legacy `TextBlock`
heading candidates are a valid, if less structurally rich, signal, exactly
as 7D.5 used them), but any future implementation milestone touching those
four issuers should expect to run Track 7C.1a canonical extraction for them
first if font-size/structural evidence becomes load-bearing (as it did for
7D.1's/7D.4a's false-positive hardening).

The full raw hit list (930 heading-candidate hits across all seven
schedules) was inspected by eye; the classifications below are the product
of that inspection, not the raw keyword match itself.

## 3. Heading inventory

Full hit counts by schedule: CEO_REVIEW 135, CHAIR_REVIEW 130, STRATEGY 484,
OUTLOOK 65, LEGAL_REGULATORY 36, MATERIAL_MATTERS 90, OPERATING_ENVIRONMENT
32. Representative real headings per schedule (full inventory retained in
the research script's output, not reproduced verbatim here):

- **CEO_REVIEW**: ACT "GROUP CEO'S REPORT" (2016-2020) / "CEO'S REVIEW"
  (2021-2024); BEL/SDL "Joint report by the chairman and chief executive" /
  "CHAIRMAN AND CEO REPORT" (fused with chair, see Section 7); SUR "CEO's
  review" / "A message from our CEO"; SBP/KP2 no standalone heading found.
- **CHAIR_REVIEW**: ACT "CHAIRPERSON'S REPORT" / "CHAIRMAN'S REPORT" /
  "CHAIRMAN'S REVIEW"; SBP "CHAIRMAN'S LETTER TO SHAREHOLDERS" (all 3
  years); SUR "Chairman's review" / "Introduction from our Chairman" /
  "Message from the chairman"; BEL/SDL fused with CEO; KP2 none found.
- **STRATEGY**: ACT "STRATEGY" as a real ~15-page bounded chapter only in
  2016 (pages 31-46, "continued" markers); from 2017 onward, "strategy"-
  family text becomes a pervasive cross-reference tag ("Link to strategic
  levers", "Responding strategically") repeated on nearly every
  material-matter/risk page; BEL "Strategic overview and risk management"
  (already documented in 7D.5 as taxonomy-unstable); KP2 "REVIEW OF
  OPERATIONS AND STRATEGIC REPORT" as a running page header/banner on
  nearly every page of the report, not one heading; SUR "strategy"
  mentioned diffusely across dozens of pages with no single bounded
  chapter.
- **OUTLOOK**: ACT "Outlook" recurs 3-12 times per year, almost always as a
  short closing subsection of each divisional/segment review (co-located
  with FINANCIAL_PERFORMANCE's own page ranges) or of the CEO/Chair review
  itself, never as its own standalone chapter; BEL only 2016-2017; KP2/SBP/
  SDL zero hits.
- **LEGAL_REGULATORY**: no bounded chapter anywhere; hits are almost all
  "Government and regulators" (a stakeholder-group subsection of the
  broader stakeholder-engagement narrative, not a legal/regulatory
  disclosure) or a single named "Regulatory risk" item inside BEL's already
  taxonomy-unstable risk register (7D.5 Section 5).
- **MATERIAL_MATTERS**: ACT's "Material matters / Why material? / Risks /
  Opportunities / Stakeholders / Response" matrix (2016-2024) is **the same
  underlying table already documented as ACT's MATERIAL_RISKS
  materiality matrix in 7D.5 Section 4** -- MATERIAL_MATTERS and
  MATERIAL_RISKS are not independent content for ACT, they are two normalized
  labels pointing at one structured table. BEL has a boilerplate
  methodology sentence every year ("Bell determines its material matters
  through the following process") plus an inconsistent "MATERIAL MATTERS"
  heading only in 2021-2022. KP2's only "Materiality" hits are financial-
  statement audit-materiality thresholds (an accounting term, not an ESG
  material-matters concept) -- a homonym false positive, not evidence of
  the schedule.
- **OPERATING_ENVIRONMENT**: exists only in ACT (2018-2024) as "External
  environment" / "Link to macro trends", embedded inside the same
  material-matters/risk narrative pages as OPERATING_ENVIRONMENT candidate
  content, never a standalone chapter. Zero hits for every other issuer.

## 4. Navigational false-positive review

Per 7D.5's own precedent (its "Risks and opportunities" navigational-label
finding), each candidate family was checked for non-structural occurrences:

- **STRATEGY** is the worst offender: KP2's "REVIEW OF OPERATIONS AND
  STRATEGIC REPORT" is a **repeated running page header**, appearing on
  nearly every page of the report (confirmed by page-number density in the
  raw hit list) -- not a heading at all in the structural sense, an
  artifact of the page-banner design. ACT's "Link to strategic levers" /
  "Related strategic levers" tags (2020-2024) are recurring **cross-
  reference labels** inside material-matter/risk cards, not section
  headings, even though they are classified as HEADING_CANDIDATE blocks by
  font size.
- **MATERIAL_MATTERS**: KP2's "Materiality" hits are audit/accounting
  materiality thresholds in the financial-statements notes -- a homonym,
  not the ESG-materiality concept the schedule is meant to capture.
- **OUTLOOK**: ACT's dense repetition (12 hits in 2020 alone) is a
  **recurring divisional-subsection label**, not a single standalone
  chapter -- the same "generic short label repeated across many
  substructures" pattern 7D.5 flagged for the bare "Risks and
  opportunities" phrase, just distributed across the report rather than
  concentrated on one navigational page.
- **CEO_REVIEW / CHAIR_REVIEW**: page-3 table-of-contents lines (e.g. "GROUP
  CEO'S REPORT 47", "Group CEO's report 19 - 22") were found and are
  correctly excluded from any real vocabulary decision -- they are TOC
  entries, not the chapter heading itself, though the real chapter heading
  is also present later at its own page for every ACT year.

These are recorded as a caution against configuring STRATEGY's or OUTLOOK's
generic phrases too broadly in any future milestone, not as evidence that
CEO_REVIEW/CHAIR_REVIEW's own vocabulary is unsafe (their real chapter
headings are much more specific and did not exhibit this problem).

## 5. Schedule-existence matrix

| schedule | ACT | BEL | KP2 | SBP | SDL | SUR |
|---|---|---|---|---|---|---|
| CEO_REVIEW | CLEAR_STANDALONE (9/9) | EMBEDDED_IN_OTHER_SCHEDULE (fused w/ chair, 7/7) | GENUINE_ABSENCE | GENUINE_ABSENCE | EMBEDDED_IN_OTHER_SCHEDULE (fused w/ chair, 2/2) | LIKELY_STANDALONE (3/3, wording varies) |
| CHAIR_REVIEW | CLEAR_STANDALONE (9/9) | EMBEDDED_IN_OTHER_SCHEDULE (fused w/ CEO, 7/7) | GENUINE_ABSENCE | CLEAR_STANDALONE (3/3) | EMBEDDED_IN_OTHER_SCHEDULE (fused w/ CEO, 2/2) | LIKELY_STANDALONE (3/3, wording varies) |
| STRATEGY | LIKELY_STANDALONE only 2016; SCATTERED_CONTENT 2017-2024 | EMBEDDED_IN_OTHER_SCHEDULE (inside risk chapter) | SCATTERED_CONTENT (running header) | INCONCLUSIVE (1 thin hit) | GENUINE_ABSENCE | SCATTERED_CONTENT |
| OUTLOOK | EMBEDDED_IN_OTHER_SCHEDULE (in CEO/Chair review + divisional reviews) | INCONCLUSIVE (2016-2017 only) | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE | INCONCLUSIVE (1 thin hit) |
| LEGAL_REGULATORY | GENUINE_ABSENCE (only stakeholder/risk mentions) | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE |
| MATERIAL_MATTERS | CLEAR_STANDALONE but == MATERIAL_RISKS table (2016-2024) | INCONCLUSIVE (2021-2022 only) | GENUINE_ABSENCE (homonym only) | GENUINE_ABSENCE | GENUINE_ABSENCE | LIKELY_STANDALONE (3/3) |
| OPERATING_ENVIRONMENT | EMBEDDED_IN_OTHER_SCHEDULE (inside material-matters/risk pages, 2018-2024) | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE | GENUINE_ABSENCE |

This is research classification only; nothing here is persisted to any
production model.

## 6. Content-shape screen

| schedule | ACT | BEL | SUR | SBP |
|---|---|---|---|---|
| CEO_REVIEW | LONG_FORM_NARRATIVE (~2-5 pages, real prose) | MIXED_NARRATIVE_AND_STRUCTURED (joint report, part narrative part director-bio table) | SHORT_COMMENTARY (1-2 pages) | n/a |
| CHAIR_REVIEW | LONG_FORM_NARRATIVE | (same joint report as CEO) | SHORT_COMMENTARY | SHORT_COMMENTARY (1-page letter) |
| STRATEGY | CARD_OR_MATRIX_LAYOUT/SCATTERED (2019+); LONG_FORM_NARRATIVE only 2016-2018 | MIXED_NARRATIVE_AND_STRUCTURED (same chapter as 7D.5's BEL risk register) | SCATTERED_ACROSS_REPORT | n/a |
| OUTLOOK | SHORT_COMMENTARY, but embedded (each hit is a 1-3 paragraph subsection, not its own chapter) | SHORT_COMMENTARY (2 years only) | n/a | n/a |
| LEGAL_REGULATORY | n/a (no content found) | n/a | n/a | n/a |
| MATERIAL_MATTERS | CARD_OR_MATRIX_LAYOUT (identical structure to 7D.5's ACT Material Risks matrix) | SHORT_COMMENTARY (boilerplate paragraph) + inconsistent heading | MIXED_NARRATIVE_AND_STRUCTURED | n/a |
| OPERATING_ENVIRONMENT | SHORT_COMMENTARY, embedded subsection of the material-matters/risk chapter | n/a | n/a | n/a |

Content shape was checked against actual canonical/legacy blocks under each
heading, not inferred from heading text alone, consistent with the
milestone's Section 6 instruction.

## 7. CEO_REVIEW / CHAIR_REVIEW special analysis

| ticker | classification | evidence |
|---|---|---|
| ACT | SEPARATE_CEO_AND_CHAIR | "GROUP CEO'S REPORT"/"CEO'S REVIEW" and "CHAIRPERSON'S REPORT"/"CHAIRMAN'S REVIEW" are distinct chapters, adjacent but separately headed, every year 2016-2024. |
| BEL | COMBINED_CEO_CHAIR | "Joint report by the chairman and chief executive" is one chapter, one heading, every year 2016-2022 -- never split. |
| SBP | CHAIR_ONLY | "CHAIRMAN'S LETTER TO SHAREHOLDERS" every year (3/3); no standalone CEO section found -- only an org-chart label "Executive Chairman/CEO" (the same person holds both roles at SBP, consistent with its family-holding-company structure already noted in 7D.3/7D.4). |
| SDL | COMBINED_CEO_CHAIR | "CHAIRMAN AND CEO REPORT" is one heading, both years (2/2) -- explicit two-name byline (Executive Chairman + Managing Director/CEO) under one shared chapter. |
| SUR | SEPARATE_CEO_AND_CHAIR | 2023: "CEO's review" (p68) and "Chairman's review" (p65) are distinct, adjacent chapters. 2024: "A message from our CEO" and "Introduction from our Chairman" likewise distinct. 2025: "CEO's review" (p11) and "Chairman's review" (p11, different page anchor) both present. Heading wording is not stable year to year (see Section 10), but the *separation* itself is. |
| KP2 | NO_CLEAR_SECTION | Zero CEO/Chairman/Chairperson heading-candidate hits in any of KP2's 6 years -- its lead narrative chapter is "Review of Operations and Strategic Report" instead, with no individually-titled CEO or Chair section found. Consistent with KP2's small-cap oil-and-gas report format already noted as structurally different in prior tracks. |

## 8. CEO/Chair normalization recommendation

**USE_FUNCTIONAL_MAPPING.** The real corpus splits cleanly into three
groups: issuers that always separate CEO and Chair content (ACT, SUR),
issuers that always fuse it into one joint chapter (BEL, SDL), and issuers
that only have one of the two roles as a standalone narrative section (SBP,
chair only) or neither (KP2). Forcing `KEEP_SEPARATE` would leave BEL/SDL
with no CEO_REVIEW or CHAIR_REVIEW content at all despite real, substantial
narrative existing (their joint report). Forcing `ADD_COMBINED_LEADERSHIP_
REVIEW` as a third schedule would leave ACT/SUR/SBP's real separation
unused. A functional mapping -- BEL's and SDL's joint chapter mapped to
*both* CEO_REVIEW and CHAIR_REVIEW as the same source span (the same
supporting-span mechanism `ScheduleInstanceSupportingSpan` already
generalizes for FINANCIAL_PERFORMANCE, see `models/schedule.py`'s own BEL
example) -- is the only option that uses all six issuers' real evidence
without forcing a heading that does not exist. This recommendation is not
implemented in this track.

## 9. Recurring semantic-unit inventory (not configured)

| schedule | ticker | candidate concept | years observed | content shape | boundary strategy (likely) | stable? |
|---|---|---|---|---|---|---|
| CEO_REVIEW | ACT | performance overview | 2016-2024 (opening paragraphs of every CEO review) | narrative | ANCHOR_SENTENCE | STABLE |
| CEO_REVIEW | ACT | strategic commentary ("strategy in action" / "responding strategically") | 2019-2024 | narrative, but wording shifts | NEXT_HEADING | MOSTLY_STABLE |
| CEO_REVIEW | ACT | outlook/closing remarks | most years (co-located "Outlook" heading immediately follows CEO review body) | narrative | NEXT_HEADING | MOSTLY_STABLE |
| CHAIR_REVIEW | ACT | board/governance commentary | 2016-2024 | narrative | ANCHOR_SENTENCE | STABLE |
| CHAIR_REVIEW | SBP | shareholder-facing performance letter | 2023-2025 | narrative (1-page letter) | whole-span (no internal subsection) | STABLE |
| CEO_REVIEW/CHAIR_REVIEW (joint) | BEL | joint narrative body | 2016-2022 | narrative | whole-span, same pattern as 7D.5's rejected joint-report handling | STABLE (chapter identity), no internal recurring unit found |
| OUTLOOK | ACT | divisional outlook subsection | most years, but always embedded | narrative | NEXT_HEADING | UNSTABLE as a standalone concept (moves between CEO review and FINANCIAL_PERFORMANCE divisional pages year to year) |
| STRATEGY | ACT | strategic pillars/levers | 2020-2024 only | mixed (card-shaped, not prose) | none plausible without a new card parser | UNSTABLE (chapter itself reorganizes; not present as a bounded chapter before 2019) |

No concept was found for LEGAL_REGULATORY, MATERIAL_MATTERS (beyond the
already-excluded materiality-matrix table), or OPERATING_ENVIRONMENT that
meets a "narrative, usable boundary" bar independent of an already-larger
structural blocker.

## 10. Structural-identity assessment

| schedule | classification | reasoning |
|---|---|---|
| CEO_REVIEW (ACT) | STABLE | Same analytical function every year; heading wording changes once (2020->2021) but chapter identity, position, and content shape do not. |
| CHAIR_REVIEW (ACT) | STABLE | Same as above. |
| CHAIR_REVIEW (SBP) | STABLE | Identical heading, identical position, all 3 years. |
| CEO_REVIEW/CHAIR_REVIEW (SUR) | MOSTLY_STABLE | Separation is stable; heading wording is not ("CEO's review" vs "A message from our CEO"; "Chairman's review" vs "Introduction from our Chairman" vs "Message from the chairman") -- a vocabulary-breadth problem, not a structural-identity one, similar in kind (though smaller in degree) to CORPORATE_GOVERNANCE's/REMUNERATION's own multi-phrasing handling in 7D.3/7D.4. |
| CEO_REVIEW/CHAIR_REVIEW (BEL, SDL) | STABLE (as one joint chapter) | Never splits, never renamed materially. |
| STRATEGY (ACT) | UNSTABLE | Real bounded chapter only 2016-2018; becomes a scattered cross-reference tag from 2019 onward. Chapter existence itself changes, not just wording. |
| STRATEGY (BEL) | UNSTABLE | Already documented in 7D.5 (its own "Strategic overview and risk management" chapter is the same chapter as BEL's taxonomy-unstable risk register). |
| OUTLOOK (ACT) | UNSTABLE | Moves between the CEO review, the Chair review, and individual FINANCIAL_PERFORMANCE divisional pages depending on year -- never its own fixed location. |
| MATERIAL_MATTERS (ACT) | INCONCLUSIVE as an independent schedule | Structurally identical to MATERIAL_RISKS's own matrix (7D.5); cannot be assessed as a separate concept without first resolving that overlap. |

## 11. Extraction-compatibility screen

| schedule | classification | reasoning |
|---|---|---|
| CEO_REVIEW | LIKELY_FITS_WITH_CONFIG | Long-form narrative, bounded chapter, `NEXT_HEADING`/`ANCHOR_SENTENCE` both plausible -- same shape as FINANCIAL_PERFORMANCE/CORPORATE_GOVERNANCE/REMUNERATION's own successful units. |
| CHAIR_REVIEW | LIKELY_FITS_WITH_CONFIG | Same as above. |
| CEO_REVIEW/CHAIR_REVIEW (joint, BEL/SDL) | NEEDS_SMALL_GENERIC_HARDENING | Not a new parser -- just the functional-mapping/supporting-span pattern (Section 8) applied to two schedules from one span, which the schema already supports structurally. |
| STRATEGY | NEEDS_NEW_STRUCTURED_PARSER (post-2019 content) / LIKELY_FITS_WITH_CONFIG (2016-2018 only, too thin alone) | Current card/cross-reference-tag content is not narrative-extractable; the one stable narrative window is too short to carry a schedule alone. |
| OUTLOOK | NOT_SUITABLE as a standalone schedule | Its own content has no fixed location to anchor a schedule boundary at all (Section 10). |
| LEGAL_REGULATORY | NOT_SUITABLE | No content exists to extract. |
| MATERIAL_MATTERS | NEEDS_NEW_STRUCTURED_PARSER | Same card/matrix blocker 7D.5 already found for MATERIAL_RISKS -- literally the same table for ACT. |
| OPERATING_ENVIRONMENT | NEEDS_SMALL_GENERIC_HARDENING at best | Content exists only embedded within another schedule's page range; would need a sub-schedule boundary concept the architecture does not currently have. |

## 12. Cross-schedule overlap review

| ticker | years | concept | observed source locations | likely canonical schedule | ambiguity |
|---|---|---|---|---|---|
| ACT | 2016-2024 | Outlook | CEO review closing paragraphs, Chair review closing paragraphs, individual FINANCIAL_PERFORMANCE divisional pages | none cleanly -- genuinely distributed | HIGH -- confirms the milestone's own Section 12 suspicion that Outlook is a subsection, not standalone |
| ACT | 2018-2024 | Operating environment / external environment | Embedded inside the same page range as ACT's material-matters/risk chapter | MATERIAL_MATTERS-adjacent, not its own schedule | HIGH |
| ACT | 2016-2024 | Material matters vs. material risks | Same table, same page range, two normalized labels | Ambiguous by design until a future milestone picks one | HIGH -- a genuinely new finding this track surfaces, not previously documented |
| ACT | 2019-2024 | Strategy vs. leadership commentary | "Strategy in action" appears inside the CEO's review chapter itself (2019 example: p30-38) | CEO_REVIEW-embedded, not a separate STRATEGY chapter | MEDIUM |
| BEL | 2016-2022 | CEO Review vs. Chair Review | One joint chapter | Both (Section 8) | Resolved by functional mapping, not ambiguous once addressed |

No cross-schedule overlap was resolved in this track, per its own scope
boundary.

## 13. Analytical-value screen

| schedule | value | reasoning |
|---|---|---|
| CEO_REVIEW | HIGH | Substantive year-over-year narrative from the person most accountable for performance; wording changes are informative (tone, emphasis, what gets foregrounded); recurs for every issuer that publishes one. |
| CHAIR_REVIEW | HIGH | Same reasoning, board-level framing rather than operational -- a genuinely different analytical lens than CEO_REVIEW, not a duplicate. |
| STRATEGY | MEDIUM | When present as a bounded chapter (ACT 2016-2018), high potential value; but real-corpus recurrence is too thin and unstable across the corpus to realize that value today. |
| OUTLOOK | MEDIUM | Forward-looking commentary is inherently valuable for comparison, but its embedded, moving location undermines being able to compare it as its own unit. |
| LEGAL_REGULATORY | LOW | No real content found in this corpus at all -- value cannot be assessed above a hypothetical. |
| MATERIAL_MATTERS | MEDIUM-HIGH (content) but currently unrealizable | The underlying materiality assessment is genuinely valuable, but it is the same content as MATERIAL_RISKS, so its value is not additive without resolving that overlap first. |
| OPERATING_ENVIRONMENT | LOW-MEDIUM | Real content exists only for one issuer, always embedded -- too thin corpus-wide to expect much year-over-year comparability value yet. |

## 14. Implementation-difficulty screen

| schedule | difficulty | reasoning |
|---|---|---|
| CEO_REVIEW | LOW | Stable heading per issuer (one wording change for ACT, mirroring already-handled multi-phrasing in 7D.3/7D.4), narrative content, `NEXT_HEADING`/`ANCHOR_SENTENCE` fit directly. |
| CHAIR_REVIEW | LOW | Same. |
| CEO/Chair joint mapping (BEL/SDL) | LOW-MEDIUM | Needs the functional-mapping design decision (Section 8) applied in config, not new algorithm code. |
| STRATEGY | HIGH | Real content is either absent, scattered, or card-shaped depending on issuer and year; the one stable narrative window (ACT 2016-2018) is too short to justify a schedule alone. |
| OUTLOOK | HIGH | No fixed schedule boundary exists to configure at all. |
| LEGAL_REGULATORY | VERY_HIGH (not evaluable) | No content exists in this corpus; difficulty cannot even be meaningfully assessed. |
| MATERIAL_MATTERS | VERY_HIGH | Same structured-table blocker 7D.5 already found for MATERIAL_RISKS, plus a genuinely new overlap-resolution problem this track surfaced. |
| OPERATING_ENVIRONMENT | HIGH | No independent schedule boundary exists; embedded-subsection extraction is not a capability the architecture has today. |

## 15. Master opportunity matrix

| schedule | companies w/ clear/likely schedule | years w/ evidence | dominant content shape | recurring-unit potential | structural stability | architecture fit | analytical value | implementation difficulty | major blocker | recommendation |
|---|---|---|---|---|---|---|---|---|---|---|
| CEO_REVIEW | ACT, SUR (standalone); BEL, SDL (joint) | 25/30 | LONG_FORM_NARRATIVE / SHORT_COMMENTARY | 2-3 concepts (performance overview, strategic commentary, outlook) | STABLE (ACT, BEL, SDL); MOSTLY_STABLE (SUR) | LIKELY_FITS_WITH_CONFIG | HIGH | LOW | CEO/Chair functional mapping needed for BEL/SDL | **IMPLEMENT_NEXT** |
| CHAIR_REVIEW | ACT, SBP, SUR (standalone); BEL, SDL (joint) | 25/30 | LONG_FORM_NARRATIVE / SHORT_COMMENTARY | 1-2 concepts (board/governance commentary, shareholder letter) | STABLE (ACT, SBP, BEL, SDL); MOSTLY_STABLE (SUR) | LIKELY_FITS_WITH_CONFIG | HIGH | LOW | Same functional-mapping need | **IMPLEMENT_NEXT** |
| STRATEGY | ACT (2016-2018 only) | 3/30 stable + scattered elsewhere | SCATTERED_CONTENT / CARD_OR_MATRIX_LAYOUT | 0 stable | UNSTABLE | NEEDS_NEW_STRUCTURED_PARSER | MEDIUM | HIGH | Chapter existence itself is unstable; running-header false positive (KP2) | DEFER |
| OUTLOOK | ACT (embedded only) | thin, always embedded | SHORT_COMMENTARY, no fixed location | 0 stable | UNSTABLE | NOT_SUITABLE | MEDIUM | HIGH | No fixed schedule boundary | DEFER |
| LEGAL_REGULATORY | none | 0 | n/a | 0 | n/a | NOT_SUITABLE | LOW | VERY_HIGH (not evaluable) | Content does not exist in this corpus | DO_NOT_PURSUE_WITH_CURRENT_ARCHITECTURE |
| MATERIAL_MATTERS | ACT (== MATERIAL_RISKS table); BEL, SUR (inconsistent) | 16/30-ish, overlapping | CARD_OR_MATRIX_LAYOUT | 0 stable independent of MATERIAL_RISKS | INCONCLUSIVE (overlap unresolved) | NEEDS_NEW_STRUCTURED_PARSER | MEDIUM-HIGH (unrealizable) | VERY_HIGH | Same table as MATERIAL_RISKS; unresolved schedule-identity overlap | DO_NOT_PURSUE_WITH_CURRENT_ARCHITECTURE |
| OPERATING_ENVIRONMENT | ACT only, embedded | 7/30 | SHORT_COMMENTARY, embedded | 0 stable | UNSTABLE | NEEDS_SMALL_GENERIC_HARDENING at best | LOW-MEDIUM | HIGH | No independent boundary; single-issuer evidence | DEFER |

## 16. Fast-path candidates

**CEO_REVIEW and CHAIR_REVIEW both meet the fast-path bar explicitly.**
Both exist in multiple issuers (ACT, SBP, SUR as standalone; BEL, SDL as one
fusable joint chapter), recur across nearly every available report year,
are primarily narrative (long-form or short commentary, never table/card/
graphic-dominated), have reasonably stable headings per issuer (the one
real instability, SUR's varying phrasing, is a vocabulary-breadth problem
of the same kind CORPORATE_GOVERNANCE/REMUNERATION already handle, not a
structural one), show 2-3 plausible recurring semantic concepts each
(performance overview, strategic/leadership commentary, board/governance
commentary), fit current `NEXT_HEADING`/`ANCHOR_SENTENCE` extraction
directly, and require no new structured/visual parser. The only real
complication -- BEL's and SDL's joint chapter -- is addressed by
functional mapping using a mechanism (`ScheduleInstanceSupportingSpan`)
the schema already has, not a new capability.

STRATEGY and OUTLOOK do **not** meet the fast-path bar: neither has a
stable schedule boundary corpus-wide (Section 10), and both would need
either a new structured/card parser (STRATEGY, post-2019 content) or an
embedded-subsection extraction capability the architecture does not have
today (OUTLOOK).

## 17. Stop rule

Not triggered -- CEO_REVIEW and CHAIR_REVIEW both meet the fast-path
criteria, so this track does not need to recommend proceeding straight to
release hardening with all remaining schedules deferred.

## 18. Release-readiness implication

**ADD_ONE_OR_TWO_MORE_SCHEDULES_FIRST.**

Supporting evidence: CEO_REVIEW and CHAIR_REVIEW are real, narrative,
recurring, structurally stable content that exists for every issuer in the
corpus in some form (either standalone or as one fusable joint chapter),
using extraction machinery this codebase has already proven works
(FINANCIAL_PERFORMANCE, CORPORATE_GOVERNANCE, REMUNERATION). Passing on
this evidence to go straight to release hardening would leave two
genuinely low-cost, high-value schedules on the table for no structural
reason -- unlike MATERIAL_RISKS (7D.5), STRATEGY, LEGAL_REGULATORY,
MATERIAL_MATTERS, and OPERATING_ENVIRONMENT, none of which show this
combination of low difficulty and high value.

## 19. Caveats

- This is a heading- and content-shape screen, not a full localization
  implementation -- actual heading vocabulary, boundary strategy choice,
  and semantic-unit configuration for CEO_REVIEW/CHAIR_REVIEW still need
  their own dedicated milestone (a 7D.6-style track), including the
  CEO/Chair functional-mapping design decision (Section 8) made concrete
  in code.
- The real navigational-false-positive risk documented for
  STRATEGY (Section 4) should be treated as a standing caution for any
  future work that touches strategy-adjacent vocabulary, even
  incidentally (e.g. if a future CEO_REVIEW extraction pass ever needs to
  bound "strategy in action" as an internal subsection).
- MATERIAL_MATTERS' overlap with MATERIAL_RISKS (Section 3, 12) is a new
  finding this track surfaced that 7D.5 did not know about when it reached
  its own zero-narrative-units verdict -- a future schedule-identity
  decision (are these one normalized schedule or two with a required
  supporting-span link?) should be made explicitly before either is
  revisited, rather than accidentally double-counting ACT's one real
  table as two schedules' evidence.
- KP2's absence of any CEO/Chair/Strategy/Outlook/Legal/Material-Matters/
  Operating-Environment standalone heading across all 6 years reflects a
  real, confirmed structural difference (its lead narrative is "Review of
  Operations and Strategic Report"), not an evidence gap -- consistent
  with KP2's small-cap, differently-structured report format already
  noted in prior tracks.
- Canonical-extraction coverage is incomplete for KP2/SBP/SDL/SUR (Section
  2) -- this did not block this screen, but any future milestone relying
  on font-size-based structural evidence (as 7D.1/7D.4a's false-positive
  hardening did) for those four issuers should run Track 7C.1a canonical
  extraction for them first.

## Final verdict

**ADD_ONE_OR_TWO_MORE_SCHEDULES_FIRST**

- **Best next schedule**: CEO_REVIEW
- **Second-best next schedule**: CHAIR_REVIEW (implemented together with
  CEO_REVIEW is likely more efficient than sequentially, given they share
  the BEL/SDL joint-chapter functional-mapping problem)
- **Schedules deferred**: STRATEGY, OUTLOOK, OPERATING_ENVIRONMENT
- **Schedules incompatible with current architecture**:
  LEGAL_REGULATORY (no real content found in this corpus),
  MATERIAL_MATTERS (same structured-table blocker as MATERIAL_RISKS, plus
  an unresolved schedule-identity overlap with it)

No schedule was implemented, no production configuration was changed, and
no database state was altered in this track.

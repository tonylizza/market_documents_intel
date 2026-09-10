# Milestone 7 — Human Validation Labeling Guide

This guide is for the reviewer(s) labeling `validation/human_validation_cases_blinded.csv`. It defines every construct the review asks you to judge. Read it once fully before labeling, and re-check it any time a case feels ambiguous.

You are validating whether a frozen automated pipeline's passage-level correspondences and change classifications agree with independent human judgment. **You are not told what the system decided.** Your job is to look at the passage text (and page images, where you inspect the source PDF) and judge each case on its own terms.

Do not try to guess or reverse-engineer the system's similarity scores. There are no scores in front of you, and there should not be — judging "is this the same disclosure" or "how much did it change" from the text itself is the entire point.

---

## Part 1 — Matched-passage cases (`sample_bucket` = UNCHANGED / LIGHTLY_MODIFIED / SUBSTANTIALLY_MODIFIED / AMBIGUOUS)

Each row shows an `earlier_text` passage (from the earlier report) and a `later_text` passage (from the later report), with heading and page context, and optionally the immediately preceding/following passage in each report (`*_context_before` / `*_context_after`) for structural orientation.

### Q1 — Correspondence: `human_correspondence`

**Are these passages versions of the same underlying disclosure?**

Enter one of:
- `YES` — the two passages communicate the same disclosure/topic in a corresponding structural role, even if the wording changed substantially.
- `NO` — the two passages are not really about the same thing; any textual overlap is coincidental or generic.
- `UNCERTAIN` — you cannot tell from the text given (rare; use sparingly, and add a note explaining why).

**Same underlying disclosure** means: a knowledgeable reader comparing the two annual reports would say "this is where they say the same thing about X" — even if the surrounding structure, ordering, or exact section moved. It does **not** require identical wording, identical length, or identical position in the document.

Judge this independent of how much the text changed — a passage can be substantially rewritten and still be "the same disclosure" (e.g., last year's revenue commentary vs. this year's, even if every number and most sentences differ).

### Q2 — Change magnitude: `human_change` (only if Q1 = YES)

- `EFFECTIVELY_UNCHANGED` — only cosmetic, annual-rollover (e.g., year number, page number), or negligible textual variation. A reader would not describe this as "changed."
- `MINOR` — recognizably the same disclosure with limited wording or content modification — a sentence added/removed, numbers updated, phrasing tightened, without a materially different message.
- `SUBSTANTIAL` — same disclosure unit, but meaningfully rewritten, expanded, contracted, qualified, or altered — the content or its implications read differently even though it is about the same topic.
- `STRUCTURAL_AMBIGUOUS` — a split/merge or passage-boundary difference (e.g., one earlier passage's content is now spread across two later passages, or vice versa) prevents a clean one-to-one judgment. Use this instead of forcing a single earlier/later comparison that doesn't really fit. Note which other passage(s) (by page/heading) seem to be involved, if you can tell.

### Q3 — Analytical significance: `human_significance` (optional, exploratory)

Does the change appear potentially meaningful to an analyst reading the report for investment/disclosure purposes?

- `COSMETIC` — no / cosmetic only.
- `POSSIBLY` — could matter, not obviously so.
- `CLEARLY_MEANINGFUL` — a clear substantive change an analyst would want to flag (new risk, changed guidance, changed accounting treatment, materially different tone, etc).
- `UNABLE_TO_DETERMINE` — can't tell from the passage alone (e.g., needs surrounding financial statements).

This column is exploratory only. It does not redefine or replace the system's existing UNCHANGED/LIGHTLY_MODIFIED/SUBSTANTIALLY_MODIFIED labels — it captures something additional (whether a change would matter to an analyst), which is not the same axis as how much text changed.

---

## Part 2 — Unmatched cases (`sample_bucket` = NEW / REMOVED)

These rows show one passage (`later_text` for a NEW case, `earlier_text` for a REMOVED case) plus three diagnostic alternatives pulled from the *opposite* report, purely to give you enough context to judge — **not** a ranked or "system-preferred" list:

- `opposite_top_lexical_*` — the opposite-report passage with the highest raw word-overlap similarity to this one.
- `opposite_top_semantic_*` — the opposite-report passage with the highest embedding-similarity to this one.
- `opposite_top_positional_*` — the opposite-report passage nearest this one's relative position in the document.

Any, all, or none of these three may be a genuine match. They are computed independently by simple, separate methods — none of them is "what the system chose."

### Q4 — Unmatched validity: `human_unmatched_label`

**Is there a reasonable corresponding disclosure in the adjacent report?**

- `NO_CORRESPONDENCE` — none of the candidates (or anything else you'd expect) is a real match; NEW/REMOVED looks correct.
- `CORRESPONDENCE_EXISTS` — one of the candidates (or something you recall seeing) is clearly the same disclosure; the pipeline likely missed a match. Note which candidate (lexical/semantic/positional) in `notes`, if any.
- `STRUCTURAL_SPLIT_MERGE` — the disclosure exists but is now split across / merged from multiple passages, so a clean single match isn't possible.
- `UNCERTAIN` — genuinely can't tell.

---

## Part 3 — Passage-quality review (separate subset)

For the ~100-passage passage-quality subset, rate the **canonical passage itself** (not correspondence, not change) using the categories in the passage-quality CSV:

- `COHERENT_SUBSTANTIVE` — a coherent, self-contained substantive disclosure unit (a paragraph or section that reads as a complete thought).
- `COHERENT_STRUCTURAL` — a coherent short structural/analytical item (e.g., a heading-only line, a short list item, a table caption) that is legitimately short, not broken.
- `TABLE_ARTIFACT` — table/layout content that leaked into narrative text (numbers, column headers, running totals) rather than prose.
- `MIXED_POOR_BOUNDARY` — mixes two unrelated topics, or the passage boundary clearly cuts a sentence/thought in the wrong place.
- `EXTRACTION_ARTIFACT` — garbled, duplicated, or clearly a PDF-extraction error (broken encoding, repeated fragments, running headers/footers leaking in).
- `OTHER` — none of the above; explain in notes.

---

## Worked examples

**Correspondence = YES, change = MINOR** (illustrative, not from the actual corpus):
> Earlier: "The Group's revenue for the year increased by 8% to R1.2 billion, driven primarily by strong performance in the retail segment."
> Later: "The Group's revenue for the year increased by 6% to R1.3 billion, driven primarily by continued strong performance in the retail segment."
Same disclosure (revenue growth driver commentary), numbers updated, message essentially the same → MINOR.

**Correspondence = YES, change = SUBSTANTIAL**:
> Earlier: "The Group continues to monitor credit risk through its standard provisioning policy."
> Later: "Following a detailed review, the Group has revised its expected credit loss methodology, resulting in a R45 million increase in the provision for credit losses, reflecting heightened macroeconomic uncertainty."
Same disclosure topic (credit risk/provisioning), but materially different content and implication → SUBSTANTIAL.

**Correspondence = NO**:
> Earlier passage about directors' remuneration; "later" candidate passage is a generic boilerplate paragraph about "forward-looking statements." Different topics entirely, despite superficial paragraph-length/positional similarity → NO.

**NEW, `human_unmatched_label` = NO_CORRESPONDENCE**:
A later-report passage introducing a brand-new ESG disclosure required by a rule that only came into force this year; none of the three opposite-report candidates address the same topic → NO_CORRESPONDENCE, NEW is correct.

---

## General reminders

- Judge from the text given; only consult the source PDF (`earlier_report_pdf_path` / `later_report_pdf_path`, `earlier_page` / `later_page`) when the case is genuinely unclear from text alone, or when your label is UNCERTAIN / STRUCTURAL_* / a NEW-REMOVED disagreement — see Milestone 7 Section 12.
- Do not infer or reproduce a similarity threshold. If two passages feel "close enough," judge them on disclosure content and message, not on how many words overlap.
- It's fine to leave `notes` with a short rationale, especially for UNCERTAIN/STRUCTURAL/disagreement-prone cases — that record is what makes the later disagreement analysis (Milestone 7 Section 25) possible.
- Put your reviewer identifier in `reviewer_id` on every row you label (e.g., `R1`, `R2`) so a second reviewer's independent pass on the overlap subset can be distinguished.

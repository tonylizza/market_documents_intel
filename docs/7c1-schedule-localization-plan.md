# Plan: Track 7C.1 — Financial Performance Schedule Localization + Headed Narrative Semantic Units

Status: planning document only. No code has been written. Revised from the prior draft to correct
scope drift: the original draft implemented a full localize → reconstruct → align → compare
vertical slice. **7C.1 stops at source-faithful semantic-unit reconstruction and provenance.**
Alignment and comparison are explicitly out of scope and deferred to later 7C milestones (§7).

This plan is scoped by explicit user decision to the following constraints, recorded here so
later phases don't have to re-derive them:

1. **Parallel replacement track, not an additive layer.** The new pipeline is built entirely
   alongside the existing passage-segmentation/alignment/feature pipeline. Nothing in this plan
   modifies, calls, or is called by `passage_segmentation.py`, `passage_alignment.py`,
   `feature_extraction.py`, `financial_language_signals.py`, or any `publishing/` module. The
   existing pipeline keeps running unchanged as the production baseline until a future, separate
   cutover decision. Convergence is tracked as "functional parity," not "integration."
2. **Milestone scope: one schedule, one semantic-unit type, stop at persistence + provenance.**
   7C.1 proves `PDF/block extraction → FINANCIAL_PERFORMANCE schedule localization → one headed
   narrative semantic-unit type → source-faithful reconstruction → page/block/char-span
   provenance → persistence + audit`. It does **not** implement cross-year alignment, comparison
   of any kind (lexical, structured, or otherwise), or comparison-type routing. Those are
   real, separately-scoped future milestones (§7), not columns or tables quietly included now.
3. **New roadmap track, numbered 7C.** This does not renumber or replace the completed Milestone 1
   in `CLAUDE.md`, nor insert into 7A/7B. A follow-up edit to `CLAUDE.md`'s roadmap table (adding
   the 7C.1–7C.6 rows from §7) is recommended once this plan is approved, but is not made by this
   document.
4. **Terminology: structural semantic unit, not analytical unit.** The research explicitly
   distinguishes a *structural semantic unit* (a source-grounded, reconstructed passage of text
   with known boundaries and provenance) from an *analytical comparison unit* (the same content,
   once it has been classified with a comparison type and is ready for cross-year comparison).
   7C.1 produces only the former. The persisted row is named `SemanticUnit`, not
   `AnalyticalUnit` — it carries no comparison-type classification, because that classification
   is a downstream, not-yet-built concept (7C.3).

Grounded in the eight prior experiment docs in `docs/experiments/`, especially
`annual-report-schedule-localization.md` (schedule taxonomy, per-company boundary behavior),
`annual-report-analytical-unit-eligibility.md` (the structural-unit vs. analytical-unit
distinction this plan preserves), and `annual-report-bel-compact-validation.md` (source of the
BEL Gross Margin chart-interruption case this milestone's regression test is built around).

---

## 1. Current-state audit

*(Unchanged from the prior draft — still accurate.)*

Audited: `src/market_documents/models/*.py`, `src/market_documents/services/*.py`,
`migrations/versions/*.py`, `src/market_documents/cli/*.py`.

**Finding: no existing table, enum, or service references "schedule" or "semantic/analytical
unit" in any form.** `grep -ril "schedule\|analytical_unit\|semantic_unit" src/ migrations_app/`
matches only `structured_content_audit.py`, an unrelated block-classification diagnostic. This is
a genuinely new layer, not an extension of an existing one.

**Existing pipeline this track must not touch** (main DB, `migrations/`):

```
Report -> ExtractionRun -> Page, TextBlock -> NarrativeDocument
       -> PassageSegmentationRun -> Passage, PassageSourceBlock
       -> EmbeddingRun -> PassageEmbedding, PassageRetrievalChunk
       -> AlignmentRun -> PassageAlignment   (scoped to ReportPair)
       -> FeatureRun -> ReportPairFeatures
       -> LanguageSignalRun -> PassageLanguageSignal, ReportPairLanguageFeatures
```

**What this track reuses read-only:** `Report`, `Company`, `ExtractionRun`, `Page`, `TextBlock`,
`NarrativeDocument` — i.e. everything up to and including source extraction. Schedule
localization and semantic-unit extraction both read `Page`/`TextBlock` text the same way
`passage_segmentation.py` does; they do not read `Passage` at all, and (revised from the prior
draft) 7C.1 never reads or references `ReportPair` either, since there is no cross-year work in
this milestone. This is a deliberate boundary: the new track re-derives its own units directly
from blocks, so it never depends on passage segmentation's boundaries or config, keeping the two
tracks genuinely independent — a prerequisite for a later apples-to-apples parity comparison.

**Conventions confirmed by reading `alignment.py`, `feature.py`, `report_pair.py`,
`passage_segmentation.py`, `passage.py`** (these still govern every new file in §3):

- Run/Result split: a `*Run` row (status, timestamps, `algorithm_version`,
  `configuration_hash`, `error_message`/`review_reason`) plus one or more result rows produced by
  a successful run. "Current successful run" is always a query-time rule (`get_current_*`), never
  a stored boolean flag.
- Every score/measurement column is individually nullable — never a fabricated 0/None conflation.
- `UUIDPkMixin` + `TimestampMixin` on every table; `SAEnum(Enum, name="snake_case_name")`.
- Pure, DB-free algorithm functions kept separate from orchestration functions that touch the
  `Session` — both live in the same module but are independently unit-testable.
- CLI commands are thin `typer` wrappers that open a session and call one service function.

---

## 2. Revised scope statement

**In scope for 7C.1:**

- Localizing exactly one normalized schedule, `FINANCIAL_PERFORMANCE`, from a `Report`'s existing
  `Page`/`TextBlock` extraction.
- Extracting exactly one semantic-unit type, `HEADED_NARRATIVE_UNIT`, from a localized
  `FINANCIAL_PERFORMANCE` schedule instance, with two boundary strategies
  (`NEXT_HEADING`, `ANCHOR_SENTENCE`).
- Source-faithful text reconstruction for each extracted unit.
- Full page/block/character-span provenance for each extracted unit, traceable back to
  `TextBlock` → `Page` → `Report`.
- Persistence of runs, schedule instances, and semantic units, with idempotent reruns via
  configuration hash, following the codebase's Run/Result convention.
- Validation against two companies (BEL, ACT) to prove the extraction *pattern* — a headed
  narrative subsection inside `FINANCIAL_PERFORMANCE` — generalizes, without requiring the two
  companies' chosen units to represent the same underlying financial concept.

**Explicitly out of scope for 7C.1** (deferred to §7's later milestones):

- Cross-year semantic-unit alignment (matching a unit across adjacent reports) — no
  `UnitAlignmentRun`, `UnitAlignment`, or related enums/tables/services/CLI/tests.
- Any comparison or scoring — lexical, structured, or otherwise. No `UnitComparison`, no
  `ComparisonType` classification, no reuse of `similarity_metrics.py`, no word-count-change
  output.
- The other nine normalized schedules. The `NormalizedSchedule` enum may still name all ten
  (harmless, avoids a future migration just to add enum members), but only
  `FINANCIAL_PERFORMANCE` has an implemented, tested localization path in 7C.1. Any other value
  passed to the localization service fails/skips explicitly (`NotImplementedError`-style
  rejection at the service boundary, not a silent no-op).
- Any other semantic-unit type beyond `HEADED_NARRATIVE_UNIT`.
- Corpus-wide backfill. Only the specific ACT/BEL report-years needed to reproduce the
  already-validated research cases are run.
- Publishing, web app, or any integration with the existing passage pipeline.

---

## 3. Revised dependency graph

```
┌─────────────────────────────────────────────────────────────────────┐
│ EXISTING (untouched, read-only dependency)                          │
│  Report, Company, ExtractionRun, Page, TextBlock, NarrativeDocument │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ reads
                                 v
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE A — Schedule localization  (per Report; FINANCIAL_PERFORMANCE │
│           only in 7C.1)                                             │
│  models/schedule.py: ScheduleLocalizationRun, ScheduleInstance,     │
│                       ScheduleInstanceSupportingSpan                │
│  services/schedule_config.py, services/schedule_localization.py     │
└───────────────────────────────┬───────────────────────────────────┘
                                 │ reads ScheduleInstance
                                 v
┌─────────────────────────────────────────────────────────────────────┐
│ STAGE B — Semantic-unit extraction  (per Report, per schedule       │
│           instance; HEADED_NARRATIVE_UNIT only in 7C.1)             │
│  models/semantic_unit.py: SemanticUnitRun, SemanticUnit,            │
│                            SemanticUnitSourceBlock                   │
│  services/semantic_unit_config.py,                                  │
│  services/semantic_unit_extraction.py                               │
└─────────────────────────────────────────────────────────────────────┘
                                 │
                                 v
                     CLI: cli/units.py (thin, wraps A-B: localize/extract/status)

╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌ 7C.1 BOUNDARY ╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌
  Not built in 7C.1 (see §7 roadmap):
  Stage C — cross-year unit alignment                        (7C.2)
  Stage D — analytical eligibility / comparison-type routing  (7C.3)
  Stage E — lexical comparison                                (7C.3)
  Stage F — structured-table comparison                       (7C.4)
```

Each built stage is independently re-runnable and idempotent (same `configuration_hash` skip
logic as the existing pipeline). Stage B never re-derives localization; it only reads a given
`ScheduleInstance` and the `TextBlock`s under its page range.

---

## 4. Revised minimal schema

One new Alembic migration against the **main** DB (`migrations/`, not `migrations_app/`).

### 4.1 New enums (`models/enums.py` additions)

```python
class NormalizedSchedule(str, enum.Enum):
    """Full validated taxonomy named for future convenience; only
    FINANCIAL_PERFORMANCE has an implemented localization path in 7C.1 (see
    schedule_config.py). Any other value is rejected explicitly at the
    service boundary, not silently skipped."""
    CEO_REVIEW = "CEO_REVIEW"
    CHAIR_REVIEW = "CHAIR_REVIEW"
    FINANCIAL_PERFORMANCE = "FINANCIAL_PERFORMANCE"
    MATERIAL_RISKS = "MATERIAL_RISKS"
    STRATEGY = "STRATEGY"
    OUTLOOK = "OUTLOOK"
    CORPORATE_GOVERNANCE = "CORPORATE_GOVERNANCE"
    REMUNERATION = "REMUNERATION"
    LEGAL_REGULATORY = "LEGAL_REGULATORY"
    MATERIAL_MATTERS_OPERATING_ENVIRONMENT = "MATERIAL_MATTERS_OPERATING_ENVIRONMENT"

class ScheduleLocalizationRunStatus(str, enum.Enum):
    PENDING = "PENDING"; RUNNING = "RUNNING"; COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"; FAILED = "FAILED"

class ScheduleLocalizationStatus(str, enum.Enum):
    FOUND_PRIMARY_ONLY = "FOUND_PRIMARY_ONLY"
    FOUND_PRIMARY_AND_SUPPORTING = "FOUND_PRIMARY_AND_SUPPORTING"
    DISTRIBUTED_NO_CLEAR_PRIMARY = "DISTRIBUTED_NO_CLEAR_PRIMARY"
    NOT_FOUND = "NOT_FOUND"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class BoundaryConfidence(str, enum.Enum):
    HIGH = "HIGH"; MEDIUM = "MEDIUM"; LOW = "LOW"

class SemanticUnitRunStatus(str, enum.Enum):
    PENDING = "PENDING"; RUNNING = "RUNNING"; COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"; FAILED = "FAILED"

class SemanticUnitType(str, enum.Enum):
    """Only HEADED_NARRATIVE_UNIT is implemented in 7C.1. Not a broad
    ontology -- one member, added to because it's an enum rather than a
    literal string, not because more types are expected imminently."""
    HEADED_NARRATIVE_UNIT = "HEADED_NARRATIVE_UNIT"

class SemanticUnitBoundaryStrategy(str, enum.Enum):
    NEXT_HEADING = "NEXT_HEADING"
    ANCHOR_SENTENCE = "ANCHOR_SENTENCE"

class SemanticUnitBoundaryStatus(str, enum.Enum):
    """Whether an end boundary was actually resolved -- kept independent of
    *how confidently* it was resolved (see `BoundaryConfidence`, reused
    below). Conflating the two into one enum (e.g. a single
    RESOLVED_LOW_CONFIDENCE member) would make it impossible to represent
    "resolved, but only medium confidence" without inventing a cross
    product of members -- two orthogonal fields do that cleanly."""
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
```

Removed from the prior draft, entirely: `ComparisonType`, `UnitAlignmentRunStatus`,
`UnitAlignmentStatus`, `UnitAlignmentConfidence`. None of these are defined in the 7C.1
migration. They are introduced in 7C.2/7C.3 when the services that produce them actually exist —
not pre-declared here on the theory that they'll be needed eventually.

### 4.2 New tables

**`schedule_localization_runs`** — mirrors `PassageSegmentationRun`. *(Unchanged from prior
draft.)*

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| report_id | UUID FK→reports, CASCADE | |
| extraction_run_id | UUID FK→extraction_runs, CASCADE | |
| schedule | enum NormalizedSchedule | the run's scope, `FINANCIAL_PERFORMANCE` only in 7C.1. Stored on the run itself (not inferred from child `ScheduleInstance` rows) because the run/service is scoped per `(report, schedule)` — a future schedule's run needs its own identity before any instance exists under it, e.g. to record a `FAILED` run that produced zero instances. |
| algorithm_version | String(64) | |
| configuration_hash | String(64) | |
| status | enum ScheduleLocalizationRunStatus | default PENDING |
| started_at, completed_at | DateTime tz, nullable | |
| error_message, review_reason | Text, nullable | |
| created_at, updated_at | TimestampMixin | |

Index: `(report_id, schedule, status)`, `(report_id, completed_at)`.

**`schedule_instances`** — one row per `(run, schedule)`. In 7C.1 every run only ever localizes
`FINANCIAL_PERFORMANCE`, so in practice one row per run, but the column stays generic (not
narrowed to a boolean) so 7C.x can add schedules later without a schema change.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| schedule_localization_run_id | UUID FK→schedule_localization_runs, CASCADE | |
| report_id | UUID FK→reports, CASCADE | denormalized |
| schedule | enum NormalizedSchedule | `FINANCIAL_PERFORMANCE` only, enforced by the service (§6.1), not a DB constraint |
| status | enum ScheduleLocalizationStatus | |
| heading_text | String(512), nullable | null when NOT_FOUND/DISTRIBUTED |
| start_page, end_page | Integer, nullable | PDF page index, 1-based |
| boundary_confidence | enum BoundaryConfidence, nullable | |
| confidence_score | Float, nullable | 0–1 |
| reasoning_summary | Text, nullable | |

Constraint: `UniqueConstraint(schedule_localization_run_id, schedule)`.
Index: `(report_id, schedule)`.

**`schedule_instance_supporting_spans`** — kept, still justified: BEL's
`FINANCIAL_PERFORMANCE` schedule itself has a supporting fragment inside the joint report
(§3.3 of the schedule-localization experiment: "Financial" subsection within the Joint report,
p.35, supporting the Finance director's report primary). Losing this would understate a case
7C.1's own target company/schedule already exhibits.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| schedule_instance_id | UUID FK→schedule_instances, CASCADE | |
| heading_text | String(512), nullable | |
| start_page, end_page | Integer | |

**`semantic_unit_runs`** — mirrors `PassageSegmentationRun`; one per `(report, schedule)`.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| report_id | UUID FK→reports, CASCADE | |
| schedule_localization_run_id | UUID FK→schedule_localization_runs, CASCADE | pins the source schedule instance(s) |
| schedule | enum NormalizedSchedule | `FINANCIAL_PERFORMANCE` only in 7C.1 |
| algorithm_version, configuration_hash | String(64) | |
| status | enum SemanticUnitRunStatus | |
| started_at, completed_at, error_message, review_reason | as above | |

Index: `(report_id, schedule, status)`.

**`semantic_units`** — the milestone's central deliverable. Renamed from `AnalyticalUnit`: this
row carries no comparison-type classification and is not yet an analytical/comparison-ready
object — see §1's terminology note.

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| semantic_unit_run_id | UUID FK→semantic_unit_runs, CASCADE | |
| report_id | UUID FK→reports, CASCADE | denormalized |
| schedule_instance_id | UUID FK→schedule_instances, CASCADE | |
| unit_key | String(128) | stable slug, e.g. `"gross_margin"` — company+schedule-scoped, hand-defined per unit config, **not required to match across companies** (§6.1: BEL uses `gross_margin`, ACT uses whatever clean headed subsection is chosen for it — see §6.3) |
| unit_type | enum SemanticUnitType | `HEADED_NARRATIVE_UNIT` only in 7C.1 |
| source_heading | String(512) | the matched subsection *start* heading text — always known: a `SemanticUnit` row is only created once a start heading has actually matched, so this and `start_page` are never null even when the end boundary later fails to resolve |
| start_page | Integer | always known, see above |
| boundary_strategy | enum SemanticUnitBoundaryStrategy | `NEXT_HEADING` or `ANCHOR_SENTENCE` — records which strategy was *attempted*, independent of whether it succeeded |
| boundary_anchor_text | Text, nullable | the recurring phrase used to resolve the end boundary, when `ANCHOR_SENTENCE` is used |
| boundary_status | enum SemanticUnitBoundaryStatus | `RESOLVED`/`UNRESOLVED` — whether an end boundary was actually found (see §4.1 note; kept independent of confidence) |
| boundary_confidence | enum BoundaryConfidence, nullable | reused from §4.1's schedule-localization enum. Null when `boundary_status = UNRESOLVED` (there is no confidence to report about a boundary that wasn't found); `HIGH`/`MEDIUM`/`LOW` when `RESOLVED` |
| end_page | Integer, nullable | null when `boundary_status = UNRESOLVED` |
| source_text | Text, nullable | source-faithful reconstructed text; **null when `boundary_status = UNRESOLVED` — never a fabricated or partial best-guess string.** An unresolved unit is persisted as an audit record of the attempt, not as invented content |
| word_count | Integer, nullable | metadata only, derived from `source_text` when present — not a comparison input in this milestone |
| extraction_note | Text, nullable | free-text record of any boundary correction applied (RESOLVED case) or the reason resolution failed (UNRESOLVED case) — always populated for UNRESOLVED rows so the audit trail explains *why*, not just *that* |
| created_at, updated_at | TimestampMixin | |

Constraint: `UniqueConstraint(semantic_unit_run_id, schedule_instance_id, unit_key)`.
Index: `(report_id, unit_key)`, `(report_id, boundary_status)`.

**Persistence behavior for UNRESOLVED units** (correction to the prior draft, which implicitly
required `source_text`/`end_page` to always be populated): if `semantic_unit_extraction.py`'s
pure `extract_unit` function cannot resolve a trustworthy end boundary — the configured
`ANCHOR_SENTENCE` phrase is not found anywhere in the schedule instance's remaining text, and
`NEXT_HEADING` is not configured as a fallback for that unit — the orchestration layer still
persists one `SemanticUnit` row: `boundary_status = UNRESOLVED`, `end_page = None`,
`source_text = None`, `boundary_confidence = None`, and `extraction_note` explaining what was
searched for and not found. This makes an unresolved unit visible and queryable (`WHERE
boundary_status = 'UNRESOLVED'`) rather than either silently absent (indistinguishable from "not
yet attempted") or silently populated with untrustworthy text. The run itself is
`COMPLETED_WITH_WARNINGS` in this case, not `FAILED` — one unresolved unit doesn't invalidate the
rest of the run's results.

Removed from the prior draft: `comparison_type` column. There is no comparison-type classifier
in 7C.1 to populate it, and adding the column now would be exactly the "speculative future
comparison column" the revision instructions rule out.

**`semantic_unit_source_blocks`** — provenance join, mirrors `PassageSourceBlock`. *(Unchanged
from prior draft — this is the mechanism that answers "exactly which source block text produced
this semantic unit?", required by acceptance criterion 7.)*

| column | type | notes |
|---|---|---|
| id | UUID PK | |
| semantic_unit_id | UUID FK→semantic_units, CASCADE | |
| text_block_id | UUID FK→text_blocks, CASCADE | |
| block_order | Integer | position of this block within the unit |
| char_start, char_end | Integer | span within the block's text contributed to this unit; `(0, len(block.text))` for a fully-included block, narrower only for the block containing the anchor-sentence boundary |

**Total: 6 tables, 8 enums** (down from the prior draft's 8 tables, 8 enums — the three removed
tables, `unit_alignment_runs`, `unit_alignments`, and `unit_comparisons`, are replaced by nothing
in 7C.1; no FK columns referencing them exist anywhere in this schema).

---

## 5. Revised file-by-file build plan

All paths are new files unless marked *(edit)*. Nothing under `publishing/`, `web/`,
`cli/pairs.py`, `cli/passages.py`, or any existing `services/passage_*`, `services/alignment_*`,
`services/feature_*`, `services/financial_language_*` module is touched.

### 5.1 Schema

| File | Purpose |
|---|---|
| `src/market_documents/models/enums.py` *(edit)* | Add the 8 enums from §4.1. Additive only. |
| `src/market_documents/models/schedule.py` *(new)* | `ScheduleLocalizationRun`, `ScheduleInstance`, `ScheduleInstanceSupportingSpan`. |
| `src/market_documents/models/semantic_unit.py` *(new)* | `SemanticUnitRun`, `SemanticUnit`, `SemanticUnitSourceBlock`. |
| `src/market_documents/models/__init__.py` *(edit)* | Register the 2 new model modules. |
| `migrations/versions/<rev>_schedule_and_semantic_unit_schema.py` *(new)* | One Alembic migration: 8 new PG enum types, 6 new tables, all indexes/constraints from §4.2. |

Removed from the prior draft: `models/unit_alignment.py`, `models/unit_comparison.py`.

### 5.2 Stage A — schedule localization

| File | Purpose |
|---|---|
| `src/market_documents/services/schedule_config.py` *(new)* | `ScheduleConfig` dataclass. In 7C.1 this holds exactly one entry: `FINANCIAL_PERFORMANCE`'s heading vocabulary per company (e.g. `["Finance director's report", "CFO's review", "Financial performance", ...]`, drawn from the schedule-localization experiment's per-company findings). `ALGORITHM_VERSION`, `compute_configuration_hash()` — mirrors `passage_config.py`. |
| `src/market_documents/services/schedule_localization.py` *(new)* | Pure function `localize_schedule(pages, schedule: NormalizedSchedule, config) -> ScheduleLocalizationResult`. Raises `NotImplementedError` (a real, visible failure, not a silent skip) if `schedule != NormalizedSchedule.FINANCIAL_PERFORMANCE` — enforcing the §2 scope boundary at the code level, not just in this document. Plus orchestration `run_localization(session, report, schedule)` / `get_current_localization_run(session, report, schedule)`. |

### 5.3 Stage B — semantic-unit extraction

| File | Purpose |
|---|---|
| `src/market_documents/services/semantic_unit_config.py` *(new)* | Per-`unit_key` `HEADED_NARRATIVE_UNIT` boundary definition: start heading/phrase, `boundary_strategy` (`NEXT_HEADING` or `ANCHOR_SENTENCE` + the anchor phrase/regex). Whitespace-tolerant anchor matching from the start (directly reflecting the BEL 2022 line-wrap finding). Holds the two 7C.1 unit definitions: BEL `gross_margin` and one ACT unit (chosen in step 4 of the rollout, §6, from ACT's `FINANCIAL_PERFORMANCE`/CFO's-review schedule — see §2's note that it need not be the same underlying concept as BEL's). |
| `src/market_documents/services/semantic_unit_extraction.py` *(new)* | Pure function `extract_unit(schedule_instance, blocks, unit_config) -> SemanticUnitResult` (resolves the boundary, reconstructs `source_text`, computes the block/char-span provenance) + orchestration `run_extraction(session, report, schedule)` / `get_current_extraction_run(session, report, schedule)`. |

Removed from the prior draft: `services/unit_alignment.py`, `services/unit_lexical_comparison.py`.

### 5.4 CLI

| File | Purpose |
|---|---|
| `src/market_documents/cli/units.py` *(new)* | Thin `typer` app: `units localize <ticker> --schedule financial_performance`, `units extract <ticker> --schedule financial_performance`, `units status <ticker>` (prints current run states for both stages). No `align` or `compare` subcommand exists in 7C.1's CLI at all — not merely undocumented. |
| `src/market_documents/cli/main.py` *(edit)* | One line: `app.add_typer(units.app, name="units")`. |

### 5.5 Tests

| File | Purpose |
|---|---|
| `tests/services/test_schedule_localization.py` | Clean `FINANCIAL_PERFORMANCE` primary match; NOT_FOUND case; the recurring BEL/Spur heading-displaced-to-bottom-of-page artifact; asserts calling `localize_schedule` with any non-`FINANCIAL_PERFORMANCE` schedule raises `NotImplementedError`. |
| `tests/services/test_semantic_unit_extraction.py` | `NEXT_HEADING` boundary case; `ANCHOR_SENTENCE` boundary case; whitespace/line-wrap-tolerant anchor matching (the BEL 2022 "prior \nyear" case); the BEL 2019 Gross Margin chart-interruption regression — asserts `NEXT_HEADING` on that fixture incorrectly includes chart text and `ANCHOR_SENTENCE` correctly excludes it. |
| `tests/services/test_semantic_unit_provenance.py` | Correct `SemanticUnitSourceBlock` block associations and ordering; correct `char_start`/`char_end` for a unit whose boundary falls mid-block. |
| `tests/integration/test_semantic_unit_pipeline_acceptance.py` | End-to-end: `Report`/`TextBlock`s → `FINANCIAL_PERFORMANCE` `ScheduleInstance` → `SemanticUnit` → provenance, for both BEL and ACT fixtures. See §7. |

Removed from the prior draft: `tests/services/test_unit_alignment.py`,
`tests/services/test_unit_lexical_comparison.py`.

---

## 6. Revised rollout sequence

1. **Migration + models** (§5.1). Run `alembic upgrade head` against a local/dev DB only;
   `alembic downgrade -1` verified to cleanly reverse. No data backfill — new tables start empty.
2. **Financial Performance schedule localization**, run only against the specific report-years
   needed for steps 3–4 below (not a corpus-wide backfill): BEL 2018–2022 and the ACT report-year
   used in the lexical-change-pilot/schedule-localization experiments (ACT 2022, plus at least one
   adjacent year if needed to pick a clean recurring ACT unit in step 4). Manually spot-check the
   resulting `schedule_instances` rows against the primary heading/start/end page/status already
   recorded in `annual-report-schedule-localization.md` and
   `annual-report-bel-compact-validation.md` for those report-years.
3. **BEL headed-narrative semantic unit** (`gross_margin`). Manually diff `SemanticUnit.source_text`
   against the source PDF for all 5 BEL years already manually checked in the BEL compact-validation
   experiment — this should reproduce that experiment's corrected reconstruction exactly, including
   reproducing (as a passing regression test) the 2019 chart-interruption fix and the 2022
   whitespace/line-wrap fix.
4. **ACT headed-narrative semantic unit.** Choose one clean, recurring, headed narrative
   subsection inside ACT's `FINANCIAL_PERFORMANCE` schedule (CFO's review) — it does not need to
   be "gross margin" or any cross-company-equivalent concept, only a genuine headed narrative
   subsection, per §2. Manually diff the reconstructed text against source for the years checked.
   This step validates that the *extraction pattern* generalizes, independent of which specific
   disclosure concept each company's report happens to name.
5. **Provenance validation** for both companies' units: confirm every `SemanticUnitSourceBlock`
   row's `text_block_id`/`block_order`/`char_start`/`char_end` reconstructs `source_text` exactly
   when concatenated, for every unit produced in steps 3–4.
6. **CLI/status wiring**, once stages 1–5 are independently verified.
7. **Final shadow-mode audit**: run `units status` across the full set of report-years touched in
   this rollout and confirm every run is `COMPLETED` (or `COMPLETED_WITH_WARNINGS` with a
   documented `review_reason`) with no silent `FAILED`/`UNRESOLVED` rows left unexamined.

No corpus-wide backfill at any step. No `publishing/`, `web/`, or existing-pipeline touch at any
step.

---

## 7. Revised acceptance criteria for Track 7C.1

Pass/fail gate for calling this milestone done:

1. The migration applies and reverses cleanly on a scratch DB; all 6 tables, 8 enums, and listed
   indexes/constraints exist exactly as specified in §4.
2. The existing passage pipeline remains behaviorally untouched — `git diff` against `main`
   touches only the files listed in §5 plus `models/__init__.py`, `models/enums.py`,
   `cli/main.py`, confirmed by review before merge.
3. `FINANCIAL_PERFORMANCE` localization for the selected ACT/BEL reports matches the
   already-validated research boundaries (heading, start/end page, status) within the tolerance
   the source experiments used.
4. BEL's `gross_margin` unit is reconstructed source-faithfully across all validated years
   (2018–2022).
5. The BEL 2019 Gross Margin regression test proves a naive `NEXT_HEADING` boundary includes
   chart noise while the configured `ANCHOR_SENTENCE` boundary excludes it — i.e. the anchor
   strategy is demonstrated load-bearing, not merely present.
6. One recurring ACT headed-narrative subsection is also reconstructed correctly using the same
   general `HEADED_NARRATIVE_UNIT` mechanism, with its own independently-chosen `unit_key`.
7. Every persisted `SemanticUnit` is traceable back to exact source `TextBlock`s, pages, and
   character spans (where a boundary falls mid-block) via `SemanticUnitSourceBlock`.
8. Any localization or extraction result with low confidence or an unresolved boundary is
   persisted with an explicit, independent `boundary_status` (`RESOLVED`/`UNRESOLVED`) and, when
   resolved, `boundary_confidence` (`HIGH`/`MEDIUM`/`LOW`) — never silently accepted as if fully
   resolved, and an `UNRESOLVED` unit's `source_text`/`end_page` are persisted as `NULL`, never
   invented or partially fabricated.
9. **No cross-year alignment, lexical scoring, structured comparison, comparison-type
   classification, publishing integration, or old-pipeline retirement is implemented anywhere in
   this milestone.** Confirmed by the absence of any `unit_alignment*`/`unit_comparison*`
   file, table, enum, or CLI command in the diff — not merely by this document's intent.

---

## 8. Roadmap placement (7C.1–7C.6)

Recommended addition to `CLAUDE.md`'s roadmap table once this plan is approved (not made by this
document):

| Milestone | Main result | Status |
|---|---|---|
| 7C.1 | Source blocks → Financial Performance schedule localization → headed narrative semantic units, with full source provenance | This plan |
| 7C.2 | Cross-year semantic-unit alignment | Planned |
| 7C.3 | Analytical eligibility / comparison-type routing + lexical comparison | Planned |
| 7C.4 | Structured-table comparison | Planned |
| 7C.5 | Shadow publishing / parity evaluation against the existing passage pipeline | Planned |
| 7C.6 | Production cutover and passage-alignment retirement | Planned |

None of 7C.2–7C.6 are designed, scoped, or implemented by this document. They are named here only
so 7C.1's schema and service boundaries can be reviewed against where the track is headed, without
building any of that future work now.

# Track 7C.2: Cross-Year Semantic-Unit Alignment

## 1. Scope

7C.2 answers exactly one question:

> Which semantic unit in the later report corresponds to which semantic unit
> in the earlier report?

It does **not** answer "how much did it change" (7C.3), does not touch
lexical metrics, analytical eligibility, structured-table comparison,
publishing, or UI, and does not cut over the passage pipeline. It reads
only the persisted output of 7C.1 (`SemanticUnitRun` / `SemanticUnit`) for
an adjacent-year `ReportPair` and never re-localizes schedules, re-extracts
units, or reads `Passage`/`PassageAlignment`/legacy `TextBlock`.

```
ReportPair
   ->
current successful SemanticUnitRun (earlier)
current successful SemanticUnitRun (later)
   ->
SemanticUnitAlignmentRun
   ->
SemanticUnitAlignment
```

Every `ReportPair` row is already an adjacent-year pair by construction
(`services.pairing.build_pairs` only ever pairs a report with its immediate
predecessor by `period_end`), so no additional adjacency filtering was
needed.

## 2. Alignment model

States implemented: `MATCHED`, `ADDED`, `REMOVED`, `UNRESOLVED_UPSTREAM`,
`AMBIGUOUS`. `RENAMED` is declared in `SemanticUnitAlignmentStatus` but
**not currently emitted** -- see Section 7.

`MOVED`, `SPLIT`, `MERGED`, `RESTRUCTURED`, `EXTERNALIZED` are explicitly
out of scope and not implemented. The `SemanticUnitAlignment` schema
enforces this at the database level: within one run, a partial unique
index on `(alignment_run_id, later_semantic_unit_id)` (and the symmetric
one for `earlier_semantic_unit_id`) guarantees one earlier unit is never
silently aligned to multiple later units or vice versa.

`confidence` reuses the existing `AlignmentConfidence` enum
(`HIGH`/`MEDIUM`/`LOW`/`NEEDS_REVIEW`) rather than introducing a duplicate
type with identical members.

## 3. The deterministic matching cascade

Implemented in `services.semantic_unit_alignment.align_units` (pure,
DB-free: takes/returns plain dataclasses), invoked per `(ReportPair,
schedule)` by the orchestration in the same module.

1. **Exact unit_key match.** For each unit_key with a `RESOLVED` unit on
   both sides -> `MATCHED`, `HIGH` confidence. This is the primary happy
   path for the currently configured BEL `gross_margin` and ACT
   `cfo_conclusion` units, whose `unit_key` is fixed per company by
   `semantic_unit_config.py` and does not vary by year.
2. **Normalized heading match.** Among `RESOLVED` units left unmatched
   after step 1, a *unique* match on normalized heading text (case,
   whitespace, punctuation, and leading-numbering-prefix normalized) ->
   `MATCHED`, `MEDIUM` confidence. More than one candidate on either side
   -> `AMBIGUOUS`, `NEEDS_REVIEW`, never guessed.
3. **Presence-based classification** for everything still unmatched:
   - A unit present (`RESOLVED`) on one side with nothing under that
     unit_key on the other side is `REMOVED`/`ADDED` (`HIGH` confidence)
     **only if** the other side's `SemanticUnitRun` completed with **zero
     warnings** -- proof every unit that run attempted was cleanly
     resolved, so a missing counterpart there is confirmed absence.
   - If the other side's run completed **with warnings**, or the
     counterpart unit exists but its `boundary_status` is `UNRESOLVED`,
     the result is `UNRESOLVED_UPSTREAM` (`NEEDS_REVIEW`) instead. This is
     the load-bearing distinction that keeps an extraction limitation from
     being reported as a disclosure event -- see Section 8.

No embeddings, LLMs, VLMs, or lexical similarity metrics are used anywhere
in this cascade, per the milestone's explicit constraint.

## 4. Schema / files changed

- `src/market_documents/models/enums.py`: `SemanticUnitAlignmentRunStatus`,
  `SemanticUnitAlignmentStatus`.
- `src/market_documents/models/semantic_unit_alignment.py`:
  `SemanticUnitAlignmentRun`, `SemanticUnitAlignment`.
- `src/market_documents/models/__init__.py`: exports for the above.
- `src/market_documents/services/semantic_unit_alignment.py`: the pure
  cascade (`align_units`) and orchestration (`run_alignment`,
  `get_current_alignment_run`).
- `migrations/versions/b3e7d1a9f024_semantic_unit_alignment_schema.py`:
  `semantic_unit_alignment_runs` / `semantic_unit_alignments` tables.
- `src/market_documents/cli/units.py`: `units align <ticker> --schedule
  ...` command; `units status` now also prints each `ReportPair`'s current
  alignment-run state.
- Tests: `tests/test_semantic_unit_alignment.py` (pure cascade),
  `tests/test_semantic_unit_alignment_service.py` (DB-backed
  orchestration/integration).

No existing table, model, or migration was modified.

## 5. Tests

19 tests added, all passing:

- `test_semantic_unit_alignment.py` (12): exact unit_key match, earlier/
  later-only presence under a clean run (`REMOVED`/`ADDED`), normalized
  heading variation, ambiguous multiple candidates, unresolved-upstream in
  both directions (missing row and existing-but-`UNRESOLVED` row), no
  units on either side, and multiple simultaneous outcomes in one run.
- `test_semantic_unit_alignment_service.py` (7): end-to-end integration
  (persisted earlier + later `SemanticUnit` -> `SemanticUnitAlignmentRun`
  -> expected rows), ineligibility when one side has no current successful
  `SemanticUnitRun` at all, rerun/idempotency via `configuration_hash`,
  `force`, current-run selection, current-successful-`SemanticUnitRun`
  selection (a stale `FAILED` rerun must not be picked over the existing
  successful one), the BEL-2020-shaped missing-upstream-unit case end to
  end, and a direct assertion that `Passage`/`PassageAlignment` are never
  touched.

Full suite: **944 passed, 3 skipped, 0 failed** (`HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1 .venv/bin/python -m pytest -q`, 951.61s). The
pre-existing suite was 925 passed / 3 skipped immediately before this
track began (Track 7C.1 commit report); 944 - 925 = 19, exactly the new
7C.2 tests, with zero regressions elsewhere. The long wall-clock time is a
host artifact, not a code issue: the machine intermittently carried a very
high load average (peaks of ~70, normally near-idle) during this session,
which stretched a couple of pre-existing, legitimately slow
HuggingFace-model-loading test files
(`tests/test_embedding_service.py`,
`tests/publishing/test_publishing_disclosure_change_quality.py`) well
beyond their normal runtime when run as part of the full suite; both were
independently confirmed to pass cleanly and quickly in isolation (15
passed/6.64s and 16 passed/75.31s respectively), and neither intersects
any 7C.2 code path.

## 6. Real-corpus smoke results

`units align BEL --schedule financial_performance`:

| Pair | Result |
|---|---|
| 2016->2017 | ineligible -- earlier has no current successful semantic-unit run |
| 2017->2018 | COMPLETED_WITH_WARNINGS -- `gross_margin`: UNRESOLVED_UPSTREAM (earlier run warned, no row) |
| 2018->2019 | COMPLETED -- `gross_margin` -> `gross_margin`: MATCHED (HIGH, exact unit_key) |
| 2019->2020 | COMPLETED_WITH_WARNINGS -- `gross_margin`: UNRESOLVED_UPSTREAM (later run warned, no row -- the BEL 2020 caveat) |
| 2020->2021 | COMPLETED_WITH_WARNINGS -- `gross_margin`: UNRESOLVED_UPSTREAM (earlier run warned, no row) |
| 2021->2022 | COMPLETED -- `gross_margin` -> `gross_margin`: MATCHED (HIGH, exact unit_key) |

`units align ACT --schedule financial_performance`:

| Pair | Result |
|---|---|
| 2016->2024, 2016->2017 | ineligible -- earlier has no current successful semantic-unit run |
| 2017->2018, 2018->2019, 2022->2023, 2023->2024 | COMPLETED -- no configured unit resolved on either side for that pair (nothing to align) |
| 2019->2020 | ineligible -- later has no current successful semantic-unit run (schedule NOT_FOUND for ACT 2020) |
| 2020->2021 | ineligible -- earlier has no current successful semantic-unit run |
| 2021->2022 | COMPLETED_WITH_WARNINGS -- `cfo_conclusion`: UNRESOLVED_UPSTREAM (later run warned, no row) |

No pair in the real corpus produced a genuine `MATCHED`-via-heading,
`ADDED`, `REMOVED`, or `AMBIGUOUS` result: `MATCHED`-via-exact-key covers
every case where both sides cleanly resolved the same configured unit_key,
and every other case falls to `UNRESOLVED_UPSTREAM` because the
`unit_key`-having side's `SemanticUnitRun` always carries at least one
other warning in this corpus (see Section 8). This is the correct,
conservative outcome given the currently configured single-unit-per-company
setup -- not a gap in the mechanism.

## 7. Unsupported cases

- **RENAMED**: declared in `SemanticUnitAlignmentStatus`, never emitted.
  Step 2's normalized-heading match only fires when two headings are
  normalization-*equal*, at which point there is no deterministic way to
  tell "cosmetic formatting difference" apart from "genuine rename" without
  fuzzier evidence -- out of scope for 7C.2's no-lexical-similarity
  constraint. Reserved for a future milestone with real evidence to
  justify it.
- **MOVED / SPLIT / MERGED / RESTRUCTURED / EXTERNALIZED**: not
  implemented, per the milestone's explicit scope boundary. The
  partial-unique-index constraints on `SemanticUnitAlignment` make a
  SPLIT/MERGED-shaped bug fail loudly rather than silently fabricate a
  one-to-one match.
- **Semantic/LLM adjudication**: none used anywhere in this milestone.

## 8. Caveats

- **BEL 2020 `gross_margin`** remains unresolved from 7C.1 (no `TextBlock`
  anywhere contains the "Gross Margin" heading text -- a Category C
  upstream limitation, not a 7C.1 or 7C.2 bug). 7C.2 correctly reports both
  adjacent pairs touching it (2019->2020, 2020->2021) as
  `UNRESOLVED_UPSTREAM`, never as a false `REMOVED`/`ADDED` disclosure
  event.
- **Real-corpus REMOVED/ADDED coverage**: given the current single fixed
  `unit_key`-per-company configuration, a *clean* (zero-warning)
  `SemanticUnitRun` on the side missing a unit essentially cannot coexist
  with a genuine absence in this corpus -- every report/schedule pair that
  has warnings anywhere in its run also lacks the specific configured
  unit, so `ADDED`/`REMOVED` are exercised only by the unit tests, not the
  real corpus. This is intentional conservatism, not a defect: it means
  7C.2 never manufactures a disclosure event it cannot actually confirm.
- **ACT years with no configured unit resolved on either side** (e.g.
  2017->2018) complete as `COMPLETED` with zero alignment rows -- not an
  error, just nothing to align for that pair.

## 9. Final verdict

**PASS WITH DOCUMENTED CAVEAT -- READY FOR 7C.3**

Exact-key and normalized-heading alignment work correctly for every
currently resolved real semantic unit, and the BEL 2020 (and equivalent
ACT) unresolved/missing-upstream cases are handled without ever producing
a false `ADDED`/`REMOVED` disclosure event. The documented caveat is that
the real corpus's current single-unit-per-company configuration means
genuine `ADDED`/`REMOVED` are exercised only by unit tests, not by the real
corpus smoke test -- a consequence of the conservative design, not a defect
in it.

Verification commands:

```
.venv/bin/python -m pytest -q
.venv/bin/python -m alembic heads
.venv/bin/python -m market_documents.cli.main units align BEL --schedule financial_performance
.venv/bin/python -m market_documents.cli.main units align ACT --schedule financial_performance
```

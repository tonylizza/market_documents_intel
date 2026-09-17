# Track 7D.2c — ACT `healthcare_services_review` production-scope promotion

## 1. Unit being promoted

`("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review")`
— a `HEADED_NARRATIVE_UNIT` extracted for ACT's healthcare-services narrative
section, routed to `AnalyticalMode.LEXICAL_ONLY`.

## 2. Prior candidate evidence

Track 7D.2/7D.2a/7D.2b left this unit technically validated but scoped as
`production: candidate`:

- source-faithful extraction across 2021, 2022, 2023 reports;
- canonical provenance preference (7D.2a);
- two real MATCHED adjacent-year alignments (2021→2022, 2022→2023);
- valid `LEXICAL_ONLY` routing (`analytical_eligibility.py`);
- clean lexical comparisons;
- short alphanumeric chart/data-label noise hardened (7D.2b);
- no regressions in BEL `gross_margin` or ACT `cfo_conclusion`;
- full test suite green.

Its only remaining gate was `NEW_PIPELINE_NARRATIVE_SCOPE` membership — a
deliberate, explicit production-routing decision, not a technical readiness
gap.

## 3. Scope-config change

One tuple added to `NEW_PIPELINE_NARRATIVE_SCOPE` in
`src/market_documents/services/cutover_config.py`:

```python
("ACT", NormalizedSchedule.FINANCIAL_PERFORMANCE, "healthcare_services_review")
```

`CONFIG_VERSION` bumped `1.0.0` → `1.1.0`. No other scope tuple touched (no
Capital management, no additional units, no table-scope or BEL changes).

## 4. Coverage-registry result

`services/coverage_registry.py` derives `production_status` purely from
`NEW_PIPELINE_NARRATIVE_SCOPE` membership — no second hardcoded scope
source exists anywhere in the codebase (verified by explicit repo-wide
search across the Python backend, the CLI, and the Next.js frontend). The
registry flipped automatically, with no code change to `coverage_registry.py`
itself:

| unit | before | after |
|---|---|---|
| ACT `healthcare_services_review` | `candidate` | `enabled` |
| ACT `cfo_conclusion` | `enabled` | `enabled` (unchanged) |
| BEL `gross_margin` | `enabled` | `enabled` (unchanged) |

## 5. Targeted tests

- `tests/test_coverage_registry.py`: updated to assert `enabled` for the
  promoted unit; added a control assertion that an unconfigured unit
  (`capital_management`, which has no extraction config at all) still
  returns no registry entry.
- `tests/test_cutover_comparison.py`: added
  `test_promoted_healthcare_services_review_matched_returns_lexical_comparison`
  and
  `test_promoted_healthcare_services_review_unresolved_upstream_is_not_silently_backfilled_from_legacy`
  — exercises `get_narrative_comparison` end-to-end for the newly-enabled
  unit, both MATCHED/RESOLVED and UNRESOLVED_UPSTREAM paths.
- `tests/test_cutover_publishing.py` and
  `tests/publishing/test_publishing_lifecycle.py`: updated row-count
  assertions (ACT now publishes 2 narrative rows per pair, not 1, since it
  has two in-scope narrative units) — a direct, expected consequence of the
  scope change, not a regression.

## 6. UI architecture gap found and fixed (frontend)

Section-6 smoke testing surfaced a real, previously-latent bug:
`PostgresComparisonRepository.getNarrativeUnitComparison` queried
`app.current_narrative_unit_comparisons` by `report_comparison_id` alone
(no `unit_key` filter, no `ORDER BY`) and returned only `rows[0]`. This was
invisible while ACT had exactly one in-scope narrative unit
(`cfo_conclusion`); promoting a second one for the same ticker/schedule
made two rows exist per ACT report-comparison, and the single-row query
would non-deterministically drop one of the two units from the page.

Fixed (contained change, mirrors the existing `structured` list pattern
already used for ACT's two remuneration table families):

- `getNarrativeUnitComparison(id): NarrativeUnitComparison | null` →
  `getNarrativeUnitComparisons(id): NarrativeUnitComparison[]` (added
  `ORDER BY unit_key`), in `comparison-repository.ts` /
  `postgres-comparison-repository.ts`.
- `ComparisonView.narrative` changed from `NarrativeUnitComparison | null`
  to `NarrativeUnitComparison[]` in `comparison-facade.ts`.
- `page.tsx` now maps over `view.narrative` and renders one
  `NarrativeUnitComparisonSection` per unit, exactly as it already did for
  `view.structured`.
- Test fixture (`seed-app-database.ts`) extended with a second seeded
  narrative row (`healthcare_services_review`, `UNRESOLVED_UPSTREAM`)
  alongside the existing `cfo_conclusion` row, so the repository/facade
  test suites exercise the multi-unit case directly.

No extraction, alignment, lexical-comparison, classification, or
publishing-architecture code was touched — this fix is confined to the
frontend read/render path.

## 7. Publication results (local)

Built `2026-09-17-7d2c-healthcare-services-review-promotion.1` against the
local Docker Postgres app database, validated (458,592 checks, all passed),
and promoted to ACTIVE locally. Queried published rows directly:

```
ACT healthcare_services_review:
  2016-06-30 -> 2017-06-30   UNRESOLVED_UPSTREAM
  2016-06-30 -> 2024-06-30   UNRESOLVED_UPSTREAM
  2017-06-30 -> 2018-06-30   UNRESOLVED_UPSTREAM
  2018-06-30 -> 2019-06-30   UNRESOLVED_UPSTREAM
  2019-06-30 -> 2020-06-30   UNRESOLVED_UPSTREAM
  2020-06-30 -> 2021-06-30   UNRESOLVED_UPSTREAM
  2021-06-30 -> 2022-06-30   RESOLVED
  2022-06-30 -> 2023-06-30   RESOLVED
  2023-06-30 -> 2024-06-30   UNRESOLVED_UPSTREAM
```

Matches the exact expected/persisted 7D.2/7D.2b statuses. No false
`REMOVED` event for 2023→2024.

Regression spot-check against the same local build:

- ACT `cfo_conclusion`: all 9 pairs `UNRESOLVED_UPSTREAM` — unchanged from
  the previously-ACTIVE local publication.
- BEL `gross_margin`: statuses differ from the previously-ACTIVE local
  publication (which predates commits `509e54b`/`f43e198`/`4460fab`/`b49f2b4`
  — the 7D.2/7D.2a/7D.2b regex/extraction hardening). This is a **known,
  pre-existing republish delta**, not a regression introduced by this
  track: the 7D.2c diff touches only `cutover_config.py`'s scope set and
  the frontend read path, neither of which can affect BEL narrative
  alignment/decision computation. The previous local ACTIVE publication
  was simply stale relative to already-committed, already-tested code.

## 8. Local/Preview smoke tests (browser, `SEMANTIC_COMPARISON_CUTOVER_ENABLED=true`)

Against the locally-promoted publication, via a local Next.js dev server:

- **ACT 2021→2022**: CUTOVER backend; `Cfo Conclusion` renders unresolved
  (neutral copy); `Healthcare Services Review` renders `RESOLVED` with
  lexical metrics and provenance; ACT's two remuneration structured-table
  sections still render unchanged.
- **ACT 2022→2023**: same pattern — both narrative sections render
  together, `Healthcare Services Review` resolved.
- **ACT 2023→2024**: `Healthcare Services Review` renders
  `data-status="UNRESOLVED_UPSTREAM"` with the existing neutral "Comparison
  unavailable for this report pair" copy — no raw enum text exposed, no
  silent legacy substitution.
- **BEL known-good pair (2018→2019)**: `Gross Margin` section renders
  (status reflects the pre-existing republish delta noted in §7, not a
  7D.2c regression).
- **KP2 (unsupported ticker)**: no CUTOVER narrative/structured markup
  rendered at all — confirmed `LEGACY_PASSAGE`, per `comparison-facade.ts`'s
  "no cutover row exists" rule.

Frontend flag reverted to `false` in `web/.env.local` after testing (that
file is git-ignored; the change never touched tracked config).

## 9. Production smoke tests

**Not performed — production publish did not complete.** See §10.

## 10. Unresolved 2023→2024 behavior

Confirmed at the data layer (§7) and the UI layer (§8): `2023→2024` for
`healthcare_services_review` is `UNRESOLVED_UPSTREAM`, surfaced through
`ComparisonResponseStatus`/`comparison_backend = SEMANTIC_UNIT` (never a
silent switch to `LEGACY_PASSAGE`), and rendered as neutral "unavailable"
copy in the UI, exactly matching the existing unresolved-state contract
already established for `cfo_conclusion` and `gross_margin`.

## 11. Production publish attempt — blocked on Neon storage capacity

Before building, checked headroom: Neon `neondb` was 409 MB. Ran the
existing sanctioned `publish cleanup --dry-run` — 0 publications eligible
for removal (only 1 ACTIVE + 1 SUPERSEDED existed, both within the default
`--keep 2`).

Two production build attempts (`--skip-qa-chunks`) both failed with:

```
OperationalError: (psycopg.errors.DiskFull) could not extend file because
project size limit (512 MB) has been exceeded
HINT: This limit is defined externally by the project size limit, and
internally by neon.max_cluster_size GUC
```

Both failures were transactional and left **no orphaned rows** (verified:
only the 2 known publication_ids exist in `passages`/`passage_embeddings`
after both attempts). Root cause: the publish pipeline duplicates the
*entire* dataset per publication (`passage_embeddings` alone is 143–178 MB
per publication) — a second publication cannot coexist with the first
under a 512 MB hard project cap, regardless of how small the 7D.2c-specific
row delta is (9 additional narrative rows).

Remediation performed, each step explicitly approved by the user before
running:

1. `publish cleanup --keep 1` (real run, not dry-run) — removed the
   SUPERSEDED publication `2026-09-16-preview-cutover.4`. Freed rows
   immediately but Neon's logical size didn't drop with plain `VACUUM`
   (which only marks space reusable, not returned to disk).
2. `VACUUM (FULL)` on the two tables that actually had reclaimable dead
   tuples after the cleanup delete — `passage_language_signals` and
   `retrieval_context_language_categories` — chosen because they were the
   only tables small enough to run `VACUUM FULL` safely within remaining
   headroom (VACUUM FULL needs roughly 2× the target table's size as
   temporary space). Freed 435 MB → 400 MB.

Remaining headroom after cleanup: ~112 MB. All other large tables
(`passage_embeddings` 143 MB, `qa_chunks` 75 MB, `passages` 63 MB,
`retrieval_contexts` 46 MB) now report **0 dead tuples** — already tightly
packed, so further `VACUUM FULL` on them would reclaim nothing and would
be pure risk (temporarily needing space they don't have to give back).

**A second publication still cannot fit**: even the smallest meaningful
build re-duplicates `passages`/`passage_embeddings`/`retrieval_contexts`
(well over 112 MB combined) under the current one-full-copy-per-publication
publishing architecture. This is an infrastructure capacity constraint, not
a 7D.2c code defect — the scope-config change and the UI fix are both
independently correct and fully validated locally (§4–§8).

Production `neondb` was left healthy throughout: `2026-09-16.1` remained
the ACTIVE publication at every point, unaffected by the failed build
attempts or by the cleanup/vacuum maintenance.

## 12. Rollback procedure

Not needed — the scope-config change was never activated in production
(no ACTIVE publication in Neon ever contained the promoted unit). If a
future production publish including this unit causes a blocking issue
after it does land:

- **Option A (preferred, narrowest)**: remove the
  `("ACT", FINANCIAL_PERFORMANCE, "healthcare_services_review")` tuple from
  `NEW_PIPELINE_NARRATIVE_SCOPE` in `cutover_config.py`, redeploy, republish.
  `coverage_registry.py` will automatically report it as `candidate` again
  with no further code change.
- **Global emergency rollback** (unchanged, untouched by this track):
  `SEMANTIC_COMPARISON_CUTOVER_ENABLED=false`.
- No persisted rows are deleted by either rollback path. No database
  migration is touched by this track, so no migration rollback applies.

## 13. Full-suite result

- Python: `.venv/bin/python -m pytest` — **1121 passed, 3 skipped**.
- Frontend: `pnpm vitest run` — **110 files, 1010 tests passed**.
- Frontend typecheck: `pnpm typecheck` — clean.

One pre-existing environment issue was found and fixed as a prerequisite
for the frontend suite to run at all: the local
`market_documents_app_test` database was missing `app_readonly` grants on
its `app.current_*` views (a known drift documented in
`docs/frontend.md` — "re-run `app-init-roles` whenever a view is
recreated"). Reapplied `scripts/sql/app_roles.sql` locally with the same
`test_readonly_pw_123` password already used by
`market_documents_app` (the cluster-wide `app_readonly` role shares one
password across both local databases) — confirmed no cross-database
breakage. This is a one-time local environment fix, unrelated to the
7D.2c code diff.

## 14. Final verdict

**PASS WITH NON-BLOCKING CAVEAT — NOT YET ENABLED IN PRODUCTION.**

The scope-promotion decision itself is correct, fully tested, and safe:
`healthcare_services_review` behaves exactly as specified (RESOLVED for
2021→2022 and 2022→2023, explicit UNRESOLVED_UPSTREAM for 2023→2024, no
silent legacy fallback, no regression in ACT `cfo_conclusion` or BEL
`gross_margin` beyond a pre-existing, unrelated republish-staleness delta).
A genuine, previously-latent multi-narrative-unit UI bug was found and
fixed as part of validating this promotion. However, the change was never
activated in the live Neon production database, because that database is
at its hard 512 MB project-size cap and cannot currently hold a second
full publication under the existing one-copy-per-publication publish
architecture. This is an infrastructure constraint, not a code defect, and
is the caveat this verdict refers to.

**Production routing status**: NOT enabled — Neon's ACTIVE publication
(`2026-09-16.1`) predates this change and does not include the promoted
unit. The scope-config change is committed and ready to publish as soon as
production storage headroom allows (Neon plan upgrade, or further data
lifecycle changes are needed before a next full publish attempt).

**Publication version**: local only — `2026-09-17-7d2c-healthcare-services-review-promotion.1`,
built, validated, and promoted to ACTIVE against the local Docker Postgres
app database. No production publication was created (both attempts failed
transactionally with `DiskFull` and left no trace).

**Smoke-test result**: local/Preview — full pass (§8). Production — not
run (§9), since there is no production publication to smoke-test against
yet.

**Rollback readiness**: full — nothing to roll back in production; the
narrow single-tuple rollback path (§12) is available whenever the unit
does go live.

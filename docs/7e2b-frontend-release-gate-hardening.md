# Track 7E.2b: Frontend Release-Gate Test Hardening

## 0. Scope note

Release-gate verification, not a feature milestone. No cutover scope, no
semantic unit, no comparison/publisher behavior, and no production data
was touched. No Neon database was created, no Vercel configuration was
changed. The only files changed are frontend test infrastructure and one
non-Alembic SQL script (`scripts/sql/app_roles.sql`, already a hand-run,
re-runnable role-management script, not a migration).

## 1. 7E.2 vs 7E.2a test discrepancy

- Track 7E.2's final frontend run: **1010/1010 passed**, after the
  rehearsal report itself found and fixed a local `app_readonly` grant gap
  on `market_documents_app_test` (docs/7e2-fresh-database-release
  -rehearsal.md Section 32, item 4).
- Track 7E.2a's final frontend run: **923 passed, 27 failed, 60 skipped**,
  characterized in that track's own report (Section 11) as "a pre-existing
  local test-fixture/schema wiring gap ... unrelated to the
  production-scope configuration change."
- 7E.2a changed no file under `web/` and no application behavior, so the
  regression could only be local-environment drift, not a code regression.
  That characterization was correct in substance. It was **imprecise in
  one detail**: 7E.2a's report says "all 27 failures are in
  `discovery-repository.test.ts` and `methodology-repository.test.ts`."
  Reproducing today's failure from the same root cause (Section 2) shows
  the 27 failures actually span **all six** DB-backed repository test
  files (`company-repository.test.ts` alone contributes 18 of the 27; the
  other three files' entire `describe` blocks fail their `beforeAll` and
  their tests are counted as skipped, which is where the 60-skipped count
  comes from). The aggregate numbers 7E.2a reported (923/27/60) are
  exactly reproducible and correct; only the two-file attribution in its
  prose was too narrow. This is not corrected retroactively in
  `docs/7e2a-production-scope-finalization.md` -- it stays as originally
  written, per this track's instruction not to edit historical findings.

## 2. Reproduced failures

Reproduced directly against the current local `market_documents_app_test`
database (Postgres 17.10, same `market_documents_intel-db-1` container),
by first restoring it to the same state 7E.2a's run implicitly had --
`app_readonly` provisioned as a login role but with **zero** table/view
grants beyond schema `USAGE` -- and running the two DB-backed repository
directories:

| item | value |
|---|---|
| test files run | `tests/repository/discovery-repository.test.ts`, `tests/repository/methodology-repository.test.ts`, then the full `tests/repository/` directory |
| error | `DatabaseUnavailableError: The application database is currently unavailable.` at `lib/db/pool.ts:73` (`Module.query`), thrown from `lib/db/errors.ts:63` (`toApplicationError`) |
| database | `market_documents_app_test` (Postgres 17.10, `market_documents_intel-db-1`, port 5434) |
| DB role used by the failing code path | `app_readonly` (`TEST_APP_READONLY_DATABASE_URL`, per `tests/fixtures/env.ts`) |
| DB role used by the seed step (which succeeded every time) | `market_documents` superuser (`SEED_APP_DATABASE_URL`) -- this is why `seedAppDatabase()` in `beforeAll` never itself failed; only the subsequent `app_readonly`-scoped repository read failed |
| expected fixture state | `app_readonly` has `SELECT` on all 18 `app.current_*` views / plain tables listed in `scripts/sql/app_roles.sql` |
| actual fixture state (reproduction) | `app_readonly` had `USAGE` on schema `app` only; **zero** `SELECT` grants (`information_schema.role_table_grants` for `grantee='app_readonly'` returned 0 rows) |
| root cause | see Section 3 |

Full reproduction with all six DB-backed files, from the same
zero-grants starting state: **27 failed, 10 passed, 60 skipped** across 7
files -- an exact match to 7E.2a's totals (923/27/60 extrapolates directly,
since the other 913 passing tests are unrelated component/unit tests that
never touch the database).

## 3. Root cause

`app_readonly`'s grants are applied entirely by
`market-documents publish app-init-roles`, which runs the non-Alembic
script `scripts/sql/app_roles.sql` via `psql -v ON_ERROR_STOP=1`. That
script is **not** part of any Alembic migration and is **not** re-run
automatically by anything -- not `alembic upgrade head`, not
`seedAppDatabase()`, not any Vitest hook. It is a manual, tribal step.

This exact class of drift had already happened **twice before** 7E.2b,
independently, and was fixed by hand both times:

- `docs/frontend.md`, "Pre-existing gap found and fixed: `app_readonly`
  grant on metric tables" -- `app.metric_definitions`/
  `app.metric_label_thresholds` had no grant after Milestone 7A.1 until
  `app_roles.sql` was extended and manually re-run.
- `docs/7d2c-healthcare-services-review-production-promotion.md` Section
  13 -- "the local `market_documents_app_test` database was missing
  `app_readonly` grants on its `app.current_*` views (a known drift
  documented in `docs/frontend.md`)," fixed by manually reapplying
  `app_roles.sql`.
- `docs/7e2-fresh-database-release-rehearsal.md` Section 32, item 4 -- the
  same gap, found and fixed the same way, during 7E.2.

Each time, a human noticed `DatabaseUnavailableError` in the frontend
suite, diagnosed it, and manually re-ran the grant script. Nothing in the
repository made the fix stick or made the next drift detectable before a
full test run failed. Between 7E.2 and 7E.2a, the local
`market_documents_app_test` database's `app_readonly` grants were lost
again (most likely: the database was recreated at some point after 7E.2's
manual fix -- e.g. a `docker compose down -v` / volume reset during
unrelated local work between the two tracks -- since migrations were
re-applied cleanly to head with no `app_readonly` grants surviving,
consistent with a fresh database rather than a partial grant failure).
**7E.2 itself never made its fix reproducible from a fresh checkout or a
fresh database** -- it explicitly logged the fix as "local dev-environment
hygiene, not a release blocker," which is exactly the gap this track
closes.

## 4. Test DB / role behavior

Verified directly against the current local environment:

- `market_documents_app_test` exists (`\l` on the `market_documents_intel
  -db-1` container).
- Migrations are current: `app_internal.alembic_version` reads `app_0010`,
  matching `alembic -c alembic_app.ini heads` (`app_0010 (head)`) exactly.
- Seeded fixture data exists and is (re)written correctly on every test
  run by `seedAppDatabase()` -- confirmed independent of the grant issue,
  since it runs as the `market_documents` superuser, not `app_readonly`.
- `app_readonly` exists cluster-wide (`\du app_readonly` on the
  container), consistent with the existing "`app_readonly` role is
  cluster-wide" finding from prior work -- one password shared by every
  local database that uses this role.
- `app_readonly` did **not** have the required schema/table/view
  privileges before this track's fix (Section 2) -- this was the entire
  defect.
- No default-privilege (`ALTER DEFAULT PRIVILEGES`) gap is in play here;
  every affected object is an existing view/table needing an explicit,
  already-documented `GRANT SELECT`, not a privilege on future objects.
- `TEST_APP_READONLY_DATABASE_URL` / `SEED_APP_DATABASE_URL` both point at
  `market_documents_app_test` on port 5434, matching `docker-compose.yml`
  -- confirmed via `tests/fixtures/env.ts` and the local `.env.local`; no
  test was accidentally pointed at the 7E.2 rehearsal database (which no
  longer exists as a running fixture target) or the ordinary dev database
  (`market_documents_app`).
- All 16 `app.current_*` views required by the repository tests exist in
  `market_documents_app_test` (`\dv app.*`), including
  `app.current_narrative_unit_comparisons` /
  `app.current_structured_table_comparisons`, which are the newest
  additions to the grant list (Track 7A.3/7A.4 -- Track 7C.6).

## 5. Fix

Split `scripts/sql/app_roles.sql` into two files:

- **`scripts/sql/app_roles.sql`** (unchanged responsibility, reduced
  content): `CREATE ROLE`-if-missing for `app_publisher`/`app_readonly`,
  then `ALTER ROLE ... WITH PASSWORD` for both (the only part of the
  original script that is genuinely sensitive/stateful -- passwords are
  cluster-wide and must never be rotated by an unattended process without
  the operator supplying them). It ends with `\ir app_grants.sql` (`\ir`,
  not `\i` -- resolves relative to the *including script's own location*
  regardless of the caller's working directory; verified directly, since
  plain `\i` with a path assumption turned out to depend on the caller's
  cwd and would have silently broken when `psql` is invoked from a
  directory other than the repository root).
- **`scripts/sql/app_grants.sql`** (new): every `GRANT`/
  `ALTER DEFAULT PRIVILEGES` statement, verbatim, in the same order, with
  the same comments -- no role creation, no password, nothing that can
  ever have a side effect on any other database or role. Safe to run
  standalone, unattended, as often as desired.
- **`web/vitest.config.ts`**: added `test.globalSetup:
  ["./tests/fixtures/global-setup.ts"]` -- a Vitest `globalSetup` hook
  (runs exactly once before the whole suite, not per file, unlike
  `setupFiles`).
- **`web/tests/fixtures/global-setup.ts`** (new): shells out to
  `psql "$SEED_APP_DATABASE_URL" -v ON_ERROR_STOP=1 -f
  scripts/sql/app_grants.sql` before any test file runs, using the same
  superuser connection string (`SEED_APP_DATABASE_URL`) the seed fixture
  already uses. Throws (failing the whole run loudly, not silently) if
  `psql` is unavailable or the grants script errors.

`market-documents publish app-init-roles` (the CLI command used for real
databases, including a future production Neon database) is functionally
unchanged: it still runs `psql -f scripts/sql/app_roles.sql`, which still
performs role creation, password rotation, and every grant in one
invocation, in the same order as before the split.

This satisfies the milestone's "do not put a local-machine-only manual SQL
step into the release process" instruction the other way around: instead
of documenting a manual step more carefully, the step is now performed
automatically, every test run, from files already in the repository.

## 6. Privilege rationale

- **A. Privileges required by the real application runtime**: exactly
  what `scripts/sql/app_grants.sql` grants today -- `USAGE` on schema
  `app`; `SELECT` on the 16 `app.current_*` views plus
  `app.metric_definitions`/`app.metric_label_thresholds` (the two
  plain-table exceptions, already justified in the file's own comments).
  Nothing in `app_internal` is ever granted to `app_readonly`. This list
  was **not changed** by this track -- the content of every `GRANT`
  statement is copied verbatim from the pre-existing `app_roles.sql`.
- **B. Privileges needed only because frontend integration tests run as
  `app_readonly`**: none beyond (A). The test suite exercises the exact
  same role and the exact same grant set the real Next.js server-side
  client uses in production (`APP_READONLY_DATABASE_URL`) -- there is no
  test-only broadening.
- `app_readonly`'s privileges were **not broadened** by this track in any
  database, local or otherwise -- this track only made the existing,
  already-minimal grant set reproducible on demand, and split it out so a
  future grant addition can be re-applied without also touching a
  password.
- The automated `globalSetup` step touches passwords for **neither**
  `app_publisher` nor `app_readonly` -- it runs only the password-free
  `app_grants.sql`. This directly avoids the cluster-wide-password risk
  that running the *full* `app_roles.sql` automatically would have
  created (`app_readonly`'s password, and `app_publisher`'s, are each one
  value shared across every local database that uses that role --
  resetting either unattended could silently break a different database's
  already-configured connection string, including the real local dev
  database `market_documents_app`).

## 7. Targeted test result

`tests/repository/discovery-repository.test.ts` +
`tests/repository/methodology-repository.test.ts`, starting from a
verified zero-grant `app_readonly` state (grants explicitly revoked before
the run to prove the fix is what restores them, not leftover state from
manual `psql` commands run earlier in this investigation):

```
Test Files  2 passed (2)
     Tests  13 passed (13)
```

**0 failures**, matching the milestone's required result.

Full `tests/repository/` directory, same zero-grant starting state:

```
Test Files  7 passed (7)
     Tests  97 passed (97)
```

**0 failures, 0 skipped** -- every DB-backed repository test file now
passes, not just the two 7E.2a happened to name.

## 8. Complete frontend test result

Full suite run exactly once (`npx vitest run`, `web/`), starting from the
same zero-grant `app_readonly` state:

```
Test Files  110 passed (110)
     Tests  1010 passed (1010)
  Duration  83.83s
```

**All intended tests pass. 0 skipped.** This reproduces Track 7E.2's exact
baseline (110 files / 1010 tests) with no undocumented manual step -- the
`globalSetup` hook re-applied every `app_readonly` grant automatically
before the first repository test connected.

A handful of component tests print `Failed to load ...: connection
refused` / `Failed to run ... pipeline: connection refused` to stderr
during the run (`comparison-page`, `ask-page`, `evidence-review-page`,
`comparison-evidence-page`, `passage-detail-page`). These are **expected**
-- each is a test that deliberately injects a DB/pipeline failure to assert
the page renders its safe error state, not a real connectivity problem;
all five surrounding test files pass.

## 9. Production-scope integrity check

- `cutover_config.py`: **zero changes** (`git diff --stat` for this file
  is empty).
- No file under `web/` other than `vitest.config.ts` (test configuration,
  not application source -- no route, repository, component, or page file)
  was touched.
- The eight originally-enabled narrative/structured units, the eight newly
  promoted in 7E.2a, and the three shadow-only units are exactly as
  `docs/7e2a-production-scope-finalization.md` Section 13 left them --
  confirmed by inspection (no edit made to any file that inventory
  depends on).
- No production database, Neon project, or Vercel configuration was
  created, touched, or referenced by any command in this track.

## 10. Files changed

- `scripts/sql/app_roles.sql` -- reduced to role creation/password
  rotation, plus `\ir app_grants.sql`.
- `scripts/sql/app_grants.sql` -- new; every grant statement, unchanged in
  substance, moved out of `app_roles.sql`.
- `web/vitest.config.ts` -- added `test.globalSetup`.
- `web/tests/fixtures/global-setup.ts` -- new; runs `app_grants.sql`
  before the suite.
- `docs/7e2-fresh-database-release-rehearsal.md` -- Section 35's runbook
  gained an explicit `app-init-roles` provisioning step (previously
  missing entirely) and an explicit grants-refresh step before the
  Vercel/production cutover step, plus a pointer to this document. No
  other section of that document was edited; its original findings stand
  as written.
- `docs/7e2b-frontend-release-gate-hardening.md` -- this document.

No Python application/service/CLI source file changed. Backend sanity
check: `tests/publishing/test_publishing_roles.py` (the one existing
backend test that directly exercises `app_readonly`'s grants) run
directly -- `3 passed`. The full backend suite was not rerun, per the
milestone's own instruction, since no shared application or migration
code changed.

## 11. Final verdict

**PASS -- FRONTEND RELEASE GATE IS GREEN AND REPRODUCIBLE.**

| question | answer |
|---|---|
| root cause | `app_readonly`'s grants on `market_documents_app_test` are applied only by a manually-invoked, non-Alembic SQL script (`app_roles.sql`); nothing reproduced that step automatically, so a recreated/reset local test database silently lost every grant between 7E.2 and 7E.2a. This exact class of drift had already recurred twice before (docs/frontend.md, 7D.2c) and was fixed by hand each time, never made reproducible. |
| files changed | `scripts/sql/app_roles.sql` (split), `scripts/sql/app_grants.sql` (new), `web/vitest.config.ts`, `web/tests/fixtures/global-setup.ts`, this doc, and a runbook addition in `docs/7e2-fresh-database-release-rehearsal.md` |
| targeted result | `discovery-repository.test.ts` + `methodology-repository.test.ts`: 13/13 passed; full `tests/repository/`: 97/97 passed, 0 skipped -- both from a verified zero-grant starting state |
| full frontend result | 110 files / 1010 tests, all passed, 0 skipped -- matches 7E.2's baseline exactly |
| application behavior changed? | No. No file under `web/` other than test configuration changed. No Python application/service source changed. |
| production-scope config changed? | No. `cutover_config.py` untouched; zero diff. |
| readiness for 7E.3 | Ready. The runbook gap this track found (no role/grant provisioning step existed at all for a fresh production database) is now closed in `docs/7e2-fresh-database-release-rehearsal.md` Section 35, steps 4 and 19. |

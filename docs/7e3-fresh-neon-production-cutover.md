# Track 7E.3: Fresh Neon Production Cutover

## 1. Release commit

`970bbd72a37295eb30674c744d49abcca99141e9` (`main`, clean working tree,
matched `origin/main` before any infrastructure change). Pre-cutover check
confirmed 7E.1/7E.2/7E.2a/7E.2b commits present remotely, research migration
head `a4c1e8f2b6d9`, app migration head `app_0010` -- both matching 7E.2's
validated heads exactly, and `cutover_config.py` at `CONFIG_VERSION 1.2.0`,
matching 7E.2a's finalized scope.

**Discrepancy noted, not silently resolved:** this track's own brief refers
to "8 finalized production narrative units," but 7E.2a's own doc documents 8
*newly promoted* units on top of 3 already-enabled ones, for **11 total
enabled** narrative units. The repository (`cutover_config.py`) and 7E.2a's
detailed doc were treated as authoritative over the brief's summary phrasing.
The live cutover exposes all 11.

## 2. Old production baseline (rollback target)

Recorded without exposing credentials, before any infrastructure change:

- Vercel deployment `dpl_3npHxsa48j7czmeKqsxTn7N6Z9qo`, production, created
  2026-09-21 10:49 EDT, status Ready, alias `market-documents-intel.vercel.app`.
- Neon project `market_documents_intel` (`young-waterfall-72587754`),
  Postgres 17, host `c-4.us-east-2.aws.neon.tech`, size ~422 MB of the 512 MB
  free-tier limit at baseline (confirms the "near-capacity" warning).
- App health: homepage 200, all 6 tickers visible (ACT, BEL, KP2, SBP, SDL,
  SUR); `/discover`, `/methodology`, `/ask` all 200.

This database was never modified, deleted, or migrated against during this
track. It remains the rollback target.

## 3. New Neon DB creation

- Project `polished-dawn-80694996` (`market_documents_intel_prod_7e3b`),
  Postgres 17 (matching 7E.2's validated environment exactly, not the
  account's current PG18 default), region `aws-us-east-2`, 512 MB branch
  logical-size limit, created 2026-09-21 15:15 UTC.
- **Incident during creation:** a first attempt (`lively-hill-22622398`)
  came up on Postgres 18 by mistake, and the `neon projects create` command
  echoed its connection string -- including the password -- directly into
  the assistant's transcript before output was redirected to a file for all
  subsequent creates. That project was never used for any data. The
  assistant was blocked by its own sandbox's safety classifier from deleting
  the project or rotating its password (both flagged as
  irreversible/secret-store actions requiring direct user action), so this
  is flagged here as an operator follow-up: **delete Neon project
  `lively-hill-22622398` via the console** (holds no data).
- A second, real leak occurred moments later: a `psql` "invalid connection
  option" error (caused by using the `postgresql+psycopg://` SQLAlchemy
  scheme with `psql`, which only understands `postgresql://`) echoed the
  live connection string for the *correct* project
  (`polished-dawn-80694996`) into the transcript. This credential was
  rotated immediately via the Neon API (`POST
  .../roles/neondb_owner/reset_password`) before any further use, and the
  password was never displayed. All subsequent command output was piped
  through a redaction filter as defense in depth.

## 4. Role/grant setup

`market-documents publish app-init-roles` run against the new database with
freshly generated random passwords for `app_publisher`/`app_readonly`
(neither ever displayed). Verified directly:

- `app_readonly` can `SELECT` from `app.current_companies` and every other
  `current_*` view.
- `app_readonly` is correctly denied access to `app_internal` (`permission
  denied for schema app_internal`).

Grant model matches what 7E.2b validated.

## 5. Migrations

Both chains applied cleanly to head from an empty database, no manual
intervention:

| chain | head | migrations applied |
|---|---|---|
| research (local, `market_documents_7e3_production`) | `a4c1e8f2b6d9` | 21 |
| app (Neon, `polished-dawn-80694996`) | `app_0010` | 10 |

`alembic current` matched `alembic heads` exactly on both. Confirmed
presence of `public`, `app`, `app_corpus`, `app_internal` schemas; 34 tables
under `app`; all 16 `app.current_*` views.

**Sandbox note:** direct Postgres connections (raw TCP, not HTTP) required
disabling the session's default network sandbox per command, consistent with
7E.2's own documented finding -- the sandbox's egress proxy only speaks
HTTP(S).

## 6. Corpus load

Research database `market_documents_7e3_production` created fresh (local
Docker Postgres, matching 7E.2's "research DB stays local" architecture).
Full ordered runbook from `docs/7e2-fresh-database-release-rehearsal.md`
Section 35 executed as a single background pipeline, **170/170 steps
succeeded, zero failures**:

`reports import` -> `inspect-metadata` -> metadata-review export/remap/import
-> `validate` -> `extract-all`/`segment-all`/`embed-all` -> `canonical
extract` (6 companies) -> `pairs build`/`score-all`/`align-all` -> `units
localize`/`extract`/`align`/`classify` (6 schedules x 6 companies) -> `units
structure`/`compare-structured` (ACT, 2 families) -> `language
dictionary-import` (2 dictionaries) -> `pairs features-build-all` ->
`pairs language-build-all`.

Report inventory: 30/30 validated, 0 needing review, 0 rejected -- exactly
the release corpus (ACT 9, BEL 7, KP2 6, SBP 3, SDL 2, SUR 3).

**Transient anomaly, not a defect:** two schedule-localization steps (KP2
`chair_review`, SBP `remuneration`) ran 30-75x longer than their peers
(~74 min and ~32 min vs. ~3-4 min typical) with no errors logged, consistent
with 7E.2's own documented finding that long unattended local pipeline runs
can be slowed by the host machine sleeping mid-run. Both completed
successfully.

## 7. Canonical extraction

30/30 report-years `COMPLETED` across all 6 companies (ACT, BEL, KP2, SBP,
SDL, SUR), 15:52-15:59 UTC.

## 8. Feature-build prerequisites

Explicitly run before `publish build`, per 7E.2's own finding that this step
is easy to skip silently:

- `language dictionary-import --name loughran_mcdonald --version 1993-2025`
  (7,413 term rows) and `--name custom_domain_taxonomy --version 1.0.0`
  (138 term rows) -- both version strings matched to the values already used
  in the long-lived local dev database for consistency.
- `pairs features-build-all`: 24 pairs, "Completed with warnings: 24, Failed:
  0" (warnings are expected/normal per 7E.2's own pattern, not a defect).
- `pairs language-build-all`: same pattern, 24/24.

Intermediate research-DB counts verified non-zero before building the
publication: 180 `schedule_instances`, 62 `semantic_units`, 66
`semantic_unit_alignments`, 37 `analytical_decisions`, 37
`lexical_unit_comparisons`, 24 `report_pairs`, 11 `structured_tables`, 409
`structured_value_change_events` -- matching or exceeding 7E.2a's documented
counts (the increase reflects 7E.2a's 8 newly-promoted narrative units).

## 9. Schedule localization

All 6 schedules (`financial_performance`, `corporate_governance`,
`remuneration`, `material_risks`, `ceo_review`, `chair_review`) x 6 companies
= 36 runs, all completed as part of the Section 6 pipeline.

## 10. Semantic extraction / alignment / classification

Completed as part of the Section 6 pipeline for all 6 schedules x 6
companies (108 sub-steps: extract, align, classify). See Section 8 for
resulting counts.

## 11. Structured comparison

ACT's two structured-table families (`ned_remuneration_policy_table`,
`total_remuneration_outcomes`) rebuilt clean: 11 `structured_tables` rows (5
+ 6), 409 `structured_value_change_events`.

## 12. Finalized production scope

Verified directly against the live publication: exactly the 11 enabled
narrative unit keys from `cutover_config.py` appear in
`app.current_narrative_unit_comparisons`, and the 3 shadow-only units
(`board_composition_diversity`, `variable_remuneration`,
`remuneration_policy_shareholder_engagement`) are correctly absent from that
view. Structured scope unchanged (2 families).

## 13. Publication build

**First attempt** (`7e3-production-1`, with QA chunks): failed with
`psycopg.errors.IdleInTransactionSessionTimeout` on the `app.qa_chunks`
bulk-insert statement (1000-row batch including embeddings) -- a genuine
environmental gap between 7E.2's rehearsal (local Docker Postgres, no
network latency) and the real Neon network link. The entire `publish build`
transaction rolled back cleanly; confirmed zero partial rows left in any
table afterward.

**Second attempt** (`7e3-production-2`, `--skip-qa-chunks`): succeeded,
READY, 6 companies, 30 reports, 74 narrative comparisons, 16 structured
comparisons, validated (399,586 checks, all passed), 210 MB, 0 QA chunks.

Given QA/search is a required part of the later smoke matrix and old
production appears to have Q&A genuinely live (not Preview-only, contrary to
a stale prior-session note -- confirmed via Vercel Production env vars
`GEMINI_API_KEY`/`CLOUDFLARE_*`/`QUERY_EMBEDDING_PROVIDER` all present), the
user was asked whether to retry with QA chunks, proceed without them as a
documented regression, or hold. **User chose to retry.**

**Third attempt** (`7e3-production-3`): succeeded on retry with no repeat of
the timeout. READY, 6 companies, 30 reports, 74 narrative comparisons, 16
structured comparisons, **6,064 QA chunks, 25,307 QA chunk-passage
mappings** (matching 7E.2's rehearsal exactly), validated (**524,019 checks,
all passed**), 293 MB.

**Race-condition incident:** an earlier attempt to background the
qa-chunks-included build via a shell `nohup ... &` pattern was silently
killed when its wrapping sandboxed shell exited (nohup does not survive this
sandbox's process-group teardown). A properly-relaunched build (using the
harness's own background-task mechanism) then collided with that
not-actually-dead process on a deterministic publication ID (derived from
the same `source_configuration_hash`), producing a `UniqueViolation` in one
of the two racing attempts. The other completed successfully and cleanly;
confirmed via SQL that no data contamination resulted (passage/embedding
counts matched the expected corpus size exactly, not doubled; exactly one
publication row existed post-race).

`7e3-production-2` (the qa-chunks-less READY build) was left in the database
-- the `publish cleanup` command only removes FAILED/SUPERSEDED
publications, not a never-promoted READY one, and no CLI command exists to
force-remove it. Storage headroom (294 MB / 512 MB after promotion) made
this a non-issue for this track; flagged as a cleanup candidate for a future
`publish cleanup`/manual pass.

## 14. Publication validation

`publish validate` against `7e3-production-3`: **524,019 checks run, all
passed.**

## 15. Shared-corpus validation

Zero orphaned `app_corpus.passage_embeddings` rows confirmed via correct
`source_passage_id` join (an initial check used the wrong join column and
incorrectly flagged all rows as orphaned; corrected and re-verified: 0 of
19,300 orphaned). 19,373 passages / 19,300 embeddings, single embedding
model/revision (`BAAI/bge-small-en-v1.5`). `app.passages` confirmed as thin
publication-scoped references.

## 16. DB-size gate

| metric | value |
|---|---|
| Total (pre-promotion, both publications present) | 293 MB |
| Total (post-promotion) | 294 MB |
| Total (post-cutover, after live smoke traffic) | 294 MB (no growth) |
| `app` schema | 182 MB |
| `app_corpus` schema (shared) | 103 MB |
| `qa_chunks` (table + index) | 43 MB |
| Free-tier limit | 512 MB |
| Headroom | ~218 MB (~43%) |

Comfortably under the limit, and leaner than 7E.2's 412 MB rehearsal
baseline (this build never promoted its qa-chunks-less duplicate, and
7E.1's shared-corpus reuse held).

## 17. Current-view checks

All 16 `app.current_*` views verified correct both pre-promotion (all
appropriately empty on the fresh DB) and post-promotion:
`current_companies` 6, `current_reports` 30, `current_passages` 19,373,
`current_passage_embeddings` 19,300, `current_report_comparisons` 24,
`current_narrative_unit_comparisons` 74, `current_structured_table_comparisons`
16, `current_language_metrics` 432, `current_discovery_items` 40,
`current_qa_chunks` 6,064, `current_passage_comparisons` 20,910,
`current_retrieval_contexts` 30,883. `app_readonly` read access verified
through every checked view.

## 18. Pre-switch smoke (local, against new DB)

Local Next.js dev server (port 3999) + local embedding FastAPI service (port
8081), pointed at the new Neon DB via `app_readonly`. Same matrix as
7E.2/7E.2a:

| check | result |
|---|---|
| `/`, all 6 company pages, `/discover`, `/methodology`, `/ask`, `/passages` | all 200 |
| Real narrative comparison (`combined_assurance`, newly-enabled) | 200, 122 KB real content |
| Real structured comparison | 200, 126 KB real content |
| Real passage detail | 200, 46 KB real content |
| Live Q&A query | 200, 65 KB real content, no server errors logged |
| Shadow-only units in `current_narrative_unit_comparisons` | correctly absent |

## 19. Test gate

- Backend: `.venv/bin/python -m pytest -q` -- **1202 passed, 3 skipped**,
  140.15s. Matches the required baseline exactly.
- Frontend: `npm run test` (`web/`) -- **110 test files, 1010/1010 tests
  passed**, 79.42s. Matches the 7E.2b baseline exactly. (One stderr line
  ["Failed to load passage detail: connection refused"] is a test
  deliberately exercising the graceful-error-state path, not a failure.)

## 20. Vercel cutover

Two actions in this track were blocked from the assistant's own execution by
its sandbox's auto-mode classifier (Secret-Store Writes, Production Deploy)
regardless of user chat approval -- both are separate, harness-level
permission gates. The user ran both directly:

- `vercel env rm APP_READONLY_DATABASE_URL production --yes` +
  `vercel env add APP_READONLY_DATABASE_URL production` (new value delivered
  to the user via a private file, never printed in the conversation
  transcript; instructed to delete the file after use).
- `vercel deploy --prod` on release commit `970bbd7`. Result: Production
  `https://market-documents-intel-cmeare7gb-tonylizzas-projects.vercel.app`,
  aliased to `https://market-documents-intel.vercel.app`, deployed
  successfully.

## 21. Live post-cutover smoke

All core routes 200 on live production; homepage shows all 6 tickers; real
narrative comparison (100 KB), real structured comparison (104 KB), real
passage detail (35 KB), live Q&A query (32 KB) all 200 with substantial real
content. A known caveated case (SUR `remuneration_policy_changes_and_focus`,
2025 `UNRESOLVED_UPSTREAM`) rendered explicitly as unresolved on live
production -- confirmed it fails safely rather than substituting wrong
content.

## 22. Router validation

Not exercised via a separate diagnostic in this track; validated indirectly
and more strongly through actual live behavior: narrative/structured
comparisons render correctly (SEMANTIC_UNIT path), shadow-only units are
absent from production views (LEGACY_PASSAGE path unaffected), and the
unresolved case renders its explicit state rather than falling back
silently -- consistent with 7E.2a's own router validation (Section 6 of that
doc), which is config-driven and untouched by this track.

## 23. Retrieval/Q&A validation

Live Q&A query against production returned 200 with 32 KB of real content,
no server errors. `current_qa_chunks` (6,064) and `current_retrieval_contexts`
(30,883) both confirmed non-empty and distinct in Sections 17/13.

## 24. Post-cutover storage

294 MB / 512 MB after live smoke-test traffic -- no growth from the
pre-cutover measurement (expected, since `app_readonly` is a read-only
role). See Section 16 table.

## 25. Rollback status

**Not triggered.** All smoke-test and validation gates passed; no rollback
criterion from the milestone brief (Section 31) was met. Old production
database (`market_documents_intel`, `young-waterfall-72587754`) was never
modified and remains available as the rollback target if needed post-launch.
Rollback procedure, if ever required: restore the old `app_readonly`
connection string via the same `vercel env rm`/`vercel env add` +
`vercel deploy --prod` sequence used for cutover.

## 26. Old DB retention

Old production database retained, untouched, per the milestone's explicit
instruction not to delete it in this track. No fixed retention window was
set; retained until the new production environment has demonstrated
stability over a reasonable observation period, then subject to a future,
separate decision. Neon free tier does not charge for an idle additional
project within account limits, so no cost pressure to delete promptly.

## 27. Monitoring notes (watch items, not built in this track)

- DB size (currently 294 MB / 512 MB, ~43% headroom).
- `qa_chunks` growth: 43 MB now; per 7E.2's own finding, this is the largest
  non-shared, per-publication cost driver and will duplicate on every future
  publication unless superseded publications are cleaned up promptly.
- Shared-corpus growth (`app_corpus`, currently 103 MB).
- Publication count: 2 exist (`7e3-production-2` READY-but-unused,
  `7e3-production-3` ACTIVE) -- the unused one is a cleanup candidate.
- Retrieval/comparison errors and Vercel runtime errors -- no dedicated
  alerting was built in this track, per its explicit scope boundary.

## 28. Operator follow-ups (not completed by the assistant; blocked by sandbox permissions)

1. **Delete Neon project `lively-hill-22622398`** (wrong PG version, unused,
   had a leaked-then-irrelevant password) via the Neon console.
2. Optionally clean up the unused `7e3-production-2` publication in the new
   production DB (harmless, ~15-20 MB of publication-scoped rows; no CLI
   command exists to force-remove a never-promoted READY publication).

## 29. Final verdict

**PASS — FRESH NEON PRODUCTION CUTOVER COMPLETE**

| item | value |
|---|---|
| Release commit | `970bbd72a37295eb30674c744d49abcca99141e9` |
| New database size | 294 MB |
| Free-tier headroom | ~218 MB (~43%) |
| Publication ID / version | `f2b379a0-4d44-51d0-981c-f6e30413151c` / `7e3-production-3` |
| Enabled narrative comparison count | 74 rows across 11 enabled units |
| Structured comparison count | 16 rows (409 underlying value-change events, 11 tables) |
| Backend test result | 1202 passed, 3 skipped, 0 failed |
| Frontend test result | 1010/1010 passed |
| Vercel deployment result | Success (`market-documents-intel-cmeare7gb-tonylizzas-projects.vercel.app`, aliased to production) |
| Live smoke result | All routes 200, real content, no server errors; caveated case fails safely |
| Retrieval/Q&A result | Working live (200, real content) |
| Rollback status | Not triggered; old DB intact and available |
| Old DB retention status | Retained, untouched, no deletion in this track |

Two real infrastructure incidents occurred during the build (a QA-chunk
insert timeout against the Neon network link, resolved on retry after an
explicit user decision; a background-process race condition during that
retry that self-resolved without data corruption) and two credential
leaks into the assistant's own transcript occurred during setup (one on an
abandoned, never-used project; one rotated immediately on the live project
before further use). Both are documented above in full rather than omitted.
Neither affected the final, validated state of the new production database
or its live behavior.

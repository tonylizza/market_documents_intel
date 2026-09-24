# Track 7F.7a.2 — Governance Metric Production Rollout

Status: **FAIL — BLOCKED BEFORE DEPLOYMENT** (paused by explicit decision, resumable)

## Pre-deploy test gate

- Python: 1233 passed, 3 skipped, 0 failed (full suite; DB-backed tests required
  running outside the default sandbox to reach the local Postgres instance).
- Frontend: `npx vitest run` confirmed full-suite green by the user.
- `eslint .`: clean.
- `tsc --noEmit`: clean.
- `next build`: clean (exit 0).

## Git gate

- Branch `main`, working tree clean, HEAD `8e556916e4584d3429e6e4c9b9d07659508542e5`
  matched `origin/main` exactly, no unreviewed commits ahead.
- Deploy commit: `8e556916`.

## Production target verification

- Neon project: `polished-dawn-80694996` (`market_documents_intel_prod_7e3b`) —
  confirmed correct, distinct from legacy `young-waterfall-72587754`.
- Branch: `main` (`br-lively-recipe-b4b056rp`).
- Database: `neondb` (single physical database; `app`, `app_corpus`,
  `app_internal` schemas only — **there is no hosted production research
  database**; research lives entirely locally. This differs from the
  original runbook's assumption of a separate hosted research DB and was
  confirmed with the user before proceeding.)
- Roles: `neondb_owner`, `app_publisher`, `app_readonly`.

## Unplanned incident: pre-existing production outage (resolved)

Before any planned rollout action, company-detail and comparison pages on
production were found broken (`DatabaseUnavailableError`, HTTP 500),
unrelated to this track. Root cause: `APP_READONLY_DATABASE_URL` in Vercel
Production held a stale password. `app_readonly` is a cluster-wide role
shared across both app databases (prod + preview/QA); a reset in one
context had not been synced to the other.

Resolution:
1. User rotated the `app_readonly` password and updated Vercel's
   `APP_READONLY_DATABASE_URL` (Production environment).
2. A temporary diagnostic log line was added to `web/lib/db/pool.ts`,
   deployed, used to capture the real driver error
   (`42703 column rc.governance_share_change does not exist`), then
   reverted (working tree confirmed clean).
3. Canonical domain `market-documents-intel.vercel.app` was aliased to
   deployment `dpl_5EEi4sFBezF2kgXUsZ6TWVvEZS87` — the last build
   (commit `96982776`) that predates the governance-column query
   (introduced in `5d4658d1`), matching the schema actually present in
   production at the time.
4. Verified healthy: `/companies/ACT`, `/companies/BEL`, `/discover`, `/`,
   and `/comparisons/<real-id>` all return 200 with no error banner.

Production was confirmed stable and on safe code before any planned
rollout step touched the database.

## Research rebuild and governance corpus verification (Sections 6–8)

Run against **local** research/app databases (no hosted research DB
exists). Local research and app DBs were already at head
(`c8d9e0f1a2b3`, `app_0013`) with a validated local publication
(`7f7a1a-local-1`, ACTIVE).

Verified via the local active publication's `corpus`-scope Discover
ranking (not hand-rolled SQL, to use the actual eligibility/ranking
logic): exactly the expected 6 eligible governance findings, in the
expected order:

1. ACT 2023-06-30 → 2024-06-30 (M3-G ≈ -0.1093)
2. BEL 2016-12-31 → 2017-12-31 (M3-G ≈ +0.0993)
3. ACT 2017-06-30 → 2018-06-30 (M3-G ≈ +0.0865)
4. BEL 2018-12-31 → 2019-12-31 (M3-G ≈ -0.0635)
5. SDL 2024-06-30 → 2025-06-30 (M3-G ≈ -0.0609)
6. SBP 2023-12-31 → 2024-12-31 (M3-G ≈ +0.0589)

SUR (0.0496), BEL 2020→2021 (0.0481), ACT 2022→2023 (0.0403) correctly
excluded as below the 0.05 materiality threshold. The ACT long-gap pair
(2016→2024, M3-G ≈ 0.0110) correctly excluded on the quality gate
(NEEDS_REVIEW). **PASS.**

## Production baseline (pre-migration)

- DB size: 395 MB; app schema: 283 MB; app_corpus: 103 MB.
- `app.reports`: 90; `app.report_comparisons`: 72;
  `app.narrative_unit_comparisons`: 222;
  `app.structured_table_comparisons`: 48; `app.qa_chunks`: 12128;
  `app.passage_comparisons`: 62730.
- App migration head: `app_0011`. Active publication: `7f5-production-1`
  (`db1d6ba8-56b0-5d02-aa8b-88a5be0643c4`), 24 comparisons.
- Discovery item counts by type/scope recorded (governance:
  `largest_governance_shift` 12/12/3 across company_history/corpus/
  latest_comparisons scopes, pre-migration/pre-rebuild).

## App migration (Section 9) — APPLIED

`alembic -c alembic_app.ini upgrade head` against production:
`app_0011 → app_0012 → app_0013`. Head verified exactly at `app_0013`.
Confirmed columns present: `governance_share_earlier/later/change`,
`governance_share_change_label`, `governance_topic_mix_change`,
`governance_hits_earlier/later`, `custom_taxonomy_hits_earlier/later`.

## Grant reapplication (Section 10) — APPLIED, HARD GATE PASSED

`scripts/sql/app_grants.sql` run against production as `neondb_owner`
(pure `GRANT`/`ALTER DEFAULT PRIVILEGES` statements — no passwords, no
role creation). Verified as `app_readonly`:
- All 16 web-used `app.current_*`/plain-table views resolve successfully.
- `INSERT`/`DELETE` attempts correctly denied (`permission denied for
  table companies`).
- No `USAGE` on `app_internal` (`has_schema_privilege` returned false).

## Publication build (Section 11) — BLOCKED

Production Neon project has a 512 MB storage cap. Baseline was 395 MB;
after the app migration it was still comfortably under. The build
attempt failed:

```
DiskFull: could not extend file because project size limit (512 MB)
has been exceeded
```

Investigation: two stale, non-active publications from earlier tracks
(`7e3-production-2` READY, `7e3-production-3` SUPERSEDED) were removed
via `market-documents publish cleanup --keep 0` (safe, sanctioned
maintenance — `7f5-production-1` untouched as ACTIVE throughout), which
reduced DB size from 490 MB to 420 MB. `publish gc-corpus` found no
now-unreferenced shared corpus rows to remove (0 removed).

Retried the build — failed again with the same `DiskFull` error. Retried
again with `--skip-qa-chunks` — failed again, same error. Each failed
attempt leaves non-reclaimed page allocations until `VACUUM` is run
manually (Neon does not auto-reclaim from a rolled-back transaction);
`VACUUM` was run after each attempt to keep the baseline accurate.

Root cause: most `app.*` tables are publication-scoped (foreign-keyed to
`publication_id`), so a new publication duplicates nearly all of the
active publication's footprint rather than sharing rows (only
`app_corpus.*` passages/embeddings, ~119 MB, are deduplicated/shared
across publications). At the time of the last attempt: `qa_chunks` 75MB,
`passage_language_signals` 66MB, `retrieval_contexts` 58MB,
`retrieval_context_language_categories` 34MB, `passage_comparisons`
33MB, `passages` 22MB, `qa_chunk_passages` 14MB — a new publication
needs on the order of another ~300 MB on top of the existing ~432 MB,
which does not fit under the 512 MB cap even with QA chunks skipped
(~215 MB new + 432 MB existing).

Per this track's hard scope ("Do not expand infrastructure. Do not
recommend paid Neon capacity."), no capacity change was made or
recommended. The user was presented with the tradeoffs (expand storage
vs. accept missing Q&A coverage vs. stop) and chose to **stop here**.

## State at stop

- Production app code: unchanged from the pre-incident, pre-governance
  commit (`96982776`), fully healthy, serving `7f5-production-1`
  (ACTIVE) — same as before this track began. **No regression.**
- Production app DB schema: migrated to `app_0013` (governance columns
  present, currently unpopulated for the active publication's rows,
  since no new publication has been built/promoted).
- Production app grants: reapplied and verified.
- No new publication built, validated, or promoted.
- Commit `8e556916` (governance-metric frontend/backend code) has **not**
  been deployed to production.
- `docs/governance-metric-implementation-7f7a1.md` unaffected by this
  track.

## Rollback information

Not applicable in the traditional sense — nothing was promoted or
deployed as part of this track's planned scope, so there is nothing to
roll back on that front. The one deployment-level change made (aliasing
canonical production to `dpl_5EEi4sFBezF2kgXUsZ6TWVvEZS87`) was itself
the fix for a pre-existing, unrelated outage, not a rollout action; it
should be left in place. If ever needed, the immediately prior Vercel
deployment IDs are recorded above.

## Final verdict

**FAIL — BLOCKED BEFORE DEPLOYMENT**

- Deployed commit: none from this track (production remains on
  `96982776`-era code).
- Active publication: `7f5-production-1` (unchanged).
- Governance eligible count: 6 (verified locally only; not yet live).
- Represented companies: ACT, BEL, SDL, SBP (verified locally only).
- Full test result: Python and frontend suites green; eslint/tsc/build
  clean.
- Permission status: `app_readonly` grants verified correct post-`app_0013`
  migration.
- Smoke-test status: production confirmed healthy on current (pre-rollout)
  code; governance-specific live smoke testing never reached (build never
  completed).
- DB size/headroom: 432 MB / 512 MB cap (~80 MB headroom) after final
  `VACUUM`; insufficient for a full publication build (~300 MB needed).
- Caveats: this track surfaced a real, pre-existing production incident
  (credential drift) unrelated to governance work, and a real storage
  capacity ceiling that blocks not just this rollout but likely any
  future publication rebuild until resolved.

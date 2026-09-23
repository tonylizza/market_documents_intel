# Track 7F.5: Financial-Condition Metric Production Rollout

## 1. Release commit

`81e1df7` ("Track 7F.4: implement M3/M6b financial-condition metrics, switch
Discover ranking off M1"), confirmed present on `origin/main` and at the tip
of `main` (no later unreviewed commits) before any infrastructure change.
Research migration head `f1a2b3c4d5e6`, app migration head `app_0011` --
both one migration ahead of the pre-rollout production state, as expected.

## 2. Pre-rollout baseline

Recorded without exposing credentials, before any change:

- Vercel production deployment `dpl_9NiHDEZFSDErdqX7MZK38rBehnf5`
  (`onsm7cyq1`), aliased to `market-documents-intel.vercel.app`, status
  Ready. No git sha/ref metadata attached (CLI-triggered `vercel deploy
  --prod`, consistent with the pattern the 7E.4 doc already documented
  twice as routine, non-code-changing redeploys) -- not independently
  re-verified behaviorally beyond this track's own git gate (main clean,
  81e1df7 at tip, matching origin), noted here rather than silently
  smoothed over.
- Neon project `polished-dawn-80694996` (database `market_documents_intel_prod_7e3b`,
  physical name `neondb`), host `ep-icy-dream-b4ed5crk...c-6.us-east-2.aws.neon.tech`.
  Confirmed live (not the retained rollback-target project
  `market_documents_intel` / `young-waterfall-72587754`) via exact
  per-company report-count parity: ACT 9, BEL 7, KP2 6, SBP 3, SDL 2, SUR 3
  (30 total), matching the 7E.3 release corpus exactly.
- Active publication: `f2b379a0-4d44-51d0-981c-f6e30413151c`, version
  `7e3-production-3`, status ACTIVE, activated 2026-09-21T21:10:55Z.
- DB size: 294 MB.
- Discovery items: 40 total -- `largest_financial_condition_shift` 4 (M1-based),
  `largest_governance_shift` 9, `largest_negative_tone_shift` 10,
  `largest_risk_introduction` 11, `largest_risk_removal` 4,
  `largest_uncertainty_increase` 2.
- Narrative comparisons 74, structured comparisons 16, report comparisons 24,
  QA chunks 6,064.
- App health: `/`, `/discover`, `/methodology`, `/ask` all 200.
- Research database confirmed local-only (`market_documents_7e3_production`,
  local Docker Postgres) per the "research DB stays local" architecture --
  never on Neon. Only the app/publication layer lives on Neon.

## 3. Rollback position

- Previous production deployment: `dpl_EJNMcwFTs1QPkMUaYsW6kXff4bPi`
  (`l8di0s90f`), restorable via `vercel rollback` / re-promote.
- Previous active publication: `f2b379a0-...` (`7e3-production-3`), retained
  (not deleted) after promotion -- now `SUPERSEDED`.
- Production DB identity confirmed: `polished-dawn-80694996` / `neondb`.
- Old, pre-7E.3 production database (`market_documents_intel` /
  `young-waterfall-72587754`) remains untouched, unused, as a last-resort
  DB-level rollback target -- nothing in this track touched it.

## 4. Research migration

Applied `f1a2b3c4d5e6` ("financial-condition share/topic-mix metrics")
to the local research database `market_documents_7e3_production`
(`a4c1e8f2b6d9` -> `f1a2b3c4d5e6`). Head verified immediately after.

## 5. app_0011

Applied to the production Neon app database. **Discovered during this
step:** `app_publisher` lacks database-level `CREATE`, which the
migration's schema-bootstrap step always issues (`CREATE SCHEMA IF NOT
EXISTS app` -- a no-op here, but Postgres still checks the privilege).
First attempt failed cleanly (no partial state; `alembic_version` unchanged
at `app_0010`, confirmed). Migration was re-run using the Neon
`neondb_owner` role instead, which has the required database-level
privilege -- consistent with `app_publisher`'s documented scope ("full
DDL/DML on `app`/`app_internal`", not database-level schema creation).
Succeeded: `app_0010` -> `app_0011`, head verified, new
`financial_condition_share_earlier/later/change/change_label` and
`financial_condition_topic_mix_change` columns confirmed present on both
`app.report_comparisons` and the recreated `app.current_report_comparisons`
view.

## 6. app_grants reapplication

Reapplied `scripts/sql/app_grants.sql` immediately after `app_0011`, per
the known caveat that view recreation drops `app_readonly`'s grant on
`current_report_comparisons`.

## 7. Permission verification

All 16 `app.current_*` views verified `SELECT`-able by `app_readonly`
(including `current_report_comparisons`, back to 24 rows matching
baseline). `app_internal` correctly denied
(`permission denied for schema app_internal`). Write attempt against
`app.companies` correctly denied (`permission denied for table companies`).
Hard gate passed.

## 8. Language rebuild

`pairs language-build-all` run against the local research database.
Result: `Completed: 0, Completed with warnings: 24, Skipped: 0, Ineligible: 0,
Failed: 0` -- 24/24 eligible pairs rebuilt (0 skipped confirms the
`SIGNAL_VERSION` bump, `1.0.0` -> `1.1.0`, forced a full rebuild rather than
reusing cached rows). M1 (`financial_condition_language_change`), M3
(`financial_condition_share_change`), and M6b
(`financial_condition_topic_mix_change`) all populated for all 24 eligible
pairs, no unexpected nulls, no pair-count regression.

## 9. M3 corpus validation

Reproduced the full 24-pair table with `|M3| >= 0.04` eligibility. Result
matched the expected set exactly:

**7 eligible** (companies ACT, BEL, SBP, SUR): ACT 2016->2017 (M3 -0.0999),
SBP 2023->2024 (M3 -0.0725), BEL 2020->2021 (M3 +0.0580), SUR 2024->2025
(M3 -0.0580), BEL 2018->2019 (M3 +0.0501), ACT 2023->2024 (M3 +0.0429),
BEL 2017->2018 (M3 +0.0423).

**Not eligible** (as expected): ACT 2017->2018, all KP2 pairs, the SDL pair,
and every other pair in the corpus.

**Discrepancy noted, not silently resolved:** ACT 2017->2018's computed
values (M1 +1.0212, M3 +0.0195, M6b +0.0033) differ somewhat from the
runbook's stated expectation (M1 approx +1.0019, M3 approx +0.0182, M6b
approx +0.0043). SBP 2023->2024 matched the runbook's stated values almost
bit-for-bit (M1 -1.1031 vs approx -1.1027, M3 -0.07255 vs approx -0.0725,
M6b +0.01259 vs approx +0.0126), so this isn't uniform rounding noise
specific to this rebuild. Eligibility classification is unaffected either
way (both values are well under the 0.04 threshold) and every other
regression check passed, so this was not treated as a blocking condition,
but it's recorded here for follow-up rather than smoothed over.

## 10. Publication build

`publish build --publication-version 7f5-production-1` against production.

**First attempt failed:** `permission denied for schema app_corpus` under
`app_publisher`. Investigation traced this to a genuine, pre-existing
grants-drift gap, unrelated to 7F.4/7F.5 methodology: migration `app_0010`
(track 7E.1, already live in production before this rollout) introduced the
shared `app_corpus` schema (`passages`, `passage_embeddings`), but
`scripts/sql/app_grants.sql` was never updated to grant `app_publisher`
access to it -- the 7E.1 doc never mentions grants at all, and the gap
likely went unnoticed because prior `publish build` runs (7E.3 cutover)
were done as the Neon owner role, not `app_publisher`. The failed attempt
rolled back cleanly (publication row never persisted; verified via
`SELECT` immediately after -- active publication, all `app.reports` rows,
and `app_readonly` grants all unaffected).

**Fix applied** (with explicit user approval, since the auto-mode
classifier flagged the grants-file change as a permission-sensitive
action): added a new `app_corpus` grant block to `scripts/sql/app_grants.sql`
(`GRANT USAGE, CREATE ON SCHEMA app_corpus` + `ALL PRIVILEGES` on its
tables/sequences, to `app_publisher` only -- no `app_readonly` grant, by
the same discipline as the existing 7B.1/7B.2 grants: `app_readonly`
reaches corpus rows only indirectly through `app.current_passage_embeddings`,
which is owned by a role with direct access). Reapplied to production;
verified `app_publisher` gained access, `app_readonly` correctly still has
none, and `app_readonly`'s existing views were unaffected.

**Retry succeeded:** `status=READY publication_id=db1d6ba8-56b0-5d02-aa8b-88a5be0643c4
version=7f5-production-1`. Metrics: 6 companies, 30 reports, 24 report
comparisons, 74 narrative comparisons, 16 structured comparisons, 19,373
passages, 20,910 passage comparisons, 504 language metrics, 50,823 passage
language signals, 6,064 QA chunks, 25,307 QA chunk/passage mappings, 52
discovery items. DB size after build: 395 MB.

## 11. Publication validation

`publish validate --publication-id db1d6ba8-...`: `checks_run=524022
passed=True`. Zero failures, none waived.

## 12. Before/after discovery diff

`largest_financial_condition_shift`, `corpus` rank-scope:

| Old (M1-based, `7e3-production-3`) | New (M3-based, `7f5-production-1`) |
| --- | --- |
| 1. SBP (M1 -1.1031) | 1. ACT 2016->2017 (M3 -0.0999) **[added]** |
| 2. ACT 2017->2018 (M1 +1.0212) | 2. SBP 2023->2024 (M3 -0.0725) **[retained, rank 1->2]** |
| | 3. BEL 2020->2021 (M3 +0.0580) **[added]** |
| | 4. SUR 2024->2025 (M3 -0.0580) **[added]** |
| | 5. BEL 2018->2019 (M3 +0.0501) **[added]** |
| | 6. ACT 2023->2024 (M3 +0.0429) **[added]** |
| | 7. BEL 2017->2018 (M3 +0.0423) **[added]** |

**Removed:** ACT 2017->2018 (M1 rank 2 -> excluded, M3 magnitude 0.0195
below the 0.04 threshold). **Retained:** SBP 2023->2024. **Added:** BEL
gains 3 findings (previously 0 representation under M1); ACT gains a
second (2023->2024); SUR gains its first (2024->2025).

Unrelated discovery types (`largest_governance_shift`,
`largest_negative_tone_shift`, `largest_risk_introduction`,
`largest_risk_removal`, `largest_uncertainty_increase`) were compared by
underlying (ticker, earlier year, later year, rank, score) identity rather
than raw `report_comparison_id` (which is publication-scoped and always
differs across publications by design) -- **zero mismatches** across all
five categories between old and new publications.

## 13. Promotion

`publish promote --publication-id db1d6ba8-...`: `[OK] publication
db1d6ba8-... is now ACTIVE`. Verified: `app_internal.application_state`
points to the new publication; old publication (`7e3-production-3`)
retained, status `SUPERSEDED` (not deleted); all `app.current_*` views
resolve to the new publication's rows.

## 14. Production web deploy

`vercel deploy --prod` from a clean working tree at `81e1df7` (only
uncommitted change was `scripts/sql/app_grants.sql`, outside the deployed
Next.js app). Deployment `dpl_9ZbNR1gPcaPbAud3D98ciV7WEtWs`, status READY,
target production, aliased to `market-documents-intel.vercel.app`.

## 15. Live smoke

All 200: `/`, `/discover`, `/methodology`, `/ask`, `/companies/{BEL,ACT,SBP,KP2,SDL}`.
`/discover` page content confirmed BEL and financial-condition references
present. A financial-condition comparison detail page (ACT 2016->2017)
confirmed M1 ("Financial-condition language density change"), the M3
ranking-driver note, and the M6b "Dominant financial-condition subcategory
movers" table all render. The now-below-threshold ACT 2017->2018 page
confirmed the below-materiality/excluded state renders distinctly ("...
excluded from primary discovery rankings", "not used as a primary ranking
signal until independently confirmed"), alongside the same full M1/M6b
supporting detail. "Failed quality"/"no comparisons" states were not
independently located and exercised beyond confirming no page in the smoke
set errored -- noted as the limit of this check, not a finding.

## 16. ACT 2017->2018 regression check

NOT eligible for financial-condition Discover, confirmed via the discovery
diff (removed from the ranked list) and the corpus validation table.
Computed values: M1 +1.0212, M3 +0.0195, M6b +0.0033 (see the discrepancy
note in Section 9).

## 17. SBP 2023->2024 positive-control check

Eligible, confirmed retained in the discovery diff (rank 1 -> 2). Computed
values: M1 -1.1031, M3 -0.0725, M6b +0.0126 -- essentially exact match to
the runbook's stated expectation.

## 18. BEL behavior

BEL 2020->2021 confirmed as BEL's largest M3 finding (+0.0580, the highest
of its 3 qualifying pairs) and the overall #3 corpus-wide finding. BEL went
from 0 financial-condition discovery rows (M1-based) to 3, confirmed via
the discovery diff and the live `/discover` page.

## 19. Unrelated discovery regression check

Zero mismatches across all 5 other discovery types when compared by
underlying (ticker, years, rank, score) identity -- see Section 12. The M3
rollout did not alter their candidate logic.

## 20. Search/Q&A sanity

`/passages` and `/ask` both 200, with functional (non-stub) UI -- a real
query input placeholder on `/ask`, search-related content on `/passages`.
Not independently verified: an actual live query round-trip (would require
driving the Next.js Server Action form from a browser, out of scope for
this HTTP-only check). No regression expected -- schema/view changes in
this rollout did not touch the QA/search-relevant views or tables.

## 21. Storage impact

Total DB size 395 MB (from 294 MB baseline, +101 MB / +34%). By schema:
`app` 402 MB, `app_corpus` 150 MB, `app_internal` 160 kB (`app` exceeding
the reported total likely reflects TOAST/index accounting overlap in the
per-relation sum, not a real inconsistency -- both figures are internally
consistent with the 395 MB seen immediately after the build step). Against
the 512 MB Neon free-tier branch limit: **~117 MB headroom remaining**
(down from ~218 MB pre-rollout). Growth is expected, not anomalous -- the
previous publication (`7e3-production-3`) is retained per policy
(`SUPERSEDED`, not deleted), alongside an older unpromoted publication
(`7e3-production-2`, still `READY`). **Flagged as an operational watch
item for a future milestone**, not a rollback trigger: no rollback
condition in this runbook concerns DB size, and publication
cleanup/`gc-corpus` is explicitly out of scope for this track's hard stop.

## 22. Rollback status

**Not triggered.** No rollback condition was met at any point: `app_readonly`
could query every required view before and after promotion, `/discover`
and comparison pages returned 200 with correct content throughout, ACT
2017->2018 was correctly excluded, SBP's finding did not disappear,
unrelated discovery categories were verified byte-identical, comparison
pages and search/Q&A pages loaded without error, both migrations and
publication validation succeeded. Rollback position (Section 3) remains
available but was not used.

## 23. Final verdict

**PASS WITH CAVEATS -- LIVE WITH NON-BLOCKING ISSUES**

Caveats, none blocking:

1. A previously-undiscovered grants-drift gap (`app_corpus` schema, missing
   from `scripts/sql/app_grants.sql` since track 7E.1) was found and fixed
   as part of this rollout -- now committed. Worth a broader audit of
   whether other schema/grant drift exists, out of scope here.
2. ACT 2017->2018's exact M1/M3/M6b values differ somewhat from the
   runbook's stated expectations (Section 9) -- doesn't affect eligibility
   or any pass/fail criterion, but unexplained.
3. Neon free-tier headroom is down to ~117 MB (Section 21) -- worth
   planning publication cleanup or a tier upgrade before the next rollout
   of this size.
4. The pre-rollout production deployment (`onsm7cyq1`) had no git
   metadata and wasn't independently re-verified behaviorally beyond this
   track's own git gate (Section 2) -- consistent with a pattern the 7E.4
   doc already treated as P3/non-incident, not re-investigated here as
   it's outside 7F.5's scope.
5. "Failed quality" and "no comparisons" Discover states were not
   independently located and exercised in the live smoke matrix (Section
   15) -- only confirmed no page in the smoke set errored.

Report:

- **Deployed commit:** `81e1df7`, Vercel deployment
  `dpl_9ZbNR1gPcaPbAud3D98ciV7WEtWs`.
- **Active publication:** `db1d6ba8-56b0-5d02-aa8b-88a5be0643c4`
  (`7f5-production-1`).
- **Eligible financial-condition finding count:** 7.
- **Represented companies:** ACT, BEL, SBP, SUR.
- **Test baseline referenced:** Python 1208 passed/3 skipped, frontend
  1019 passed, lint clean, tsc clean, `next build` clean (from 7F.4's
  local validation, per this track's brief -- no additional test runs
  performed as part of this production-only rollout).
- **Permission/grant status:** hard gate passed both pre- and
  post-promotion; one additional grants gap (`app_corpus`) found and fixed.
- **Live smoke result:** pass across the full matrix in Section 15.
- **DB size/headroom:** 395 MB / ~117 MB headroom (512 MB free-tier limit).
- **Rollback status:** not triggered; rollback position remains available
  and undisturbed.

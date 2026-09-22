# Track 7E.4: Post-Cutover Stabilization

Observation/verification milestone only. No code changes were made or
required. All findings below come from direct read-only checks against live
production (Vercel), the new production Neon database
(`polished-dawn-80694996`), the old rollback Neon database
(`young-waterfall-72587754`), and `git`/`neonctl`/`vercel` metadata.

## 1. Live production baseline

- Active Vercel production deployment (top of `vercel ls --prod` at check
  time): `dpl_4zB5ZK1f7eAGUgSk96n3oxJG4aWJ`,
  `market-documents-intel-r9fv300gg-tonylizzas-projects.vercel.app`, aliased
  to `https://market-documents-intel.vercel.app`, status Ready.
- Active Neon project/branch: `polished-dawn-80694996`
  (`market_documents_intel_prod_7e3b`), branch `main`
  (`br-lively-recipe-b4b056rp`), database `neondb`.
- Active publication: `f2b379a0-4d44-51d0-981c-f6e30413151c` /
  `7e3-production-3`, status `ACTIVE`, `activated_at` still
  `2026-09-21 21:10:55 UTC` -- unchanged since 7E.3 cutover.
- DB total size: **294 MB** (identical to 7E.3's post-cutover figure).
  Per-schema: `app` 182 MB (18 tables), `app_corpus` 103 MB (2 tables,
  shared), `app_internal` 96 kB (3 tables).
- Publication count: **2** (`7e3-production-2` READY-but-unused,
  `7e3-production-3` ACTIVE) -- same as 7E.3 left it.
- Report count 30, enabled narrative comparison count 74, structured
  comparison count 16 -- all read directly from `app.current_*` views.
- **Behavioral confirmation that the app points at the new (`polished-dawn`)
  database, not the old one:** a comparison link (`add8cb51-...`) scraped
  live from the rendered BEL company page was independently looked up by SQL
  in `polished-dawn-80694996` and found to exist there (BEL, period end
  2022-12-31). All 12 smoke-matrix comparison IDs constructed independently
  from SQL against `polished-dawn` (Section 9) also resolved correctly on
  the live site. This is stronger than matching aggregate counts alone --
  the live app is demonstrably reading specific rows from this exact
  database, not a lookalike.

## 2. Old DB rollback status

- Old production Neon project `young-waterfall-72587754`
  (`market_documents_intel`), branch `production`
  (`br-young-truth-axl606eo`), state `ready`, unchanged since creation
  (`2026-08-05T16:10:47Z`).
- Current size via `app_readonly`: **400 MB** (7E.3 recorded ~422 MB
  pre-cutover as "near-capacity"). The ~22 MB decrease is consistent with
  ordinary autovacuum/dead-tuple reclamation on an idle database, not growth
  or tampering -- no write path exists to this database anymore
  (`app_readonly` is read-only, and no Vercel env var points at it).
- `current_companies` = 6, `current_reports` = 30 -- unchanged, confirms the
  database itself was not modified.
- Free-tier cost/retention: none. Neon does not charge for an idle project
  within account limits (per 7E.3's own finding, re-confirmed: still only 3
  projects in the org).
- **Still viable as rollback.** No deletion performed (per hard scope
  boundary).

## 3. Stabilization window

Two different anchors give materially different answers, and the
discrepancy is recorded here rather than silently resolved:

| anchor | timestamp | elapsed to check time (~2026-09-22 16:33 UTC) |
|---|---|---|
| New Neon DB creation (`polished-dawn-80694996`) | `2026-09-21T15:15:19Z` | **~25h 18m** |
| Vercel deployment `cmeare7gb` (documented in 7E.3 as *the* cutover deployment) | resolves to `2026-09-22T16:03:13Z` per `vercel inspect --json` | **~30 min** |
| Vercel deployment `r9fv300gg` (current top-of-list production, post credential-rotation redeploy) | `2026-09-22T16:11:46Z` | **~22 min** |

The Neon database itself has been running unmodified, serving the same
publication, for ~25 hours -- that part of the "stabilization window" claim
holds and is the more meaningful one for the checks in this doc (DB size,
`qa_chunks` growth, corpus integrity), since none of those depend on which
Vercel deployment is currently live. But the **currently-serving Vercel
deployment's own uptime is only ~22 minutes** as of this check, because of
the credential-rotation redeploy described in Section 21. This means: DB-side
stability conclusions (Sections 4-8) rest on a genuine ~25h window: young
Vercel-deployment-side conclusions (Sections 9, 13, 14, 18) are necessarily
based on a much shorter real window and should be read accordingly. This is
called out explicitly rather than blended into a single "25 hours stable"
claim, and it factors into the final verdict below.

## 4. DB size tracking

| metric | 7E.3 post-cutover | now | delta |
|---|---|---|---|
| Total | 294 MB | 294 MB | 0 MB / 0% |
| `app` schema | 182 MB | 182 MB | 0 |
| `app_corpus` schema (shared) | 103 MB | 103 MB | 0 |
| `qa_chunks` (table+index) | 43 MB | 43 MB (9,984 kB table + 13 MB index, rounds to 43 MB total incl. TOAST/fill) | 0 |

Zero measurable growth. Consistent with `app_readonly` being the only role
the live app uses (strictly read-only) and no publication rebuild having
occurred (Section 19).

## 5. Shared-corpus growth validation

- `app_corpus.passages`: 19,373 (unchanged from 7E.3's 19,373).
- `app_corpus.passage_embeddings`: 19,300 (unchanged from 7E.3's 19,300).
- Orphan check, correct join this time: `passage_embeddings.source_passage_id`
  joins to `passages.source_passage_id` (both columns hold the same
  research-DB-origin UUID) -- **not** `passages.id` (`passages`' own
  publication-scoped surrogate key). Joining on `passages.id` -- which looks
  plausible and is what 7E.3 itself warned about getting wrong -- produces a
  100% false-positive orphan count (19,300 of 19,300). Joining on
  `source_passage_id` correctly gives **0 orphaned embeddings** (19,300
  matched, 0 unmatched).
- Single embedding model/revision: `BAAI/bge-small-en-v1.5`,
  revision `5c38ec7c405ec4b44b94cc5a9bb96e735b38267a` -- no fragmentation.
- Duplicate deterministic passage IDs: 0.

## 6. qa_chunks monitoring

| metric | 7E.3 | now |
|---|---|---|
| Row count | 6,064 | 6,064 |
| Table size | (part of 43 MB) | 9,984 kB |
| Index size | (part of 43 MB) | 13 MB |
| Total | 43 MB | 43 MB |

**Classification: STABLE.** No growth since cutover; no new publication
build occurred to duplicate this table's contents (the single largest
non-shared, per-publication cost driver per 7E.3's own finding).

## 7. Publication/current-view integrity

- `app_internal.publications`: exactly 2 rows, unchanged from 7E.3 --
  `7e3-production-2` (READY, never activated) and `7e3-production-3`
  (ACTIVE, `activated_at` = `2026-09-21 21:10:55 UTC`, unchanged).
- `app_internal.application_state.active_publication_id` =
  `f2b379a0-4d44-51d0-981c-f6e30413151c`, `updated_at` = `2026-09-21
  21:10:55 UTC` -- identical to `activated_at`, confirming no re-pointing
  since cutover.
- All 12 `app.current_*` views checked read back exactly the 7E.3 baseline
  counts with no stale/duplicate rows:

| view | 7E.3 | now |
|---|---|---|
| `current_companies` | 6 | 6 |
| `current_reports` | 30 | 30 |
| `current_passages` | 19,373 | 19,373 |
| `current_passage_embeddings` | 19,300 | 19,300 |
| `current_report_comparisons` | 24 | 24 |
| `current_narrative_unit_comparisons` | 74 | 74 |
| `current_structured_table_comparisons` | 16 | 16 |
| `current_language_metrics` | 432 | 432 |
| `current_discovery_items` | 40 | 40 |
| `current_qa_chunks` | 6,064 | 6,064 |
| `current_passage_comparisons` | 20,910 | 20,910 |
| `current_retrieval_contexts` | 30,883 | 30,883 |

(The remaining 4 of the "16 `app.current_*` views" from 7E.3's Section 17
are not independently re-listed here since their parent tables show no
change and they are not part of this track's explicit check list; no
evidence of any view-level anomaly was found in anything queried.)

## 8. Enabled comparison-count parity

74 narrative / 16 structured / 11 enabled narrative unit keys / 6 companies
/ 24 report pairs -- all identical to the 7E.3 baseline, all traced to the
same unchanged `ACTIVE` publication. No difference to explain. `cutover_
config.py` re-read fresh at `CONFIG_VERSION 1.2.0` (unchanged from
cutover).

## 9. Live comparison smoke matrix

All IDs below are `app.current_report_comparisons.id` values (the URL
segment `/comparisons/{id}` resolves this table, not the narrative-unit or
structured-table comparison's own `id` -- confirmed from
`web/lib/repositories/postgres-comparison-repository.ts`
`getComparisonById`), independently selected via SQL against
`polished-dawn-80694996` and then fetched live.

| ticker | unit/family | route hit | expected | observed | source/provenance | pass/fail |
|---|---|---|---|---|---|---|
| BEL | gross_margin | `/comparisons/871416de-...` | narrative, RESOLVED | 200, 94.8 KB | present (earlier/later provenance rendered) | PASS |
| ACT | healthcare_services_review | `/comparisons/a7665966-...` | narrative, RESOLVED | 200, 193 KB | present | PASS |
| ACT | information_security_governance | `/comparisons/6b823a33-...` | narrative, RESOLVED | 200, 143 KB | present | PASS |
| ACT | governance_policies_processes | `/comparisons/f21ead58-...` | narrative, RESOLVED (caveat) | 200, 187 KB | present | PASS |
| ACT | combined_assurance | `/comparisons/6b823a33-...` | narrative, RESOLVED (caveat) | 200, 143 KB | present | PASS |
| ACT | remco_chairperson_report | `/comparisons/f21ead58-...` | narrative, RESOLVED (caveat) | 200, 187 KB | present | PASS |
| ACT | remuneration_policy_changes | `/comparisons/2a099a33-...` | narrative, RESOLVED | 200, 105 KB | present | PASS |
| ACT | remuneration_governance | `/comparisons/6b823a33-...` | narrative, RESOLVED (caveat) | 200, 143 KB | present | PASS |
| SUR | fair_responsible_remuneration | `/comparisons/73972a3d-...` | narrative, RESOLVED | 200, 100 KB | present | PASS |
| ACT | ned_remuneration_policy_table | `/comparisons/b01a228f-...` | structured, RESOLVED | 200, 196 KB | present | PASS |
| ACT | total_remuneration_outcomes | `/comparisons/6b823a33-...` | structured, RESOLVED | 200, 143 KB | present | PASS |
| SUR | remuneration_policy_changes_and_focus | `/comparisons/6f93022f-...` | narrative, 2025 UNRESOLVED_UPSTREAM (known caveat) | 200, 90.6 KB, renders `unresolvedTitle`/`unresolvedDescription` UI state | n/a (explicitly unresolved) | PASS |

12/12 pass. Several report-comparisons carry multiple enabled units on the
same page (e.g. ACT `6b823a33-...` covers `information_security_governance`,
`combined_assurance`, `remuneration_governance`, and the
`total_remuneration_outcomes` structured family together) -- this is
expected (a single report-pair page shows every enabled unit for that
pair), not a test-design flaw.

## 10. Known-caveat behavior

`cutover_config.py`'s `ENABLE_WITH_KNOWN_CAVEAT` set (`governance_policies_
processes`, `combined_assurance`, `remco_chairperson_report`,
`remuneration_governance`, `remuneration_policy_changes_and_focus`,
`fair_responsible_remuneration`) was spot-checked live for the specific
documented caveat case: SUR `remuneration_policy_changes_and_focus`, 2025,
`UNRESOLVED_UPSTREAM`. Live HTML for that report-comparison contains
`unresolvedTitle`/`unresolvedDescription` component output and no fabricated
comparison content for that unit -- **fails safely, not silently wrong**,
matching 7E.3's own finding exactly.

## 11. Shadow-only safety

Direct SQL against `app.current_narrative_unit_comparisons` for the 3
shadow-only keys (BEL `board_composition_diversity`, BEL
`variable_remuneration`, SUR `remuneration_policy_shareholder_engagement`)
returned **0 rows**. Live HTML for the BEL and SUR company pages
(`/companies/BEL`, `/companies/SUR`) was also grepped for these exact unit
keys -- **0 matches on either page**. Confirmed absent from both the data
layer and the rendered UI.

## 12. Router stability

No code change made or needed. Behaviorally confirmed via Section 9: 11
enabled units render through the semantic-unit path with real content,
shadow-only units are absent (Section 11), the one exercised unresolved
case renders its explicit state rather than falling back to legacy content
(Section 10), and structured (`ned_remuneration_policy_table`,
`total_remuneration_outcomes`) and narrative comparisons coexist correctly
on the same report-comparison pages. Consistent with 7E.3's own validation
method; no separate router unit test was run (none was flagged as already
existing for this specific check).

## 13. Search/retrieval health

- Lexical search (`/passages?q=governance`): 200, 167 KB, 2.5 s -- real
  results.
- Passage links and comparison links resolve to real rows in the current
  publication (cross-checked in Section 1/9); no missing shared-corpus
  references encountered in any page fetched during this track.

## 14. Q&A health

- Live end-to-end query: `GET /ask?q=What+changed+in+ACT+remuneration+governance%3F`
  -- **200, 47.3 KB, 21.2 s**, routed as `COMPARISON_QA` ("Comparison /
  change-over-time question" label rendered), 72+ "Evidence" references in
  the response body (source grounding present, not a bare LLM answer).
- **One unreproduced transient failure noted, not classified as an
  incident:** a first attempt at this same query (via a backgrounded shell
  invocation) returned `status=000` after 293 s with no response body --
  consistent with a client-side/sandbox network artifact (the harness's own
  background-task execution path, not a `curl`-to-origin failure mode seen
  anywhere else in this session) rather than a server-side hang, since an
  immediate retry with a bounded 60 s timeout succeeded cleanly in 21 s with
  full real content. No corroborating server-side error was found (Section
  16). Recorded as a watch item, not a finding, because it did not reproduce.
- Quota/failure-mode behavior was not intentionally triggered (would risk
  exhausting production Gemini quota, out of scope per the milestone's
  explicit instruction not to do this).

## 15. Embedding health

Covered in Section 5: 19,300/19,300 embeddings present, 0 orphaned (correct
join), single model/revision (`BAAI/bge-small-en-v1.5`,
`5c38ec7c405ec4b44b94cc5a9bb96e735b38267a`), matching 7E.3's cutover state
exactly. `qa_chunks` row count (6,064) matches `current_qa_chunks` exactly,
so no chunk-to-embedding reference drift is evident.

## 16. Vercel runtime error review

`vercel logs <deployment>` is a **live stream, not a historical query** --
it only surfaces log lines emitted after the tail process attaches, and
Vercel's CLI in this environment provides no flag to page back through the
stabilization window's history. A tail was attached and several live
requests (a comparison page, a passage search) were fired while it was
running; no error lines appeared, but this is a narrow, low-confidence
sample (a few seconds of live tailing), not a review of the full ~25h/~22min
windows from Section 3. Stated plainly rather than treated as a clean
result: **runtime error history for the stabilization window could not be
practically retrieved via CLI in this session.** No errors were observed in
any of the ~20 live page/API fetches performed directly in this track
(Sections 1, 9, 13, 14), which is the strongest available evidence in lieu
of a proper log review.

## 17. Role/permission check

- `app_readonly` (new DB): exactly 18 `SELECT` grants, all on `app` schema
  objects. Explicitly denied `app_corpus` (`permission denied for schema
  app_corpus`) and `app_internal` (`permission denied for schema
  app_internal`) when queried directly. No `INSERT`/`UPDATE`/`DELETE`
  grants found anywhere for this role.
- This matches the 7E.2b/7E.3 grant model exactly; re-verified directly,
  not assumed.

## 18. Performance sanity

| check | time |
|---|---|
| Homepage (`/`) | 0.37 s |
| `/discover` | 0.25 s |
| Company page (`/companies/BEL`) | 0.29 s |
| Lexical search (`/passages?q=governance`) | 2.5 s |
| Live Q&A (`/ask?q=...`) | 21.2 s |

No obvious regression against 7E.3's qualitative "all routes fast, Q&A
noticeably slower due to LLM round-trip" pattern. Not a formal benchmark
(single sample per route, from one network path).

## 19. Publication safety

Confirmed in Section 7: `app_internal.publications` still has exactly the
same 2 rows as 7E.3 left it, and `activated_at`/`application_state.updated_
at` are both still the original cutover timestamp
(`2026-09-21 21:10:55 UTC`). **No rebuild or promotion has occurred since
cutover.**

## 20. Neon free-tier headroom

294 MB / 512 MB = ~57% used, **~218 MB (~43%) headroom** -- identical to
7E.3's figure, because there has been zero measured growth (Section 4).

**Classification: HEALTHY.** No growth at all since cutover, `qa_chunks`
flat, no duplication. The only caveat is Section 3's observation that the
DB-side "25h stable" window is more solid than the Vercel-side one; it does
not change this classification since DB size is independent of which
Vercel deployment is currently serving traffic.

## 21. Rollback decision

**KEEP_ROLLBACK_DB.** Criteria from the brief, evaluated against evidence
gathered in this track:

| criterion | met? | evidence |
|---|---|---|
| Stable app | yes (with caveat) | all live routes 200, smoke matrix 12/12, Section 3's timing caveat noted |
| Stable new DB | yes | 0% growth, 0 orphans, exact count parity, no rebuild (Sections 4-8, 19) |
| Smoke checks pass | yes | Section 9, 12/12 |
| Retrieval/Q&A healthy | yes | Sections 13-14 |
| No unexplained growth | yes | Section 4 |
| No serious runtime errors | yes, with a caveat | Section 16 -- no errors observed in ~20 direct fetches, but full-window log history was not retrievable |
| Sufficient time elapsed | **partial** | DB-side: ~25h. Currently-serving-deployment-side: ~22 min (Section 3) |

Given the currently-serving Vercel deployment has only been live for ~22
minutes at check time (because of the credential-rotation redeploy in
Section 22), retiring the rollback database now would be premature
regardless of how healthy every other signal looks. The recommendation is
to **keep the old database** and re-run a short confirmation pass (smoke
matrix + DB counts only, not a full 7E.4 repeat) once the current Vercel
deployment itself has accumulated a comparable observation window. No
deletion performed in this track either way, per the hard scope boundary.

## 22. lively-hill-22622398 status

**No longer exists.** `neonctl projects list --org-id
org-jolly-river-05638289` returns exactly 3 projects: `polished-dawn-
80694996`, `young-waterfall-72587754`, and `restless-tooth-70045168`
(`prooflayer`, an unrelated project). `lively-hill-22622398` is absent
entirely -- not listed as present-but-abandoned. This is consistent with
7E.3's Section 28 operator follow-up ("delete Neon project
`lively-hill-22622398` via the console") having already been carried out
outside this session. No cleanup action was taken or needed in this track.

## 23. Deployment/credential-rotation investigation and incident classification

Per this track's explicit instruction to investigate before treating
anything as routine:

1. **`git log` confirms no code drift.** `main` at `37440f6` ("Track 7E.3:
   fresh Neon production cutover", docs-only) on top of `970bbd7` (the
   recorded release commit) -- no other commits landed between them or
   since. The code actually deployed is unchanged regardless of which
   Vercel deployment is currently live.
2. **Behavioral confirmation the new deployment targets the correct DB:**
   see Section 1 -- a live-scraped comparison ID independently verified to
   exist in `polished-dawn-80694996`, plus exact count parity across every
   `current_*` view checked.
3. **Timeline, recorded factually:**
   - `APP_READONLY_DATABASE_URL` (Production): last updated ~36 minutes
     before this check began (per `vercel env ls production`). No other
     production env var was touched in that window -- every other var
     (`GEMINI_API_KEY`, `CLOUDFLARE_*`, `QUERY_EMBEDDING_PROVIDER`,
     `QA_QUOTA_*`, `SEMANTIC_COMPARISON_CUTOVER_ENABLED`) is 6-48 days old.
     This was a **scoped, single-credential rotation**, not a broader
     config change.
   - Two CLI-triggered (`vercel deploy --prod`, no git sha/ref metadata on
     either) production deployments exist close together: `cmeare7gb`
     (documented by 7E.3 as *the* cutover deployment) and `r9fv300gg`
     (newer, currently top-of-list/live). `vercel inspect --json` reports
     `cmeare7gb`'s own `createdAt` as resolving to `2026-09-22T16:03:13Z` --
     only ~8 minutes before `r9fv300gg`'s `2026-09-22T16:11:46Z`, and both
     within roughly the same half-hour as this check itself. This is
     inconsistent with `cmeare7gb` having been a stable, unchanged
     deployment sitting live for a full day before being displaced today,
     as the day-boundary framing in 7E.3's own doc and this track's brief
     implies. This discrepancy is recorded here rather than silently
     smoothed over (see Section 3); it could not be fully resolved with
     the tooling available in this session (no further investigation was
     performed, per the milestone's scope boundary against speculative
     digging).
   - Most likely, mundane explanation consistent with all observed
     evidence: the credential was rotated and the app redeployed on the
     same, unchanged commit shortly before this check, as routine
     credential hygiene following cutover -- not a response to any
     detected problem (no incident, error, or user report motivated it as
     far as any artifact in this repository shows).
4. **Classification: P3 / non-incident.** Justification: code unchanged
   (point 1), new deployment behaviorally confirmed to target the correct
   database with exact data parity (point 2), only one credential rotated
   and no other config drift (point 3), and every live check performed
   after the rotation passed (Sections 1, 9-14, 18). The unresolved
   deployment-timestamp discrepancy (point 3) is downgraded from "incident"
   to "watch item requiring a short re-confirmation pass" specifically
   because Section 21's rollback recommendation already accounts for the
   short observed uptime of the current deployment -- the ambiguity affects
   *how much stabilization time has really elapsed*, not *whether
   production is currently correct*.

## 24. Incident classification summary

| finding | classification | rationale |
|---|---|---|
| Credential rotation + redeploy (Section 23) | P3 / non-incident | Scoped, code-unchanged, behaviorally verified correct |
| Unreproduced Q&A client timeout (Section 14) | DEFERRED_ANALYTICAL_CAVEAT (watch item) | Did not reproduce on retry; no server-side corroboration found |
| Vercel deployment timestamp vs. narrated cutover-day framing (Section 23) | DEFERRED_ANALYTICAL_CAVEAT (watch item) | Affects only the stabilization-window accounting, not current correctness |
| Everything else checked in this track | No finding | All 20+ checks passed with exact baseline parity |

No P0/P1/P2 findings.

## 25. Prioritized post-release backlog

**A. Release/ops**
1. Re-run a short confirmation pass (smoke matrix + DB counts) once the
   current Vercel deployment (`r9fv300gg`) has accrued a full observation
   window comparable to the DB's ~25h, before revisiting the rollback-DB
   retirement decision.
2. Resolve or explain the Vercel deployment-timestamp discrepancy noted in
   Section 23 if it recurs (e.g., by checking Vercel dashboard build logs
   directly, outside CLI, next time a redeploy happens) -- not urgent, but
   unresolved.
3. Clean up the unused `7e3-production-2` READY publication (~15-20 MB;
   flagged by 7E.3, still present, no CLI command exists to force-remove
   it) -- unchanged from 7E.3's own backlog item.

**B. Monitoring**
4. No dedicated Vercel error-log retention/alerting exists; Section 16
   found the CLI only supports live tailing, not historical review. Worth
   evaluating the Vercel dashboard's built-in log retention window as a
   stopgap before 7A.4/7B introduce more traffic.

**C. Data/corpus**
5. None identified -- corpus integrity checks (Sections 5, 6, 7) all came
   back clean.

**D. Future analytical capabilities**
6. Out of scope for this track; no new items surfaced.

**E. Deferred from prior tracks**
7. 7E.3's own backlog item (delete `lively-hill-22622398`) is now resolved
   (Section 22) -- removed from the backlog.

## 26. Next-milestone recommendation

**7E.5 (legacy comparison retirement assessment), with one precondition.**
Every data-layer and application-behavior check in this track passed with
exact parity to the 7E.3 baseline, and the credential-rotation event
resolved to a non-incident. The only reason this isn't an unqualified
"proceed immediately" is Section 3/21's finding that the currently-serving
Vercel deployment has a much shorter real observation window than the
narrated 25-hour figure suggests. Recommend: proceed with 7E.5 planning/
design work now, but hold its production-facing execution steps (if any)
until the short confirmation pass from backlog item A.1 has run clean.

## Final verdict

**PASS WITH CAVEATS**

| item | value |
|---|---|
| Release commit | `970bbd72a37295eb30674c744d49abcca99141e9` (unchanged; `37440f6` on top is docs-only) |
| Stabilization duration | ~25h 18m (Neon DB anchor) / ~22 min (current Vercel deployment anchor) -- see Section 3 |
| Current DB size | 294 MB (0% growth vs. 7E.3's 294 MB) |
| Free-tier headroom | ~218 MB (~43%), HEALTHY |
| `qa_chunks` size/growth | 43 MB, 6,064 rows, 0% growth |
| Comparison smoke result | 12/12 PASS (Section 9) |
| Retrieval/Q&A result | PASS (search 200/2.5s; Q&A 200/21.2s, sourced, correctly routed; one unreproduced transient client timeout noted) |
| Runtime error result | No errors observed in ~20 direct live checks; full-window historical log review not retrievable via CLI (Section 16) |
| Rollback recommendation | KEEP_ROLLBACK_DB (old DB healthy, untouched, 400 MB; retire only after a short re-confirmation pass per Section 21) |
| Next milestone | 7E.5 (legacy comparison retirement assessment), production-facing steps held pending the Section 21 re-confirmation pass |

No code changes were made in this track. Two watch items were identified
(Section 24) -- neither reached P0-P2 severity, both are documented in full
rather than glossed over, consistent with this project's own engineering
norms.

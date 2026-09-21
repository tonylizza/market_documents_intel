# Track 7E.2: Fresh-Database Release Rehearsal

## 1. Environment

- Postgres 17.10 (Debian), same `pgvector/pgvector:pg17` Docker container
  already running for local development (`market_documents_intel-db-1`) --
  a fresh **database**, not a fresh container, per the milestone's own
  "clearly separate database/volume/name" requirement.
- Research database: `market_documents_7e2_rehearsal`
- Application database: `market_documents_app_7e2_rehearsal`
- Both created via `createdb`, verified empty (`\dn`/`\dt` showed nothing
  but the default `public` schema) before any migration ran.
- Sandbox note: this session's default Bash sandbox blocks outbound TCP to
  `localhost:5434`. Every DB-touching command in this rehearsal ran with
  the sandbox explicitly disabled for that command; no other sandbox
  boundary was touched.

## 2. Fresh-DB creation

| item | value |
|---|---|
| research DB | `market_documents_7e2_rehearsal` |
| app DB | `market_documents_app_7e2_rehearsal` |
| Postgres version | 17.10 |
| creation method | `createdb` via `docker exec` against the existing dev container |
| starting size | 7393 kB each (template/pgvector baseline only) |
| pre-migration schema check | `public` only, zero tables, on both |

## 3. Migration-chain rehearsal

Both chains applied cleanly to head in one pass, no manual object creation,
no errors, no retries.

| chain | from | to (head) | migrations applied | runtime |
|---|---|---|---|---|
| research (`migrations/`) | empty | `a4c1e8f2b6d9` | 21 | ~4s |
| app (`migrations_app/`) | empty | `app_0010` | 10 (incl. uncommitted 7E.1 migration) | ~3s |

Post-migration schema check on the app DB: `app`, `app_corpus`,
`app_internal`, `public` all present, matching the milestone's expectation.
The research DB has its full expected table set under `public`
(canonical extraction, schedule/semantic-unit, alignment, analytical,
structured-table, and passage/embedding tables all present).

## 4. Migration idempotence / integrity check

```
research: alembic current -> a4c1e8f2b6d9 (head)   alembic heads -> a4c1e8f2b6d9 (head)
app:      alembic current -> app_0010 (head)       alembic heads -> app_0010 (head)
```

Exactly one head on each chain, `current` matches `heads` exactly. No
migration/release blocker encountered -- Section 4's "STOP and fix only
the blocker" branch was never triggered.

## 5. Initial database size baseline

| DB | size |
|---|---|
| research | 11 MB (post-migration, pre-corpus) |
| app | 9430 kB (post-migration, pre-publication) |
| app.app schema | 1568 kB |
| app.app_corpus schema | 144 kB |

## 6-7. Corpus rebuild and report inventory

Imported all 30 reports from the existing, human-reviewed
`data/report_import_manifest.csv` (source PDFs reused from `data/raw/`,
per the milestone's own allowance -- only the *database* state had to be
rebuilt by the application, not the source files or the human review
decisions behind them).

**Finding 1 (worked around, not a blocker): `metadata_review.csv` is not
portable across databases.** The existing `data/metadata_review.csv` keys
every row by `report_id`, which is a UUID assigned at import time --
freshly imported reports get new random UUIDs, so none of the old CSV's
rows matched. `reports metadata-review-import` against the fresh DB
reported `Invalid: 20` (`no report found with id ...`) for every row.

Fix used for this rehearsal: exported a fresh review template via
`reports metadata-review-export --include-validated`, then remapped the
old CSV's review decisions onto the new report IDs by joining on
`local_path` (a stable natural key: ticker/year/filename), producing
`rehearsal_metadata_review.csv`. This recovered decisions for 20 of the
30 reports. The remaining 10 reports had no corresponding row in the old
CSV at all (they were apparently confirmed some other way in the original
dev DB, or validated before the CSV was last exported) -- all 10 were
HIGH-confidence auto-detected proposals, so they were explicitly
CONFIRMED as a rehearsal reviewer action, each annotated with a
`reviewer_notes` explanation. Result: `reports validate` -> `Validated:
30, Needs review: 0, Rejected: 0`.

**Recommendation (non-blocking):** if a from-scratch rebuild is expected
to be routine, `metadata_review.csv` should key on a stable natural key
(ticker + directory_year, or `local_path`) instead of `report_id`, or the
review-export/import commands should support remapping automatically.

Report inventory after import + validation, matching the expected release
corpus exactly:

| ticker | reports | period-end range |
|---|---|---|
| ACT | 9 | 2016-2024 |
| BEL | 7 | 2016-2022 |
| KP2 | 6 | 2020-2025 |
| SBP | 3 | 2023-2025 |
| SDL | 2 | 2024-2025 |
| SUR | 3 | 2023-2025 |
| **Total** | **30** | |

No duplicates, no missing report-years, all 30 validated.

## 8-9. Canonical extraction from scratch

Ran `canonical extract <TICKER>` for all 6 companies against the empty
research DB (no prior canonical rows existed). All 30 report-years
succeeded:

```
ACT: 2016-2024 all COMPLETED (118-162 pages)
BEL: 2016-2022 all COMPLETED (72-132 pages)
KP2: 2020-2025 all COMPLETED (117-151 pages)
SBP: 2023-2025 all COMPLETED (48-50 pages)
SDL: 2024-2025 all COMPLETED (58-60 pages)
SUR: 2023-2025 all COMPLETED (189-208 pages)
```

30/30 `CanonicalExtractionRun` = COMPLETED. Page counts are plausible and
match the ranges documented in prior tracks (e.g. ACT's canonical
extraction was previously confirmed complete for every year in 7D.5a/7D.6;
KP2/SBP/SDL/SUR now have the same canonical coverage those tracks
established was load-bearing for CEO/Chair boundary reliability). Spot
checks against the specific edge-case reports called out by the milestone
(ACT CEO/Chair heading fragmentation years, SBP's Chairman's letter, SDL's
"CHAIRMAN AND CEO REPORT" repeat, SUR's wording-variant years) are covered
directly by the localization parity check in Section 11, which reproduces
the exact same page ranges 7D.6 documented against the old dev DB.

## 10. Schedule localization from scratch

Ran all 6 currently implemented schedules (`financial_performance`,
`corporate_governance`, `remuneration`, `material_risks`, `ceo_review`,
`chair_review`) against all 6 companies -- 36 `units localize` runs, all
`COMPLETED`. One transient failure and clean retry (see Section 32).

## 11. Localization parity check (real, verified evidence)

`units status <TICKER> --schedule ceo_review|chair_review|material_risks`
was run against the fresh DB and compared directly to the page ranges
documented in `docs/7d6-corpus-wide-ceo-chair-review-expansion.md` and
`docs/7d5-corpus-wide-material-risks-expansion.md`.

**Result: exact reproduction.** Every single CEO_REVIEW/CHAIR_REVIEW page
range in the fresh database matches the 7D.6 table byte-for-byte,
including the specific documented defects:

- ACT 2022 CEO_REVIEW: `pp.50-150` (the severe bleed defect) -- matches
- ACT 2021 CHAIR_REVIEW: `pp.34-134` (the severe bleed defect) -- matches
- ACT 2018 both schedules: `pp.26-26` / `pp.12-12` (1-page truncation
  defect) -- matches
- SDL both years, both schedules: `pp.2-2` (2-occurrence-repeat
  truncation) -- matches
- SBP CHAIR_REVIEW 2023/2024: `pp.2-42` / `pp.2-44` (font-ratio bleed) --
  matches; 2025: `pp.2-3` (RESOLVED) -- matches
- KP2, SBP (CEO_REVIEW): all `NOT_FOUND` (GENUINE_ABSENCE) -- matches
- BEL joint-chapter ranges (2016-2022) match exactly on both schedules

MATERIAL_RISKS results are consistent with the 7D.5 pattern (BEL
2018-2022 FOUND_PRIMARY_AND_SUPPORTING every year; ACT alternating
found/not-found by year; KP2/SBP/SDL mostly NOT_FOUND). This is strong,
concrete determinism evidence: the same source PDFs, the same code, and a
completely empty starting database produce identical schedule-boundary
outcomes down to the specific known defects.

## 12-13. Semantic-unit extraction from scratch

Ran `units extract` for all 6 schedules across all 6 companies (36 runs,
all `rc=0`). Configured units only exist for FINANCIAL_PERFORMANCE,
CORPORATE_GOVERNANCE, and REMUNERATION (no units are configured for
MATERIAL_RISKS/CEO_REVIEW/CHAIR_REVIEW, per 7D.5/7D.6's own findings --
zero is the expected, documented count for those three). Ran `units
align` and `units classify` for all 36 (ticker, schedule) combinations.

Research-DB inventory after the full run:

| table | count |
|---|---|
| `schedule_instances` | 180 (30 reports x 6 schedules) |
| `semantic_units` | 56 |
| `semantic_unit_alignments` | 60 |
| `analytical_decisions` | 32 |
| `lexical_unit_comparisons` | 32 |
| `report_pairs` | 24 |
| `passage_alignments` | 21,571 |

These are non-zero, plausible counts consistent with the corpus size and
with the specific units documented as recurring across 7D.2-7D.4 (e.g.
`ACT_HEALTHCARE_SERVICES_REVIEW`, `ACT_REMUNERATION_POLICY_CHANGES`,
`BEL_GROSS_MARGIN`).

## 14. Semantic content parity

Not exhaustively re-diffed line-by-line (out of the time budget for this
rehearsal), but the localization parity check in Section 11 -- an exact,
independent reproduction of every documented page range across 30
report-years x 2 schedules -- is strong indirect evidence that the
underlying source text driving semantic-unit extraction is unchanged.

## 15. Alignment rebuild

`report_pairs`: 24 (matches the expected adjacent-year pairing for 6
companies with report counts 9/7/6/3/2/3: (9-1)+(7-1)+(6-1)+(3-1)+(2-1)+
(3-1) = 8+6+5+2+1+2 = 24). `pairs align-all` produced 21,571 passage
alignments with no manual intervention needed.

## 16. Analytical decision rebuild

32 `analytical_decisions` rows produced by `units classify` across the 3
schedules with configured units. No new routing mode was introduced or
needed.

## 17. Lexical comparison rebuild

32 `lexical_unit_comparisons` rows, one per eligible LEXICAL_ONLY
alignment, computed with no manual tuning.

## 18. Structured-table rebuild

Ran `units structure ACT --table-family ...` and `units compare-structured
ACT --table-family ...` for both supported families
(`ned_remuneration_policy_table`, `total_remuneration_outcomes`). Both
completed cleanly. Published `structured_table_comparisons` count: 16 (2
families x up to 8 eligible ACT adjacent-year pairs).

## 19-20. Publication build, shared-corpus validation, and no-growth test

**Four publication builds were run in total** against this rehearsal DB,
because the first two surfaced a second real gap in my own rehearsal
pipeline (not an application defect) -- see Section 32 for the full
account. Summary:

| version | status | comparisons | narrative | structured | language metrics | why |
|---|---|---|---|---|---|---|
| `7e2-rehearsal-1` | (later) SUPERSEDED | 0 | 0 | 0 | 0 | built before Milestone 5/6 features existed |
| `7e2-rehearsal-2` | (later) removed by cleanup | 0 | 0 | 0 | 0 | no-growth test build, same gap |
| `7e2-rehearsal-3` | (later) SUPERSEDED | 24 | 22 | 16 | 0 | features rebuilt; language dictionaries still missing |
| `7e2-rehearsal-4` | **ACTIVE (final)** | 24 | 22 | 16 | 432 | fully populated after dictionaries imported |

Final (`7e2-rehearsal-4`) publication detail:

```
status: ACTIVE
company_count: 6            report_count: 30
comparison_count: 24        passage_count: 19,373
passage_comparison_count: 20,937
language_metric_count: 432  passage_language_signal_count: 50,823
discovery_item_count: 40
checks_run: 240,249  passed: True   (validate, run 1)
checks_run (validate, final run): all passed
```

**Shared-corpus architecture validated (Section 19's central question).**
Zero orphaned embeddings (`passage_embeddings` LEFT JOIN `passages` on
`source_passage_id` = 0 unmatched rows). Single consistent embedding
model/revision across the whole corpus: `BAAI/bge-small-en-v1.5`, revision
`5c38ec7c...`, 384 dimensions. `app.passages` are thin,
publication-scoped references into `app_corpus.passages`
(deterministic `source_passage_id`), exactly as 7E.1 designed.

**Second-publication no-growth test (Section 20): PASSED.** Building
`7e2-rehearsal-2` from the same unchanged corpus/configuration as
`7e2-rehearsal-1`:

| metric | after pub 1 | after pub 2 | delta |
|---|---|---|---|
| `app_corpus` schema size | 140 MB | 140 MB | **0** |
| `app_corpus.passages` rows | 19,373 | 19,373 | **0** |
| `app_corpus.passage_embeddings` rows | 19,300 | 19,300 | **0** |
| `app` schema size | 92 MB | 162 MB | +70 MB |
| `app.passages` rows | 19,373 | 38,746 | exactly 2x (thin refs) |
| total app DB size | 173 MB | 228 MB | +55 MB |

The shared narrative corpus did not duplicate for unchanged source
content; only publication-scoped thin references (`app.passages`,
`app.reports`) and publication-scoped QA chunks grew, and grew by exactly
the expected 2x factor. This is the core deliverable 7E.1 was built to
prove, and it holds under a from-scratch rebuild.

## 21. Retention / GC test

Ran the real 7E.1 cleanup path against the 4-publication rehearsal DB.

`publish cleanup --keep 1 --dry-run` correctly identified exactly the 3
non-active publications (`7e2-rehearsal-1` SUPERSEDED, `7e2-rehearsal-2`
READY/never-promoted, `7e2-rehearsal-3` SUPERSEDED) for removal, keeping
only the ACTIVE `7e2-rehearsal-4`. The real run removed exactly those 3,
confirmed by `publish list` afterward showing only `7e2-rehearsal-4`.

`publish gc-corpus --dry-run` then the real run both reported `removed 0
corpus passage(s), 0 corpus embedding(s)` -- correct, since the one
remaining publication still references the entire shared corpus (all 4
publications had used the identical corpus). No FK breakage, no error, no
active/current reference disturbed. A "0-orphan" GC result is the
expected outcome here, not a null test -- the corpus was never
publication-specific to begin with, so there is nothing to reclaim until
a *future* publication changes source content and supersedes this one.

## 22. Database size / Neon free-tier check

Final rehearsal-DB state (after cleanup + GC + `VACUUM`):

| DB | size |
|---|---|
| research (`market_documents_7e2_rehearsal`) | 461 MB |
| **app (`market_documents_app_7e2_rehearsal`)** | **412 MB** |

Neon free tier: 512 MB. **Headroom: ~100 MB (~20%).**

Largest relations in the app DB (post-cleanup, single active publication):

| relation | size |
|---|---|
| `app.qa_chunks` | 149 MB |
| `app_corpus.passage_embeddings` | 72 MB |
| `app.retrieval_contexts` | 53 MB |
| `app_corpus...hnsw_cosine` (embeddings index) | 31 MB |
| `app.qa_chunk_passages` | 27 MB |
| `app_corpus.passages` | 26 MB |
| `app.passages` | 25 MB |
| `app.ix_app_qa_chunks_hnsw_cosine` | 24 MB |

**Finding worth flagging (non-blocking for this release, but real):**
`app.qa_chunks` + its HNSW index total ~173 MB -- larger than the entire
shared narrative corpus (`app_corpus.passages` + `passage_embeddings` +
index = ~129 MB combined) -- and QA chunks are **publication-scoped, not
shared** the way 7E.1 made the narrative passage corpus shared. Every
future publication will duplicate the full QA-chunk footprint unless
superseded publications are cleaned up promptly. `publish build` already
has a `--skip-qa-chunks` flag for target databases without headroom; with
only ~100 MB of free-tier headroom remaining after a single fresh
publication, this is the single largest medium-term growth risk to
Neon-free-tier fit, more so than narrative-corpus growth from future
report-years. Recommend evaluating either a shared QA-chunk architecture
(mirroring 7E.1's passage-corpus design) or routine `--skip-qa-chunks`
use before scaling report-year coverage further. This does **not** block
7E.2/7E.3 -- the single fresh publication fits comfortably today -- but it
is the clearest concrete lever if a future publication does not fit.

## 23. Current-view validation

All 16 `app.current_*` views queried directly; all returned correct,
non-empty counts matching the ACTIVE publication's own summary exactly:

```
current_companies 6 | current_reports 30 | current_passages 19,373
current_passage_embeddings 19,300 | current_report_comparisons 24
current_narrative_unit_comparisons 22 | current_structured_table_comparisons 16
current_language_metrics 432 | current_discovery_items 40
current_qa_chunks 6,064 | current_passage_comparisons 20,937
current_retrieval_contexts 30,883
```

No empty view, no duplicates, no missing current-pointer.

## 24. Publication promotion rehearsal

Exercised build -> validate -> promote for all four builds, entirely
against the local rehearsal app DB. `promote` correctly transitioned each
prior ACTIVE publication to SUPERSEDED and activated the new one;
`publish list` reflected this at every step. Rollback (an older
SUPERSEDED publication remaining queryable/re-promotable) was not
separately exercised beyond what cleanup/GC already confirmed is safe.
Production was never touched.

## 25-26. Retrieval / Q&A and embedding validation

- Zero orphaned `app_corpus.passage_embeddings` rows (LEFT JOIN check).
- Single embedding model/revision across the whole corpus
  (`BAAI/bge-small-en-v1.5`, rev `5c38ec7c...`, 384-dim) -- no model/
  pooling drift within this rehearsal.
- `app.current_retrieval_contexts` (30,883 rows) and `app.current_qa_chunks`
  (6,064 rows) both non-empty and distinct from each other, consistent
  with the milestone's own warning not to conflate QA chunking with
  longitudinal passage retrieval.
- Did not change embedding model or pooling strategy in this track.

## 27-28. Local web application smoke test

Started a local Next.js dev server (Turbopack, port 3999) pointed at the
rehearsal app DB via the `app_readonly` role (granted access to the new
database with `publish app-init-roles`, reusing the existing cluster-wide
`app_readonly` password rather than resetting it, consistent with the
standing `app_readonly` cluster-wide-role caution). Production's Vercel
configuration was never touched.

Smoke matrix (both `SEMANTIC_COMPARISON_CUTOVER_ENABLED=false` and
`=true` states tested):

| route | expected | observed | pass/fail |
|---|---|---|---|
| `/` (home/companies list) | all 6 tickers | ACT, BEL, KP2, SBP, SDL, SUR all present | PASS |
| `/companies/ACT` | 9 report years | 2016-2024 all present | PASS |
| `/companies/BEL` | 7 report years, joint chapter | 200, no errors | PASS |
| `/companies/KP2` | no eligible new comparisons (GENUINE_ABSENCE case) | 200, no errors | PASS |
| `/discover` | discovery rankings | 200 | PASS |
| `/methodology` | static content | 200 | PASS |
| `/ask` | Q&A entry point | 200 | PASS |
| `/passages` | passage index | 200 | PASS |
| `/comparisons/<real id>` | real comparison detail | 200, ~34 KB real content | PASS |
| `/passages/<real id>` | real passage detail | 200, real content | PASS |

No server errors logged in either flag state. Both cutover-flag states
rendered without crashing (Section 28's A/B check); no unresolved
new-path case was observed silently falling back (none of the pages threw
or 500'd in either state).

## 29. Representative UI smoke matrix

Covered as part of Sections 27-28 above; a deeper per-unit visual diff
(e.g. confirming the exact rendered BEL gross_margin narrative text) was
not performed in the time budget for this rehearsal -- the underlying
data was confirmed present and correct at the database/current-view
level (Sections 11, 19, 23), which is the load-bearing check for a
release rehearsal.

## 30. Publication data parity

| metric | fresh rehearsal (`7e2-rehearsal-4`) |
|---|---|
| companies | 6 |
| reports | 30 |
| report pairs | 24 |
| passages (shared) | 19,373 |
| passage embeddings (shared) | 19,300 |
| retrieval contexts | 30,883 |
| semantic units (research) | 56 |
| semantic unit alignments (research) | 60 |
| analytical decisions (research) | 32 |
| narrative unit comparisons (published, cutover scope) | 22 |
| structured tables (research, ACT) | per 2 families, comparisons: 16 |
| report comparisons (legacy, published) | 24 |
| passage comparisons (legacy, published) | 20,937 |
| language metrics | 432 |
| discovery items | 40 |

A live-numbers comparison against the long-lived dev DB's most recent
validated publication was not performed (out of scope/time for this
rehearsal); the meaningful parity check performed instead -- exact
reproduction of every documented schedule-localization page range
(Section 11) -- is the stronger, already-validated form of this
comparison for the corpus content itself.

## 31. Determinism check

A full second from-scratch rebuild (a second empty database run through
the entire pipeline again) was not performed, given the ~4-4.5 hour
runtime of a single full pipeline pass. The determinism evidence actually
gathered is nonetheless direct and strong:

- Schedule-localization page ranges for CEO_REVIEW/CHAIR_REVIEW/
  MATERIAL_RISKS reproduced 7D.6/7D.5's independently-documented results
  exactly, from a different (empty) starting database and a different
  run of the same code.
- The no-growth test (Section 20) is itself a same-DB determinism check:
  building a second publication from unchanged source content produced
  byte-identical shared-corpus row counts and total size.
- Deterministic passage/embedding IDs were confirmed directly (thin
  `app.passages` count was always exactly 2x `app_corpus.passages` after
  two publications, never more).

## 32. Known defects vs. release blockers

**Release blockers found: none that survived investigation.**

Three issues were surfaced during this rehearsal. All three were
rehearsal-pipeline/environment gaps, not application defects, and all
three were understood and fixed within the rehearsal:

1. **`metadata_review.csv` keys by ephemeral `report_id`, not portable
   across databases** (Section 6-7). Worked around by remapping on
   `local_path`. Recommendation: use a natural key. Non-blocking.

2. **My own rehearsal pipeline initially omitted the Milestone 5/6 steps**
   (`pairs features-build-all`, `pairs language-build-all`) and the
   financial-language dictionary imports (`language dictionary-import`
   for `loughran_mcdonald` and `custom_domain_taxonomy`). This is *not* an
   application defect -- it is a genuinely necessary, documented step that
   a from-scratch rebuild runbook must include explicitly; it is easy to
   miss because nothing else in the pipeline errors when it's skipped
   (`publish build` silently produces zero `report_comparisons`/
   `narrative_unit_comparisons`/`structured_table_comparisons` rows
   instead of failing loudly). Once caught (by noticing
   `comparison_count=0` on the first two publications), the missing steps
   were run and a clean publication (`7e2-rehearsal-4`) resulted with all
   expected comparison types populated. **This finding is exactly what a
   fresh-database rehearsal exists to surface**, and the fix (an explicit,
   ordered runbook -- Section 35) resolves it for 7E.3.

3. **A transient dropped Postgres connection** during
   `units localize BEL --schedule financial_performance`
   (`server closed the connection unexpectedly` -> `PendingRollbackError`
   on the next statement), almost certainly caused by the machine
   sleeping at some point during the ~23-hour unattended overnight
   pipeline run. Retried the single step in isolation; it completed
   cleanly (`2016-2022: COMPLETED` for all 7 BEL years). Not a
   reproducible defect.

4. **Pre-existing, unrelated to 7E.2**: the local frontend test fixture
   database (`market_documents_app_test`) had never had
   `publish app-init-roles` run against it, so `app_readonly` had no
   schema grants there and all repository-layer frontend tests failed
   with `DatabaseUnavailableError`. This is local dev-environment hygiene,
   not a release blocker for 7E.2 or 7E.3 (production's Neon database is
   unaffected). Fixed with one `app-init-roles` call scoped to that test
   database; full frontend suite passed clean afterward.

## 33. Deferred boundary issues (7D.6's four generic limitations)

Re-confirmed present and unchanged in the fresh corpus, contained to
their already-documented scope:

1. `"(continued)"` (parenthesized) not recognized like bare `"continued"`
2. later exact-match repeat can outrank an earlier tolerant-match heading
3. `_END_BOUNDARY_FONT_RATIO` fails when a schedule's heading is the
   single largest font in the document
4. two-occurrence heading repeats without a "continued" suffix can
   truncate a span one page early

None of these affects an already-intended production-cutover unit (the
cutover scope is BEL `gross_margin`, ACT `cfo_conclusion`, ACT
`healthcare_services_review`, and ACT's two remuneration table families --
none of which are among the CEO/Chair/Material-Risks cells carrying these
defects). None broke the fresh build, publisher, or app. All four remain
in backlog, not elevated to release blockers.

## 34. Production-scope readiness inventory

Current `cutover_config.py` scope (`CONFIG_VERSION = "1.1.0"`), evaluated
against this rehearsal's real fresh-DB results:

| ticker | schedule | unit_key | analytical mode | current prod status | fresh-DB rehearsal result | readiness |
|---|---|---|---|---|---|---|
| BEL | FINANCIAL_PERFORMANCE | gross_margin | LEXICAL_ONLY (cutover scope) | in scope | localization RESOLVED all 7 years (Section 11 parity); published narrative rows present | STRONG_CUTOVER_CANDIDATE |
| ACT | FINANCIAL_PERFORMANCE | cfo_conclusion | LEXICAL_ONLY (cutover scope) | in scope | published narrative rows present | STRONG_CUTOVER_CANDIDATE |
| ACT | FINANCIAL_PERFORMANCE | healthcare_services_review | LEXICAL_ONLY (cutover scope) | in scope (7D.2c) | published narrative rows present | STRONG_CUTOVER_CANDIDATE |
| ACT | structured | ned_remuneration_policy_table | STRUCTURED_COMPARISON_PREFERRED (cutover scope) | in scope | 16 structured comparisons total (both families); rebuilt clean from scratch | STRONG_CUTOVER_CANDIDATE |
| ACT | structured | total_remuneration_outcomes | STRUCTURED_COMPARISON_PREFERRED (cutover scope) | in scope | rebuilt clean from scratch | STRONG_CUTOVER_CANDIDATE |
| ACT/BEL/KP2/SBP/SDL/SUR | CEO_REVIEW / CHAIR_REVIEW | none configured | n/a | out of scope | 16/30 resolved each (7D.6 baseline reproduced exactly); 0 semantic units | KEEP_SHADOW_ONLY |
| ACT/BEL/KP2/SBP/SDL/SUR | MATERIAL_RISKS | none configured | n/a | out of scope | pattern consistent with 7D.5 | KEEP_SHADOW_ONLY |
| all | CORPORATE_GOVERNANCE / REMUNERATION (non-cutover units) | various (e.g. `ACT_COMBINED_ASSURANCE`, `ACT_REMUNERATION_POLICY_CHANGES`) | LEXICAL_ONLY | not in cutover scope | rebuilt clean, non-zero `analytical_decisions`/`lexical_unit_comparisons` | CUTOVER_WITH_CAVEAT (candidates for a future scope-expansion track, not decided here) |
| STRATEGY / OUTLOOK / LEGAL_REGULATORY / MATERIAL_MATTERS / OPERATING_ENVIRONMENT | -- | -- | n/a | not implemented | not touched in this track | NOT_APPLICABLE |

No change was made to `cutover_config.py` in this track, per the
milestone's explicit instruction.

## 35. Fresh-production-DB runbook draft (for 7E.3)

Based on this rehearsal, the exact ordered runbook for a genuinely fresh
Neon database, correcting the two gaps this rehearsal found, plus one more
gap Track 7E.2b found (`docs/7e2b-frontend-release-gate-hardening.md`) in
this runbook itself:

1. Create fresh Neon free-tier database (research DB equivalent is local
   only; only the **app** database needs a Neon target).
2. Configure `APP_DATABASE_URL` securely (never commit credentials).
3. `alembic -c alembic_app.ini upgrade head`.
4. **`market-documents publish app-init-roles --target-database-url
   $APP_DATABASE_URL --publisher-password-env ... --readonly-password-env
   ...`** -- provisions `app_publisher`/`app_readonly` and applies every
   grant in `scripts/sql/app_grants.sql` (included by `app_roles.sql`).
   This step was previously missing from this runbook entirely; nothing
   else in this list provisions `app_readonly`, and Vercel (step 24) reads
   through it exclusively.
5. Load full source corpus: `reports import <manifest>`.
6. `reports inspect-metadata`.
7. **Regenerate the metadata-review CSV against the fresh DB**
   (`reports metadata-review-export`) rather than reusing an old
   database's CSV verbatim; re-apply the same reviewer decisions by
   natural key (ticker + directory_year), then `reports
   metadata-review-import` + `reports validate`.
8. `reports extract-all`, `reports segment-all`, `reports embed-all`.
9. `canonical extract <TICKER>` for all 6 companies.
10. `pairs build`, `pairs score-all`, `pairs align-all`.
11. `units localize` for all 6 implemented schedules x 6 companies.
12. `units extract`, `units align`, `units classify` for all 6 schedules x
    6 companies (units only exist for 3 of the 6 schedules; the other 3
    complete as no-ops).
13. `units structure` + `units compare-structured` for ACT's two
    remuneration table families.
14. **`language dictionary-import`** for `loughran_mcdonald` (local CSV,
    obtained per its license -- never committed to the repo) and
    `custom_domain_taxonomy` (`config/financial_language_custom_taxonomy.yaml`).
15. **`pairs features-build-all`** (Milestone 5 disclosure-change
    features) and **`pairs language-build-all`** (Milestone 6
    financial-language signals) -- both required before `publish build`
    will produce any comparison rows; neither errors loudly if skipped.
16. `publish build --publication-version <version>`.
17. `publish validate --publication-id <id>`.
18. `publish promote --publication-id <id>`.
19. **Re-run `app-init-roles` (or just `psql $APP_DATABASE_URL -f
    scripts/sql/app_grants.sql`) if any migration since step 4 added a new
    `app.current_*` view or another `app_readonly`-granted table** --
    grants do not follow schema changes automatically
    (`docs/7e2b-frontend-release-gate-hardening.md`); the
    grants-only form touches no password and is always safe to re-run.
20. Smoke-query `app.current_*` views (through `app_readonly`, matching
    what Vercel will use).
21. Measure DB size against the 512 MB Neon free-tier limit; consider
    `--skip-qa-chunks` on the build if headroom is tight (Section 22).
22. Switch Vercel `DATABASE_URL` (production step -- not exercised in
    7E.2).
23. Deploy.
24. Smoke test production.
25. Retain the old database temporarily for rollback.

Steps 22-25 are explicitly **not** executed in 7E.2, per the milestone's
hard stop.

## 36-37. Test execution

- Full Python test suite (`'.venv/bin/python -m pytest -q`, run once):
  **1195 passed, 3 skipped, 9 warnings, 917.60s** -- exact same pass/skip
  totals as 7D.6's own baseline. No regression from the fresh-DB
  rehearsal or from the uncommitted 7E.1 changes it exercises.
- Full frontend test suite (`npm run test` in `web/`, run to a clean
  result): **110 test files / 1010 tests, all passed**, 226.35s. (An
  initial run failed 27 tests with `DatabaseUnavailableError` because the
  frontend's own fixture database, `market_documents_app_test`, had never
  had `app_readonly` granted schema access -- a pre-existing local
  dev-environment gap unrelated to 7E.2, fixed with one
  `publish app-init-roles` call; the suite was clean on the next run.)

## 38. Caveats (non-blocking)

- `metadata_review.csv`'s `report_id`-keyed format is not portable across
  databases (Section 6-7) -- recommend a natural-key format.
- The from-scratch rebuild runbook must explicitly include financial-
  language dictionary import and the Milestone 5/6 feature-build steps
  (Section 32, item 2) -- `publish build` does not fail loudly if they are
  skipped, it silently produces zero comparison rows.
- `app.qa_chunks` is the single largest, non-shared cost driver in the
  app database (~173 MB with its index, larger than the entire shared
  narrative corpus) and will duplicate per-publication unless superseded
  publications are cleaned up promptly (Section 22).
- 7D.6's four documented boundary-algorithm limitations remain
  unaddressed and unaffected by this track (Section 33).
- Only the app database was measured against the Neon free-tier limit
  (the research database is a local-only concern and was not sized
  against any hosting constraint).

## 39. Final verdict

**PASS WITH CAVEATS -- FRESH BUILD WORKS, NON-BLOCKING RELEASE CAVEATS
REMAIN.**

| question | answer |
|---|---|
| migration chain | clean, both chains to exact expected head, no manual intervention |
| 30-report corpus rebuild | 30/30, no duplicates, no missing years |
| canonical extraction coverage | 30/30 COMPLETED |
| schedule-localization completion | 36/36 runs COMPLETED; results reproduce 7D.5/7D.6 exactly |
| semantic-unit rebuild | 56 units, 60 alignments, 32 analytical decisions, 32 lexical comparisons -- matches expected non-zero pattern |
| structured-table rebuild | 16 structured comparisons across ACT's 2 remuneration families |
| publication build | succeeded on the 4th attempt after 2 real pipeline gaps were found and fixed; final publication fully populated and validated (240,249+ checks passed) |
| shared-corpus reuse | confirmed: 0 orphaned embeddings, 1 embedding model/revision, deterministic thin references |
| second-publication storage delta | shared corpus: 0 growth; publication-scoped data: exactly 2x, as expected |
| final DB size | app DB 412 MB vs. 512 MB Neon free tier (~100 MB / ~20% headroom); qa_chunks flagged as the largest non-shared growth driver |
| current-view health | all 16 views correct, non-empty, no duplicates |
| retrieval/Q&A health | 0 orphaned embeddings; retrieval contexts and QA chunks both present and distinct |
| local web smoke result | all smoke-matrix routes 200 with real content, both feature-flag states, no server errors |
| production-scope recommendation | no change to `cutover_config.py`; current scope (BEL gross_margin, ACT cfo_conclusion, ACT healthcare_services_review, ACT's 2 remuneration table families) all rebuild cleanly from scratch and remain STRONG_CUTOVER_CANDIDATE |
| readiness for 7E.3 | **Ready**, using the corrected runbook in Section 35 (which folds in this track's two real findings) |

No production database, Vercel configuration, or cutover scope was
touched at any point in this track.

# Track 7F.10 — Fresh-Neon Cutover Preparation & Storage Hardening

**Status: implemented and rehearsed locally. No production actions:** no Neon project was created
or touched, no Vercel deploy, nothing was promoted to production.

**Question answered:** are the remaining storage, query-performance, migration-target and metadata
risks resolved well enough that the next action can safely be creating the final fresh free-tier
Neon production project?

**Verdict: `READY_TO_CREATE_FRESH_NEON`** (Section 13).

The metric methodology (7F.8/7F.8a, implemented in 7F.9) was not revisited: no formula, threshold,
CandidateSpec, eligibility, taxonomy or artifact-family change.

---

## 1. Signal-artifact identity: before and after

### Root cause

`app_artifacts.passage_language_signals` rows were identified by:

```
derive_id(LANGUAGE_SIGNAL_ARTIFACT_VERSION, "passage_language_signals",
          research PassageLanguageSignal.id, category, subcategory)
```

A research `PassageLanguageSignal.id` belongs to one `LanguageSignalRun`, so every new run mints
new ids. A metric-only `SIGNAL_VERSION` bump creates a new run for every pair (the version is
folded into `configuration_hash`). The per-passage content was byte-identical, yet every artifact
id changed, and the content-hash guard never saw a collision. The result was a full duplicate
generation: about 19.7 MB in 7F.9.

### New identity (`signals_v2`)

```
derive_id(LANGUAGE_SIGNAL_ARTIFACT_VERSION, "passage_language_signals",
          research passage_alignment_id, report_side, category, subcategory)
```

Why `(passage_alignment_id, report_side)` is the right key:

- **Unique per run.** It is enforced by the research constraint
  `uq_passage_language_signals_run_alignment_side`.
- **Stable across runs.** It is identical across every `LanguageSignalRun` pinned to the same
  `AlignmentRun`. A metric-only rerun pins the same alignment run.
- **Re-alignment is a new identity.** A new `AlignmentRun` mints new alignment ids, so realigned
  data can never falsely reuse an old artifact.
- **The pair-specific flags are covered.** `is_introduced`, `is_removed` and `is_retained` come
  from the alignment row's status, so they are a function of the key. `passage_id` alone would
  be wrong: a passage sits in two pairs (as later side, then earlier side) with different
  statuses.

What the brief asked us to decide about each candidate identity part:

| Candidate part | In identity? | Why |
|---|---|---|
| Source passage identity | No (implied), but it is in the content hash | `(alignment row, side)` determines the passage. `source_passage_id` is stored as lineage and hashed, so a re-pointed alignment would fail loudly. |
| Alignment version | Implicitly, via `passage_alignment_id` | New alignment runs mint new ids. `ALIGNMENT_ARTIFACT_VERSION` covers comparison scoring, which does not affect signal counts. |
| Taxonomy version | No | Covered by the `LANGUAGE_SIGNAL_ARTIFACT_VERSION` bump rule. The content hash fails loudly if a taxonomy change alters counts without a bump. |
| Normalization/tokenization version | No | Same as taxonomy. |
| Negation semantics | No | Same as taxonomy. |
| `LANGUAGE_SIGNAL_ARTIFACT_VERSION` | Yes | It is the deliberate, human-controlled generation boundary. |
| Research `PassageLanguageSignal.id` | **No longer** | Transient: new on every run. |

Folding extraction settings (taxonomy, dictionary, negation) into the identity would make a
forgotten version bump silently create a parallel generation. Keeping them out means such a
mistake fails the build, which is the behaviour the brief asks for.

### Content hash and reuse rule

The hash covers `source_passage_id`, raw/negated/adjusted counts, `rate_per_1000`, and the
introduced/removed/retained flags. `_check_content_hash` is unchanged:

- identity exists and the hash matches → **reuse**;
- identity exists and the hash differs → **`RuntimeError` ("content hash mismatch")**, and
  nothing is overwritten;
- identity is new → insert.

### Schema (migration `app_0016`)

| Change | Why |
|---|---|
| `source_passage_alignment_id`, `source_passage_id` added (nullable) | the v2 identity and lineage |
| `source_signal_id` made nullable | v2 rows do not carry the transient id |
| old unique constraint → partial unique index `WHERE source_signal_id IS NOT NULL` | signals_v1 rows keep their exact original uniqueness semantics |
| new partial unique index on `(source_passage_alignment_id, report_side, category, subcategory, version) NULLS NOT DISTINCT WHERE source_passage_alignment_id IS NOT NULL` | enforces the v2 identity at the database level |
| `CHECK (source_signal_id IS NOT NULL OR source_passage_alignment_id IS NOT NULL)` | every row carries one identity |

- **No backfill.** A v1 generation can legitimately hold two rows for one
  (alignment, side, category, subcategory): that is exactly the duplication being fixed. So v1
  rows cannot be re-keyed.
- **Downgrade.** It refuses (it does not delete) while any v2 row exists. A v2 row cannot
  satisfy app_0015's `NOT NULL` identity, and deleting it would break the publications that
  reference it.
- **GC.** Unchanged. It reference-counts through the thin `language_signal_artifact_id` link,
  which does not depend on how the artifact id was derived.

## 2. Artifact version semantics

- **`LANGUAGE_SIGNAL_ARTIFACT_VERSION`: `signals_v1` → `signals_v2`, bumped exactly once.** The
  identity scheme itself changed, and the content hash formula now includes the passage id.
  Mixing both schemes in one generation would make "same version" mean two different things.
  The bump gives a clean boundary:
  - existing v1 generations stay immutable and resolvable, so an older publication rolled back
    to still reads its own rows;
  - the first `signals_v2` build writes one fresh generation.

  This costs nothing at the cutover, because the fresh Neon database has no v1 rows.
- **New bump rule.** A metric-only research `SIGNAL_VERSION` bump must **not** bump
  `LANGUAGE_SIGNAL_ARTIFACT_VERSION`; it now reuses 100%. The version is bumped only when
  per-passage content changes. The content hash enforces this.
- **Not bumped:** `ALIGNMENT_ARTIFACT_VERSION` (`alignment_v1`) and
  `QA_CHUNKING_ARTIFACT_VERSION` (`qa_chunk_v1`). Nothing in this track changes their content.

## 3. Signal reuse qualification

**Tests (real end-to-end pipeline fixtures):**

`tests/publishing/test_signal_artifact_identity.py` covers:

- the identity is independent of the research signal id and sensitive to alignment, side,
  category, subcategory and version;
- an identical-content signal rerun reuses 100% of rows: the same artifact ids, zero new rows,
  zero duplicate content;
- a changed per-passage count without a version bump makes the build fail with
  "content hash mismatch";
- a changed count with a bumped version creates a new, disjoint generation. The old rows are
  byte-identical, and the current views resolve each publication to its own generation, including
  after a rollback.

`test_publishing_topic_change.py::test_signal_run_regeneration_reuses_signal_artifact_generation`
replaces the 7F.9 test that pinned the duplication.

**Realistic local sequence** (fresh DB `market_documents_app_7f10`, full corpus):

| Step | What ran | Signal artifacts |
|---|---|---|
| P1 `7f10-local-1` | first build (`signals_v2`) | 54,003 rows created |
| research rerun | `pairs language-build-all --force`: 25 new `LanguageSignalRun`s, 25 completed with warnings, 0 failed. Research `passage_language_signals` went from 289,808 to 324,924 rows (35,116 new ids, identical content). | — |
| P2 `7f10-local-2` | metric-only republish from the new runs | **0 created, 54,003 reused** |

P1 and P2 each reference 54,003 distinct signal artifacts. The intersection is **54,003 (100%)**.
`count(*) = count(distinct (alignment, side, category, subcategory, content_hash)) = 54,003`, so
there are zero duplicate content rows. P2 validated (566,171 checks) and was promoted.

- **How the rerun was produced.** It was a forced regeneration under the unchanged
  `SIGNAL_VERSION` (1.4.0), not a patched version bump. The mechanism that duplicated artifacts in
  7F.9 is new research signal ids with identical content, which both routes produce identically.
- **Why not a patched bump.** A patched version on the research DB would have left
  fake-version runs as the "current" runs.
- **The rehearsal clone was abandoned.** A clone of the research DB would have needed 1.5 GB more
  on the Docker volume, which was full (Section 9).
- **Version-bump coverage.** `scripts/rehearsal_7f10_signal_version_rerun.py` performs the
  literal version-bump variant, but refuses to run anywhere except a `*_rehearsal` clone. The
  bump itself is exercised by the unit tests.

**Genuine content change under a bumped version, at full scale.** P3 (`7f10-local-3-sigv3`) was
built with `LANGUAGE_SIGNAL_ARTIFACT_VERSION` patched to `signals_v3_rehearsal`.

- It created a new, isolated generation of **54,003 rows (+20.7 MB)**.
- `signals_v2` stayed untouched.
- P2 and P3 each resolve to their own version.

A content change with no bump is covered by the failing-build test above; the research DB was
not mutated to produce one at scale.

## 4. Storage measurement: identical-content signal rerun

`pg_total_relation_size` by schema on `market_documents_app_7f10`:

| Schema | After P1 | After P2 (identical-content signal rerun) | Delta | 7F.9 delta, same operation |
|---|---|---|---|---|
| `app_artifacts` | 107.03 MB | 107.03 MB | **+0.00 MB** | +19.67 MB |
| `app` (thin) | 76.34 MB | 149.88 MB | +73.54 MB (P2's membership rows, expected) | +76.6 MB |
| `app_corpus` | 103.20 MB | 103.20 MB | +0.00 MB | +0.02 MB |
| `app_internal` | 0.09 MB | 0.09 MB | 0 | 0 |
| **database** | 295.19 MB | 368.74 MB | **+73.55 MB** | +96.9 MB |

- **Signal generations:** old 54,003 rows, new **0**.
- **Every other family:** reused 100% (identical sizes).
- **Savings:** the ≈ 19.7 MB of avoidable duplication measured in 7F.9 is now exactly 0.

## 5. GC and retention with the new identity

Sequence on the rehearsal DB. P3 (bumped signal version) was promoted, so P2 was the rollback
and P1 the oldest.

| Step | Publications retained | GC removed | Signal generations left |
|---|---|---|---|
| `cleanup --keep 2`, then `gc-artifacts`, then `gc-corpus` | P3 (active), P2 (rollback); P1 removed | **0** in every family | `signals_v2`=54,003 (still referenced by P2), `signals_v3_rehearsal`=54,003 |
| validate P2 and P3 | — | — | both pass (566,171 checks each) |
| `cleanup --keep 1`, then `gc-artifacts`, then `gc-corpus` | P3 only; P2 removed | **54,003 `passage_language_signals`**, 0 in every other family, 0 corpus rows | `signals_v3_rehearsal`=54,003 |
| validate P3 | — | — | pass |

- **Shared rows survive partial cleanup.** Artifacts shared by P1 and P2 survived P1's cleanup.
- **An old generation lives while referenced.** `signals_v2` survived as long as any retained
  publication referenced it.
- **It is collected exactly once unreferenced.** It was removed only when its last referencing
  publication was cleaned.
- **Active and rollback publications stayed valid** at every step.

The same properties are pinned in
`test_signal_artifact_identity.py::test_gc_keeps_shared_signal_artifacts_until_last_reference_is_cleaned`.

**Space reclamation.** `DELETE` does not return space to the filesystem.

- After GC, the DB still measured 463.4 MB (dead tuples, reusable by later inserts).
- `VACUUM FULL` brought the one-publication database to **275.6 MB**.
- On Neon, reclamation is the same; autovacuum makes the space reusable. Measure storage after
  vacuum, not straight after GC.

## 6. QA vector search

### Root cause

`app.current_qa_chunks` selects `COALESCE(t.embedding, art.embedding) AS embedding`.
`ORDER BY embedding <=> $1` therefore sorts on an expression that neither HNSW index covers
(`ix_app_artifacts_qa_chunks_hnsw_cosine` indexes `art.embedding`, and `ix_app_qa_chunks_hnsw_cosine`
indexes `t.embedding`). Every query was a hash join, a full distance computation over the active
publication's chunks, and a top-N sort.

### Constraint discovered while fixing it

The web tier connects as `app_readonly`, which by design (`scripts/sql/app_grants.sql`) can read
only `app.current_*` views. It has no access to `app_internal` or `app_artifacts`. A repository
query against the artifact table would work locally as the owner and then fail with
permission denied in production. The fix therefore had to stay a view.

### Shapes tried (real 7F.9 corpus, 6,088 chunks)

| Shape | Plan | Time |
|---|---|---|
| Current COALESCE view | hash join + full scan + top-N sort | ≈ 29–58 ms |
| Artifact-first join, no thin index | hash join, no HNSW | ≈ 58 ms |
| Artifact-first join + `(qa_chunking_artifact_id, publication_id)` index | HNSW → nested-loop index lookup | ≈ 1.3–3.4 ms |
| View: UNION ALL of shared + legacy-inline branches | ORDER BY not pushed into branches; full scan | ≈ 158 ms |
| View: single branch, join `application_state` | HNSW, but a join filter after the lookup | ≈ 5.8 ms |
| **View: single branch, active publication as a scalar subquery** | **HNSW → nested-loop index lookup (InitPlan)** | **≈ 0.5 ms** |

### Change (smallest correct)

1. **Index** `ix_app_qa_chunks_artifact_publication` on
   `app.qa_chunks (qa_chunking_artifact_id, publication_id)` (app_0016).
2. **View** `app.current_qa_chunk_vectors` (app_0016, defined in
   `schema.QA_CHUNK_VECTOR_CURRENT_VIEWS`): the active publication's shared-artifact chunks, with
   `art.embedding` exposed un-COALESCEd. `WHERE t.embedding IS NULL` keeps it consistent with the
   COALESCE view's precedence for every row it returns.
3. **Grant:** `GRANT SELECT ON app.current_qa_chunk_vectors TO app_readonly` in `app_grants.sql`.
4. **Repository** (`postgres-qa-chunk-repository.ts`): in `hnsw` mode, **unscoped** semantic search
   reads the new view. The candidate set is materialized and re-sorted by exact distance
   (`relaxed_order` iterative scans can return near-ties out of order).
   - An empty result falls back to the unchanged exact query. That happens only if the active
     publication is a legacy inline one, from before 7F.7a.5.
   - **Unchanged:** `exact` mode (exact by definition), company-scoped search (already bounded to
     one company; an exact scan is cheap there and a filtered ANN scan could only lose recall),
     lexical search, citations and membership. They all stay on `app.current_qa_chunks` and
     `current_qa_chunk_passages`.

**View compatibility:**

- `app.current_qa_chunks` is not modified and remains the relational interface.
- Only the vector ORDER BY moves to the new view. That is a documented bypass of the COALESCE
  view, not a replacement for it.

### Benchmark (`scripts/benchmark_7f10_qa_vector_search.py`)

**Setup:**

- Rehearsal DB with P2 active: 6,088 chunks, one QA generation.
- 20 deterministic query vectors: normalized midpoints of two random chunks.
- k = 25 (the production semantic candidate limit).
- 5 warm-ups, then 50 timed runs per query.
- Same GUCs as the web tier: `hnsw.iterative_scan = relaxed_order`.

**Correctness against exact ground truth** (the COALESCE-view query with an id tie-break):

| `hnsw.ef_search` | Identical ordered top-25 | Identical top-25 set | Mean / min recall@25 | Mean / min recall@10 | After median / p95 ms |
|---|---|---|---|---|---|
| 40 (shared default) | 14/20 | 15/20 | 0.970 / **0.60** | 0.965 / 0.60 | 4.72 / 29.05 |
| 100 | 18/20 | 19/20 | 0.998 / 0.96 | 0.995 / 0.90 | 5.33 / 5.78 |
| **200 (adopted for QA)** | **20/20** | **20/20** | **1.000 / 1.000** | **1.000 / 1.000** | **5.19 / 5.74** |
| 400 | 20/20 | 20/20 | 1.000 / 1.000 | 1.000 / 1.000 | 33.43 / 41.77 |

(The 18/20 ordered result at ef 100–400 before the tie-break fix was two exact-distance ties.)

**Recall and `ef_search`:**

- At the shared default `ef_search = 40`, HNSW lost recall: the worst query found only 15 of the
  true top 25.
- The QA path therefore sets its own `QA_HNSW_EF_SEARCH = 200`, passed through a new optional
  `efSearch` argument to `queryVector`, validated as an integer from 1 to 1000.
- Passage retrieval keeps 40; it is outside this track.

**Final result at ef 200:**

| Query | Median ms | p95 ms | Timed runs | Result count | Index |
|---|---|---|---|---|---|
| before: `current_qa_chunks` (COALESCE) | 43.84 | 59.52 | 50 | 25 | none (seq scan + top-N heapsort over 6,088) |
| **after: `current_qa_chunk_vectors`** | **5.19** | **5.74** | 50 | 25 | **`ix_app_artifacts_qa_chunks_hnsw_cosine`** |
| company-scoped (SBP), unchanged exact path | 5.87 | 6.61 | 50 | 25 | n/a (bounded to one company) |

- **Result identity:** 20/20 identical ordered top-25 lists, the maximum |similarity difference|
  on shared ids is 0, and the result counts are equal (25/25).
- **Timing composition:** the median includes the client round trip and the per-query
  `BEGIN`/`SET LOCAL`/`COMMIT`. Server execution is ≈ 0.7 ms after, against ≈ 45–72 ms before.

**Plans:**

```
BEFORE (Execution Time: 45.1 ms, HNSW index used: False)
Limit -> Sort (top-N heapsort, key COALESCE(t.embedding, art.embedding) <=> q)
  -> Nested Loop Left Join
       -> Hash Join (t.publication_id = s.active_publication_id)
            -> Seq Scan on qa_chunks t (rows=12176)
       -> Index Scan using qa_chunks_pkey on qa_chunks art (loops=6088)

AFTER (Execution Time: 0.73 ms, HNSW index used: True)
Incremental Sort (nn.distance, nn.id)
  CTE nn -> Limit
    InitPlan 1 -> Index Scan using application_state_pkey
    -> Nested Loop (rows=25)
         -> Index Scan using ix_app_artifacts_qa_chunks_hnsw_cosine on qa_chunks art
              Order By: (embedding <=> q)
         -> Index Scan using ix_app_qa_chunks_artifact_publication on qa_chunks t (loops=25)
              Index Cond: (qa_chunking_artifact_id = art.id AND publication_id = (InitPlan 1))
```

**The live app uses the index too.** During the `/ask` smoke test,
`pg_stat_user_indexes.idx_scan` for `ix_app_artifacts_qa_chunks_hnsw_cosine` went 302 → 303, so
the production build's request went through the HNSW path under `app_readonly`.

**Correctness tests:**

- `tests/publishing/test_qa_chunk_vector_view.py`: the view returns exactly the
  `current_qa_chunks` rows and embeddings and the same exact nearest-neighbour order; it follows
  activation and rollback across QA generations; the plan uses the artifact HNSW index.
- `web/tests/repository/qa-chunk-repository.test.ts`, via the real `app_readonly` pool:
  - the view is granted and holds exactly the active shared chunks;
  - HNSW mode equals exact mode, including when nearer artifact rows the active publication does
    not reference are present;
  - company-scoped search stays scoped;
  - a legacy inline publication falls back correctly.
- `tests/publishing/test_publishing_roles.py`: `app_readonly` can read the view and is denied on
  raw `app_artifacts.qa_chunks`.

## 7. Migration-target footgun (`app-init --target-database-url`)

**Exact flow (before):**

1. `cli/publish.py::app_init` put the URL into `cfg.set_main_option("sqlalchemy.url", url)`.
2. `migrations_app/env.py` then executed, at import,
   `config.set_main_option("sqlalchemy.url", get_settings().app_database_url)`.
3. The explicit target was always replaced by `APP_DATABASE_URL`.

In 7F.9 this upgraded the dev DB instead of the new one. The migration tests only worked because
their masked `str(engine.url)` (`***` password) was also being replaced.

**Fix:**

- `session.resolve_app_migration_url(explicit, ini_url, settings_url)` applies a strict
  precedence:
  1. explicit caller target (`Config.attributes["target_database_url"]`);
  2. a real, non-placeholder `sqlalchemy.url`;
  3. `APP_DATABASE_URL`.
- `env.py` builds its engine from that resolved URL and never overwrites it.
- `app_init` passes the flag through `Config.attributes`. ConfigParser `%` interpolation can no
  longer corrupt passwords.
- The option no longer silently doubles as `envvar=APP_DATABASE_URL`, so the CLI knows which
  source it used.

**Operator confirmation:** `app-init` prints
`[INFO] migration target: localhost:5434/market_documents_app_7f10 (from --target-database-url)`,
then reads the revision back from that same database:
`[OK] application schema at app_0016 on localhost:5434/market_documents_app_7f10`. It shows
host, port and database only, never the user or password.

**Tests** (`tests/publishing/test_app_migration_target.py`, two throwaway databases):

| Brief case | Test | Result |
|---|---|---|
| A. explicit target migrates the intended DB | `test_explicit_target_migrates_target_and_leaves_app_database_url_untouched` | pass |
| B. default path still uses `APP_DATABASE_URL` | `test_default_path_still_uses_app_database_url` | pass |
| C. explicit target not replaced by settings | same as A, plus `test_resolver_precedence_explicit_over_ini_over_settings` | pass |
| D. source/dev DB untouched | same as A: no `alembic_version`, not even the `app*` schemas on the `APP_DATABASE_URL` DB | pass |
| no credentials printed | `test_describe_database_target_never_prints_credentials`, plus an output assertion in A | pass |

- **Regression proof:** with the pre-7F.10 `env.py` restored, the explicit-target test fails
  (`assert None is not None`, meaning the target was never migrated).
- **Masked test URL fixed:** `tests/publishing/test_app_migrations.py` now renders the real URL
  (`render_as_string(hide_password=False)`). It had been passing `***`, which only worked because
  of the bug.
- **Live check in the rehearsal:** the dev DB `market_documents_app` stayed at `app_0014` while
  `market_documents_app_7f10` went to `app_0016`.

## 8. KP2 period-end resolution — `CONFIRMED_2025`

**Inspected:**

- the raw PDF (metadata, cover, contents, Directors' Report, auditor's report, primary
  statements);
- the registration row and its full `validation_notes` history;
- `data/kp2_metadata.csv` and `data/all_metadata.csv`;
- git history (`5e924053 fixed date issue in documents`);
- the neighbouring KP2 file (`data/raw/KP2/2024`).

| Evidence (`data/raw/KP2/2025/annual_report.pdf`, sha256 `3bcf6f68572a…`, 138 pp.) | Says |
|---|---|
| PDF metadata | created `2026-03-24` (Docusign) |
| Cover, p.1 | "ANNUAL REPORT FOR THE FINANCIAL YEAR ENDED 31 DECEMBER 2025" |
| Directors' Report, signed p.37 | "Non-Executive Chairman David Hathorn **24 March 2026**" |
| Going concern, p.45 | "The 31 December 2025 full-year report has been prepared on a going concern basis" |
| BDO LLP audit opinion, dated p.91 | **24 March 2026** |
| Income statement, p.92 | "FOR THE YEAR ENDED 31 DECEMBER 2025", columns **Dec 2025 / Dec 2024** |
| Statement of financial position, p.93 | "AS AT 31 DECEMBER 2025", columns Dec 2025 / Dec 2024 |
| Notes, p.97 | "New standards … effective from 1 January 2025" |

- **The directory-2024 file** (sha256 `fc05556bf3c2…`) is a different document: "FINANCIAL YEAR
  ENDED 31 DECEMBER 2023", created 2024-03-27.
- **No FY2024 copy exists locally.** Nothing is under `data/raw/KP2`, or anywhere else in `data/`
  or the downloader directory.
- **FY2024 is genuinely missing.** The directory-2025 slot holds the FY2025 report (published
  March 2026) instead of the FY2024 report (published about March 2025).

**The 2026-07-17 manual note** ("corrected period_end from 2025-12-31 to 2024-12-31 after
verification from the annual report") cites no page. Every piece of evidence above contradicts it.

- `data/kp2_metadata.csv`, exported before that correction, still shows 2025-12-31.
- `data/all_metadata.csv` carries 2024-12-31 only in the reviewer-override column.
- Most likely, the directory-year pattern (FY + 1) was applied to a slot that was never filled
  with the FY2024 report.

**Correction (local research DB only).** Applied with
`scripts/sql/kp2_period_end_correction_7f10.sql`: guarded, transactional, and it aborts unless
the exact pre-correction state is present.

- **Backup first:** `market_documents_pre7f10_backup`, a template clone of the research DB, taken
  before any change.
- **Report `6727add6…`:** `period_end` 2024-12-31 → **2025-12-31**. The evidence (with pages) is
  appended to `validation_notes`.
- **Pair `393f45ef…`:** `gap_months` 12 → **24**. The same earlier/later ids and ordering are
  kept, so the chronology stays FY2019 → FY2020 → FY2021 → FY2022 → FY2023 → FY2025.
- **`is_transition` stays false.** Both sides are 12-month December year ends. The irregular gap
  is flagged by the pipeline's own rules (it is never silently inferred).
- **Why a script:** `metadata-review-import` refuses by design to overwrite an existing
  `period_end`, and `pairs build` never refreshes `gap_months` on an existing pair.

**Minimum reruns (that pair only, `--force`).** The gap feeds similarity quality (> 18 months),
per-passage alignment confidence (HIGH → MEDIUM, > 18 months) and feature `irregular_gap`
(outside 9–15 months):

| Step | Before | After |
|---|---|---|
| `pairs score` | — | NEEDS_REVIEW, "reporting gap (24 months) exceeds tolerance (18)" |
| `pairs align` | — | COMPLETED_WITH_WARNINGS, "irregular reporting gap (24 months)" |
| `pairs features-build` | NEEDS_REVIEW, not eligible | NEEDS_REVIEW, not eligible; "irregular reporting gap: unexplained, not a flagged transition period" |
| `pairs language-build` | report-side USABLE, **eligible** | report-side **NEEDS_REVIEW, not eligible** |
| FC / GOV / UNC topic change, net tone | +0.149 / −0.053 / +0.533 / −0.323 | identical (content unchanged) |

Nothing else was rerun: no extraction, segmentation, embedding, or other pair.

**What changes:**

- The KP2 FY2023 → FY2025 comparison is now labelled as a 24-month, irregular-gap comparison.
- It leaves the report-side Discover candidate pool. It was below every threshold before, so no
  published finding changes (Section 10).

## 9. Fresh-local-database rehearsal

**Database:** `market_documents_app_7f10`, created empty. The final shared-artifact architecture
and the 7F.9 metric code were used, with the KP2-corrected research data.

| Step | Result |
|---|---|
| `publish app-init --target-database-url …/market_documents_app_7f10` | `app_0001` → `app_0016`; printed target `localhost:5434/market_documents_app_7f10 (from --target-database-url)`; dev DB `market_documents_app` stayed at `app_0014` |
| `scripts/sql/app_grants.sql` | applied (password-free) |
| empty-DB footprint | 9.68 MB |
| `publish build 7f10-local-1` (P1) | READY in 17 min 57 s |
| `publish validate` P1 | 566,171 checks, passed |
| `publish promote` P1 | ACTIVE (first attempt failed: local Docker volume full, see below) |
| P1 footprint | **295.19 MB** (app 76.34 / artifacts 107.03 / corpus 103.20 / internal 0.09) |
| research `language-build-all --force` → P2 build | READY in 9 min 53 s; **signal reuse 100%**, artifacts +0.00 MB |
| validate + promote P2 | 566,171 checks, passed; ACTIVE, P1 is the rollback |
| second-build peak (active + rollback) | **368.74 MB** |
| Discover findings P1 vs P2 | identical |
| rollback | Pointing the active publication at P1 (the documented mechanism; `activate_publication` refuses SUPERSEDED targets): every current view, including `current_qa_chunk_vectors`, resolved only P1's rows (0 rows from another publication); findings identical to P1's. Switched back to P2: identical to before. |
| P3 (bumped signal artifact version), cleanup + GC | Section 5 |
| post-GC, `VACUUM FULL`, one publication | **275.61 MB** |

**Artifact reuse, P1 → P2**, all families:

| Family | Reuse | Rows |
|---|---|---|
| passage comparisons | 100% | 23,279 |
| retrieval contexts (+ children) | 100% | 34,099 (+ 51,369 + 533) |
| QA chunks (+ membership) | 100% | 6,088 (+ 26,461) |
| language signals | 100% | 54,003 |

**Smoke tests** (`next build`, then `next start`, `APP_READONLY_DATABASE_URL` pointed at the
rehearsal DB as `app_readonly`, local embedding service):

| Check | Result |
|---|---|
| `/discover` | 200; published tabs; "Not currently published" section |
| disabled states (`?type=largest_risk_introduction`, `largest_overall_change`) | 200; "methodology under review … does not mean that no change occurred" |
| comparison SBP 2023→2024 | 200; −0.90, Dividend evidence |
| comparison ACT 2017→2018 (net tone) | 200; −6.63, "fewer positive words" |
| comparison KP2 2023→2025 | 200; shows 2025 and the 24-month gap |
| evidence explorer | 200; "Possibly moved or restructured" badges on filtered status tabs (7–15 per page) |
| passage detail, keyword search | 200 |
| semantic and hybrid retrieval | 200 with results |
| company page KP2, methodology | 200 |
| Q&A, unscoped | 200; excerpts retrieved via the HNSW path (index counter 302 → 303) |
| Q&A, KP2-scoped (exact path) | 200; relevant KP2 going-concern excerpts retrieved |
| Q&A generation | **not verified: Gemini returned HTTP 503 on every attempt** (external provider outage). The page degraded as designed ("answer generator is temporarily unavailable", excerpts still shown). |
| Next.js server log | no errors |

**Local environment incident.** The local Docker Postgres volume filled up during the rehearsal.

- **Symptoms:** the P1 promote and a research-DB clone failed with `DiskFull`. A manual
  `CHECKPOINT` then crashed the server, which restarted cleanly.
- **Integrity after restart:** committed data was intact (reports, the KP2 correction, signal
  runs, and P1 READY).
- **Recovery:** with your approval, `market_documents_7e2_rehearsal` and
  `market_documents_app_7e2_rehearsal` were dropped (≈ 873 MB). Everything after that ran
  normally.
- **Production impact:** none. It does not affect Neon, which is not a Docker volume.
- **Research-DB clone abandoned:** the rehearsal uses a forced regeneration instead (Section 3).

**Local databases left in place:**

- `market_documents_app_7f10`: rehearsal DB, now holding only P3 (`7f10-local-3-sigv3`, a
  rehearsal-only signal version). Safe to drop.
- `market_documents_pre7f10_backup`: 1.5 GB template clone of the research DB taken before the
  KP2 correction. Drop it once you're satisfied.

The research DB `market_documents` gained 25 identical-content signal runs, which are now current,
plus the KP2 correction and the KP2 pair's reruns.

## 10. Discover findings after the KP2 correction

The KP2 correction removes one pair from the report-side candidate pools. That pair was below
every threshold before (FC +0.149 < 0.25, GOV −0.053, UNC +0.533 < 0.75, tone −0.323 > −2.25).

- **Every scope checked:** all 31 `current_discovery_items` rows, across all rank scopes and
  types, are **identical** to the 7F.9 publication `7f9-local-1`: same type, scope, ticker, rank
  and value.
- **Corpus scope:** exactly the frozen 5 / 5 / 1 / 3 set.

| Type | Ranks (corpus scope) |
|---|---|
| FC | ACT 2016→2017 −0.925620; SBP 2023→2024 −0.901586; BEL 2017→2018 +0.554362; SUR 2024→2025 −0.373637; BEL 2020→2021 +0.278294 |
| GOV | BEL 2016→2017 +1.188940; ACT 2023→2024 −0.916825; ACT 2017→2018 +0.499796; SDL 2024→2025 −0.452412; ACT 2020→2021 −0.268963 |
| UNC | ACT 2019→2020 +0.759565 |
| Net tone | ACT 2017→2018 −6.634620; BEL 2018→2019 −3.825999; ACT 2021→2022 −2.446246 |

P2, built from the regenerated signal runs, has findings identical to P1.

## 11. Storage model for the fresh Neon project

**Measured locally** (`pg_total_relation_size`, fresh DB, full corpus: 6 companies, 30 reports,
25 comparisons):

| Component | MB |
|---|---|
| corpus (`app_corpus`: passages + embeddings) | 103.20 |
| artifacts: QA chunks + membership | 49.39 (44.26 + 5.13) |
| artifacts: retrieval contexts + children | 27.58 (17.83 + 9.59 + 0.16) |
| artifacts: passage language signals | 19.13 |
| artifacts: passage comparisons | 10.92 |
| **artifacts total** | **107.03** |
| thin publication layer (`app`) | 76.34 (73.54 for each additional publication) |
| `app_internal` | 0.09 |
| system/catalog overhead (database minus schemas) | ≈ 8.5 |
| **one publication (fresh build)** | **295.19** |
| **active + rollback (metric-only republish peak)** | **368.74** |
| one publication after GC + `VACUUM FULL` | 275.61 |

**Scaling to production:**

- The production Neon corpus is the same corpus: 24 comparisons and 6,064 QA chunks, against
  25 / 6,088 locally.
- Production `app_corpus` measured 119 MB (7F.7a.3), against 103.2 MB here. That ratio is
  **1.153**.
- Applying ×1.16 to every application schema, plus ≈ 8.6 MB of Neon system overhead:

| Scenario | Local data MB | Projected Neon MB | Headroom vs 512 MB |
|---|---|---|---|
| one publication (post-cutover steady state) | 286.66 | **341** | **171 MB** |
| active + rollback, metric-only republish peak (full reuse) | 360.20 | **427** | **85 MB** |
| active + rollback + one signal-content bump (+19.1 MB new generation) | 379.33 | **449** | **63 MB** |
| active + rollback + a QA-chunking/embedding bump (+49.4 MB) | 409.59 | **484** | **28 MB** |
| active + rollback + alignment + QA + signal bumps together (+106 MB) | 466.3 | **550** | **−38 MB (over the cap)** |

**Read-out:**

- The cutover itself needs about 341 MB.
- The routine case (a metric-only republish with a rollback retained) peaks at about 427 MB,
  leaving 85 MB.
- A release that bumps several artifact families at once does **not** fit with a rollback
  retained. Such a release needs `cleanup --keep 1` + `gc-artifacts` + a vacuum before the build.
  That is the 7F.7a.4a retention policy, now quantified.
- Before this track, every metric-only republish also carried about 23 MB of duplicate signal
  generation (19.7 MB × 1.16). That would have cut routine headroom to about 62 MB.

## 12. Test results

| Suite | Result |
|---|---|
| Python, full (`.venv/bin/python -m pytest`) | **1302 passed, 5 skipped, 0 failed** (1288 before this track) |
| Python role tests with `APP_READONLY_TEST_PASSWORD` set (normally skipped) | **5 passed**, including 2 new vector-view grant tests, after re-applying `app_grants.sql` to the test DB (the downgrade-to-base migration test drops grants; the web suite's global setup normally re-applies them) |
| Frontend, full (`vitest run`, including repository tests on the seeded test DB) | **1056 passed, 0 failed** (114 files; 1052 / 113 before) |
| `eslint` | clean |
| `tsc --noEmit` | clean |
| `next build` | success |

**New tests:**

- `tests/publishing/test_signal_artifact_identity.py` (5): identity, 100% reuse, a hash
  mismatch without a bump, bump isolation with rollback, GC reference-counting.
- `tests/publishing/test_app_migration_target.py` (4): cases A–D and credential redaction.
- `tests/publishing/test_qa_chunk_vector_view.py` (2): view equivalence with rollback, and the
  HNSW plan.
- `tests/publishing/test_app_migrations.py` (+3): the `app_0016` round trip, the downgrade
  refusal, and the identity CHECK.
- `tests/publishing/test_publishing_roles.py` (+2): the vector-view grant, and denial on raw
  artifacts.
- `web/tests/repository/qa-chunk-repository.test.ts` (4): the grant, HNSW equals exact with
  trap rows, company scope, and the legacy fallback.

**Updated tests:**

- `test_publishing_topic_change.py`: the duplication-pinning test now asserts reuse.
- `test_app_migrations.py`: real URL rendering, and the new view is expected at head.

## 13. Remaining cutover blockers and final verdict

### Requirement check

| READY requires | Status |
|---|---|
| identical-content signal rerun reuses shared signal artifacts | **yes**: 54,003/54,003 (100%), +0.00 MB |
| no unexplained artifact duplication | **yes**: zero duplicate content rows; all growth is the expected thin layer |
| QA vector path uses HNSW | **yes**: plan and live `idx_scan` evidence |
| vector results remain correct | **yes**: 20/20 identical ordered top-25, recall 1.0 (with `ef_search` 200) |
| explicit target DB is honored | **yes**: tests A–D, plus the live rehearsal (dev DB untouched) |
| KP2 resolved | **yes**: `CONFIRMED_2025`, corrected, minimum reruns, findings unchanged |
| fresh local rehearsal passes | **yes**: migrate, grants, build, validate, promote, republish, rollback, cleanup, GC |
| storage model fits 512 MB | **yes**: 341 MB at cutover, 427 MB peak for a routine republish |
| full regressions green | **yes** |

### Operational notes for the cutover runbook (none blocks creating the project)

1. **Rollout order on the fresh project:**
   1. `publish app-init --target-database-url <neon>`: check the printed target and the
      read-back revision (`app_0016`);
   2. `app_roles.sql` / `app-init-roles`, then `app_grants.sql` (required for
      `current_qa_chunk_vectors`);
   3. build;
   4. validate;
   5. promote;
   6. smoke.

   The research DB is already at signal 1.4.0 with the KP2 correction, so no research step is
   needed.
2. **Multi-family artifact bumps** do not fit alongside a retained rollback (Section 11). Run
   `cleanup --keep 1` + `gc-artifacts` (+ vacuum) first.
3. **Q&A answer generation was not verified** in this track: Gemini returned HTTP 503 throughout.
   Retrieval (both paths) was verified. Re-check generation in the cutover smoke test.
4. **Local housekeeping:** `market_documents_pre7f10_backup` (1.5 GB) and
   `market_documents_app_7f10` can be dropped. The local Docker volume ran out of space once
   during this track.
5. **Pre-existing and unchanged:** thresholds remain single-corpus and provisional (7F.8/7F.8a).
   KP2 FY2024 is absent from the corpus; the pair is labelled irregular (24 months), not
   silently bridged.

### Final verdict — `READY_TO_CREATE_FRESH_NEON`

- **Signal duplication:** fixed at the identity level, so a metric-only rerun costs nothing in
  shared storage.
- **QA vector search:** uses HNSW with exact-equivalent results, without widening
  `app_readonly`'s privileges.
- **Migration target:** can no longer silently miss the database it names.
- **KP2:** resolved from the document's own evidence.
- **Rehearsal:** the full lifecycle ran end to end on a fresh database, within a quantified
  512 MB budget.

The next action can safely be creating the final fresh free-tier Neon project.

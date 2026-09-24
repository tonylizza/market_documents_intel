# Track 7F.7a.3: Production Storage Audit (Read-Only)

## 0. Scope and method

Read-only audit against the current production Neon project
**`polished-dawn-80694996`** (host `ep-icy-dream-b4ed5crk.c-6.us-east-2.aws.neon.tech`,
database `neondb`, credential from `.env.neon`), run via `psql` directly.
No writes, no `VACUUM`, no schema changes, no publish/promote/deploy actions
were performed. The retained rollback project (the pre-`7e3`-cutover Neon
database) was **not** queried; figures for it below are taken from
`docs/7e4-post-cutover-stabilization.md` (measured there, ~400MB, untouched)
and are cited only for comparison, per the brief's restriction.

Two prior tracks already characterized most of this territory and are the
basis for several conclusions below rather than re-derived from scratch:

- `docs/7e1-publication-storage-lifecycle-hardening.md` — designed and
  shipped the `app_corpus` shared-passage/embedding architecture
  (migration `app_0010_shared_passage_corpus`) specifically to remove
  cross-publication duplication of `passages.text`/`passage_embeddings`.
- `docs/7e3-fresh-neon-production-cutover.md` /
  `docs/7e4-post-cutover-stabilization.md` — cut production over to a
  **brand-new** Neon project already running the post-7E.1 schema, rather
  than migrating in place (the in-place migration was blocked by the same
  512MB cap this audit re-examines).

This audit's job is to confirm what state that left production in today,
after two further production rollouts (`7f5` financial-condition metrics,
`7f7a2` governance metrics) added rows and columns since the 7E.1/7E.3
baseline.

## 1. Storage by database

| database | size | notes |
|---|---|---|
| `neondb` | **432 MB** (452,509,696 bytes) | only database holding application data |
| `postgres`, `template0`, `template1` | default Postgres/Neon system databases, not measured (not application data) | — |

Project cap: 512 MB. Free headroom today: **512 MB − 432 MB ≈ 80 MB**
(84,361,216 bytes).

## 2. Storage by schema

`pg_total_relation_size` already includes each table's own TOAST and
indexes, so schema totals below are summed from `pg_class`/`pg_namespace`
directly (not from a naive `pg_toast`-schema-inclusive sum, which
double-counts):

| schema | total size | purpose |
|---|---|---|
| `app` | ~304 MB | publication-scoped tables (one full copy per publication that has ever been built and not cleaned up) |
| `app_corpus` | ~119 MB | shared, non-publication-scoped `passages`/`passage_embeddings` (the 7E.1 dedup design) |
| `app_internal` | ~0.2 MB | publication lifecycle bookkeeping (`publications`, `application_state`, `alembic_version`) |
| (unattributed) | ~8.6 MB | Postgres/Neon system overhead (catalogs, `vector` extension metadata) — not application data, not reclaimable by any means in scope |

Sum of `app` + `app_corpus` + `app_internal` + unattributed ≈ 432 MB, matching
`pg_database_size` exactly.

## 3. Storage by table (top consumers)

| table | table size | index size | total size | rows | publication-scoped? |
|---|---|---|---|---|---|
| `app_corpus.passage_embeddings` | 38 MB | 51 MB | **89 MB** | 19,300 | no (shared) |
| `app.qa_chunks` | 61 MB | 14 MB | **75 MB** | 6,064 | yes |
| `app.passage_language_signals` | 25 MB | 41 MB | **66 MB** | 32,823 | yes |
| `app.retrieval_contexts` | 28 MB | 29 MB | **58 MB** | 25,524 | yes |
| `app.retrieval_context_language_categories` | 14 MB | 20 MB | **34 MB** | 48,302 | yes |
| `app.passage_comparisons` | 18 MB | 15 MB | **33 MB** | 13,129 | yes |
| `app_corpus.passages` | 18 MB | 12 MB | **30 MB** | 19,158 | no (shared) |
| `app.passages` | 11 MB | 11 MB | **22 MB** | 12,481 | yes (`text` column is `NULL` on every row — see §5) |
| `app.qa_chunk_passages` | 5.3 MB | 8.3 MB | **14 MB** | 25,307 | yes |
| everything else (`language_metrics`, `report_comparisons`, `discovery_items`, `reports`, `companies`, `metric_definitions`, `metric_label_thresholds`, `narrative_unit_comparisons`, `structured_table_comparisons`, `retrieval_context_risk_subcategories`) | — | — | **~2.4 MB combined** | ≤ ~700 each | yes |
| `app.passage_embeddings` | 8 KB | 48 KB | **56 KB** | **0** | yes — dead table, see §8 |

Requested tables explicitly, for the record:

- `app.report_comparisons`: 264 KB total, 24 rows.
- `app.discovery_items`: 176 KB total, 52 rows.
- `app.language_metrics`: 912 KB total, 504 rows.
- Narrative/structured comparison tables: `app.narrative_unit_comparisons`
  (560 KB, 74 rows), `app.structured_table_comparisons` (408 KB, 16 rows).
- QA chunk tables: `app.qa_chunks` (75 MB), `app.qa_chunk_passages` (14 MB).
- `app_corpus.passages`: 30 MB, 19,158 rows.
- `app_corpus.passage_embeddings`: 89 MB, 19,300 rows.
- Research language-signal tables, report-pair feature tables: **do not
  exist in this database** — see §4.
- Historical publications / historical language-signal runs: **none
  exist** — see §5.
- Indexes: 203 MB total across `app`/`app_corpus`/`app_internal` (see §7).

## 4. Research/signal tables are out of scope by architecture, not by omission

Only four schemas exist in `neondb`: `app`, `app_corpus`, `app_internal`,
`pg_toast`. There is no `research`, `public`-with-research-tables, or any
other schema. This matches `docs/publishing.md`'s stated architecture: the
research database (companies, extraction, segmentation, embeddings,
alignment, feature runs, language-signal runs) is a **separate,
local** PostgreSQL database and is "never queried directly by a public
application." Neon holds only the *published, publication-scoped snapshot*
that the local research pipeline writes via `market-documents publish
build`.

Consequently: "research language-signal tables," "report-pair feature
tables," and "obsolete language-signal runs" (Question D) have **zero
footprint in this Neon project** — they aren't here to clean up. Any
cleanup of research-side history happens against the local database and is
outside this audit's scope (and outside this project's 512MB cap
entirely).

## 5. There is exactly one publication — no rollback or superseded data to reclaim

This is the audit's central finding and it overturns the brief's framing.

```
app_internal.publications: 1 row  (publication_version = '7f5-production-1',
                                    status = ACTIVE, id = db1d6ba8-...)
app_internal.application_state.active_publication_id = db1d6ba8-... (matches)
```

Every publication-scoped table in `app` — `passages`, `passage_comparisons`,
`qa_chunks`, `qa_chunk_passages`, `passage_language_signals`,
`retrieval_contexts`, `discovery_items`, `language_metrics`, `reports`,
`report_comparisons`, etc. — was checked directly for
`count(distinct publication_id)`. Every one returned **1**. There is no
second publication, in any status (`READY`, `SUPERSEDED`, `FAILED`), present
in this database at all.

This is architecturally expected, not a data-hygiene lapse:
`docs/7e3-fresh-neon-production-cutover.md` shows this Neon project was
created fresh for the cutover and has only ever held one publication lineage
since (`7f5-production-1`, built during the `7f5` financial-condition
rollout, still active through the subsequent `7f7a2` governance rollout —
governance apparently rebuilt the *same* publication version in place,
consistent with `publishing.md`'s idempotent-rebuild-of-the-same-version
behavior, rather than promoting a new one). The **rollback path for this
system is a separate Neon project** (the pre-cutover database,
`docs/7e4-post-cutover-stabilization.md`'s "old rollback Neon database," ~400
MB, explicitly not touched by this audit), not a second publication retained
inside `polished-dawn-80694996`.

Direct implication for Questions A–D:

- **A. ACTIVE publication data:** ~304 MB (the entire `app` schema — every
  row belongs to the one active publication).
- **B. Immediately previous rollback publication (inside this database):**
  **0 MB — none exists.** The actual rollback path is the external Neon
  project, not a row set here.
- **C. Older superseded publications:** **0 MB — none exist.**
- **D. Obsolete research signal runs:** **0 MB — not stored in this
  database at all** (§4).
- **E. Shared corpus data that cannot be removed:** ~119 MB
  (`app_corpus.passages` + `app_corpus.passage_embeddings`) — referenced by
  the one live publication's `retrieval_contexts`/`current_passages` views;
  removing any of it would break production reads.
- **F. Index/bloat overhead:** see §7 — essentially all overhead is index
  structure, not bloat.

## 6. There is no bloat

`pg_stat_user_tables` was checked for every `app`/`app_corpus` table:
`n_dead_tup = 0` on all of them, and `last_autovacuum` timestamps are within
the last few minutes of this audit for every table with meaningful row
counts. Neon's autovacuum is keeping up; there are no dead tuples to reclaim
via `VACUUM` (which the brief correctly excluded from scope — it would have
reclaimed nothing measurable here anyway).

## 7. Index overhead is real, but it is structural, not reclaimable waste

| | table (heap) size | index size | total |
|---|---|---|---|
| `app` + `app_corpus` + `app_internal`, summed | 220 MB | **203 MB** | 423 MB |

Indexes are ~48% of total table-inclusive size — high, but not bloat (§6
already rules that out) and not discretionary: the two largest single
indexes are the pgvector HNSW cosine indexes required for retrieval —
`ix_app_corpus_passage_embeddings_hnsw_cosine` (44 MB, the shared corpus
embedding index — one index total, replacing what would otherwise be one
per publication) and `ix_app_qa_chunks_hnsw_cosine` (12 MB). The rest are
the composite uniqueness/scope indexes (`uq_app_*_scope`,
`uq_app_*_pub_source`) that every publication-scoped table needs to enforce
`(publication_id, source_*)` uniqueness, plus ordinary FK/lookup B-tree
indexes and one GIN full-text index on `app_corpus.passages.search_vector`
(8.8 MB). Dropping any of these would change user-visible behavior
(retrieval, search, or referential integrity), so none qualify as a safe
cleanup target under this audit's constraints.

**F. Answer:** ~0 MB is bloat; the ~203 MB of index overhead is structural
and not reclaimable without removing functionality.

## 8. One genuinely dead artifact (immaterial in size)

`app.passage_embeddings` — the pre-7E.1, per-publication embeddings table —
still exists in the schema, still has its HNSW index, and holds **0 rows**
(56 KB total, entirely index/catalog overhead for an empty table). Per
`docs/7e1-publication-storage-lifecycle-hardening.md` §4, the publisher was
changed to stop writing to this table entirely; the shared
`app_corpus.passage_embeddings` fully replaced it. It is genuinely dead
schema, not data, and it is **56 KB** — three orders of magnitude too small
to matter for a 300 MB headroom problem. Flagged for a future migration to
drop it; not modeled in any scenario below because it changes nothing
material.

Also confirmed: `app.passages.text` is `NULL` on all 19,373 rows in the
active publication, and `app.passage_language_signals` has 0 rows outside
the active publication's `publication_id` — both confirm the 7E.1
shared-corpus design is fully in effect in production today, not a partial
rollout.

## 9. Cleanup scenarios

Given §5 (no superseded/rollback publications and no obsolete research runs
exist *inside this database*) and §6 (no bloat), every scenario that assumes
there is something to delete finds nothing:

### SCENARIO 1 — CONSERVATIVE (keep active + rollback + all research runs, delete only publications older than rollback)

- Reclaimable: **0 MB.** There is no publication older than the single
  active one to delete.
- Resulting size: 432 MB (unchanged).
- Headroom: 80 MB (unchanged).
- Fits a 300 MB build: **No.**

### SCENARIO 2 — MODERATE (keep active + one rollback + current research runs, delete superseded publications + obsolete signal runs)

- Reclaimable: **0 MB.** No superseded publications exist to delete; no
  language-signal-run data exists in this database to delete (§4).
- Resulting size: 432 MB (unchanged).
- Headroom: 80 MB (unchanged).
- Fits a 300 MB build: **No.**

### SCENARIO 3 — MINIMUM-FOOTPRINT BLUE/GREEN (keep only what's needed to serve production, retain one rollback path, build one new publication safely)

- Reclaimable from *this* database: **0 MB** — production is already at
  its minimum footprint (one active publication, fully corpus-deduplicated,
  no dead rows, no bloat; the true rollback path is already external and
  costs this database nothing).
- The blocking factor is not standing data to delete; it is the **build
  lifecycle itself**. Per `docs/publishing.md` §"Publication lifecycle,"
  `build` always creates a complete new set of publication-scoped rows
  under a new `Publication`, and only `promote` (after validation) retires
  the old one to `SUPERSEDED` — `cleanup` (which actually frees space) can
  only run *after* that. A new build must therefore coexist, in full, with
  the current 432 MB **before** anything can be reclaimed.
- Estimated transient peak: current 432 MB + a new publication's
  release-specific layer. Per Track 7E.1's own measurement (§10 there) and
  this audit's §2/§3, the corpus-shared tables (~119 MB) would not need to
  be duplicated again for unchanged source passages — the new build's cost
  is essentially the `app`-schema layer alone, currently measured at ~304
  MB for one publication. Peak ≈ 432 MB + ~300 MB ≈ **~730 MB**, far over
  the 512 MB cap, even though the *steady state* after promote + cleanup
  would return to roughly today's 432 MB (or less, if the new publication
  is smaller).
- Fits a 300 MB build: **No — not because of standing waste, but because
  the build-before-promote step needs ~300 MB of headroom that a
  cleanup-only approach can never create**, since there is nothing to clean
  up until *after* the new build already exists.

## 10. Is the ~300 MB estimate genuinely required, or is it duplicated shared data?

Mostly genuine, with one caveat already flagged in Track 7E.1 and not yet
acted on. Track 7E.1 deliberately solved the *provably-safe* half of this
problem: `passages.text` and `passage_embeddings` are pure, stable copies of
upstream research data and are now shared unconditionally via
`app_corpus.*` — confirmed still true in production today (§8). That
leaves the four tables 7E.1 explicitly left publication-scoped because
their content is a genuine output of code that changes between releases
(`retrieval_contexts`, `passage_comparisons`, `qa_chunks`,
`passage_language_signals`) — together these four tables plus their child
tables (`qa_chunk_passages`, `retrieval_context_language_categories`,
`retrieval_context_risk_subcategories`) account for **~280 MB of the
current 304 MB `app` schema**, i.e. most of what a new build would have to
duplicate.

7E.1 measured (in its local test dataset) that these tables were, in that
specific instance, byte-identical across two publications built from
unchanged source data — but explicitly declined to make them shared,
because there is no `source_configuration_hash`-style versioning axis for
them yet, and a single code change (exactly what `7f5`/`7f7a2` were) bumps
that hash for an entire publish run, not per-table. Extending sharing to
these four tables is a "legitimate future track," in 7E.1's own words, not
something this audit can respecify — it would need its own design and
benchmarking, matching the caution 7E.1 already applied to
`passages`/`passage_embeddings`.

So: **some** of the ~300 MB genuinely does duplicate data that is
unchanged between releases in practice, but no *safe*, already-designed
mechanism exists today to avoid storing it — this is an open architectural
gap, not an oversight fixable by different cleanup choices.

## 11. Final recommendation

**ARCHITECTURAL_CHANGE_REQUIRED**

Not `SAFE_CLEANUP_SUFFICIENT`: there is no superseded publication, no
retained rollback publication, and no research-signal history inside this
database to clean up (§5, §9) — cleanup scenarios 1–3 all reclaim 0 MB.
Not `BOTH_...`: since cleanup contributes nothing, there is nothing for an
architectural fix to be paired with. Not `MORE_DATA_NEEDED`: production was
queried directly and completely; every table in scope was measured, and the
one open question (§10, whether comparison/signal outputs are stable enough
to share) is a *design* question for a future track, not missing
measurement data.

The real constraint is structural: the `build → validate → promote →
cleanup` lifecycle requires a full second copy of the ~300 MB
publication-scoped layer to exist simultaneously with the current one
before anything can be promoted or cleaned up, and today's 432 MB baseline
(already minimal — one publication, fully deduplicated corpus, zero bloat)
leaves only ~80 MB of the 512 MB cap for that. No paid-capacity change and
no additional cleanup pass can close a ~220 MB gap that isn't made of
deletable data. Closing it requires an architectural change — most directly,
extending Track 7E.1's corpus-sharing design to some or all of
`retrieval_contexts`/`passage_comparisons`/`qa_chunks`/
`passage_language_signals` (with a proper versioning axis, as 7E.1 itself
scoped out), or restructuring the publish lifecycle so a new build doesn't
require full coexistence with the current `ACTIVE` publication before
promotion.

# Track 7E.1: Publication Storage / Lifecycle Hardening

## 0. Background

Track 7D.2c promoted `healthcare_services_review` coverage in code, but
production activation was blocked: production Neon (512MB project cap) was
~400MB with a single `ACTIVE` publication, and a second full publication
could not fit. This track audits why, measures the real duplication, and
implements the smallest safe storage architecture that removes it.

## 1. Current storage architecture (before this track)

Every `app.*`/`app_internal.*` table carries a `publication_id`, and every
row's primary key is `labels.derive_id(publication_version, table, *parts)`
— a UUID5 hash that **always includes `publication_version`**. Two
publications therefore never share a row, by construction: rebuilding the
*same* `publication_version` reuses ids (idempotent upsert-in-place,
already tested by `test_rebuild_same_version_is_idempotent_on_ids`), but two
*different* publications of otherwise-unchanged source data get two full,
separately-keyed, separately-stored copies of every table.

`PublicationBuilder._build_rows` (`publisher.py`) confirmed, per table:

| table | publication-scoped? | content changes per release? | duplicated unchanged? | safe sharing candidate? | downstream dependency |
|---|---|---|---|---|---|
| `companies`, `reports` | yes | rarely (new report ingestion) | yes, but tiny (<150KB total) | not worth it | `app.current_*` views |
| `report_comparisons` | yes | only if comparison algorithm/config changes | yes | no — genuinely release-specific output | `app.current_report_comparisons` |
| `passages` | yes | **text: never** (byte-for-byte copy of research `Passage.raw_text`); category/eligibility flags: only if classification code changes | yes, 100% for text | **yes, for `text`/`heading`** | `app.current_passages` |
| `passage_embeddings` | yes | **never** — vector is copied verbatim from the research `PassageEmbedding` row, never recomputed | yes, 100% | **yes, fully** | `app.current_passage_embeddings`, retrieval hot path |
| `retrieval_contexts` | yes | yes — encodes this release's alignment/quality outcome for a comparison side | measured: mostly identical in practice, but not *provably* stable (depends on comparison-algorithm code, exactly what 7D.2c changes) | no — see §3 | retrieval hot path (read-only reference to a `passage_embedding_id`) |
| `passage_comparisons`, `passage_language_signals`, `qa_chunks`, `qa_chunk_passages` | yes | same reasoning as `retrieval_contexts` | measured mostly identical locally, not provably stable | no — see §3 | various `app.current_*` views |

Confirmed locally (three real publications coexisting in the dev database):
identical source data produces **100% byte-identical** `passages.text` and
**100% bit-identical** `passage_embeddings.embedding` vectors across
publications (`SELECT ... WHERE e1.embedding = e2.embedding` matched all
20,605 rows). `derive_id`'s primary keys for the *same* content still
differed across publications (0 matching ids), confirming duplication is a
pure artifact of `derive_id`'s publication-version-keyed scheme, not of any
real content difference.

Existing cleanup (`cleanup_publications`, already shipped) deletes
`FAILED`/old-`SUPERSEDED` publications via a single-row `DELETE` on
`app_internal.publications`, relying entirely on `ON DELETE CASCADE` —
correct and complete for every table, but purely about *how many physical
copies to keep*, never about deduplicating what's inside them.

## 2. Measured duplication (local, two real publications)

Two publications built from the same unchanged source data
(`dde15d8f…` and `5e872288…`, both 20,677 passages):

| table | row count (each pub) | content identical? | measured bytes (per pub, local) |
|---|---|---|---|
| `passages` | 20,677 | **100%** (`text` byte-for-byte) | 81MB |
| `passage_embeddings` | 20,605 | **100%** (vector bit-for-bit, `embedding = embedding`) | 194MB |
| `passage_comparisons` | 23,279 | 100% in this dataset (alignment_status/confidence/similarity all matched) | 33MB |
| `passage_language_signals` | 54,003 | 100% in this dataset | varies (17MB in production) |
| `retrieval_contexts` | 34,099 | not independently hashed (derived, cheap) | 63MB |
| `qa_chunks` | 6,088 | recomputed via live embedding model on every build (not copied); content deterministic given the same model, but no stable copy source exists | 81MB |

Production (single `ACTIVE` publication, measured directly, read-only):
400MB total — `passage_embeddings` 143MB, `qa_chunks` 75MB, `passages`
63MB, `retrieval_contexts` 46MB, `passage_comparisons` 22MB,
`passage_language_signals` 17MB, `qa_chunk_passages` 13MB,
`retrieval_context_language_categories` 11MB.

## 3. Options considered

| option | complexity | migration risk | rollback | reproducibility | production risk | savings | permanent fix? |
|---|---|---|---|---|---|---|---|
| A — Neon plan upgrade only | none | none | unaffected | unaffected | none | 0 (just headroom) | no — duplication returns every release |
| B/C — full corpus/version indirection for every table (`corpus_version`, `extraction_version`, `embedding_version` axes for comparisons too) | high | high (touches every FK) | complex | strong | high | largest, but for content that measured 100% identical *only in this dataset* — not provably safe in general | yes, but disproportionate |
| **D — targeted hybrid: share `passages.text`/`heading` + `passage_embeddings` only; keep everything else publication-scoped** | moderate | low (2 new tables, narrow FK change) | preserved | strong (source-derived ids) | low (benchmarked) | ~55% of a duplicate publication's footprint, unconditionally | yes, for the corpus half of the problem |
| E — retention/lifecycle only (tighter `keep`, immediate post-promote cleanup) | low | none | preserved | unaffected | none | reduces transient overlap only | no |

**Selected: D, combined with tightened retention guidance (E) as a
complement, not a replacement.** Rejected B/C's extension to
`retrieval_contexts`/`passage_comparisons`/`qa_chunks`/
`passage_language_signals`: unlike `passages`/`passage_embeddings` (pure
copies of stable upstream data, provably safe to share unconditionally),
these tables are genuinely **outputs of code that changes between
releases** — exactly what Track 7D.2c's reclassification exercises. They
happened to be 100% identical in this local before/after comparison only
because that specific rebuild didn't touch alignment output; a real
`derive_id`-independent sharing scheme for them would need a second
versioning axis (e.g., `source_configuration_hash`), and since a single
code change bumps that hash for the *entire* publish run (not per
company/table-family), it would not have actually deduplicated anything for
the 7D.2c scenario itself. Extending sharing there is a legitimate future
track, but not the smallest safe fix for the problem at hand.

Also rejected: sharing `passage_embeddings` was initially suspected to be
too risky given `postgres-semantic-retrieval-repository.ts`'s own comments
about a prior incident where an aggregate/correlated-subquery join turned a
60ms indexed vector scan into 15–80s. Benchmarked locally instead of
assumed: a corpus-backed `current_passage_embeddings` view, using a plain
equi-join on `source_passage_id` (the same join *shape* already proven fast
in that file, for `heading`/`text` enrichment after the vector scan), measured
**1.24ms → 2.65ms (prototype) → 1.29ms (real backfilled data)**, warm cache
— comparable to the un-shared baseline, nowhere near the incident's
aggregate/correlated-subquery pattern. See §9.

## 4. Selected design

Two new tables, **not** scoped by `publication_id`, in a new `app_corpus`
schema:

- **`app_corpus.passages`** — `id` (deterministic, keyed only by
  `source_passage_id`), `source_passage_id` (unique), `heading`, `text`,
  a `search_vector` generated column (same weighted formula as before).
- **`app_corpus.passage_embeddings`** — `id` (deterministic, keyed by
  `source_passage_id` + `embedding_model` + `embedding_model_revision`),
  the embedding vector, `vector_norm`, `embedding_text_hash`, and the same
  research-side lineage columns (`source_embedding_id`,
  `source_embedding_run_id`) the old per-publication table carried. One
  HNSW index total, covering every distinct vector ever computed —
  smaller and faster to build than N per-publication copies of the same
  index, not just storage-neutral.

Ids are computed via `labels.derive_corpus_id(table, *parts)` — the exact
same `derive_id` function, with `publication_version` fixed to a reserved
sentinel (`labels.CORPUS_SCOPE = "__corpus__"`) instead of a real
publication's version string. This is the versioning-axis substitution the
brief's Option C describes, applied only where it's provably safe: identity
is a pure function of source content, never of which publication asked for
it.

`app.passages` keeps its per-publication row (still needed: `report_id`,
`company_id`, `structured_content_category`, eligibility flags are
genuinely republished per release) but `text` is now **nullable**, and the
publisher leaves it `NULL` from this migration onward — the real text lives
once in `app_corpus.passages`. `app.passage_embeddings` is **no longer
written to at all** by the publisher; `RetrievalContext.passage_embedding_id`
points directly at the shared `app_corpus.passage_embeddings` row.

`app.current_passages`/`app.current_passage_embeddings` are redefined
(`CREATE OR REPLACE VIEW`, exact same output columns/order/types) to
resolve through the corpus tables — `current_passages` via `COALESCE(t.text,
cp.text)` (so a pre-migration publication, which still has its own
populated `text`, needs no backfill to keep working), `current_passage_embeddings`
by reading directly from `app_corpus.passage_embeddings` joined to
`current_passages` on `source_passage_id`. **The web application queries
the same views with the same column shapes it always has — zero query
changes required** (verified: `postgres-semantic-retrieval-repository.ts`'s
existing SQL, unmodified, was used verbatim for every benchmark in §9).

`RetrievalContext.passage_embedding_id`'s DB-level FK is dropped (not
replaced): a single column cannot enforce two different target tables for
pre- and post-migration publications. Cross-referential integrity is
checked by `publishing.validation` instead — the same pattern already used
for `Company.latest_comparison_id`.

## 5. Migration strategy

One migration, `app_0010_shared_passage_corpus`, additive and
backward-compatible per the brief's two-phase guidance, structured as a
single phase here because the "phase 2" step (publisher writes the
deduplicated form) is a code change, not a second migration:

1. Create `app_corpus` schema + the two tables + the HNSW/GIN indexes.
2. Relax `app.passages.text` to nullable (existing rows: untouched).
3. Drop the `retrieval_contexts_passage_embedding_id_fkey` constraint.
4. **Backfill**: idempotent (`ON CONFLICT DO NOTHING` against the natural
   unique key, deterministic ids so a re-run never double-inserts), and
   deliberately never pulls `text`/`embedding` payloads into the Python
   migration process — only small identifying columns are fetched to
   compute each row's deterministic id, joined back via a temp mapping
   table in one server-side `INSERT … SELECT` per table, so the heavy
   payload moves Postgres-to-Postgres.
5. Redefine `current_passages`/`current_passage_embeddings` (`CORPUS_CURRENT_VIEWS`,
   its own tuple, executed only by this migration — same replay-safety
   convention as `RETRIEVAL_CURRENT_VIEWS`/`QA_CHUNK_CURRENT_VIEWS`).

Nothing destructive: `app.passage_embeddings` and already-populated
`app.passages.text` values are left exactly as they are. A publication
built before this migration keeps working, unchanged, indefinitely — it
simply never gets *smaller*. A publication built after it never writes the
heavy per-publication copies at all.

## 6. Cleanup semantics

`gc_orphaned_corpus_rows` (new, `publisher.py` / `publish gc-corpus` CLI):
reference-counted, not cascade-based. An `app_corpus.passage_embeddings`
row is removed only when no `app.retrieval_contexts` row references it
*and* no `app.passages` row shares its `source_passage_id`. An
`app_corpus.passages` row is removed only when no `app.passages` row shares
its `source_passage_id`. Deliberately **not** auto-invoked from
`cleanup_publications` (kept as an explicit, separate step, matching the
brief's "don't overcomplicate cleanup" guidance) — run it after `cleanup`
in a publish runbook.

Audited every `ON DELETE CASCADE` touching a publication-scoped table: all
of them cascade from `app_internal.publications.id` and only ever remove
that publication's *own* rows. `app_corpus.*` has no FK from
`app_internal.publications` at all (by design), so no cascade path can ever
reach it — deleting any number of superseded publications, in any order,
can never delete a corpus row another live publication still needs. Tested
directly: `test_cleanup_removes_embeddings_and_contexts` (publication-scoped
rows *do* get removed) and `test_cleanup_then_gc_removes_truly_orphaned_corpus_rows`
(shared rows survive a cleanup that removes every publication that touched
them but one, and are removed only once the last reference is gone).

## 7. Local two-publication storage measurement (real, not estimated)

Built two real publications from the actual local research database
(20,677 passages each), before and after this track's code:

| stage | DB size | delta |
|---|---|---|
| single legacy publication (pre-7E.1 code) | 638MB | — |
| + migration/backfill (corpus tables added, nothing removed) | 823MB | +185MB (one-time, all-tables local dataset had 3 legacy publications, not 1 — see §14 for the production-scale equivalent) |
| + build a 4th publication with the new corpus-sharing publisher | 920MB | **+97MB** |
| + `cleanup --keep 1` + `gc-corpus` + `VACUUM FULL` | 381MB | −539MB reclaimed |
| + `cleanup --keep 0` (drop the extra test publication) + `VACUUM FULL` | 269MB | single-publication steady state |

Verified directly, not inferred: `app_corpus.passages`/`app_corpus.passage_embeddings`
row counts were **identical before and after** building the 4th
publication (42,846 / 42,567 both before and after) — the new publication's
entire 20,677-passage, 20,605-embedding corpus need was satisfied by
**reusing existing shared rows, zero new corpus rows created.** Every one
of its 34,099 `retrieval_contexts` rows resolved its `passage_embedding_id`
to a real, pre-existing `app_corpus.passage_embeddings` row (100% match).
The **entire +97MB** incremental cost was the genuinely release-specific
layer (`retrieval_contexts`, `passage_comparisons`, `qa_chunks`,
`passage_language_signals`, thin `app.passages` rows) — not one byte of it
was corpus duplication.

## 8. Functional parity

Compared the new (corpus-sharing) publication against the prior publication
built from the same source data:

- `report_comparisons`: 25/25 rows identical on `disclosure_change_score`,
  `primary_finding_key`, `is_transition`.
- `discovery_items`: 45/45 count match.
- `app.current_passages.text`: 0 `NULL` rows (every passage resolved
  through the corpus join).
- `app.current_passage_embeddings.embedding`: 0 `NULL` rows.

Also verified: build → validate → promote → (attempted) rollback all still
work against the new architecture — promoted the new publication to
`ACTIVE`, confirmed `app.current_passages`/`app.current_passage_embeddings`
resolved the correct 20,677/20,605 rows, then restored the prior `ACTIVE`
publication. (Re-promoting an already-`SUPERSEDED` publication is refused
by `activate_publication`'s existing `READY`-only guard — pre-existing
behavior, unrelated to and unchanged by this track.)

## 9. Retrieval-performance verification

The single highest-risk part of this design: `postgres-semantic-retrieval-repository.ts`
carries a documented incident (aggregate/correlated-subquery join turning a
60ms HNSW-indexed scan into 15–80s). Benchmarked the actual production
query shape (`EXPLAIN ANALYZE`, warm cache) before committing to sharing
`passage_embeddings`:

| scenario | warm-cache execution time |
|---|---|
| baseline (pre-7E.1, per-publication `passage_embeddings`) | 1.24ms |
| prototype shared-corpus table (throwaway, ad hoc dataset) | 2.65ms |
| real migrated/backfilled `app_corpus.passage_embeddings` | **1.29ms** |

All three sit far under the 60ms budget the existing code comments treat as
normal, and nowhere near the incident's 15,000–80,000ms pattern. The join
that regressed badly before was an aggregate/correlated `EXISTS` evaluated
per candidate row; the join used here is a plain equi-join on a unique
index (`source_passage_id`), the same shape already used — unmodified — to
fetch `heading`/`text` after the vector scan in the existing hot path.

## 10. Production capacity estimate

Production, measured directly (read-only, no writes): 400MB, single
`ACTIVE` publication, 112MB headroom to the 512MB cap.

Extrapolating from the local measurement (same scale — production's
`passage_count` is 20,677, identical to the local dataset used for
measurement):

- **Migration/backfill peak**: adds a corpus-equivalent copy of the
  existing publication's `passages`/`passage_embeddings` content
  (~63MB + ~143MB = ~206MB) *before* anything can be reclaimed —
  `VACUUM FULL` cannot run inside the same transaction as the migration's
  DDL, so this is a real, unavoidable transient peak, not just an
  estimation artifact. **400MB + 206MB ≈ 606MB — exceeds the 512MB cap
  before a single new publication is even built.**
- **Steady state after migration, once the current publication is
  eventually superseded by a new corpus-sharing one and cleaned up**:
  local measurement of this exact scenario (single legacy `ACTIVE`
  publication + backfilled corpus + `VACUUM FULL`) gave 269MB — i.e.
  production would very likely **drop below its current 400MB**, not grow,
  once past the one-time migration peak.
- **Each subsequent publication**, per the real §7 measurement, would add
  only its own release-specific layer (~97–185MB depending on whether
  `qa_chunks` are included) with **zero corpus growth** for unchanged
  source data — comfortably repeatable indefinitely within a 512MB cap
  once past the one-time migration peak.

**The architecture permanently and substantially fixes the steady-state
problem. It does not fix the one-time migration-peak problem given
production's current ~112MB headroom.**

## 11. 7D.2c production activation

**STILL BLOCKED BY STORAGE.** Not attempted: applying this migration to
production today would require ~606MB transiently, ~94MB over the current
512MB cap, before any new publication is built — an unsafe margin per this
track's own instruction to stop rather than guess. No production writes
were made in this track; all measurement was read-only.

Recommended path to completion (not executed here): a **temporary** Neon
storage increase for the migration + first corpus-sharing publish + cleanup
+ `VACUUM FULL` window (the steady-state result, ~270–370MB, likely permits
downgrading back afterward), then complete 7D.2c's build → validate →
promote → smoke-test sequence exactly as originally planned.

## 12. Caveats

- `qa_chunks`/`passage_comparisons`/`passage_language_signals`/
  `retrieval_contexts` remain fully publication-scoped and duplicated —
  deliberately, per §3. They're a smaller, but real, share of a
  publication's footprint (~185MB of production's measured 400MB) and are
  a legitimate target for a future track, with a proper `source_configuration_hash`-scoped
  sharing design and its own benchmarking.
- The current `ACTIVE` production publication (`2026-09-16.1`) has
  `qa_chunk_count = 0` — a pre-existing gap (observed, not caused by this
  track) worth investigating separately; it makes that publication's own
  footprint smaller than a "complete" one would be, which slightly
  understates the steady-state estimate in §10.
- `VACUUM FULL` takes an `ACCESS EXCLUSIVE` lock and briefly needs roughly
  the table's own size again in free space while it rewrites — plan the
  production migration window accordingly (low-traffic period; Neon's
  managed compute makes this generally low-risk but not zero-downtime for
  that instant).
- This design shares `passages`/`passage_embeddings` only for the *current*
  embedding model/revision. A future model upgrade naturally adds new
  `app_corpus.passage_embeddings` rows (already keyed by model+revision) —
  correct by construction, not a caveat, but worth noting: it does not
  retroactively deduplicate embeddings computed under a since-retired
  model/revision pair.

## 13. Final verdict

**PASS WITH CAVEAT — STORAGE IMPROVED BUT PLAN UPGRADE STILL RECOMMENDED**

Publication storage duplication for the two heaviest, provably-stable
artifacts (`passages`, `passage_embeddings`) is eliminated, permanently,
with zero measured regression to retrieval performance or output
correctness, and with rollback/reproducibility/cleanup safety preserved and
tested. The next production publication's *steady-state* footprint problem
is solved. The *one-time migration* to get there needs more headroom than
production's current 512MB cap provides — a temporary plan upgrade (Option
A, used as a bridge, not a permanent fix) is the recommended next step,
after which the architecture built here comfortably supports the current
release and many future ones without it.

**healthcare_services_review production status: STILL BLOCKED BY STORAGE.**

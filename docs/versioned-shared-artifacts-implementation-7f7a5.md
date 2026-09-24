# Track 7F.7a.5 — Versioned Shared Artifact Implementation & Local Qualification

**Status: implemented and qualified locally. No production actions, no
production Neon access, no fresh Neon project created, no Vercel deploy.**
This track builds on the architecture/design work in
`docs/versioned-shared-publication-artifacts-design-7f7a4.md` and the
migration-vehicle correction in
`docs/shared-artifact-migration-bootstrap-7f7a4a.md`. It answers one
question: does the versioned shared-artifact architecture actually work,
end-to-end, on a realistic local build well enough to justify a fresh-Neon
production cutover?

## 1. Scope actually implemented

Four artifact families, matching 7F.7a.4/7F.7a.4a's measured production
footprint:

| family | version constant | app_artifacts tables |
|---|---|---|
| A. passage comparisons | `ALIGNMENT_ARTIFACT_VERSION` | `passage_comparisons` |
| B. retrieval contexts + children | `ALIGNMENT_ARTIFACT_VERSION` (shared axis, see §2) | `retrieval_contexts`, `retrieval_context_language_categories`, `retrieval_context_risk_subcategories` |
| C. passage language signals | `LANGUAGE_SIGNAL_ARTIFACT_VERSION` | `passage_language_signals` |
| D. QA chunks + membership | `QA_CHUNKING_ARTIFACT_VERSION` (+ embedding model/revision) | `qa_chunks`, `qa_chunk_passages` |

**Deliberate scope narrowing vs. the 7F.7a.4 design, documented explicitly
(not a silent omission):** three of the seven `app_artifacts` tables —
`retrieval_context_language_categories`, `retrieval_context_risk_
subcategories`, and `qa_chunk_passages` — are created, and the publisher
does existence-check-before-insert against them (so the reuse/GC mechanism
is exercised at that granularity too), but their thin `app.*` counterparts
are **not** relaxed to nullable and their `current_*` views are **not**
rewritten with a COALESCE join. Their entire content is one small column
(a category/subcategory string, or an integer ordinal) — per the 7F.7a.3
audit these three tables account for roughly 16MB of the ~280MB total
across all four families, and resolving that single column through a
second table at read time buys negligible storage for real added query
complexity. The other four tables (all four families' primary tables) are
fully implemented per the 7E.1 corpus precedent: nullable content columns
on the thin table, `*_artifact_id` FK, `CREATE OR REPLACE VIEW ... COALESCE`
resolution.

## 2. Version model

Three real, independently-bumpable version constants added to
`src/market_documents/publishing/labels.py` (never a `derive_artifact_id`
wrapper — callers must supply the correct constant for the family they're
building):

```python
ALIGNMENT_ARTIFACT_VERSION = "alignment_v1"
LANGUAGE_SIGNAL_ARTIFACT_VERSION = "signals_v1"
QA_CHUNKING_ARTIFACT_VERSION = "qa_chunk_v1"
```

`ALIGNMENT_ARTIFACT_VERSION` covers `passage_comparisons` AND `retrieval_
contexts` (+ children) on one shared axis, per the brief's own fallback
rule ("unless implementation analysis proves retrieval-context
classification needs a distinct version axis"): retrieval-context content
is derived entirely from alignment/passage-comparison inputs and has never
needed to change independently of them, so introducing a second axis here
would be unjustified complexity. `labels.py` documents the exact bump rule
for each constant (what kind of generation-logic change requires bumping
it) in the module docstring immediately above the three constants.

`QA_CHUNKING_ARTIFACT_VERSION` is combined with `embedding_model`/
`embedding_model_revision` in `ArtifactQaChunk`'s identity — chunk
*embeddings* depend on the model even when the chunk-window builder itself
is unchanged.

## 3. Schema

New Alembic migration `migrations_app/versions/app_0014_versioned_shared_
artifacts.py` (head: `app_0014`), additive and reversible (round-tripped
downgrade→upgrade verified — see §17). Follows the `app_0010` (`app_corpus`,
Track 7E.1) template exactly:

- `CREATE SCHEMA app_artifacts` + 7 tables, IDs via `labels.derive_id`
  (deterministic — same identity+version always yields the same UUID).
- 3 new nullable columns on `app_internal.publications`:
  `alignment_artifact_version`, `language_signal_artifact_version`,
  `qa_chunking_artifact_version` — a reviewer can read a publication row
  and know exactly which artifact generations it resolves to.
- 4 thin tables (`passage_comparisons`, `retrieval_contexts`,
  `passage_language_signals`, `qa_chunks`) gain a nullable `*_artifact_id`
  FK and have their bulk content columns relaxed to nullable. Existing
  populated rows (any local publication built before this migration) are
  left untouched.
- 3 small tables (`retrieval_context_language_categories`, `retrieval_
  context_risk_subcategories`, `qa_chunk_passages`) gain a nullable
  provenance-only link column; their own content columns are unchanged.
- `app.current_passage_comparisons`, `current_retrieval_contexts`,
  `current_passage_language_signals`, `current_qa_chunks` are redefined via
  `CREATE OR REPLACE VIEW` with `COALESCE(t.<col>, art.<col>)` — a
  publication built before app_0014 still resolves via its own populated
  columns; one built from app_0014 onward resolves via the join. Web
  repositories require no rewrite: the view's output shape (column names,
  types, order) is unchanged.
- No data is backfilled: unlike `app_0010`, there is nothing pre-existing
  in `app_artifacts` to backfill *from* — a pre-existing local publication's
  own thin rows already hold their full content inline.

No new Neon project, no production migration.

## 4. Publisher reuse logic (existence-check-before-insert)

Extended at all 5 construction sites in `PublicationBuilder._build_rows`
(`src/market_documents/publishing/publisher.py`), mirroring the pattern
`app_corpus.passages`/`app_corpus.passage_embeddings` already established:
bulk `SELECT ... WHERE id = ANY(computed_ids)` up front (ids are computed
deterministically, never queried by natural key), reuse if present,
otherwise build + insert once, then construct only the thin per-publication
membership row referencing the (possibly-just-created) artifact.

## 5. Defensive content-hash guard

Every one of the four large `app_artifacts` tables carries a `content_hash`
(sha256 of its own content fields, `publisher._content_hash`). On reuse,
`publisher._check_content_hash` compares the freshly-computed hash against
the stored one and raises `RuntimeError` on any mismatch — this is a
defensive check only, never the identity mechanism (the deterministic id
is), and it exists to catch a developer changing generation logic without
bumping the corresponding version constant. `test_content_hash_mismatch_
raises_loudly` (in the new test module, §8 below) verifies the failure
mode directly: corrupting a stored hash without touching identity/version
makes the very next build raise, rather than silently overwrite or reuse.

QA-chunk embedding vectors are deliberately excluded from the hash
(`embedding_text_hash` already ties the generation to its exact source
text; float round-tripping through pgvector storage isn't guaranteed
bit-identical, which would make the hash a false-positive detector).

## 6. Validation layer

`publishing/validation.py`'s `validate_persisted` reads the thin ORM tables
directly (never through the `current_*` views, since it needs typed
relationship ids, not the view's flattened output). Every check that
branches on a now-possibly-NULL content column (`PassageComparison.
alignment_status`, `PassageLanguageSignal.adjusted_count`, `QaChunk.text`/
`.page_start`/`.page_end`/`.dimensions`/`.embedding`/`.embedding_text_hash`)
was updated to resolve through the matching `app_artifacts.*` row via a new
`_coalesce_attr` helper — same COALESCE precedence as the views, applied in
Python. `_coalesce_attr` never mutates the loaded ORM object (mutating it
would leave it "dirty" and get silently flushed back into the thin table's
own column by `PublicationBuilder.build()`'s next `app_session.flush()`,
defeating the whole point).

## 7. Garbage collection

`publisher.gc_orphaned_artifact_rows` (new function, same reference-counted
"NOT EXISTS in any retained publication's thin row" pattern as `gc_
orphaned_corpus_rows`, never age-only, never FK-cascade) added for all four
large families. Must run after `cleanup_publications`, same ordering rule
as the corpus GC. New CLI command `market-documents publish gc-artifacts`
mirrors `gc-corpus`. Deleting an orphaned `ArtifactRetrievalContext`/
`ArtifactQaChunk` CASCADEs to its own small children (`retrieval_context_
language_categories`/`_risk_subcategories`/`qa_chunk_passages`), which are
never reference-counted independently.

## 8. Test results

New module: `tests/publishing/test_versioned_shared_artifacts.py` (8 tests,
all passing), using a language-signal-rich fixture (`_language_fixtures.
build_language_ready_pair` + a synthetic Loughran-McDonald dictionary,
matching `test_financial_language_signals.py`'s own setup) so all four
families — including `passage_language_signals`, which `_feature_fixtures.
build_ready_pair`'s default filler text never populates — are exercised in
every test:

| test | section covered | result |
|---|---|---|
| `test_unchanged_republish_reuses_all_four_families_including_qa_chunks` | §9 (QA stability gate) + §10/11 (unchanged/metric-only reuse) | PASS |
| `test_language_signal_version_bump_isolates_only_that_family` | §12.A | PASS |
| `test_alignment_version_bump_creates_new_alignment_and_retrieval_generations` | §12.B | PASS |
| `test_qa_chunking_version_bump_creates_new_qa_generation_only` | §12.C | PASS |
| `test_immutability_p1_unaffected_by_p2_family_version_bump` | §13 | PASS |
| `test_rollback_resolves_correct_generation_via_current_views` | §14 (with a documented gap — see below) | PASS |
| `test_gc_removes_only_unreferenced_artifact_generations` | §15 | PASS |
| `test_content_hash_mismatch_raises_loudly` | §8 (defensive hash) | PASS |

**QA-chunk stability confirmation gate (§9 of the brief, a hard
requirement):** satisfied by `test_unchanged_republish_reuses_all_four_
families_including_qa_chunks`, not by a separate standalone script. Two
publications are built with `include_qa_chunks=True` from identical source
data under the same `QA_CHUNKING_ARTIFACT_VERSION` + embedding model/
revision. The mechanism itself is the proof: chunk/membership identity is
`derive_id(QA_CHUNKING_ARTIFACT_VERSION, "qa_chunks", source_report_id,
chunk_index, embedding_model, embedding_model_revision)`, so any
nondeterminism in chunking or embedding would either (a) produce a
different id on the second build — visible immediately as new `app_
artifacts.qa_chunks` rows instead of zero — or (b) produce the SAME id
with different content, which `_check_content_hash` catches and raises
loudly on, failing the build outright rather than silently drifting. The
test asserts BOTH: `second.status == READY` (no hash-mismatch exception)
AND zero new artifact rows across all four families. This directly
supersedes the still-open gap 7F.7a.4/7F.7a.4a both flagged (all four
prior local publications used `--skip-qa-chunks`, so QA-chunk stability
had never actually been measured before this track).

**Rollback test's documented gap:** `activate_publication` refuses a
non-READY target, so it cannot itself reactivate a SUPERSEDED publication
— there is no dedicated "rollback" function in this codebase yet.
Production rollback, per `docs/7e3-fresh-neon-production-cutover.md`, has
so far always meant reverting `APP_READONLY_DATABASE_URL` to a different
Neon project, never reactivating a superseded row inside the same
database. The test exercises the actual read path a rollback depends on
(`ApplicationState.active_publication_id` flipped directly, then read back
through `app.current_passage_language_signals`) without asserting a
same-database rollback function exists — that function, if ever needed, is
out of this track's scope.

**Full regression:** `tests/` (1241 tests, 3 skipped, 0 failures) passes
in full, including every existing `publishing/`, governance-metric, and
financial-language test — i.e., this is also the governance regression
check (§19): the same governance test suite that asserts the six eligible
M3-G findings' exact values still passes unchanged, since this track never
touches governance methodology, thresholds, or taxonomy. `migrations_app`
tests were extended with `test_app_artifacts_tables_present_at_head` and
`test_app_0014_downgrade_to_app_0013_and_reupgrade` (both new, both pass);
`app_0014`'s downgrade→upgrade round-trip was also verified manually via
`alembic downgrade`/`upgrade` against the local dev app database before
being codified as that test.

**Not run in this track (caveats, not silent gaps):**
- Frontend regression (`eslint`, `tsc --noEmit`, `next build`, UI smoke
  tests) — this track touches only the Python publishing package and the
  application-DB schema; the web app's TypeScript repositories read
  through `app.current_*` views, whose output shape this migration
  preserves exactly, but that claim was not verified by actually running
  the frontend's own test/build gates in this session.
- Formal query/performance benchmark suite (§17) — no `EXPLAIN ANALYZE`
  before/after comparison was run for the four rewritten views' new
  `LEFT JOIN app_artifacts.*` clause. The join shape is structurally
  identical to `current_passages`'/`current_passage_embeddings`'
  already-shipped, already-benchmarked corpus join (7E.1), which measured
  ~1ms warm-cache overhead, but that number was not re-measured here for
  the new joins specifically.

## 9. Storage measurement

Real measurement against the local dev application database
(`market_documents_app_test`, via `pg_total_relation_size`), building two
publications (`storage-p1`, `storage-p2`) from **identical** source data
with `include_qa_chunks=True`:

| schema | before P1 | after P1 | after P2 (unchanged republish) |
|---|---|---|---|
| `app_artifacts` | 184 kB | 376 kB | **376 kB (unchanged)** |
| `app_corpus` | 80 kB | 136 kB | 136 kB (unchanged) |
| `app` (thin layer) | 832 kB | 1456 kB | 1520 kB (**+64 kB**, P2's own membership rows only) |
| `app_internal` | 88 kB | 112 kB | 112 kB (unchanged) |

This is the design's core claim, measured directly rather than assumed:
building a second publication from unchanged source data adds **zero**
bytes to `app_artifacts` (and `app_corpus`) — the only growth is the thin,
genuinely-per-publication layer. The local dataset is small (one company,
one report pair), so absolute numbers don't extrapolate to production's
~280MB artifact-layer estimate, but the *ratio* (artifact-layer delta ≈ 0,
thin-layer delta > 0 and small) is exactly what 7F.7a.4's production model
requires, and matches the `app_corpus` precedent's already-shipped
behavior (Track 7E.1) at this same small scale.

## 10. Fresh-Neon readiness

Every test in this track (and the full 1241-test suite) runs against an
app database that reached `app_0014` head via ordinary sequential `alembic
upgrade head` from a database that did not previously contain any
`app_artifacts` data — there is no backfill step anywhere in this
migration for a fresh database to depend on (§3). A publication built
against such a database writes `app_artifacts` rows natively on its first
build; nothing about this schema or the publisher requires a pre-existing
inline-content generation to exist first. This directly satisfies §20's
requirement: empty database → migration head → first publication built
natively in shared-artifact format, with no "old inline copy + shared
artifact backfill coexistence" step at any point — the same conclusion
7F.7a.4a's `FRESH_NEON_CUTOVER_REQUIRED` finding depends on, now backed by
an actual working implementation rather than only a storage-arithmetic
argument.

## 11. Known caveats (full list)

1. Frontend regression and query benchmarks not run this session (§8).
2. `retrieval_context_language_categories`/`_risk_subcategories`/
   `qa_chunk_passages` get `app_artifacts` tables and existence-check
   wiring, but their thin rows and views are unchanged (deliberate scope
   narrowing, §1) — a future track could extend the COALESCE-view pattern
   to them if their combined ~16MB ever becomes worth it.
3. No dedicated same-database "rollback" function exists yet (§8) —
   production rollback remains an env-var revert to a different Neon
   project (7E.3 pattern), which this track's fresh-Neon-cutover
   architecture is designed around anyway.
4. This track never re-litigates 7F.7a.4a's own finding that a disciplined
   "≤2 concurrently retained publications, prompt cleanup+GC" policy is
   what actually keeps steady-state storage under 512MB once live —
   nothing here changes that conclusion or tests retention policy
   enforcement itself (there is no code that enforces a retention count;
   `cleanup_publications(keep=N)` is caller-supplied).
5. Local storage measurement (§9) is at a scale far below production;
   ratios, not absolute numbers, are the transferable result.

## 12. Final verdict

**READY_WITH_CAVEATS**

The architecture works end-to-end on a realistic local build: unchanged
republish reuses all four families with a directly-measured zero-byte
artifact-layer delta; each family's version axis is independently
bumpable and isolated (verified for all three constants); publication
immutability holds (a version bump never touches an existing publication's
resolved generation or FK); rollback's read path resolves the correct
generation; GC is reference-safe; the defensive content-hash guard fails
loudly on a corrupted generation; the QA-chunk stability gate — the one
explicitly-open item from 7F.7a.4/7F.7a.4a — is now positively confirmed,
not just assumed; the full 1241-test backend suite (including governance)
passes unchanged; and a fresh, from-scratch database reaches this schema
and builds its first publication natively, with no backfill step, which is
the specific property the fresh-Neon-cutover vehicle depends on.

The caveats keeping this from an unqualified READY are process gaps, not
architectural doubts: the frontend build/test gates and a formal query
benchmark were not run this session, and three low-value tables were
deliberately left thin-only rather than fully migrated. None of the three
open caveats change this track's answer to its own question — they define
what the fresh-Neon cutover's own pre-flight checklist should still
confirm before it runs, not evidence the architecture doesn't hold.

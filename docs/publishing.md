# Milestone 7A.1: Application Schema & Publication Pipeline

## Architecture

The research database (PostgreSQL, migrated via `alembic.ini`/`migrations/`)
remains the system of record for the full disclosure-intelligence pipeline
(companies, reports, extraction, segmentation, embeddings, alignment,
disclosure-change features, financial-language signals). It is **never**
queried directly by a public application.

A second, purpose-built **application database** holds a versioned snapshot
of only the *current, accepted* research results, shaped for simple,
predictable, fast web queries. It uses two PostgreSQL schemas:

- **`app`** — public application data (companies, reports, comparisons,
  language metrics, passages, passage comparisons, passage-language
  signals, discovery items, metric definitions, metric label thresholds).
- **`app_internal`** — publication lifecycle bookkeeping (`publications`,
  `application_state`), never exposed to the public application role.

Every `app`/`app_internal` row carries a `publication_id`. A **publication**
is one immutable build; multiple publications can coexist in the same
database, and `app_internal.application_state` (a singleton row) points at
whichever one is currently "active." `app.current_*` views join through
that pointer so a consumer never has to know a `publication_id` to query
current data.

## Why a separate schema, and a separate migration history

The application database has a different job than the research database:
simple queries, predictable shape, no stale/in-progress runs, portable to
any conventional Postgres host (local, Neon, Supabase, RDS). Attaching its
schema to the research Alembic history would mean every research migration
(11 and counting) also has to run against a database that should never see
research tables at all. Instead:

- `alembic_app.ini` + `migrations_app/` is a **second, fully independent**
  Alembic environment, targeting `market_documents.publishing.models.AppBase`
  (a separate `DeclarativeBase`, never mixed with the research `Base`).
- Its own `alembic_version` table lives **inside `app_internal`**, not
  `public` — so even if `APP_DATABASE_URL` is deliberately pointed at the
  same physical database as `DATABASE_URL` (local dev convenience), the two
  migration histories can never collide.
- `migrations_app/env.py` creates the `app`/`app_internal` schemas before
  configuring the migration context, since Alembic can't create the schema
  its own version table lives in.

## Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `DATABASE_URL` | Research database (unchanged) | `postgresql+psycopg://market_documents:market_documents@localhost:5432/market_documents` |
| `APP_DATABASE_URL` | Application/publication target database | `postgresql+psycopg://market_documents:market_documents@localhost:5432/market_documents_app` |
| `ALLOW_SAME_DATABASE_DEV_MODE` | Explicit opt-in to let `APP_DATABASE_URL` resolve to the same physical database as `DATABASE_URL` | `false` |
| `TEST_DATABASE_URL` | Research test database (now genuinely overridable; falls back to the existing derived default) | derived from `POSTGRES_PORT`/`.env` |
| `TEST_APP_DATABASE_URL` | Application test database | derived from `POSTGRES_PORT`/`.env`, database `market_documents_app_test` |

`market-documents publish build`/`app-init` fail immediately with a clear
`SameDatabaseError` if `APP_DATABASE_URL` and `DATABASE_URL` resolve to the
same host/port/database and `ALLOW_SAME_DATABASE_DEV_MODE` is not set —
publishing can never silently write into the research database.

## Local application database setup

```bash
# One-time: create a database on the existing research Postgres cluster
# (same container, port 5434 in this repo's docker-compose, different
# database name -- no new docker service required).
createdb -h localhost -p 5434 -U market_documents market_documents_app

export APP_DATABASE_URL="postgresql+psycopg://market_documents:market_documents@localhost:5434/market_documents_app"

.venv/bin/python -m market_documents.cli.main publish app-init
```

## Migration commands

The app schema has its own Alembic environment; use `-c alembic_app.ini`
with `script_location` pointed at `migrations_app`:

```bash
.venv/bin/python -m alembic -c alembic_app.ini upgrade head
.venv/bin/python -m alembic -c alembic_app.ini downgrade base
.venv/bin/python -m alembic -c alembic_app.ini current
```

(`market-documents publish app-init` wraps `upgrade head` for convenience.)
Migration order: `app_0001` (publications, application_state, companies,
metric_definitions, metric_label_thresholds) → `app_0002` (reports) →
`app_0003` (passages, report_comparisons) → `app_0004` (language_metrics,
passage_comparisons, passage_language_signals, discovery_items) → `app_0005`
(`app.current_*` views, isolated from table DDL so a future view
redefinition never touches table history).

## Publisher commands

```bash
market-documents publish app-init        --target-database-url "$APP_DATABASE_URL"
market-documents publish build           --target-database-url "$APP_DATABASE_URL" --publication-version "2026-07-27.1"
market-documents publish validate        --target-database-url "$APP_DATABASE_URL" --publication-id <uuid>
market-documents publish promote         --target-database-url "$APP_DATABASE_URL" --publication-id <uuid>
market-documents publish list            --target-database-url "$APP_DATABASE_URL"
market-documents publish show            --target-database-url "$APP_DATABASE_URL" --publication-id <uuid>
market-documents publish audit           --target-database-url "$APP_DATABASE_URL" --publication-id <uuid>
market-documents publish cleanup         --target-database-url "$APP_DATABASE_URL" --keep 2 [--dry-run]
market-documents publish app-init-roles  --target-database-url "$APP_DATABASE_URL" --publisher-password-env APP_PUBLISHER_ROLE_PASSWORD --readonly-password-env APP_READONLY_ROLE_PASSWORD
```

`--target-database-url` may be omitted everywhere; it then falls back to
`APP_DATABASE_URL`. No command ever logs a password.

## Publication lifecycle

1. **`build`** resolves the entire pinned lineage for every accepted
   company/report/comparison (current segmentation run → current feature
   run → the feature run's own pinned `alignment_run_id`, never
   independently re-resolved — see `source_dataset.py`), constructs every
   `app`/`app_internal` row with deterministic IDs, and writes them under a
   **new** `Publication` row. It never touches `application_state` or any
   other publication's rows.
2. **Validation** runs automatically at the end of `build` (and is
   re-runnable standalone via `validate`): company/report/comparison
   referential integrity, chronological-index contiguity, passage-exclusion
   policy, passage-comparison side rules (NEW/REMOVED/matched), discovery
   rank contiguity, quality-label vocabulary. A validation failure marks
   the publication `FAILED` with every failing check recorded in
   `validation_summary` — it never partially activates.
3. A validated publication is `READY`. **`promote`** is the only thing that
   can make it `ACTIVE` — atomically: the prior `ACTIVE` publication (if
   any) becomes `SUPERSEDED`, the new one becomes `ACTIVE`, and
   `application_state.active_publication_id` is updated, all in one
   transaction.
4. **Rollback**: promote an older `READY`/previously-`SUPERSEDED`-but-still
   present publication back to `ACTIVE` the same way — old publications'
   rows are never deleted by `promote`, only by `cleanup`.
5. **`cleanup`** removes `FAILED` publications and old `SUPERSEDED` ones,
   always retaining `ACTIVE` and the most recent `keep` (default 2)
   successful publications. `--dry-run` reports what would be removed
   without deleting anything.

Rebuilding the **same** `publication_version` against unchanged source data
reproduces byte-identical row IDs (see Deterministic IDs below) — a retried
`build` after a transient failure is an in-place upsert, not a duplicate.

## Deterministic IDs

`uuid5(APP_ID_NAMESPACE, f"{publication_version}:{table}:{research_pk}[:discriminator...]")`,
using each entity's existing stable research UUID primary key as the
natural key. A pivoted table (e.g. `passage_language_signals`, one research
row → several app rows, one per category) adds the category/subcategory as
extra discriminator parts. `APP_ID_NAMESPACE` is a frozen constant
(`market_documents.publishing.labels.APP_ID_NAMESPACE`) that must never
change.

## Passage publication policy

Every current-segmentation-run passage is published **except** those
classified `short_fragment_invalid` or `broken_fragment_sequence` by
`structured_content_audit.classify_passage` (recomputed fresh at publish
time — the research `Passage` row has no stored category). This is a
narrower, separate policy from the existing (6-category)
`PRIMARY_NARRATIVE_EXCLUDED_CATEGORIES` used to gate *feature/signal*
eligibility: only these two categories mean "not coherent text at all."
Everything else — list items, table context, captions, financial tables
rendered as prose, etc. — is real document content and is published, with
`primary_narrative_eligible`/`feature_eligible` flags carrying the
analytical nuance. Confirmed against the real corpus: ~22,169 passages
published out of ~22,658 current-generation passages (the milestone's own
pre-publication-exclusion figure) — roughly 490 excluded artifacts.

## Discovery rankings and findings

The 8 discovery types are gated by whichever quality dimension actually
governs their underlying metric — `report_side_signal_quality`/
`report_side_primary_eligible` for pure earlier-vs-later rate deltas (tone,
uncertainty, governance, financial condition), `alignment_change_signal_
quality`/`alignment_change_primary_eligible` for attribution-dependent
introduction/removal measures, and `feature_quality`/`primary_eligible` for
the disclosure-change score and new-disclosure share. Every candidate must
also clear a per-metric materiality epsilon (magnitude ≥ 1× epsilon) to be
eligible at all — a technically-largest-in-its-pool value that's still
immaterial never ranks. Bands/percentiles for magnitude labels are computed
fresh per publication from that publication's own eligible population
(`labels.compute_percentile_bands`), never from a hardcoded constant.

`primary_finding_key`/`secondary_finding_key`/`tertiary_finding_key` per
comparison use the same eligible-candidate list, sorted by descending
magnitude with a fixed candidate-order tie-break; `NULL` for any slot beyond
how many candidates actually survived.

## Review-qualified disclosure-change publication (Milestone 7A.1 follow-up)

The real corpus captured by the initial 7A.1 build had **all 25** current
`FeatureRun`s at `feature_quality = NEEDS_REVIEW` (`primary_eligible =
False`) — an upstream Milestone 3/6 characteristic, not a publishing
defect. The *initial* implementation gated `disclosure_change_label`/
`disclosure_change_percentile` on primary eligibility, which left them
empty everywhere despite `disclosure_change_score` itself always being
present — in direct conflict with the approved UI design (overall
disclosure change shown on company cards, company histories, and
comparison summaries).

This was corrected without recalibrating Milestones 3–5, changing
`FeatureQuality`, or making review-qualified comparisons primary eligible:

- `app.report_comparisons.disclosure_change_score` is now published for
  **every** comparison with a non-null upstream value, regardless of
  `FeatureQuality` tier — **except** when quality is `FAILED` (then the
  score is withheld entirely, matching the `FAILED` → "Unavailable" label)
  or the raw value itself is `None`. See
  `labels.disclosure_change_score_displayed`.
- `disclosure_change_label`/`disclosure_change_percentile` are computed via
  the same percentile-band process as every other metric, but over the
  broader *displayed* population (quality ≠ `FAILED`, score not null) —
  not the primary-eligible-only population. This is the one population
  scoped more broadly than before; every other metric's banding population
  (language signals, `new_rate_words`) is unchanged.
- Four new columns on `app.report_comparisons` make the score's own quality
  explicit and independent of the raw value:
  - `disclosure_change_quality` — raw upstream `FeatureQuality`, verbatim, never recalculated.
  - `disclosure_change_quality_label` — plain-language translation (`GOOD`→"Analysis ready", `USABLE`→"Ready with caution", `NEEDS_REVIEW`→"Review recommended", `FAILED`→"Unavailable" — the same generic vocabulary already used for extraction/similarity/feature quality).
  - `disclosure_change_primary_eligible` — raw `ReportPairFeatures.primary_eligible`, verbatim. **Never** widened; this is the flag that keeps a NEEDS_REVIEW comparison out of feature-quality-gated discovery rankings (`largest_overall_change`, `largest_new_disclosure_share`) and out of `primary_finding_key`/`secondary_finding_key`/`tertiary_finding_key` selection — `findings.py`/`discovery.py` are entirely unchanged by this follow-up.
  - `disclosure_change_warning` — `ReportPairFeatures.warning_reasons`/`exclusion_reasons`, combined, explaining *why* quality is what it is.
- A new `market_documents_app` migration, `app_0006`, adds these four
  columns and re-`CREATE OR REPLACE`s `app.current_report_comparisons` (a
  `SELECT *` view — Postgres expands `*` at `CREATE`/`CREATE OR REPLACE`
  time, so new base-table columns do **not** appear through an existing
  view until it is recreated; this is now a documented, tested pattern any
  future comparable schema change should follow).
- `publication_comparison_audit.csv` gained four fields:
  `disclosure_change_score_available` (was the raw upstream value non-null,
  before any `FAILED`-quality suppression — recovered from a small
  diagnostics dict stashed in `finding_payload` at build time, since the
  persisted `disclosure_change_score` column itself holds the
  post-suppression, *displayed* value), `disclosure_change_score_displayed`,
  `disclosure_change_primary_eligible`, and `discovery_exclusion_reason`
  (a plain-language reason, or `None` if the comparison is primary
  eligible).
- `validate_persisted` gained checks: every comparison has a non-null
  `disclosure_change_quality`; `FAILED` quality implies no displayed score;
  `disclosure_change_primary_eligible` implies `GOOD`/`USABLE` quality; and
  — the key regression guard for requirement 6 — no
  `largest_overall_change`/`largest_new_disclosure_share` discovery item
  ever references a non-primary-eligible comparison.

Report-side and alignment-change language findings (tone, uncertainty, risk
introduction/removal, governance, financial condition) were already
unaffected by the original limitation and remain unaffected by this
follow-up, matching the milestone's own "24/25 report-side, 23/25
alignment-change eligible" figures.

## Full-text search

`app.passages.search_vector` is a `GENERATED ALWAYS ... STORED` `tsvector`
column (heading weight A, passage text weight B), backed by a GIN index —
no application-side trigger or backfill job required; it stays in sync with
`heading`/`text` automatically.

## Database roles

`scripts/sql/app_roles.sql` (idempotent, psql `:'variable'` password
interpolation — passwords are never hardcoded or logged) defines:

- **`app_publisher`** — full DDL/DML on `app` and `app_internal`. Used only
  by the local research pipeline (`market-documents publish ...`), never by
  the future Next.js deployment.
- **`app_readonly`** — `SELECT` on the eight `app.current_*` views only. No
  `USAGE` grant on `app_internal` at all, so it cannot discover
  `application_state`/`publications` exist, let alone query them. Intended
  for the future Next.js server-side database client.

Run via `market-documents publish app-init-roles` (reads passwords from the
named environment variables) after `app-init` has created the views, or
directly: `psql "$APP_DATABASE_URL" -v publisher_pw=... -v readonly_pw=... -f scripts/sql/app_roles.sql`.

**Security note on `app.current_*` views**: Postgres checks view
permissions against the view's *owner*, not the querying role, for an
ordinary (non `SECURITY INVOKER`) view. Since these views are owned by
`app_publisher`, `app_readonly` can successfully `SELECT` from
`app.current_report_comparisons` — which internally joins
`app_internal.application_state` to resolve the active publication —
without ever being granted access to `app_internal` itself. This is the
intended mechanism; `tests/publishing/test_publishing_roles.py` asserts it
holds (verified against both the real corpus database and a dedicated test
database during this milestone's implementation).

## Future Neon / Next.js / semantic-search notes

- **Neon**: `APP_DATABASE_URL` is an ordinary `postgresql://` connection
  string; nothing here depends on Neon-specific branching, pooling, or
  edge-runtime APIs. Point `APP_DATABASE_URL` at a Neon connection string
  and run `publish app-init` / `publish build` / `publish promote` exactly
  as documented above.
- **Next.js**: the future server-side database client should connect as
  `app_readonly` and query only `app.current_*` views — never
  `app.<table>` directly, and never `app_internal`.
- **Semantic search** (Milestone 7B): `app.passages.id` and
  `source_passage_id` are stable across a publication's lifetime, so a
  later `app.passage_embeddings` table (publication_id, passage_id,
  embedding model, model revision, dimensions, vector) can be added without
  redesigning passage identity. Embeddings are deliberately not published
  in 7A.1.

## Milestone 7B.1: passage embeddings and retrieval contexts

Implements the note above. Migration `app_0007` (revises `app_0006`) adds:

- `CREATE EXTENSION IF NOT EXISTS vector` (fails clearly on a provider
  without pgvector, rather than silently skipping vector support).
- `app.passage_embeddings` -- one deduplicated `VECTOR(384)` row per
  published passage (unique on `publication_id, passage_id, embedding_model,
  embedding_model_revision`), HNSW cosine index
  (`ix_app_passage_embeddings_hnsw_cosine`), plus source-lineage columns
  (`source_embedding_id`, `source_embedding_run_id`) and a self-consistency
  `embedding_text_hash`.
- `app.retrieval_contexts` -- one row per valid `(passage, passage
  comparison, report side)` interpretation, plus `REPORT_ONLY` rows for the
  small number of passages with no comparison link at all. Built by a
  single deterministic rule in `publisher.py`: one context per non-null
  `earlier_passage_id`/`later_passage_id` on each `app.passage_comparisons`
  row -- this alone implements every alignment-status side rule (NEW is
  later-side only, REMOVED is earlier-side only, matched statuses get both
  sides, one-sided AMBIGUOUS preserves whichever side exists) without any
  status-specific branching.
- `app.retrieval_context_language_categories` /
  `app.retrieval_context_risk_subcategories` -- normalized category/
  subcategory child tables (mirrors the existing
  `passage_language_signals` normalization choice), populated from
  non-zero published language signals for the same `(passage_comparison_id,
  report_side)` scope.
- Four new `current_*` views (`app.current_passage_embeddings`,
  `app.current_retrieval_contexts`, and the two category views), created
  via their own `RETRIEVAL_CURRENT_VIEWS` tuple in `schema.py` --
  deliberately **not** merged into the existing `CURRENT_VIEWS` tuple that
  `app_0005`/`app_0006` already replay on every upgrade/downgrade, since
  merging them would make a from-scratch `upgrade head` try to create these
  views before `app_0007`'s own tables exist.
- `app_readonly` is granted `SELECT` on the four new views only -- never on
  the raw `app.passage_embeddings`/`app.retrieval_contexts` tables.

### Embedding-coverage policy

The research embedding pipeline skips (never truncates) a passage whose
token count exceeds the model's 512-token limit. On the real corpus this
affects a small fraction of passages (measured: 207 of 22,169, ~0.93%,
concentrated in a few long report sections). Rather than hard-failing
publication over every individual gap, `validate_persisted` requires
**aggregate** embedding coverage to stay at or above `MINIMUM_EMBEDDING_
COVERAGE` (95%, see `publishing/validation.py`) and records every
individual gap in `publication_embedding_missing_audit.csv` for review.

### New publisher build steps

For each current, non-excluded passage: resolve its current research
embedding via the existing `get_current_embedding_run`/segmentation-run
lineage (`source_dataset.py`), verify dimensions match `APP_EMBEDDING_
DIMENSION` (384), compute `embedding_text_hash` and `vector_norm`, and
insert a deterministic `app.passage_embeddings` row. Retrieval contexts and
their category rows are then derived from the already-built `app.passage_
comparisons`/`app.passage_language_signals` rows in the same build pass.

### New validation checks

Embedding-coverage threshold, no-duplicate-vector, dimension/zero-vector
integrity, no-duplicate-context, context-references-published-passage/
embedding/passage-comparison, report-side-matches-passage-comparison-side,
NEW-is-later-side/REMOVED-is-earlier-side, REPORT_ONLY-has-no-comparison-
fields, and retrieval-context categories/quality fields agree with the
published `passage_language_signals`/`report_comparisons` rows they were
derived from. See `publishing/validation.py` for the full list.

### New audit CSVs

`publication_embedding_audit.csv`, `publication_embedding_lineage_audit.csv`,
`publication_embedding_missing_audit.csv`,
`publication_vector_integrity_audit.csv`,
`publication_retrieval_context_audit.csv`,
`publication_retrieval_context_duplicate_audit.csv` -- written by `market-
documents publish audit` alongside the existing 7A.1 audit files.

### New CLI command

`market-documents publish benchmark --publication-id <id>` -- runs the
exact-vs-HNSW retrieval benchmark (`publishing/retrieval_benchmark.py`)
against a publication's embeddings and writes `publication_retrieval_
benchmark.csv`.

### Real-data results (publication `2026-07-29.1`)

21,962 embeddings (99.07% coverage), 36,597 retrieval contexts (4
`REPORT_ONLY`), 0 duplicate vectors/contexts. Benchmark: exact and HNSW
both sub-3ms at this corpus scale; HNSW recall@10 = 1.0 relative to exact
(unfiltered and company-filtered), ~30% lower unfiltered latency. Full
figures in the Milestone 7B.1 final report.

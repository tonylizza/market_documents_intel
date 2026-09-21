"""Raw SQL for the application database's schema-level objects that live
outside SQLAlchemy's table metadata: the two Postgres schemas themselves and
the `app.current_*` views.

Single source of truth, imported by both the bootstrap Alembic migration
(`migrations_app/versions/0001_app_schema_bootstrap.py`,
`0005_app_current_views.py`) and by tests -- view SQL is never duplicated as
a second string anywhere else.

Security note on `app.current_*` views: each view joins
`app_internal.application_state` to resolve which `publication_id` is
currently active. Postgres checks view permissions against the view's
*owner*, not the querying role, for an ordinary (non `SECURITY INVOKER`)
view. As long as these views are created/owned by the publisher role
(`app_publisher`, see `scripts/sql/app_roles.sql`), the read-only
`app_readonly` role can `SELECT` from `app.current_report_comparisons` (and
therefore transitively resolve the active publication) without ever being
granted `USAGE` on `app_internal` itself -- it cannot query
`app_internal.application_state` or `app_internal.publications` directly.
If a future migration recreates a view under a role without `app_internal`
access, or marks it `security_invoker`, the view fails closed (permission
denied) rather than leaking data -- but it will also stop serving the
application, so `tests/publishing/test_publishing_roles.py` asserts the
current, intended behavior in CI.
"""

CREATE_SCHEMAS_SQL = (
    "CREATE SCHEMA IF NOT EXISTS app;",
    "CREATE SCHEMA IF NOT EXISTS app_internal;",
)

# Track 7E.1: created by its own migration (app_0010), not app_0001 --
# `app_corpus` did not exist at bootstrap time and this constant is only
# ever referenced by app_0010 onward. Kept here (not inlined in the
# migration) for the same single-source-of-truth reason as `CREATE_SCHEMAS_
# SQL` above.
CREATE_CORPUS_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS app_corpus;"

_ACTIVE_PUBLICATION_JOIN = """
    JOIN app_internal.application_state s
        ON s.singleton_key = 'active'
    WHERE t.publication_id = s.active_publication_id
"""

CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_companies",
        f"CREATE OR REPLACE VIEW app.current_companies AS "
        f"SELECT t.* FROM app.companies t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_reports",
        f"CREATE OR REPLACE VIEW app.current_reports AS "
        f"SELECT t.* FROM app.reports t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_report_comparisons",
        f"CREATE OR REPLACE VIEW app.current_report_comparisons AS "
        f"SELECT t.* FROM app.report_comparisons t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_language_metrics",
        f"CREATE OR REPLACE VIEW app.current_language_metrics AS "
        f"SELECT t.* FROM app.language_metrics t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_passages",
        f"CREATE OR REPLACE VIEW app.current_passages AS "
        f"SELECT t.* FROM app.passages t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_passage_comparisons",
        f"CREATE OR REPLACE VIEW app.current_passage_comparisons AS "
        f"SELECT t.* FROM app.passage_comparisons t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_passage_language_signals",
        f"CREATE OR REPLACE VIEW app.current_passage_language_signals AS "
        f"SELECT t.* FROM app.passage_language_signals t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_discovery_items",
        f"CREATE OR REPLACE VIEW app.current_discovery_items AS "
        f"SELECT t.* FROM app.discovery_items t {_ACTIVE_PUBLICATION_JOIN};",
    ),
)

DROP_CURRENT_VIEWS_SQL = tuple(
    f"DROP VIEW IF EXISTS app.{name};" for name, _ in reversed(CURRENT_VIEWS)
)

# ---------------------------------------------------------------------------
# Milestone 7B.1: retrieval (vector/context) current views
# ---------------------------------------------------------------------------
#
# Deliberately a SEPARATE tuple from `CURRENT_VIEWS`, not appended to it.
# `app_0005_current_views.py` (upgrade) and its downgrade both iterate over
# the *literal* `CURRENT_VIEWS`/`DROP_CURRENT_VIEWS_SQL` module constants at
# whatever revision is currently running -- if the retrieval views were
# folded into those same tuples, replaying app_0005's upgrade (e.g. via a
# from-scratch `upgrade head` or a downgrade that passes back through
# app_0005) would try to create/drop `app.current_passage_embeddings` /
# `app.current_retrieval_contexts` before their base tables exist (those
# arrive in app_0007), breaking migration replay. Keeping this milestone's
# views in their own tuple, created/dropped only by their own migration,
# avoids ever mutating app_0005's replay behavior.
RETRIEVAL_CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_passage_embeddings",
        "CREATE OR REPLACE VIEW app.current_passage_embeddings AS "
        f"SELECT t.* FROM app.passage_embeddings t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_retrieval_contexts",
        "CREATE OR REPLACE VIEW app.current_retrieval_contexts AS "
        f"SELECT t.* FROM app.retrieval_contexts t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_retrieval_context_language_categories",
        "CREATE OR REPLACE VIEW app.current_retrieval_context_language_categories AS "
        "SELECT t.* FROM app.retrieval_context_language_categories t "
        "JOIN app_internal.application_state s ON s.singleton_key = 'active' "
        "WHERE t.publication_id = s.active_publication_id;",
    ),
    (
        "current_retrieval_context_risk_subcategories",
        "CREATE OR REPLACE VIEW app.current_retrieval_context_risk_subcategories AS "
        "SELECT t.* FROM app.retrieval_context_risk_subcategories t "
        "JOIN app_internal.application_state s ON s.singleton_key = 'active' "
        "WHERE t.publication_id = s.active_publication_id;",
    ),
)

DROP_RETRIEVAL_CURRENT_VIEWS_SQL = tuple(
    f"DROP VIEW IF EXISTS app.{name};" for name, _ in reversed(RETRIEVAL_CURRENT_VIEWS)
)

# pgvector is required only from Milestone 7B.1 onward -- created inside the
# app database, never assumed present. `IF NOT EXISTS` keeps this idempotent
# against a cluster where the research database already enabled it (same
# Postgres instance, different database -- extensions are per-database).
CREATE_VECTOR_EXTENSION_SQL = "CREATE EXTENSION IF NOT EXISTS vector;"

# ---------------------------------------------------------------------------
# Milestone 7B.2: Q&A retrieval-chunk current views
# ---------------------------------------------------------------------------
#
# Same replay-safety reasoning as `RETRIEVAL_CURRENT_VIEWS` above: a
# SEPARATE tuple, created/dropped only by app_0008 (never appended to
# `RETRIEVAL_CURRENT_VIEWS`, which app_0007 already owns the replay of).
QA_CHUNK_CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_qa_chunks",
        "CREATE OR REPLACE VIEW app.current_qa_chunks AS "
        f"SELECT t.* FROM app.qa_chunks t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_qa_chunk_passages",
        "CREATE OR REPLACE VIEW app.current_qa_chunk_passages AS "
        "SELECT t.* FROM app.qa_chunk_passages t "
        "JOIN app_internal.application_state s ON s.singleton_key = 'active' "
        "WHERE t.publication_id = s.active_publication_id;",
    ),
)

DROP_QA_CHUNK_CURRENT_VIEWS_SQL = tuple(
    f"DROP VIEW IF EXISTS app.{name};" for name, _ in reversed(QA_CHUNK_CURRENT_VIEWS)
)

# ---------------------------------------------------------------------------
# Track 7A.3/7A.4: Track 7C.6 cutover-comparison current views
# ---------------------------------------------------------------------------
#
# Same replay-safety reasoning as `RETRIEVAL_CURRENT_VIEWS`/
# `QA_CHUNK_CURRENT_VIEWS` above: a SEPARATE tuple, created/dropped only by
# the migration that introduces `app.narrative_unit_comparisons`/
# `app.structured_table_comparisons`, never appended to an earlier
# milestone's tuple.
CUTOVER_COMPARISON_CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_narrative_unit_comparisons",
        "CREATE OR REPLACE VIEW app.current_narrative_unit_comparisons AS "
        f"SELECT t.* FROM app.narrative_unit_comparisons t {_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_structured_table_comparisons",
        "CREATE OR REPLACE VIEW app.current_structured_table_comparisons AS "
        f"SELECT t.* FROM app.structured_table_comparisons t {_ACTIVE_PUBLICATION_JOIN};",
    ),
)

DROP_CUTOVER_COMPARISON_CURRENT_VIEWS_SQL = tuple(
    f"DROP VIEW IF EXISTS app.{name};" for name, _ in reversed(CUTOVER_COMPARISON_CURRENT_VIEWS)
)

# ---------------------------------------------------------------------------
# Track 7E.1: shared-corpus-aware `current_passages`/`current_passage_
# embeddings` view redefinitions
# ---------------------------------------------------------------------------
#
# These `CREATE OR REPLACE VIEW` statements REDEFINE (never re-create from
# scratch) the two views `app_0005`/`app_0007` already created -- deliberately
# a separate tuple, executed only by app_0010, for the exact replay-safety
# reason documented on `RETRIEVAL_CURRENT_VIEWS` above: `app_0005`'s own
# replay must keep creating the pre-7E.1 `SELECT t.* ...` form (it runs
# before `app_corpus.passages` exists), and only app_0010 -- which runs after
# `app_corpus` is created -- upgrades them to the corpus-aware form. Column
# names, order, and types exactly match what the original `SELECT t.*` form
# produced (verified against the live view's `\d` output), which is required
# for `CREATE OR REPLACE VIEW` to be legal (it may add trailing columns, but
# may never reorder, rename, retype, or remove an existing one).
#
# `current_passages.text`/`.search_vector` now come from `app_corpus.
# passages` via `COALESCE` against the per-publication column: a
# publication built before app_0010 still has its own populated `text`
# (COALESCE prefers it, so old publications need no backfill to keep
# working); a publication built from app_0010 onward always has `text IS
# NULL` on its own row and falls through to the corpus join. Benchmarked
# locally against the semantic-search hot path (see docs/7e1-publication-
# storage-lifecycle-hardening.md section 9): this LEFT JOIN sits after the
# view is inlined into the caller's query, on a small already-`LIMIT`-ed
# candidate set exactly like the existing `current_passages` join in
# `postgres-semantic-retrieval-repository.ts` -- not the kind of
# aggregate/correlated-subquery join that file's own comments warn defeats
# the planner.
#
# `current_passage_embeddings` is redefined even more fundamentally: from
# app_0010 onward the publisher never writes to `app.passage_embeddings` at
# all (see `PassageEmbedding`'s docstring in `models.py`), so this view now
# reads directly from the shared `app_corpus.passage_embeddings` table,
# joined to `app.current_passages` (already publication-filtered) on
# `source_passage_id`. The `id`/`created_at` columns are the retrieval-
# context-facing embedding row's own id/timestamp (from `app_corpus`, not a
# per-publication row) -- `RetrievalContext.passage_embedding_id` for any
# publication built from app_0010 onward is exactly this id (see that
# column's docstring in `models.py`). A publication built before app_0010
# still resolves correctly here too: its own `app.passage_embeddings` rows
# were backfilled into `app_corpus.passage_embeddings` by app_0010's
# migration with the SAME deterministic id `labels.derive_corpus_id` would
# produce, so the join finds them under the corpus id, not the legacy
# per-publication id -- `RetrievalContext.passage_embedding_id` on those
# older rows still points at the legacy id, which is why validation checks
# both id spaces (see `publishing/validation.py`).
CORPUS_CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_passages",
        "CREATE OR REPLACE VIEW app.current_passages AS "
        "SELECT t.publication_id, t.source_passage_id, t.company_id, t.report_id, "
        "t.report_period_end, t.passage_index, t.first_page_number, t.last_page_number, "
        "t.heading, t.passage_type, "
        "COALESCE(t.text, cp.text) AS text, "
        "t.word_count, t.structured_content_category, t.primary_narrative_eligible, "
        "t.feature_eligible, "
        "COALESCE(t.search_vector, cp.search_vector) AS search_vector, "
        "t.id, t.created_at "
        "FROM app.passages t "
        "LEFT JOIN app_corpus.passages cp ON cp.source_passage_id = t.source_passage_id "
        f"{_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_passage_embeddings",
        "CREATE OR REPLACE VIEW app.current_passage_embeddings AS "
        "SELECT p.publication_id, p.id AS passage_id, "
        "ce.source_embedding_id, ce.source_embedding_run_id, ce.embedding_model, "
        "ce.embedding_model_revision, ce.dimensions, ce.embedding_text_hash, "
        "ce.embedding, ce.vector_norm, ce.id, ce.created_at "
        "FROM app_corpus.passage_embeddings ce "
        "JOIN app.current_passages p ON p.source_passage_id = ce.source_passage_id;",
    ),
)

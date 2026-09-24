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
CREATE_ARTIFACTS_SCHEMA_SQL = "CREATE SCHEMA IF NOT EXISTS app_artifacts;"

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

# ---------------------------------------------------------------------------
# Track 7F.7a.5: versioned shared artifacts (`app_artifacts` schema)
# ---------------------------------------------------------------------------
#
# Same COALESCE-against-a-LEFT-JOIN template as `CORPUS_CURRENT_VIEWS` above,
# extended to the four artifact families whose per-row content is large
# enough to matter (passage_comparisons, retrieval_contexts,
# passage_language_signals, qa_chunks -- see docs/versioned-shared-artifacts-
# implementation-7f7a5.md section on scope). `t.<col>` is always NULL for a
# publication built by the publisher from this migration onward (it stops
# populating these columns; see `publisher.py`), and always the pre-existing
# populated value for a publication built before this migration -- exactly
# the same backward-compatibility shape `CORPUS_CURRENT_VIEWS` established
# for `current_passages`. `retrieval_context_language_categories`,
# `retrieval_context_risk_subcategories`, and `qa_chunk_passages` are
# deliberately NOT redefined here: their entire content is one small
# column (a category/subcategory string, or an integer ordinal) that is
# already minimal on the thin per-publication row, so there is no
# meaningful byte saving to chase by moving it into `app_artifacts` and
# rewriting these views -- their `app_artifacts.*` counterparts exist (see
# `models.py`) purely to prove the same existence-check/reuse/GC mechanism
# at that granularity, addressed via their own `*_artifact_id` link column,
# never through a COALESCE view.
ARTIFACT_CURRENT_VIEWS: tuple[tuple[str, str], ...] = (
    (
        "current_passage_comparisons",
        "CREATE OR REPLACE VIEW app.current_passage_comparisons AS "
        "SELECT t.publication_id, t.source_alignment_id, t.report_comparison_id, "
        "t.earlier_passage_id, t.later_passage_id, "
        "COALESCE(t.alignment_status, art.alignment_status) AS alignment_status, "
        "COALESCE(t.alignment_type, art.alignment_type) AS alignment_type, "
        "COALESCE(t.confidence, art.confidence) AS confidence, "
        "COALESCE(t.confidence_label, art.confidence_label) AS confidence_label, "
        "COALESCE(t.semantic_similarity, art.semantic_similarity) AS semantic_similarity, "
        "COALESCE(t.lexical_similarity, art.lexical_similarity) AS lexical_similarity, "
        "COALESCE(t.heading_similarity, art.heading_similarity) AS heading_similarity, "
        "COALESCE(t.content_score, art.content_score) AS content_score, "
        "COALESCE(t.position_difference, art.position_difference) AS position_difference, "
        "COALESCE(t.collision_flag, art.collision_flag) AS collision_flag, "
        "COALESCE(t.split_merge_flag, art.split_merge_flag) AS split_merge_flag, "
        "COALESCE(t.primary_alignment, art.primary_alignment) AS primary_alignment, "
        "COALESCE(t.review_reason, art.review_reason) AS review_reason, "
        "t.id, t.created_at, t.alignment_artifact_id "
        "FROM app.passage_comparisons t "
        "LEFT JOIN app_artifacts.passage_comparisons art ON art.id = t.alignment_artifact_id "
        f"{_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_retrieval_contexts",
        "CREATE OR REPLACE VIEW app.current_retrieval_contexts AS "
        "SELECT t.publication_id, t.passage_id, t.passage_embedding_id, t.passage_comparison_id, "
        "t.report_comparison_id, t.report_id, t.company_id, t.context_type, t.report_side, "
        "COALESCE(t.alignment_status, art.alignment_status) AS alignment_status, "
        "COALESCE(t.alignment_type, art.alignment_type) AS alignment_type, "
        "COALESCE(t.confidence, art.confidence) AS confidence, "
        "t.report_period_end, t.earlier_period_end, t.later_period_end, "
        "COALESCE(t.heading, art.heading) AS heading, "
        "COALESCE(t.passage_type, art.passage_type) AS passage_type, "
        "COALESCE(t.primary_narrative_eligible, art.primary_narrative_eligible) AS primary_narrative_eligible, "
        "COALESCE(t.feature_eligible, art.feature_eligible) AS feature_eligible, "
        "COALESCE(t.structured_content_category, art.structured_content_category) AS structured_content_category, "
        "t.report_side_quality, t.alignment_change_quality, "
        "COALESCE(t.collision_flag, art.collision_flag) AS collision_flag, "
        "COALESCE(t.split_merge_flag, art.split_merge_flag) AS split_merge_flag, "
        "t.irregular_gap_flag, t.id, t.created_at, t.alignment_artifact_id "
        "FROM app.retrieval_contexts t "
        "LEFT JOIN app_artifacts.retrieval_contexts art ON art.id = t.alignment_artifact_id "
        f"{_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_passage_language_signals",
        "CREATE OR REPLACE VIEW app.current_passage_language_signals AS "
        "SELECT t.publication_id, t.passage_id, t.passage_comparison_id, t.report_comparison_id, "
        "t.report_side, t.category, t.subcategory, "
        "COALESCE(t.raw_count, art.raw_count) AS raw_count, "
        "COALESCE(t.negated_count, art.negated_count) AS negated_count, "
        "COALESCE(t.adjusted_count, art.adjusted_count) AS adjusted_count, "
        "COALESCE(t.rate_per_1000, art.rate_per_1000) AS rate_per_1000, "
        "COALESCE(t.is_introduced, art.is_introduced) AS is_introduced, "
        "COALESCE(t.is_removed, art.is_removed) AS is_removed, "
        "COALESCE(t.is_retained, art.is_retained) AS is_retained, "
        "t.id, t.created_at, t.language_signal_artifact_id "
        "FROM app.passage_language_signals t "
        "LEFT JOIN app_artifacts.passage_language_signals art ON art.id = t.language_signal_artifact_id "
        f"{_ACTIVE_PUBLICATION_JOIN};",
    ),
    (
        "current_qa_chunks",
        "CREATE OR REPLACE VIEW app.current_qa_chunks AS "
        "SELECT t.publication_id, t.report_id, t.company_id, t.chunk_index, "
        "COALESCE(t.text, art.text) AS text, "
        "COALESCE(t.section_heading, art.section_heading) AS section_heading, "
        "COALESCE(t.page_start, art.page_start) AS page_start, "
        "COALESCE(t.page_end, art.page_end) AS page_end, "
        "COALESCE(t.token_count, art.token_count) AS token_count, "
        "COALESCE(t.truncation_policy, art.truncation_policy) AS truncation_policy, "
        "COALESCE(t.embedding_model, art.embedding_model) AS embedding_model, "
        "COALESCE(t.embedding_model_revision, art.embedding_model_revision) AS embedding_model_revision, "
        "COALESCE(t.dimensions, art.dimensions) AS dimensions, "
        "COALESCE(t.embedding_text_hash, art.embedding_text_hash) AS embedding_text_hash, "
        "COALESCE(t.embedding, art.embedding) AS embedding, "
        "COALESCE(t.vector_norm, art.vector_norm) AS vector_norm, "
        "COALESCE(t.search_vector, art.search_vector) AS search_vector, "
        "t.id, t.created_at, t.qa_chunking_artifact_id "
        "FROM app.qa_chunks t "
        "LEFT JOIN app_artifacts.qa_chunks art ON art.id = t.qa_chunking_artifact_id "
        f"{_ACTIVE_PUBLICATION_JOIN};",
    ),
)

DROP_ARTIFACT_CURRENT_VIEWS_SQL = tuple(
    f"DROP VIEW IF EXISTS app.{name};" for name, _ in reversed(ARTIFACT_CURRENT_VIEWS)
)

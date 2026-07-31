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

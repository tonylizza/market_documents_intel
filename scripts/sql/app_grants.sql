-- Milestone 7A.1 application-database grants, split out of app_roles.sql
-- (Track 7E.2b) so they can be re-applied on their own, with no password
-- variables and no role creation/rotation.
--
-- This file exists because grants drift out of sync with the schema on a
-- predictable cadence: every time a migration adds a new `app.current_*`
-- view (or another table `app_readonly` needs), this file gains a new
-- GRANT statement, but any database whose roles were provisioned *before*
-- that statement was added silently keeps the old, narrower grant set --
-- nothing about a normal `alembic upgrade head` re-applies it. That drift
-- previously required a manual re-run of the whole role-creation script
-- (README/7D.2c, 7E.2, 7E.2b's own reproduction) each time; requires only
-- `app_publisher`/`app_readonly` to already exist (via app_roles.sql /
-- `market-documents publish app-init-roles`), and NEVER creates a role or
-- touches a password -- safe to run as a routine idempotent step (e.g.
-- every frontend test run) with no cluster-wide password side effect.
--
-- Run directly: `psql <target-database-url> -v ON_ERROR_STOP=1 -f
-- scripts/sql/app_grants.sql`. Also included by app_roles.sql itself, so
-- `market-documents publish app-init-roles` continues to apply both role
-- creation/passwords and grants in one call.

GRANT USAGE, CREATE ON SCHEMA app, app_internal TO app_publisher;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA app, app_internal TO app_publisher;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA app, app_internal TO app_publisher;
ALTER DEFAULT PRIVILEGES IN SCHEMA app GRANT ALL ON TABLES TO app_publisher;
ALTER DEFAULT PRIVILEGES IN SCHEMA app_internal GRANT ALL ON TABLES TO app_publisher;

-- app_readonly gets USAGE on `app` only -- deliberately never granted any
-- privilege on `app_internal`, so it cannot even discover
-- `application_state`/`publications` exist. It reads the active publication
-- indirectly, through the `app.current_*` views, which are owned by
-- app_publisher: Postgres checks view permissions against the view owner
-- for an ordinary (non SECURITY INVOKER) view, so app_readonly can select
-- from app.current_report_comparisons without ever touching app_internal
-- directly. See `market_documents.publishing.schema` module docstring.
GRANT USAGE ON SCHEMA app TO app_readonly;
GRANT SELECT ON
    app.current_companies,
    app.current_reports,
    app.current_report_comparisons,
    app.current_language_metrics,
    app.current_passages,
    app.current_passage_comparisons,
    app.current_passage_language_signals,
    app.current_discovery_items
TO app_readonly;

-- Milestone 7B.1: comparison-aware semantic retrieval. app_readonly gets
-- SELECT on the current vector/context views only -- never on the raw
-- app.passage_embeddings/app.retrieval_contexts tables (a raw grant would
-- let a compromised or buggy frontend query across every historical
-- publication's vectors, not just the active one).
GRANT SELECT ON
    app.current_passage_embeddings,
    app.current_retrieval_contexts,
    app.current_retrieval_context_language_categories,
    app.current_retrieval_context_risk_subcategories
TO app_readonly;

-- Milestone 7B.2: standard-RAG Q&A retrieval chunks. Same discipline as the
-- 7B.1 grant above -- app_readonly gets SELECT on the current-view wrapper
-- only, never on raw app.qa_chunks/app.qa_chunk_passages (which would leak
-- every historical publication's chunks/vectors, not just the active one).
-- The disposable qa_experiment schema (7B.1d research spike) gets no grant
-- at all -- app_readonly has zero access to it, by design.
GRANT SELECT ON
    app.current_qa_chunks,
    app.current_qa_chunk_passages
TO app_readonly;

-- Milestone 7A.2: metric_definitions/metric_label_thresholds have no
-- current_* view wrapper (7A.1 only defined the eight views above), but the
-- application needs their display metadata (name/unit/description,
-- threshold bands) for the Methodology page. This is a plain GRANT, not a
-- schema change -- both tables remain publication-scoped, so any consumer
-- must filter by the active publication_id itself (resolved from an
-- already-granted current_* view, e.g. `SELECT publication_id FROM
-- app.current_companies LIMIT 1`) rather than reading across every
-- historical publication.
GRANT SELECT ON app.metric_definitions, app.metric_label_thresholds TO app_readonly;

-- Track 7A.3/7A.4: Track 7C.6 cutover comparison rows (narrative
-- semantic-unit / structured-table comparisons), scoped to the active
-- publication only, same current-view-wrapper discipline as every other
-- grant above.
GRANT SELECT ON
    app.current_narrative_unit_comparisons,
    app.current_structured_table_comparisons
TO app_readonly;

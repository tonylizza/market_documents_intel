-- Milestone 7A.1 application-database roles.
--
-- Run via `market-documents publish app-init-roles` (which invokes
-- `psql <target-database-url> -v publisher_pw=... -v readonly_pw=... -f
-- scripts/sql/app_roles.sql`), or directly with psql. Passwords are always
-- supplied as psql variables -- never hardcoded here and never logged.
--
-- app_publisher: migrates and writes app/app_internal. Used only by the
-- local research pipeline (never by Vercel/Next.js).
-- app_readonly: SELECT on app.current_* views only. Cannot see
-- app_internal at all (no USAGE grant on that schema), cannot insert,
-- update, delete, alter, or access research tables. Intended for the
-- future Next.js server-side database client.
--
-- Idempotent: safe to re-run against an existing database.

-- psql does not interpolate `:'variable'` tokens inside a dollar-quoted
-- (`$$ ... $$`) plpgsql block -- only in ordinary top-level SQL text. Role
-- creation (idempotent, no password) therefore happens inside the DO
-- block; the password itself is always set by a plain top-level ALTER ROLE
-- below, every run, so a re-run also rotates the password to whatever was
-- just supplied.
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_publisher') THEN
        CREATE ROLE app_publisher WITH LOGIN;
    END IF;

    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_readonly') THEN
        CREATE ROLE app_readonly WITH LOGIN;
    END IF;
END
$$;

ALTER ROLE app_publisher WITH PASSWORD :'publisher_pw';
ALTER ROLE app_readonly WITH PASSWORD :'readonly_pw';

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

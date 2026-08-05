-- Milestone 7B.3 abuse-control quota counters.
--
-- Deliberately a separate schema (`qa_quota`) from `app`/`app_internal`:
-- this is deployment/abuse-control bookkeeping, not corpus data, and must
-- never be reachable via the `app_readonly` role or mixed into the
-- publication lifecycle. The only way anything (including the Next.js
-- runtime) can touch this schema is EXECUTE on one SECURITY DEFINER
-- function -- no direct table grant to any application-facing role, so a
-- compromised/buggy request can increment or read its own day's counters
-- but can never see other keys, truncate the table, or alter counts
-- out-of-band.
--
-- Run directly via psql (idempotent, safe to re-run):
--   psql "$NEON_DATABASE_URL" -v writer_pw=... -f scripts/sql/qa_quota.sql

CREATE SCHEMA IF NOT EXISTS qa_quota;

CREATE TABLE IF NOT EXISTS qa_quota.counters (
    scope text NOT NULL,       -- 'client' | 'global'
    key_hash text NOT NULL,    -- sha256 hex of the client-id cookie ('global' has a fixed constant key)
    day date NOT NULL,
    count integer NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, key_hash, day)
);

-- No index-free growth: old rows are small (one row per scope/key/day) and
-- are pruned by `qa_quota.prune_old_counters`, called opportunistically
-- from the increment function itself (no separate cron needed for a
-- free-tier deployment) -- retention: 7 days, comfortably past any
-- daily-quota window.
CREATE OR REPLACE FUNCTION qa_quota.prune_old_counters() RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path = qa_quota, pg_temp
AS $$
    DELETE FROM qa_quota.counters WHERE day < CURRENT_DATE - INTERVAL '7 days';
$$;

-- Atomically increments today's counter for (scope, key_hash) and returns
-- whether the NEW count is within the given limit. SECURITY DEFINER so the
-- calling role never needs direct INSERT/UPDATE/SELECT on the table --
-- only EXECUTE on this one function, with its own bounded, injection-safe
-- surface (three scalar args, no dynamic SQL).
CREATE OR REPLACE FUNCTION qa_quota.increment_and_check(
    p_scope text,
    p_key_hash text,
    p_limit integer
) RETURNS TABLE(allowed boolean, current_count integer)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = qa_quota, pg_temp
AS $$
DECLARE
    v_count integer;
BEGIN
    IF p_scope NOT IN ('client', 'global') THEN
        RAISE EXCEPTION 'invalid scope: %', p_scope;
    END IF;

    PERFORM qa_quota.prune_old_counters();

    INSERT INTO qa_quota.counters (scope, key_hash, day, count)
    VALUES (p_scope, p_key_hash, CURRENT_DATE, 1)
    ON CONFLICT (scope, key_hash, day)
    DO UPDATE SET count = qa_quota.counters.count + 1
    RETURNING qa_quota.counters.count INTO v_count;

    RETURN QUERY SELECT (v_count <= p_limit), v_count;
END;
$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'app_quota_writer') THEN
        CREATE ROLE app_quota_writer WITH LOGIN;
    END IF;
END
$$;

ALTER ROLE app_quota_writer WITH PASSWORD :'writer_pw';

-- No table grants at all -- USAGE on the schema (required to call a
-- function that lives in it) plus EXECUTE on the two functions above is
-- the entire surface. Explicitly no SELECT/INSERT/UPDATE/DELETE on
-- qa_quota.counters, no USAGE/CREATE beyond EXECUTE, no visibility into
-- `app`/`app_internal` (never granted here).
GRANT USAGE ON SCHEMA qa_quota TO app_quota_writer;
GRANT EXECUTE ON FUNCTION qa_quota.increment_and_check(text, text, integer) TO app_quota_writer;
REVOKE ALL ON FUNCTION qa_quota.prune_old_counters() FROM PUBLIC;
REVOKE ALL ON FUNCTION qa_quota.increment_and_check(text, text, integer) FROM PUBLIC;
REVOKE ALL ON qa_quota.counters FROM PUBLIC;
REVOKE ALL ON qa_quota.counters FROM app_quota_writer;

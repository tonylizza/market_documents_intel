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
--
-- Track 7E.2b: the grants themselves (which change every time a migration
-- adds a new `app.current_*` view or another table `app_readonly` needs)
-- live in the separate, password-free, no-role-creation `app_grants.sql`,
-- included below via `\ir` (resolves relative to this script's own
-- location, not the caller's working directory). That file is also safe
-- to run completely on its own -- see its own header -- which is what
-- lets the frontend test
-- bootstrap keep `app_readonly`'s grants current without ever touching a
-- role's password (the risk this split exists to remove; `app_readonly`'s
-- password is a single cluster-wide value shared by every local database
-- using this role, per docs/frontend.md).

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

\ir app_grants.sql

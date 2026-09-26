-- Atlas initial schema.
--
-- Tenant isolation: every tenant table carries org_id and has row-level
-- security. The API and worker run as role atlas_app, which is subject to RLS
-- and sees only rows whose org_id equals the transaction setting app.org_id.
-- With no org set, atlas_app sees nothing.
--
-- Tables are owned by the migration role. A few SECURITY DEFINER functions,
-- owned by that role, do the narrow cross-tenant work (sign-in, claiming a
-- job, expiring files) and nothing else.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atlas_app') THEN
        CREATE ROLE atlas_app NOLOGIN NOBYPASSRLS;
    END IF;
END
$$;

-- The migration role must be able to SET ROLE atlas_app for local use and tests.
GRANT atlas_app TO CURRENT_USER;

CREATE OR REPLACE FUNCTION current_org() RETURNS uuid
    LANGUAGE sql STABLE
    AS $$ SELECT NULLIF(current_setting('app.org_id', true), '')::uuid $$;

-- ---------------------------------------------------------------- identity

CREATE TABLE organizations (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_org_id  text NOT NULL UNIQUE,
    name          text NOT NULL,
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id             uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    clerk_user_id  text NOT NULL UNIQUE,
    email          text,
    name           text,
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE memberships (
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    user_id     uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role        text NOT NULL CHECK (role IN ('owner', 'admin', 'member')),
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, user_id)
);

-- ---------------------------------------------------------------- datasets

CREATE TABLE datasets (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name            text NOT NULL,
    status          text NOT NULL CHECK (status IN ('parsing', 'ready', 'blocked', 'failed')),
    created_by      uuid REFERENCES users(id) ON DELETE SET NULL,
    file_format     text CHECK (file_format IN ('csv', 'xlsx', 'json')),
    sheet_name      text,
    sheets          jsonb NOT NULL DEFAULT '[]',
    columns         jsonb NOT NULL DEFAULT '[]',
    mapping         jsonb NOT NULL DEFAULT '{}',
    report          jsonb,
    rows_read       integer,
    error_code      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX datasets_org_created ON datasets (org_id, created_at DESC);

CREATE TABLE dataset_files (
    id                 uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id             uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id         uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    object_key         text NOT NULL UNIQUE,
    original_filename  text NOT NULL,
    size_bytes         bigint NOT NULL,
    sha256             text NOT NULL,
    uploaded_at        timestamptz NOT NULL DEFAULT now(),
    expires_at         timestamptz NOT NULL,
    deleted_at         timestamptz
);
CREATE INDEX dataset_files_expiry ON dataset_files (expires_at) WHERE deleted_at IS NULL;

-- One row per task, exactly as read. Normalized fields arrive in Phase 4 as
-- separate columns; `original` is never modified.
CREATE TABLE tasks (
    id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id            uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id        uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    row_number        integer NOT NULL,
    original          jsonb NOT NULL,
    malformed_reason  text,
    UNIQUE (dataset_id, row_number)
);

-- ---------------------------------------------------------------- jobs

CREATE TABLE jobs (
    id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id          uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    kind            text NOT NULL,
    payload         jsonb NOT NULL DEFAULT '{}',
    status          text NOT NULL DEFAULT 'queued' CHECK (status IN ('queued', 'running', 'done', 'failed')),
    attempts        integer NOT NULL DEFAULT 0,
    max_attempts    integer NOT NULL DEFAULT 3,
    run_after       timestamptz NOT NULL DEFAULT now(),
    locked_by       text,
    locked_at       timestamptz,
    last_error      text,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX jobs_ready ON jobs (run_after) WHERE status = 'queued';

-- ---------------------------------------------------------------- audit

-- IDs and counts only. Never task content, never filenames.
CREATE TABLE audit_events (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id         uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    actor_user_id  uuid REFERENCES users(id) ON DELETE SET NULL,
    action         text NOT NULL,
    target_type    text,
    target_id      text,
    meta           jsonb NOT NULL DEFAULT '{}',
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX audit_events_org_created ON audit_events (org_id, created_at DESC);

-- ---------------------------------------------------------------- RLS

ALTER TABLE organizations  ENABLE ROW LEVEL SECURITY;
ALTER TABLE users          ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships    ENABLE ROW LEVEL SECURITY;
ALTER TABLE datasets       ENABLE ROW LEVEL SECURITY;
ALTER TABLE dataset_files  ENABLE ROW LEVEL SECURITY;
ALTER TABLE tasks          ENABLE ROW LEVEL SECURITY;
ALTER TABLE jobs           ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events   ENABLE ROW LEVEL SECURITY;

CREATE POLICY org_self ON organizations TO atlas_app
    USING (id = current_org());

CREATE POLICY org_members ON users TO atlas_app
    USING (id IN (SELECT user_id FROM memberships WHERE org_id = current_org()));

CREATE POLICY tenant ON memberships   TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON datasets      TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON dataset_files TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON tasks         TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON jobs          TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON audit_events  TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());

GRANT SELECT ON organizations TO atlas_app;
GRANT SELECT ON users, memberships TO atlas_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON datasets, dataset_files, tasks, jobs TO atlas_app;
GRANT SELECT, INSERT ON audit_events TO atlas_app;

-- ---------------------------------------------------------------- narrow cross-tenant functions

-- Called at sign-in, before any org is known: creates or updates the org,
-- the user and the membership, and returns their ids.
CREATE OR REPLACE FUNCTION ensure_identity(
    p_clerk_org_id text, p_org_name text,
    p_clerk_user_id text, p_email text, p_name text, p_role text
) RETURNS TABLE (org_id uuid, user_id uuid, role text)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
#variable_conflict use_column
DECLARE
    v_org uuid;
    v_user uuid;
    v_role text;
BEGIN
    IF p_role NOT IN ('owner', 'admin', 'member') THEN
        RAISE EXCEPTION 'invalid role';
    END IF;

    INSERT INTO organizations (clerk_org_id, name) VALUES (p_clerk_org_id, p_org_name)
    ON CONFLICT (clerk_org_id) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO v_org;

    INSERT INTO users (clerk_user_id, email, name) VALUES (p_clerk_user_id, p_email, p_name)
    ON CONFLICT (clerk_user_id) DO UPDATE
        SET email = COALESCE(EXCLUDED.email, users.email),
            name  = COALESCE(EXCLUDED.name, users.name)
    RETURNING id INTO v_user;

    INSERT INTO memberships (org_id, user_id, role) VALUES (v_org, v_user, p_role)
    ON CONFLICT (org_id, user_id) DO UPDATE SET role = EXCLUDED.role
    RETURNING memberships.role INTO v_role;

    RETURN QUERY SELECT v_org, v_user, v_role;
END
$$;

-- Claims the next runnable job for a worker. Returns at most one row.
CREATE OR REPLACE FUNCTION claim_job(p_worker text)
    RETURNS TABLE (id bigint, org_id uuid, kind text, payload jsonb, attempts integer, max_attempts integer)
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
#variable_conflict use_column
BEGIN
    RETURN QUERY
    UPDATE jobs j
       SET status = 'running', attempts = j.attempts + 1, locked_by = p_worker, locked_at = now(), updated_at = now()
     WHERE j.id = (
           SELECT q.id FROM jobs q
            WHERE q.status = 'queued' AND q.run_after <= now()
            ORDER BY q.run_after, q.id
            LIMIT 1
            FOR UPDATE SKIP LOCKED)
    RETURNING j.id, j.org_id, j.kind, j.payload, j.attempts, j.max_attempts;
END
$$;

-- Requeues jobs whose worker died mid-run (no progress for p_stale_seconds).
CREATE OR REPLACE FUNCTION requeue_stale_jobs(p_stale_seconds integer)
    RETURNS integer
    LANGUAGE plpgsql SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
DECLARE n integer;
BEGIN
    UPDATE jobs SET status = 'queued', locked_by = NULL, locked_at = NULL, updated_at = now()
     WHERE status = 'running' AND locked_at < now() - make_interval(secs => p_stale_seconds);
    GET DIAGNOSTICS n = ROW_COUNT;
    RETURN n;
END
$$;

-- Lists uploaded files past their retention date, across tenants.
CREATE OR REPLACE FUNCTION files_due_for_expiry(p_limit integer)
    RETURNS TABLE (id uuid, org_id uuid, object_key text)
    LANGUAGE sql SECURITY DEFINER SET search_path = public, pg_temp
    AS $$
    SELECT f.id, f.org_id, f.object_key FROM dataset_files f
     WHERE f.deleted_at IS NULL AND f.expires_at <= now()
     ORDER BY f.expires_at
     LIMIT p_limit
$$;

REVOKE ALL ON FUNCTION ensure_identity(text, text, text, text, text, text) FROM PUBLIC;
REVOKE ALL ON FUNCTION claim_job(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION requeue_stale_jobs(integer) FROM PUBLIC;
REVOKE ALL ON FUNCTION files_due_for_expiry(integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION ensure_identity(text, text, text, text, text, text) TO atlas_app;
GRANT EXECUTE ON FUNCTION claim_job(text) TO atlas_app;
GRANT EXECUTE ON FUNCTION requeue_stale_jobs(integer) TO atlas_app;
GRANT EXECUTE ON FUNCTION files_due_for_expiry(integer) TO atlas_app;
GRANT EXECUTE ON FUNCTION current_org() TO atlas_app;

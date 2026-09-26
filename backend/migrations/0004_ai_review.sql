-- Phase 4, milestone 3: AI review of pairs the rules can't decide.
--
-- workspace_settings holds the per-workspace switch for AI review (on unless
-- a workspace turns it off). ai_cache remembers each answer so re-running an
-- analysis never pays twice; it is per workspace, never shared, and keyed by
-- a hash of the fields sent, the model and the prompt version.

CREATE TABLE workspace_settings (
    org_id      uuid PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
    ai_review   boolean NOT NULL DEFAULT true,
    updated_by  uuid REFERENCES users(id) ON DELETE SET NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ai_cache (
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    key         text NOT NULL,
    verdict     text NOT NULL CHECK (verdict IN ('same', 'different', 'unsure')),
    reason      text NOT NULL,
    model       text NOT NULL,
    created_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (org_id, key)
);

ALTER TABLE workspace_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE ai_cache           ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant ON workspace_settings TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON ai_cache           TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());

GRANT SELECT, INSERT, UPDATE ON workspace_settings TO atlas_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ai_cache TO atlas_app;

-- Phase 4, milestone 2: duplicate groups, look-alikes and pairs to review.
--
-- Results are rebuilt from scratch on every analysis run and deleted with
-- their dataset. Every table carries org_id and the same tenant policy as the
-- rest of the schema, so one company can never read another's results.

ALTER TABLE datasets DROP CONSTRAINT datasets_status_check;
ALTER TABLE datasets ADD CONSTRAINT datasets_status_check
    CHECK (status IN ('parsing', 'ready', 'blocked', 'failed', 'analysing', 'analysed'));

-- Progress while analysing; the headline summary afterwards.
ALTER TABLE datasets ADD COLUMN analysis jsonb;

CREATE TABLE match_groups (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id               uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id           uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    label                text NOT NULL,                  -- "G-0001", shown to people and in exports
    confidence           text NOT NULL CHECK (confidence IN ('high', 'medium')),
    master_row           integer NOT NULL,
    reasons              jsonb NOT NULL DEFAULT '[]',
    name_standard        text,
    stock_total          numeric,                        -- milestone 4
    stock_on_duplicates  numeric,
    value_on_duplicates  numeric,
    cost_low             numeric,
    cost_high            numeric,
    UNIQUE (dataset_id, label)
);

CREATE TABLE match_members (
    group_id    uuid NOT NULL REFERENCES match_groups(id) ON DELETE CASCADE,
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id  uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    row_number  integer NOT NULL,
    role        text NOT NULL CHECK (role IN ('master', 'duplicate')),
    PRIMARY KEY (group_id, row_number)
);
CREATE INDEX match_members_dataset ON match_members (dataset_id, row_number);

-- Look-alikes (kept apart on purpose) and pairs Atlas couldn't decide.
CREATE TABLE match_pairs (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id  uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    kind        text NOT NULL CHECK (kind IN ('lookalike', 'review')),
    row_a       integer NOT NULL,
    row_b       integer NOT NULL,
    reason_code text NOT NULL,
    detail      text NOT NULL,
    score       real NOT NULL,
    source      text NOT NULL CHECK (source IN ('rule', 'text', 'ai'))
);
CREATE INDEX match_pairs_dataset ON match_pairs (dataset_id, kind, score DESC);

ALTER TABLE match_groups  ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE match_pairs   ENABLE ROW LEVEL SECURITY;

CREATE POLICY tenant ON match_groups  TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON match_members TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
CREATE POLICY tenant ON match_pairs   TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());

GRANT SELECT, INSERT, UPDATE, DELETE ON match_groups, match_members, match_pairs TO atlas_app;

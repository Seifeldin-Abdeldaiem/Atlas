-- Phase 4, milestone 5: people review the results.
--
-- Every decision is recorded, applied to the stored results straight away and
-- re-applied whenever the analysis runs again, so a re-run never undoes a
-- person's work. Decisions refer to rows by row number and are deleted when
-- the file is read again (a different sheet means different rows).

ALTER TABLE match_groups DROP CONSTRAINT match_groups_confidence_check;
ALTER TABLE match_groups ADD CONSTRAINT match_groups_confidence_check CHECK (confidence IN ('high', 'medium', 'reviewed'));

ALTER TABLE match_pairs DROP CONSTRAINT match_pairs_source_check;
ALTER TABLE match_pairs ADD CONSTRAINT match_pairs_source_check CHECK (source IN ('rule', 'text', 'ai', 'review'));

CREATE TABLE review_decisions (
    id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    org_id      uuid NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    dataset_id  uuid NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    -- approve: the group is right. reject: these rows are not duplicates.
    -- set_master: keep this row. remove_row: this row doesn't belong with the others.
    -- same / different: a person settled a pair.
    action      text NOT NULL CHECK (action IN ('approve', 'reject', 'set_master', 'remove_row', 'same', 'different')),
    rows        integer[] NOT NULL,
    user_id     uuid REFERENCES users(id) ON DELETE SET NULL,
    created_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX review_decisions_dataset ON review_decisions (dataset_id, id);

ALTER TABLE review_decisions ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant ON review_decisions TO atlas_app USING (org_id = current_org()) WITH CHECK (org_id = current_org());
GRANT SELECT, INSERT, DELETE ON review_decisions TO atlas_app;

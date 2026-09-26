-- Phase 4, milestone 1: product catalogues.
--
-- A dataset is now a task export or a product catalogue. Catalogue rows get
-- their normalised values (brand, part number, variants, sizes, stock, cost)
-- in tasks.norm, beside the untouched original. Both columns sit on tables
-- that already have row-level security, so tenant isolation is unchanged.

ALTER TABLE datasets
    ADD COLUMN kind text NOT NULL DEFAULT 'tasks' CHECK (kind IN ('tasks', 'catalogue'));

ALTER TABLE tasks
    ADD COLUMN norm jsonb;

COMMENT ON COLUMN tasks.norm IS
    'Catalogue datasets only: normalised values computed from original and the column mapping. Recomputed whenever the mapping changes; never user-edited.';

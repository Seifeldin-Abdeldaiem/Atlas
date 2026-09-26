-- Phase 4, milestone 4: stock and value figures, and the cleaned file export.
--
-- Export files live in dataset_files next to the upload (kind = 'export'), so
-- they are private, stored under random keys, deleted with the dataset and
-- removed by the same 7-day expiry. A dataset has at most one upload.

ALTER TABLE dataset_files
    ADD COLUMN kind text NOT NULL DEFAULT 'upload' CHECK (kind IN ('upload', 'export'));
CREATE UNIQUE INDEX dataset_files_one_upload ON dataset_files (dataset_id) WHERE kind = 'upload';

-- Export progress and the file's details; cleared when results change.
ALTER TABLE datasets ADD COLUMN export jsonb;

-- Currency assumed for costs written without a symbol.
ALTER TABLE workspace_settings
    ADD COLUMN currency text NOT NULL DEFAULT 'GBP' CHECK (currency ~ '^[A-Z]{3}$');

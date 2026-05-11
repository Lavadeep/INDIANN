-- Annotators can mark document as "done"; once done they cannot edit.
-- Curators can curate only after all assigned annotators have marked done.
-- Single column on documents avoids a new table.

ALTER TABLE documents
ADD COLUMN IF NOT EXISTS annotator_completed_ids INTEGER[] NOT NULL DEFAULT '{}';

COMMENT ON COLUMN documents.annotator_completed_ids IS 'user_ids of annotators who clicked "Mark as done" for this document';

-- Create document_members table for document-level curator/annotator assignments.
-- Run this if create_all doesn't create it, or for manual migration.

CREATE TABLE IF NOT EXISTS document_members (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    project_id INTEGER NOT NULL REFERENCES projects(project_id) ON DELETE CASCADE,
    role VARCHAR(50) NOT NULL,
    user_ids INTEGER[] NOT NULL DEFAULT '{}',
    granted_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    granted_by INTEGER REFERENCES users(user_id) ON DELETE SET NULL,
    CONSTRAINT uq_document_member_doc_role UNIQUE (document_id, role)
);

CREATE INDEX IF NOT EXISTS ix_document_members_document_id ON document_members(document_id);
CREATE INDEX IF NOT EXISTS ix_document_members_project_id ON document_members(project_id);

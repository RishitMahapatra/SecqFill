-- Run this once against the existing production database (e.g. in Supabase's
-- SQL editor). schema.sql's questionnaire_items CREATE TABLE has also been
-- updated to include this column for fresh installs, but that only affects
-- databases created from scratch — it does not alter a table that already
-- exists, hence this migration.

ALTER TABLE questionnaire_items
    ADD COLUMN approved BOOLEAN NOT NULL DEFAULT false;

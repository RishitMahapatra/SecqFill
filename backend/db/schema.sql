-- SecQFill core schema
-- Run once against a Postgres 15+ database with the pgvector extension available.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- One row per customer company (the vendor using SecQFill, not the enterprise sending the questionnaire)
CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    stripe_customer_id TEXT,
    plan_tier TEXT NOT NULL DEFAULT 'trial',
    monthly_spend_limit_cents INT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The reusable Q&A library each company builds up over time. This is the core asset/moat.
CREATE TABLE answer_bank (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    question_text TEXT NOT NULL,
    answer_text TEXT NOT NULL,
    embedding VECTOR(768),
    source TEXT NOT NULL DEFAULT 'manual',
    times_used INT NOT NULL DEFAULT 0,
    last_used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX answer_bank_embedding_idx ON answer_bank
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX answer_bank_company_idx ON answer_bank(company_id);

-- One row per uploaded questionnaire file
CREATE TABLE questionnaires (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    company_id UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
    original_filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'processing',
    storage_path TEXT,
    uploaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One row per extracted question from a questionnaire
CREATE TABLE questionnaire_items (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    questionnaire_id UUID NOT NULL REFERENCES questionnaires(id) ON DELETE CASCADE,
    row_number INT NOT NULL,
    question_text TEXT NOT NULL,
    matched_answer_id UUID REFERENCES answer_bank(id),
    confidence_score NUMERIC(4,3),
    status TEXT NOT NULL DEFAULT 'pending',
    final_answer_text TEXT,
    -- True once a human has reviewed and approved this item. Rematching
    -- (see db/migrations/0001_add_approved_to_questionnaire_items.sql)
    -- skips items where this is true, so it doubles as "don't overwrite me."
    approved BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX questionnaire_items_qid_idx ON questionnaire_items(questionnaire_id);

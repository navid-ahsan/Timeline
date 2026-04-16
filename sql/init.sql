-- Enable pgvector
CREATE EXTENSION IF NOT EXISTS vector;

-- LangGraph schema (PostgresSaver creates its own tables, but the schema must exist)
CREATE SCHEMA IF NOT EXISTS langgraph;

-- LangChain PGVector tables
CREATE TABLE IF NOT EXISTS langchain_pg_collection (
    name      VARCHAR PRIMARY KEY,
    cmetadata JSON,
    uuid      UUID DEFAULT gen_random_uuid()
);

CREATE TABLE IF NOT EXISTS langchain_pg_embedding (
    id            UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    collection_id VARCHAR REFERENCES langchain_pg_collection(name) ON DELETE CASCADE,
    embedding     VECTOR(768),
    document      TEXT,
    cmetadata     JSON
);

CREATE INDEX IF NOT EXISTS idx_embedding_cosine
    ON langchain_pg_embedding USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

-- Audit trail
CREATE TABLE IF NOT EXISTS audit_log (
    id             SERIAL PRIMARY KEY,
    timestamp      TIMESTAMPTZ DEFAULT NOW(),
    patient_id     TEXT NOT NULL,
    worker_id      TEXT NOT NULL,
    action         TEXT NOT NULL,
    llm_suggestion JSONB,
    human_decision JSONB,
    diff           JSONB
);

CREATE INDEX IF NOT EXISTS idx_audit_patient    ON audit_log(patient_id);
CREATE INDEX IF NOT EXISTS idx_audit_timestamp  ON audit_log(timestamp);

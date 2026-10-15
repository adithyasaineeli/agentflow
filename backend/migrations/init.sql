-- ==============================================================================
-- AgentFlow: Database Initialization & Migrations (Supabase / PostgreSQL)
-- Enables pgvector, creates tables, and configures HNSW vector indexing
-- ==============================================================================

-- 1. Enable Required Extensions
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Helper function to auto-update 'updated_at' timestamps
CREATE OR REPLACE FUNCTION update_timestamp_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 2. Agents Table (Machine Authentication)
CREATE TABLE IF NOT EXISTS agents (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    name VARCHAR(100) NOT NULL,
    api_key_hash VARCHAR(255) UNIQUE NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_agents_api_key_hash ON agents (api_key_hash);

-- 3. Trajectories Table (Execution Playbooks & Vector Embeddings)
CREATE TABLE IF NOT EXISTS trajectories (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    agent_id VARCHAR(36) NOT NULL REFERENCES agents(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    task_goal TEXT NOT NULL,
    error_trace TEXT,
    playbook JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'completed',
    embedding vector(1536),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_trajectories_agent_id ON trajectories (agent_id);
CREATE INDEX IF NOT EXISTS idx_trajectories_status ON trajectories (status);
CREATE INDEX IF NOT EXISTS idx_trajectories_created_at ON trajectories (created_at DESC);

-- 4. HNSW Vector Index on Trajectory Embeddings (Cosine Distance)
CREATE INDEX IF NOT EXISTS idx_trajectories_embedding 
ON trajectories USING hnsw (embedding vector_cosine_ops);

-- Trigger for trajectories.updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_update_trajectories_timestamp'
    ) THEN
        CREATE TRIGGER trg_update_trajectories_timestamp
        BEFORE UPDATE ON trajectories
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_column();
    END IF;
END $$;

-- 5. Queue Tasks Table (PostgresSkipLockedQueue)
CREATE TABLE IF NOT EXISTS queue_tasks (
    id VARCHAR(36) PRIMARY KEY DEFAULT uuid_generate_v4()::text,
    task_type VARCHAR(100) NOT NULL,
    payload JSONB NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    locked_at TIMESTAMPTZ,
    locked_by VARCHAR(100),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_queue_tasks_task_type ON queue_tasks (task_type);

-- 6. Index to optimize SELECT ... FOR UPDATE SKIP LOCKED
CREATE INDEX IF NOT EXISTS idx_queue_tasks_status_created_at 
ON queue_tasks (status, created_at);

-- Trigger for queue_tasks.updated_at
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger WHERE tgname = 'trg_update_queue_tasks_timestamp'
    ) THEN
        CREATE TRIGGER trg_update_queue_tasks_timestamp
        BEFORE UPDATE ON queue_tasks
        FOR EACH ROW
        EXECUTE FUNCTION update_timestamp_column();
    END IF;
END $$;

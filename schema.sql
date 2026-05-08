-- AetherFlow Database Schema (PostgreSQL)
-- Generated from Alembic migration 001_initial_schema
-- This file shows the final database structure after migration

-- =====================================================
-- WORKFLOWS TABLE
-- =====================================================

CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description VARCHAR(1000),
    definition JSONB NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for workflows
CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_created_at ON workflows(created_at);

-- =====================================================
-- EXECUTIONS TABLE
-- =====================================================

-- Create enum types first
CREATE TYPE executionstatus AS ENUM ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED');
CREATE TYPE taskstatus AS ENUM ('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'RETRYING', 'SKIPPED');

CREATE TABLE executions (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    execution_request_id VARCHAR(255) UNIQUE,  -- For idempotency
    triggered_by VARCHAR(50) NOT NULL DEFAULT 'api',
    status executionstatus NOT NULL DEFAULT 'PENDING',
    input JSONB,
    result JSONB,
    error VARCHAR(1000),
    trace_id VARCHAR(255) NOT NULL UNIQUE,  -- For distributed tracing
    retry_count INTEGER NOT NULL DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for executions
CREATE INDEX idx_executions_workflow_id ON executions(workflow_id);
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_created_at ON executions(created_at);
CREATE INDEX idx_executions_trace_id ON executions(trace_id);

-- =====================================================
-- TASKS TABLE
-- =====================================================

CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    workflow_task_id VARCHAR(255) NOT NULL,  -- Reference to workflow definition
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'http', 'python', etc
    config JSONB NOT NULL,      -- Task configuration (url, timeout, etc)
    input JSONB,                -- Computed input for this task
    output JSONB,               -- Task result
    error VARCHAR(1000),        -- Error message if failed
    status taskstatus NOT NULL DEFAULT 'PENDING',
    worker_id VARCHAR(255),     -- Which worker is executing this
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 3,
    depends_on JSONB NOT NULL DEFAULT '[]'::jsonb,  -- Task dependencies
    position INTEGER NOT NULL DEFAULT 0,  -- Execution order
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    heartbeat_at TIMESTAMPTZ,   -- Worker crash detection
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for tasks
CREATE INDEX idx_tasks_execution_id ON tasks(execution_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_worker_id ON tasks(worker_id);
CREATE INDEX idx_tasks_created_at ON tasks(created_at);

-- =====================================================
-- SCHEMA VALIDATION QUERIES
-- =====================================================

-- Verify tables exist
SELECT schemaname, tablename
FROM pg_tables
WHERE schemaname = 'public'
ORDER BY tablename;

-- Verify enum types
SELECT typname, enumtypid
FROM pg_enum e
JOIN pg_type t ON e.enumtypid = t.oid
WHERE t.typname IN ('executionstatus', 'taskstatus');

-- Verify indexes
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;

-- Verify constraints
SELECT conname, conrelid::regclass, contype, conkey, confkey
FROM pg_constraint
WHERE conrelid IN (
    SELECT oid FROM pg_class
    WHERE relname IN ('workflows', 'executions', 'tasks')
)
ORDER BY conrelid::regclass, contype;

-- =====================================================
-- SAMPLE DATA QUERIES
-- =====================================================

-- Insert sample workflow
INSERT INTO workflows (id, name, definition, version, status)
VALUES (
    '550e8400-e29b-41d4-a716-446655440000',
    'Sample HTTP Workflow',
    '{
        "version": 1,
        "tasks": [
            {
                "id": "fetch_data",
                "type": "http",
                "name": "Fetch Data",
                "config": {
                    "url": "https://httpbin.org/get",
                    "method": "GET",
                    "timeout": 30
                },
                "depends_on": []
            }
        ]
    }'::jsonb,
    1,
    'ACTIVE'
);

-- Insert sample execution
INSERT INTO executions (id, workflow_id, triggered_by, status, trace_id)
VALUES (
    '550e8400-e29b-41d4-a716-446655440001',
    '550e8400-e29b-41d4-a716-446655440000',
    'api',
    'PENDING',
    'trace_123456789'
);

-- Insert sample task
INSERT INTO tasks (id, execution_id, workflow_task_id, name, type, config, depends_on, position)
VALUES (
    '550e8400-e29b-41d4-a716-446655440002',
    '550e8400-e29b-41d4-a716-446655440001',
    'fetch_data',
    'Fetch Data',
    'http',
    '{"url": "https://httpbin.org/get", "method": "GET", "timeout": 30}'::jsonb,
    '[]'::jsonb,
    0
);

-- Query sample data
SELECT
    w.name as workflow_name,
    e.status as execution_status,
    t.name as task_name,
    t.status as task_status,
    t.type as task_type
FROM workflows w
JOIN executions e ON w.id = e.workflow_id
JOIN tasks t ON e.id = t.execution_id
ORDER BY w.created_at DESC, e.created_at DESC, t.position;

-- =====================================================
-- PERFORMANCE QUERIES
-- =====================================================

-- Count by status (common dashboard queries)
SELECT status, COUNT(*) FROM executions GROUP BY status;
SELECT status, COUNT(*) FROM tasks GROUP BY status;

-- Recent executions with task counts
SELECT
    e.id,
    e.status,
    e.created_at,
    COUNT(t.id) as task_count,
    COUNT(CASE WHEN t.status = 'SUCCESS' THEN 1 END) as completed_tasks
FROM executions e
LEFT JOIN tasks t ON e.id = t.execution_id
GROUP BY e.id, e.status, e.created_at
ORDER BY e.created_at DESC
LIMIT 10;

-- Failed tasks in last 24 hours
SELECT
    t.id,
    t.name,
    t.error,
    e.trace_id,
    t.created_at
FROM tasks t
JOIN executions e ON t.execution_id = e.id
WHERE t.status = 'FAILED'
AND t.created_at > NOW() - INTERVAL '24 hours'
ORDER BY t.created_at DESC;

-- Worker activity (if multiple workers)
SELECT
    worker_id,
    COUNT(*) as tasks_processed,
    AVG(EXTRACT(EPOCH FROM (completed_at - started_at))) as avg_duration_seconds
FROM tasks
WHERE worker_id IS NOT NULL
AND completed_at IS NOT NULL
GROUP BY worker_id
ORDER BY tasks_processed DESC;
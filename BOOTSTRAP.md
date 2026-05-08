# AetherFlow Bootstrap Guide

**Quick Start?** See [QUICKREF.md](QUICKREF.md) for handy command reference.

## What's Included

This bootstrap provides:

- **SQLAlchemy models** (Workflow, Execution, Task) with proper indexes
- **FastAPI setup** with database connection and health checks
- **Docker Compose** for local development (PostgreSQL + Redis)
- **Alembic migrations** ready for schema management
- **Structured logging** with structlog JSON output
- **Configuration management** via environment variables

## Project Structure

```
aetherflow/
├── src/aetherflow/
│   ├── __init__.py          # Package marker
│   ├── main.py              # FastAPI app entry
│   ├── models.py            # SQLAlchemy models
│   ├── config.py            # Settings (env vars)
│   ├── logging.py           # Structured logging
│   └── ... (endpoints added in next phases)
├── alembic/
│   ├── env.py               # Alembic runtime config
│   ├── script.py.mako       # Migration template
│   └── versions/            # Migration files (auto-generated)
├── requirements.txt         # Python dependencies
├── docker-compose.yml       # Local dev environment
├── Dockerfile               # Container image
└── .env.example            # Environment template
```

## Quick Start

### 1. Prerequisites

- Docker & Docker Compose (for local PostgreSQL + Redis)
- Python 3.11+ (if running locally outside Docker)

### 2. Setup Local Environment

```bash
# Clone/navigate to project
cd aetherflow

# Copy environment template
cp .env.example .env

# Start services (PostgreSQL + Redis + API)
docker-compose up -d

# Run migrations (creates tables)
# Option A: Inside container
docker-compose exec api alembic upgrade head

# Option B: Locally (if Python installed)
export DATABASE_URL=postgresql://aetherflow:aetherflow_dev@localhost:5432/aetherflow
alembic upgrade head
```

### 3. Verify Setup

```bash
# Check API is running
curl http://localhost:8000/health

# Should return:
# {"status":"healthy","service":"aetherflow","environment":"development"}

# View API docs
open http://localhost:8000/docs
```

### 4. View Logs

```bash
# Stream API logs
docker-compose logs -f api

# Stream all services
docker-compose logs -f
```

## Key Design Decisions

### Models (models.py)

**Workflow**
- Immutable workflow definition (JSONB)
- Version tracking for schema evolution
- Simple status (ACTIVE/ARCHIVED)
- No complex relationships initially

**Execution**
- Tracks single workflow run
- `trace_id`: for distributed tracing (debugging across workers)
- `execution_request_id`: idempotency key (prevents duplicate executions)
- Status enum (PENDING → RUNNING → SUCCESS/FAILED)
- Stores input/result as JSON (flexible for any task output)

**Task**
- Tracks individual task execution
- `depends_on`: task dependency list (no foreign keys, just JSON array of IDs)
- `config`: task configuration (URL for HTTP, code for Python, etc)
- Worker crash detection via `worker_id` + `heartbeat_at`
- Structured columns for queryability (error as TEXT, not JSON)

### Configuration (config.py)

- Single `Settings` class loaded from environment
- No multiple config files (dev/prod/test)
- Pydantic validates types at startup
- All defaults sensible for local development

**Why no ConfigurationManager/Repository?**
- Pydantic handles validation, environment loading, defaults
- Simple dict access is sufficient for MVP
- Can add dependency injection later if needed

### Logging (logging.py)

- `structlog` for JSON structured output
- Context propagation via `contextvars` (thread-safe)
- `LogContext` manager for adding execution context
- All logs go to stdout (Docker/container-friendly)

**Example usage:**
```python
with LogContext(execution_id=exec_id, trace_id=trace_id):
    logger.info("task_executed", status="SUCCESS", duration_ms=245)
# Output: {"timestamp":"...","execution_id":"...","task_id":"...","status":"SUCCESS"}
```

### Database

**Indexes**
- On `status` (filter running executions)
- On `created_at` (list recent executions)
- On `trace_id` (lookup by trace)
- Partial indexes deferred to phase 2

**Foreign Keys**
- `execution.workflow_id` → `workflow.id`
- `task.execution_id` → `execution.id` (with cascade delete)
- No task → task dependencies (referential integrity deferred, using JSON array)

**Why JSON array for dependencies?**
- Avoids N+M lookup complexity for DAG queries
- Simpler initial implementation
- Can migrate to graph table if needed in phase 2

### FastAPI (main.py)

- Single `app = FastAPI()` instance
- Lifespan context manager for startup/shutdown
- Database connection pooling built-in
- Health check endpoint (for Docker healthchecks)
- No middleware yet (add as needed)
- No dependency injection framework (keep simple)

**Why?**
- Minimal cognitive load for solo engineer
- Easy to add complexity later
- Explicit is better than implicit

### Docker Compose

**Services**
- `postgres`: Database with health checks
- `redis`: Queue and caching
- `api`: FastAPI application with hot reload
- `worker`: Commented out (to implement next)

**Volumes**
- Source code mounted (hot reload)
- PostgreSQL data persisted
- No shared volumes initially

**Networks**
- Single bridge network for service discovery
- All services can reach each other by hostname

## Next Steps (Milestone 1 Continuation)

1. **Generate initial migration**
   ```bash
   alembic revision --autogenerate -m "Initial schema: workflows, executions, tasks"
   alembic upgrade head
   ```

2. **Create Workflow CRUD endpoints** (api.py)
   - POST /workflows (create)
   - GET /workflows (list)
   - GET /workflows/{id} (detail)

3. **Create Execution trigger endpoint**
   - POST /workflows/{id}/execute

4. **Implement Service layer** (service.py)
   - Workflow validation (DAG cycles)
   - Execution creation with idempotency
   - Task queueing logic

5. **Setup Redis queue** (queue.py)
   - Redis connection
   - Enqueue/dequeue task helpers

6. **Implement Worker** (worker.py)
   - Connect to queue
   - Task executor dispatch
   - DB updates

## Tradeoffs & Rationale

### ✅ Included in Bootstrap

- **Pydantic for settings**: Validation + environment loading built-in
- **SQLAlchemy ORM**: Mature, flexible, zero boilerplate
- **Alembic migrations**: Version control for schema changes
- **Docker Compose**: No local database setup needed
- **Structured logging**: JSON output from day 1 (queryable, AI-friendly)
- **Enum for status**: Type-safe, queryable, explicit

### ❌ Deliberately Omitted

- **DTO layer**: Use SQLAlchemy models directly in FastAPI
- **Abstract repositories**: Simple CRUD queries sufficient for MVP
- **Async everywhere**: FastAPI async where needed; sync ORM queries fine
- **Dependency injection framework**: Pydantic factories sufficient
- **Multiple config files**: One environment-driven config class
- **ORM relationships**: Foreign keys only; no lazy loading complexity
- **Task registry pattern**: Simple if/elif dispatch until needed
- **Event sourcing**: Just track status; events table in phase 2
- **Distributed tracing setup**: Logs and trace_id sufficient for now

## Common Tasks

### Adding a New Environment Variable

```python
# 1. Add to config.py
class Settings(BaseSettings):
    my_new_setting: str = "default_value"

# 2. In .env or docker-compose.yml
MY_NEW_SETTING=some_value

# 3. Use in code
from aetherflow.config import settings
print(settings.my_new_setting)
```

### Running Migrations

```bash
# Inside container
docker-compose exec api alembic upgrade head

# Locally
export DATABASE_URL=postgresql://aetherflow:aetherflow_dev@localhost:5432/aetherflow
alembic upgrade head

# Create new migration after schema changes
alembic revision --autogenerate -m "Add new column to workflows"
alembic upgrade head
```

### Debugging Database Issues

```bash
# Connect to PostgreSQL directly
docker-compose exec postgres psql -U aetherflow -d aetherflow

# List tables
\dt

# View schema
\d workflows

# Count records
SELECT COUNT(*) FROM workflows;
```

### Viewing Logs

```bash
# Real-time logs
docker-compose logs -f

# Just API service
docker-compose logs -f api

# Search in logs
docker-compose logs api | grep "error"
```

### Restarting Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart api postgres

# Full restart (reset data)
docker-compose down
docker-compose up -d
```

## Production Considerations (Phase 2+)

- Replace SQLite-like usage with connection pooling best practices
- Add API authentication (JWT or similar)
- Implement rate limiting
- Add request/response validation in API layer
- Use `gunicorn` with multiple workers
- Add CORS if needed
- Structured error responses
- Database backups strategy
- Monitoring and alerting

## Troubleshooting

**Port already in use**
```bash
# Change port in docker-compose.yml or .env
# Then:
docker-compose down
docker-compose up -d
```

**Database connection refused**
```bash
# Wait for PostgreSQL to fully start
docker-compose logs postgres
# Should show: "database system is ready to accept connections"

# Try manually
docker-compose exec api psql $DATABASE_URL -c "SELECT 1"
```

**Migrations fail**
```bash
# Check migration syntax
alembic revision --autogenerate -m "test"

# Downgrade and retry
alembic downgrade base
alembic upgrade head
```

---

**Next**: Continue to Milestone 1 Phase 2: Workflow CRUD endpoints and service layer.

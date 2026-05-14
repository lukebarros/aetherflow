# AetherFlow

**AI-enabled workflow orchestration and operational automation platform**

An opinionated, production-minded orchestration engine built for reliability, observability, and intelligent automation assistance.

## Features (Roadmap)

- ✅ **Workflow CRUD** (create, list workflows)
- ✅ **Execution management** (create executions, track status)
- ✅ **Task workflow execution** (sequential DAG execution via worker)
- ✅ **Retry logic** (exponential backoff, max retries per task)
- ✅ **Worker processing** (async task execution with HTTP and Python support)
- ✅ **Execution lifecycle tracking** (PENDING → RUNNING → SUCCESS/FAILED)
- ✅ **Dependency resolution** (automatic DAG ordering and task queuing)
- ✅ **Structured logging** (JSON logs for debugging and analysis)
- ✅ **Redis queue** (persistent async task queue)
- 🔄 **Execution status aggregation** (update execution status based on tasks) — Phase 1.6
- 🔄 **Job scheduling** (cron-based execution) — Phase 2
- 🔄 **Sub-workflows** (nested DAGs) — Phase 2
- 🔄 **Conditional branching** (if/else task flows) — Phase 2
- 🔄 **Distributed execution** (multi-worker coordination) — Phase 2+
- 🔄 **AI-assisted automation** (ML-based workflow optimization) — Phase 3+

## Stack

- **Backend**: FastAPI + Python
- **Database**: PostgreSQL
- **Queue**: Redis + RQ
- **Frontend**: React + Vite (roadmap)
- **Containerization**: Docker

## Quick Start

See [BOOTSTRAP.md](BOOTSTRAP.md) for detailed setup instructions, or [QUICKREF.md](QUICKREF.md) for handy commands.

```bash
# Start all services (API, database, Redis, worker)
docker-compose up -d

# Run migrations
docker-compose exec api alembic upgrade head

# Check health
curl http://localhost:8000/health

# View API docs
open http://localhost:8000/docs

# Watch worker logs
docker logs aetherflow_worker -f
```

## Example Usage

```bash
# Create a workflow
WORKFLOW_ID=$(curl -s -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Workflow",
    "definition": {
      "version": 1,
      "tasks": [
        {
          "id": "task_1",
          "type": "http",
          "name": "Fetch Data",
          "config": {"url": "https://api.example.com/data"},
          "depends_on": []
        },
        {
          "id": "task_2",
          "type": "http",
          "name": "Process",
          "config": {"url": "https://api.example.com/process"},
          "depends_on": ["task_1"]
        }
      ]
    }
  }' | jq -r '.id')

# Trigger execution
EXECUTION_ID=$(curl -s -X POST http://localhost:8000/workflows/$WORKFLOW_ID/execute \
  -H "Content-Type: application/json" \
  -d '{}' | jq -r '.id')

# Check status (worker processes tasks automatically)
curl http://localhost:8000/executions/$EXECUTION_ID | jq '.tasks[].status'
```

## Architecture

See [ARCHITECTURE_PRAGMATIC_MVP.md](ARCHITECTURE_PRAGMATIC_MVP.md) for detailed design rationale and [ARCHITECTURE.md](ARCHITECTURE.md) for comprehensive reference.

### Design Principles

- **Operational clarity**: System state visible in database; easy to debug
- **Idempotency first**: Safe retries and replay
- **Worker independence**: Stateless workers; state in database
- **Pragmatic simplicity**: Avoid architecture astronaut patterns
- **Future-proof foundation**: Design for distributed execution and AI integration

### Core Concepts

**Workflow**: DAG of tasks with retry policies and dependencies

**Execution**: Single run of a workflow with input, output, and status

**Task**: Unit of work within an execution (HTTP call, Python function, etc)

**Job**: Scheduled execution trigger (cron-based, roadmap)

## Development

### Milestone 1: MVP Execution Engine (Week 1-2)

- [x] Bootstrap project structure
- [x] Database schema and migrations
- [x] Workflow CRUD endpoints
- [x] Execution trigger and status tracking
- [ ] Worker task execution
- [ ] Integration test

### Milestone 2: Reliability & Scheduling (Week 3-4)

- [ ] Retry logic with backoff
- [ ] Job scheduling (cron)
- [ ] Worker crash recovery
- [ ] Enhanced logging and metrics

### Milestone 3: Observability (Week 5-6)

- [ ] Distributed tracing
- [ ] Metrics export (Prometheus)
- [ ] Dashboards
- [ ] Error aggregation

### Phase 2+: Advanced Features

- Conditional branching
- Sub-workflows
- Manual approval steps
- AI-assisted workflow optimization
- Multi-worker coordination

## Project Structure

```
aetherflow/
├── src/aetherflow/          # Application source
│   ├── main.py              # FastAPI app
│   ├── models.py            # SQLAlchemy models
│   ├── config.py            # Settings
│   ├── logging.py           # Structured logging
│   └── ... (service, api, worker in following phases)
├── alembic/                 # Database migrations
├── tests/                   # Test suite
├── docker-compose.yml       # Local dev environment
├── Dockerfile               # Container image
├── ARCHITECTURE.md          # Detailed design reference
├── ARCHITECTURE_PRAGMATIC_MVP.md  # MVP refinement guide
└── BOOTSTRAP.md             # Setup guide
```

## License

[To be determined]

## Contact

Built for operational clarity and production reliability.

Questions? [Open an issue](https://github.com/aetherflow/aetherflow/issues) (roadmap).

---

**Status**: Alpha - Milestone 1 in progress  
**Last Updated**: May 14, 2026

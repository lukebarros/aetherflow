# AetherFlow MVP Architecture Guide

**Status**: Design Phase  
**Scope**: Orchestration Core MVP  
**Target Audience**: Implementation team (current: solo engineer)  
**Last Updated**: May 8, 2026

---

## 1. Project Folder Structure

```
aetherflow/
├── backend/
│   ├── src/
│   │   ├── aetherflow/
│   │   │   ├── __init__.py
│   │   │   ├── main.py                 # FastAPI app entry
│   │   │   │
│   │   │   ├── domain/                 # Business logic (independent)
│   │   │   │   ├── workflow.py         # Workflow entity
│   │   │   │   ├── execution.py        # Execution entity
│   │   │   │   ├── task.py             # Task entity
│   │   │   │   ├── job.py              # Job entity (scheduled execution)
│   │   │   │   ├── events.py           # Domain events
│   │   │   │   └── exceptions.py       # Domain exceptions
│   │   │   │
│   │   │   ├── application/            # Use cases & orchestration
│   │   │   │   ├── workflow_service.py
│   │   │   │   ├── execution_service.py
│   │   │   │   ├── job_service.py
│   │   │   │   ├── scheduler.py        # Job scheduling logic
│   │   │   │   └── dto.py              # Data transfer objects
│   │   │   │
│   │   │   ├── infrastructure/
│   │   │   │   ├── postgres/
│   │   │   │   │   ├── models.py       # SQLAlchemy ORM models
│   │   │   │   │   ├── repositories.py # Data access layer
│   │   │   │   │   └── migrations.py   # Alembic migrations
│   │   │   │   ├── redis/
│   │   │   │   │   ├── queue_client.py # Redis queue interface
│   │   │   │   │   └── cache.py        # Caching if needed
│   │   │   │   ├── workers/
│   │   │   │   │   ├── celery_worker.py (or rq_worker.py)
│   │   │   │   │   └── task_registry.py
│   │   │   │   └── logging/
│   │   │   │       ├── structured.py
│   │   │   │       ├── context.py      # Context propagation
│   │   │   │       └── exporters.py    # OpenTelemetry exporters
│   │   │   │
│   │   │   ├── api/
│   │   │   │   ├── routes/
│   │   │   │   │   ├── workflows.py
│   │   │   │   │   ├── executions.py
│   │   │   │   │   ├── jobs.py
│   │   │   │   │   └── health.py
│   │   │   │   ├── middleware.py       # Logging, context injection
│   │   │   │   └── dependencies.py     # FastAPI dependency injection
│   │   │   │
│   │   │   └── config.py               # Settings (pydantic)
│   │   │
│   │   └── worker.py                   # Worker process entry (separate)
│   │
│   ├── tests/
│   │   ├── unit/
│   │   ├── integration/
│   │   └── fixtures/
│   │
│   ├── requirements.txt
│   ├── Dockerfile
│   └── alembic/

├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── pages/
│   │   ├── components/
│   │   └── api/
│   ├── vite.config.ts
│   └── package.json

├── docker-compose.yml
├── docker-compose.prod.yml
├── .env.example
└── README.md
```

**Rationale:**
- **domain/** is framework-agnostic—can be tested without FastAPI or databases
- **application/** orchestrates domain logic and infrastructure
- **infrastructure/** contains all external concerns (DB, queue, logging)
- **api/** is thin and delegates to application services
- **worker/** is separate to allow independent scaling

---

## 2. Core Domain Entities and Responsibilities

### 2.1 Domain Entities

```
Workflow
├─ id (UUID)
├─ name (string)
├─ description (string)
├─ definition (JSON) → WorkflowDefinition
├─ version (int) → immutable once created
├─ created_at (timestamp)
├─ updated_at (timestamp)
├─ created_by (string)
└─ status (ACTIVE | ARCHIVED)

Execution (run of a workflow)
├─ id (UUID)
├─ workflow_id (FK)
├─ triggered_by (string) → "api" | "scheduler" | "manual"
├─ input (JSON) → context/params
├─ status (PENDING | RUNNING | SUCCESS | FAILED | CANCELLED)
├─ lifecycle_state (enum below)
├─ started_at (timestamp)
├─ completed_at (timestamp)
├─ created_at (timestamp)
├─ execution_trace_id (string) → for distributed tracing
├─ retry_count (int)
├─ parent_execution_id (FK, nullable) → for sub-workflows
└─ result (JSON, nullable)

Task (step within an execution)
├─ id (UUID)
├─ execution_id (FK)
├─ workflow_task_id (string) → reference to workflow definition
├─ name (string)
├─ type (string) → "http" | "function" | "subworkflow" | "manual"
├─ input (JSON)
├─ status (PENDING | RUNNING | SUCCESS | FAILED | SKIPPED | WAITING)
├─ lifecycle_state (enum)
├─ started_at (timestamp)
├─ completed_at (timestamp)
├─ result (JSON, nullable)
├─ error (string, nullable)
├─ retry_count (int)
├─ worker_id (string, nullable)
├─ position (int) → execution order
└─ depends_on (array of task IDs)

Job (scheduled execution)
├─ id (UUID)
├─ workflow_id (FK)
├─ schedule_expression (cron)
├─ next_run_at (timestamp)
├─ last_run_at (timestamp)
├─ last_execution_id (FK, nullable)
├─ status (ACTIVE | PAUSED | DISABLED)
├─ input (JSON) → default params
├─ created_at (timestamp)
└─ timezone (string)
```

### 2.2 Execution Lifecycle States

**Execution Lifecycle**:
```
PENDING → RUNNING → SUCCESS
              ↘ → FAILED (terminal)
              ↘ → CANCELLED (terminal)
```

**Task Lifecycle** (within an Execution):
```
PENDING → WAITING (dependencies) → RUNNING → SUCCESS
                                        ↘ → FAILED
                                        ↘ → RETRYING → RUNNING
PENDING → SKIPPED (conditional)
```

**Why separate status from lifecycle_state?**
- `status` = current position in the flow
- `lifecycle_state` = internal state machine position (allows pause/resume/cancel without confusion)

### 2.3 Responsibilities

| Entity | Responsibility |
|--------|-----------------|
| **Workflow** | Define task DAG, validation rules, metadata |
| **Execution** | Track single workflow run, manage retries, store result |
| **Task** | Represent work unit, track dependencies, store outcome |
| **Job** | Store schedule, trigger executions on cron |
| **WorkflowDefinition (JSON schema)** | DAG structure, task configs, retry policies |

---

## 3. Execution Lifecycle Design

### 3.1 State Machine (ASCII)

```
┌─────────────────────────────────────────────────────────────┐
│                   EXECUTION LIFECYCLE                        │
└─────────────────────────────────────────────────────────────┘

CREATED (in DB, not queued)
  │
  ├─→ API validates workflow exists
  │
  ├─→ Queue execution task to Redis
  │
QUEUED (in Redis, waiting for worker)
  │
  ├─→ Worker claims task
  │
RUNNING
  ├─→ Evaluate task dependencies
  ├─→ All dependencies met? Execute next task
  ├─→ Task succeeds? Move to next
  ├─→ Task fails? Check retry policy
  │   ├─→ Retries available? → RETRYING → back to RUNNING
  │   ├─→ No retries? → FAILED (check error strategy)
  ├─→ All tasks done?
  │   ├─→ YES → completion handler → SUCCESS
  │   ├─→ NO → queue next task
  │
SUCCESS / FAILED / CANCELLED
  │
  ├─→ Update status in DB
  ├─→ Emit completion event
  ├─→ Cleanup if needed
```

### 3.2 Retry Strategy

```python
# In WorkflowDefinition
{
  "tasks": [
    {
      "id": "task_1",
      "type": "http",
      "retry_policy": {
        "max_retries": 3,
        "backoff_type": "exponential",
        "initial_delay_seconds": 1,
        "max_delay_seconds": 60,
        "retry_on": ["timeout", "5xx"]
      }
    }
  ]
}
```

**Backoff calculation**:
- Linear: delay = initial_delay × attempt
- Exponential: delay = initial_delay × (2 ^ attempt)
- With jitter: delay × (0.8 + random(0.4))

### 3.3 Error Handling Strategies

```json
{
  "error_handlers": [
    {
      "condition": "task fails with 429",
      "action": "backoff_and_retry"
    },
    {
      "condition": "task fails with 5xx",
      "action": "retry_or_fail_execution"
    },
    {
      "condition": "task times out",
      "action": "fail_and_alert"
    }
  ]
}
```

---

## 4. PostgreSQL Schema (DDL)

```sql
-- Workflows (immutable catalog)
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    definition JSONB NOT NULL,  -- WorkflowDefinition
    version INTEGER NOT NULL DEFAULT 1,
    created_by VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, ARCHIVED
    UNIQUE(name, version)
);

CREATE INDEX idx_workflows_status ON workflows(status);
CREATE INDEX idx_workflows_created_at ON workflows(created_at DESC);

-- Executions (workflow runs)
CREATE TABLE executions (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    parent_execution_id UUID REFERENCES executions(id),  -- for sub-workflows
    triggered_by VARCHAR(50) NOT NULL,  -- 'api', 'scheduler', 'manual'
    input JSONB,
    result JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',  -- PENDING, RUNNING, SUCCESS, FAILED, CANCELLED
    lifecycle_state VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    execution_trace_id VARCHAR(255) NOT NULL UNIQUE,
    retry_count INTEGER DEFAULT 0,
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_executions_workflow_id ON executions(workflow_id);
CREATE INDEX idx_executions_status ON executions(status);
CREATE INDEX idx_executions_created_at ON executions(created_at DESC);
CREATE INDEX idx_executions_trace_id ON executions(execution_trace_id);
CREATE INDEX idx_executions_parent_id ON executions(parent_execution_id);
CREATE INDEX idx_executions_completed_at ON executions(completed_at DESC) WHERE status IN ('SUCCESS', 'FAILED');

-- Tasks (execution steps)
CREATE TABLE tasks (
    id UUID PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    workflow_task_id VARCHAR(255) NOT NULL,  -- reference to workflow definition
    name VARCHAR(255) NOT NULL,
    type VARCHAR(50) NOT NULL,  -- 'http', 'function', 'subworkflow', 'manual'
    input JSONB,
    result JSONB,
    error TEXT,
    status VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    lifecycle_state VARCHAR(50) NOT NULL DEFAULT 'PENDING',
    retry_count INTEGER DEFAULT 0,
    worker_id VARCHAR(255),
    position INTEGER NOT NULL,
    depends_on TEXT ARRAY,  -- array of task IDs
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_tasks_execution_id ON tasks(execution_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_worker_id ON tasks(worker_id);
CREATE INDEX idx_tasks_created_at ON tasks(created_at DESC);

-- Jobs (scheduled executions)
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    workflow_id UUID NOT NULL REFERENCES workflows(id),
    schedule_expression VARCHAR(255) NOT NULL,  -- cron format
    next_run_at TIMESTAMPTZ NOT NULL,
    last_run_at TIMESTAMPTZ,
    last_execution_id UUID REFERENCES executions(id),
    input JSONB,
    status VARCHAR(50) NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE, PAUSED, DISABLED
    timezone VARCHAR(100) DEFAULT 'UTC',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_jobs_workflow_id ON jobs(workflow_id);
CREATE INDEX idx_jobs_next_run_at ON jobs(next_run_at) WHERE status = 'ACTIVE';
CREATE INDEX idx_jobs_status ON jobs(status);

-- Execution Events (audit log + event sourcing foundation)
CREATE TABLE execution_events (
    id BIGSERIAL PRIMARY KEY,
    execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
    task_id UUID REFERENCES tasks(id) ON DELETE CASCADE,
    event_type VARCHAR(100) NOT NULL,  -- CREATED, STARTED, COMPLETED, FAILED, RETRYING, etc.
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_execution_events_execution_id ON execution_events(execution_id);
CREATE INDEX idx_execution_events_created_at ON execution_events(created_at DESC);
CREATE INDEX idx_execution_events_event_type ON execution_events(event_type);

-- Audit Log (compliance, debugging)
CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    resource_type VARCHAR(100),  -- 'workflow', 'execution', 'job'
    resource_id UUID,
    action VARCHAR(50),  -- 'created', 'updated', 'deleted', 'executed'
    actor VARCHAR(255),
    changes JSONB,  -- what changed
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_audit_log_resource ON audit_log(resource_type, resource_id);
CREATE INDEX idx_audit_log_created_at ON audit_log(created_at DESC);
```

**Key Design Decisions:**
- **JSONB for definition/input/result**: Flexible schema evolution, queryable
- **execution_trace_id**: Enables distributed tracing across workers
- **execution_events table**: Foundation for event-driven architecture + AI analysis
- **Cascading deletes**: Clean up task records with execution
- **Partial indexes on status**: Performance for active queries
- **Audit log**: Track changes for compliance and debugging

---

## 5. Worker Execution Flow

### 5.1 Worker Loop

```
Worker Process
├─ Connect to Redis queue
├─ Loop:
│  ├─ Dequeue task (blocking wait, timeout 30s)
│  │
│  ├─ [If task]:
│  │  ├─ Load execution from DB
│  │  ├─ Load execution context (trace ID, input)
│  │  ├─ Validate task dependencies are met
│  │  ├─ Mark task as RUNNING in DB
│  │  ├─ Execute task:
│  │  │  ├─ Call task handler (HTTP, function, etc.)
│  │  │  ├─ Capture result
│  │  │  ├─ Emit task event (COMPLETED or FAILED)
│  │  ├─ On success:
│  │  │  ├─ Mark task SUCCESSFUL
│  │  │  ├─ Queue next dependent tasks (if any)
│  │  │  ├─ If last task: mark execution as SUCCESS
│  │  ├─ On failure:
│  │  │  ├─ Check retry policy
│  │  │  ├─ If retries available: requeue with backoff
│  │  │  ├─ If no retries: mark execution FAILED
│  │  ├─ Update DB with result/error
│  │  └─ Log with execution_trace_id context
│  │
│  ├─ [If timeout]:
│  │  └─ Continue loop (no task)
│
└─ (Graceful shutdown on SIGTERM)
```

### 5.2 Dependency Resolution

**Simple approach** (MVP):
- On task completion, query DB for tasks with depends_on = [completed_task_id]
- Mark those as eligible (WAITING → PENDING)
- Queue them to Redis

**Future approach** (better for large DAGs):
- Cache dependency graph in memory
- Use topological sort

### 5.3 Worker Configuration

```python
# config.py
class WorkerConfig:
    queue_name = "aetherflow_tasks"
    max_concurrent_tasks = 10
    task_timeout_seconds = 3600
    heartbeat_interval_seconds = 30
    
    # For RQ vs Celery choice:
    # RQ: simpler, synchronous, better for MVP
    # Celery: more mature, distributed, complexity tax
```

**Recommendation for MVP**: Use **RQ** (Redis Queue)
- Simpler Python API
- No Celery broker complexity
- Good for < 1000 tasks/sec throughput
- Can upgrade to Celery later if needed

---

## 6. API Endpoint Suggestions

### 6.1 Workflow Management

```
POST   /api/v1/workflows
       Create new workflow
       Body: { name, description, definition }
       Response: { id, version, ... }

GET    /api/v1/workflows
       List workflows (paginated)
       Query: ?status=ACTIVE&limit=20&offset=0
       Response: { items: [...], total }

GET    /api/v1/workflows/{workflow_id}
       Get workflow definition
       Response: Workflow + definition

PUT    /api/v1/workflows/{workflow_id}
       Update workflow (new version)
       Body: { definition, description }
       Response: { version, ... }

DELETE /api/v1/workflows/{workflow_id}
       Archive workflow (soft delete)

POST   /api/v1/workflows/{workflow_id}/validate
       Validate workflow definition without creating
       Body: { definition }
       Response: { valid: bool, errors?: [...] }
```

### 6.2 Execution Management

```
POST   /api/v1/workflows/{workflow_id}/execute
       Trigger execution
       Body: { input?, triggered_by? }
       Response: { execution_id, status }

GET    /api/v1/executions/{execution_id}
       Get execution details with all tasks
       Response: { execution, tasks: [...] }

GET    /api/v1/executions
       List executions (paginated, filterable)
       Query: ?workflow_id=X&status=RUNNING&limit=50
       Response: { items: [...], total }

POST   /api/v1/executions/{execution_id}/cancel
       Cancel running execution
       Response: { status: CANCELLED }

GET    /api/v1/executions/{execution_id}/tasks
       Get task details for execution
       Response: { items: [...] }

GET    /api/v1/executions/{execution_id}/logs
       Stream execution logs (future: WebSocket)
       Response: { logs: [...] }
```

### 6.3 Job Management

```
POST   /api/v1/workflows/{workflow_id}/jobs
       Create scheduled job
       Body: { schedule_expression, input?, timezone? }
       Response: { job_id, next_run_at }

GET    /api/v1/jobs
       List scheduled jobs
       Response: { items: [...] }

PUT    /api/v1/jobs/{job_id}
       Update job (pause, resume, change schedule)
       Body: { schedule_expression?, status? }

DELETE /api/v1/jobs/{job_id}
       Delete job

GET    /api/v1/jobs/{job_id}/executions
       List executions triggered by this job
```

### 6.4 Observability

```
GET    /health
       Basic health check
       Response: { status: "healthy", timestamp }

GET    /health/detailed
       Detailed service health
       Response: { database: ok, redis: ok, workers: count }

GET    /metrics
       Prometheus metrics endpoint
       (execution count, task count, latencies, etc.)
```

**API Design Principles:**
- RESTful where sensible
- Pagination for list endpoints (limit, offset)
- Consistent error responses: `{ error: string, code: string, details?: {} }`
- Trace ID in response headers for debugging

---

## 7. Logging and Observability Recommendations

### 7.1 Structured Logging

```python
# All logs structured with fields:
{
  "timestamp": "2026-05-08T14:30:00Z",
  "level": "INFO",
  "logger": "aetherflow.application.execution_service",
  "message": "Execution started",
  "execution_id": "exec_123",
  "workflow_id": "wf_456",
  "execution_trace_id": "trace_789",  # For tracing
  "user": "api_client_1",
  "duration_ms": 125,
  "status": "SUCCESS"
}
```

**Stack:**
- **Logging library**: `python-json-logger` + `structlog`
- **Context propagation**: OpenTelemetry SDK
- **Export to**: CloudWatch / Datadog / ELK
- **Log level**: DEBUG in dev, INFO in prod

### 7.2 Distributed Tracing

```python
# Every execution gets a unique trace_id
# Propagate through:
# - execution.execution_trace_id
# - HTTP headers (X-Trace-ID)
# - Task context
# - Worker heartbeats

# Collect in OpenTelemetry:
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

with tracer.start_as_current_span("execute_task") as span:
    span.set_attribute("execution_id", execution_id)
    span.set_attribute("task_id", task_id)
    # ... execute
```

### 7.3 Metrics to Instrument

```
Counter:
  - executions_created_total (by workflow, status)
  - tasks_created_total (by type)
  - tasks_failed_total (by error type)
  - retries_total

Histogram:
  - execution_duration_seconds
  - task_duration_seconds
  - task_wait_time_seconds (queued time)
  - workflow_end_to_end_time_seconds

Gauge:
  - executions_running
  - tasks_pending
  - workers_available
  - redis_queue_depth
```

### 7.4 Error Tracking

```python
# Use Sentry or similar:
import sentry_sdk

sentry_sdk.init("https://key@sentry.io/project")

try:
    execute_task()
except Exception as e:
    sentry_sdk.capture_exception(e, {
        "execution_id": execution_id,
        "task_id": task_id,
        "trace_id": trace_id
    })
```

---

## 8. Suggested Development Order

### Phase 1: Foundation (Week 1-2)
1. **Project setup**
   - FastAPI app skeleton
   - PostgreSQL + Alembic setup
   - Docker Compose (dev environment)
   - Structured logging foundation

2. **Domain + Database**
   - Workflow, Execution, Task, Job domain entities
   - Generate migrations
   - Repository layer (basic CRUD)

3. **API Scaffolding**
   - POST /workflows
   - GET /workflows/{id}
   - POST /workflows/{id}/execute
   - GET /executions/{id}
   - Middleware for logging + tracing

### Phase 2: Execution Engine (Week 3-4)
1. **Worker foundation**
   - Redis queue connection
   - Task executor skeleton
   - RQ integration

2. **Execution lifecycle**
   - Queuing logic (POST /execute)
   - Task dependency resolver
   - State machine transitions

3. **Integration**
   - Worker dequeues and executes
   - Database updates
   - Test end-to-end simple workflow

### Phase 3: Reliability (Week 5)
1. **Retry logic**
   - Backoff strategies
   - Error handling
   - Max retries enforcement

2. **Execution events**
   - Event persistence
   - Audit log

3. **Error responses**
   - Structured errors
   - HTTP status codes

### Phase 4: Scheduling (Week 6)
1. **Job model + API**
2. **Scheduler service** (cron evaluation)
3. **Integration with execution service**

### Phase 5: Observability (Week 7)
1. **Metrics export**
2. **Distributed tracing**
3. **Health endpoints**
4. **Dashboards** (Grafana/CloudWatch)

### Phase 6: Polish (Week 8)
1. **Integration tests**
2. **Load testing**
3. **Documentation**

---

## 9. Common Architectural Mistakes to Avoid

### ❌ Mistake 1: Monolithic Task Execution
**Wrong**: All task logic in one function
```python
def execute_task(task):
    if task.type == "http":
        # ... HTTP logic
    elif task.type == "function":
        # ... function logic
    # 200 lines of if/elif
```

**Right**: Task handler registry
```python
class TaskHandlerRegistry:
    handlers: Dict[str, TaskHandler] = {}
    
    def register(task_type: str, handler: TaskHandler):
        handlers[task_type] = handler
    
    def execute(task: Task) -> Result:
        handler = handlers.get(task.type)
        return handler.execute(task)
```

---

### ❌ Mistake 2: Worker Synchronously Waiting
**Wrong**: Worker blocks on completion
```python
# Don't do this
result = execute_task_blocking()  # 5 minute wait
update_db(result)
```

**Right**: Queue result processing or use callbacks
```python
# Queue a separate result-processing task
execute_task_async()
# Worker picks up result when ready
# Or: separate worker for result handling
```

---

### ❌ Mistake 3: No Task Dependency Validation
**Wrong**: Execute tasks in order without checking dependencies
```python
# Assumes task ordering is correct
task_1 = tasks[0]
task_2 = tasks[1]
execute(task_1)
execute(task_2)  # What if task_1 failed?
```

**Right**: Explicit dependency check + DAG validation
```python
def can_execute_task(task: Task, execution: Execution) -> bool:
    for dep_id in task.depends_on:
        dep_task = find_task(execution, dep_id)
        if dep_task.status != TaskStatus.SUCCESS:
            return False
    return True

# Validate DAG on workflow creation
def validate_dag(definition: WorkflowDefinition) -> bool:
    # Check for cycles
    # Check all dependencies exist
```

---

### ❌ Mistake 4: Losing Context Between Workers
**Wrong**: No trace ID propagation
```python
# Worker A starts execution
# Worker B picks up task—no connection to original execution
# Logs are scattered
```

**Right**: Execution trace ID everywhere
```python
execution.execution_trace_id = uuid.uuid4().hex
# Pass to all tasks, all logs
task.execution_trace_id = execution.execution_trace_id
# In logs:
logger.info("Task executed", execution_id=execution.id, 
            trace_id=execution.execution_trace_id)
```

---

### ❌ Mistake 5: Retry Logic in Task Code
**Wrong**: Retry inside task implementation
```python
def my_task():
    for i in range(3):
        try:
            call_external_api()
            break
        except:
            time.sleep(2 ** i)
```

**Right**: Retry at execution level
```python
# Workflow definition
{
  "tasks": [{
    "retry_policy": {
      "max_retries": 3,
      "backoff": "exponential"
    }
  }]
}

# Worker respects policy
# Task code focuses on logic only
```

---

### ❌ Mistake 6: Circular Dependencies
**Wrong**: Not validating DAG structure
```python
# Task A depends on Task B
# Task B depends on Task A
# → Infinite wait
```

**Right**: Topological sort validation
```python
def validate_workflow_definition(definition):
    graph = build_dependency_graph(definition)
    if has_cycle(graph):
        raise ValidationError("Circular dependency detected")
```

---

### ❌ Mistake 7: Unbounded Retries
**Wrong**: Allowing exponential backoff to grow infinitely
```python
{
  "retry_policy": {
    "max_retries": 999,
    "initial_delay": 1,
    "backoff": "exponential"  # 2^999 seconds!
  }
}
```

**Right**: Cap delays
```python
{
  "retry_policy": {
    "max_retries": 5,
    "initial_delay_seconds": 1,
    "max_delay_seconds": 300,  # 5 minutes max
    "backoff": "exponential"
  }
}
```

---

### ❌ Mistake 8: No State Machine Enforcement
**Wrong**: Status updates happen anywhere
```python
execution.status = "SUCCESS"  # Too easy to set wrong
execution.status = "RUNNING"  # Inconsistent transitions
```

**Right**: State machine with validations
```python
class Execution:
    def mark_running(self):
        if self.status not in [ExecutionStatus.PENDING]:
            raise InvalidStateTransition(
                f"Cannot move from {self.status} to RUNNING"
            )
        self.status = ExecutionStatus.RUNNING
        self.started_at = now()
```

---

### ❌ Mistake 9: Writing to DB During Task Execution
**Wrong**: Task writes its own result
```python
def task_handler():
    result = do_work()
    task.result = result  # Direct write
    db.commit()  # Race conditions!
```

**Right**: Return result, let orchestrator write
```python
def task_handler(task_config) -> TaskResult:
    return TaskResult(status="SUCCESS", output=do_work())

# Worker receives result
worker.execute_task()
worker.update_db_with_result()  # Single write
```

---

### ❌ Mistake 10: Hardcoding External Service URLs
**Wrong**: URLs in code
```python
response = requests.get("http://api.example.com/endpoint")
```

**Right**: Configuration + environment variables
```python
class Config:
    external_api_url = os.getenv("EXTERNAL_API_URL")

# In task config
{
  "type": "http",
  "url": "${config.external_api_url}/endpoint"
}
```

---

## 10. Future-Proofing for AI Integration

**Design principles** for AI assistant features (roadmap, not MVP):

1. **Structured inputs/outputs**: All task data in JSON, standardized schema
2. **Audit trail**: execution_events table enables LLM analysis of failures
3. **Suggested fixes**: AI can analyze error patterns and suggest configuration changes
4. **Intelligent retries**: ML model predicts likelihood of success, adjusts retry strategy
5. **Workflow optimization**: Analyze execution patterns, suggest parallelization
6. **Natural language workflow creation**: "Create a workflow that calls API X then sends email"

---

## 11. Future-Proofing for Distributed Execution

**Design principles** for multi-node deployment:

1. **No shared state in workers**: Workers are stateless (all state in DB)
2. **Optimistic locking**: Use DB version numbers for concurrent updates
3. **Distributed locks**: For critical sections (job scheduling, task claiming)
4. **Queue-based fan-out**: Tasks pushed to Redis (workers auto-discover)
5. **Trace ID propagation**: Correlate work across multiple workers
6. **Health checks**: Workers register heartbeat, coordinator detects failures

---

## 12. Technology Decision Summary

| Layer | Choice | Why | Alternative |
|-------|--------|-----|--------------|
| API Framework | FastAPI | Async, modern, minimal overhead | Flask, Django |
| Database | PostgreSQL | Proven, JSONB, transactions, good Python support | MySQL, MongoDB |
| Queue | Redis + RQ | Simple, synchronous, easy debugging | Celery, RabbitMQ |
| ORM | SQLAlchemy | Flexible, explicit, widely supported | Tortoise, Peewee |
| Async | asyncio (FastAPI) | Native Python, good library support | Manual threading |
| Migrations | Alembic | SQLAlchemy-native, version control friendly | Flyway, raw SQL |
| Logging | structlog + json | Structured data, queryable, LLM-friendly | Standard logging |
| Tracing | OpenTelemetry | Vendor-neutral, industry standard | Jaeger SDK directly |
| Testing | pytest | Fixtures, plugins, wide adoption | unittest |

---

## Next Steps

1. **Review this architecture** with team (if applicable)
2. **Create Phase 1 scaffolding** (FastAPI + DB schema)
3. **Implement first simple workflow** end-to-end (design validation)
4. **Add observability early** (not an afterthought)
5. **Document as you go** (ADRs for major decisions)

---

**Document Version**: 1.0  
**Last Reviewed**: May 8, 2026  
**Maintainer**: Senior Backend Engineer

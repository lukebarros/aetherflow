# AetherFlow: Pragmatic MVP Refinement

**Purpose**: Refactor ARCHITECTURE.md for solo engineer implementation with minimal premature complexity  
**Date**: May 8, 2026  
**Status**: Implementation guidance for Phase 1

---

## Executive Summary

The original architecture is sound but over-engineered for MVP. This document simplifies it by:

- **Reducing abstraction layers** from domain/application/infrastructure to core/api/infra
- **Deferring event sourcing** (execution_events table) to phase 2
- **Removing unnecessary DTOs** (use domain models directly in FastAPI)
- **Simplifying state machine** to enum + validation (not a library)
- **Focusing JSONB** on workflow definition only, structure everything else
- **Delaying observability** beyond structured logs (metrics/tracing phase 2)
- **Cutting scheduling** from MVP scope (pure async execution first)
- **Keeping idempotency practical** (database constraints, idempotency keys, not sagas)

**Result**: A maintainable system that can be built in 4 weeks by a solo engineer, not 8.

---

## 1. Simplified Folder Structure

### Current (Over-engineered)
```
src/aetherflow/
├── domain/          # 4 files
├── application/     # 3 files  
├── infrastructure/  # 6+ files
├── api/             # 2 files
└── config.py
```

### Refined (MVP-focused)
```
src/aetherflow/
├── models.py           # 3 domain classes: Workflow, Execution, Task
├── schema.py           # Pydantic for API serialization (no DTO layer)
├── repo.py             # Simple repository layer (CRUD)
├── service.py          # Orchestration logic (small, focused)
├── worker.py           # Worker entry point + task executor
├── api.py              # FastAPI routes (all in one file initially)
├── config.py           # Settings
└── logging.py          # Structured logging setup
```

**Why?**
- No domain/ application/ infrastructure/ separation for MVP
- Single files scale to ~500-1000 lines before splitting
- Easier to navigate as a solo engineer
- Avoid "folder as namespace" confusion
- When refactoring becomes necessary, split strategically

**Migration path**: Phase 2 can split into core/ api/ worker/ infra/ if needed. No wasted early refactoring.

---

## 2. Minimal MVP Scope

### Remove from MVP

| Component | When | Why |
|-----------|------|-----|
| **Job/Scheduling** | Phase 2 | Extra complexity; API-triggered execution is enough |
| **execution_events table** | Phase 2 | Defer event sourcing; track status changes in executions table |
| **Audit log table** | Phase 2 | Nice to have; logging covers this initially |
| **Distributed tracing** | Phase 2+ | Overkill for single worker; structured logs sufficient |
| **Metrics export** | Phase 2+ | Focus on logs first; add Prometheus later |
| **WebSocket logs** | Phase 2+ | HTTP polling is fine initially |
| **Manual task type** | Phase 2 | Start with HTTP + inline Python functions |
| **Sub-workflows** | Phase 2 | DAG execution is complex; add after MVP works |
| **Conditional branching** | Phase 2 | Strict sequential first |

### Keep in MVP

```
✓ Workflow CRUD (define, store, list)
✓ Workflow definition validation (simple DAG check)
✓ Execution trigger (POST /execute)
✓ Task execution (HTTP calls, Python functions)
✓ Dependency resolution (sequential for MVP)
✓ Retries with backoff
✓ Worker process (single threaded initially)
✓ Execution status tracking (PENDING → RUNNING → SUCCESS/FAILED)
✓ Structured logging (JSON logs to stdout)
✓ Error tracking (error field in task)
✓ Docker Compose dev environment
```

---

## 3. Recommended "Thin Vertical Slice"

Execute this path **first** to validate architecture:

### 3.1 Path: Create → Store → Execute → Complete

**File creation order:**

#### Step 1: Models (`models.py`)
```
Define 3 classes:
  - Workflow (id, name, definition: dict, created_at)
  - Execution (id, workflow_id, status, input, result, created_at, updated_at)
  - Task (id, execution_id, name, status, input, result, error)

No repository interfaces yet. Direct SQLAlchemy.
```

#### Step 2: Database (`schema.py` migrations)
```
Create tables:
  - workflows
  - executions
  - tasks

Run one Alembic migration. No fancy versioning.
```

#### Step 3: API endpoints (`api.py`)
```
POST   /workflows
  Input: { name, definition }
  - Validate definition (simple: check all task ids exist)
  - Store in DB
  - Return workflow

GET    /workflows/{id}
  - Return from DB

POST   /workflows/{id}/execute
  Input: { input? }
  - Create execution record (status=PENDING)
  - Return execution_id immediately
  - Queue task to Redis
  - (Worker picks up async)

GET    /executions/{id}
  - Return execution + all tasks
```

#### Step 4: Worker (`worker.py`)
```
Loop:
  - Dequeue from Redis
  - Load execution from DB
  - Load task from DB
  - If no dependencies remain: execute_task()
  - Update task with result/error in DB
  - If task success and more tasks: queue next
  - If task failed: check retry; requeue or mark execution FAILED
```

#### Step 5: Task executor
```
def execute_task(task):
  if task.type == "http":
    response = requests.get(task.config["url"], ...)
    return response.json()
  elif task.type == "python":
    # Load function code from task.config["code"]
    # eval() or import from file
    return fn(task.input)

Keep it simple. No task handler registry yet.
```

#### Step 6: Logging
```
Use structlog:
  logger.info("task_executed", 
    execution_id=..., 
    task_id=..., 
    status=...,
    duration_ms=...)

Log to stdout in JSON format. Done.
```

### 3.2 Complete Flow (Traced)

```
User: POST /workflows/{id}/execute

API:
  1. Load Workflow from DB
  2. Create Execution(status=PENDING) → save to DB
  3. Find first task in workflow.definition
  4. Create Task(status=PENDING) → save to DB
  5. Queue task to Redis
  6. Return { execution_id, status: "PENDING" }

Worker (async):
  1. Dequeue task
  2. Load Execution, Task, Workflow from DB
  3. execute_task(task) → result
  4. Update Task(status=SUCCESS, result=result)
  5. Load Execution tasks, find next executable task
  6. If exists: create Task and queue
  7. If not: update Execution(status=SUCCESS)
  8. Log completion

User: GET /executions/{id}
  - Execution with all tasks
```

**Time to implement**: ~1 week (solo engineer)

---

## 4. Idempotency and Reliability

### 4.1 Duplicate Execution Protection

**Problem**: User clicks "execute" twice → two executions  
**MVP Solution**: Add `execution_request_id` (idempotency key)

```python
# API request
POST /workflows/{id}/execute
{
  "execution_request_id": "user-generated-uuid-or-hash",  # Client provides
  "input": {}
}

# Database
executions table:
  - execution_request_id (UNIQUE)
  
# Logic in API:
try:
  existing = db.query(Execution).filter_by(
    execution_request_id=request_id
  ).first()
  if existing:
    return existing  # Idempotent
  
  new_exec = create_execution()
  db.commit()
  return new_exec
except IntegrityError:
  # Race condition: another request won
  existing = db.query(Execution).filter_by(
    execution_request_id=request_id
  ).first()
  return existing
```

**Why**: Simple, doesn't require complex distributed transactions.

---

### 4.2 Retry Safety

**Problem**: Retried task executes twice  
**MVP Solution**: Idempotent task execution

```python
# Task executor must be idempotent
# If task already marked SUCCESS and retry is triggered:
#   1. Don't execute again
#   2. Mark execution as SUCCESS

def execute_next_task(execution_id):
  task = get_next_pending_task(execution_id)
  
  if not task:
    # All tasks done
    mark_execution_complete(execution_id)
    return
  
  if task.status == TaskStatus.SUCCESS:
    # Already executed; move to next
    execute_next_task(execution_id)
    return
  
  try:
    result = task_executor.run(task)
    task.result = result
    task.status = TaskStatus.SUCCESS
  except Exception as e:
    if task.retry_count < task.max_retries:
      task.retry_count += 1
      task.status = TaskStatus.PENDING
      # Requeue with delay
      queue.enqueue_at(task, delay=backoff(task.retry_count))
    else:
      task.error = str(e)
      task.status = TaskStatus.FAILED
      mark_execution_failed(execution_id, reason=str(e))
      return
```

**Key**: Status in DB is source of truth. Re-execution checks status first.

---

### 4.3 Worker Crash Recovery

**Problem**: Worker crashes mid-task execution  
**MVP Solution**: Task ownership + timeout

```python
# Task table
CREATE TABLE tasks (
  ...
  worker_id VARCHAR(255),         # Which worker claimed it
  started_at TIMESTAMPTZ,
  heartbeat_at TIMESTAMPTZ,       # Last worker heartbeat
  ...
);

# Worker heartbeat
def heartbeat_worker():
  while True:
    db.update(tasks)
      .filter(worker_id = MY_ID)
      .set(heartbeat_at = NOW())
    time.sleep(10)

# Crash detection (background job, simplest: cron every minute)
def detect_stalled_tasks():
  stalled = db.query(Task).filter(
    status == TaskStatus.RUNNING
    AND heartbeat_at < NOW() - interval('30 seconds')
  )
  
  for task in stalled:
    # Mark for retry or fail
    if task.retry_count < task.max_retries:
      task.status = TaskStatus.PENDING
      task.retry_count += 1
    else:
      task.status = TaskStatus.FAILED
      task.error = "Worker crashed"
```

**Why**: Simple, doesn't require complex distributed consensus.

---

### 4.4 External Side Effect Concern

**Problem**: Task calls external API, succeeds, worker crashes before DB update  
**MVP Reality**: Accept this risk in MVP, mitigate with idempotency

```
External API Must Be Idempotent:
  - POST /charge/{user_id}?idempotency_key=TASK_ID
  - API refuses duplicate charges within window
  
This is task implementation responsibility, not framework.

Advanced (phase 2):
  - Transactional outbox pattern
  - Store "side effect pending" before calling API
  - Async confirmation job checks API state
  
For MVP: Document that tasks must be idempotent.
```

---

### 4.5 Execution Checkpointing

**Not needed for MVP**. Keep simple:

```
Execution lifecycle is atomic at task granularity:
  - Task succeeds and result persisted: immutable
  - Task retries: mark PENDING, retry from scratch
  
No partial task state. No checkpoints.
```

---

## 5. JSONB Usage Tradeoffs

### Current (Too Liberal)

| Field | Type | Problem |
|-------|------|---------|
| workflow.definition | JSONB | ✓ Good (schema evolves) |
| execution.input | JSONB | ✓ OK (variable user data) |
| execution.result | JSONB | ✓ OK (variable outcome) |
| task.input | JSONB | ✗ Problematic (repeats definition) |
| task.result | JSONB | ✗ Problematic (query/filter issues) |
| task.error | JSONB | ✗ Should be TEXT |

### Refined

```sql
-- Workflows: definition stays JSONB (flexible)
CREATE TABLE workflows (
  id UUID PRIMARY KEY,
  name VARCHAR(255) NOT NULL,
  definition JSONB NOT NULL,          -- ✓ flexible
  version INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL,
  status VARCHAR(50) NOT NULL
);

-- Executions: input/result stay JSONB (user-controlled)
CREATE TABLE executions (
  id UUID PRIMARY KEY,
  workflow_id UUID NOT NULL REFERENCES workflows(id),
  triggered_by VARCHAR(50) NOT NULL,  -- 'api'
  input JSONB,                        -- ✓ user params
  result JSONB,                       -- ✓ outcome data
  status VARCHAR(50) NOT NULL,        -- ✓ structured (enum)
  retry_count INTEGER DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  UNIQUE(execution_request_id)        -- for idempotency
);

-- Tasks: be explicit
CREATE TABLE tasks (
  id UUID PRIMARY KEY,
  execution_id UUID NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
  workflow_task_id VARCHAR(255) NOT NULL,  -- from workflow.definition
  name VARCHAR(255) NOT NULL,
  type VARCHAR(50) NOT NULL,               -- 'http', 'python'
  config JSONB NOT NULL,                   -- task configuration (url, timeout, etc)
  input JSONB,                             -- computed input for this task
  output JSONB,                            -- task result (not "result")
  error TEXT,                              -- ✓ not JSONB (queryable)
  status VARCHAR(50) NOT NULL,
  worker_id VARCHAR(255),
  retry_count INTEGER DEFAULT 0,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL,
  INDEX (execution_id),
  INDEX (status),
  INDEX (created_at DESC)
);
```

### Schema Evolution Strategy

**For workflow.definition**:
```python
# Keep definition as JSON, version incrementally
@dataclass
class WorkflowDefinition:
  version: int = 1
  tasks: List[TaskDef] = ...
  
  @staticmethod
  def from_json(data: dict) -> "WorkflowDefinition":
    v = data.get("version", 1)
    if v == 1:
      return WorkflowDefinitionV1.parse(data)
    elif v == 2:
      return WorkflowDefinitionV2.parse(data)
    else:
      raise ValueError(f"Unknown definition version {v}")
```

**For execution/task data**:
```
Assume input/output/config are opaque JSON.
Version them within the data if needed, or leave unversioned.
No schema migration required—flexible by design.
```

---

## 6. Execution State Machine Enforcement

### Simplified State Machine

**No library needed. Enum + validation:**

```python
from enum import Enum

class ExecutionStatus(str, Enum):
  PENDING = "PENDING"      # Created, not yet queued
  RUNNING = "RUNNING"      # Task executing
  SUCCESS = "SUCCESS"      # Complete, all tasks succeeded
  FAILED = "FAILED"        # Complete, task failed (no more retries)
  CANCELLED = "CANCELLED"  # User cancelled

class TaskStatus(str, Enum):
  PENDING = "PENDING"       # Waiting to execute
  RUNNING = "RUNNING"       # Currently executing
  SUCCESS = "SUCCESS"       # Completed successfully
  FAILED = "FAILED"         # Failed (will not retry)
  RETRYING = "RETRYING"     # Failed but will retry (intermediate state)

class Execution:
  def __init__(self, ...):
    self.status = ExecutionStatus.PENDING
  
  def mark_running(self):
    assert self.status == ExecutionStatus.PENDING, \
      f"Cannot run execution in {self.status} state"
    self.status = ExecutionStatus.RUNNING
    self.started_at = now()
    db.commit()
  
  def mark_success(self):
    assert self.status == ExecutionStatus.RUNNING, \
      f"Cannot succeed execution in {self.status} state"
    self.status = ExecutionStatus.SUCCESS
    self.completed_at = now()
    db.commit()
  
  def mark_failed(self, reason: str):
    assert self.status in [ExecutionStatus.PENDING, ExecutionStatus.RUNNING], \
      f"Cannot fail execution in {self.status} state"
    self.status = ExecutionStatus.FAILED
    self.error = reason
    self.completed_at = now()
    db.commit()

class Task:
  def mark_running(self):
    assert self.status == TaskStatus.PENDING, \
      f"Task already {self.status}"
    self.status = TaskStatus.RUNNING
    self.started_at = now()
  
  def mark_success(self, result: dict):
    assert self.status == TaskStatus.RUNNING
    self.status = TaskStatus.SUCCESS
    self.output = result
    self.completed_at = now()
  
  def mark_failed(self, error: str, retryable: bool = True):
    if retryable and self.retry_count < self.max_retries:
      self.status = TaskStatus.RETRYING
      self.retry_count += 1
    else:
      self.status = TaskStatus.FAILED
      self.error = error
    self.completed_at = now()
```

**Validation**: Assertions at state transitions. Simple, not a library.

---

## 7. Task Plugin Architecture

### Problem with Current Design

Creating TaskHandler interface + registry for 2-3 task types is overkill.

### Pragmatic MVP Approach

```python
# task.py: Simple, zero framework

TaskConfig = TypedDict('TaskConfig', {
  'url': str,           # for HTTP tasks
  'method': str,        # GET, POST
  'timeout': int,
  'headers': dict,      # optional
})

def execute_http_task(task: Task) -> dict:
  """Execute HTTP task."""
  config = task.config
  response = requests.request(
    method=config.get("method", "GET"),
    url=config["url"],
    json=task.input,
    timeout=config.get("timeout", 30),
    headers=config.get("headers", {})
  )
  response.raise_for_status()
  return response.json()

def execute_python_task(task: Task) -> dict:
  """Execute inline Python task."""
  code = task.config["code"]
  namespace = {"input": task.input}
  exec(code, namespace)
  return namespace.get("result", {})

TASK_EXECUTORS = {
  "http": execute_http_task,
  "python": execute_python_task,
}

def execute_task(task: Task) -> dict:
  """Dispatch to appropriate executor."""
  executor = TASK_EXECUTORS.get(task.type)
  if not executor:
    raise ValueError(f"Unknown task type: {task.type}")
  return executor(task)
```

### Future Extensibility (Phase 2+)

When you want a plugin system:

```python
# Make the map injectable
class TaskExecutor:
  def __init__(self, executors: Dict[str, Callable]):
    self.executors = executors
  
  def execute(self, task: Task) -> dict:
    executor = self.executors.get(task.type)
    if not executor:
      raise ValueError(f"Unknown task type: {task.type}")
    return executor(task)

# Usage
executor = TaskExecutor({
  "http": execute_http_task,
  "python": execute_python_task,
  # Add custom handlers at runtime
})
```

**Benefit**: No premature design. When you need plugins, add them. Until then: simple function dispatch.

---

## 8. Observability Simplification

### MVP: Structured Logging Only

```python
# logging.py
import json
import structlog
from datetime import datetime

def configure_logging():
  structlog.configure(
    processors=[
      structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
  )

# Usage in code
logger = structlog.get_logger()

# In worker
logger.info(
  "task_executed",
  execution_id=execution.id,
  task_id=task.id,
  task_name=task.name,
  status="SUCCESS",
  duration_ms=elapsed,
  output_size=len(json.dumps(task.output))
)

# In API
logger.info(
  "execution_created",
  execution_id=execution.id,
  workflow_id=workflow.id,
  triggered_by="api"
)

# In error
logger.error(
  "task_failed",
  execution_id=execution.id,
  task_id=task.id,
  error=str(e),
  traceback=traceback.format_exc()
)
```

**Output** (to stdout, captured by Docker):
```json
{"timestamp":"2026-05-08T14:30:00Z","level":"INFO","event":"task_executed","execution_id":"abc123","task_id":"def456","status":"SUCCESS","duration_ms":245}
{"timestamp":"2026-05-08T14:30:01Z","level":"ERROR","event":"task_failed","execution_id":"abc123","task_id":"def456","error":"Connection timeout"}
```

### What to Defer to Phase 2+

| Component | When | Why |
|-----------|------|-----|
| Distributed tracing | Phase 2 | Single worker doesn't need it |
| Trace ID propagation | Phase 2 | Useful at scale; add when needed |
| Prometheus metrics | Phase 2 | Focus on logging first |
| Sentry integration | Phase 2 | Structured logs + error field cover it |
| OpenTelemetry | Phase 2+ | Complexity tax not worth it yet |
| Custom dashboards | Phase 2+ | CSV export or simple query sufficient |
| Log aggregation | Phase 2+ | Local file rotation is fine initially |

### MVP Observability Stack

```
structlog (structured logging)
  ↓
JSON to stdout
  ↓
Docker logs / local file rotation
  ↓
Manual inspection via `docker logs` or `tail -f app.log`
```

When you scale: Forward logs to ELK / Datadog / CloudWatch.

---

## 9. Most Dangerous Architectural Risks

### Risk 1: Worker Stalling Without Recovery ⚠️ HIGH

**Issue**: Worker crashes or hangs; tasks stuck in RUNNING state forever.

**MVP Mitigation**:
- Add worker heartbeat to `tasks` table (30-second intervals)
- Simple cron job every minute checks for stalled tasks:
  ```python
  # In a separate lightweight service or scheduled task
  stalled = db.query(Task).filter(
    Task.status == "RUNNING",
    Task.updated_at < now() - 60 seconds
  )
  for task in stalled:
    task.status = "PENDING"  # Requeue
    task.retry_count += 1
  ```
- Add task timeout config (default 1 hour, configurable)
- Document: Workers must be monitored/restarted

**Phase 2**: Upgrade to worker registry + health checks.

---

### Risk 2: DAG Cycles / Invalid Definitions ⚠️ MEDIUM

**Issue**: Circular dependency hangs system. Bad workflow definition accepted.

**MVP Mitigation**:
- On workflow creation: validate DAG using topological sort
  ```python
  def validate_workflow_definition(definition: dict) -> bool:
    tasks = definition.get("tasks", [])
    task_ids = {t["id"] for t in tasks}
    
    for task in tasks:
      for dep in task.get("depends_on", []):
        if dep not in task_ids:
          raise ValueError(f"Dependency {dep} not found")
    
    # Simple cycle detection: DFS
    visited = set()
    rec_stack = set()
    
    def has_cycle(task_id):
      visited.add(task_id)
      rec_stack.add(task_id)
      
      task = next(t for t in tasks if t["id"] == task_id)
      for dep in task.get("depends_on", []):
        if dep not in visited:
          if has_cycle(dep):
            return True
        elif dep in rec_stack:
          return True
      
      rec_stack.remove(task_id)
      return False
    
    for task in tasks:
      if task["id"] not in visited:
        if has_cycle(task["id"]):
          raise ValueError("Circular dependency detected")
    
    return True
  ```

**Phase 2**: Advance execution validation, max DAG depth.

---

### Risk 3: Database Becomes Bottleneck ⚠️ MEDIUM

**Issue**: Too many workers hammering DB; connection pool exhausted.

**MVP Mitigation**:
- Single worker initially (no pooling stress)
- Document: Add read replicas before scaling to 10+ workers
- Use connection pooling (SQLAlchemy default)
- Index on `(execution_id, status)` for task queries

**Phase 2**: Connection pooling tuning, read replicas, caching layer.

---

### Risk 4: Unbounded Task Retries ⚠️ MEDIUM

**Issue**: Task keeps retrying, backoff grows exponentially, system slows.

**MVP Mitigation**:
- Enforce MAX_RETRIES constant (default 3)
- Enforce MAX_BACKOFF_SECONDS (default 300)
- Validation in task config:
  ```python
  assert task.config.get("max_retries", 3) <= 10, "Too many retries"
  assert task.config.get("max_backoff_seconds", 300) <= 3600, "Backoff too long"
  ```

**Phase 2**: Exponential backoff with jitter, dead letter queue.

---

### Risk 5: Lost Execution State on Worker Crash ⚠️ LOW (Mitigated)

**Issue**: Worker in middle of task; DB not updated; state lost.

**MVP Mitigation**:
- Task status is source of truth in DB
- On crash: stalled task detection (Risk 1) recovers
- Document: Tasks must be idempotent

**Phase 2**: Transactional outbox pattern.

---

### Risk 6: Distributed Locking Not Addressed 🟡 LOW PRIORITY

**Issue**: Multiple workers scheduling jobs (not in MVP) could conflict.

**MVP Mitigation**:
- Scheduling deferred to Phase 2
- No distributed lock needed yet

**Phase 2**: Use DB advisory locks or Redis for coordination.

---

### Risk 7: Accidental "Hot Loop" in Worker ⚠️ MEDIUM

**Issue**: Bug causes worker to requeue task infinitely; Redis grows.

**MVP Mitigation**:
- Add queue depth monitoring (simple Redis LEN command)
- Add max task executions per workflow (e.g., max 1000 tasks)
- Log requeue events:
  ```python
  logger.info("task_requeued", 
    task_id=task.id, 
    retry_count=task.retry_count,
    next_run_at=delayed_until)
  ```

**Phase 2**: Queue monitoring dashboard, alerts.

---

### Risk 8: No Clear Failure Mode Definition 🟡 LOW

**Issue**: When does execution give up? When does it alert?

**MVP Mitigation**:
- Document execution failure behavior:
  - Task fails with no retries → execution FAILED (terminal)
  - Execution FAILED → emit log event
  - Monitor logs for ERROR level manually
- Add `error_count` to Execution:
  ```
  If error_count > 0, mark execution as requiring attention
  Manual inspection or simple alert rule
  ```

**Phase 2**: Alert system, error aggregation.

---

### Acceptable Technical Debt for MVP

✓ Single worker (no horizontal scaling yet)  
✓ No distributed tracing (logs sufficient)  
✓ No metrics collection (logs sufficient)  
✓ No scheduling (async API execution only)  
✓ No sub-workflows (sequential only)  
✓ No conditional branching (all tasks execute)  
✓ No manual approval steps  
✓ No priority queues  

### Dangerous Technical Debt to Avoid

✗ No idempotency consideration (fix now)  
✗ No worker crash recovery (fix now)  
✗ No DAG validation (fix now)  
✗ No state machine enforcement (fix now)  
✗ No task timeout (fix now)  
✗ No structured logging (fix now)  

---

## 10. Recommended Immediate Next Step

### Milestone 1: "End-to-End Execution" (Week 1)

**Deliverable**: Single workflow → single task → execution success  

**Exact sequence**:

1. **Setup** (Day 1)
   ```bash
   mkdir -p aetherflow
   python -m venv venv
   pip install fastapi uvicorn sqlalchemy alembic psycopg2 pydantic redis rq structlog
   
   # Create structure
   src/aetherflow/
   ├── __init__.py
   ├── models.py           # Models only, no ORM yet
   ├── schema.py           # Pydantic schemas
   ├── api.py              # Routes
   ├── service.py          # Logic
   ├── worker.py           # Worker loop
   ├── config.py           # Settings
   └── logging.py          # Logging setup
   ```

2. **Database** (Day 1-2)
   ```
   - Define Workflow, Execution, Task SQLAlchemy models
   - Create Alembic migration
   - docker-compose.yml with postgres + redis
   - Migrate schema
   ```

3. **API** (Day 2-3)
   ```
   POST /workflows
   GET /workflows/{id}
   POST /workflows/{id}/execute
   GET /executions/{id}
   ```

4. **Service Layer** (Day 3-4)
   ```
   - create_workflow(name, definition)
   - create_execution(workflow_id, input)
   - validate_definition(definition) → check DAG
   - queue_next_tasks(execution_id)
   ```

5. **Worker** (Day 4-5)
   ```
   - Connect to Redis
   - Dequeue task
   - execute_task() stub (always return success)
   - Update DB
   - Queue next task
   - Handle graceful shutdown
   ```

6. **Logging** (Day 5)
   ```
   - structlog setup
   - Log all major events
   - JSON output to stdout
   ```

7. **Test** (Day 5-6)
   ```
   - Docker Compose start
   - curl POST /workflows
   - curl POST /execute
   - Observe worker picking up task
   - View JSON logs
   ```

**Success Criteria**:
```
1. Workflow stored in DB
2. Execution created on API call
3. Task queued to Redis
4. Worker dequeued task
5. Task marked SUCCESS in DB
6. Structured logs output JSON
7. All in Docker Compose locally
8. No external dependencies
```

**Time estimate**: 1 week (solo engineer)

---

### After Milestone 1: What Not to Do

❌ Don't add scheduling  
❌ Don't add event sourcing  
❌ Don't add distributed tracing  
❌ Don't add metrics  
❌ Don't add WebSocket logs  
❌ Don't add task handler registry (keep dispatch simple)  
❌ Don't add middleware complexity  
❌ Don't use dependency injection framework  

### After Milestone 1: What to Validate

✓ Can you add a new task type easily?  
✓ Are logs useful for debugging?  
✓ Is the DB schema sufficient?  
✓ Can you trace an execution through all layers?  
✓ What's missing for multi-task workflows?  

---

## Summary: Key Changes from Original Architecture

| Area | Original | Pragmatic MVP | Benefit |
|------|----------|---------------|---------|
| **Structure** | domain/app/infra | flat (models/service/api) | Simpler navigation |
| **Scope** | Jobs + events | Executions only | 50% less code |
| **DTOs** | Separate layer | Use models directly | No translation |
| **State Machine** | Conceptual + library | Enum + assertions | Simple validation |
| **Retries** | Complex saga | Idempotent requeue | MVP-safe |
| **Logging** | OpenTelemetry | structlog JSON | Effective now |
| **Observability** | Metrics + tracing | Logs only | Phase 2 upgrade |
| **Task Execution** | Registry pattern | Simple dispatch | Extensible later |
| **JSONB** | Liberal | Targeted | Better queries |
| **Timeline** | 8 weeks | 4 weeks | Solo feasible |

---

## Final Recommendation

**This refined MVP is production-ready in spirit while being pragmatically simple to implement.** Build it. Get it working. Ship it. Then measure where you actually need complexity.

The original architecture was 80% right. This refinement removes the unnecessary 20% for MVP without sacrificing operational clarity or future extensibility.

---

**Next Action**: Start Milestone 1 scaffolding. Create `src/aetherflow/models.py` with Workflow, Execution, Task classes. Time box to 2 hours.

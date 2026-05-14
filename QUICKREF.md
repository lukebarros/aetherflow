# AetherFlow Quick Reference

## Initial Setup (One-time)

```bash
# Copy environment
cp .env.example .env

# Start services
docker-compose up -d

# Generate migration
docker-compose exec api alembic revision --autogenerate -m "Initial schema"

# Apply migration
docker-compose exec api alembic upgrade head
```

## Daily Development

```bash
# Start all services (API, database, Redis, worker)
docker-compose up -d

# Watch API logs
docker-compose logs -f api

# Watch worker logs  
docker-compose logs -f worker

# Stop services
docker-compose down

# Stop specific service
docker-compose stop api
docker-compose stop worker
```

## Database Commands

```bash
# Connect to PostgreSQL
docker-compose exec postgres psql -U aetherflow -d aetherflow

# List tables
\dt

# View schema
\d workflows
\d executions
\d tasks

# Query data
SELECT COUNT(*) FROM workflows;
SELECT * FROM executions ORDER BY created_at DESC LIMIT 5;

# Exit
\q
```

## API Testing

```bash
# Create a workflow
WORKFLOW_ID=$(curl -s -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test Workflow",
    "definition": {
      "version": 1,
      "tasks": [
        {
          "id": "task_1",
          "type": "http",
          "name": "HTTP Task",
          "config": {"url": "https://httpbin.org/get"},
          "depends_on": []
        }
      ]
    }
  }' | jq -r '.id')

# List workflows
curl http://localhost:8000/workflows | jq '.items[].name'

# Execute workflow
EXECUTION_ID=$(curl -s -X POST http://localhost:8000/workflows/$WORKFLOW_ID/execute \
  -H "Content-Type: application/json" \
  -d '{}' | jq -r '.id')

# Get execution status (worker processes automatically)
curl http://localhost:8000/executions/$EXECUTION_ID | jq '{status: .status, tasks: [.tasks[].status]}'

# View task output
curl http://localhost:8000/executions/$EXECUTION_ID | jq '.tasks[0].output'

# Health check
curl http://localhost:8000/health | jq '.'
```

## Migration Commands

```bash
# Create new migration
docker-compose exec api alembic revision --autogenerate -m "Description"

# View current migration
docker-compose exec api alembic current

# Apply all pending migrations
docker-compose exec api alembic upgrade head

# Downgrade one migration
docker-compose exec api alembic downgrade -1

# See all migrations
docker-compose exec api alembic history
```

## API Testing

```bash
# Health check
curl http://localhost:8000/health

# View documentation
open http://localhost:8000/docs

# Create workflow (example)
curl -X POST http://localhost:8000/workflows \
  -H "Content-Type: application/json" \
  -d '{"name":"test","definition":{"tasks":[]}}'
```

## Docker Commands

```bash
# View logs
docker-compose logs -f

# View specific service logs
docker-compose logs -f api
docker-compose logs -f postgres
docker-compose logs -f redis

# Restart services
docker-compose restart

# Stop and remove everything
docker-compose down

# Full reset (delete data)
docker-compose down -v
docker-compose up -d
```

## Debugging

```bash
# Check service status
docker-compose ps

# View detailed logs
docker-compose logs --tail=100 api

# Execute command in container
docker-compose exec api python -c "from aetherflow.models import Workflow; print('OK')"

# Check database connection
docker-compose exec api python -c "from sqlalchemy import create_engine, text; engine = create_engine('postgresql://aetherflow:aetherflow_dev@postgres:5432/aetherflow'); conn = engine.connect(); result = conn.execute(text('SELECT 1')); print('DB OK:', result.fetchone())"

# View Redis queue
docker-compose exec redis redis-cli
> KEYS *
> LLEN aetherflow_tasks
```

## File Locations

```
Configuration:
  env variables → .env
  code config  → src/aetherflow/config.py
  app settings → docker-compose.yml

Database:
  schema       → alembic/versions/*.py
  models       → src/aetherflow/models.py
  connection   → src/aetherflow/main.py

Application:
  API entry    → src/aetherflow/main.py
  Logging      → src/aetherflow/logging.py
  Endpoints    → src/aetherflow/api.py (to create)
  Logic        → src/aetherflow/service.py (to create)
  Queue        → src/aetherflow/queue.py (to create)
  Worker       → src/aetherflow/worker.py (to create)
```

## Common Issues

**Port already in use**
```bash
# Kill existing process
lsof -ti:8000 | xargs kill -9
# Or change port in docker-compose.yml
```

**Database connection refused**
```bash
# Wait for PostgreSQL to start
docker-compose logs postgres | grep "ready to accept"

# Or restart
docker-compose restart postgres
```

**Migration fails**
```bash
# Check migration syntax
cat alembic/versions/001_*.py

# Downgrade and retry
docker-compose exec api alembic downgrade base
docker-compose exec api alembic upgrade head
```

**Redis not responding**
```bash
docker-compose restart redis
docker-compose exec redis redis-cli ping
```

## Performance Tips

```bash
# Check table sizes
SELECT schemaname, tablename, pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) 
FROM pg_tables 
WHERE schemaname = 'public' 
ORDER BY pg_total_relation_size(schemaname||'.'||tablename) DESC;

# Check slow queries (PostgreSQL must be running with log_statement='all')
SELECT query, mean_exec_time FROM pg_stat_statements ORDER BY mean_exec_time DESC LIMIT 10;

# Check connection pool
SELECT datname, count(*) FROM pg_stat_activity GROUP BY datname;
```

## Next Phases

**Phase 1.2**: Generate Alembic migration, verify schema
**Phase 1.3**: Create API endpoints (CRUD)
**Phase 1.4**: Create service layer (business logic)
**Phase 1.5**: Create worker and integration test

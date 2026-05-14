"""Business logic and service layer."""

from typing import Optional, Dict, Any
from uuid import uuid4
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from aetherflow.models import Workflow, Execution, Task, ExecutionStatus, TaskStatus
from aetherflow.logging import get_logger

logger = get_logger(__name__)

# Import queue only if available (avoid circular imports)
def get_queue():
    """Lazy import to avoid circular imports."""
    try:
        from aetherflow.queue import task_queue
        return task_queue
    except ImportError:
        return None


def create_workflow(
    db: Session,
    name: str,
    definition: Dict[str, Any],
    description: Optional[str] = None,
) -> Workflow:
    """
    Create a new workflow.
    
    Args:
        db: Database session
        name: Workflow name
        definition: Workflow DAG definition (dict)
        description: Optional description
        
    Returns:
        Created Workflow object
    """
    workflow = Workflow(
        id=uuid4(),
        name=name,
        description=description,
        definition=definition,
        version=1,
        status="ACTIVE",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(workflow)
    db.commit()
    db.refresh(workflow)
    
    logger.info(
        "workflow_created",
        workflow_id=str(workflow.id),
        name=name,
    )
    
    return workflow


def list_workflows(
    db: Session,
    skip: int = 0,
    limit: int = 10,
) -> tuple[list[Workflow], int]:
    """
    List workflows with pagination.
    
    Args:
        db: Database session
        skip: Number of workflows to skip (for pagination)
        limit: Maximum number of workflows to return
        
    Returns:
        Tuple of (workflows list, total count)
    """
    query = db.query(Workflow)
    total = query.count()
    
    workflows = query.order_by(desc(Workflow.created_at)).offset(skip).limit(limit).all()
    
    logger.info(
        "workflows_listed",
        total=total,
        skip=skip,
        limit=limit,
        returned=len(workflows),
    )
    
    return workflows, total


def validate_workflow_definition(definition: Dict[str, Any]) -> bool:
    """
    Validate workflow DAG definition.
    
    Checks for:
    - All task IDs are unique
    - All dependencies reference existing tasks
    - No circular dependencies
    
    Args:
        definition: Workflow definition (dict)
        
    Returns:
        True if valid
        
    Raises:
        ValueError: If definition is invalid
    """
    tasks = definition.get("tasks", [])
    if not tasks:
        raise ValueError("Workflow definition must have at least one task")
    
    # Check unique task IDs
    task_ids = {t["id"] for t in tasks}
    if len(task_ids) != len(tasks):
        raise ValueError("Duplicate task IDs in definition")
    
    # Check dependencies exist
    for task in tasks:
        for dep in task.get("depends_on", []):
            if dep not in task_ids:
                raise ValueError(f"Task dependency '{dep}' not found in definition")
    
    # Check for cycles (DFS)
    visited = set()
    rec_stack = set()
    
    def has_cycle(task_id: str) -> bool:
        visited.add(task_id)
        rec_stack.add(task_id)
        
        task = next((t for t in tasks if t["id"] == task_id), None)
        if not task:
            return False
        
        for dep in task.get("depends_on", []):
            if dep not in visited:
                if has_cycle(dep):
                    return True
            elif dep in rec_stack:
                return True
        
        rec_stack.discard(task_id)
        return False
    
    for task in tasks:
        if task["id"] not in visited:
            if has_cycle(task["id"]):
                raise ValueError("Circular dependency detected in workflow")
    
    logger.info("workflow_definition_valid", task_count=len(tasks))
    return True


def create_execution(
    db: Session,
    workflow_id: Any,
    input_data: Optional[Dict[str, Any]] = None,
    execution_request_id: Optional[str] = None,
) -> Execution:
    """
    Create a new execution of a workflow.
    
    Args:
        db: Database session
        workflow_id: ID of the workflow to execute
        input_data: Input parameters for execution
        execution_request_id: Idempotency key
        
    Returns:
        Created Execution object
        
    Raises:
        ValueError: If workflow not found or invalid
    """
    # Load workflow
    workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not workflow:
        raise ValueError(f"Workflow {workflow_id} not found")
    
    # Check for existing execution (idempotency)
    if execution_request_id:
        existing = db.query(Execution).filter(
            Execution.execution_request_id == execution_request_id
        ).first()
        if existing:
            logger.info(
                "execution_already_exists",
                execution_id=str(existing.id),
                execution_request_id=execution_request_id,
            )
            return existing
    
    # Validate workflow definition
    validate_workflow_definition(workflow.definition)
    
    # Create execution
    execution = Execution(
        id=uuid4(),
        workflow_id=workflow_id,
        execution_request_id=execution_request_id,
        triggered_by="api",
        status=ExecutionStatus.PENDING,
        input=input_data or {},
        trace_id=str(uuid4()),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(execution)
    db.flush()  # Get the ID without committing yet
    
    # Create initial tasks (all with no dependencies resolved yet)
    tasks_def = workflow.definition.get("tasks", [])
    for position, task_def in enumerate(tasks_def):
        task = Task(
            id=uuid4(),
            execution_id=execution.id,
            workflow_task_id=task_def["id"],
            name=task_def.get("name", task_def["id"]),
            type=task_def.get("type", "http"),
            config=task_def.get("config", {}),
            input=task_def.get("input"),
            status=TaskStatus.PENDING,
            retry_count=0,
            max_retries=task_def.get("max_retries", 3),
            depends_on=task_def.get("depends_on", []),
            position=position,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(task)
    
    db.commit()
    db.refresh(execution)
    
    # Enqueue initial tasks (with no dependencies)
    enqueue_initial_tasks(db, execution.id)
    
    logger.info(
        "execution_created",
        execution_id=str(execution.id),
        workflow_id=str(workflow_id),
        task_count=len(tasks_def),
        trace_id=execution.trace_id,
    )
    
    return execution


def get_execution(db: Session, execution_id: Any) -> Optional[Execution]:
    """
    Get an execution with all its tasks.
    
    Args:
        db: Database session
        execution_id: ID of the execution
        
    Returns:
        Execution object with tasks, or None if not found
    """
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        logger.warning("execution_not_found", execution_id=str(execution_id))
        return None
    
    # Ensure tasks are loaded
    _ = execution.tasks
    
    return execution


def get_execution_tasks(db: Session, execution_id: Any) -> list[Task]:
    """
    Get all tasks for an execution.
    
    Args:
        db: Database session
        execution_id: ID of the execution
        
    Returns:
        List of Task objects
    """
    tasks = db.query(Task).filter(Task.execution_id == execution_id).order_by(Task.position).all()
    return tasks


def enqueue_initial_tasks(db: Session, execution_id: Any) -> int:
    """
    Enqueue all ready tasks (with no dependencies) for an execution.
    
    Args:
        db: Database session
        execution_id: ID of the execution
        
    Returns:
        Number of tasks enqueued
    """
    queue = get_queue()
    if not queue:
        logger.warning("queue_not_available", execution_id=str(execution_id))
        return 0
    
    # Get all tasks with no dependencies
    tasks = db.query(Task).filter(
        Task.execution_id == execution_id,
        Task.status == TaskStatus.PENDING,
    ).all()
    
    enqueued_count = 0
    for task in tasks:
        if not task.depends_on:  # Only enqueue tasks with no dependencies
            success = queue.enqueue_task(
                task_id=task.id,
                execution_id=execution_id,
                workflow_task_id=task.workflow_task_id,
                task_type=task.type,
                config=task.config,
                depends_on=task.depends_on,
            )
            if success:
                enqueued_count += 1
    
    logger.info(
        "initial_tasks_enqueued",
        execution_id=str(execution_id),
        count=enqueued_count,
    )
    return enqueued_count


def update_execution_status(
    db: Session,
    execution_id: Any,
    status: ExecutionStatus,
    result: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
) -> Optional[Execution]:
    """
    Update execution status.
    
    Args:
        db: Database session
        execution_id: ID of the execution
        status: New status
        result: Result data
        error: Error message
        
    Returns:
        Updated Execution object
    """
    execution = db.query(Execution).filter(Execution.id == execution_id).first()
    if not execution:
        logger.warning("execution_not_found_for_update", execution_id=str(execution_id))
        return None
    
    execution.status = status
    execution.updated_at = datetime.utcnow()
    
    if status == ExecutionStatus.RUNNING:
        execution.started_at = datetime.utcnow()
    elif status in (ExecutionStatus.SUCCESS, ExecutionStatus.FAILED):
        execution.completed_at = datetime.utcnow()
    
    if result:
        execution.result = result
    if error:
        execution.error = error
    
    db.commit()
    logger.info(
        "execution_status_updated",
        execution_id=str(execution_id),
        status=status,
    )
    return execution


def check_execution_completion(db: Session, execution_id: Any) -> Optional[str]:
    """
    Check if all tasks in an execution are complete.
    Returns the status: SUCCESS if all succeeded, FAILED if any failed, None if still running.
    
    Args:
        db: Database session
        execution_id: ID of the execution
        
    Returns:
        ExecutionStatus string or None if still running
    """
    tasks = db.query(Task).filter(Task.execution_id == execution_id).all()
    if not tasks:
        return None
    
    statuses = [t.status for t in tasks]
    
    # If any failed, execution failed
    if TaskStatus.FAILED in statuses:
        return ExecutionStatus.FAILED
    
    # If all succeeded, execution succeeded
    if all(s == TaskStatus.SUCCESS for s in statuses):
        return ExecutionStatus.SUCCESS
    
    # Otherwise still running
    return None

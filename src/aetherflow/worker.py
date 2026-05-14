"""Task worker service - executes queued tasks."""

import asyncio
import httpx
import json
import signal
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4

from sqlalchemy.orm import Session
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from aetherflow.config import settings
from aetherflow.models import Task, TaskStatus, Execution, ExecutionStatus
from aetherflow.queue import task_queue
from aetherflow.logging import get_logger

logger = get_logger(__name__)


class TaskWorker:
    """Worker that processes tasks from the queue."""
    
    def __init__(self):
        """Initialize worker with database connection."""
        self.engine = create_engine(
            settings.database_url,
            pool_size=10,
            max_overflow=20,
        )
        self.SessionLocal = sessionmaker(
            autocommit=False,
            autoflush=False,
            bind=self.engine,
        )
        self.running = False
        self.worker_id = str(uuid4())[:8]
        logger.info("worker_initialized", worker_id=self.worker_id)
    
    def get_db(self) -> Session:
        """Get database session."""
        return self.SessionLocal()
    
    async def execute_http_task(
        self,
        config: Dict[str, Any],
        task_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute an HTTP task.
        
        Args:
            config: Task config with 'url' and optional method/headers/body
            task_input: Optional input data for the task
            
        Returns:
            Task output (response status, body, headers)
        """
        url = config.get("url")
        if not url:
            raise ValueError("HTTP task requires 'url' in config")
        
        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        body = config.get("body") or task_input
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.request(
                    method=method,
                    url=url,
                    json=body if body else None,
                    headers=headers,
                )
            
            result = {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response.text,
            }
            
            # Treat 4xx/5xx as task failure
            if response.status_code >= 400:
                raise Exception(f"HTTP {response.status_code}: {response.text[:200]}")
            
            return result
        except httpx.TimeoutException as e:
            raise Exception(f"HTTP request timeout: {str(e)}")
        except Exception as e:
            raise Exception(f"HTTP request failed: {str(e)}")
    
    async def execute_python_task(
        self,
        config: Dict[str, Any],
        task_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a Python eval task.
        
        Args:
            config: Task config with 'code' to execute
            task_input: Input data available as 'input' in execution context
            
        Returns:
            Task output (code return value)
        """
        code = config.get("code")
        if not code:
            raise ValueError("Python task requires 'code' in config")
        
        # Create safe execution context
        exec_globals = {
            "input": task_input or {},
            "__builtins__": {"len": len, "str": str, "int": int, "float": float, "dict": dict, "list": list},
        }
        
        try:
            exec(code, exec_globals)
            result = exec_globals.get("result", None)
            return {"result": result}
        except Exception as e:
            raise Exception(f"Python execution failed: {str(e)}")
    
    async def execute_task(
        self,
        task_id: str,
        execution_id: str,
        task_type: str,
        config: Dict[str, Any],
        task_input: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task based on its type.
        
        Args:
            task_id: UUID of the task
            execution_id: UUID of the execution
            task_type: Type of task (http, python, etc)
            config: Task configuration
            task_input: Optional input data
            
        Returns:
            Task output
            
        Raises:
            Exception: If execution fails
        """
        logger.info(
            "task_execution_started",
            task_id=task_id,
            type=task_type,
            worker_id=self.worker_id,
        )
        
        try:
            if task_type == "http":
                output = await self.execute_http_task(config, task_input)
            elif task_type == "python":
                output = await self.execute_python_task(config, task_input)
            else:
                raise ValueError(f"Unknown task type: {task_type}")
            
            logger.info(
                "task_execution_success",
                task_id=task_id,
                type=task_type,
                worker_id=self.worker_id,
            )
            return output
        except Exception as e:
            logger.error(
                "task_execution_failed",
                task_id=task_id,
                type=task_type,
                error=str(e),
                worker_id=self.worker_id,
            )
            raise
    
    def update_task_status(
        self,
        db: Session,
        task_id: str,
        status: TaskStatus,
        output: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
    ) -> None:
        """Update task status in database."""
        task = db.query(Task).filter(Task.id == task_id).first()
        if not task:
            logger.warning("task_not_found_for_update", task_id=task_id)
            return
        
        task.status = status
        task.worker_id = self.worker_id
        task.updated_at = datetime.utcnow()
        
        if status == TaskStatus.RUNNING:
            task.started_at = datetime.utcnow()
        elif status in (TaskStatus.SUCCESS, TaskStatus.FAILED):
            task.completed_at = datetime.utcnow()
        
        if output:
            task.output = output
        if error:
            task.error = error
            task.retry_count += 1
        
        db.commit()
        logger.info(
            "task_status_updated",
            task_id=task_id,
            status=status,
            worker_id=self.worker_id,
        )
    
    def get_pending_tasks(self, db: Session, execution_id: str) -> list[Task]:
        """Get all pending tasks for an execution that are ready to run."""
        tasks = db.query(Task).filter(
            Task.execution_id == execution_id,
            Task.status == TaskStatus.PENDING,
        ).order_by(Task.position).all()
        
        # Filter to only tasks with no pending dependencies
        ready_tasks = []
        for task in tasks:
            # Check if all dependencies are complete
            if not task.depends_on:
                # No dependencies, ready to run
                ready_tasks.append(task)
            else:
                # Check dependency status
                dep_tasks = db.query(Task).filter(
                    Task.execution_id == execution_id,
                    Task.workflow_task_id.in_(task.depends_on),
                ).all()
                
                if all(dt.status == TaskStatus.SUCCESS for dt in dep_tasks):
                    ready_tasks.append(task)
        
        return ready_tasks
    
    async def process_task(self, task: Dict[str, Any]) -> bool:
        """
        Process a single task.
        
        Args:
            task: Task message from queue
            
        Returns:
            True if successful, False if should retry
        """
        task_id = task["task_id"]
        execution_id = task["execution_id"]
        task_type = task["type"]
        config = task["config"]
        
        db = self.get_db()
        try:
            # Update task status to RUNNING
            self.update_task_status(db, task_id, TaskStatus.RUNNING)
            
            # Execute task
            output = await self.execute_task(
                task_id=task_id,
                execution_id=execution_id,
                task_type=task_type,
                config=config,
                task_input=task.get("input"),
            )
            
            # Mark as successful
            self.update_task_status(
                db,
                task_id,
                TaskStatus.SUCCESS,
                output=output,
            )
            
            # Check if we should enqueue dependent tasks
            self.enqueue_dependent_tasks(db, execution_id, task["workflow_task_id"])
            
            return True
        except Exception as e:
            # Get retry count
            task_obj = db.query(Task).filter(Task.id == task_id).first()
            if task_obj and task_obj.retry_count < task_obj.max_retries:
                # Retry
                self.update_task_status(
                    db,
                    task_id,
                    TaskStatus.RETRYING,
                    error=str(e),
                )
                # Requeue task
                task_queue.enqueue_task(
                    task_id=task_id,
                    execution_id=execution_id,
                    workflow_task_id=task["workflow_task_id"],
                    task_type=task_type,
                    config=config,
                )
                return True
            else:
                # Failed permanently
                self.update_task_status(
                    db,
                    task_id,
                    TaskStatus.FAILED,
                    error=str(e),
                )
                return False
        finally:
            db.close()
    
    def enqueue_dependent_tasks(
        self,
        db: Session,
        execution_id: str,
        completed_task_id: str,
    ) -> None:
        """
        Check for tasks that depend on the completed task and enqueue them.
        
        Args:
            db: Database session
            execution_id: UUID of the execution
            completed_task_id: Workflow task ID that just completed
        """
        # Find all tasks that depend on this one
        dependent_tasks = db.query(Task).filter(
            Task.execution_id == execution_id,
            Task.status == TaskStatus.PENDING,
        ).all()
        
        for task in dependent_tasks:
            if completed_task_id in task.depends_on:
                # Check if all dependencies are now complete
                dep_tasks = db.query(Task).filter(
                    Task.execution_id == execution_id,
                    Task.workflow_task_id.in_(task.depends_on),
                ).all()
                
                if all(dt.status == TaskStatus.SUCCESS for dt in dep_tasks):
                    # All dependencies met, enqueue this task
                    task_queue.enqueue_task(
                        task_id=task.id,
                        execution_id=execution_id,
                        workflow_task_id=task.workflow_task_id,
                        task_type=task.type,
                        config=task.config,
                        depends_on=task.depends_on,
                    )
                    logger.info(
                        "dependent_task_enqueued",
                        task_id=str(task.id),
                        workflow_task_id=task.workflow_task_id,
                        completed_task=completed_task_id,
                    )
    
    async def start(self) -> None:
        """Start the worker event loop."""
        self.running = True
        logger.info("worker_started", worker_id=self.worker_id)
        
        # Handle signals for graceful shutdown
        def signal_handler(sig, frame):
            logger.info("worker_shutdown_signal", worker_id=self.worker_id)
            self.running = False
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        # Main event loop
        while self.running:
            try:
                # Try to get a task from queue (blocking with timeout)
                task = task_queue.dequeue_task(timeout=5)
                
                if task:
                    await self.process_task(task)
                else:
                    # No task available, wait a bit
                    await asyncio.sleep(1)
            except Exception as e:
                logger.error("worker_error", error=str(e), worker_id=self.worker_id)
                await asyncio.sleep(5)
        
        logger.info("worker_stopped", worker_id=self.worker_id)


async def run_worker() -> None:
    """Entry point for running the worker."""
    worker = TaskWorker()
    
    # Check Redis connectivity
    if not task_queue.health_check():
        logger.error("redis_not_available")
        return
    
    try:
        await worker.start()
    except KeyboardInterrupt:
        logger.info("worker_interrupted")

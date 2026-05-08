"""SQLAlchemy domain models."""

from datetime import datetime
from enum import Enum
from typing import Optional, List
import uuid

from sqlalchemy import Column, String, DateTime, JSON, Integer, ForeignKey, Index, Enum as SQLEnum
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, Mapped
from sqlalchemy.dialects.postgresql import UUID

Base = declarative_base()


class ExecutionStatus(str, Enum):
    """Execution lifecycle status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    RETRYING = "RETRYING"
    SKIPPED = "SKIPPED"


class Workflow(Base):
    """
    Workflow definition.

    Represents a DAG of tasks that can be executed.
    Immutable once created; new versions should be new records.
    """
    __tablename__ = "workflows"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False, index=True)
    description = Column(String(1000))

    # Workflow definition as JSON
    # Example structure:
    # {
    #   "version": 1,
    #   "tasks": [
    #     {"id": "task_1", "type": "http", "config": {...}, "depends_on": []},
    #     {"id": "task_2", "type": "http", "config": {...}, "depends_on": ["task_1"]}
    #   ]
    # }
    definition = Column(JSON, nullable=False)

    version = Column(Integer, nullable=False, default=1)
    status = Column(String(50), nullable=False, default="ACTIVE")  # ACTIVE, ARCHIVED

    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    executions: Mapped[List["Execution"]] = relationship("Execution", back_populates="workflow", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_workflows_status", "status"),
        Index("idx_workflows_created_at", "created_at"),
    )


class Execution(Base):
    """
    Single execution of a workflow.

    Tracks the execution lifecycle, input, and result of a workflow run.
    """
    __tablename__ = "executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    workflow_id = Column(UUID(as_uuid=True), ForeignKey("workflows.id"), nullable=False, index=True)

    # Idempotency key: prevents duplicate executions
    execution_request_id = Column(String(255), unique=True, nullable=True, index=True)

    # Who triggered this execution
    triggered_by = Column(String(50), nullable=False, default="api")  # api, scheduler, etc

    # Execution state
    status = Column(SQLEnum(ExecutionStatus), nullable=False, default=ExecutionStatus.PENDING, index=True)

    # Input context passed to execution
    input = Column(JSON)

    # Final result of execution
    result = Column(JSON)

    # Error message if failed
    error = Column(String(1000))

    # For distributed tracing and debugging
    trace_id = Column(String(255), unique=True, nullable=False, default=lambda: str(uuid.uuid4()))

    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    workflow: Mapped["Workflow"] = relationship("Workflow", back_populates="executions")
    tasks: Mapped[List["Task"]] = relationship("Task", back_populates="execution", cascade="all, delete-orphan")

    # Enum access for convenience
    ExecutionStatus = ExecutionStatus

    __table_args__ = (
        Index("idx_executions_workflow_id", "workflow_id"),
        Index("idx_executions_status", "status"),
        Index("idx_executions_created_at", "created_at"),
        Index("idx_executions_trace_id", "trace_id"),
        Index("idx_executions_completed_at", "completed_at"),
    )


class Task(Base):
    """
    Single task within an execution.

    Represents a unit of work in the workflow DAG.
    """
    __tablename__ = "tasks"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    execution_id = Column(UUID(as_uuid=True), ForeignKey("executions.id", ondelete="CASCADE"), nullable=False, index=True)

    # Reference to task definition in workflow
    workflow_task_id = Column(String(255), nullable=False)

    # Display name
    name = Column(String(255), nullable=False)

    # Task type determines execution handler
    type = Column(String(50), nullable=False)  # http, python, etc

    # Task configuration (url, method, code, etc)
    config = Column(JSON, nullable=False)

    # Computed input for this task
    input = Column(JSON)

    # Task output/result
    output = Column(JSON)

    # Error message if task failed
    error = Column(String(1000))

    # Task execution state
    status = Column(SQLEnum(TaskStatus), nullable=False, default=TaskStatus.PENDING, index=True)

    # Which worker is executing this task
    worker_id = Column(String(255), index=True)

    # Retry tracking
    retry_count = Column(Integer, nullable=False, default=0)
    max_retries = Column(Integer, nullable=False, default=3)

    # Dependency tracking (task IDs this task depends on)
    depends_on = Column(JSON, nullable=False, default=list)  # List of task IDs

    # Position in execution order
    position = Column(Integer, nullable=False, default=0)

    # Timing
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    heartbeat_at = Column(DateTime(timezone=True))  # Worker heartbeat for crash detection
    created_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow)
    updated_at = Column(DateTime(timezone=True), nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    execution: Mapped["Execution"] = relationship("Execution", back_populates="tasks")

    # Enum access for convenience
    TaskStatus = TaskStatus

    __table_args__ = (
        Index("idx_tasks_execution_id", "execution_id"),
        Index("idx_tasks_status", "status"),
        Index("idx_tasks_worker_id", "worker_id"),
        Index("idx_tasks_created_at", "created_at"),
    )

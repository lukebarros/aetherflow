"""Pydantic schemas for API request/response validation."""

from datetime import datetime
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field
from uuid import UUID


class WorkflowCreate(BaseModel):
    """Schema for creating a new workflow."""
    name: str = Field(..., min_length=1, max_length=255, description="Workflow name")
    description: Optional[str] = Field(None, max_length=1000, description="Workflow description")
    definition: Dict[str, Any] = Field(..., description="Workflow DAG definition (JSON)")


class WorkflowResponse(BaseModel):
    """Schema for workflow response."""
    id: UUID
    name: str
    description: Optional[str]
    definition: Dict[str, Any]
    version: int
    status: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    """Schema for list of workflows."""
    total: int
    skip: int
    limit: int
    items: list[WorkflowResponse]


class ExecutionCreate(BaseModel):
    """Schema for creating a new execution."""
    input: Optional[Dict[str, Any]] = Field(None, description="Execution input parameters")
    execution_request_id: Optional[str] = Field(
        None, 
        max_length=255,
        description="Idempotency key for duplicate prevention"
    )


class TaskResponse(BaseModel):
    """Schema for task response."""
    id: UUID
    execution_id: UUID
    workflow_task_id: str
    name: str
    type: str
    config: Dict[str, Any]
    input: Optional[Dict[str, Any]]
    output: Optional[Dict[str, Any]]
    error: Optional[str]
    status: str
    worker_id: Optional[str]
    retry_count: int
    max_retries: int
    depends_on: list[str]
    position: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ExecutionResponse(BaseModel):
    """Schema for execution response."""
    id: UUID
    workflow_id: UUID
    execution_request_id: Optional[str]
    triggered_by: str
    status: str
    input: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]
    error: Optional[str]
    trace_id: str
    retry_count: int
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    tasks: list[TaskResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True

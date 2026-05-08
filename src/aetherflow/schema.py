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

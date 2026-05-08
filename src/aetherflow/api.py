"""FastAPI routes and endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from aetherflow.dependencies import get_db
from aetherflow.schema import WorkflowCreate, WorkflowResponse, WorkflowListResponse
from aetherflow.service import create_workflow, list_workflows
from aetherflow.logging import get_logger

logger = get_logger(__name__)

# Create router
router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
def create_new_workflow(
    workflow: WorkflowCreate,
    db: Session = Depends(get_db),
):
    """
    Create a new workflow.
    
    Args:
        workflow: Workflow creation data
        db: Database session (dependency injected)
        
    Returns:
        Created workflow with ID and metadata
    """
    try:
        created = create_workflow(
            db=db,
            name=workflow.name,
            description=workflow.description,
            definition=workflow.definition,
        )
        logger.info("workflow_creation_success", workflow_id=str(created.id))
        return created
    except Exception as e:
        logger.error(
            "workflow_creation_failed",
            error=str(e),
            name=workflow.name,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create workflow",
        )


@router.get("", response_model=WorkflowListResponse)
def list_all_workflows(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db),
):
    """
    List all workflows with pagination.
    
    Args:
        skip: Number of workflows to skip
        limit: Maximum number of workflows to return
        db: Database session (dependency injected)
        
    Returns:
        Paginated list of workflows
    """
    # Validate pagination params
    if skip < 0:
        skip = 0
    if limit < 1:
        limit = 1
    if limit > 100:
        limit = 100
    
    try:
        workflows, total = list_workflows(db=db, skip=skip, limit=limit)
        logger.info("workflows_fetch_success", total=total)
        return WorkflowListResponse(
            total=total,
            skip=skip,
            limit=limit,
            items=workflows,
        )
    except Exception as e:
        logger.error("workflows_fetch_failed", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch workflows",
        )

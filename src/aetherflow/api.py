"""FastAPI routes and endpoints."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from aetherflow.dependencies import get_db
from aetherflow.schema import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowListResponse,
    ExecutionCreate,
    ExecutionResponse,
)
from aetherflow.service import (
    create_workflow,
    list_workflows,
    create_execution,
    get_execution,
)
from aetherflow.logging import get_logger

logger = get_logger(__name__)

# Create routers
workflows_router = APIRouter(prefix="/workflows", tags=["workflows"])
executions_router = APIRouter(prefix="/executions", tags=["executions"])


@workflows_router.post("", response_model=WorkflowResponse, status_code=status.HTTP_201_CREATED)
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


@workflows_router.get("", response_model=WorkflowListResponse)
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


@workflows_router.post("/{workflow_id}/execute", response_model=ExecutionResponse, status_code=status.HTTP_202_ACCEPTED)
def execute_workflow(
    workflow_id: str,
    execution: ExecutionCreate,
    db: Session = Depends(get_db),
):
    """
    Execute a workflow (trigger execution).
    
    Returns 202 Accepted since execution is asynchronous.
    
    Args:
        workflow_id: ID of the workflow to execute
        execution: Execution input data
        db: Database session (dependency injected)
        
    Returns:
        Created execution with initial status PENDING
    """
    try:
        exec_obj = create_execution(
            db=db,
            workflow_id=workflow_id,
            input_data=execution.input,
            execution_request_id=execution.execution_request_id,
        )
        logger.info("execution_trigger_success", execution_id=str(exec_obj.id))
        return exec_obj
    except ValueError as e:
        logger.error("execution_trigger_failed", error=str(e), workflow_id=workflow_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error("execution_trigger_error", error=str(e), workflow_id=workflow_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to trigger execution",
        )


@executions_router.get("/{execution_id}", response_model=ExecutionResponse)
def get_execution_status(
    execution_id: str,
    db: Session = Depends(get_db),
):
    """
    Get execution status and all tasks.
    
    Args:
        execution_id: ID of the execution
        db: Database session (dependency injected)
        
    Returns:
        Execution with all tasks
    """
    try:
        exec_obj = get_execution(db=db, execution_id=execution_id)
        if not exec_obj:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Execution {execution_id} not found",
            )
        logger.info("execution_fetch_success", execution_id=execution_id)
        return exec_obj
    except HTTPException:
        raise
    except Exception as e:
        logger.error("execution_fetch_failed", error=str(e), execution_id=execution_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch execution",
        )

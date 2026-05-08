"""Business logic and service layer."""

from typing import Optional, Dict, Any
from uuid import uuid4
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import desc

from aetherflow.models import Workflow
from aetherflow.logging import get_logger

logger = get_logger(__name__)


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

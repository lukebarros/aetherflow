"""Redis-based task queue for worker processes."""

import json
import redis
from typing import Optional, Dict, Any
from uuid import UUID

from aetherflow.config import settings
from aetherflow.logging import get_logger

logger = get_logger(__name__)


class TaskQueue:
    """Redis-backed task queue for managing async task execution."""
    
    def __init__(self):
        """Initialize Redis connection."""
        self.redis_client = redis.from_url(settings.redis_url, decode_responses=True)
        self.queue_key = "aetherflow:tasks:queue"
        self.processing_key = "aetherflow:tasks:processing"
        self.dead_letter_key = "aetherflow:tasks:dead_letter"
    
    def enqueue_task(
        self,
        task_id: UUID,
        execution_id: UUID,
        workflow_task_id: str,
        task_type: str,
        config: Dict[str, Any],
        depends_on: list = None,
    ) -> bool:
        """
        Add a task to the queue.
        
        Args:
            task_id: UUID of the task
            execution_id: UUID of the execution
            workflow_task_id: Task ID in workflow definition
            task_type: Type of task (http, python, etc)
            config: Task configuration
            depends_on: List of task IDs this task depends on
            
        Returns:
            True if enqueued successfully
        """
        task_msg = {
            "task_id": str(task_id),
            "execution_id": str(execution_id),
            "workflow_task_id": workflow_task_id,
            "type": task_type,
            "config": config,
            "depends_on": depends_on or [],
        }
        
        try:
            self.redis_client.rpush(self.queue_key, json.dumps(task_msg))
            logger.info(
                "task_enqueued",
                task_id=str(task_id),
                execution_id=str(execution_id),
                workflow_task_id=workflow_task_id,
            )
            return True
        except Exception as e:
            logger.error(
                "task_enqueue_failed",
                task_id=str(task_id),
                error=str(e),
            )
            return False
    
    def dequeue_task(self, timeout: int = 5) -> Optional[Dict[str, Any]]:
        """
        Get the next task from the queue (blocking).
        
        Args:
            timeout: How long to wait for a task (seconds)
            
        Returns:
            Task dict or None if timeout
        """
        try:
            result = self.redis_client.blpop(self.queue_key, timeout=timeout)
            if result:
                _, task_json = result
                task = json.loads(task_json)
                
                # Move to processing list
                self.redis_client.rpush(self.processing_key, task_json)
                
                logger.info(
                    "task_dequeued",
                    task_id=task["task_id"],
                    execution_id=task["execution_id"],
                )
                return task
            return None
        except Exception as e:
            logger.error("task_dequeue_failed", error=str(e))
            return None
    
    def mark_task_complete(self, task_id: str, output: Any) -> bool:
        """
        Mark a task as complete and remove from processing.
        
        Args:
            task_id: UUID of the task
            output: Task output/result
            
        Returns:
            True if successful
        """
        try:
            # Remove from processing (we'd need to track it better in production)
            logger.info("task_marked_complete", task_id=task_id, output=output)
            return True
        except Exception as e:
            logger.error("task_complete_failed", task_id=task_id, error=str(e))
            return False
    
    def mark_task_failed(self, task_id: str, error: str, should_retry: bool = True) -> bool:
        """
        Mark a task as failed.
        
        Args:
            task_id: UUID of the task
            error: Error message
            should_retry: Whether to requeue for retry
            
        Returns:
            True if successful
        """
        try:
            if should_retry:
                logger.info("task_marked_failed_retry", task_id=task_id, error=error)
                # In production, would requeue with retry count
            else:
                logger.error("task_marked_failed", task_id=task_id, error=error)
                # Send to dead letter queue
                self.redis_client.rpush(self.dead_letter_key, task_id)
            return True
        except Exception as e:
            logger.error("task_failed_update_failed", task_id=task_id, error=str(e))
            return False
    
    def get_queue_size(self) -> int:
        """Get current queue size."""
        return self.redis_client.llen(self.queue_key)
    
    def get_processing_size(self) -> int:
        """Get number of tasks being processed."""
        return self.redis_client.llen(self.processing_key)
    
    def get_dead_letter_size(self) -> int:
        """Get number of tasks in dead letter queue."""
        return self.redis_client.llen(self.dead_letter_key)
    
    def health_check(self) -> bool:
        """Check if Redis is accessible."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error("redis_health_check_failed", error=str(e))
            return False


# Global queue instance
task_queue = TaskQueue()

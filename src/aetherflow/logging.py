"""Structured logging setup."""

import json
import logging
from datetime import datetime
from typing import Any, Dict

import structlog

from aetherflow.config import settings


def configure_logging() -> None:
    """Configure structlog for JSON output."""
    
    # Standard library configuration
    logging.basicConfig(
        format="%(message)s",
        stream=None,  # We'll handle output via structlog
        level=settings.log_level,
    )
    
    # structlog configuration
    structlog.configure(
        processors=[
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer(),
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = __name__) -> Any:
    """Get a structlog logger instance."""
    return structlog.get_logger(name)


class LogContext:
    """Context manager for adding execution context to logs."""
    
    def __init__(self, **context: Any):
        """
        Initialize context.
        
        Example:
            with LogContext(execution_id=exec_id, trace_id=trace_id):
                logger.info("task executed", status="SUCCESS")
        """
        self.context = context
        self.logger = get_logger()
    
    def __enter__(self):
        """Enter context and bind logger."""
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(**self.context)
        return self.logger
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and clear logger context."""
        structlog.contextvars.clear_contextvars()
        return False


# Initialize on import
configure_logging()

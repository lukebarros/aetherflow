#!/usr/bin/env python3
"""
Worker service entry point.

Run with: python -m aetherflow.worker_main
"""

import asyncio
import sys

from aetherflow.config import settings
from aetherflow.logging import get_logger
from aetherflow.worker import run_worker

logger = get_logger(__name__)


def main():
    """Run the worker."""
    logger.info("starting_worker", environment=settings.env)
    
    try:
        asyncio.run(run_worker())
    except Exception as e:
        logger.error("worker_fatal_error", error=str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()

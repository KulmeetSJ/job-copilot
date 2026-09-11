"""CLI entry point for running the background browser worker."""

import asyncio
import sys

from job_copilot.browser_worker.worker import BrowserWorker
from job_copilot.db.database import init_db
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def main():
    """Start the standalone browser worker."""
    logger.info("Initializing Job Copilot Database for Browser Worker...")
    init_db()
    worker = BrowserWorker()
    asyncio.run(worker.run_loop())


if __name__ == "__main__":
    main()

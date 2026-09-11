"""Standalone Browser Worker runner loop and task processor."""

import asyncio
from datetime import datetime, timezone
import os
import signal
import socket
from typing import Optional
import uuid
from sqlalchemy.orm import Session

from job_copilot.browser_worker.task_executor import BrowserTaskExecutor
from job_copilot.db.database import get_db
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserWorker:
    """
    Background worker process that continuously polls for QUEUED browser tasks,
    executes form preparation safely in isolated Playwright instances, and halts at READY_FOR_REVIEW.
    """

    def __init__(
        self,
        worker_id: Optional[str] = None,
        poll_interval_seconds: float = 5.0,
        max_tasks: Optional[int] = None,
    ):
        self.worker_id = worker_id or f"worker-{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_interval_seconds = poll_interval_seconds
        self.max_tasks = max_tasks
        self._running = False
        self._processed_count = 0

    async def process_next_task(self, db: Session) -> Optional[BrowserTaskModel]:
        """Fetch and execute the next available QUEUED task."""
        repo = BrowserTaskRepository(db)
        queued_tasks = repo.list_by_status(BrowserTaskStatus.QUEUED, limit=1)
        if not queued_tasks:
            return None

        task = queued_tasks[0]
        logger.info(f"Worker '{self.worker_id}' claimed task '{task.task_id}' for URL: {task.target_url}")

        # Check attempt limits
        if task.attempt_count >= task.max_attempts:
            logger.warning(f"Task '{task.task_id}' exceeded max attempts ({task.max_attempts}). Marking FAILED.")
            repo.update_status(task.task_id, BrowserTaskStatus.FAILED, failure_reason="Max execution attempts exceeded")
            return task

        task.attempt_count += 1
        task.worker_id = self.worker_id
        db.commit()

        executor = BrowserTaskExecutor(db=db)
        result = await executor.execute_task(task.task_id)
        self._processed_count += 1
        return result

    async def run_once(self) -> Optional[BrowserTaskModel]:
        """Run a single execution cycle."""
        session_gen = get_db()
        db = next(session_gen)
        try:
            return await self.process_next_task(db)
        finally:
            db.close()

    async def run_loop(self) -> None:
        """Continuous polling execution loop."""
        self._running = True
        logger.info(f"Starting Browser Worker '{self.worker_id}' (poll_interval={self.poll_interval_seconds}s)...")

        def handle_signal(sig, frame):
            logger.info(f"Received stop signal ({sig}). Gracefully shutting down worker...")
            self._running = False

        try:
            signal.signal(signal.SIGINT, handle_signal)
            signal.signal(signal.SIGTERM, handle_signal)
        except (ValueError, AttributeError):
            pass

        while self._running:
            try:
                task = await self.run_once()
                if not task:
                    await asyncio.sleep(self.poll_interval_seconds)
                else:
                    if self.max_tasks and self._processed_count >= self.max_tasks:
                        logger.info(f"Reached max task count ({self.max_tasks}). Stopping worker.")
                        break
            except Exception as e:
                logger.error(f"Worker iteration encountered error: {e}")
                await asyncio.sleep(self.poll_interval_seconds)

        logger.info(f"Browser Worker '{self.worker_id}' stopped. Total processed: {self._processed_count}.")

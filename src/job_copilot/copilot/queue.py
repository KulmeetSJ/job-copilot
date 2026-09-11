"""Persistent Copilot Queue Manager for Phase 9."""

import json
from pathlib import Path
import threading
from typing import Dict, List, Optional

from job_copilot.copilot.models import (
    CopilotJob,
    PriorityBand,
    QueueStatus,
    utc_now,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CopilotQueueStore:
    """
    Thread-safe persistent storage for the Copilot Opportunity Queue.
    Stores entries in data/copilot/queue.json referencing Phase 5 jobs, Phase 6 packages,
    and Phase 8 tracking without duplicating their data.
    """

    def __init__(self, queue_dir: Optional[Path] = None):
        self.queue_dir = queue_dir or Path("data/copilot")
        self._lock = threading.Lock()
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self._init_files()

    def _init_files(self) -> None:
        q_file = self.queue_dir / "queue.json"
        if not q_file.exists():
            q_file.write_text("{}", encoding="utf-8")

    def add_or_update(self, job: CopilotJob) -> CopilotJob:
        """Add or update an opportunity in the queue."""
        with self._lock:
            q_file = self.queue_dir / "queue.json"
            registry: Dict[str, Dict] = {}
            if q_file.exists():
                try:
                    registry = json.loads(q_file.read_text(encoding="utf-8"))
                except Exception:
                    registry = {}

            job.updated_at = utc_now()
            registry[job.job_id] = json.loads(job.model_dump_json())
            q_file.write_text(json.dumps(registry, indent=2), encoding="utf-8")
            return job

    def get(self, job_id: str) -> Optional[CopilotJob]:
        """Fetch job from queue by ID."""
        q_file = self.queue_dir / "queue.json"
        if not q_file.exists():
            return None
        try:
            registry = json.loads(q_file.read_text(encoding="utf-8"))
            if job_id in registry:
                return CopilotJob.model_validate(registry[job_id])
        except Exception as e:
            logger.error(f"Error reading job '{job_id}' from queue: {e}")
        return None

    def list_jobs(
        self,
        queue_status: Optional[QueueStatus] = None,
        priority_band: Optional[PriorityBand] = None,
        min_priority_score: Optional[float] = None,
    ) -> List[CopilotJob]:
        """List and filter jobs from the queue sorted by priority score descending."""
        q_file = self.queue_dir / "queue.json"
        if not q_file.exists():
            return []
        try:
            registry = json.loads(q_file.read_text(encoding="utf-8"))
            jobs = [CopilotJob.model_validate(v) for v in registry.values()]

            if queue_status:
                jobs = [j for j in jobs if j.queue_status == queue_status]
            if priority_band:
                jobs = [j for j in jobs if j.priority_band == priority_band]
            if min_priority_score is not None:
                jobs = [j for j in jobs if j.priority_score >= min_priority_score]

            # Sort by priority score descending, then created_at descending
            return sorted(jobs, key=lambda j: (j.priority_score, j.created_at), reverse=True)
        except Exception as e:
            logger.error(f"Error listing queue: {e}")
            return []

    def update_status(
        self,
        job_id: str,
        new_status: QueueStatus,
        notes: Optional[str] = None,
    ) -> Optional[CopilotJob]:
        """Transition queue status of a job."""
        job = self.get(job_id)
        if not job:
            return None

        job.queue_status = new_status
        if notes:
            now_str = utc_now().strftime("%Y-%m-%d %H:%M:%S UTC")
            job.user_notes.append(f"[{now_str}] (Status: {new_status.value}) {notes}")
        return self.add_or_update(job)

    def get_counts(self) -> Dict[str, int]:
        """Return counts of jobs by queue status."""
        jobs = self.list_jobs()
        counts: Dict[str, int] = {s.value: 0 for s in QueueStatus}
        for j in jobs:
            counts[j.queue_status.value] = counts.get(j.queue_status.value, 0) + 1
        return counts

"""Unit tests for CopilotQueueStore."""

from pathlib import Path
from job_copilot.copilot.models import CopilotJob, PriorityBand, QueueStatus, utc_now
from job_copilot.copilot.queue import CopilotQueueStore


def test_queue_persistence_and_transitions(tmp_path: Path):
    queue_store = CopilotQueueStore(queue_dir=tmp_path / "copilot")

    job1 = CopilotJob(
        job_id="job-1",
        title="Senior Backend Engineer",
        company="Target Co",
        priority_score=85.0,
        priority_band=PriorityBand.HIGH,
        queue_status=QueueStatus.REVIEW,
    )
    job2 = CopilotJob(
        job_id="job-2",
        title="Staff Cloud Engineer",
        company="Cloud Corp",
        priority_score=92.0,
        priority_band=PriorityBand.CRITICAL,
        queue_status=QueueStatus.REVIEW,
    )

    # 1. Add jobs
    queue_store.add_or_update(job1)
    queue_store.add_or_update(job2)

    # 2. List sorted by priority descending
    jobs = queue_store.list_jobs()
    assert len(jobs) == 2
    assert jobs[0].job_id == "job-2"  # 92.0 > 85.0

    # 3. Update status
    updated = queue_store.update_status("job-1", QueueStatus.APPROVED, notes="Approved by candidate")
    assert updated.queue_status == QueueStatus.APPROVED
    assert len(updated.user_notes) == 1

    # 4. Filter by status
    approved_jobs = queue_store.list_jobs(queue_status=QueueStatus.APPROVED)
    assert len(approved_jobs) == 1
    assert approved_jobs[0].job_id == "job-1"

    # 5. Counts
    counts = queue_store.get_counts()
    assert counts[QueueStatus.APPROVED.value] == 1
    assert counts[QueueStatus.REVIEW.value] == 1

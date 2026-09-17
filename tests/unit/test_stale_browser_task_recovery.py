"""Regression tests for stale browser task recovery and concurrency safety."""

from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from job_copilot.db.base import Base
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository


@pytest.fixture
def db_session() -> Session:
    """Provide an isolated in-memory SQLite database session."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    try:
        yield session
    finally:
        session.close()


def test_fresh_running_task_is_untouched(db_session: Session):
    """Verify that an actively running task within the timeout window is not recovered."""
    repo = BrowserTaskRepository(db_session)
    now = datetime.now(timezone.utc)

    task = repo.create_task(
        application_id="app-fresh-run",
        job_id="job-fresh-run",
        target_url="https://example.com/careers/1",
        status=BrowserTaskStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
    )
    # Ensure updated_at is within fresh window
    task.updated_at = now - timedelta(minutes=2)
    db_session.commit()

    recovered = repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered == 0

    reloaded = repo.get_by_task_id(task.task_id)
    assert reloaded.status == BrowserTaskStatus.RUNNING


def test_stale_running_task_is_recovered(db_session: Session):
    """Verify that a running preparation task older than timeout is safely recovered to QUEUED."""
    repo = BrowserTaskRepository(db_session)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=25)

    task = repo.create_task(
        application_id="app-stale-run",
        job_id="job-stale-run",
        target_url="https://example.com/careers/2",
        status=BrowserTaskStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
    )
    task.updated_at = stale_time
    db_session.commit()

    recovered = repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered == 1

    reloaded = repo.get_by_task_id(task.task_id)
    assert reloaded.status == BrowserTaskStatus.QUEUED
    assert "Recovered" in (reloaded.pause_reason or "")
    # Audit log entry created
    events = reloaded.audit_events or []
    assert any(e.get("event") == "stale_task_recovered" for e in events)


def test_fresh_submission_running_task_is_untouched(db_session: Session):
    """Verify that an in-flight submission task within the timeout window is never prematurely recovered."""
    repo = BrowserTaskRepository(db_session)
    now = datetime.now(timezone.utc)

    task = repo.create_task(
        application_id="app-fresh-sub",
        job_id="job-fresh-sub",
        target_url="https://example.com/careers/3",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        attempt_count=1,
        max_attempts=3,
    )
    task.updated_at = now - timedelta(minutes=3)
    db_session.commit()

    recovered = repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered == 0

    reloaded = repo.get_by_task_id(task.task_id)
    assert reloaded.status == BrowserTaskStatus.SUBMISSION_RUNNING


def test_stale_submission_running_task_cannot_become_submitted_automatically(db_session: Session):
    """
    CRITICAL INVARIANT: A crashed submission task must NEVER be silently converted into SUBMITTED
    or re-authorized automatically. It must require manual review or re-authorization.
    """
    repo = BrowserTaskRepository(db_session)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=30)

    # 1. Crash occurred before clicking submit button
    task_pre_click = repo.create_task(
        application_id="app-crashed-pre",
        job_id="job-crashed-pre",
        target_url="https://example.com/careers/4",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        attempt_count=1,
        max_attempts=3,
    )
    task_pre_click.updated_at = stale_time

    # 2. Crash occurred after clicking submit button (ambiguous external state)
    task_post_click = repo.create_task(
        application_id="app-crashed-post",
        job_id="job-crashed-post",
        target_url="https://example.com/careers/5",
        status=BrowserTaskStatus.SUBMISSION_RUNNING,
        attempt_count=1,
        max_attempts=3,
        audit_events=[
            {"event": "submit_click_dispatched", "timestamp": stale_time.isoformat()}
        ],
    )
    task_post_click.updated_at = stale_time
    db_session.commit()

    recovered = repo.recover_stale_running_tasks(timeout_minutes=15)
    assert recovered == 2

    # Task pre-click must transition to FAILED (never SUBMITTED or SUBMISSION_AUTHORIZED)
    reloaded_pre = repo.get_by_task_id(task_pre_click.task_id)
    assert reloaded_pre.status == BrowserTaskStatus.FAILED
    assert reloaded_pre.status != BrowserTaskStatus.COMPLETED
    assert reloaded_pre.status != BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert "never automatically retried" in (reloaded_pre.failure_reason or "")

    # Task post-click must transition to SUBMISSION_UNVERIFIED (never SUBMITTED or auto-retry)
    reloaded_post = repo.get_by_task_id(task_post_click.task_id)
    assert reloaded_post.status == BrowserTaskStatus.SUBMISSION_UNVERIFIED
    assert reloaded_post.status != BrowserTaskStatus.COMPLETED
    assert reloaded_post.status != BrowserTaskStatus.SUBMISSION_AUTHORIZED
    assert "Outcome unverified" in (reloaded_post.pause_reason or "")


def test_concurrent_recovery_cannot_claim_same_task_twice(db_session: Session):
    """Verify that multiple concurrent worker processes cannot recover/claim the same stale task twice."""
    repo1 = BrowserTaskRepository(db_session)
    stale_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=15)

    task = repo1.create_task(
        application_id="app-concurrent-recovery",
        job_id="job-concurrent-recovery",
        target_url="https://example.com/careers/6",
        status=BrowserTaskStatus.RUNNING,
        attempt_count=1,
        max_attempts=3,
    )
    task.updated_at = stale_time
    db_session.commit()

    # Worker 1 recovers task atomically
    claimed_w1 = repo1.recover_stale_task(
        task_id=task.task_id,
        expected_status=BrowserTaskStatus.RUNNING,
        new_status=BrowserTaskStatus.QUEUED,
        cutoff=cutoff,
        reason="Recovered by worker 1",
    )
    assert claimed_w1 is True

    # Concurrent Worker 2 attempts to recover the exact same task
    claimed_w2 = repo1.recover_stale_task(
        task_id=task.task_id,
        expected_status=BrowserTaskStatus.RUNNING,
        new_status=BrowserTaskStatus.QUEUED,
        cutoff=cutoff,
        reason="Recovered by worker 2",
    )
    assert claimed_w2 is False  # Cannot claim already recovered task

    # Verify task state was only modified once
    reloaded = repo1.get_by_task_id(task.task_id)
    assert reloaded.status == BrowserTaskStatus.QUEUED
    assert reloaded.pause_reason == "Recovered by worker 1"

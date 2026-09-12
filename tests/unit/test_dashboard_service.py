"""Unit tests for Phase 11 DashboardService."""

import pytest
from unittest.mock import MagicMock
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.copilot.models import CopilotJob, PriorityBand, QueueStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.base import Base
from job_copilot.models.application import Application, ApplicationEventModel
from job_copilot.models.job import Job
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.schemas.dashboard import HumanInputSubmitRequest, HumanInputAnswerItem, SubmissionConfirmPayload
from job_copilot.services.dashboard_service import DashboardService


from sqlalchemy.pool import StaticPool


@pytest.fixture
def in_memory_db():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def mock_copilot_service():
    service = MagicMock()
    service.get_queue.return_value = [
        CopilotJob(
            job_id="job-stripe-001",
            title="Senior Backend Engineer",
            company="Stripe",
            location="Bengaluru",
            source="manual",
            priority_score=92.0,
            priority_band=PriorityBand.CRITICAL,
            queue_status=QueueStatus.NEW,
            match_score=92.0,
            recommendation_tier="STRONG_APPLY",
        ),
        CopilotJob(
            job_id="job-hsbc-002",
            title="Lead Software Engineer",
            company="HSBC",
            location="Pune",
            source="manual",
            priority_score=85.0,
            priority_band=PriorityBand.HIGH,
            queue_status=QueueStatus.REVIEW,
            match_score=88.0,
            recommendation_tier="STRONG_APPLY",
        ),
    ]
    service.get_sources_health.return_value = []
    service.get_sources.return_value = []
    return service


def test_dashboard_overview_aggregation(in_memory_db, mock_copilot_service):
    """Test dashboard overview metrics calculation."""
    # Seed an application
    job = Job(
        job_id="job-stripe-001",
        title="Senior Backend Engineer",
        company="Stripe",
        description="Java Spring Boot engineer",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-stripe-001",
        job_id=job.id,
        job_id_str="job-stripe-001",
        company="Stripe",
        role="Senior Backend Engineer",
        status=ApplicationStatus.READY_TO_APPLY,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    overview = service.get_overview()

    assert overview.queue_counts.critical == 1
    assert overview.queue_counts.high == 1
    assert overview.queue_counts.total_active == 2
    assert overview.pipeline_counts.ready_for_review >= 1


def test_dashboard_queue_retrieval(in_memory_db, mock_copilot_service):
    """Test priority queue filtering and response mapping."""
    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    queue = service.get_queue()

    assert queue.total_count == 2
    assert queue.critical_count == 1
    assert queue.high_count == 1
    assert queue.items[0].company == "Stripe"
    assert queue.items[0].match_score == 92.0


def test_dashboard_job_detail_explanation(in_memory_db, mock_copilot_service):
    """Test job detail match explanation with 7 dimensions and Fact vs Inference."""
    job = Job(
        job_id="job-hsbc-002",
        title="Lead Software Engineer",
        company="HSBC",
        description="Seeking a Senior Java and Spring Boot engineer with GCP experience in Fintech payments.",
        lifecycle_status="DISCOVERED",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    mock_copilot_service.get_job.return_value = CopilotJob(
        job_id="job-hsbc-002",
        title="Lead Software Engineer",
        company="HSBC",
        match_score=88.0,
        priority_score=85.0,
        priority_band=PriorityBand.HIGH,
        recommendation_tier="STRONG_APPLY",
    )

    service = DashboardService(db=in_memory_db, copilot_service=mock_copilot_service)
    detail = service.get_job_detail("job-hsbc-002")

    assert detail.company == "HSBC"
    assert detail.match_score >= 70.0
    assert len(detail.dimension_scores) == 7
    # Verify Fact vs Inference vs Recommendation separation
    assert len(detail.explanation.facts) > 0
    assert len(detail.explanation.recommendations) > 0


def test_dashboard_human_input_submission_safe(in_memory_db):
    """Test submitting human answers stores in application state without mutating candidate files."""
    job = Job(
        job_id="job-test-input-001",
        title="Backend Engineer",
        company="TestCorp",
        description="Software engineer",
    )
    in_memory_db.add(job)
    in_memory_db.commit()

    app = Application(
        application_id="app-test-input-001",
        job_id=job.id,
        job_id_str="job-test-input-001",
        company="TestCorp",
        role="Backend Engineer",
        status=ApplicationStatus.PREPARING,
    )
    in_memory_db.add(app)
    in_memory_db.commit()

    service = DashboardService(db=in_memory_db)
    payload = HumanInputSubmitRequest(
        answers=[
            HumanInputAnswerItem(
                question_id="work_auth",
                question_text="Are you authorized to work in the country?",
                answer_value="Yes, Citizen",
            ),
            HumanInputAnswerItem(
                question_id="notice_period",
                question_text="What is your notice period?",
                answer_value="30 days",
            ),
        ]
    )

    updated = service.submit_user_inputs("app-test-input-001", payload)
    assert updated.application_id == "app-test-input-001"
    assert len(updated.user_notes) > 0
    assert "work_auth='Yes, Citizen'" in updated.user_notes[0]

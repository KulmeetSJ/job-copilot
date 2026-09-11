"""Unit tests for Job and Application repositories."""

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from job_copilot.domain.enums import ApplicationStatus, EmploymentType, RemoteStatus, ResumeStrategy
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.application import ApplicationCreate, ApplicationUpdate
from job_copilot.schemas.job import JobCreate, JobUpdate


def test_create_and_get_job(db_session: Session):
    """Test creating and retrieving a job record."""
    repo = JobRepository(db_session)
    job_in = JobCreate(
        title="Backend Software Engineer",
        company="Stripe",
        location="Remote, US",
        remote_status=RemoteStatus.REMOTE,
        employment_type=EmploymentType.FULL_TIME,
        url="https://stripe.com/jobs/123",
        source="greenhouse",
        description="We are looking for a Backend Engineer to build payment infrastructure.",
        requirements=["5+ years Python or Java", "Distributed systems experience"],
        technologies=["Python", "FastAPI", "PostgreSQL"],
        salary_min=160000,
        salary_max=220000,
    )
    job = repo.create(job_in)

    assert job.id is not None
    assert job.title == "Backend Software Engineer"
    assert job.company == "Stripe"
    assert job.requirements == ["5+ years Python or Java", "Distributed systems experience"]

    fetched = repo.get_by_id(job.id)
    assert fetched is not None
    assert fetched.id == job.id


def test_update_and_delete_job(db_session: Session):
    """Test updating and deleting a job record."""
    repo = JobRepository(db_session)
    job_in = JobCreate(
        title="Software Engineer",
        company="Datadog",
        description="Monitoring systems backend engineer.",
    )
    job = repo.create(job_in)

    # Update
    updated = repo.update(job.id, JobUpdate(title="Senior Software Engineer", salary_min=180000))
    assert updated.title == "Senior Software Engineer"
    assert updated.salary_min == 180000

    # Delete
    deleted = repo.delete(job.id)
    assert deleted is True
    assert repo.get_by_id(job.id) is None


def test_create_and_update_application(db_session: Session):
    """Test creating an application, querying it, and updating its status."""
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)

    # 1. Create Job
    job = job_repo.create(
        JobCreate(
            title="Systems Engineer",
            company="Cloudflare",
            description="Edge routing and distributed systems.",
        )
    )

    # 2. Create Application
    app_in = ApplicationCreate(
        job_id=job.id,
        status=ApplicationStatus.DISCOVERED,
        strategy_used=ResumeStrategy.PLATFORM_DEVOPS,
        notes="Discovered via referral.",
    )
    app = app_repo.create(app_in)
    assert app.id is not None
    assert app.job_id == job.id
    assert app.status == ApplicationStatus.DISCOVERED

    # 3. Update status to APPLIED (should set applied_at timestamp)
    updated_app = app_repo.update_status(
        app.id,
        status=ApplicationStatus.APPLIED,
        notes="Submitted via company portal.",
    )
    assert updated_app.status == ApplicationStatus.APPLIED
    assert updated_app.applied_at is not None
    assert "Submitted via company portal" in updated_app.notes

    # 4. Query by job_id
    by_job = app_repo.get_by_job_id(job.id)
    assert by_job is not None
    assert by_job.id == app.id
    assert by_job.job.company == "Cloudflare"


def test_duplicate_application_per_job_prevented(db_session: Session):
    """Test that creating multiple applications for the same job violates unique constraint."""
    job_repo = JobRepository(db_session)
    app_repo = ApplicationRepository(db_session)

    job = job_repo.create(
        JobCreate(
            title="Backend Engineer",
            company="Airbnb",
            description="Search backend team.",
        )
    )

    app_repo.create(ApplicationCreate(job_id=job.id))

    with pytest.raises(IntegrityError):
        app_repo.create(ApplicationCreate(job_id=job.id))
        db_session.commit()

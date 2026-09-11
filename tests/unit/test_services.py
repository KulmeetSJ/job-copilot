"""Unit tests for the Service layer."""

from pathlib import Path
import pytest
from sqlalchemy.orm import Session

from job_copilot.domain.enums import ApplicationStatus, ResumeStrategy
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.schemas.application import ApplicationCreate
from job_copilot.schemas.job import JobCreate
from job_copilot.services.application_service import ApplicationService
from job_copilot.services.candidate_service import CandidateService
from job_copilot.services.job_service import JobService
from job_copilot.services.resume_service import ResumeService


def test_candidate_service(temp_profile_file: Path):
    """Test CandidateService retrieving structured candidate information."""
    repo = CandidateRepository(profile_path=temp_profile_file)
    service = CandidateService(repository=repo)

    profile = service.get_profile()
    assert profile.personal_info.full_name == "Jane Doe"

    skills = service.get_skills()
    assert len(skills) == 2

    experience = service.get_experience()
    assert len(experience) == 1
    assert experience[0].company == "Tech Innovators Inc"

    projects = service.get_projects()
    assert len(projects) == 1
    assert projects[0].name == "Async Task Queue"

    education = service.get_education()
    assert len(education) == 1
    assert education[0].institution == "University of California, Berkeley"


def test_job_service_and_analysis(db_session: Session, temp_profile_file: Path):
    """Test JobService creation and deterministic match scoring against profile."""
    candidate_repo = CandidateRepository(profile_path=temp_profile_file)
    job_service = JobService(db=db_session, candidate_repo=candidate_repo)

    # 1. Create a job
    job = job_service.create_job(
        JobCreate(
            title="Senior Python Backend Engineer",
            company="ModernStack",
            description="We are seeking an engineer experienced in Python, FastAPI, and PostgreSQL to scale microservices.",
        )
    )
    assert job.id is not None
    assert job.company == "ModernStack"

    # 2. Analyze job description
    analysis = job_service.analyze_job(
        description=job.description,
        title=job.title,
        company=job.company,
        job_id=job.id,
    )
    assert analysis.job_id == job.id
    assert analysis.match_score > 70.0
    assert "Python" in analysis.matching_skills or "Fastapi" in analysis.matching_skills
    assert analysis.recommended_strategy in [ResumeStrategy.GENERAL_SWE, ResumeStrategy.BACKEND_JAVA]


def test_application_service_lifecycle(db_session: Session):
    """Test ApplicationService application creation and status advancement."""
    job_service = JobService(db=db_session)
    app_service = ApplicationService(db=db_session)

    job = job_service.create_job(
        JobCreate(
            title="Distributed Systems Engineer",
            company="Anthropic",
            description="Building scalable AI training infra.",
        )
    )

    # 1. Create application
    app = app_service.create_application(
        ApplicationCreate(
            job_id=job.id,
            status=ApplicationStatus.DISCOVERED,
        )
    )
    assert app.id is not None
    assert app.status == ApplicationStatus.DISCOVERED

    # 2. Duplicate rejection
    with pytest.raises(ValueError):
        app_service.create_application(ApplicationCreate(job_id=job.id))

    # 3. Update status
    updated = app_service.update_status(
        app.id,
        status=ApplicationStatus.INTERVIEW,
        notes="Phone screen scheduled with HM.",
    )
    assert updated.status == ApplicationStatus.INTERVIEW
    assert "Phone screen scheduled" in updated.notes


def test_resume_service_validation_and_generation(temp_profile_file: Path):
    """Test ResumeService loading and tailoring with Phase 3 engine."""
    service = ResumeService(master_profile_path=temp_profile_file)

    profile = service.load_master_profile()
    assert profile.personal_info.full_name == "Jane Doe"
    assert len(service.list_strategies()) == 5

    res = service.generate_tailored_resume("backend_java")
    assert res.strategy_name == "backend_java"
    assert res.validation.is_valid is True


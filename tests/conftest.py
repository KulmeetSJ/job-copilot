"""Pytest shared test fixtures and configuration."""

import tempfile
from pathlib import Path
from typing import Generator
import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from job_copilot.api.app import app
from job_copilot.models.base import Base
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.schemas.candidate import CandidateProfile


@pytest.fixture
def sample_profile_data() -> dict:
    """Return a valid candidate profile dictionary for tests."""
    return {
        "version": "1.0.0",
        "last_updated": "2026-09-08",
        "personal_info": {
            "full_name": "Jane Doe",
            "email": "jane.doe@example.com",
            "phone": "+1-555-123-4567",
            "location": "San Francisco, CA",
            "headline": "Senior Backend Engineer",
            "summary": None,
            "links": [
                {"label": "GitHub", "url": "https://github.com/janedoe"},
                {"label": "LinkedIn", "url": "https://linkedin.com/in/janedoe"},
            ],
            "evidence_ids": ["PI-001"],
        },
        "work_authorization": {
            "current_country": "United States",
            "current_work_authorization": "Authorized to work",
            "international_sponsorship_required": False,
            "notes": None,
        },
        "education": [
            {
                "institution": "University of California, Berkeley",
                "degree": "B.S.",
                "field_of_study": "Computer Science",
                "location": "Berkeley, CA",
                "start_date": "2016-08",
                "end_date": "2020-05",
                "gpa": "3.85",
                "coursework": ["Operating Systems", "Databases", "Algorithms"],
                "honors": ["Dean's List"],
                "evidence_ids": ["EDU-001"],
            }
        ],
        "employment": [
            {
                "company": "Tech Innovators Inc",
                "role": "Senior Software Engineer",
                "canonical_role": None,
                "historical_titles": ["Senior Software Engineer"],
                "location": "San Francisco, CA",
                "remote_status": "REMOTE",
                "start_date": "2020-06",
                "end_date": None,
                "current": True,
                "description": "Core payment platform team.",
                "technologies": ["Python", "FastAPI", "PostgreSQL", "Kafka"],
                "responsibilities": [
                    "Architect high-throughput transactional payment services."
                ],
                "achievements": [
                    {
                        "description": "Scaled payment processing pipeline to 10k TPS.",
                        "metrics": ["10k TPS", "45% latency reduction"],
                        "technologies": ["Python", "PostgreSQL"],
                        "impact": "Saved $1.2M annually in compute costs.",
                        "evidence_ids": ["ACH-001"],
                    }
                ],
                "evidence_ids": ["EXP-001"],
            }
        ],
        "projects": [
            {
                "name": "Async Task Queue",
                "description": "Lightweight distributed job queue in Python.",
                "technologies": ["Python", "AsyncIO", "Redis"],
                "architecture": "Distributed queue",
                "deployment_status": "PORTFOLIO_DEMO",
                "responsibilities": ["Lead author and maintainer."],
                "achievements": [
                    {
                        "description": "Gained 500+ GitHub stars.",
                        "metrics": ["500 stars"],
                        "technologies": ["Python"],
                        "impact": "Adopted by 5 open source projects.",
                        "evidence_ids": ["PRJ-ACH-001"],
                    }
                ],
                "metrics": ["500 stars"],
                "links": [
                    {"label": "GitHub", "url": "https://github.com/janedoe/async-queue"}
                ],
                "start_date": None,
                "end_date": None,
                "evidence_ids": ["PRJ-001"],
            }
        ],
        "skills": [
            {
                "category": "Languages",
                "skills": [
                    {
                        "name": "Python",
                        "status": "CONFIRMED",
                        "evidence": [
                            {
                                "type": "professional",
                                "source_file": "Resume.pdf",
                                "source_section": "Experience",
                                "context": "Python backend development",
                                "evidence_id": "EXP-001",
                            }
                        ],
                    },
                    {
                        "name": "SQL",
                        "status": "CONFIRMED",
                        "evidence": [
                            {
                                "type": "professional",
                                "source_file": "Resume.pdf",
                                "source_section": "Experience",
                                "context": "SQL databases",
                                "evidence_id": "EXP-001",
                            }
                        ],
                    },
                ],
            },
            {
                "category": "Frameworks & Tools",
                "skills": [
                    {
                        "name": "FastAPI",
                        "status": "CONFIRMED",
                        "evidence": [
                            {
                                "type": "professional",
                                "source_file": "Resume.pdf",
                                "source_section": "Experience",
                                "context": "FastAPI services",
                                "evidence_id": "EXP-001",
                            }
                        ],
                    },
                    {
                        "name": "Docker",
                        "status": "CONFIRMED",
                        "evidence": [
                            {
                                "type": "professional",
                                "source_file": "Resume.pdf",
                                "source_section": "Experience",
                                "context": "Docker containers",
                                "evidence_id": "EXP-001",
                            }
                        ],
                    },
                ],
            },
        ],
        "certifications": [
            {
                "name": "AWS Certified Solutions Architect",
                "issuer": "Amazon Web Services",
                "issue_date": "2022-04",
                "expiration_date": "2025-04",
                "credential_id": "AWS-12345",
                "credential_url": "https://aws.amazon.com/verify/AWS-12345",
                "evidence_ids": ["CERT-001"],
            }
        ],
        "awards": [],
        "domain_experience": [],
    }


@pytest.fixture
def temp_profile_file(sample_profile_data: dict) -> Generator[Path, None, None]:
    """Create a temporary master_profile.yaml file for testing."""
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.safe_dump(sample_profile_data, f)
        temp_path = Path(f.name)

    yield temp_path

    if temp_path.exists():
        temp_path.unlink()


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """Create an in-memory SQLite database session for unit tests."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = Session()

    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


@pytest.fixture
def api_client() -> TestClient:
    """FastAPI TestClient fixture."""
    return TestClient(app)

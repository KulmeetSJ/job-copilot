"""Service layer for Job ingestion, retrieval, and analysis."""

import re
from typing import List, Optional, Set
from sqlalchemy.orm import Session

from job_copilot.domain.enums import ResumeStrategy
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.job import JobAnalysisResult, JobCreate, JobRead, JobUpdate
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobService:
    """Business operations for Job posting management and analysis."""

    def __init__(
        self,
        db: Session,
        candidate_repo: Optional[CandidateRepository] = None,
    ):
        self.repository = JobRepository(db)
        self.candidate_repo = candidate_repo or CandidateRepository()

    def create_job(self, job_in: JobCreate) -> JobRead:
        """Create a new job posting."""
        job = self.repository.create(job_in)
        return JobRead.model_validate(job)

    def get_job(self, job_id: int) -> Optional[JobRead]:
        """Fetch a job posting by ID."""
        job = self.repository.get_by_id(job_id)
        if not job:
            return None
        return JobRead.model_validate(job)

    def list_jobs(self, skip: int = 0, limit: int = 100) -> List[JobRead]:
        """List all tracked job postings."""
        jobs = self.repository.list_jobs(skip=skip, limit=limit)
        return [JobRead.model_validate(j) for j in jobs]

    def update_job(self, job_id: int, job_in: JobUpdate) -> Optional[JobRead]:
        """Update an existing job posting."""
        job = self.repository.update(job_id, job_in)
        if not job:
            return None
        return JobRead.model_validate(job)

    def analyze_job(
        self,
        description: str,
        title: Optional[str] = None,
        company: Optional[str] = None,
        job_id: Optional[int] = None,
    ) -> JobAnalysisResult:
        """
        Analyze a job description against the canonical Master Candidate Profile.
        
        Currently performs deterministic profile matching and keyword analysis.
        Future phases will augment this with LLM-based deep semantic evaluation.
        """
        candidate_skills: Set[str] = set()
        try:
            if self.candidate_repo.exists():
                profile = self.candidate_repo.load()
                for cat in profile.skills:
                    for skill in cat.skills:
                        candidate_skills.add(skill.name.lower())
        except Exception as e:
            logger.warning(f"Could not load candidate profile for job analysis: {e}")

        # Basic keyword extraction from JD text
        jd_lower = description.lower()
        
        # Check skill overlap
        matching: List[str] = []
        for skill in candidate_skills:
            # Word boundary check
            if re.search(r'\b' + re.escape(skill) + r'\b', jd_lower):
                matching.append(skill.title())

        # Determine canonical strategy suggestion
        strategy = ResumeStrategy.BACKEND_JAVA
        if any(w in jd_lower for w in ["devops", "kubernetes", "terraform", "sre", "reliability"]):
            strategy = ResumeStrategy.SRE_DEVOPS
        elif any(w in jd_lower for w in ["aws", "gcp", "azure", "cloud", "docker", "infrastructure"]):
            strategy = ResumeStrategy.CLOUD_DEVOPS
        elif any(w in jd_lower for w in ["spark", "data engineer", "etl", "pipeline", "hadoop", "flink"]):
            strategy = ResumeStrategy.DATA_ENGINEERING
        elif any(w in jd_lower for w in ["react", "vue", "frontend", "full stack", "fullstack", "typescript"]):
            strategy = ResumeStrategy.FULL_STACK
        elif any(w in jd_lower for w in ["java", "spring", "backend", "grpc", "microservices"]):
            strategy = ResumeStrategy.BACKEND_JAVA

        # Baseline scoring
        base_score = 65.0
        if matching:
            base_score = min(95.0, base_score + len(matching) * 5.0)

        recommendation = "APPLY" if base_score >= 75.0 else ("CONSIDER" if base_score >= 60.0 else "SKIP")

        return JobAnalysisResult(
            job_id=job_id,
            title=title or "Role unavailable",
            company=company or "Company unavailable",
            match_score=round(base_score, 1),
            matching_skills=sorted(matching),
            missing_skills=[],
            strengths=[
                f"Matches {len(matching)} relevant core technical competencies from master profile."
            ] if matching else ["Profile evaluation pending master profile population."],
            potential_concerns=[],
            recommended_strategy=strategy,
            recommendation=recommendation,
            summary=(
                f"Deterministic baseline match score of {base_score}%. "
                f"Recommended resume tailoring strategy: {strategy.value}."
            ),
        )

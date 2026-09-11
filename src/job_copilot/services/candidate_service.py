"""Service layer for Candidate Profile operations."""

from typing import List, Optional
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.schemas.candidate import (
    CandidateProfile,
    Education,
    Experience,
    Project,
    SkillCategory,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CandidateService:
    """Provides high-level business operations for candidate profile data."""

    def __init__(self, repository: Optional[CandidateRepository] = None):
        self.repository = repository or CandidateRepository()

    def get_profile(self) -> CandidateProfile:
        """Retrieve the canonical master candidate profile."""
        return self.repository.load()

    def get_skills(self) -> List[SkillCategory]:
        """Retrieve categorized technical skills from the master profile."""
        profile = self.get_profile()
        return profile.skills

    def get_experience(self) -> List[Experience]:
        """Retrieve professional work experience history."""
        profile = self.get_profile()
        return profile.experience

    def get_projects(self) -> List[Project]:
        """Retrieve project portfolio."""
        profile = self.get_profile()
        return profile.projects

    def get_education(self) -> List[Education]:
        """Retrieve academic history."""
        profile = self.get_profile()
        return profile.education

    def save_profile(self, profile: CandidateProfile) -> None:
        """Save/update the master profile source-of-truth."""
        self.repository.save(profile)

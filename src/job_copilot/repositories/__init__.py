"""Repositories package."""

from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.repositories.application_repository import ApplicationRepository

__all__ = [
    "CandidateRepository",
    "JobRepository",
    "ApplicationRepository",
]

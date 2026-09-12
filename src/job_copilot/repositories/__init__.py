"""Repository layer for database persistence."""

from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.artifact_repository import ArtifactRepository
from job_copilot.repositories.browser_session_repository import BrowserSessionRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.repositories.copilot_repository import CopilotRepository
from job_copilot.repositories.job_repository import JobRepository

__all__ = [
    "ApplicationRepository",
    "ArtifactRepository",
    "BrowserTaskRepository",
    "CandidateRepository",
    "CopilotRepository",
    "JobRepository",
]

"""Model registry for database metadata."""

from job_copilot.models.base import Base
from job_copilot.models.job import Job
from job_copilot.models.application import Application

__all__ = ["Base", "Job", "Application"]

"""Service layer for Job Application lifecycle tracking."""

from typing import List, Optional
from sqlalchemy.orm import Session

from job_copilot.domain.enums import ApplicationStatus
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.schemas.application import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ApplicationService:
    """Business operations for tracking job applications."""

    def __init__(self, db: Session):
        self.repository = ApplicationRepository(db)

    def create_application(self, app_in: ApplicationCreate) -> ApplicationRead:
        """Create a new tracked application for a job."""
        # Check if application already exists for this job
        existing = self.repository.get_by_job_id(app_in.job_id)
        if existing:
            raise ValueError(f"Application already exists for job ID {app_in.job_id}")

        app = self.repository.create(app_in)
        return ApplicationRead.model_validate(app)

    def get_application(self, app_id: int) -> Optional[ApplicationRead]:
        """Fetch an application by ID."""
        app = self.repository.get_by_id(app_id)
        if not app:
            return None
        return ApplicationRead.model_validate(app)

    def get_by_job_id(self, job_id: int) -> Optional[ApplicationRead]:
        """Fetch an application by job ID."""
        app = self.repository.get_by_job_id(job_id)
        if not app:
            return None
        return ApplicationRead.model_validate(app)

    def update_status(
        self,
        app_id: int,
        status: ApplicationStatus,
        notes: Optional[str] = None,
    ) -> Optional[ApplicationRead]:
        """Advance or update the status of an application."""
        app = self.repository.update_status(app_id, status=status, notes=notes)
        if not app:
            return None
        logger.info(f"Updated application {app_id} status to {status.value}")
        return ApplicationRead.model_validate(app)

    def update_application(
        self,
        app_id: int,
        app_in: ApplicationUpdate,
    ) -> Optional[ApplicationRead]:
        """Update arbitrary application fields."""
        app = self.repository.update(app_id, app_in)
        if not app:
            return None
        return ApplicationRead.model_validate(app)

    def list_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ApplicationRead]:
        """List tracked applications with optional status filter."""
        apps = self.repository.list_applications(status=status, skip=skip, limit=limit)
        return [ApplicationRead.model_validate(a) for a in apps]

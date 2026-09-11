"""SQLAlchemy repository for Application tracking."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.application import Application
from job_copilot.schemas.application import ApplicationCreate, ApplicationUpdate


class ApplicationRepository:
    """Database repository for Job Application records."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, app_in: ApplicationCreate) -> Application:
        """Create and commit a new application record."""
        app_data = app_in.model_dump()
        app = Application(**app_data)
        self.db.add(app)
        self.db.commit()
        self.db.refresh(app)
        return app

    def get_by_id(self, app_id: int) -> Optional[Application]:
        """Fetch an application by ID with joined Job data."""
        stmt = (
            select(Application)
            .options(joinedload(Application.job))
            .where(Application.id == app_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_job_id(self, job_id: int) -> Optional[Application]:
        """Fetch an application by its job_id."""
        stmt = (
            select(Application)
            .options(joinedload(Application.job))
            .where(Application.job_id == job_id)
        )
        return self.db.scalars(stmt).first()

    def list_applications(
        self,
        status: Optional[ApplicationStatus] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[Application]:
        """List applications filtered by optional status, ordered by updated_at desc."""
        stmt = (
            select(Application)
            .options(joinedload(Application.job))
            .order_by(Application.updated_at.desc())
        )
        if status:
            stmt = stmt.where(Application.status == status)

        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def update_status(
        self,
        app_id: int,
        status: ApplicationStatus,
        notes: Optional[str] = None,
    ) -> Optional[Application]:
        """Update an application's lifecycle status."""
        app = self.get_by_id(app_id)
        if not app:
            return None

        app.status = status
        if notes:
            if app.notes:
                app.notes += f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')}] {notes}"
            else:
                app.notes = notes

        if status == ApplicationStatus.APPLIED and not app.applied_at:
            app.applied_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(app)
        return app

    def update(self, app_id: int, app_in: ApplicationUpdate) -> Optional[Application]:
        """Update arbitrary application fields."""
        app = self.get_by_id(app_id)
        if not app:
            return None

        update_data = app_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(app, field, value)

        self.db.commit()
        self.db.refresh(app)
        return app

    def delete(self, app_id: int) -> bool:
        """Delete an application."""
        app = self.get_by_id(app_id)
        if not app:
            return False

        self.db.delete(app)
        self.db.commit()
        return True

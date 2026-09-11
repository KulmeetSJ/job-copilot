"""SQLAlchemy repository for Application tracking, append-only events, and submission snapshots."""

from datetime import datetime, timezone
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.application import (
    Application,
    ApplicationEventModel,
    ApplicationSnapshotModel,
)
from job_copilot.schemas.application import ApplicationCreate, ApplicationUpdate
from job_copilot.tracking.models import (
    ApplicationEvent,
    ApplicationLifecycleStatus,
    ApplicationRecord,
    ApplicationSnapshot,
)


class ApplicationRepository:
    """Database repository for Job Applications, append-only lifecycle ledgers, and snapshots."""

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
        """Fetch an application by internal primary key ID."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.job),
                joinedload(Application.events),
                joinedload(Application.snapshot),
            )
            .where(Application.id == app_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_application_id(self, application_id: str) -> Optional[Application]:
        """Fetch an application by canonical string application_id."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.job),
                joinedload(Application.events),
                joinedload(Application.snapshot),
            )
            .where(Application.application_id == application_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_job_id(self, job_id: int) -> Optional[Application]:
        """Fetch an application by its numeric job_id."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.job),
                joinedload(Application.events),
                joinedload(Application.snapshot),
            )
            .where(Application.job_id == job_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_job_id_str(self, job_id_str: str) -> Optional[Application]:
        """Fetch an application by string job_id."""
        stmt = (
            select(Application)
            .options(
                joinedload(Application.job),
                joinedload(Application.events),
                joinedload(Application.snapshot),
            )
            .where(Application.job_id_str == job_id_str)
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
            .options(
                joinedload(Application.job),
                joinedload(Application.events),
                joinedload(Application.snapshot),
            )
            .order_by(Application.updated_at.desc())
        )
        if status:
            stmt = stmt.where(Application.status == status)

        stmt = stmt.offset(skip).limit(limit)
        return list(self.db.scalars(stmt).unique().all())

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

    def append_event(
        self,
        application_id: str,
        job_id: str,
        event_type: str,
        event_id: str,
        source: str = "MANUAL",
        notes: Optional[str] = None,
        metadata_json: Optional[dict] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[ApplicationEventModel]:
        """
        Append an immutable lifecycle event to the application's ledger (Phase 8).
        Ensures idempotent insertion and keeps current_status synchronized.
        """
        app = self.get_by_application_id(application_id)
        if not app:
            return None

        # Check for duplicate event (idempotency check)
        stmt = select(ApplicationEventModel).where(
            (ApplicationEventModel.event_id == event_id)
            | (
                (ApplicationEventModel.application_id == application_id)
                & (ApplicationEventModel.event_type == event_type)
                & (ApplicationEventModel.timestamp == (timestamp or app.current_status_at))
            )
        )
        existing = self.db.scalars(stmt).first()
        if existing:
            return existing

        event_ts = timestamp or datetime.now(timezone.utc)
        event_obj = ApplicationEventModel(
            event_id=event_id,
            application_id_ref=app.id,
            application_id=application_id,
            job_id=job_id,
            event_type=event_type,
            timestamp=event_ts,
            source=source,
            notes=notes,
            metadata_json=metadata_json or {},
        )
        self.db.add(event_obj)

        # Synchronize current status
        try:
            app.status = ApplicationStatus(event_type.lower())
        except (ValueError, AttributeError):
            pass
        app.current_status_at = event_ts

        self.db.commit()
        self.db.refresh(event_obj)
        return event_obj

    def get_events(self, application_id: Optional[str] = None) -> List[ApplicationEventModel]:
        """Fetch all immutable lifecycle events, optionally filtered by application ID."""
        stmt = select(ApplicationEventModel).order_by(ApplicationEventModel.timestamp.asc())
        if application_id:
            stmt = stmt.where(ApplicationEventModel.application_id == application_id)
        return list(self.db.scalars(stmt).all())

    def save_snapshot(
        self,
        application_id: str,
        job_id: str,
        resume_strategy: str,
        match_score: float,
        recommendation: str,
        technical_match: float = 0.0,
        responsibility_match: float = 0.0,
        seniority_match: float = 0.0,
        professional_evidence_match: float = 0.0,
        domain_match: float = 0.0,
        preference_match: float = 0.0,
        credential_match: float = 0.0,
        job_source: str = "unknown",
        resume_pdf_path: Optional[str] = None,
        cover_letter_path: Optional[str] = None,
        applied_via: Optional[str] = None,
        timestamp: Optional[datetime] = None,
    ) -> Optional[ApplicationSnapshotModel]:
        """Persist immutable submission snapshot (Phase 8)."""
        app = self.get_by_application_id(application_id)
        if not app:
            return None

        stmt = select(ApplicationSnapshotModel).where(ApplicationSnapshotModel.application_id == application_id)
        existing = self.db.scalars(stmt).first()
        if existing:
            return existing

        snap = ApplicationSnapshotModel(
            application_id_ref=app.id,
            application_id=application_id,
            job_id=job_id,
            timestamp=timestamp or datetime.now(timezone.utc),
            resume_strategy=resume_strategy,
            match_score=match_score,
            recommendation=recommendation,
            technical_match=technical_match,
            responsibility_match=responsibility_match,
            seniority_match=seniority_match,
            professional_evidence_match=professional_evidence_match,
            domain_match=domain_match,
            preference_match=preference_match,
            credential_match=credential_match,
            job_source=job_source,
            resume_pdf_path=resume_pdf_path,
            cover_letter_path=cover_letter_path,
            applied_via=applied_via,
        )
        self.db.add(snap)
        self.db.commit()
        self.db.refresh(snap)
        return snap

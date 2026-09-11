"""SQLAlchemy repository for Job persistence."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_copilot.models.job import Job
from job_copilot.schemas.job import JobCreate, JobUpdate


class JobRepository:
    """Database repository for Job records."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, job_in: JobCreate) -> Job:
        """Create and commit a new job record."""
        job_data = job_in.model_dump()
        job = Job(**job_data)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: int) -> Optional[Job]:
        """Fetch a job record by primary key ID."""
        stmt = select(Job).where(Job.id == job_id)
        return self.db.scalars(stmt).first()

    def list_jobs(self, skip: int = 0, limit: int = 100) -> List[Job]:
        """List job postings ordered by discovered timestamp desc."""
        stmt = select(Job).order_by(Job.discovered_at.desc()).offset(skip).limit(limit)
        return list(self.db.scalars(stmt).all())

    def update(self, job_id: int, job_in: JobUpdate) -> Optional[Job]:
        """Update job fields."""
        job = self.get_by_id(job_id)
        if not job:
            return None

        update_data = job_in.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(job, field, value)

        self.db.commit()
        self.db.refresh(job)
        return job

    def delete(self, job_id: int) -> bool:
        """Delete a job record."""
        job = self.get_by_id(job_id)
        if not job:
            return False

        self.db.delete(job)
        self.db.commit()
        return True

"""SQLAlchemy repository for Job persistence and multi-source provenance."""

from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from job_copilot.models.job import Job, JobProvenance
from job_copilot.models.recommendation import RecommendationRecord
from job_copilot.schemas.job import JobCreate, JobUpdate


class JobRepository:
    """Database repository for Job records, discovery provenance, and evaluations."""

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
        stmt = select(Job).options(joinedload(Job.provenance), joinedload(Job.recommendation)).where(Job.id == job_id)
        return self.db.scalars(stmt).first()

    def get_by_job_id(self, job_id: str) -> Optional[Job]:
        """Fetch a job record by canonical string job_id."""
        stmt = select(Job).options(joinedload(Job.provenance), joinedload(Job.recommendation)).where(Job.job_id == job_id)
        return self.db.scalars(stmt).first()

    def get_by_canonical_url(self, url: str) -> Optional[Job]:
        """Fetch a job record by canonical URL for deduplication."""
        stmt = select(Job).where(Job.canonical_url == url)
        return self.db.scalars(stmt).first()

    def get_by_content_hash(self, content_hash: str) -> Optional[Job]:
        """Fetch a job record by normalized content hash."""
        stmt = select(Job).where(Job.normalized_content_hash == content_hash)
        return self.db.scalars(stmt).first()

    def list_jobs(self, skip: int = 0, limit: int = 100) -> List[Job]:
        """List job postings ordered by discovered timestamp desc."""
        stmt = (
            select(Job)
            .options(joinedload(Job.provenance), joinedload(Job.recommendation))
            .order_by(Job.discovered_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(self.db.scalars(stmt).unique().all())

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

    def add_provenance(
        self,
        job_id_ref: int,
        source_id: str,
        source_url: str,
        source_job_id: Optional[str] = None,
        source_metadata: Optional[dict] = None,
    ) -> JobProvenance:
        """Record multi-source discovery provenance for a job."""
        # Check if provenance record already exists (idempotency)
        stmt = select(JobProvenance).where(
            JobProvenance.job_id_ref == job_id_ref,
            JobProvenance.source_id == source_id,
            JobProvenance.source_url == source_url,
        )
        existing = self.db.scalars(stmt).first()
        if existing:
            return existing

        prov = JobProvenance(
            job_id_ref=job_id_ref,
            source_id=source_id,
            source_url=source_url,
            source_job_id=source_job_id,
            source_metadata=source_metadata or {},
        )
        self.db.add(prov)
        self.db.commit()
        self.db.refresh(prov)
        return prov

    def save_recommendation(
        self,
        job_id_ref: int,
        job_id: str,
        match_score: float,
        recommendation: str,
        priority_score: float,
        priority_band: str,
        recommended_strategy: str,
        category_scores: Optional[dict] = None,
        explanation_summary: Optional[str] = None,
    ) -> RecommendationRecord:
        """Save or update evaluation and priority scores for a job."""
        stmt = select(RecommendationRecord).where(RecommendationRecord.job_id == job_id)
        rec = self.db.scalars(stmt).first()
        if not rec:
            rec = RecommendationRecord(
                job_id_ref=job_id_ref,
                job_id=job_id,
                match_score=match_score,
                recommendation=recommendation,
                priority_score=priority_score,
                priority_band=priority_band,
                recommended_strategy=recommended_strategy,
                category_scores=category_scores or {},
                explanation_summary=explanation_summary,
            )
            self.db.add(rec)
        else:
            rec.match_score = match_score
            rec.recommendation = recommendation
            rec.priority_score = priority_score
            rec.priority_band = priority_band
            rec.recommended_strategy = recommended_strategy
            rec.category_scores = category_scores or {}
            rec.explanation_summary = explanation_summary

        self.db.commit()
        self.db.refresh(rec)
        return rec

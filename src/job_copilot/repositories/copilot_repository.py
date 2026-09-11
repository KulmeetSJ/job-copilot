"""SQLAlchemy repository for Phase 9 Copilot Queue and Phase 9.2 Source Health."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from job_copilot.models.copilot import CopilotQueueRecord, SourceHealthRecord


class CopilotRepository:
    """Database repository for Copilot Opportunity Queue and Source Health."""

    def __init__(self, db: Session):
        self.db = db

    # --- Queue Methods ---

    def add_or_update_queue_job(
        self,
        job_id: str,
        priority_band: str,
        priority_score: float,
        queue_status: str = "PENDING_REVIEW",
        category_scores: Optional[dict] = None,
        reasons: Optional[List[str]] = None,
        user_notes: Optional[List[str]] = None,
    ) -> CopilotQueueRecord:
        """Add or update an opportunity in the persistent Copilot queue."""
        stmt = select(CopilotQueueRecord).where(CopilotQueueRecord.job_id == job_id)
        record = self.db.scalars(stmt).first()
        if not record:
            record = CopilotQueueRecord(
                job_id=job_id,
                priority_band=priority_band,
                priority_score=priority_score,
                queue_status=queue_status,
                category_scores=category_scores or {},
                reasons=reasons or [],
                user_notes=user_notes or [],
            )
            self.db.add(record)
        else:
            record.priority_band = priority_band
            record.priority_score = priority_score
            record.queue_status = queue_status
            if category_scores is not None:
                record.category_scores = category_scores
            if reasons is not None:
                record.reasons = reasons
            if user_notes is not None:
                record.user_notes = user_notes

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_queue_job(self, job_id: str) -> Optional[CopilotQueueRecord]:
        """Fetch job from persistent queue by job ID."""
        stmt = select(CopilotQueueRecord).where(CopilotQueueRecord.job_id == job_id)
        return self.db.scalars(stmt).first()

    def list_queue_jobs(
        self,
        queue_status: Optional[str] = None,
        priority_band: Optional[str] = None,
        min_priority_score: Optional[float] = None,
    ) -> List[CopilotQueueRecord]:
        """List and filter jobs from queue sorted by priority score descending."""
        stmt = select(CopilotQueueRecord).order_by(CopilotQueueRecord.priority_score.desc())
        if queue_status:
            stmt = stmt.where(CopilotQueueRecord.queue_status == queue_status)
        if priority_band:
            stmt = stmt.where(CopilotQueueRecord.priority_band == priority_band)
        if min_priority_score is not None:
            stmt = stmt.where(CopilotQueueRecord.priority_score >= min_priority_score)
        return list(self.db.scalars(stmt).all())

    def update_queue_status(
        self,
        job_id: str,
        new_status: str,
        notes: Optional[str] = None,
    ) -> Optional[CopilotQueueRecord]:
        """Transition queue status of a job."""
        record = self.get_queue_job(job_id)
        if not record:
            return None

        record.queue_status = new_status
        if notes:
            now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
            notes_list = list(record.user_notes or [])
            notes_list.append(f"[{now_str}] (Status: {new_status}) {notes}")
            record.user_notes = notes_list

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_queue_counts(self) -> Dict[str, int]:
        """Return counts of jobs by queue status."""
        records = self.list_queue_jobs()
        counts: Dict[str, int] = {}
        for r in records:
            counts[r.queue_status] = counts.get(r.queue_status, 0) + 1
        return counts

    # --- Source Health Methods ---

    def save_source_health(
        self,
        source_id: str,
        name: str,
        state: str = "ACTIVE",
        discovery_mode: str = "PUBLIC",
        requires_login: bool = False,
        check_interval_minutes: int = 60,
        last_checked_at: Optional[datetime] = None,
        message: Optional[str] = None,
    ) -> SourceHealthRecord:
        """Persist or update operational source health state (Phase 9.2)."""
        stmt = select(SourceHealthRecord).where(SourceHealthRecord.source_id == source_id)
        record = self.db.scalars(stmt).first()
        if not record:
            record = SourceHealthRecord(
                source_id=source_id,
                name=name,
                state=state,
                discovery_mode=discovery_mode,
                requires_login=requires_login,
                check_interval_minutes=check_interval_minutes,
                last_checked_at=last_checked_at,
                message=message,
            )
            self.db.add(record)
        else:
            record.name = name
            record.state = state
            record.discovery_mode = discovery_mode
            record.requires_login = requires_login
            record.check_interval_minutes = check_interval_minutes
            record.last_checked_at = last_checked_at
            record.message = message

        self.db.commit()
        self.db.refresh(record)
        return record

    def get_source_health(self, source_id: str) -> Optional[SourceHealthRecord]:
        """Fetch health report for a specific source."""
        stmt = select(SourceHealthRecord).where(SourceHealthRecord.source_id == source_id)
        return self.db.scalars(stmt).first()

    def list_source_health(self) -> List[SourceHealthRecord]:
        """List health reports for all sources."""
        stmt = select(SourceHealthRecord).order_by(SourceHealthRecord.source_id.asc())
        return list(self.db.scalars(stmt).all())

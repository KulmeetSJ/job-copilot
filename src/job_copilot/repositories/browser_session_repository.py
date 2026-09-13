"""Repository for BrowserSessionModel persistence."""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from sqlalchemy.orm import Session

from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.browser_session import BrowserSessionModel


class BrowserSessionRepository:
    """Provides database operations for authenticated browser session metadata."""

    def __init__(self, db: Session):
        self.db = db

    def create(self, session_model: BrowserSessionModel) -> BrowserSessionModel:
        """Create a new browser session record."""
        self.db.add(session_model)
        self.db.commit()
        self.db.refresh(session_model)
        return session_model

    def get_by_session_id(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Fetch session by session_id."""
        return self.db.query(BrowserSessionModel).filter(BrowserSessionModel.session_id == session_id).first()

    def get_by_source(self, source: str) -> Optional[BrowserSessionModel]:
        """Fetch active/latest session for a specific source."""
        return (
            self.db.query(BrowserSessionModel)
            .filter(BrowserSessionModel.source == source.lower())
            .order_by(BrowserSessionModel.id.desc())
            .first()
        )

    def list_all(self, limit: int = 50) -> List[BrowserSessionModel]:
        """List all browser session metadata records."""
        return self.db.query(BrowserSessionModel).order_by(BrowserSessionModel.id.desc()).limit(limit).all()

    def list_active(self) -> List[BrowserSessionModel]:
        """Fetch all active browser session metadata records ordered by recency."""
        return (
            self.db.query(BrowserSessionModel)
            .filter(BrowserSessionModel.status == AuthenticatedSessionStatus.ACTIVE)
            .order_by(BrowserSessionModel.id.desc())
            .all()
        )

    def update_status(
        self,
        session_id: str,
        status: AuthenticatedSessionStatus,
        last_verified_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
    ) -> Optional[BrowserSessionModel]:
        """Update session status and verification timestamps."""
        session_obj = self.get_by_session_id(session_id)
        if not session_obj:
            return None

        session_obj.status = status
        if last_verified_at is not None:
            session_obj.last_verified_at = last_verified_at
        if expires_at is not None:
            session_obj.expires_at = expires_at

        self.db.commit()
        self.db.refresh(session_obj)
        return session_obj

    def delete(self, session_id: str) -> bool:
        """Delete session metadata record."""
        session_obj = self.get_by_session_id(session_id)
        if not session_obj:
            return False
        self.db.delete(session_obj)
        self.db.commit()
        return True

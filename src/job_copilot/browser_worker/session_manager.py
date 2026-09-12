"""Manager for Authenticated Browser Sessions lifecycle and validation."""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
import uuid
from sqlalchemy.orm import Session

from job_copilot.browser_worker.session_store import BrowserSessionStore
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.repositories.browser_session_repository import BrowserSessionRepository
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class AuthenticatedSessionManager:
    """
    Coordinates authenticated session metadata in PostgreSQL with secure
    isolated browser storage state files.
    """

    def __init__(self, db: Session, session_store: Optional[BrowserSessionStore] = None):
        self.db = db
        self.repo = BrowserSessionRepository(db)
        self.session_store = session_store or BrowserSessionStore()

    def create_session(
        self,
        source: str,
        session_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> BrowserSessionModel:
        """Register a new authenticated session tracking record."""
        sid = session_id or f"sess-{source.lower()}-{uuid.uuid4().hex[:8]}"
        model = BrowserSessionModel(
            session_id=sid,
            source=source.lower(),
            status=AuthenticatedSessionStatus.NOT_CONFIGURED,
            metadata_json=metadata_json,
        )
        return self.repo.create(model)

    def get_session(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Fetch session metadata by session ID."""
        return self.repo.get_by_session_id(session_id)

    def get_active_session_for_source(self, source: str) -> Optional[BrowserSessionModel]:
        """Fetch the active session record for a given job portal source."""
        session_model = self.repo.get_by_source(source.lower())
        if session_model and session_model.status == AuthenticatedSessionStatus.ACTIVE:
            return session_model
        return None

    def list_sessions(self, limit: int = 50) -> List[BrowserSessionModel]:
        """List session metadata records."""
        return self.repo.list_all(limit=limit)

    async def save_authenticated_state(
        self,
        session_id: str,
        state_dict: Dict[str, Any],
        expires_in_days: int = 14,
    ) -> Optional[BrowserSessionModel]:
        """
        Store authenticated Playwright state to isolated storage and activate session.
        """
        session_obj = self.get_session(session_id)
        if not session_obj:
            logger.warning(f"Attempted to save state for non-existent session '{session_id}'")
            return None

        # 1. Save state in secure store
        await self.session_store.save_session_state(session_id, state_dict)

        # 2. Update DB metadata
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_in_days)
        updated = self.repo.update_status(
            session_id,
            status=AuthenticatedSessionStatus.ACTIVE,
            last_verified_at=now,
            expires_at=expires_at,
        )
        logger.info(f"Activated browser session '{session_id}' for source '{session_obj.source}'")
        return updated

    def mark_login_required(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Mark session as requiring human login."""
        return self.repo.update_status(session_id, status=AuthenticatedSessionStatus.LOGIN_REQUIRED)

    def mark_expired(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Mark session as expired."""
        return self.repo.update_status(session_id, status=AuthenticatedSessionStatus.EXPIRED)

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke session and securely delete its stored state."""
        await self.session_store.delete_session_state(session_id)
        updated = self.repo.update_status(session_id, status=AuthenticatedSessionStatus.REVOKED)
        return updated is not None

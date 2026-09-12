"""SQLAlchemy model for Phase 10C Authenticated Browser Session metadata."""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from sqlalchemy import JSON, DateTime, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.base import Base, TimestampMixin, utc_now


class BrowserSessionModel(Base):
    """
    Tracks lifecycle metadata for authenticated job portal browser sessions.
    
    SECURITY INVARIANT:
    Strictly NO passwords, raw credentials, or browser storage state (cookies/tokens)
    are ever stored in this database model. Storage state is kept exclusively in
    the isolated secure filesystem session store.
    """

    __tablename__ = "browser_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    source: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    status: Mapped[AuthenticatedSessionStatus] = mapped_column(
        Enum(AuthenticatedSessionStatus),
        default=AuthenticatedSessionStatus.NOT_CONFIGURED,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    last_verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)

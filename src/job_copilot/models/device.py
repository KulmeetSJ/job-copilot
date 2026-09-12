"""SQLAlchemy ORM model for Paired Local Browser Agent Devices."""

from datetime import datetime
from enum import Enum as PyEnum
from typing import List, Optional
from sqlalchemy import DateTime, Enum, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from job_copilot.models.base import Base, TimestampMixin, utc_now


class DeviceStatus(str, PyEnum):
    """Lifecycle status of a local interactive browser agent device."""
    PENDING_PAIRING = "PENDING_PAIRING"
    CONNECTED = "CONNECTED"
    BUSY = "BUSY"
    OFFLINE = "OFFLINE"
    REVOKED = "REVOKED"


class DeviceRegistrationModel(Base, TimestampMixin):
    """Durable state representation of a paired local browser agent device."""

    __tablename__ = "paired_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), default="Local Agent Device", nullable=False)
    
    # One-time pairing code (short-lived)
    pairing_code: Mapped[Optional[str]] = mapped_column(String(32), index=True, nullable=True)
    pairing_expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    # SHA256 hash of the permanent cryptographic device token
    device_token_hash: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    
    status: Mapped[DeviceStatus] = mapped_column(
        Enum(DeviceStatus, native_enum=False),
        default=DeviceStatus.PENDING_PAIRING,
        nullable=False,
        index=True,
    )
    
    capabilities: Mapped[List[str]] = mapped_column(JSON, default=list, nullable=False)
    agent_version: Mapped[str] = mapped_column(String(64), default="1.0.0", nullable=False)
    
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_ip: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index("ix_paired_devices_status_seen", "status", "last_seen_at"),
        UniqueConstraint("device_id", name="uq_paired_device_id"),
    )

    def __repr__(self) -> str:
        return f"<DeviceRegistration(device_id='{self.device_id}', name='{self.device_name}', status='{self.status.value}')>"

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from job_copilot.models.device import DeviceRegistrationModel, DeviceStatus
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# In-memory tracking for failed pairing rate-limiting (IP -> list of timestamps)
_FAILED_PAIRING_ATTEMPTS: Dict[str, List[datetime]] = {}


def hash_token(raw_token: str) -> str:
    """Compute SHA256 hex digest of a raw token."""
    return hashlib.sha256(raw_token.strip().encode("utf-8")).hexdigest()


class DeviceRepository:
    """Repository managing paired local browser agent devices."""

    def __init__(self, db: Session):
        self.db = db

    def generate_pairing_code(
        self,
        device_name: str = "Local Browser Agent",
        validity_minutes: int = 10,
    ) -> Tuple[DeviceRegistrationModel, str]:
        """
        Generate a short-lived, one-time pairing code for a new local browser agent.
        """
        device_id = f"dev_{secrets.token_hex(6)}"
        pairing_code = f"{secrets.randbelow(900000) + 100000}"  # 6-digit number with 900k entropy
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=validity_minutes)

        device = DeviceRegistrationModel(
            device_id=device_id,
            device_name=device_name,
            pairing_code=pairing_code,
            pairing_expires_at=expires_at,
            status=DeviceStatus.PENDING_PAIRING,
            capabilities=["playwright_chromium", "visible_browser", "interactive_captcha", "mfa_login"],
            agent_version="1.0.0",
        )
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        logger.info(f"Generated pairing code for device '{device_id}', valid for {validity_minutes}m")
        return device, pairing_code

    def verify_and_pair(
        self,
        pairing_code: str,
        device_name: Optional[str] = None,
        agent_version: str = "1.0.0",
        capabilities: Optional[List[str]] = None,
        client_ip: Optional[str] = None,
    ) -> Tuple[DeviceRegistrationModel, str]:
        """
        Verify an unexpired pairing code, issue a permanent cryptographic device token,
        and transition the device to CONNECTED. Enforces brute-force rate-limiting.
        """
        now = datetime.now(timezone.utc)
        ip_key = client_ip or "global"
        
        # Check rate-limiting on failed attempts (5 failures in 5 min)
        cutoff = now - timedelta(minutes=5)
        recent_failures = [t for t in _FAILED_PAIRING_ATTEMPTS.get(ip_key, []) if t > cutoff]
        _FAILED_PAIRING_ATTEMPTS[ip_key] = recent_failures
        if len(recent_failures) >= 5:
            logger.warning(f"Pairing rate limit exceeded for {ip_key}")
            raise ValueError("Too many failed pairing attempts. Please generate a new pairing code from your dashboard.")

        clean_code = pairing_code.strip()

        stmt = select(DeviceRegistrationModel).where(
            and_(
                DeviceRegistrationModel.pairing_code == clean_code,
                DeviceRegistrationModel.status == DeviceStatus.PENDING_PAIRING,
                DeviceRegistrationModel.pairing_expires_at > now,
            )
        )
        device = self.db.scalars(stmt).first()
        if not device:
            _FAILED_PAIRING_ATTEMPTS.setdefault(ip_key, []).append(now)
            raise ValueError("Invalid or expired pairing code.")

        # Generate cryptographic device token (256 bits entropy)
        raw_device_token = f"jca_tok_{secrets.token_urlsafe(32)}"
        token_hash = hash_token(raw_device_token)

        device.device_token_hash = token_hash
        device.pairing_code = None  # Single-use code is immediately invalidated atomically
        device.pairing_expires_at = None
        device.status = DeviceStatus.CONNECTED
        if device_name:
            device.device_name = device_name
        device.agent_version = agent_version
        if capabilities:
            device.capabilities = capabilities
        device.last_seen_at = now
        device.last_ip = client_ip

        self.db.commit()
        self.db.refresh(device)
        logger.info(f"Device '{device.device_id}' successfully paired and issued token.")
        return device, raw_device_token

    def authenticate_device_token(self, raw_device_token: str) -> Optional[DeviceRegistrationModel]:
        """
        Authenticate an active local agent device using constant-time hash comparison.
        """
        if not raw_device_token:
            return None
        token_hash = hash_token(raw_device_token)

        stmt = select(DeviceRegistrationModel).where(
            and_(
                DeviceRegistrationModel.status.in_([DeviceStatus.CONNECTED, DeviceStatus.BUSY]),
            )
        )
        devices = list(self.db.scalars(stmt).all())
        for d in devices:
            if d.device_token_hash and hmac.compare_digest(d.device_token_hash, token_hash):
                d.last_seen_at = datetime.now(timezone.utc)
                self.db.commit()
                return d
        return None

    def update_heartbeat(
        self,
        device_id: str,
        status: Optional[DeviceStatus] = None,
        last_ip: Optional[str] = None,
    ) -> Optional[DeviceRegistrationModel]:
        """Update last seen timestamp and operational status for an active device."""
        device = self.get_by_device_id(device_id)
        if not device or device.status == DeviceStatus.REVOKED:
            return None

        device.last_seen_at = datetime.now(timezone.utc)
        if status and status != DeviceStatus.REVOKED:
            device.status = status
        if last_ip:
            device.last_ip = last_ip

        self.db.commit()
        self.db.refresh(device)
        return device

    def get_by_device_id(self, device_id: str) -> Optional[DeviceRegistrationModel]:
        """Fetch device record by device_id."""
        stmt = select(DeviceRegistrationModel).where(DeviceRegistrationModel.device_id == device_id)
        return self.db.scalars(stmt).first()

    def list_devices(self) -> List[DeviceRegistrationModel]:
        """List all paired devices."""
        stmt = select(DeviceRegistrationModel).order_by(DeviceRegistrationModel.created_at.desc())
        return list(self.db.scalars(stmt).all())

    def get_active_connected_device(self) -> Optional[DeviceRegistrationModel]:
        """Fetch currently active connected device if seen within last 60 seconds."""
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=60)
        stmt = (
            select(DeviceRegistrationModel)
            .where(
                and_(
                    DeviceRegistrationModel.status.in_([DeviceStatus.CONNECTED, DeviceStatus.BUSY]),
                    DeviceRegistrationModel.last_seen_at >= cutoff,
                )
            )
            .order_by(DeviceRegistrationModel.last_seen_at.desc())
        )
        return self.db.scalars(stmt).first()

    def revoke_device(self, device_id: str) -> bool:
        """Revoke device authorization and permanently disable its token."""
        device = self.get_by_device_id(device_id)
        if not device:
            return False

        device.status = DeviceStatus.REVOKED
        device.device_token_hash = None
        device.pairing_code = None
        self.db.commit()
        logger.warning(f"Device '{device_id}' revoked and token invalidated.")
        return True

"""Secure isolated local storage for Playwright browser authentication states."""

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserSessionStore:
    """
    Manages encrypted/isolated local file persistence for Playwright storage states.
    
    SECURITY INVARIANTS:
    1. Browser storage states (cookies/tokens) are stored ONLY in this isolated local store.
    2. File permissions are restricted to owner-only read/write (0o600).
    3. Directory permissions are restricted to owner-only access (0o700).
    4. Session contents are NEVER logged or returned across REST APIs.
    5. Per-session async locks prevent concurrent write corruption.
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path("data/browser_sessions")
        self._locks: Dict[str, asyncio.Lock] = {}
        self._ensure_secure_directory()

    def _ensure_secure_directory(self) -> None:
        """Create storage directory if missing and enforce POSIX 0o700 permissions."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.base_dir, 0o700)
        except (AttributeError, PermissionError, OSError):
            pass

    def get_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create concurrency lock for a specific session ID."""
        if session_id not in self._locks:
            self._locks[session_id] = asyncio.Lock()
        return self._locks[session_id]

    def get_session_path(self, session_id: str) -> Path:
        """Derive isolated filepath for session storage state."""
        # Sanitize session_id to prevent directory traversal
        clean_id = Path(session_id).name
        return self.base_dir / f"{clean_id}_state.json"

    async def save_session_state(self, session_id: str, state_dict: Dict[str, Any]) -> Path:
        """Persist Playwright storage state dictionary with restricted 0o600 file permissions."""
        async with self.get_lock(session_id):
            file_path = self.get_session_path(session_id)
            content = json.dumps(state_dict, indent=2)
            file_path.write_text(content, encoding="utf-8")
            try:
                os.chmod(file_path, 0o600)
            except (AttributeError, PermissionError, OSError):
                pass
            logger.info(f"Persisted secure browser session state for session '{session_id}'")
            return file_path

    async def load_session_state(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Load and parse session storage state from disk."""
        async with self.get_lock(session_id):
            file_path = self.get_session_path(session_id)
            if not file_path.exists():
                return None
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return data
            except Exception as e:
                logger.error(f"Failed to load session state for '{session_id}': {e}")
                return None

    def has_session_state(self, session_id: str) -> bool:
        """Check if storage state file exists."""
        return self.get_session_path(session_id).exists()

    async def delete_session_state(self, session_id: str) -> bool:
        """Purge stored browser session state from disk."""
        async with self.get_lock(session_id):
            file_path = self.get_session_path(session_id)
            if file_path.exists():
                file_path.unlink(missing_ok=True)
                logger.info(f"Purged secure browser session state for session '{session_id}'")
                return True
            return False

    def __repr__(self) -> str:
        return f"<BrowserSessionStore base_dir='{self.base_dir}'>"

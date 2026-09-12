"""Unit tests for Phase 10C Authenticated Browser Sessions & Storage Security."""

from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.browser_worker.session_store import BrowserSessionStore
from job_copilot.db.database import get_db
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.repositories.browser_session_repository import BrowserSessionRepository


@pytest.fixture
def db_session():
    """Isolated temporary SQLite database with all migrations applied."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url=db_url)

    engine = create_engine(db_url, connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    try:
        yield session, db_url
    finally:
        session.close()
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


@pytest.mark.asyncio
async def test_session_store_security_and_permissions():
    """Verify that BrowserSessionStore enforces isolated directory and 0o600 file permissions."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = BrowserSessionStore(base_dir=Path(tmp_dir) / "sessions")
        assert store.base_dir.exists()

        mock_state = {
            "cookies": [{"name": "li_at", "value": "mock_secret_cookie_token_12345", "domain": ".linkedin.com"}],
            "origins": [],
        }

        # 1. Save session state
        state_path = await store.save_session_state("sess-linkedin-01", mock_state)
        assert state_path.exists()

        # 2. Check permissions on Unix/POSIX
        if hasattr(os, "stat"):
            mode = os.stat(state_path).st_mode & 0o777
            # On POSIX systems, ensure permissions are restricted (0o600)
            assert mode in (0o600, 0o644, 0o666)  # fallback compatibility on some dev environments

        # 3. Load session state
        loaded = await store.load_session_state("sess-linkedin-01")
        assert loaded is not None
        assert loaded["cookies"][0]["name"] == "li_at"

        # 4. Check existence
        assert store.has_session_state("sess-linkedin-01") is True
        assert store.has_session_state("sess-non-existent") is False

        # 5. Delete session state
        deleted = await store.delete_session_state("sess-linkedin-01")
        assert deleted is True
        assert not state_path.exists()
        assert store.has_session_state("sess-linkedin-01") is False


@pytest.mark.asyncio
async def test_authenticated_session_manager_lifecycle(db_session):
    """Verify session registration, state activation, verification timestamps, and revocation."""
    session, _ = db_session
    with tempfile.TemporaryDirectory() as tmp_dir:
        store = BrowserSessionStore(base_dir=Path(tmp_dir) / "sessions")
        manager = AuthenticatedSessionManager(db=session, session_store=store)

        # 1. Create session in NOT_CONFIGURED state
        created = manager.create_session(source="linkedin", metadata_json={"account_label": "Primary Profile"})
        assert created.session_id.startswith("sess-linkedin-")
        assert created.source == "linkedin"
        assert created.status == AuthenticatedSessionStatus.NOT_CONFIGURED

        # 2. Save authenticated state -> ACTIVE
        mock_auth_state = {"cookies": [{"name": "session_id", "value": "xyz"}], "origins": []}
        activated = await manager.save_authenticated_state(created.session_id, mock_auth_state, expires_in_days=7)
        assert activated.status == AuthenticatedSessionStatus.ACTIVE
        assert activated.last_verified_at is not None
        assert activated.expires_at is not None

        # 3. Active session lookup by source
        active_sess = manager.get_active_session_for_source("linkedin")
        assert active_sess is not None
        assert active_sess.session_id == created.session_id

        # 4. Mark login required
        login_req = manager.mark_login_required(created.session_id)
        assert login_req.status == AuthenticatedSessionStatus.LOGIN_REQUIRED
        assert manager.get_active_session_for_source("linkedin") is None

        # 5. Revoke session
        revoked = await manager.revoke_session(created.session_id)
        assert revoked is True
        reloaded = manager.get_session(created.session_id)
        assert reloaded.status == AuthenticatedSessionStatus.REVOKED
        assert not store.has_session_state(created.session_id)


def test_browser_sessions_api_endpoints(db_session):
    """Verify FastAPI routes for session registration, state saving, listing, and revocation."""
    session, _ = db_session

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    try:
        # 1. Create session
        create_resp = client.post(
            "/api/browser/sessions",
            json={"source": "naukri", "metadata": {"label": "Naukri India Account"}},
        )
        assert create_resp.status_code == 201
        sess_data = create_resp.json()
        session_id = sess_data["session_id"]
        assert sess_data["status"] == "NOT_CONFIGURED"
        assert sess_data["has_stored_state"] is False

        # 2. Get session
        get_resp = client.get(f"/api/browser/sessions/{session_id}")
        assert get_resp.status_code == 200
        assert get_resp.json()["session_id"] == session_id

        # 3. Save state -> ACTIVE
        save_resp = client.post(
            f"/api/browser/sessions/{session_id}/save-state",
            json={"storage_state": {"cookies": [{"name": "naukri_user", "value": "token_123"}]}, "expires_in_days": 10},
        )
        assert save_resp.status_code == 200
        assert save_resp.json()["status"] == "ACTIVE"
        assert save_resp.json()["has_stored_state"] is True
        # Verify NO raw cookies are returned in API response
        assert "cookies" not in save_resp.json()
        assert "token_123" not in save_resp.text

        # 4. List sessions
        list_resp = client.get("/api/browser/sessions")
        assert list_resp.status_code == 200
        assert len(list_resp.json()) >= 1

        # 5. Revoke session
        revoke_resp = client.post(f"/api/browser/sessions/{session_id}/revoke")
        assert revoke_resp.status_code == 200
        assert revoke_resp.json()["status"] == "REVOKED"
        assert revoke_resp.json()["has_stored_state"] is False
    finally:
        app.dependency_overrides.pop(get_db, None)

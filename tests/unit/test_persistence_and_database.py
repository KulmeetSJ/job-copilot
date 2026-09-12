"""Unit and integration tests for Phase 9.5 Persistent Storage & Database Foundation."""

from datetime import datetime, timezone
from pathlib import Path
import tempfile
import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from job_copilot.api.app import app
from job_copilot.db.database import check_db_connection, sanitize_database_url
from job_copilot.db.migrations_runner import downgrade_migrations, run_migrations
from job_copilot.db.migrator import migrate_runtime_state_to_db
from job_copilot.domain.enums import ApplicationStatus, EmploymentType, RemoteStatus, ResumeStrategy
from job_copilot.models import (
    Application,
    ApplicationEventModel,
    ApplicationSnapshotModel,
    CopilotQueueRecord,
    Job,
    JobProvenance,
    RecommendationRecord,
    SourceHealthRecord,
)
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.copilot_repository import CopilotRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.application import ApplicationCreate
from job_copilot.schemas.job import JobCreate


@pytest.fixture
def db_session():
    """Create an isolated temporary SQLite database and session with all migrations applied."""
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


def test_migration_upgrade_and_downgrade():
    """Verify that Alembic migrations create all 8 core tables and can cleanly roll back."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        db_url = f"sqlite:///{db_path}"
        # 1. Upgrade to head
        run_migrations(db_url=db_url)
        engine = create_engine(db_url)
        inspector = inspect(engine)
        tables = sorted(inspector.get_table_names())

        expected_tables = [
            "alembic_version",
            "application_events",
            "application_snapshots",
            "applications",
            "artifacts",
            "browser_sessions",
            "browser_tasks",
            "copilot_queue",
            "job_provenance",
            "jobs",
            "recommendations",
            "source_health",
        ]
        for tbl in expected_tables:
            assert tbl in tables, f"Expected table '{tbl}' not found in database"

        # 2. Downgrade to base
        downgrade_migrations("base", db_url=db_url)
        inspector_post_down = inspect(engine)
        remaining = [t for t in inspector_post_down.get_table_names() if t != "alembic_version"]
        assert len(remaining) == 0, f"Expected 0 tables after downgrade, found: {remaining}"
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_job_repository_crud_provenance_and_dedup(db_session):
    """Verify JobRepository CRUD, unique constraints, and multi-source provenance."""
    session, _ = db_session
    repo = JobRepository(session)

    job_in = JobCreate(
        title="Senior Backend Engineer",
        company="Fintech Corp",
        location="Pune, India",
        remote_status=RemoteStatus.HYBRID,
        employment_type=EmploymentType.FULL_TIME,
        url="https://fintech.example.com/jobs/101",
        source="linkedin_pune",
        description="Looking for Java, Python, GCP and distributed systems expert.",
        requirements=["Java", "Python", "GCP"],
        technologies=["Java", "PostgreSQL", "Docker"],
    )
    job = repo.create(job_in)
    job.job_id = "fintech-senior-backend-101"
    job.canonical_url = "https://fintech.example.com/jobs/101"
    job.normalized_content_hash = "a1b2c3d4e5f60718"
    session.commit()
    session.refresh(job)

    assert job.id is not None
    assert job.job_id == "fintech-senior-backend-101"

    # Multi-source provenance
    prov1 = repo.add_provenance(
        job_id_ref=job.id,
        source_id="linkedin_pune",
        source_url="https://linkedin.com/jobs/view/101",
    )
    prov2 = repo.add_provenance(
        job_id_ref=job.id,
        source_id="naukri",
        source_url="https://naukri.com/job/101",
    )
    assert prov1.id is not None
    assert prov2.id is not None

    # Idempotent provenance addition
    prov1_dup = repo.add_provenance(
        job_id_ref=job.id,
        source_id="linkedin_pune",
        source_url="https://linkedin.com/jobs/view/101",
    )
    assert prov1_dup.id == prov1.id

    # Lookup by canonical URL and content hash
    found_by_url = repo.get_by_canonical_url("https://fintech.example.com/jobs/101")
    assert found_by_url is not None
    assert found_by_url.id == job.id

    found_by_hash = repo.get_by_content_hash("a1b2c3d4e5f60718")
    assert found_by_hash is not None
    assert found_by_hash.id == job.id


def test_recommendation_record_persistence(db_session):
    """Verify recommendation and score persistence without modifying Phase 4 logic."""
    session, _ = db_session
    job_repo = JobRepository(session)

    job = job_repo.create(
        JobCreate(
            title="Data Platform Engineer",
            company="Payment Systems Ltd",
            description="Big data engineer with GCP & Kafka experience",
        )
    )
    job.job_id = "payment-data-platform-202"
    session.commit()

    rec = job_repo.save_recommendation(
        job_id_ref=job.id,
        job_id="payment-data-platform-202",
        match_score=88.5,
        recommendation="STRONG_APPLY",
        priority_score=94.2,
        priority_band="CRITICAL",
        recommended_strategy="data_engineering",
        category_scores={"technical": 90.0, "domain": 85.0},
        explanation_summary="Strong match with candidate payments and streaming background.",
    )
    assert rec.id is not None
    assert rec.match_score == 88.5
    assert rec.priority_band == "CRITICAL"

    # Verify relationship from Job
    reloaded_job = job_repo.get_by_id(job.id)
    assert reloaded_job.recommendation is not None
    assert reloaded_job.recommendation.match_score == 88.5


def test_application_and_append_only_event_ledger(db_session):
    """Verify Phase 8 event ledger: append-only semantics, status synchronization, and snapshot."""
    session, _ = db_session
    job_repo = JobRepository(session)
    app_repo = ApplicationRepository(session)

    job = job_repo.create(
        JobCreate(
            title="Senior Software Engineer",
            company="Global Tech",
            description="Backend developer",
        )
    )
    job.job_id = "global-tech-swe-303"
    session.commit()

    # 1. Create Application
    app = Application(
        application_id="app-global-tech-303",
        job_id_str="global-tech-swe-303",
        job_id=job.id,
        company="Global Tech",
        role="Senior Software Engineer",
        source="wellfound",
        status=ApplicationStatus.DISCOVERED,
        strategy_used=ResumeStrategy.BACKEND_JAVA,
        resume_strategy="backend_java",
        match_score=91.0,
        recommendation="APPLY",
    )
    session.add(app)
    session.commit()
    session.refresh(app)

    # 2. Append events in chronological order
    e1 = app_repo.append_event(
        application_id="app-global-tech-303",
        job_id="global-tech-swe-303",
        event_type="PREPARED",
        event_id="evt-001",
        source="SYSTEM",
        notes="Tailored resume compiled successfully",
    )
    assert e1 is not None
    assert e1.event_type == "PREPARED"

    # Status must synchronize with latest event
    app_reloaded = app_repo.get_by_application_id("app-global-tech-303")
    assert app_reloaded.current_status_at == e1.timestamp

    e2 = app_repo.append_event(
        application_id="app-global-tech-303",
        job_id="global-tech-swe-303",
        event_type="SUBMITTED",
        event_id="evt-002",
        source="USER",
        notes="Confirmed by human operator",
    )
    assert e2 is not None

    app_reloaded = app_repo.get_by_application_id("app-global-tech-303")
    assert app_reloaded.current_status_at == e2.timestamp

    # 3. Idempotent event insertion (duplicate event_id ignored)
    e2_dup = app_repo.append_event(
        application_id="app-global-tech-303",
        job_id="global-tech-swe-303",
        event_type="SUBMITTED",
        event_id="evt-002",
    )
    assert e2_dup.id == e2.id

    # 4. Save Submission Snapshot
    snap = app_repo.save_snapshot(
        application_id="app-global-tech-303",
        job_id="global-tech-swe-303",
        resume_strategy="backend_java",
        match_score=91.0,
        recommendation="APPLY",
        technical_match=92.0,
        domain_match=90.0,
        job_source="wellfound",
    )
    assert snap is not None
    assert snap.match_score == 91.0

    # 5. List events
    events = app_repo.get_events("app-global-tech-303")
    assert len(events) == 2
    assert [e.event_type for e in events] == ["PREPARED", "SUBMITTED"]


def test_copilot_queue_and_source_health_repository(db_session):
    """Verify Copilot queue and source health persistence (Phase 9 & 9.2)."""
    session, _ = db_session
    repo = CopilotRepository(session)

    # Queue management
    q_entry = repo.add_or_update_queue_job(
        job_id="job-tier1-hsbc-404",
        priority_band="CRITICAL",
        priority_score=96.5,
        queue_status="PENDING_REVIEW",
        category_scores={"fit": 95.0, "tier_bonus": 5.0},
        reasons=["Tier 1 target company", "Strong payments experience"],
    )
    assert q_entry.id is not None
    assert q_entry.priority_score == 96.5

    updated = repo.update_queue_status("job-tier1-hsbc-404", "APPROVED", notes="Approved for prep")
    assert updated is not None
    assert updated.queue_status == "APPROVED"
    assert any("Approved for prep" in note for note in updated.user_notes)

    counts = repo.get_queue_counts()
    assert counts.get("APPROVED") == 1

    # Source Health
    h_rec = repo.save_source_health(
        source_id="linkedin_pune",
        name="LinkedIn Jobs - Pune",
        state="LOGIN_REQUIRED",
        discovery_mode="AUTHENTICATED_BROWSER",
        requires_login=True,
        check_interval_minutes=60,
        message="Authenticated session required",
    )
    assert h_rec.source_id == "linkedin_pune"
    assert h_rec.state == "LOGIN_REQUIRED"

    all_health = repo.list_source_health()
    assert len(all_health) == 1
    assert all_health[0].source_id == "linkedin_pune"


def test_database_url_sanitization():
    """Verify that credentials in database URLs are masked for secure logging."""
    raw_postgres_url = "postgresql://myuser:superSecretPassword123@db.render.com:5432/copilot_db"
    sanitized = sanitize_database_url(raw_postgres_url)
    assert "superSecretPassword123" not in sanitized
    assert "myuser:***@db.render.com" in sanitized

    raw_sqlite_url = "sqlite:///./data/job_copilot.db"
    assert sanitize_database_url(raw_sqlite_url) == raw_sqlite_url


def test_readiness_endpoint_response():
    """Verify that GET /ready returns 200 with database health status."""
    client = TestClient(app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"
    # Never leak connection strings or passwords
    assert "password" not in str(data).lower()
    assert "token" not in str(data).lower()


def test_normalize_database_url_render_schemes():
    """Verify normalization of various Render and standard PostgreSQL URL schemes."""
    from job_copilot.db.database import normalize_database_url

    # Render legacy format: postgres://
    render_url = "postgres://user:secret@dpg-12345.oregon-postgres.render.com/copilot_db"
    normalized = normalize_database_url(render_url)
    assert normalized.startswith("postgresql+psycopg://")
    assert "dpg-12345.oregon-postgres.render.com" in normalized

    # Standard postgresql:// scheme
    std_url = "postgresql://user:secret@localhost:5432/copilot_db"
    assert normalize_database_url(std_url).startswith("postgresql+psycopg://")

    # Already explicit dialect scheme
    explicit_url = "postgresql+psycopg://user:secret@localhost:5432/copilot_db"
    assert normalize_database_url(explicit_url) == explicit_url

    # SQLite URLs untouched
    sqlite_url = "sqlite:///./data/job_copilot.db"
    assert normalize_database_url(sqlite_url) == sqlite_url

    # Empty / None handling
    assert normalize_database_url("") == ""


def test_synthetic_persistence_roundtrip_and_restart_survival():
    """
    Controlled Phase 9.6 safe persistence test & restart survival test.
    1. Writes a synthetic, non-personal record (company: '__PHASE_9_6_PERSISTENCE_TEST__').
    2. Verifies write -> read roundtrip.
    3. Simulates container/API restart by completely disposing the engine/session and creating a fresh connection.
    4. Verifies the synthetic record survived restart.
    5. Cleanly deletes the synthetic record and verifies database is clean.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    db_url = f"sqlite:///{db_path}"
    run_migrations(db_url=db_url)

    # Initial Engine & Session (Process 1)
    engine1 = create_engine(db_url, connect_args={"check_same_thread": False})
    Session1 = sessionmaker(autocommit=False, autoflush=False, bind=engine1)
    session1 = Session1()

    synthetic_company = "__PHASE_9_6_PERSISTENCE_TEST__"
    synthetic_job_id = "job-phase-9-6-persistence-synthetic-test"

    try:
        repo1 = JobRepository(session1)
        job_create = JobCreate(
            title="Synthetic Verification Engineer",
            company=synthetic_company,
            location="Cloud Environment",
            url="https://test.example.com/synthetic-verification",
            description="Harmless synthetic test record for Phase 9.6 persistence verification.",
            source="synthetic_verification",
        )
        job = repo1.create(job_create)
        job.job_id = synthetic_job_id
        session1.commit()
        session1.refresh(job)

        # 1. Verify written in initial process
        saved_id = job.id
        assert saved_id is not None
        assert job.company == synthetic_company

        # 2. Simulate API / Container Restart: Dispose engine1 & close session1
        session1.close()
        engine1.dispose()

        # 3. Reconnect in new process (Process 2)
        engine2 = create_engine(db_url, connect_args={"check_same_thread": False})
        Session2 = sessionmaker(autocommit=False, autoflush=False, bind=engine2)
        session2 = Session2()

        repo2 = JobRepository(session2)
        reloaded_job = repo2.get_by_id(saved_id)

        # 4. Verify record survived restart
        assert reloaded_job is not None, "Synthetic record failed to survive container/engine restart!"
        assert reloaded_job.company == synthetic_company
        assert reloaded_job.job_id == synthetic_job_id

        # 5. Clean deletion of synthetic record
        session2.delete(reloaded_job)
        session2.commit()

        # Verify completely removed
        deleted_check = repo2.get_by_id(saved_id)
        assert deleted_check is None, "Synthetic record was not cleanly deleted after test!"

        session2.close()
        engine2.dispose()
    finally:
        Path(db_path).unlink(missing_ok=True)


def test_readiness_failure_unreachable_database(monkeypatch):
    """Verify that /ready returns HTTP 503 and clean error when database is unreachable."""
    from unittest.mock import patch
    from fastapi.testclient import TestClient

    with patch("job_copilot.api.app.check_db_connection", return_value=False):
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["detail"] == "Database connectivity unavailable"
        assert "password" not in str(data).lower()


def test_schema_unique_constraints_and_foreign_keys(db_session):
    """Verify that schema enforces unique constraints and foreign key relationships."""
    session, _ = db_session
    repo = JobRepository(session)

    job1 = repo.create(
        JobCreate(
            title="DevOps Lead",
            company="Cloud Corp",
            url="https://cloudcorp.example.com/jobs/1",
            description="Manage Kubernetes clusters and cloud infrastructure.",
        )
    )
    job1.job_id = "job-cloudcorp-unique-1"
    session.commit()

    # 1. Verify duplicate job_id is rejected by unique constraint
    from sqlalchemy.exc import IntegrityError

    job2 = Job(
        title="DevOps Lead Duplicate",
        company="Cloud Corp",
        job_id="job-cloudcorp-unique-1",  # Duplicate unique job_id
        description="Duplicate posting",
    )
    session.add(job2)
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

    # 2. Verify cascade deletion from Job to Provenance
    prov = repo.add_provenance(
        job_id_ref=job1.id,
        source_id="render_cloud",
        source_url="https://cloudcorp.example.com/jobs/1",
    )
    assert prov.id is not None

    session.delete(job1)
    session.commit()

    from job_copilot.models import JobProvenance
    prov_check = session.query(JobProvenance).filter_by(id=prov.id).first()
    assert prov_check is None, "Cascading delete failed to remove child provenance record"


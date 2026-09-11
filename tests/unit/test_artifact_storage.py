"""Unit and integration tests for Phase 10A Object Storage & Artifact Management."""

import hashlib
from pathlib import Path
import tempfile
from unittest.mock import MagicMock
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.config import Settings
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.artifact_enums import ArtifactStatus, ArtifactType, StorageProvider
from job_copilot.models.artifact import ArtifactModel
from job_copilot.repositories.artifact_repository import ArtifactRepository
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.storage.base import ArtifactStore
from job_copilot.storage.factory import create_artifact_store
from job_copilot.storage.key_builder import (
    build_storage_key,
    sanitize_filename,
    sanitize_path_segment,
    validate_storage_key,
)
from job_copilot.storage.local_store import LocalArtifactStore
from job_copilot.storage.migrator import infer_artifact_type, infer_content_type, migrate_existing_filesystem_artifacts
from job_copilot.storage.s3_store import S3ArtifactStore


@pytest.fixture
def temp_dir():
    """Temporary directory fixture for local storage tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


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


# ==============================================================================
# 1. Local Store & Path Security Tests
# ==============================================================================


def test_local_artifact_store_crud_and_checksums(temp_dir):
    """Verify LocalArtifactStore put, get, exists, delete, list_keys, and checksum computation."""
    store = LocalArtifactStore(base_dir=temp_dir)

    payload = b"%PDF-1.4 Mock Tailored Resume Content for Backend Java"
    storage_key = "applications/app-test-123/tailored_resume_pdf/art-001/resume.pdf"

    # 1. Put
    size_bytes, sha256 = store.put(storage_key, payload, content_type="application/pdf")
    assert size_bytes == len(payload)
    assert sha256 == hashlib.sha256(payload).hexdigest()

    # 2. Exists
    assert store.exists(storage_key) is True
    assert store.exists("nonexistent/key.bin") is False

    # 3. Get
    retrieved = store.get(storage_key)
    assert retrieved == payload

    # 4. List keys
    keys = store.list_keys("applications/app-test-123")
    assert storage_key in keys

    # 5. Presigned URL
    url = store.presigned_url(storage_key)
    assert url is not None
    assert "resume.pdf" in url

    # 6. Delete
    assert store.delete(storage_key) is True
    assert store.exists(storage_key) is False
    assert store.delete(storage_key) is False  # Second delete returns False


def test_local_artifact_store_path_traversal_defenses(temp_dir):
    """Verify that malicious path traversal keys are strictly rejected."""
    store = LocalArtifactStore(base_dir=temp_dir)
    payload = b"malicious content"

    dangerous_keys = [
        "../etc/passwd",
        "../../secrets.env",
        "/absolute/path/file.txt",
        "\\windows\\path\\file.txt",
        "applications/../../../etc/shadow",
        "applications/app-1/../../passwords.txt",
        "applications/\x00/nullbyte.txt",
    ]

    for bad_key in dangerous_keys:
        with pytest.raises((ValueError, PermissionError)):
            store.put(bad_key, payload)

        with pytest.raises((ValueError, PermissionError)):
            store.get(bad_key)


# ==============================================================================
# 2. Key Builder & Sanitization Tests
# ==============================================================================


def test_key_builder_sanitization_and_determinism():
    """Verify filename sanitization, scope segment cleaning, and deterministic key construction."""
    # Filename sanitization
    assert sanitize_filename("my resume.pdf") == "my_resume.pdf"
    assert sanitize_filename("../../etc/passwd") == "etc_passwd"
    assert sanitize_filename("cover_letter.md") == "cover_letter.md"
    assert sanitize_filename(None) == "artifact.bin"

    # Path segment sanitization
    assert sanitize_path_segment("job/123:test") == "job_123_test"
    assert sanitize_path_segment(None, default="general") == "general"

    # Deterministic key generation
    key = build_storage_key(
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        artifact_id="art-xyz123",
        application_id="app-google-swe-404",
        filename="resume.pdf",
    )
    assert key == "applications/app-google-swe-404/tailored_resume_pdf/art-xyz123/resume.pdf"
    validate_storage_key(key)


# ==============================================================================
# 3. S3 Store Mock Operations Tests
# ==============================================================================


def test_s3_artifact_store_mocked_operations():
    """Verify S3ArtifactStore interactions with mock S3 client."""
    mock_client = MagicMock()
    mock_client.put_object.return_value = {"ETag": '"mock-etag"'}
    mock_client.head_object.return_value = {"ContentLength": 100}
    mock_client.generate_presigned_url.return_value = "https://s3.amazonaws.com/bucket/key?signature=mock"

    store = S3ArtifactStore(
        bucket_name="job-copilot-artifacts",
        region_name="us-east-1",
        client=mock_client,
    )

    payload = b"Sample S3 Content"
    storage_key = "applications/app-s3-1/cover_letter/art-s3/cover_letter.md"

    # 1. Put
    size, sha = store.put(storage_key, payload, content_type="text/markdown")
    assert size == len(payload)
    mock_client.put_object.assert_called_once()

    # 2. Exists
    assert store.exists(storage_key) is True
    mock_client.head_object.assert_called_once()

    # 3. Presigned URL
    url = store.presigned_url(storage_key, expires_in_seconds=1800)
    assert "signature=mock" in url
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "job-copilot-artifacts", "Key": storage_key},
        ExpiresIn=1800,
    )

    # 4. Delete
    store.delete(storage_key)
    mock_client.delete_object.assert_called_once_with(
        Bucket="job-copilot-artifacts",
        Key=storage_key,
    )


def test_s3_artifact_store_requires_bucket():
    """Verify S3ArtifactStore validation on missing bucket name."""
    with pytest.raises(ValueError, match="requires a valid 'bucket_name'"):
        S3ArtifactStore(bucket_name="")


# ==============================================================================
# 4. Factory & Configuration Tests
# ==============================================================================


def test_artifact_store_factory_local_and_s3(temp_dir):
    """Verify create_artifact_store selects appropriate backend and fails fast on bad config."""
    # 1. Local
    local_store = create_artifact_store(provider="local", base_dir=str(temp_dir))
    assert isinstance(local_store, LocalArtifactStore)

    # 2. Unsupported
    with pytest.raises(ValueError, match="Unsupported ARTIFACT_STORAGE_PROVIDER"):
        create_artifact_store(provider="unknown_provider")


# ==============================================================================
# 5. Database Repository & Metadata Persistence Tests
# ==============================================================================


def test_artifact_repository_crud_and_queries(db_session):
    """Verify PostgreSQL ArtifactRepository CRUD operations and metadata querying."""
    session, _ = db_session
    repo = ArtifactRepository(session)

    art = ArtifactModel(
        artifact_id="art-repo-test-001",
        application_id="app-repo-test",
        job_id="job-repo-test",
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        storage_provider=StorageProvider.LOCAL,
        storage_key="applications/app-repo-test/tailored_resume_pdf/art-repo-test-001/resume.pdf",
        content_type="application/pdf",
        size_bytes=10240,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        original_filename="resume.pdf",
        status=ArtifactStatus.ACTIVE,
        metadata_json={"pages": 1, "strategy": "backend_java"},
    )
    saved = repo.create(art)
    assert saved.id is not None
    assert saved.artifact_id == "art-repo-test-001"

    # Query by artifact_id
    found = repo.get_by_artifact_id("art-repo-test-001")
    assert found is not None
    assert found.size_bytes == 10240

    # Query by SHA-256
    found_sha = repo.get_by_sha256("e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855")
    assert found_sha is not None
    assert found_sha.id == saved.id

    # List by application
    app_list = repo.list_by_application("app-repo-test")
    assert len(app_list) == 1
    assert app_list[0].artifact_type == ArtifactType.TAILORED_RESUME_PDF

    # Status update
    updated = repo.update_status("art-repo-test-001", ArtifactStatus.ARCHIVED)
    assert updated.status == ArtifactStatus.ARCHIVED

    # Delete
    assert repo.delete("art-repo-test-001") is True
    assert repo.get_by_artifact_id("art-repo-test-001") is None


# ==============================================================================
# 6. High-Level ArtifactService Integration & Lifecycle Tests
# ==============================================================================


def test_artifact_service_end_to_end_lifecycle(db_session, temp_dir):
    """Verify ArtifactService storing, retrieving, idempotency, integrity checking, and soft/hard delete."""
    session, _ = db_session
    local_store = LocalArtifactStore(base_dir=temp_dir)
    repo = ArtifactRepository(session)
    service = ArtifactService(store=local_store, repo=repo, db=session)

    pdf_bytes = b"%PDF-1.4 Tailored Resume for Google SRE Role"

    # 1. Store artifact
    record = service.store_artifact(
        data=pdf_bytes,
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        application_id="app-google-sre-101",
        job_id="google-sre-101",
        original_filename="resume.pdf",
        content_type="application/pdf",
        metadata={"target_company": "Google"},
    )
    assert record.id is not None
    assert record.size_bytes == len(pdf_bytes)
    assert record.sha256 == hashlib.sha256(pdf_bytes).hexdigest()

    # 2. Get artifact content & verify integrity
    data, meta = service.get_artifact(record.artifact_id)
    assert data == pdf_bytes
    assert meta.artifact_id == record.artifact_id
    assert service.verify_integrity(record.artifact_id) is True

    # 3. Idempotent re-upload of identical artifact
    re_uploaded = service.store_artifact(
        data=pdf_bytes,
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        application_id="app-google-sre-101",
        job_id="google-sre-101",
        original_filename="resume.pdf",
        custom_artifact_id=record.artifact_id,
    )
    assert re_uploaded.id == record.id

    # 4. Archival
    assert service.archive_artifact(record.artifact_id) is True
    archived = service.get_artifact_metadata(record.artifact_id)
    assert archived.status == ArtifactStatus.ARCHIVED

    # 5. Soft delete
    assert service.delete_artifact(record.artifact_id, hard_delete=False) is True
    soft_deleted = service.get_artifact_metadata(record.artifact_id)
    assert soft_deleted.status == ArtifactStatus.DELETED
    # Binary should still exist on soft-delete
    assert local_store.exists(record.storage_key) is True

    # 6. Hard delete
    assert service.delete_artifact(record.artifact_id, hard_delete=True) is True
    assert service.get_artifact_metadata(record.artifact_id) is None
    assert local_store.exists(record.storage_key) is False


def test_artifact_service_corrupted_integrity_detection(db_session, temp_dir):
    """Verify that ArtifactService detects corrupted or tampered binary objects."""
    session, _ = db_session
    local_store = LocalArtifactStore(base_dir=temp_dir)
    repo = ArtifactRepository(session)
    service = ArtifactService(store=local_store, repo=repo, db=session)

    original_bytes = b"Original Package JSON"
    record = service.store_artifact(
        data=original_bytes,
        artifact_type=ArtifactType.APPLICATION_PACKAGE,
        application_id="app-integrity-test",
        original_filename="package.json",
    )

    # Tamper with the underlying storage file directly
    storage_file = temp_dir / record.storage_key
    storage_file.write_bytes(b"Tampered Corrupted Package JSON")

    # verify_integrity should return False
    assert service.verify_integrity(record.artifact_id) is False

    # get_artifact should raise IOError
    with pytest.raises(IOError, match="Integrity check failed"):
        service.get_artifact(record.artifact_id)


# ==============================================================================
# 7. Non-Destructive Migrator Tests
# ==============================================================================


def test_filesystem_artifact_migrator_non_destructive(db_session, temp_dir):
    """Verify that migrate_existing_filesystem_artifacts indexes existing disk files without deleting them."""
    session, _ = db_session
    local_store = LocalArtifactStore(base_dir=temp_dir / "artifacts_root")
    repo = ArtifactRepository(session)
    service = ArtifactService(store=local_store, repo=repo, db=session)

    # Create synthetic existing applications structure
    apps_dir = temp_dir / "data" / "applications"
    job_dir = apps_dir / "hsbc-backend-pune-101"
    job_dir.mkdir(parents=True, exist_ok=True)

    pkg_file = job_dir / "package.json"
    pkg_file.write_text('{"job_id": "hsbc-backend-pune-101", "status": "READY"}', encoding="utf-8")

    cv_file = job_dir / "cover_letter.md"
    cv_file.write_text("Dear Hiring Team at HSBC...", encoding="utf-8")

    pdf_file = job_dir / "tailored_resume.pdf"
    pdf_file.write_bytes(b"%PDF-1.4 HSBC Tailored Resume")

    # Run non-destructive migration
    counts = migrate_existing_filesystem_artifacts(
        applications_dir=apps_dir,
        artifact_service=service,
        db_session=session,
    )

    assert counts["discovered"] == 3
    assert counts["migrated"] == 3
    assert counts["errors"] == 0

    # Verify original files still exist (strictly non-destructive)
    assert pkg_file.exists()
    assert cv_file.exists()
    assert pdf_file.exists()

    # Verify records registered in PostgreSQL
    records = repo.list_by_job("hsbc-backend-pune-101")
    assert len(records) == 3
    types = {r.artifact_type for r in records}
    assert ArtifactType.APPLICATION_PACKAGE in types
    assert ArtifactType.COVER_LETTER in types
    assert ArtifactType.TAILORED_RESUME_PDF in types

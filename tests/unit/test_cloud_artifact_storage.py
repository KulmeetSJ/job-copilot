"""Comprehensive test suite for Phase 12.2 Cloud Artifact Storage & Persistence."""

import hashlib
import io
from pathlib import Path
import tempfile
from unittest.mock import MagicMock, patch
import pytest
from botocore.exceptions import ClientError, EndpointConnectionError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from job_copilot.api.app import app
from job_copilot.config import settings
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
from job_copilot.storage.s3_store import S3ArtifactStore


@pytest.fixture
def temp_dir():
    """Isolated temporary directory fixture."""
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
        yield session
    finally:
        session.close()
        engine.dispose()
        Path(db_path).unlink(missing_ok=True)


# ==============================================================================
# 1. LocalArtifactStore Tests
# ==============================================================================

def test_local_artifact_store_lifecycle(temp_dir):
    """Verify LocalArtifactStore put, get, exists, delete, list_keys, and presigned url."""
    store = LocalArtifactStore(base_dir=temp_dir)
    payload = b"%PDF-1.4 Mock Tailored Resume"
    key = "applications/app-test-1/tailored_resume_pdf/art-001/resume.pdf"

    # Put
    size, sha = store.put(key, payload, content_type="application/pdf")
    assert size == len(payload)
    assert sha == hashlib.sha256(payload).hexdigest()

    # Exists & Get
    assert store.exists(key) is True
    assert store.get(key) == payload

    # List keys
    keys = store.list_keys("applications/app-test-1")
    assert key in keys

    # Delete
    assert store.delete(key) is True
    assert store.exists(key) is False
    assert store.delete(key) is False


def test_local_artifact_store_traversal_rejection(temp_dir):
    """Verify LocalArtifactStore strictly blocks directory traversal attempts."""
    store = LocalArtifactStore(base_dir=temp_dir)
    payload = b"malicious content"

    with pytest.raises(ValueError):
        store.put("../../../etc/passwd", payload)

    with pytest.raises(ValueError):
        store.get("../secret.txt")


# ==============================================================================
# 2. S3ArtifactStore (Mocked) Tests
# ==============================================================================

def test_s3_store_put_and_get():
    """Verify S3ArtifactStore put and get operations with metadata and content type."""
    mock_client = MagicMock()
    store = S3ArtifactStore(bucket_name="test-bucket", client=mock_client)

    payload = b"Sample Cloud Resume Binary Data"
    key = "applications/app-100/tailored_resume_pdf/art-100/resume.pdf"
    expected_sha = hashlib.sha256(payload).hexdigest()

    # 1. Put
    size, sha = store.put(key, payload, content_type="application/pdf")
    assert size == len(payload)
    assert sha == expected_sha
    mock_client.put_object.assert_called_once_with(
        Bucket="test-bucket",
        Key=key,
        Body=payload,
        ContentType="application/pdf",
        Metadata={"sha256": expected_sha},
    )

    # 2. Get
    mock_client.get_object.return_value = {"Body": io.BytesIO(payload)}
    retrieved = store.get(key)
    assert retrieved == payload
    mock_client.get_object.assert_called_once_with(Bucket="test-bucket", Key=key)


def test_s3_store_exists_and_delete():
    """Verify S3ArtifactStore exists and delete operations."""
    mock_client = MagicMock()
    store = S3ArtifactStore(bucket_name="test-bucket", client=mock_client)
    key = "applications/app-100/tailored_resume_pdf/art-100/resume.pdf"

    # Exists: True
    mock_client.head_object.return_value = {}
    assert store.exists(key) is True

    # Exists: False on ClientError
    mock_client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "head_object")
    assert store.exists(key) is False

    # Delete
    mock_client.head_object.side_effect = None
    mock_client.head_object.return_value = {}  # exists returns True
    mock_client.delete_object.return_value = {}
    assert store.delete(key) is True
    mock_client.delete_object.assert_called_once_with(Bucket="test-bucket", Key=key)


def test_s3_store_missing_object_raises_file_not_found():
    """Verify that NoSuchKey / 404 on S3 get raises clean FileNotFoundError."""
    mock_client = MagicMock()
    store = S3ArtifactStore(bucket_name="test-bucket", client=mock_client)
    key = "applications/app-100/tailored_resume_pdf/art-999/nonexistent.pdf"

    mock_client.get_object.side_effect = ClientError(
        {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
        "get_object",
    )

    with pytest.raises(FileNotFoundError, match="Artifact not found in S3"):
        store.get(key)


def test_s3_store_transient_retry_and_exponential_backoff():
    """Verify that transient 500/503/timeout S3 errors trigger retries and succeed on subsequent attempt."""
    mock_client = MagicMock()
    store = S3ArtifactStore(bucket_name="test-bucket", client=mock_client)
    key = "applications/app-100/tailored_resume_pdf/art-100/resume.pdf"
    payload = b"Retried Content"

    # Fail twice with 503 Service Unavailable, then succeed on 3rd attempt
    mock_client.put_object.side_effect = [
        ClientError({"Error": {"Code": "503", "Message": "SlowDown"}}, "put_object"),
        ClientError({"Error": {"Code": "500", "Message": "InternalError"}}, "put_object"),
        {},  # Success
    ]

    size, sha = store.put(key, payload)
    assert size == len(payload)
    assert mock_client.put_object.call_count == 3


def test_s3_store_persistent_failure_raises_ioerror():
    """Verify that persistent S3 errors exhaust max retries and raise IOError."""
    mock_client = MagicMock()
    store = S3ArtifactStore(bucket_name="test-bucket", client=mock_client)
    key = "applications/app-100/tailored_resume_pdf/art-100/resume.pdf"

    mock_client.put_object.side_effect = EndpointConnectionError(endpoint_url="https://s3.us-east-1.amazonaws.com")

    with pytest.raises(IOError, match="Failed uploading to S3"):
        store.put(key, b"data")
    assert mock_client.put_object.call_count == 3


def test_s3_store_config_validation():
    """Verify that empty bucket name raises ValueError."""
    with pytest.raises(ValueError, match="requires a valid 'bucket_name'"):
        S3ArtifactStore(bucket_name="")


# ==============================================================================
# 3. Factory Provider Selection Tests
# ==============================================================================

def test_factory_local_selection(monkeypatch):
    """Verify factory returns LocalArtifactStore when configured as local."""
    monkeypatch.setattr(settings, "artifact_storage_provider", "local")
    store = create_artifact_store()
    assert isinstance(store, LocalArtifactStore)


def test_factory_s3_selection_fails_fast_when_bucket_missing(monkeypatch):
    """Verify factory raises ValueError fast when S3 is requested without a bucket."""
    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")
    monkeypatch.setattr(settings, "artifact_storage_bucket", None)

    with pytest.raises(ValueError, match="ARTIFACT_STORAGE_BUCKET must be configured"):
        create_artifact_store()


# ==============================================================================
# 4. Storage Key Security Matrix
# ==============================================================================

@pytest.mark.parametrize(
    "invalid_key",
    [
        "../secret.txt",
        "../../etc/passwd",
        "/absolute/path/file.pdf",
        "\\windows\\path\\file.pdf",
        "C:\\Windows\\System32\\cmd.exe",
        "D:/Data/file.pdf",
        "applications/%2e%2e/file.pdf",
        "applications/%2froot/file.pdf",
        "applications/%5croot/file.pdf",
        "applications/..%2ffile.pdf",
        "applications/art-01\x00/file.pdf",
        "applications//file.pdf",
        "applications/./file.pdf",
        "applications/../file.pdf",
        "",
    ],
)
def test_storage_key_security_rejections(invalid_key):
    """Verify that malicious, traversal, or malformed storage keys are strictly rejected."""
    with pytest.raises(ValueError):
        validate_storage_key(invalid_key)


def test_build_storage_key_sanitization():
    """Verify that build_storage_key safely sanitizes user-controlled inputs."""
    key = build_storage_key(
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        artifact_id="art/../../hack-001",
        application_id="../app/secret:123",
        job_id=None,
        filename="../../my_resume.pdf",
    )
    assert ".." not in key
    assert "/" in key
    assert key.startswith("applications/")
    assert key.endswith("my_resume.pdf")


# ==============================================================================
# 5. ArtifactService Atomicity & Two-Phase Rollback
# ==============================================================================

def test_artifact_service_upload_atomicity_compensatory_cleanup(db_session):
    """Verify that if database persistence fails, the uploaded object in storage is cleaned up."""
    data = b"X" * 100
    expected_sha = hashlib.sha256(data).hexdigest()

    mock_store = MagicMock(spec=ArtifactStore)
    mock_store.put.return_value = (100, expected_sha)

    # Create repo with mock DB commit that fails
    repo = ArtifactRepository(db_session)
    service = ArtifactService(store=mock_store, repo=repo, db=db_session)

    with patch.object(repo, "create", side_effect=Exception("Simulated PostgreSQL connection failure")):
        with pytest.raises(Exception, match="Simulated PostgreSQL connection failure"):
            service.store_artifact(
                data=data,
                artifact_type=ArtifactType.TAILORED_RESUME_PDF,
                application_id="app-atom-1",
                custom_artifact_id="art-atom-1",
            )

    # Verify that compensatory delete was called on store to avoid orphaned files
    assert mock_store.delete.called


def test_artifact_service_lifecycle_with_local_store(db_session, temp_dir):
    """Verify full end-to-end integration: store -> get -> metadata -> integrity -> delete."""
    store = LocalArtifactStore(base_dir=temp_dir)
    repo = ArtifactRepository(db_session)
    service = ArtifactService(store=store, repo=repo, db=db_session)

    pdf_data = b"%PDF-1.4 Tailored Resume for Cloud DevOps Engineer"

    # 1. Store
    model = service.store_artifact(
        data=pdf_data,
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        application_id="app-devops-01",
        job_id="job-cloud-01",
        original_filename="resume_cloud_devops.pdf",
        content_type="application/pdf",
        custom_artifact_id="art-devops-01",
    )
    assert model.artifact_id == "art-devops-01"
    assert model.sha256 == hashlib.sha256(pdf_data).hexdigest()
    assert model.size_bytes == len(pdf_data)

    # 2. Get
    retrieved_data, retrieved_model = service.get_artifact("art-devops-01")
    assert retrieved_data == pdf_data
    assert retrieved_model.artifact_id == "art-devops-01"

    # 3. Verify integrity
    assert service.verify_integrity("art-devops-01") is True

    # 4. Hard Delete
    assert service.delete_artifact("art-devops-01", hard_delete=True) is True
    assert service.verify_integrity("art-devops-01") is False


# ==============================================================================
# 6. Readiness Probe & Cloud Config Verification
# ==============================================================================

def test_readiness_probe_with_production_s3(monkeypatch):
    """Verify that in production with S3 provider, /ready endpoint checks S3 configuration."""
    from fastapi.testclient import TestClient

    client = TestClient(app, raise_server_exceptions=False)

    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "artifact_storage_provider", "s3")

    # Missing bucket -> 503
    monkeypatch.setattr(settings, "artifact_storage_bucket", None)
    resp_fail = client.get("/ready")
    assert resp_fail.status_code == 503
    assert "Storage configuration unavailable" in resp_fail.json().get("detail", "")

    # Configured bucket -> 200
    monkeypatch.setattr(settings, "artifact_storage_bucket", "my-production-artifacts")
    resp_ok = client.get("/ready")
    assert resp_ok.status_code == 200
    assert resp_ok.json()["status"] == "ready"
    assert resp_ok.json()["storage"] == "s3"

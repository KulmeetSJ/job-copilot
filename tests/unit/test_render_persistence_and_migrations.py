"""Tests for Render production persistence via ArtifactService/R2 and migration execution."""

from pathlib import Path
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from job_copilot.db.base import Base
from job_copilot.db.migrations_runner import run_migrations
from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.storage.local_store import LocalArtifactStore


@pytest.fixture
def test_db_and_artifact_service(tmp_path: Path):
    """Provide isolated database session and ArtifactService pointing to a temporary object store."""
    db_file = tmp_path / "test.db"
    db_url = f"sqlite:///{db_file}"
    engine = create_engine(db_url, echo=False)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    store = LocalArtifactStore(base_dir=tmp_path / "artifacts")
    artifact_service = ArtifactService(store=store, db=session)

    try:
        yield session, artifact_service, db_url
    finally:
        session.close()


def test_artifact_service_persists_resumes_and_packages(test_db_and_artifact_service):
    """Verify that tailored resumes and application packages persist via ArtifactService."""
    session, artifact_service, _ = test_db_and_artifact_service

    job_id = "job-render-audit-123"
    pdf_content = b"%PDF-1.4 Mock rendered resume content for production audit"
    tex_content = b"\\documentclass{article}\\begin{document}Resume\\end{document}"
    package_json = b'{"job_id": "job-render-audit-123", "status": "READY_TO_APPLY"}'

    # 1. Store application package
    pkg_art = artifact_service.store_artifact(
        data=package_json,
        artifact_type=ArtifactType.APPLICATION_PACKAGE,
        job_id=job_id,
        original_filename="package.json",
        content_type="application/json",
    )
    assert pkg_art.artifact_id.startswith("art-")

    # 2. Store tailored resume PDF
    pdf_art = artifact_service.store_artifact(
        data=pdf_content,
        artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        job_id=job_id,
        original_filename="resume_job-render-audit-123.pdf",
        content_type="application/pdf",
    )
    assert pdf_art.artifact_id.startswith("art-")

    # 3. Store tailored resume TeX
    tex_art = artifact_service.store_artifact(
        data=tex_content,
        artifact_type=ArtifactType.TAILORED_RESUME_TEX,
        job_id=job_id,
        original_filename="resume_job-render-audit-123.tex",
        content_type="application/x-tex",
    )
    assert tex_art.artifact_id.startswith("art-")

    # 4. Verify retrieval from ArtifactService abstraction
    retrieved_pdf_data, meta = artifact_service.get_artifact(pdf_art.artifact_id)
    assert retrieved_pdf_data == pdf_content
    assert meta.artifact_type == ArtifactType.TAILORED_RESUME_PDF

    # 5. Verify query by job_id
    listed = artifact_service.list_artifacts(job_id=job_id, artifact_type=ArtifactType.TAILORED_RESUME_PDF)
    assert len(listed) == 1
    assert listed[0].artifact_id == pdf_art.artifact_id


def test_migrations_runner_executes_cleanly(tmp_path: Path):
    """Verify that Alembic migrations runner executes cleanly against a fresh SQLite database."""
    db_file = tmp_path / "migration_test.db"
    db_url = f"sqlite:///{db_file}"
    # Running migrations up to head
    run_migrations(db_url=db_url)
    assert db_file.exists()

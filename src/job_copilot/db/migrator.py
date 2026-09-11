"""Explicit, opt-in migration utility for persisting runtime state to PostgreSQL/SQLite."""

from typing import Dict, Optional
from sqlalchemy.orm import Session

from job_copilot.copilot.queue import CopilotQueueStore
from job_copilot.db.database import get_db
from job_copilot.domain.enums import ApplicationStatus, EmploymentType, RemoteStatus, ResumeStrategy
from job_copilot.ingestion.store import JobStore
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.copilot_repository import CopilotRepository
from job_copilot.repositories.job_repository import JobRepository
from job_copilot.schemas.job import JobCreate
from job_copilot.tracking.store import TrackingStore
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def migrate_runtime_state_to_db(
    db: Session,
    job_store: Optional[JobStore] = None,
    tracking_store: Optional[TrackingStore] = None,
    queue_store: Optional[CopilotQueueStore] = None,
) -> Dict[str, int]:
    """
    Explicitly migrate filesystem runtime state (Jobs, Tracking, Queue) into database.
    - Strictly opt-in, explicit, and idempotent.
    - Never migrates private candidate truth files (master_profile.yaml, evidence.yaml).
    - Returns report of migrated record counts.
    """
    js = job_store or JobStore()
    ts = tracking_store or TrackingStore()
    qs = queue_store or CopilotQueueStore()

    job_repo = JobRepository(db)
    app_repo = ApplicationRepository(db)
    copilot_repo = CopilotRepository(db)

    stats = {
        "jobs_migrated": 0,
        "jobs_skipped": 0,
        "provenance_migrated": 0,
        "applications_migrated": 0,
        "applications_skipped": 0,
        "events_migrated": 0,
        "snapshots_migrated": 0,
        "queue_entries_migrated": 0,
    }

    # 1. Migrate Canonical Jobs
    canonical_jobs = js.list_canonical_jobs(include_duplicates=True)
    job_id_to_db_id: Dict[str, int] = {}

    for cjob in canonical_jobs:
        existing = job_repo.get_by_job_id(cjob.job_id)
        if existing:
            job_id_to_db_id[cjob.job_id] = existing.id
            stats["jobs_skipped"] += 1
        else:
            try:
                # Map remote status string to enum safely
                try:
                    r_status = RemoteStatus(cjob.remote_policy.value.lower())
                except Exception:
                    r_status = RemoteStatus.UNKNOWN

                raw_text = js.get_raw_job_text(cjob.job_id) or cjob.title

                job_in = JobCreate(
                    title=cjob.title,
                    company=cjob.company,
                    location=cjob.location,
                    remote_status=r_status,
                    employment_type=EmploymentType.FULL_TIME,
                    url=cjob.source_url,
                    source=cjob.source,
                    description=raw_text,
                    requirements=cjob.extracted_skills or [],
                    preferred_qualifications=[],
                    technologies=cjob.extracted_skills or [],
                    years_experience=cjob.minimum_experience_years,
                    salary_min=int(cjob.salary_min) if cjob.salary_min else None,
                    salary_max=int(cjob.salary_max) if cjob.salary_max else None,
                    currency=cjob.currency or "USD",
                    posted_at=cjob.posted_at,
                )
                db_job = job_repo.create(job_in)
                db_job.job_id = cjob.job_id
                db_job.canonical_url = cjob.canonical_url
                db_job.normalized_content_hash = cjob.content_hash
                db_job.lifecycle_status = cjob.lifecycle_status.value
                db_job.duplicate_of = cjob.duplicate_of
                db_job.discovered_at = cjob.discovered_at
                db.commit()
                db.refresh(db_job)

                job_id_to_db_id[cjob.job_id] = db_job.id
                stats["jobs_migrated"] += 1

                # Record initial provenance
                job_repo.add_provenance(
                    job_id_ref=db_job.id,
                    source_id=cjob.source,
                    source_url=cjob.source_url or "https://example.com/job",
                    source_job_id=cjob.source_job_id,
                )
                stats["provenance_migrated"] += 1

            except Exception as e:
                logger.error(f"Error migrating job {cjob.job_id}: {e}")
                db.rollback()

    # 2. Migrate Applications & Events
    tracked_apps = ts.list_applications()
    for app in tracked_apps:
        existing_app = app_repo.get_by_application_id(app.application_id)
        if existing_app:
            stats["applications_skipped"] += 1
            db_app = existing_app
        else:
            db_job_id = job_id_to_db_id.get(app.job_id)
            if not db_job_id:
                # Find or ensure job exists in DB
                db_job = job_repo.get_by_job_id(app.job_id)
                if not db_job:
                    # Create placeholder job for application
                    j_create = JobCreate(
                        title=app.role,
                        company=app.company,
                        location="Remote",
                        remote_status=RemoteStatus.REMOTE,
                        employment_type=EmploymentType.FULL_TIME,
                        url=app.canonical_job_url,
                        source=app.source,
                        description=f"{app.role} at {app.company}",
                    )
                    db_job = job_repo.create(j_create)
                    db_job.job_id = app.job_id
                    db.commit()
                    db.refresh(db_job)
                db_job_id = db_job.id

            # Create application record
            try:
                strat = ResumeStrategy.GENERAL_SWE
                if app.resume_strategy:
                    for s in ResumeStrategy:
                        if s.value == app.resume_strategy:
                            strat = s
                            break

                from job_copilot.models.application import Application
                db_app = Application(
                    application_id=app.application_id,
                    job_id_str=app.job_id,
                    job_id=db_job_id,
                    company=app.company,
                    role=app.role,
                    canonical_job_url=app.canonical_job_url,
                    source=app.source,
                    status=ApplicationStatus.DISCOVERED,
                    current_status_at=app.current_status_at,
                    strategy_used=strat,
                    resume_strategy=app.resume_strategy,
                    match_score=app.match_score,
                    recommendation=app.recommendation,
                    package_path=app.package_path,
                    browser_session_id=app.browser_session_id,
                    user_notes=app.user_notes,
                    discovered_at=app.discovered_at,
                    recommended_at=app.recommended_at,
                    prepared_at=app.prepared_at,
                    submitted_at=app.submitted_at,
                )
                db.add(db_app)
                db.commit()
                db.refresh(db_app)
                stats["applications_migrated"] += 1
            except Exception as e:
                logger.error(f"Error creating application {app.application_id}: {e}")
                db.rollback()
                continue

        # Migrate Events for this application
        for evt in app.events:
            event_res = app_repo.append_event(
                application_id=evt.application_id,
                job_id=evt.job_id,
                event_type=evt.event_type.value,
                event_id=evt.event_id,
                source=evt.source.value,
                notes=evt.notes,
                metadata_json=evt.metadata,
                timestamp=evt.timestamp,
            )
            if event_res:
                stats["events_migrated"] += 1

        # Migrate Snapshot if present
        if app.snapshot:
            snap_res = app_repo.save_snapshot(
                application_id=app.snapshot.application_id,
                job_id=app.snapshot.job_id,
                resume_strategy=app.snapshot.resume_strategy,
                match_score=app.snapshot.match_score,
                recommendation=app.snapshot.recommendation,
                technical_match=app.snapshot.technical_match,
                responsibility_match=app.snapshot.responsibility_match,
                seniority_match=app.snapshot.seniority_match,
                professional_evidence_match=app.snapshot.professional_evidence_match,
                domain_match=app.snapshot.domain_match,
                preference_match=app.snapshot.preference_match,
                credential_match=app.snapshot.credential_match,
                job_source=app.snapshot.job_source,
                resume_pdf_path=app.snapshot.resume_pdf_path,
                cover_letter_path=app.snapshot.cover_letter_path,
                applied_via=app.snapshot.applied_via,
                timestamp=app.snapshot.timestamp,
            )
            if snap_res:
                stats["snapshots_migrated"] += 1

    # 3. Migrate Copilot Queue Entries
    queue_jobs = qs.list_jobs()
    for qj in queue_jobs:
        try:
            copilot_repo.add_or_update_queue_job(
                job_id=qj.job_id,
                priority_band=qj.priority_band.value,
                priority_score=qj.priority_score,
                queue_status=qj.queue_status.value,
                category_scores=qj.category_scores,
                reasons=qj.reasons,
                user_notes=qj.user_notes,
            )
            stats["queue_entries_migrated"] += 1
        except Exception as e:
            logger.error(f"Error migrating queue entry {qj.job_id}: {e}")
            db.rollback()

    logger.info(f"Runtime state migration completed: {stats}")
    return stats

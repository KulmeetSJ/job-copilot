"""Core task execution engine for Phase 10B Browser Worker."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
from typing import List, Optional, Tuple
from sqlalchemy.orm import Session

from job_copilot.browser.classifier import FieldClassifier
from job_copilot.browser.mapper import FieldMapper
from job_copilot.browser.models import BrowserElementType, BrowserField, FieldClassification
from job_copilot.browser_worker.adapters import SourceAdapterRegistry
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserManager, BrowserSessionAdapter
from job_copilot.browser_worker.confirmation_service import HumanConfirmationService
from job_copilot.browser_worker.exceptions import (
    CaptchaDetectedError,
    DomainSecurityError,
    LoginRequiredError,
    SensitiveFieldPauseError,
)
from job_copilot.browser_worker.models import (
    BrowserTaskReviewPackage,
    DetectedFieldInfo,
)
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    mask_sensitive_value,
    validate_target_domain,
)
from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.browser_worker.session_store import BrowserSessionStore
from job_copilot.domain.artifact_enums import ArtifactType
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus, FieldAction
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.artifact_service import ArtifactService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserTaskExecutor:
    """
    Executes browser automation tasks with strict safety constraints and source adapters.
    Reaches READY_FOR_REVIEW as a terminal preparation state and NEVER autonomously submits.
    """

    def __init__(
        self,
        db: Session,
        artifact_service: Optional[ArtifactService] = None,
        browser_manager: Optional[BrowserManager] = None,
        candidate_profile: Optional[CandidateProfile] = None,
        adapter_registry: Optional[SourceAdapterRegistry] = None,
        session_store: Optional[BrowserSessionStore] = None,
    ):
        self.db = db
        self.task_repo = BrowserTaskRepository(db)
        self.app_repo = ApplicationRepository(db)
        self.artifact_service = artifact_service or ArtifactService(db=db)
        self.browser_manager = browser_manager or BrowserManager(headless=True)
        self.candidate_profile = candidate_profile or self._load_default_profile()
        self.adapter_registry = adapter_registry or SourceAdapterRegistry()
        self.session_store = session_store or BrowserSessionStore()
        self.session_manager = AuthenticatedSessionManager(db=db, session_store=self.session_store)
        self.classifier = FieldClassifier()
        self.mapper = FieldMapper

    def _load_default_profile(self) -> CandidateProfile:
        """Load canonical candidate profile for evidence matching."""
        import yaml
        from job_copilot.config import settings
        from job_copilot.schemas.candidate import PersonalInformation

        profile_path = settings.candidate_profile_path
        if profile_path.exists():
            data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
            return CandidateProfile.model_validate(data)
        # Fallback empty profile
        return CandidateProfile(
            personal_info=PersonalInformation(
                full_name="Candidate",
                email="candidate@example.com",
                phone="+1234567890",
                location="Remote",
            )
        )

    async def execute_task(self, task_id: str) -> BrowserTaskModel:
        """
        Execute the browser task from URL validation to READY_FOR_REVIEW.
        """
        task = self.task_repo.get_by_task_id(task_id)
        if not task:
            raise ValueError(f"Browser task '{task_id}' not found.")

        # 1. Resolve Source Adapter & Validate Domain
        try:
            adapter = self.adapter_registry.get_adapter(source=task.source, target_url=task.target_url)
        except DomainSecurityError as dse:
            logger.warning(f"Domain security check failed for task '{task_id}': {dse}")
            self.task_repo.update_status(
                task_id,
                BrowserTaskStatus.BLOCKED,
                pause_reason=str(dse),
            )
            return self.task_repo.get_by_task_id(task_id)

        # 2. Check Duplicate Application Guard (Phase 8 Tracking)
        if task.application_id:
            try:
                app = self.app_repo.get_by_application_id(task.application_id)
                if app and app.status in (ApplicationStatus.APPLIED, ApplicationStatus.OFFER, ApplicationStatus.REJECTED, ApplicationStatus.WITHDRAWN):
                    logger.warning(
                        f"Task '{task_id}' targets already {app.status.value} application '{task.application_id}'. Blocking duplicate preparation."
                    )
                    self.task_repo.update_status(
                        task_id,
                        BrowserTaskStatus.BLOCKED,
                        pause_reason=f"DUPLICATE_APPLICATION: Application '{task.application_id}' is already {app.status.value}",
                    )
                    self.task_repo.append_audit_event(
                        task_id,
                        {
                            "event": "duplicate_application_blocked",
                            "application_status": app.status.value,
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                        },
                    )
                    return self.task_repo.get_by_task_id(task_id)
            except Exception as e:
                logger.debug(f"Notice while checking application status: {e}")

        # 3. Mark task as RUNNING
        self.task_repo.update_status(task_id, BrowserTaskStatus.RUNNING)
        self.task_repo.append_audit_event(
            task_id,
            {"event": "task_started", "source": adapter.source_name, "target_url": task.target_url, "timestamp": datetime.now(timezone.utc).isoformat()},
        )

        # 4. Check for active authenticated session state
        storage_state_path = None
        active_session = self.session_manager.get_active_session_for_source(adapter.source_name)
        if active_session:
            sess_path = self.session_store.get_session_path(active_session.session_id)
            if sess_path.exists():
                storage_state_path = str(sess_path)
                logger.info(f"Restoring authenticated session '{active_session.session_id}' for '{adapter.source_name}'")

        browser_adapter = await self.browser_manager.get_adapter(storage_state_path=storage_state_path)
        session = BrowserSessionAdapter(browser_adapter)

        try:
            # 5. Navigation
            await session.navigate(task.target_url)
            await session.wait_for_idle()

            # 6. Initial Screenshot -> ArtifactService
            initial_screenshot_art_id = await self._capture_and_store_screenshot(
                session, task_id, task.application_id, "initial_page.png"
            )

            # 7. Check Anti-Bot / CAPTCHA via Adapter
            if await adapter.detect_captcha(session):
                logger.warning(f"CAPTCHA challenge detected on '{task.target_url}'. Pausing task '{task_id}'.")
                self.task_repo.update_status(
                    task_id,
                    BrowserTaskStatus.CAPTCHA_REQUIRED,
                    pause_reason="CAPTCHA challenge detected on page",
                )
                self.task_repo.append_audit_event(
                    task_id, {"event": "captcha_detected", "timestamp": datetime.now(timezone.utc).isoformat()}
                )
                return self.task_repo.get_by_task_id(task_id)

            # 8. Check Login Wall via Adapter
            if await adapter.detect_login(session):
                logger.info(f"Login authentication required on '{task.target_url}'. Pausing task '{task_id}'.")
                self.task_repo.update_status(
                    task_id,
                    BrowserTaskStatus.LOGIN_REQUIRED,
                    pause_reason="Authentication login wall detected",
                )
                if active_session:
                    self.session_manager.mark_login_required(active_session.session_id)
                self.task_repo.append_audit_event(
                    task_id, {"event": "login_required", "timestamp": datetime.now(timezone.utc).isoformat()}
                )
                return self.task_repo.get_by_task_id(task_id)

            # 9. Verify Job Identity (Wrong-Job Protection)
            id_matched, id_reason = await adapter.verify_job_identity(session, expected_company=task.job_id, expected_title=task.application_id)
            if not id_matched:
                logger.warning(f"Job identity mismatch for task '{task_id}': {id_reason}")
                self.task_repo.update_status(
                    task_id,
                    BrowserTaskStatus.BLOCKED,
                    pause_reason=f"JOB_IDENTITY_MISMATCH: {id_reason}",
                )
                self.task_repo.append_audit_event(
                    task_id, {"event": "job_identity_mismatch", "reason": id_reason, "timestamp": datetime.now(timezone.utc).isoformat()}
                )
                return self.task_repo.get_by_task_id(task_id)

            # 10. Form Inspection & Field Classification via Adapter
            fields = await adapter.inspect_form(session)
            fields_summary: List[DetectedFieldInfo] = []
            requires_user_input = False
            pause_reason = None
            warnings: List[str] = []

            for field in fields:
                field_text = f"{field.label or ''} {field.name or ''} {field.placeholder or ''}".strip()

                # A. Prohibited Check
                if is_prohibited_field(field_text):
                    fields_summary.append(
                        DetectedFieldInfo(
                            field_id=field.field_id,
                            element_type=field.element_type.value,
                            label=field.label,
                            name=field.name,
                            action=FieldAction.DO_NOT_FILL,
                            reason="Prohibited security/credential field skipped",
                        )
                    )
                    continue

                # B. Sensitive Field Check
                if is_sensitive_field(field_text):
                    requires_user_input = True
                    pause_reason = f"Sensitive question requiring human input: '{field.label or field.name}'"
                    fields_summary.append(
                        DetectedFieldInfo(
                            field_id=field.field_id,
                            element_type=field.element_type.value,
                            label=field.label,
                            name=field.name,
                            action=FieldAction.REQUIRES_USER_INPUT,
                            reason=f"Sensitive field: {field.label or field.name}",
                        )
                    )
                    continue

                # C. Resume File Upload
                if field.element_type == BrowserElementType.INPUT_FILE:
                    uploaded = await self._handle_file_upload(session, field, task)
                    if uploaded:
                        fields_summary.append(
                            DetectedFieldInfo(
                                field_id=field.field_id,
                                element_type=field.element_type.value,
                                label=field.label,
                                name=field.name,
                                action=FieldAction.AUTO_FILL,
                                filled_value_masked="[RESUME_UPLOADED]",
                                reason="Tailored resume uploaded via ArtifactService",
                                evidence_source="ArtifactService",
                            )
                        )
                    else:
                        fields_summary.append(
                            DetectedFieldInfo(
                                field_id=field.field_id,
                                element_type=field.element_type.value,
                                label=field.label,
                                name=field.name,
                                action=FieldAction.REQUIRES_USER_INPUT,
                                reason="File upload field requires user selection",
                            )
                        )
                    continue

                # D. Candidate Field Autofill
                val, source_key = self._resolve_candidate_field_value(field_text)
                if val:
                    await session.fill_field(field, val)
                    fields_summary.append(
                        DetectedFieldInfo(
                            field_id=field.field_id,
                            element_type=field.element_type.value,
                            label=field.label,
                            name=field.name,
                            action=FieldAction.AUTO_FILL,
                            filled_value_masked=mask_sensitive_value(val),
                            reason=f"Autofilled from candidate {source_key}",
                            evidence_source=f"candidate_profile.{source_key}",
                        )
                    )
                else:
                    # Unknown field
                    if field.required:
                        requires_user_input = True
                        pause_reason = f"Required field with no candidate match: '{field.label or field.name}'"
                    fields_summary.append(
                        DetectedFieldInfo(
                            field_id=field.field_id,
                            element_type=field.element_type.value,
                            label=field.label,
                            name=field.name,
                            action=FieldAction.UNKNOWN,
                            reason="No candidate evidence match found",
                        )
                    )

            # 8. Post-Fill Screenshot -> ArtifactService
            ready_screenshot_art_id = await self._capture_and_store_screenshot(
                session, task_id, task.application_id, "form_ready_for_review.png"
            )

            # 9. Handle User Input Required Pause
            if requires_user_input:
                self.task_repo.update_status(
                    task_id,
                    BrowserTaskStatus.USER_INPUT_REQUIRED,
                    pause_reason=pause_reason or "Form contains fields requiring user input",
                )
                self.task_repo.append_audit_event(
                    task_id,
                    {"event": "user_input_required", "reason": pause_reason, "timestamp": datetime.now(timezone.utc).isoformat()},
                )
                return self.task_repo.get_by_task_id(task_id)

            # 10. Generate Confirmation Token and Review Package -> READY_FOR_REVIEW
            token = HumanConfirmationService.generate_confirmation_token()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

            autofilled_count = sum(1 for f in fields_summary if f.action == FieldAction.AUTO_FILL)
            skipped_count = sum(1 for f in fields_summary if f.action in (FieldAction.DO_NOT_FILL, FieldAction.UNKNOWN))
            input_req_count = sum(1 for f in fields_summary if f.action == FieldAction.REQUIRES_USER_INPUT)

            review_pkg = BrowserTaskReviewPackage(
                task_id=task_id,
                application_id=task.application_id,
                job_id=task.job_id,
                source=task.source,
                target_url=task.target_url,
                fields_detected=len(fields),
                fields_autofilled=autofilled_count,
                fields_skipped=skipped_count,
                fields_requiring_user_input=input_req_count,
                fields_summary=fields_summary,
                initial_screenshot_artifact_id=initial_screenshot_art_id,
                ready_screenshot_artifact_id=ready_screenshot_art_id,
                warnings=warnings,
                confirmation_token=token,
                confirmation_expires_at=expires_at,
            )

            self.task_repo.set_review_package(
                task_id=task_id,
                review_package=review_pkg.model_dump(mode="json"),
                confirmation_token=token,
                confirmation_expires_at=expires_at,
            )
            self.task_repo.update_status(task_id, BrowserTaskStatus.READY_FOR_REVIEW)
            self.task_repo.append_audit_event(
                task_id,
                {
                    "event": "ready_for_review",
                    "fields_autofilled": autofilled_count,
                    "confirmation_token_issued": True,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                },
            )

            logger.info(f"Task '{task_id}' reached READY_FOR_REVIEW. Awaiting explicit human confirmation.")
            return self.task_repo.get_by_task_id(task_id)

        except Exception as e:
            logger.error(f"Task execution failed for '{task_id}': {e}")
            self.task_repo.update_status(task_id, BrowserTaskStatus.FAILED, failure_reason=str(e))
            self.task_repo.append_audit_event(
                task_id, {"event": "worker_failed", "error": str(e), "timestamp": datetime.now(timezone.utc).isoformat()}
            )
            return self.task_repo.get_by_task_id(task_id)

        finally:
            await self.browser_manager.close()

    async def _capture_and_store_screenshot(
        self,
        session: BrowserSessionAdapter,
        task_id: str,
        application_id: Optional[str],
        filename: str,
    ) -> Optional[str]:
        """Capture page screenshot and persist to Phase 10A ArtifactService."""
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            saved = await session.screenshot(tmp_path)
            if saved and Path(tmp_path).exists():
                data = Path(tmp_path).read_bytes()
                record = self.artifact_service.store_artifact(
                    data=data,
                    artifact_type=ArtifactType.SCREENSHOT,
                    application_id=application_id,
                    original_filename=filename,
                    content_type="image/png",
                    metadata={"task_id": task_id, "captured_at": datetime.now(timezone.utc).isoformat()},
                )
                return record.artifact_id
        except Exception as e:
            logger.warning(f"Failed to capture and store screenshot: {e}")
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    async def _handle_file_upload(
        self,
        session: BrowserSessionAdapter,
        field: BrowserField,
        task: BrowserTaskModel,
    ) -> bool:
        """Fetch resume artifact from ArtifactService and upload to file input."""
        app_id = task.application_id or task.job_id
        if not app_id:
            return False

        artifacts = self.artifact_service.list_artifacts(
            application_id=app_id,
            artifact_type=ArtifactType.TAILORED_RESUME_PDF,
        )
        if not artifacts:
            return False

        target_artifact = artifacts[0]
        pdf_bytes, _ = self.artifact_service.get_artifact(target_artifact.artifact_id)

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(pdf_bytes)
            tmp_path = tmp.name

        try:
            return await session.upload_file(field, tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def _resolve_candidate_field_value(self, field_text: str) -> Tuple[Optional[str], Optional[str]]:
        """Match form field label against authoritative candidate profile."""
        text = field_text.lower()
        p = self.candidate_profile.personal_info

        if "first name" in text or "given name" in text:
            return p.full_name.split()[0] if p.full_name else None, "first_name"
        if "last name" in text or "surname" in text or "family name" in text:
            parts = p.full_name.split() if p.full_name else []
            return parts[-1] if len(parts) > 1 else "", "last_name"
        if "full name" in text or text == "name":
            return p.full_name, "name"
        if "email" in text:
            return p.email, "email"
        if "phone" in text or "mobile" in text or "cell" in text:
            return p.phone, "phone"
        if "location" in text or "city" in text or "address" in text:
            return p.location, "location"

        for link in p.links:
            if "linkedin" in text and "linkedin" in link.label.lower():
                return link.url, "linkedin"
            if "github" in text and "github" in link.label.lower():
                return link.url, "github"

        return None, None

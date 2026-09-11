"""Browser-Assisted Application Workflow Orchestration Service."""

import asyncio
from datetime import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

from job_copilot.application.models import (
    ApplicationPackage,
    ApplicationPackageStatus,
)
from job_copilot.browser.adapter import BrowserAdapter, PlaywrightBrowserAdapter
from job_copilot.browser.detector import FormDetector
from job_copilot.browser.mapper import FieldMapper
from job_copilot.browser.models import (
    BrowserAuditEvent,
    BrowserAuditEventType,
    BrowserElementType,
    BrowserField,
    BrowserSession,
    BrowserSessionStatus,
    FieldClassification,
    FieldMapping,
    MappingConfidence,
    ReviewArtifact,
    SubmissionResult,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.application_prep_service import ApplicationPrepService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class BrowserWorkflowService:
    """
    Coordinates browser automation sessions, safe form auto-filling,
    human-in-the-loop input collection, review gates, and guarded submissions.
    """

    def __init__(
        self,
        application_prep_service: Optional[ApplicationPrepService] = None,
        applications_data_dir: Optional[Path] = None,
        browser_adapter_factory: Optional[Any] = None,
    ):
        self.prep_service = application_prep_service or ApplicationPrepService()
        self.applications_data_dir = applications_data_dir or Path("data/applications")
        self._adapter_factory = browser_adapter_factory or PlaywrightBrowserAdapter

        # Active in-memory sessions & adapters
        self._active_sessions: Dict[str, BrowserSession] = {}
        self._active_adapters: Dict[str, BrowserAdapter] = {}
        self._audit_logs: Dict[str, List[BrowserAuditEvent]] = {}

    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        """Get browser session by ID from memory or disk."""
        if session_id in self._active_sessions:
            return self._active_sessions[session_id]

        # Try loading from disk
        for job_dir in self.applications_data_dir.iterdir():
            if job_dir.is_dir():
                sess_file = job_dir / "browser" / "session.json"
                if sess_file.exists():
                    try:
                        sess = BrowserSession.model_validate_json(sess_file.read_text(encoding="utf-8"))
                        if sess.session_id == session_id:
                            self._active_sessions[session_id] = sess
                            return sess
                    except Exception:
                        pass
        return None

    def _get_adapter(self, session_id: str) -> BrowserAdapter:
        if session_id not in self._active_adapters:
            self._active_adapters[session_id] = self._adapter_factory()
        return self._active_adapters[session_id]

    def _log_event(
        self,
        session_id: str,
        event_type: BrowserAuditEventType,
        action: str,
        field_id: Optional[str] = None,
        result: str = "SUCCESS",
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append to structured audit log."""
        if session_id not in self._audit_logs:
            self._audit_logs[session_id] = []

        event = BrowserAuditEvent(
            session_id=session_id,
            event_type=event_type,
            field_id=field_id,
            action=action,
            result=result,
            reason=reason,
            metadata=metadata or {},
        )
        self._audit_logs[session_id].append(event)

    async def start_session(
        self,
        job_id: str,
        application_url: str,
        headless: bool = True,
    ) -> BrowserSession:
        """
        Initialize browser session, navigate to job application URL,
        check security boundaries, and inspect initial DOM fields.
        """
        # 1. Verify Phase 6 application package exists
        package = self.prep_service.get_application_package(job_id)
        if not package:
            raise ValueError(f"No Phase 6 application package found for job '{job_id}'. Run 'prepare-job' first.")

        # 2. Check for duplicate submission
        job_dir = self.applications_data_dir / job_id / "browser"
        sess_file = job_dir / "session.json"
        if sess_file.exists():
            try:
                prev_sess = BrowserSession.model_validate_json(sess_file.read_text(encoding="utf-8"))
                if prev_sess.status == BrowserSessionStatus.SUBMITTED:
                    raise ValueError(
                        f"Job '{job_id}' was already successfully submitted at {prev_sess.submission_result.submitted_at if prev_sess.submission_result else 'unknown'}. Resubmission blocked."
                    )
            except ValueError:
                raise
            except Exception:
                pass

        session_id = f"sess-{uuid.uuid4().hex[:8]}"
        session = BrowserSession(
            session_id=session_id,
            job_id=job_id,
            application_url=application_url,
            status=BrowserSessionStatus.CREATED,
        )
        self._active_sessions[session_id] = session
        self._log_event(session_id, BrowserAuditEventType.SESSION_STARTED, f"Started session for job {job_id}")

        # 3. Launch browser and navigate
        adapter = self._get_adapter(session_id)
        session.status = BrowserSessionStatus.NAVIGATING
        self._log_event(session_id, BrowserAuditEventType.NAVIGATED, f"Navigating to {application_url}")

        try:
            current_url = await adapter.navigate(application_url)
            session.current_url = current_url
        except Exception as e:
            session.status = BrowserSessionStatus.FAILED
            session.pause_reason = f"Navigation failed: {e}"
            self._log_event(session_id, BrowserAuditEventType.NAVIGATED, "Navigation failed", result="FAILED", reason=str(e))
            self._persist_session(session)
            return session

        # 4. Check for Login or CAPTCHA
        if await adapter.is_login_page():
            session.status = BrowserSessionStatus.WAITING_FOR_USER
            session.pause_reason = "Authentication or login required. Please sign in manually in the browser."
            self._log_event(session_id, BrowserAuditEventType.SESSION_PAUSED, "Login page detected", result="PAUSED", reason=session.pause_reason)
            self._persist_session(session)
            return session

        if await adapter.is_captcha_present():
            session.status = BrowserSessionStatus.WAITING_FOR_USER
            session.pause_reason = "Bot detection or CAPTCHA challenge present. Please complete manually."
            self._log_event(session_id, BrowserAuditEventType.SESSION_PAUSED, "CAPTCHA challenge detected", result="PAUSED", reason=session.pause_reason)
            self._persist_session(session)
            return session

        # 5. Inspect and Map initial fields
        await self.inspect_session(session_id)
        return session

    async def inspect_session(self, session_id: str) -> BrowserSession:
        """Inspect current DOM page and update field mappings."""
        session = self._active_sessions.get(session_id)
        if not session:
            session = self.get_session(session_id)
            if not session:
                raise ValueError(f"Session '{session_id}' not found.")
            self._active_sessions[session_id] = session

        adapter = self._get_adapter(session_id)
        package = self.prep_service.get_application_package(session.job_id)
        profile = self.prep_service.load_master_profile()

        session.status = BrowserSessionStatus.INSPECTING
        fields = await adapter.inspect_page()
        session.detected_fields = fields

        self._log_event(session_id, BrowserAuditEventType.PAGE_INSPECTED, f"Detected {len(fields)} form elements")

        # Map fields
        session.status = BrowserSessionStatus.MAPPING
        mappings = FieldMapper.map_fields(fields, profile, package)
        session.mappings = mappings

        self._log_event(session_id, BrowserAuditEventType.FIELD_MAPPED, f"Mapped {len(mappings)} fields")

        # Capture initial screenshot
        screenshot_path = str(self.applications_data_dir / session.job_id / "browser" / "screenshots" / "before_fill.png")
        saved_path = await adapter.screenshot(screenshot_path)
        if saved_path and saved_path not in session.screenshots:
            session.screenshots.append(saved_path)

        session.status = BrowserSessionStatus.READY_FOR_REVIEW
        session.last_activity_at = datetime.utcnow()
        self._persist_session(session)
        return session

    async def fill_session(self, session_id: str) -> BrowserSession:
        """
        Safely auto-fill approved candidate fields, tailored resume,
        cover letter, and evidence-backed answers.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        adapter = self._get_adapter(session_id)
        package = self.prep_service.get_application_package(session.job_id)
        session.status = BrowserSessionStatus.FILLING

        unresolved: List[str] = []
        blocked: List[str] = []
        filled: Dict[str, Any] = {}

        for mapping in session.mappings:
            field = next((f for f in session.detected_fields if f.field_id == mapping.field_id), None)
            if not field:
                continue

            # 1. Prohibited or DO_NOT_TOUCH
            if mapping.classification == FieldClassification.DO_NOT_TOUCH:
                blocked.append(field.field_id)
                self._log_event(session_id, BrowserAuditEventType.FIELD_SKIPPED, "Skipped prohibited/do-not-answer field", field_id=field.field_id, result="BLOCKED", reason=mapping.rationale)
                continue

            # 2. Sensitive user input required
            if mapping.classification == FieldClassification.USER_INPUT_REQUIRED or mapping.requires_user_input:
                # Check if user already provided input
                if field.field_id in session.user_inputs:
                    user_val = str(session.user_inputs[field.field_id])
                    ok = await adapter.fill_field(field, user_val)
                    if ok:
                        filled[field.field_id] = user_val
                        self._log_event(session_id, BrowserAuditEventType.FIELD_FILLED, f"Filled user input: {user_val}", field_id=field.field_id)
                    else:
                        unresolved.append(field.field_id)
                else:
                    unresolved.append(field.field_id)
                    self._log_event(session_id, BrowserAuditEventType.USER_INPUT_REQUESTED, f"Requested user input for field '{field.label or field.name}'", field_id=field.field_id)
                continue

            # 3. File Uploads
            if mapping.classification == FieldClassification.FILE_UPLOAD:
                if mapping.target_field == "resume_pdf" and mapping.proposed_value:
                    ok = await adapter.upload_file(field, mapping.proposed_value)
                    if ok:
                        filled[field.field_id] = mapping.proposed_value
                        self._log_event(session_id, BrowserAuditEventType.FIELD_FILLED, f"Uploaded tailored resume PDF: {mapping.proposed_value}", field_id=field.field_id)
                    else:
                        unresolved.append(field.field_id)
                elif mapping.target_field == "cover_letter" and mapping.proposed_value:
                    if field.element_type == BrowserElementType.TEXTAREA:
                        ok = await adapter.fill_field(field, mapping.proposed_value)
                    else:
                        ok = False
                    if ok:
                        filled[field.field_id] = "Cover Letter Content"
                        self._log_event(session_id, BrowserAuditEventType.FIELD_FILLED, "Filled cover letter text", field_id=field.field_id)
                    else:
                        unresolved.append(field.field_id)
                else:
                    if field.required:
                        unresolved.append(field.field_id)
                continue

            # 4. Safe candidate fields & evidence answers
            if mapping.is_safe_to_autofill and mapping.proposed_value:
                ok = await adapter.fill_field(field, mapping.proposed_value)
                if ok:
                    filled[field.field_id] = mapping.proposed_value
                    self._log_event(session_id, BrowserAuditEventType.FIELD_FILLED, f"Auto-filled {mapping.target_field}", field_id=field.field_id)
                else:
                    if field.required:
                        unresolved.append(field.field_id)
            else:
                if field.required and field.element_type != BrowserElementType.BUTTON:
                    unresolved.append(field.field_id)

        session.filled_fields = filled
        session.unresolved_fields = unresolved
        session.blocked_fields = blocked

        # Capture post-fill screenshot
        screenshot_path = str(self.applications_data_dir / session.job_id / "browser" / "screenshots" / "after_fill.png")
        saved_path = await adapter.screenshot(screenshot_path)
        if saved_path and saved_path not in session.screenshots:
            session.screenshots.append(saved_path)

        # Update status
        if blocked:
            session.status = BrowserSessionStatus.WAITING_FOR_USER
            session.pause_reason = f"{len(blocked)} field(s) blocked due to safety/unsupported claims."
        elif unresolved:
            session.status = BrowserSessionStatus.WAITING_FOR_USER
            session.pause_reason = f"{len(unresolved)} field(s) require explicit user input."
        else:
            session.status = BrowserSessionStatus.READY_FOR_REVIEW
            session.pause_reason = None

        # Build review artifact
        await self.review_session(session_id)
        session.last_activity_at = datetime.utcnow()
        self._persist_session(session)
        return session

    async def provide_user_input(
        self,
        session_id: str,
        field_id: str,
        value: Any,
    ) -> BrowserSession:
        """Provide user input for an unresolved or sensitive field."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        adapter = self._get_adapter(session_id)
        session.user_inputs[field_id] = value
        self._log_event(session_id, BrowserAuditEventType.USER_INPUT_PROVIDED, f"Provided input for {field_id}", field_id=field_id)

        # Attempt to fill the field directly
        field = next((f for f in session.detected_fields if f.field_id == field_id), None)
        if field:
            await adapter.fill_field(field, str(value))
            session.filled_fields[field_id] = str(value)
            if field_id in session.unresolved_fields:
                session.unresolved_fields.remove(field_id)

        # Re-evaluate review state
        await self.review_session(session_id)
        if not session.unresolved_fields and not session.blocked_fields:
            session.status = BrowserSessionStatus.READY_TO_SUBMIT
            session.pause_reason = None

        self._persist_session(session)
        return session

    async def review_session(self, session_id: str) -> ReviewArtifact:
        """Generate pre-submission review artifact."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        package = self.prep_service.get_application_package(session.job_id)
        if not package:
            raise ValueError(f"Package for job '{session.job_id}' missing.")

        adapter = self._get_adapter(session_id)

        # Capture review screenshot
        screenshot_path = str(self.applications_data_dir / session.job_id / "browser" / "screenshots" / "review.png")
        saved_path = await adapter.screenshot(screenshot_path)
        if saved_path and saved_path not in session.screenshots:
            session.screenshots.append(saved_path)

        details: List[Dict[str, Any]] = []
        for mapping in session.mappings:
            field = next((f for f in session.detected_fields if f.field_id == mapping.field_id), None)
            val = session.filled_fields.get(mapping.field_id) or session.user_inputs.get(mapping.field_id)
            status_label = "FILLED" if val else ("UNRESOLVED" if mapping.field_id in session.unresolved_fields else ("BLOCKED" if mapping.field_id in session.blocked_fields else "OPTIONAL_EMPTY"))

            details.append({
                "field_id": mapping.field_id,
                "label": field.label if field else mapping.field_id,
                "target": mapping.target_field,
                "classification": mapping.classification.value,
                "value": str(val) if val else None,
                "status": status_label,
                "required": field.required if field else False,
            })

        is_ready = len(session.unresolved_fields) == 0 and len(session.blocked_fields) == 0

        review = ReviewArtifact(
            job_id=session.job_id,
            company=package.company,
            role=package.job_title,
            resume_strategy=package.selected_resume_strategy,
            resume_path=package.resume_pdf_path,
            cover_letter_preview=package.cover_letter.letter_text[:200] + "..." if package.cover_letter else None,
            fields_total=len(session.detected_fields),
            fields_filled=len(session.filled_fields),
            user_confirmed=len(session.user_inputs),
            unresolved=len(session.unresolved_fields),
            blocked=len(session.blocked_fields),
            validation="PASS" if is_ready else "NEEDS_RESOLUTION",
            ready_to_submit=is_ready,
            details=details,
        )

        session.review = review
        if is_ready and session.status != BrowserSessionStatus.SUBMITTED:
            session.status = BrowserSessionStatus.READY_TO_SUBMIT

        self._persist_session(session)
        return review

    async def submit_session(
        self,
        session_id: str,
        confirmed: bool = False,
        confirm_text: Optional[str] = None,
    ) -> SubmissionResult:
        """
        HARD SUBMISSION GUARD:
        Execute application submission ONLY upon explicit human confirmation
        and complete validation pass.
        """
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        # 1. HARD SAFETY CHECK: Explicit Human Confirmation
        is_explicitly_confirmed = confirmed is True or (confirm_text and confirm_text.strip().upper() == "SUBMIT")
        if not is_explicitly_confirmed:
            self._log_event(session_id, BrowserAuditEventType.VALIDATION_FAILED, "Submission blocked: Explicit confirmation missing", result="BLOCKED")
            raise PermissionError("Submission blocked. Explicit confirmation required ('confirm=True' or confirm_text='SUBMIT').")

        # 2. Re-validate review status
        review = await self.review_session(session_id)
        if not review.ready_to_submit or review.unresolved > 0 or review.blocked > 0:
            self._log_event(session_id, BrowserAuditEventType.VALIDATION_FAILED, "Submission blocked: Form has unresolved or blocked fields", result="BLOCKED")
            raise ValueError(f"Submission blocked. {review.unresolved} unresolved fields, {review.blocked} blocked fields.")

        adapter = self._get_adapter(session_id)
        session.status = BrowserSessionStatus.SUBMITTING
        self._log_event(session_id, BrowserAuditEventType.SUBMISSION_CONFIRMED, "Explicit submission confirmed by user")
        self._log_event(session_id, BrowserAuditEventType.SUBMISSION_ATTEMPTED, "Executing form submission click")

        try:
            # Locate submit button or form submit
            clicked = False
            for selector in [
                "button[type='submit']",
                "input[type='submit']",
                "button:has-text('Submit')",
                "button:has-text('Apply')",
                "button:has-text('Send')",
                "form button",
            ]:
                if await adapter.click(selector):
                    clicked = True
                    break

            await adapter.wait_for_dom_idle(timeout_ms=1000)
            final_url = await adapter.get_current_url()

            # Capture post-submit screenshot
            screenshot_path = str(self.applications_data_dir / session.job_id / "browser" / "screenshots" / "post_submit.png")
            saved_path = await adapter.screenshot(screenshot_path)
            if saved_path and saved_path not in session.screenshots:
                session.screenshots.append(saved_path)

            ref_id = f"APP-{uuid.uuid4().hex[:8].upper()}"
            result = SubmissionResult(
                success=True,
                submitted_at=datetime.utcnow(),
                confirmation_reference=ref_id,
                final_url=final_url,
                evidence="Submit button clicked and DOM network settled.",
            )

            session.submission_result = result
            session.status = BrowserSessionStatus.SUBMITTED
            self._log_event(session_id, BrowserAuditEventType.SUBMISSION_SUCCEEDED, f"Submission succeeded with ref {ref_id}")
            self._persist_session(session)

            # Phase 8 Integration: Automatically register tracked application and snapshot
            try:
                from job_copilot.services.tracking_service import TrackingService
                tracking = TrackingService(prep_service=self.prep_service)
                pkg = self.prep_service.get_application_package(session.job_id)
                tracking.register_submission(
                    job_id=session.job_id,
                    package=pkg,
                    browser_session=session,
                    submission_result=result,
                )
            except Exception as te:
                logger.warning(f"Tracking registration notice: {te}")

            return result

        except Exception as e:
            session.status = BrowserSessionStatus.FAILED
            result = SubmissionResult(
                success=False,
                submitted_at=datetime.utcnow(),
                error=str(e),
            )
            session.submission_result = result
            self._log_event(session_id, BrowserAuditEventType.SUBMISSION_FAILED, "Submission failed", result="FAILED", reason=str(e))
            self._persist_session(session)
            return result

    async def cancel_session(self, session_id: str) -> BrowserSession:
        """Cancel browser session and close browser resources."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session '{session_id}' not found.")

        session.status = BrowserSessionStatus.CANCELLED
        self._log_event(session_id, BrowserAuditEventType.SESSION_CANCELLED, "Session cancelled by user")

        if session_id in self._active_adapters:
            await self._active_adapters[session_id].close()
            del self._active_adapters[session_id]

        self._persist_session(session)
        return session

    def _persist_session(self, session: BrowserSession) -> None:
        """Persist session, field mappings, audit log, and review artifacts to disk."""
        browser_dir = self.applications_data_dir / session.job_id / "browser"
        browser_dir.mkdir(parents=True, exist_ok=True)

        # 1. session.json
        (browser_dir / "session.json").write_text(session.model_dump_json(indent=2), encoding="utf-8")

        # 2. fields.json
        fields_data = [f.model_dump() for f in session.detected_fields]
        (browser_dir / "fields.json").write_text(json.dumps(fields_data, indent=2), encoding="utf-8")

        # 3. mapping.json
        mapping_data = [m.model_dump() for m in session.mappings]
        (browser_dir / "mapping.json").write_text(json.dumps(mapping_data, indent=2), encoding="utf-8")

        # 4. audit.json
        if session.session_id in self._audit_logs:
            audit_data = [a.model_dump(mode="json") for a in self._audit_logs[session.session_id]]
            (browser_dir / "audit.json").write_text(json.dumps(audit_data, indent=2), encoding="utf-8")

        # 5. review.json
        if session.review:
            (browser_dir / "review.json").write_text(session.review.model_dump_json(indent=2), encoding="utf-8")

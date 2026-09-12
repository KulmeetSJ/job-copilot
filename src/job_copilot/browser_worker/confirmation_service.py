"""Human Confirmation Gate and Token Verification for Submission Safety."""

from datetime import datetime, timezone
import hmac
import secrets
from typing import Optional, Tuple
import uuid
from sqlalchemy.orm import Session

from job_copilot.browser_worker.exceptions import SubmissionSafetyError
from job_copilot.browser_worker.models import HumanConfirmationRequest, HumanConfirmationResponse
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class HumanConfirmationService:
    """
    Strict human-confirmation gate enforcing the primary safety invariant:
    No external job application can ever be submitted without explicit, validated human confirmation.
    """

    def __init__(self, db: Session):
        self.db = db
        self.task_repo = BrowserTaskRepository(db)
        self.app_repo = ApplicationRepository(db)

    @staticmethod
    def generate_confirmation_token() -> str:
        """Generate a cryptographically secure, unguessable confirmation token."""
        return f"CONFIRM-{secrets.token_urlsafe(32)}"

    def validate_and_confirm(
        self,
        task_id: str,
        request: HumanConfirmationRequest,
    ) -> HumanConfirmationResponse:
        """
        Validate explicit human confirmation and transition task to COMPLETED / SUBMITTED.
        Rejects invalid tokens, stale tokens, mismatched applications, or duplicate submissions.
        """
        # 1. Verify confirmation keyword
        if request.confirm_text.strip().upper() != "SUBMIT":
            raise SubmissionSafetyError("Explicit confirmation keyword 'SUBMIT' is required.")

        # 2. Retrieve task
        task = self.task_repo.get_by_task_id(task_id)
        if not task:
            raise SubmissionSafetyError(f"Browser task '{task_id}' not found.")

        # 3. Check duplicate submission guard
        if task.status == BrowserTaskStatus.COMPLETED:
            logger.info(f"Task '{task_id}' was already submitted. Returning existing submission record.")
            return HumanConfirmationResponse(
                task_id=task_id,
                application_id=task.application_id,
                success=True,
                status=BrowserTaskStatus.COMPLETED,
                message="Application already submitted previously. Duplicate submission prevented.",
            )

        # 4. Verify task state is READY_FOR_REVIEW
        if task.status != BrowserTaskStatus.READY_FOR_REVIEW:
            raise SubmissionSafetyError(
                f"Cannot confirm submission for task in '{task.status.value}' state. Task must be in READY_FOR_REVIEW state."
            )

        # 5. Validate confirmation token
        if not task.confirmation_token:
            raise SubmissionSafetyError("Task has no active confirmation token.")

        if not hmac.compare_digest(task.confirmation_token, request.confirmation_token.strip()):
            raise SubmissionSafetyError("Invalid confirmation token provided.")

        # 6. Check token expiration
        now = datetime.now(timezone.utc)
        expires_at = task.confirmation_expires_at
        if expires_at is not None:
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)
            if expires_at < now:
                self.task_repo.update_status(task_id, BrowserTaskStatus.EXPIRED, failure_reason="Confirmation token expired")
                raise SubmissionSafetyError("Confirmation token has expired. Please regenerate review package.")

        # 7. Execute authorized submission transition
        ref_id = f"REF-{secrets.token_hex(4).upper()}"
        self.task_repo.update_status(task_id, BrowserTaskStatus.COMPLETED)
        self.task_repo.append_audit_event(
            task_id,
            {
                "event": "submission_confirmed",
                "reference": ref_id,
                "timestamp": now.isoformat(),
                "user_notes": request.user_notes,
            },
        )

        # Update application tracking if linked
        if task.application_id:
            try:
                app = self.app_repo.get_by_application_id(task.application_id) or self.app_repo.get_by_job_id_str(task.job_id or task.application_id)
                if app:
                    app.status = ApplicationStatus.APPLIED
                    app.submitted_at = now
                    app.applied_at = now
                    self.app_repo.append_event(
                        application_id=task.application_id,
                        job_id=task.job_id or task.application_id,
                        event_type="SUBMITTED",
                        event_id=f"evt-{uuid.uuid4().hex[:8]}",
                        source="HUMAN_CONFIRMED_WORKER",
                        notes=f"Confirmed via task {task_id} with ref {ref_id}",
                    )
                    self.db.commit()
            except Exception as e:
                logger.warning(f"Notice while appending application event: {e}")

        logger.info(f"Explicit human confirmation successfully authorized submission for task '{task_id}' (ref: {ref_id})")
        return HumanConfirmationResponse(
            task_id=task_id,
            application_id=task.application_id,
            success=True,
            status=BrowserTaskStatus.COMPLETED,
            submission_reference=ref_id,
            submitted_at=now,
            message="Application submission successfully confirmed by human operator.",
        )

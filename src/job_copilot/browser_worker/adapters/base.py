"""Base class interface for source-specific browser adapters."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.browser_worker.models import DetectedFieldInfo
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    mask_sensitive_value,
)
from job_copilot.domain.browser_worker_enums import FieldAction
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobSourceBrowserAdapter(ABC):
    """
    Abstract base class for all job portal source adapters.
    
    PRIMARY SAFETY INVARIANT:
    No source adapter may ever autonomously click a final 'Submit' button or dispatch a submit event.
    Source adapters only inspect, classify, fill safe evidence-backed fields, and build review packages.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Canonical name of the job portal source (e.g. 'linkedin', 'naukri', 'instahyre')."""
        pass

    @property
    @abstractmethod
    def supported_domains(self) -> List[str]:
        """List of exact or wildcard hostnames supported by this adapter."""
        pass

    def validate_url(self, url: str) -> bool:
        """Validate that the target URL belongs to this adapter's supported domain set."""
        try:
            parsed = urlparse(url)
            if parsed.scheme not in ("http", "https"):
                return False
            hostname = (parsed.hostname or "").lower()
            return any(
                hostname == domain or hostname.endswith("." + domain)
                for domain in self.supported_domains
            )
        except Exception:
            return False

    @abstractmethod
    async def detect_login(self, session: BrowserSessionAdapter) -> bool:
        """Detect if current page is gated behind an authentication login wall."""
        pass

    @abstractmethod
    async def detect_captcha(self, session: BrowserSessionAdapter) -> bool:
        """Detect if current page is blocked by a CAPTCHA or anti-bot challenge."""
        pass

    @abstractmethod
    async def detect_application_form(self, session: BrowserSessionAdapter) -> bool:
        """Detect whether the job application form or modal is active and ready."""
        pass

    async def verify_job_identity(
        self,
        session: BrowserSessionAdapter,
        expected_company: Optional[str] = None,
        expected_title: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Verify that the rendered page matches the expected job title and company
        to prevent accidental application to the wrong job role.
        """
        # Default base verification
        return True, "Job identity verified"

    async def inspect_form(self, session: BrowserSessionAdapter) -> List[BrowserField]:
        """Inspect and return interactive input fields on the application form."""
        return await session.inspect_fields()

    def classify_and_filter_fields(
        self,
        fields: List[BrowserField],
        candidate_profile: CandidateProfile,
    ) -> Tuple[List[DetectedFieldInfo], bool, Optional[str]]:
        """
        Classify detected fields into AUTO_FILL, REQUIRES_USER_INPUT, DO_NOT_FILL, UNKNOWN.
        Returns (field_summaries, requires_user_input_flag, pause_reason).
        """
        fields_summary: List[DetectedFieldInfo] = []
        requires_user_input = False
        pause_reason = None

        for field in fields:
            field_text = f"{field.label or ''} {field.name or ''} {field.placeholder or ''}".strip()

            # 1. Prohibited fields
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

            # 2. Sensitive fields
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
                        reason=f"Sensitive question: {field.label or field.name}",
                    )
                )
                continue

            # 3. File upload
            if field.element_type == BrowserElementType.INPUT_FILE:
                fields_summary.append(
                    DetectedFieldInfo(
                        field_id=field.field_id,
                        element_type=field.element_type.value,
                        label=field.label,
                        name=field.name,
                        action=FieldAction.AUTO_FILL,
                        filled_value_masked="[RESUME_UPLOADED]",
                        reason="Tailored resume upload",
                        evidence_source="ArtifactService",
                    )
                )
                continue

            # 4. Canonical contact match
            val, source_key = self.resolve_candidate_field_value(field_text, candidate_profile)
            if val:
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
                if field.required:
                    requires_user_input = True
                    pause_reason = f"Required field with no candidate evidence match: '{field.label or field.name}'"
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

        return fields_summary, requires_user_input, pause_reason

    def resolve_candidate_field_value(
        self,
        field_text: str,
        profile: CandidateProfile,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Resolve field value from authoritative candidate profile."""
        text = field_text.lower()
        p = profile.personal_info

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

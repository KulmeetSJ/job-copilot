"""Local Interactive Browser Agent Runtime and Execution Loop."""

import asyncio
import base64
from datetime import datetime, timezone
import os
from pathlib import Path
import tempfile
from typing import Any, Dict, Optional

from job_copilot.browser.adapter import PlaywrightBrowserAdapter
from job_copilot.browser.classifier import FieldClassifier
from job_copilot.browser.mapper import FieldMapper
from job_copilot.browser.models import BrowserElementType, BrowserField
from job_copilot.browser_agent.client import AgentProtocolClient
from job_copilot.browser_agent.config import AgentConfig, LOCAL_SESSIONS_DIR
from job_copilot.browser_worker.adapters import SourceAdapterRegistry
from job_copilot.browser_worker.adapters.base import JobSourceBrowserAdapter
from job_copilot.browser_worker.browser import BrowserSessionAdapter
from job_copilot.browser_worker.exceptions import (
    CaptchaDetectedError,
    DomainSecurityError,
    LoginRequiredError,
)
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    validate_local_agent_target_url,
    validate_target_domain,
)
from job_copilot.domain.browser_worker_enums import BrowserTaskStatus
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class LocalBrowserAgentRunner:
    """
    Local Interactive Browser Agent.
    Runs on the user's machine with a visible Playwright browser.
    Keeps the same browser session open for interactive human intervention (CAPTCHA, Login, MFA).
    """

    def __init__(
        self,
        config: AgentConfig,
        candidate_profile: Optional[CandidateProfile] = None,
        client: Optional[AgentProtocolClient] = None,
    ):
        self.config = config
        self.client = client or AgentProtocolClient(config)
        self.candidate_profile = candidate_profile or self._load_local_profile()
        self.adapter_registry = SourceAdapterRegistry()
        self.classifier = FieldClassifier()
        self.mapper = FieldMapper
        self._running = False
        self._active_adapter: Optional[PlaywrightBrowserAdapter] = None
        self._active_session_adapter: Optional[BrowserSessionAdapter] = None

    @property
    def active_page(self):
        """Expose underlying Playwright page for testing / inspection."""
        if self._active_adapter:
            return getattr(self._active_adapter, "_page", None)
        return None

    @property
    def active_context(self):
        """Expose underlying Playwright browser context for testing / inspection."""
        if self._active_adapter:
            return getattr(self._active_adapter, "_context", None)
        return None

    def _load_local_profile(self) -> CandidateProfile:
        """Load candidate profile if available in current repository or defaults."""
        import yaml
        from job_copilot.config import settings
        from job_copilot.schemas.candidate import PersonalInformation

        profile_path = settings.candidate_profile_path
        if profile_path.exists():
            try:
                data = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
                return CandidateProfile.model_validate(data)
            except Exception:
                pass
        return CandidateProfile(
            personal_info=PersonalInformation(
                full_name="Candidate",
                email="candidate@example.com",
                phone="+1234567890",
                location="Remote",
            )
        )

    async def start(self) -> None:
        """Start the local agent task polling and execution loop."""
        self._running = True
        logger.info(f"Local Interactive Browser Agent started. Connecting to {self.config.server_url}...")
        print(f"\n==================================================")
        print(f"  JOB COPILOT LOCAL BROWSER AGENT")
        print(f"  Server: {self.config.server_url}")
        print(f"  Device: {self.config.device_name} ({self.config.device_id or 'unpaired'})")
        print(f"  Mode:   Visible Browser (Interactive Human Support)")
        print(f"==================================================\n")

        # Verify device connection
        try:
            info = await self.client.get_device_info()
            print(f"[OK] Device verified. Status: {info.get('status')} | Cap: {len(info.get('capabilities', []))} features")
        except Exception as e:
            print(f"[ERROR] Connection check failed: {e}")
            print(f"Run `python -m job_copilot.browser_agent pair <code>` to pair this machine.\n")
            return

        print(f"[*] Polling for authorized tasks every {self.config.poll_interval_seconds}s. Press Ctrl+C to stop.\n")

        while self._running:
            try:
                poll_res = await self.client.poll_tasks()
                if poll_res.get("has_task") and poll_res.get("task"):
                    task_data = poll_res["task"]
                    await self.process_task(task_data)
                else:
                    await asyncio.sleep(self.config.poll_interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Error during task polling loop: {e}")
                await asyncio.sleep(self.config.poll_interval_seconds)

        await self.shutdown()

    async def process_task(self, task: Dict[str, Any]) -> None:
        """Process an authorized browser task with same-session human interaction."""
        task_id = task["task_id"]
        source = task.get("source", "generic")
        target_url = task["target_url"]
        status = task.get("status", "QUEUED")

        print(f"\n>>> [TASK CLAIMED] ID: {task_id}")
        print(f"    Source:     {source}")
        print(f"    Target URL: {target_url}")
        print(f"    Status:     {status}")

        # 1. Local defense-in-depth URL security validation (SSRF / local network / scheme protection)
        try:
            validate_local_agent_target_url(target_url, allow_test_fixture=self.config.allow_test_fixture)
            source_adapter = self.adapter_registry.get_adapter(source=source, target_url=target_url)
        except DomainSecurityError as dse:
            print(f"[REJECTED] Domain security validation failed: {dse}")
            await self.client.update_task_status(
                task_id=task_id,
                status="FAILED",
                failure_reason=str(dse),
            )
            return

        # 2. Launch visible browser adapter (or reuse active if same task)
        try:
            if not self._active_adapter:
                self._active_adapter = PlaywrightBrowserAdapter()
                # Use local sessions directory (credentials never leave this machine)
                session_path = LOCAL_SESSIONS_DIR / f"{source.lower()}_session.json"
                storage_state = str(session_path) if session_path.exists() else None
                await self._active_adapter.launch(headless=self.config.headless, storage_state_path=storage_state)
                self._active_session_adapter = BrowserSessionAdapter(self._active_adapter)

            sess = self._active_session_adapter
            await self.client.update_task_status(task_id=task_id, status="RUNNING")

            # 3. Navigate if not already on target page
            current_url = await sess.get_current_url()
            if not current_url or current_url == "about:blank" or target_url not in current_url:
                print(f"[*] Navigating to {target_url}...")
                await sess.navigate(target_url)
                await sess.wait_for_idle(2000)

            # Defense-in-depth: verify post-navigation redirect didn't escape to a forbidden address
            post_nav_url = await sess.get_current_url()
            if post_nav_url and post_nav_url != "about:blank":
                validate_local_agent_target_url(post_nav_url, allow_test_fixture=self.config.allow_test_fixture)

            # 4. Challenge Detection & Human Intervention Loop
            # Keeps the SAME browser session open until human completes action
            while True:
                is_captcha = await sess.is_captcha_present()
                is_login = await sess.is_login_required()

                if is_captcha:
                    print("\n" + "=" * 60)
                    print("  [!] HUMAN ACTION REQUIRED: CAPTCHA DETECTED")
                    print("  Please complete the CAPTCHA in the open browser window.")
                    print("  Automation is paused in the same session.")
                    print("=" * 60 + "\n")
                    await self.client.update_task_status(
                        task_id=task_id,
                        status="CAPTCHA_REQUIRED",
                        pause_reason="CAPTCHA verification required. Complete it in the open browser window.",
                    )
                    await self._wait_for_human_challenge_resolution(sess, task_id, challenge_type="CAPTCHA")
                    continue

                if is_login:
                    print("\n" + "=" * 60)
                    print("  [!] HUMAN ACTION REQUIRED: LOGIN / MFA REQUIRED")
                    print("  Please log in directly in the open browser window.")
                    print("  Your credentials remain strictly on this local machine.")
                    print("=" * 60 + "\n")
                    await self.client.update_task_status(
                        task_id=task_id,
                        status="LOGIN_REQUIRED",
                        pause_reason="Authentication login required. Log in directly in the open browser window.",
                    )
                    await self._wait_for_human_challenge_resolution(sess, task_id, challenge_type="LOGIN")
                    continue

                # No blockers detected
                break

            # 5. Execute Form Preparation or Final Submission based on status
            if status == "SUBMISSION_AUTHORIZED":
                # User has confirmed submission in dashboard with 'SUBMIT' keyword!
                await self._execute_authorized_submission(sess, source_adapter, task_id)
            else:
                # Prepare application fields safely
                await self._prepare_application_form(sess, source_adapter, task_id)

        except Exception as e:
            logger.exception(f"Error executing task {task_id}: {e}")
            print(f"[ERROR] Task execution error: {e}")
            try:
                await self.client.update_task_status(
                    task_id=task_id,
                    status="FAILED",
                    failure_reason=str(e),
                )
            except Exception:
                pass

    async def _wait_for_human_challenge_resolution(
        self,
        sess: BrowserSessionAdapter,
        task_id: str,
        challenge_type: str,
    ) -> None:
        """
        Pause automation while keeping the browser open.
        Periodically checks if the challenge disappeared or if user resumed in dashboard.
        """
        print(f"[*] Waiting for human completion in the open browser... (Checking every 1s)")
        for _ in range(600):  # Wait up to 10 minutes
            await asyncio.sleep(1)
            # Re-check challenge presence
            if challenge_type == "CAPTCHA" and not (await sess.is_captcha_present()):
                print(f"[+] CAPTCHA challenge resolved by user! Resuming automation...")
                return
            if challenge_type == "LOGIN" and not (await sess.is_login_required()):
                print(f"[+] Login challenge resolved by user! Resuming automation...")
                return

    async def _prepare_application_form(
        self,
        sess: BrowserSessionAdapter,
        source_adapter: JobSourceBrowserAdapter,
        task_id: str,
    ) -> None:
        """Inspect and fill non-sensitive form fields safely, then upload review package."""
        print("[*] Inspecting form fields...")
        fields = await sess.inspect_fields()
        detected_names = [f.label or f.name or f.id_attr or "field" for f in fields]
        filled_names = []
        unresolved_names = []

        for field in fields:
            field_str = f"{field.name or ''} {field.label or ''}".strip()
            # Check prohibited
            if is_prohibited_field(field_str):
                continue

            # Check sensitive
            if is_sensitive_field(field_str):
                unresolved_names.append(field.label or field.name or "sensitive_field")
                continue

            # Safe fill
            mapping = self.mapper.map_single_field(field, self.candidate_profile)
            if mapping and mapping.is_safe_to_autofill and mapping.proposed_value:
                try:
                    await sess.fill_field(field, mapping.proposed_value)
                    filled_names.append(field.label or field.name or "field")
                except Exception as fe:
                    logger.debug(f"Could not fill field '{field.name}': {fe}")

        # Capture evidence screenshot ONLY on safe non-login review form
        screenshot_base64 = None
        is_safe_for_ss = not (await sess.is_login_required()) and not (await sess.is_captcha_present())
        if is_safe_for_ss:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                await sess.screenshot(tmp_path)
                if Path(tmp_path).exists() and Path(tmp_path).stat().st_size > 0:
                    raw_bytes = Path(tmp_path).read_bytes()
                    screenshot_base64 = base64.b64encode(raw_bytes).decode("utf-8")
            except Exception as se:
                logger.warning(f"Could not capture screenshot: {se}")
            finally:
                if Path(tmp_path).exists():
                    Path(tmp_path).unlink()

        review_package = {
            "detected_fields": detected_names,
            "filled_fields": filled_names,
            "unresolved_fields": unresolved_names,
            "warnings": [],
            "prepared_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"[+] Form prepared: {len(filled_names)} filled, {len(unresolved_names)} requiring input.")
        print(f"[*] Uploading review package to Job Copilot server...")

        await self.client.upload_review_package(
            task_id=task_id,
            fields_detected_count=len(detected_names),
            fields_filled_count=len(filled_names),
            fields_requiring_input_count=len(unresolved_names),
            review_package_json=review_package,
            screenshot_base64=screenshot_base64,
        )

        print("\n" + "=" * 60)
        print("  [SUCCESS] APPLICATION PREPARED FOR REVIEW")
        print("  Review the screenshot and prepared answers in your dashboard.")
        print("  Confirm with 'SUBMIT' when you are ready to authorize final submission.")
        print("=" * 60 + "\n")

    async def _execute_authorized_submission(
        self,
        sess: BrowserSessionAdapter,
        source_adapter: JobSourceBrowserAdapter,
        task_id: str,
    ) -> None:
        """
        Execute final employer submit click in the same session and verify confirmation signal.
        """
        print("\n" + "=" * 60)
        print("  [*] HUMAN SUBMISSION AUTHORIZED — EXECUTING FINAL SUBMIT")
        print("=" * 60 + "\n")

        await self.client.update_task_status(task_id=task_id, status="SUBMISSION_RUNNING")

        # 1. Identify final submit button via adapter
        submit_btn = await source_adapter.get_submit_selector(sess)
        if not submit_btn:
            print("[!] Could not confidently identify final submit button.")
            await self.client.update_task_status(
                task_id=task_id,
                status="HUMAN_ACTION_REQUIRED",
                pause_reason="Submit button not found or ambiguous. Click submit directly in the visible browser.",
            )
            return

        # 2. Click final submit button
        print(f"[*] Clicking submit control: {submit_btn}...")
        await sess.click_element(submit_btn)
        await sess.wait_for_idle(3000)

        # 3. Verify confirmation signal from employer portal
        content = (await sess.get_page_content() or "").lower()
        curr_url = (await sess.get_current_url() or "").lower()
        
        confirmation_indicators = [
            "application submitted",
            "application received",
            "thank you for applying",
            "thanks for applying",
            "your application has been submitted",
            "application complete",
            "successfully submitted",
        ]
        is_confirmed = any(ind in content for ind in confirmation_indicators) or ("confirmation" in curr_url) or ("applied" in curr_url)

        if is_confirmed:
            print(f"[OK] Verified Employer Confirmation at {curr_url}")
            await self.client.upload_completion(
                task_id=task_id,
                employer_confirmation_signal="Application submitted successfully.",
                submission_reference=f"LOCAL-CONFIRM-{int(datetime.now(timezone.utc).timestamp())}",
                evidence_notes=f"Confirmed at {curr_url}",
            )
            print("\n[SUCCESS] Application submitted and confirmed with employer.\n")
        else:
            print("[WARN] Employer confirmation could not be verified automatically.")
            await self.client.update_task_status(
                task_id=task_id,
                status="SUBMISSION_UNVERIFIED",
                pause_reason="Submit was clicked, but external employer confirmation was unverified. Check the portal manually.",
            )

    async def shutdown(self) -> None:
        """Safely close active browser adapter on exit."""
        self._running = False
        if self._active_adapter:
            try:
                await self._active_adapter.close()
            except Exception:
                pass
            self._active_adapter = None
            self._active_session_adapter = None
        print("[*] Local Browser Agent stopped.")

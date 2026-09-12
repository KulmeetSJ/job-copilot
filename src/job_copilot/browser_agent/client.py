"""Outbound HTTP Client for Local Interactive Browser Agent."""

from typing import Any, Dict, Optional
import httpx

from job_copilot.browser_agent.config import AgentConfig
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class AgentProtocolClient:
    """
    Secure outbound HTTPS client communicating with the Job Copilot server.
    All communication is outbound-only — no open ports on the local machine.
    """

    def __init__(self, config: AgentConfig, http_client: Optional[httpx.AsyncClient] = None):
        self.config = config
        self.base_url = config.server_url.rstrip("/")
        self._timeout = 30.0
        self._custom_client = http_client

    def _get_client_ctx(self):
        """Return an async context manager for httpx.AsyncClient."""
        if self._custom_client is not None:
            class _NoCloseWrapper:
                def __init__(self, c):
                    self.c = c
                async def __aenter__(self):
                    return self.c
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return _NoCloseWrapper(self._custom_client)
        return httpx.AsyncClient(timeout=self._timeout)

    @property
    def _headers(self) -> Dict[str, str]:
        headers = {
            "User-Agent": f"JobCopilot-Agent/{self.config.agent_version}",
            "Accept": "application/json",
        }
        if self.config.device_token:
            headers["X-Device-Token"] = self.config.device_token
        return headers

    async def pair(self, pairing_code: str, server_url: Optional[str] = None, device_name: Optional[str] = None) -> Dict[str, Any]:
        """Pair this machine using a 6-digit code from the dashboard."""
        target_url = (server_url or self.base_url).rstrip("/") + "/api/agent/pair"
        payload = {
            "pairing_code": pairing_code.strip(),
            "device_name": device_name or self.config.device_name,
            "agent_version": self.config.agent_version,
            "capabilities": ["playwright_chromium", "visible_browser", "interactive_captcha", "mfa_login"],
        }
        async with self._get_client_ctx() as client:
            resp = await client.post(target_url, json=payload, headers={"User-Agent": f"JobCopilot-Agent/{self.config.agent_version}"})
            if resp.status_code != 200:
                detail = resp.json().get("detail", resp.text) if resp.headers.get("content-type", "").startswith("application/json") else resp.text
                raise ValueError(f"Pairing failed ({resp.status_code}): {detail}")
            data = resp.json()
            # Update in-memory config
            self.config.device_id = data["device_id"]
            self.config.device_token = data["device_token"]
            self.config.server_url = server_url or self.base_url
            self.base_url = self.config.server_url.rstrip("/")
            return data

    async def get_device_info(self) -> Dict[str, Any]:
        """Fetch status and validation of this paired device."""
        if not self.config.device_token:
            raise ValueError("Device is not paired. Run `pair` first.")
        url = f"{self.base_url}/api/agent/device"
        async with self._get_client_ctx() as client:
            resp = await client.get(url, headers=self._headers)
            if resp.status_code != 200:
                raise ValueError(f"Failed to get device info ({resp.status_code}): {resp.text}")
            return resp.json()

    async def poll_tasks(self) -> Dict[str, Any]:
        """Poll server for authorized browser execution tasks."""
        if not self.config.device_token:
            raise ValueError("Device is not paired. Run `pair` first.")
        url = f"{self.base_url}/api/agent/tasks/poll"
        async with self._get_client_ctx() as client:
            resp = await client.get(url, headers=self._headers)
            if resp.status_code != 200:
                raise ValueError(f"Task poll failed ({resp.status_code}): {resp.text}")
            return resp.json()

    async def update_task_status(
        self,
        task_id: str,
        status: str,
        pause_reason: Optional[str] = None,
        failure_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send task status heartbeat or blocker pause notification."""
        url = f"{self.base_url}/api/agent/tasks/{task_id}/heartbeat"
        payload = {
            "task_id": task_id,
            "status": status,
            "pause_reason": pause_reason,
            "failure_reason": failure_reason,
        }
        async with self._get_client_ctx() as client:
            resp = await client.post(url, json=payload, headers=self._headers)
            if resp.status_code != 200:
                raise ValueError(f"Task heartbeat failed ({resp.status_code}): {resp.text}")
            return resp.json()

    async def upload_review_package(
        self,
        task_id: str,
        fields_detected_count: int,
        fields_filled_count: int,
        fields_requiring_input_count: int,
        review_package_json: Dict[str, Any],
        screenshot_base64: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Upload prepared application review package before human confirmation."""
        url = f"{self.base_url}/api/agent/tasks/{task_id}/package"
        payload = {
            "task_id": task_id,
            "fields_detected_count": fields_detected_count,
            "fields_filled_count": fields_filled_count,
            "fields_requiring_input_count": fields_requiring_input_count,
            "review_package_json": review_package_json,
            "screenshot_base64": screenshot_base64,
        }
        async with self._get_client_ctx() as client:
            resp = await client.post(url, json=payload, headers=self._headers)
            if resp.status_code != 200:
                raise ValueError(f"Failed to upload review package ({resp.status_code}): {resp.text}")
            return resp.json()

    async def upload_completion(
        self,
        task_id: str,
        employer_confirmation_signal: str,
        submission_reference: Optional[str] = None,
        evidence_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Submit verified employer submission evidence."""
        url = f"{self.base_url}/api/agent/tasks/{task_id}/complete"
        payload = {
            "task_id": task_id,
            "employer_confirmation_signal": employer_confirmation_signal,
            "submission_reference": submission_reference,
            "evidence_notes": evidence_notes,
        }
        async with self._get_client_ctx() as client:
            resp = await client.post(url, json=payload, headers=self._headers)
            if resp.status_code != 200:
                raise ValueError(f"Failed to report completion ({resp.status_code}): {resp.text}")
            return resp.json()

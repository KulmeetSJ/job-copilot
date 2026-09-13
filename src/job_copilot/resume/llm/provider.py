"""LLM Provider Abstraction for Resume Generation."""

import os
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import ValidationError

from job_copilot.resume.llm.models import LLMResumeDraft
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class LLMResumeProvider(ABC):
    """Abstract interface for LLM resume generation providers."""

    @abstractmethod
    def generate_resume_draft(
        self,
        system_prompt: str,
        user_prompt: str,
        retry_error: str | None = None,
    ) -> LLMResumeDraft | None:
        """Generate a structured resume draft or return None if unavailable/failed."""

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this provider is configured and available to handle requests."""


class OpenAICompatibleResumeProvider(LLMResumeProvider):
    """
    OpenAI-compatible chat completion provider.
    Works seamlessly with OpenAI, Groq, Together, Ollama, DeepSeek, vLLM, or any compatible gateway.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        timeout: float = 45.0,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.timeout = timeout

    def is_available(self) -> bool:
        """Available if a valid API key string is present."""
        return bool(self.api_key and self.api_key.strip())

    def generate_resume_draft(
        self,
        system_prompt: str,
        user_prompt: str,
        retry_error: str | None = None,
    ) -> LLMResumeDraft | None:
        """Generate structured LLMResumeDraft via OpenAI-compatible endpoint."""
        if not self.is_available():
            logger.debug("OpenAICompatibleResumeProvider is not available (no API key).")
            return None

        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        if retry_error:
            messages.append({
                "role": "user",
                "content": (
                    f"CRITICAL CORRECTION REQUIRED:\n"
                    f"Your previous resume draft failed candidate truth grounding validation with these errors:\n"
                    f"{retry_error}\n\n"
                    f"Please regenerate the complete structured JSON response strictly correcting every error. "
                    f"Ensure every metric and technology exists in the candidate's verified evidence."
                ),
            })

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        endpoint = f"{self.base_url}/chat/completions"
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        try:
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(endpoint, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()

            choices = data.get("choices", [])
            if not choices:
                logger.warning("LLM provider returned empty choices.")
                return None

            content = choices[0].get("message", {}).get("content", "")
            if not content:
                logger.warning("LLM provider returned empty message content.")
                return None

            # Attempt clean JSON parse
            try:
                draft = LLMResumeDraft.model_validate_json(content)
                return draft
            except (ValueError, ValidationError) as parse_err:
                # Handle possible markdown fenced JSON: ```json ... ```
                cleaned = re.sub(r"^```json\s*", "", content.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()
                try:
                    return LLMResumeDraft.model_validate_json(cleaned)
                except (ValueError, ValidationError):
                    logger.warning(f"Failed to parse LLM resume draft JSON: {parse_err}")
                    return None

        except httpx.HTTPStatusError as http_err:
            logger.warning(f"LLM API request failed with status {http_err.response.status_code}: {http_err}")
            return None
        except (httpx.RequestError, OSError, RuntimeError, ValueError) as e:
            logger.warning(f"Unexpected error communicating with LLM provider: {e}")
            return None


def get_resume_llm_provider(config: Any | None = None) -> LLMResumeProvider:
    """Factory creating configured LLMResumeProvider."""
    api_key = getattr(config, "openai_api_key", None) or os.getenv("OPENAI_API_KEY")
    base_url = getattr(config, "openai_base_url", None) or os.getenv("OPENAI_BASE_URL") or "https://api.openai.com/v1"
    model = getattr(config, "openai_model", None) or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
    return OpenAICompatibleResumeProvider(api_key=api_key, base_url=base_url, model=model)

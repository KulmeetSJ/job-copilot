"""Local Interactive Browser Agent Configuration & Secure Credential Store."""

import json
import os
from pathlib import Path
from typing import Optional
from pydantic import BaseModel, Field

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".job_copilot"
CONFIG_FILE_PATH = DEFAULT_CONFIG_DIR / "agent_config.json"
LOCAL_SESSIONS_DIR = DEFAULT_CONFIG_DIR / "sessions"


class AgentConfig(BaseModel):
    """Local Agent configuration stored securely on the user's machine."""
    server_url: str = Field(default="http://localhost:8000", description="Job Copilot backend base URL")
    device_id: Optional[str] = Field(default=None, description="Paired unique device identifier")
    device_token: Optional[str] = Field(default=None, description="Secret cryptographic device token")
    device_name: str = Field(default="Local Browser Agent", description="Display name for this machine")
    agent_version: str = Field(default="1.0.0", description="Agent runtime software version")
    poll_interval_seconds: float = Field(default=3.0, description="Task polling interval in seconds")
    headless: bool = Field(default=False, description="Run visible browser window for human interaction")
    allow_test_fixture: bool = Field(default=False, description="Allow local test fixture domains for deterministic testing")


def get_config_dir() -> Path:
    """Ensure ~/.job_copilot directory exists with secure permissions (0700)."""
    DEFAULT_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(DEFAULT_CONFIG_DIR, 0o700)
    except Exception:
        pass
    LOCAL_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(LOCAL_SESSIONS_DIR, 0o700)
    except Exception:
        pass
    return DEFAULT_CONFIG_DIR


def load_agent_config(config_path: Optional[Path] = None) -> AgentConfig:
    """Load local agent configuration from secure disk storage."""
    target = config_path or CONFIG_FILE_PATH
    if not target.exists():
        return AgentConfig()
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return AgentConfig.model_validate(data)
    except Exception as e:
        logger.warning(f"Failed to read agent config from {target}: {e}")
        return AgentConfig()


def save_agent_config(config: AgentConfig, config_path: Optional[Path] = None) -> Path:
    """Save agent configuration with strict private file permissions (0600)."""
    get_config_dir()
    target = config_path or CONFIG_FILE_PATH
    content = config.model_dump_json(indent=2)
    target.write_text(content, encoding="utf-8")
    try:
        os.chmod(target, 0o600)
    except Exception:
        pass
    logger.info(f"Saved local agent configuration to {target}")
    return target


def clear_agent_config(config_path: Optional[Path] = None) -> None:
    """Remove paired device token and reset configuration."""
    target = config_path or CONFIG_FILE_PATH
    if target.exists():
        target.unlink()
        logger.info(f"Removed agent config at {target}")

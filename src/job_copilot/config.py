"""Application configuration management using Pydantic Settings."""

from pathlib import Path
from typing import Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central configuration for Job Copilot."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # General
    app_env: str = Field(default="development", alias="APP_ENV")
    debug: bool = Field(default=True, alias="DEBUG")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # Database
    database_url: str = Field(
        default="sqlite:///./data/job_copilot.db",
        alias="DATABASE_URL",
    )

    # Candidate Profile
    candidate_profile_path: Path = Field(
        default=Path("./data/candidate/master_profile.yaml"),
        alias="CANDIDATE_PROFILE_PATH",
    )

    # MCP Server
    mcp_server_name: str = Field(
        default="job-copilot",
        alias="MCP_SERVER_NAME",
    )

    # API Server (supports standard PORT from Render/cloud providers and API_PORT)
    api_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("API_HOST", "HOST", "api_host", "host"),
    )
    
    api_port: int = Field(
        default=8000,
        validation_alias=AliasChoices("PORT", "API_PORT", "api_port", "port"),
    )

    # Future LLM Integrations (Optional)
    llm_provider: Optional[str] = Field(default="anthropic", alias="LLM_PROVIDER")
    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    anthropic_api_key: Optional[str] = Field(default=None, alias="ANTHROPIC_API_KEY")
    ollama_base_url: Optional[str] = Field(
        default="http://localhost:11434", alias="OLLAMA_BASE_URL"
    )

    @property
    def is_sqlite(self) -> bool:
        """Check if current database is SQLite."""
        return self.database_url.startswith("sqlite")


# Global singleton settings instance
settings = Settings()

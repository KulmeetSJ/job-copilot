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

    # Dashboard Security & CORS (Phase 11 / Phase 12)
    dashboard_api_key: Optional[str] = Field(
        default=None,
        alias="DASHBOARD_API_KEY",
    )
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173",
        alias="CORS_ALLOWED_ORIGINS",
    )

    # Artifact Storage (Phase 10A / Phase 12.2)
    artifact_storage_provider: str = Field(
        default="local",
        validation_alias=AliasChoices("ARTIFACT_STORAGE_PROVIDER", "STORAGE_PROVIDER", "artifact_storage_provider"),
    )
    artifact_storage_dir: Path = Field(
        default=Path("./data/artifacts"),
        validation_alias=AliasChoices("ARTIFACT_STORAGE_DIR", "artifact_storage_dir"),
    )
    artifact_storage_bucket: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "ARTIFACT_STORAGE_BUCKET",
            "S3_BUCKET",
            "AWS_S3_BUCKET",
            "S3_BUCKET_NAME",
            "artifact_storage_bucket",
        ),
    )
    artifact_storage_region: str = Field(
        default="us-east-1",
        validation_alias=AliasChoices(
            "ARTIFACT_STORAGE_REGION",
            "S3_REGION",
            "AWS_REGION",
            "AWS_DEFAULT_REGION",
            "artifact_storage_region",
        ),
    )
    artifact_storage_endpoint: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "ARTIFACT_STORAGE_ENDPOINT",
            "S3_ENDPOINT_URL",
            "S3_ENDPOINT",
            "AWS_ENDPOINT_URL",
            "artifact_storage_endpoint",
        ),
    )
    artifact_storage_access_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "ARTIFACT_STORAGE_ACCESS_KEY",
            "S3_ACCESS_KEY_ID",
            "AWS_ACCESS_KEY_ID",
            "S3_ACCESS_KEY",
            "artifact_storage_access_key",
        ),
    )
    artifact_storage_secret_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "ARTIFACT_STORAGE_SECRET_KEY",
            "S3_SECRET_ACCESS_KEY",
            "AWS_SECRET_ACCESS_KEY",
            "S3_SECRET_KEY",
            "artifact_storage_secret_key",
        ),
    )
    artifact_max_size_bytes: int = Field(
        default=50 * 1024 * 1024,  # 50MB
        validation_alias=AliasChoices("ARTIFACT_MAX_SIZE_BYTES", "artifact_max_size_bytes"),
    )

    def validate_s3_config(self) -> tuple[bool, str]:
        """Validate whether S3 object storage configuration is complete."""
        if not self.artifact_storage_bucket:
            return False, "ARTIFACT_STORAGE_BUCKET (or S3_BUCKET) is not configured."
        return True, "S3 configuration valid."

    @property
    def is_production(self) -> bool:
        """Check if running in production mode."""
        return self.app_env.lower() in ("production", "prod")

    @property
    def is_development(self) -> bool:
        """Check if running in development mode."""
        return self.app_env.lower() in ("development", "dev", "local")

    @property
    def parsed_cors_origins(self) -> list[str]:
        """Return list of parsed CORS origins."""
        raw = self.cors_allowed_origins or ""
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        return origins

    @property
    def is_sqlite(self) -> bool:
        """Check if current database is SQLite."""
        return self.database_url.startswith("sqlite")


# Global singleton settings instance
settings = Settings()

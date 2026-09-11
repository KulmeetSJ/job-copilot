"""Repository for loading, validating, and persisting the Master Candidate Profile."""

from pathlib import Path
from typing import Any, Dict, Optional
import yaml
from pydantic import ValidationError

from job_copilot.config import settings
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CandidateRepository:
    """File-based repository for the Canonical Master Candidate Profile."""

    def __init__(self, profile_path: Optional[Path] = None):
        self.profile_path = profile_path or settings.candidate_profile_path

    def exists(self) -> bool:
        """Check if candidate profile YAML file exists."""
        return self.profile_path.exists()

    def load(self) -> CandidateProfile:
        """
        Load and validate the Master Candidate Profile from YAML.
        
        Raises:
            FileNotFoundError: If the profile file is missing.
            ValidationError: If the YAML contents do not match CandidateProfile schema.
            yaml.YAMLError: If YAML syntax is invalid.
        """
        if not self.profile_path.exists():
            raise FileNotFoundError(
                f"Master profile file not found at: {self.profile_path.resolve()}"
            )

        with open(self.profile_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)

        if raw_data is None:
            raw_data = {}

        return self.validate(raw_data)

    def validate(self, raw_data: Dict[str, Any]) -> CandidateProfile:
        """Validate raw dictionary data against CandidateProfile schema."""
        return CandidateProfile.model_validate(raw_data)

    def save(self, profile: CandidateProfile) -> Path:
        """
        Persist candidate profile to YAML file.
        
        Returns:
            Path to saved file.
        """
        self.profile_path.parent.mkdir(parents=True, exist_ok=True)
        dumped_data = profile.model_dump(mode="json", exclude_none=False)

        with open(self.profile_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(
                dumped_data,
                f,
                sort_keys=False,
                allow_unicode=True,
                default_flow_style=False,
            )

        logger.info(f"Master Candidate Profile saved to: {self.profile_path}")
        return self.profile_path

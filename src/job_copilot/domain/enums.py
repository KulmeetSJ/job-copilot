"""Domain enumerations for Job Copilot."""

from enum import Enum
from typing import Optional


class ApplicationStatus(str, Enum):
    """Lifecycle status of a job application."""
    DISCOVERED = "DISCOVERED"
    SHORTLISTED = "SHORTLISTED"
    PREPARING = "PREPARING"
    READY_TO_APPLY = "READY_TO_APPLY"
    APPLIED = "APPLIED"
    OA = "OA"                      # Online Assessment
    INTERVIEW = "INTERVIEW"
    OFFER = "OFFER"
    REJECTED = "REJECTED"
    WITHDRAWN = "WITHDRAWN"


class ApplicationMode(str, Enum):
    """Execution mode for preparing and submitting a job application."""
    MANUAL = "MANUAL"
    ASSISTED = "ASSISTED"
    AUTO_APPLY = "AUTO_APPLY"


class RemoteStatus(str, Enum):
    """Work arrangement options."""
    REMOTE = "REMOTE"
    HYBRID = "HYBRID"
    ONSITE = "ONSITE"
    UNKNOWN = "UNKNOWN"


class EmploymentType(str, Enum):
    """Type of employment."""
    FULL_TIME = "FULL_TIME"
    PART_TIME = "PART_TIME"
    CONTRACT = "CONTRACT"
    INTERNSHIP = "INTERNSHIP"
    UNKNOWN = "UNKNOWN"


class SkillProficiency(str, Enum):
    """Proficiency level for a skill."""
    BEGINNER = "BEGINNER"
    INTERMEDIATE = "INTERMEDIATE"
    ADVANCED = "ADVANCED"
    EXPERT = "EXPERT"


class ResumeStrategy(str, Enum):
    """Resume tailoring strategic focus (5 locked canonical strategies)."""
    BACKEND_JAVA = "backend_java"
    CLOUD_DEVOPS = "cloud_devops"
    DATA_ENGINEERING = "data_engineering"
    FULL_STACK = "full_stack"
    SRE_DEVOPS = "sre_devops"

    @classmethod
    def normalize(cls, value: Optional[str]) -> str:
        """Map legacy aliases and normalize to one of the 5 canonical strategies."""
        if not value:
            return cls.BACKEND_JAVA.value
        v = str(value).lower().strip().replace("-", "_")
        aliases = {
            "backend_java": cls.BACKEND_JAVA.value,
            "cloud_devops": cls.CLOUD_DEVOPS.value,
            "data_engineering": cls.DATA_ENGINEERING.value,
            "full_stack": cls.FULL_STACK.value,
            "sre_devops": cls.SRE_DEVOPS.value,
            # Legacy alias mappings
            "general_swe": cls.BACKEND_JAVA.value,
            "cloud_infrastructure": cls.CLOUD_DEVOPS.value,
            "cloud_data": cls.DATA_ENGINEERING.value,
            "platform_devops": cls.SRE_DEVOPS.value,
            "ai_backend": cls.BACKEND_JAVA.value,
        }
        return aliases.get(v, cls.BACKEND_JAVA.value)

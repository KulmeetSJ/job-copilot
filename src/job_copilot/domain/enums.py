"""Domain enumerations for Job Copilot."""

from enum import Enum


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
    """Resume tailoring strategic focus."""
    GENERAL_SWE = "GENERAL_SWE"
    BACKEND_JAVA = "BACKEND_JAVA"
    CLOUD_DATA = "CLOUD_DATA"
    PLATFORM_DEVOPS = "PLATFORM_DEVOPS"
    AI_BACKEND = "AI_BACKEND"

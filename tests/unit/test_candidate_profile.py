"""Unit tests for Candidate Profile Pydantic validation and YAML persistence."""

from pathlib import Path
import pytest
from pydantic import ValidationError

from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.schemas.candidate import (
    Achievement,
    CandidateProfile,
    Education,
    Experience,
    PersonalInformation,
    Project,
)


def test_valid_profile_parsing(sample_profile_data: dict):
    """Test that valid candidate profile dict parses successfully into CandidateProfile model."""
    profile = CandidateProfile.model_validate(sample_profile_data)
    assert profile.personal_info.full_name == "Jane Doe"
    assert profile.personal_info.email == "jane.doe@example.com"
    assert len(profile.education) == 1
    assert len(profile.experience) == 1
    assert len(profile.projects) == 1
    assert "45% latency reduction" in profile.experience[0].achievements[0].metrics


def test_invalid_profile_rejection():
    """Test that invalid candidate profile data is rejected with a ValidationError."""
    invalid_data = {
        "version": "1.0.0",
        # Missing required personal_info
        "experience": [],
    }
    with pytest.raises(ValidationError):
        CandidateProfile.model_validate(invalid_data)


def test_invalid_experience_schema():
    """Test that missing required fields on Experience raises ValidationError."""
    with pytest.raises(ValidationError):
        # Missing company and start_date
        Experience(role="Software Engineer")


def test_load_master_profile_from_disk(temp_profile_file: Path):
    """Test that CandidateRepository loads and validates from a YAML file."""
    repo = CandidateRepository(profile_path=temp_profile_file)
    assert repo.exists() is True

    profile = repo.load()
    assert isinstance(profile, CandidateProfile)
    assert profile.personal_info.full_name == "Jane Doe"


def test_load_nonexistent_profile_raises_file_not_found():
    """Test that loading a non-existent file raises FileNotFoundError."""
    repo = CandidateRepository(profile_path=Path("/tmp/nonexistent_profile_9999.yaml"))
    with pytest.raises(FileNotFoundError):
        repo.load()


def test_save_and_reload_profile_roundtrip(temp_profile_file: Path, sample_profile_data: dict):
    """Test that saving a profile and reloading it preserves data fidelity."""
    repo = CandidateRepository(profile_path=temp_profile_file)
    original_profile = CandidateProfile.model_validate(sample_profile_data)

    # Modify an attribute
    original_profile.personal_info.headline = "Lead Systems Architect"
    saved_path = repo.save(original_profile)
    assert saved_path == temp_profile_file

    reloaded_profile = repo.load()
    assert reloaded_profile.personal_info.headline == "Lead Systems Architect"
    assert reloaded_profile.personal_info.full_name == original_profile.personal_info.full_name


def test_default_master_profile_yaml_is_valid():
    """Test that the starter data/candidate/master_profile.yaml in the repo passes schema validation."""
    default_path = Path("data/candidate/master_profile.yaml")
    assert default_path.exists(), "Starter master_profile.yaml should exist in repo"

    repo = CandidateRepository(profile_path=default_path)
    profile = repo.load()
    assert isinstance(profile, CandidateProfile)
    assert profile.personal_info.full_name is not None

from pathlib import Path

from job_copilot.config import Settings


def test_candidate_profile_defaults_to_configured_candidate_directory():
    settings = Settings(CANDIDATE_DATA_DIR=Path("/runtime/private-candidate"))
    assert settings.candidate_data_dir == Path("/runtime/private-candidate")
    assert settings.candidate_profile_path == Path("/runtime/private-candidate/master_profile.yaml")


def test_explicit_candidate_profile_path_overrides_candidate_directory():
    settings = Settings(
        CANDIDATE_DATA_DIR=Path("/runtime/private-candidate"),
        CANDIDATE_PROFILE_PATH=Path("/mnt/profile/custom.yaml"),
    )
    assert settings.candidate_profile_path == Path("/mnt/profile/custom.yaml")

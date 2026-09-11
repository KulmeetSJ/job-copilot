"""Integration tests for Resume Generation, LaTeX Rendering, and PDF Compilation."""

from pathlib import Path
import pytest
from job_copilot.services.resume_service import ResumeService


@pytest.fixture
def service():
    return ResumeService()


@pytest.mark.parametrize("strat_name", [
    "backend_java",
    "cloud_devops",
    "data_engineering",
    "full_stack",
    "sre_devops",
])
def test_generate_all_five_resumes(service, strat_name):
    """Verify that all 5 strategies compile to 1-page valid PDFs without truth violations."""
    res = service.generate_tailored_resume(strat_name)

    assert res.validation.is_valid is True
    assert res.validation.pdf_generated is True
    assert res.pdf_path is not None
    assert res.pdf_path.exists()
    assert res.tex_path.exists()
    assert res.validation.page_count == 1
    assert len(res.validation.truth_violations) == 0
    assert len(res.validation.content_errors) == 0
    assert len(res.validation.latex_errors) == 0


def test_strategies_use_same_facts_differing_positioning(service):
    """Verify that all 5 resumes share the same canonical factual records but differ in positioning."""
    results = {strat: service.generate_tailored_resume(strat) for strat in service.list_strategies()}

    # Check identical factual components
    for strat, res in results.items():
        assert res.tailored_resume.personal_info.full_name == "Kulmeet Singh Jaggi"
        assert res.tailored_resume.experience[0].company == "HSBC"
        assert res.tailored_resume.experience[0].canonical_role == "Software Engineer"
        assert res.tailored_resume.education[0].institution == "Graphic Era Deemed to be University"
        assert res.tailored_resume.certifications[0].name == "Google Cloud Professional Cloud Architect"

    # Check differing positioning
    display_titles = {strat: res.tailored_resume.display_title for strat, res in results.items()}
    assert len(set(display_titles.values())) == 5  # 5 distinct display titles

    summaries = {strat: res.tailored_resume.summary for strat, res in results.items()}
    assert len(set(summaries.values())) == 5  # 5 distinct summaries

"""Integration tests for Model Context Protocol (MCP) server tools."""

from job_copilot.db.database import init_db
from job_copilot.mcp.server import (
    analyze_job,
    get_candidate_profile,
    get_candidate_skills,
    get_experience,
    get_projects,
    list_applications,
    mcp,
)


def test_mcp_instance_initialized():
    """Verify FastMCP server instance is configured with the expected name."""
    assert mcp.name == "job-copilot"


def test_mcp_get_candidate_profile():
    """Test get_candidate_profile tool."""
    profile_data = get_candidate_profile()
    assert isinstance(profile_data, dict)
    assert "personal_info" in profile_data
    assert "full_name" in profile_data["personal_info"]


def test_mcp_get_candidate_skills():
    """Test get_candidate_skills tool."""
    skills_data = get_candidate_skills()
    assert isinstance(skills_data, list)
    if skills_data:
        assert "category" in skills_data[0]
        assert "skills" in skills_data[0]


def test_mcp_get_experience():
    """Test get_experience tool."""
    exp_data = get_experience()
    assert isinstance(exp_data, list)
    if exp_data:
        assert "company" in exp_data[0]
        assert "role" in exp_data[0]


def test_mcp_get_projects():
    """Test get_projects tool."""
    proj_data = get_projects()
    assert isinstance(proj_data, list)
    if proj_data:
        assert "name" in proj_data[0]


def test_mcp_analyze_job():
    """Test analyze_job tool with sample JD text."""
    init_db()
    result = analyze_job(
        description="Looking for a Python backend engineer with experience in FastAPI, PostgreSQL, and AWS.",
        title="Senior Python Backend Developer",
        company="FastTech",
    )
    assert isinstance(result, dict)
    assert result["title"] == "Senior Python Backend Developer"
    assert result["company"] == "FastTech"
    assert "match_score" in result
    assert "recommendation" in result
    assert result["recommendation"] in ["APPLY", "CONSIDER", "SKIP"]


def test_mcp_list_applications():
    """Test list_applications tool."""
    init_db()
    apps = list_applications()
    assert isinstance(apps, list)

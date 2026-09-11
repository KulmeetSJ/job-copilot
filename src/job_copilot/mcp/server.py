"""MCP (Model Context Protocol) Server for Job Copilot.

Exposes conversational tools to AI agents using the official Python MCP SDK.
All business logic and database queries are delegated to the service layer.
"""

from typing import Any, Dict, List, Optional

try:
    from mcp.server.mcpserver import MCPServer
except ImportError:
    from mcp.server.fastmcp import FastMCP as MCPServer

from job_copilot.config import settings
from job_copilot.db.database import SessionLocal, init_db
from job_copilot.domain.enums import ApplicationStatus
from job_copilot.services.application_service import ApplicationService
from job_copilot.services.candidate_service import CandidateService
from job_copilot.services.job_service import JobService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Initialize MCP server application instance
mcp = MCPServer(settings.mcp_server_name)


@mcp.tool()
def get_candidate_profile() -> Dict[str, Any]:
    """Retrieve the canonical Master Candidate Profile source of truth."""
    service = CandidateService()
    profile = service.get_profile()
    return profile.model_dump(mode="json")


@mcp.tool()
def get_candidate_skills() -> List[Dict[str, Any]]:
    """Retrieve structured technical skill categories and proficiency from the Master Profile."""
    service = CandidateService()
    skills = service.get_skills()
    return [s.model_dump(mode="json") for s in skills]


@mcp.tool()
def get_experience() -> List[Dict[str, Any]]:
    """Retrieve verified professional work experience from the Master Profile."""
    service = CandidateService()
    experiences = service.get_experience()
    return [exp.model_dump(mode="json") for exp in experiences]


@mcp.tool()
def get_projects() -> List[Dict[str, Any]]:
    """Retrieve verified project portfolio records from the Master Profile."""
    service = CandidateService()
    projects = service.get_projects()
    return [p.model_dump(mode="json") for p in projects]


@mcp.tool()
def analyze_job(
    description: str,
    title: Optional[str] = None,
    company: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze a job description against the Master Candidate Profile.
    Evaluates skill overlap, calculates a baseline match score, and recommends a resume strategy.
    """
    db = SessionLocal()
    try:
        service = JobService(db)
        result = service.analyze_job(description=description, title=title, company=company)
        return result.model_dump(mode="json")
    finally:
        db.close()


@mcp.tool()
def list_applications(
    status: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    List tracked job applications and their current lifecycle statuses.
    Optional status filter: DISCOVERED, SHORTLISTED, PREPARING, READY_TO_APPLY, APPLIED, OA, INTERVIEW, OFFER, REJECTED, WITHDRAWN.
    """
    db = SessionLocal()
    try:
        service = ApplicationService(db)
        app_status: Optional[ApplicationStatus] = None
        if status:
            try:
                app_status = ApplicationStatus(status.upper())
            except ValueError:
                pass
        apps = service.list_applications(status=app_status)
        return [app.model_dump(mode="json") for app in apps]
    finally:
        db.close()


def main():
    """Run the MCP server via stdio transport."""
    init_db()
    logger.info(f"Starting MCP Server '{settings.mcp_server_name}'...")
    mcp.run()


if __name__ == "__main__":
    main()

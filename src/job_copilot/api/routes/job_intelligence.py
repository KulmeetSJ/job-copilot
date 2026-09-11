"""FastAPI routes for Phase 4 Job Intelligence & Matching Engine."""

from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from job_copilot.matching.models import AnalyzedJob, JobAssessment
from job_copilot.resume.models import ResumeGenerationResult
from job_copilot.services.job_intelligence_service import JobIntelligenceService

router = APIRouter(prefix="/api", tags=["Job Intelligence & Matching Engine"])

service = JobIntelligenceService()


class JobTextRequest(BaseModel):
    """Request payload for raw job description text."""
    job_description: str = Field(description="Raw text of the job description")
    source: str = Field(default="api_input", description="Source indicator")
    source_url: Optional[str] = None
    company_override: Optional[str] = None
    title_override: Optional[str] = None


class JobTailorRequest(JobTextRequest):
    """Request payload for tailoring resume to a job description."""
    strategy_override: Optional[str] = None


@router.post("/analyze-job", response_model=AnalyzedJob, summary="Analyze job description into structured model")
def analyze_job(req: JobTextRequest) -> AnalyzedJob:
    """Extract structured requirements, seniority, must-have/preferred skills, and metadata."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    return service.analyze_job(
        raw_text=req.job_description,
        source=req.source,
        source_url=req.source_url,
        company_override=req.company_override,
        title_override=req.title_override,
    )


@router.post("/match", response_model=JobAssessment, summary="Match candidate profile against job description")
def match_job(req: JobTextRequest) -> JobAssessment:
    """Evaluate candidate facts against JD requirements, compute 7-dimensional fit score, and return gap analysis."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    return service.evaluate_job(
        raw_text=req.job_description,
        source=req.source,
        source_url=req.source_url,
        company_override=req.company_override,
        title_override=req.title_override,
    )


@router.post("/recommend", response_model=JobAssessment, summary="Get application recommendation and report")
def recommend_job(req: JobTextRequest) -> JobAssessment:
    """Generate recommendation (STRONG_APPLY, APPLY, REVIEW, LOW_PRIORITY, SKIP) and explainable report."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    return service.evaluate_job(
        raw_text=req.job_description,
        source=req.source,
        source_url=req.source_url,
        company_override=req.company_override,
        title_override=req.title_override,
    )


@router.post("/tailor", response_model=ResumeGenerationResult, summary="Evaluate job and compile tailored PDF")
def tailor_resume(req: JobTailorRequest) -> ResumeGenerationResult:
    """Chain job assessment to Phase 3 resume tailoring engine to generate a 1-page PDF."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    try:
        return service.tailor_resume_for_job(
            job_text=req.job_description,
            strategy_override=req.strategy_override,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

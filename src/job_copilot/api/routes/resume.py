"""FastAPI routes for Resume Generation, Tailoring, and Analysis."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from job_copilot.resume.models import (
    JobAnalysis,
    JobMatchResult,
    ResumeGenerationResult,
    TailoredResume,
)
from job_copilot.resume.strategy import ResumeStrategyConfig
from job_copilot.services.resume_service import ResumeService

router = APIRouter(prefix="/api/resume", tags=["Resume Tailoring Engine"])

# Initialize resume service
service = ResumeService()


class AnalyzeJobRequest(BaseModel):
    """Request payload for job description analysis."""
    job_description: str = Field(description="Raw text of the job description")
    title_override: Optional[str] = None
    company_override: Optional[str] = None


class TailorResumeRequest(BaseModel):
    """Request payload for resume tailoring."""
    strategy: str = Field(description="Strategy name (e.g. backend_java, cloud_devops)")
    job_description: Optional[str] = None


class RenderResumeRequest(BaseModel):
    """Request payload for compiling a tailored resume to PDF."""
    strategy: str = Field(description="Strategy name (e.g. backend_java, cloud_devops)")
    job_description: Optional[str] = None


@router.get("/strategies", response_model=List[str], summary="List available resume strategies")
def list_strategies() -> List[str]:
    """Return all available resume positioning strategies."""
    return service.list_strategies()


@router.get("/strategies/{name}", response_model=ResumeStrategyConfig, summary="Get strategy details")
def get_strategy(name: str) -> ResumeStrategyConfig:
    """Retrieve full configuration for a specific resume strategy."""
    try:
        return service.get_strategy(name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/analyze-job", response_model=JobAnalysis, summary="Analyze a job description")
def analyze_job(req: AnalyzeJobRequest) -> JobAnalysis:
    """Extract structured requirements, seniority, and ATS keywords from raw job description text."""
    if not req.job_description.strip():
        raise HTTPException(status_code=400, detail="Job description text cannot be empty.")
    return service.analyze_job(
        job_description_text=req.job_description,
        title_override=req.title_override,
        company_override=req.company_override,
    )


@router.post("/match", response_model=JobMatchResult, summary="Match candidate profile against job analysis")
def match_candidate(analysis: JobAnalysis) -> JobMatchResult:
    """Evaluate candidate facts against extracted job requirements with truth safety classification."""
    return service.match_job(analysis)


@router.post("/tailor", response_model=TailoredResume, summary="Construct tailored resume model")
def tailor_resume(req: TailorResumeRequest) -> TailoredResume:
    """Construct strongly typed TailoredResume intermediate representation without rendering."""
    try:
        gen_res = service.generate_tailored_resume(
            strategy_name=req.strategy,
            job_description_text=req.job_description,
        )
        return gen_res.tailored_resume
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/render", response_model=ResumeGenerationResult, summary="Generate and compile tailored PDF")
def render_resume(req: RenderResumeRequest) -> ResumeGenerationResult:
    """Generate, render to LaTeX, compile to PDF, and validate a tailored resume."""
    try:
        return service.generate_tailored_resume(
            strategy_name=req.strategy,
            job_description_text=req.job_description,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/generated/{strategy}", summary="Get latest generated resume info")
def get_generated_resume(strategy: str) -> Dict[str, Any]:
    """Retrieve file paths and validation status of latest generated resume for a strategy."""
    strat_dir = Path("data/generated") / strategy
    tex_path = strat_dir / "latest.tex"
    pdf_path = strat_dir / "latest.pdf"
    val_path = strat_dir / "validation.json"

    if not tex_path.exists():
        raise HTTPException(status_code=404, detail=f"No generated resume found for strategy '{strategy}'.")

    import json
    val_data = {}
    if val_path.exists():
        with open(val_path, "r", encoding="utf-8") as f:
            val_data = json.load(f)

    return {
        "strategy": strategy,
        "tex_path": str(tex_path.resolve()),
        "pdf_path": str(pdf_path.resolve()) if pdf_path.exists() else None,
        "pdf_exists": pdf_path.exists(),
        "validation": val_data,
    }

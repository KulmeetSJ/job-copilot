"""FastAPI routes for Phase 6 Application Preparation."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from job_copilot.application.models import (
    ApplicationAnswer,
    ApplicationPackage,
    ApplicationQuestion,
    CoverLetter,
    UserInputRequest,
)
from job_copilot.services.application_prep_service import ApplicationPrepService

router = APIRouter(prefix="/api/applications", tags=["Application Preparation"])

service = ApplicationPrepService()


class PrepareApplicationRequest(BaseModel):
    """Payload to prepare an application package."""
    job_id_or_text: str = Field(description="Job ID from store or raw job description")
    custom_questions: Optional[List[ApplicationQuestion]] = Field(default=None)
    strategy_override: Optional[str] = None


class AnswerQuestionsRequest(BaseModel):
    """Payload to answer questions for a specific job."""
    questions: List[ApplicationQuestion]


@router.post("/prepare", response_model=ApplicationPackage, summary="Prepare complete application package")
def prepare_application(req: PrepareApplicationRequest) -> ApplicationPackage:
    """Build tailored resume, cover letter, answer questions, and validate package."""
    if not req.job_id_or_text.strip():
        raise HTTPException(status_code=400, detail="Job ID or description text cannot be empty.")
    try:
        return service.prepare_application(
            job_id_or_text=req.job_id_or_text,
            custom_questions=req.custom_questions,
            strategy_override=req.strategy_override,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{job_id}", response_model=ApplicationPackage, summary="Get application package by Job ID")
def get_application(job_id: str) -> ApplicationPackage:
    """Retrieve saved application package from disk."""
    package = service.get_application_package(job_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Application package for '{job_id}' not found.")
    return package


@router.post("/{job_id}/questions", response_model=List[ApplicationAnswer], summary="Answer application questions")
def answer_job_questions(job_id: str, req: AnswerQuestionsRequest) -> List[ApplicationAnswer]:
    """Answer a batch of application questions using candidate evidence."""
    package = service.get_application_package(job_id)
    if not package:
        # Generate package first if not exists
        package = service.prepare_application(job_id_or_text=job_id, custom_questions=req.questions)
        return package.answers

    profile = service.load_master_profile()
    answers: List[ApplicationAnswer] = []
    for q in req.questions:
        ans = service.qa_engine.answer_question(q, profile, package.assessment)
        answers.append(ans)
    return answers


@router.post("/{job_id}/cover-letter", response_model=CoverLetter, summary="Generate or retrieve cover letter")
def get_cover_letter(job_id: str) -> CoverLetter:
    """Generate and validate tailored cover letter for job."""
    package = service.get_application_package(job_id)
    if not package:
        package = service.prepare_application(job_id_or_text=job_id)
    return package.cover_letter


@router.get("/{job_id}/inputs", response_model=List[UserInputRequest], summary="List unresolved user input questions")
def get_user_inputs(job_id: str) -> List[UserInputRequest]:
    """Retrieve unresolved questions requiring human input."""
    package = service.get_application_package(job_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Application package for '{job_id}' not found.")
    return package.user_inputs_required


@router.post("/{job_id}/validate", summary="Validate application package")
def validate_application_package(job_id: str):
    """Run truth-safety validation checks on package."""
    package = service.get_application_package(job_id)
    if not package:
        raise HTTPException(status_code=404, detail=f"Application package for '{job_id}' not found.")
    is_valid, errors, status = service.validator.validate(package)
    return {
        "job_id": job_id,
        "is_valid": is_valid,
        "status": status.value,
        "errors": errors,
        "cover_letter_valid": package.cover_letter.validation.is_valid,
    }

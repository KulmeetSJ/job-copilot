"""Application preparation domain models, enums, question and answer schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from job_copilot.matching.models import JobAssessment


class QuestionClassification(str, Enum):
    """Deterministic classification of application questions."""
    ANSWERABLE_FROM_EVIDENCE = "ANSWERABLE_FROM_EVIDENCE"  # Factual evidence directly supports answer
    ANSWER_REQUIRES_USER_INPUT = "ANSWER_REQUIRES_USER_INPUT"  # Sensitive/legal/financial or unevidenced
    DO_NOT_ANSWER = "DO_NOT_ANSWER"  # Unsupported experience or request to fabricate facts


class QuestionType(str, Enum):
    """Data type of the application field/question."""
    FREE_TEXT = "FREE_TEXT"
    YES_NO = "YES_NO"
    SINGLE_SELECT = "SINGLE_SELECT"
    MULTI_SELECT = "MULTI_SELECT"
    NUMERIC = "NUMERIC"
    DATE = "DATE"
    SALARY = "SALARY"
    WORK_AUTHORIZATION = "WORK_AUTHORIZATION"
    SPONSORSHIP = "SPONSORSHIP"
    EXPERIENCE_DURATION = "EXPERIENCE_DURATION"


class ApplicationQuestion(BaseModel):
    """Model for an individual job application question."""
    id: str = Field(description="Unique question identifier e.g. q-java-exp or form field ID")
    question_text: str = Field(description="Raw text of the application question")
    field_name: Optional[str] = Field(default=None, description="HTML form field name or key")
    question_type: QuestionType = Field(default=QuestionType.FREE_TEXT)
    classification: Optional[QuestionClassification] = Field(default=None)
    required: bool = Field(default=True, description="Whether question is marked mandatory")
    options: List[str] = Field(default_factory=list, description="Selection options if dropdown/radio")
    source: str = Field(default="manual_input", description="manual_input, browser_extracted, default_pack")


class ClaimProvenance(BaseModel):
    """Provenance tracking for a factual claim in an answer or cover letter."""
    claim_text: str = Field(description="The factual sentence or claim asserted")
    source_type: str = Field(description="PROFESSIONAL, PERSONAL_PROJECT, TRAINING_EXPOSURE, ACADEMIC")
    source_ref: str = Field(description="Evidence ID e.g. EXP-HSBC-BEAM-001, PRJ-RL-001, SKL-GKE-001")
    context: Optional[str] = Field(default=None, description="Canonical context snippet from master profile")
    metric_type: Optional[str] = Field(default=None, description="PRODUCTION, BENCHMARK, PROJECT, UNMETRIC")


class ApplicationAnswer(BaseModel):
    """Evidence-backed generated answer for an application question."""
    question_id: str
    question_text: str
    answer: Optional[str] = Field(default=None, description="Generated answer text or null if requires input")
    classification: QuestionClassification
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    provenance: List[ClaimProvenance] = Field(default_factory=list, description="Evidence references")
    requires_user_input: bool = Field(default=False)
    rationale: str = Field(description="Explainability string for why this answer was formed or deferred")


class UserInputRequest(BaseModel):
    """Structured request for unresolved questions needing human decision."""
    question_id: str
    question_text: str
    field_name: Optional[str] = None
    reason: str = Field(description="Why automated answering is disallowed (e.g. visa, salary, unverified)")
    expected_type: QuestionType
    required: bool = True
    options: List[str] = Field(default_factory=list)


class CoverLetterValidation(BaseModel):
    """Validation outcome for generated cover letter."""
    is_valid: bool = True
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    claims_checked: int = 0
    provenance: List[ClaimProvenance] = Field(default_factory=list)


class CoverLetter(BaseModel):
    """Tailored cover letter document and metadata."""
    job_id: str
    company: str
    title: str
    letter_text: str
    word_count: int
    provenance: List[ClaimProvenance] = Field(default_factory=list)
    validation: CoverLetterValidation = Field(default_factory=CoverLetterValidation)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ApplicationPackageStatus(str, Enum):
    """Status of application package preparation."""
    PREPARING = "PREPARING"
    USER_INPUT_REQUIRED = "USER_INPUT_REQUIRED"
    READY_FOR_REVIEW = "READY_FOR_REVIEW"
    BLOCKED = "BLOCKED"


class ApplicationPackage(BaseModel):
    """Complete structured application preparation bundle for a target job."""
    job_id: str
    job_title: str
    company: str
    
    # Phase 4 Assessment
    assessment: JobAssessment
    
    # Phase 3 Tailored Resume
    selected_resume_strategy: str
    resume_pdf_path: str
    resume_tex_path: str
    
    # Cover Letter
    cover_letter: CoverLetter
    
    # Application Q&A
    questions: List[ApplicationQuestion] = Field(default_factory=list)
    answers: List[ApplicationAnswer] = Field(default_factory=list)
    user_inputs_required: List[UserInputRequest] = Field(default_factory=list)
    
    # Status & Validation
    status: ApplicationPackageStatus = Field(default=ApplicationPackageStatus.PREPARING)
    validation_errors: List[str] = Field(default_factory=list)
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

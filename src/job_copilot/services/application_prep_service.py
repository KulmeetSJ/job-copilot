"""Application Preparation Orchestrator and Package Persistence Service."""

import json
from pathlib import Path
from typing import Any, List, Optional
import yaml

from job_copilot.application.classifier import QuestionClassifier
from job_copilot.application.cover_letter import CoverLetterEngine
from job_copilot.application.models import (
    ApplicationAnswer,
    ApplicationPackage,
    ApplicationPackageStatus,
    ApplicationQuestion,
    CoverLetter,
    QuestionType,
    UserInputRequest,
)
from job_copilot.application.qa_engine import ApplicationQAEngine
from job_copilot.application.validator import ApplicationPackageValidator
from job_copilot.matching.models import JobAssessment
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.services.discovery_service import DiscoveryService
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.resume_service import ResumeService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Standard application questions included by default if none supplied
DEFAULT_APPLICATION_QUESTIONS = [
    ApplicationQuestion(
        id="q-interest",
        question_text="Why are you interested in this role?",
        question_type=QuestionType.FREE_TEXT,
    ),
    ApplicationQuestion(
        id="q-tech-experience",
        question_text="Describe your core technical experience and backend capabilities.",
        question_type=QuestionType.FREE_TEXT,
    ),
    ApplicationQuestion(
        id="q-sponsorship",
        question_text="Will you now or in the future require visa sponsorship?",
        question_type=QuestionType.SPONSORSHIP,
    ),
    ApplicationQuestion(
        id="q-salary",
        question_text="What are your salary expectations for this position?",
        question_type=QuestionType.SALARY,
    ),
]


class ApplicationPrepService:
    """
    High-level service for Phase 6 Application Preparation.
    Coordinates resume tailoring, cover letter composition, factual question answering,
    sensitive input detection, and persistent application bundling.
    """

    def __init__(
        self,
        master_profile_path: Optional[Path] = None,
        applications_data_dir: Optional[Path] = None,
        jobs_data_dir: Optional[Path] = None,
        intelligence_service: Optional[JobIntelligenceService] = None,
        resume_service: Optional[ResumeService] = None,
        artifact_service: Optional[Any] = None,
    ):
        self.master_profile_path = master_profile_path or Path("data/candidate/master_profile.yaml")
        self.applications_data_dir = applications_data_dir or Path("data/applications")
        self.jobs_data_dir = jobs_data_dir or Path("data/jobs")
        self.artifact_service = artifact_service

        self.intelligence_service = intelligence_service or JobIntelligenceService(
            master_profile_path=self.master_profile_path,
            jobs_data_dir=self.jobs_data_dir,
        )
        self.discovery_service = DiscoveryService(
            jobs_data_dir=self.jobs_data_dir,
            job_intelligence_service=self.intelligence_service,
        )
        self.resume_service = resume_service or ResumeService(master_profile_path=self.master_profile_path)

        self.classifier = QuestionClassifier()
        self.qa_engine = ApplicationQAEngine(classifier=self.classifier)
        self.cover_letter_engine = CoverLetterEngine()
        self.validator = ApplicationPackageValidator()

        self._profile_cache: Optional[CandidateProfile] = None

        # Ensure directory exists
        self.applications_data_dir.mkdir(parents=True, exist_ok=True)

    def load_master_profile(self) -> CandidateProfile:
        """Load and cache canonical master profile."""
        if self._profile_cache:
            return self._profile_cache

        if not self.master_profile_path.exists():
            raise FileNotFoundError(f"Master profile not found at {self.master_profile_path}")

        with open(self.master_profile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._profile_cache = CandidateProfile.model_validate(data)
        return self._profile_cache

    def prepare_application(
        self,
        job_id_or_text: str,
        custom_questions: Optional[List[ApplicationQuestion]] = None,
        strategy_override: Optional[str] = None,
        db_session: Optional[Any] = None,
    ) -> ApplicationPackage:
        """
        Build the complete application package for a target job.
        """
        profile = self.load_master_profile()

        # 1. Resolve Job & Phase 4 Assessment
        canonical = self.discovery_service.store.get_canonical_job(job_id_or_text)
        if canonical:
            assessment = self.intelligence_service.evaluate_job(
                raw_text=canonical.clean_description,
                company_override=canonical.company,
                title_override=canonical.title,
                save_artifacts=True,
            )
        else:
            # Check database for existing Job record
            db_job = None
            try:
                from job_copilot.repositories.job_repository import JobRepository
                from job_copilot.repositories.application_repository import ApplicationRepository
                if db_session is not None:
                    job_repo = JobRepository(db_session)
                    app_repo = ApplicationRepository(db_session)
                    db_job = job_repo.get_by_job_id(job_id_or_text)
                    if not db_job:
                        app = app_repo.get_by_application_id(job_id_or_text) or app_repo.get_by_job_id_str(job_id_or_text)
                        if app and app.job_id:
                            db_job = job_repo.get_by_id(app.job_id)
                else:
                    from job_copilot.db.database import get_db
                    db_gen = get_db()
                    db = next(db_gen)
                    try:
                        job_repo = JobRepository(db)
                        app_repo = ApplicationRepository(db)
                        db_job = job_repo.get_by_job_id(job_id_or_text)
                        if not db_job:
                            app = app_repo.get_by_application_id(job_id_or_text) or app_repo.get_by_job_id_str(job_id_or_text)
                            if app and app.job_id:
                                db_job = job_repo.get_by_id(app.job_id)
                    finally:
                        db.close()
            except Exception:
                db_job = None

            if db_job:
                assessment = self.intelligence_service.evaluate_job(
                    raw_text=db_job.description,
                    company_override=db_job.company,
                    title_override=db_job.title,
                    save_artifacts=True,
                )
            else:
                # Disallow evaluating identifiers as raw JD text to prevent fake "Target Company" generation
                text_clean = job_id_or_text.strip()
                is_likely_id = (
                    "\n" not in text_clean
                    and len(text_clean) < 120
                    and not any(kw in text_clean.lower() for kw in ["looking for", "requirements", "responsibilities", "qualifications", "experience", "we are", "role:"])
                )
                if is_likely_id:
                    raise ValueError(f"Job or Application record '{job_id_or_text}' not found.")

                assessment = self.intelligence_service.evaluate_job(
                    raw_text=job_id_or_text,
                    save_artifacts=True,
                )

        job_id = assessment.job.job_id
        strategy = strategy_override or assessment.recommended_strategy

        # 2. Phase 3 Tailored Resume Generation
        resume_res = self.resume_service.generate_tailored_resume(
            strategy_name=strategy,
            job_description_text=assessment.job.description,
        )

        # 3. Generate Tailored & Validated Cover Letter
        cover_letter = self.cover_letter_engine.generate_cover_letter(assessment, profile)

        # 4. Ingest and Answer Application Questions
        questions = custom_questions if custom_questions is not None else DEFAULT_APPLICATION_QUESTIONS
        answers: List[ApplicationAnswer] = []
        user_input_requests: List[UserInputRequest] = []

        for q in questions:
            ans = self.qa_engine.answer_question(q, profile, assessment)
            answers.append(ans)
            req = self.qa_engine.extract_user_input_request(q, ans)
            if req:
                user_input_requests.append(req)

        # 5. Assemble Package
        package = ApplicationPackage(
            job_id=job_id,
            job_title=assessment.job.title,
            company=assessment.job.company,
            assessment=assessment,
            selected_resume_strategy=strategy,
            resume_pdf_path=str(resume_res.pdf_path),
            resume_tex_path=str(resume_res.tex_path),
            cover_letter=cover_letter,
            questions=questions,
            answers=answers,
            user_inputs_required=user_input_requests,
            status=ApplicationPackageStatus.PREPARING,
        )

        # 6. Validate Package
        is_valid, errors, status = self.validator.validate(package)
        package.validation_errors = errors
        package.status = status

        # 7. Persist Package Artifacts
        self._persist_application_package(package)

        return package

    def get_application_package(self, job_id: str) -> Optional[ApplicationPackage]:
        """Load persistent application package by job ID."""
        pkg_file = self.applications_data_dir / job_id / "package.json"
        if not pkg_file.exists():
            return None
        try:
            return ApplicationPackage.model_validate_json(pkg_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Failed loading application package for '{job_id}': {e}")
            return None

    def answer_single_question(
        self,
        job_id: str,
        question_text: str,
        question_type: QuestionType = QuestionType.FREE_TEXT,
    ) -> ApplicationAnswer:
        """Answer a single ad-hoc question for a target job."""
        profile = self.load_master_profile()
        package = self.get_application_package(job_id)
        assessment = package.assessment if package else None

        question = ApplicationQuestion(
            id=f"q-{abs(hash(question_text)) % 10000}",
            question_text=question_text,
            question_type=question_type,
        )
        return self.qa_engine.answer_question(question, profile, assessment)

    def _persist_application_package(self, package: ApplicationPackage) -> None:
        """Save application package and related artifacts to disk."""
        job_dir = self.applications_data_dir / package.job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        # 1. package.json
        (job_dir / "package.json").write_text(package.model_dump_json(indent=2), encoding="utf-8")

        # 2. cover_letter.md and cover_letter.json
        (job_dir / "cover_letter.md").write_text(package.cover_letter.letter_text, encoding="utf-8")
        (job_dir / "cover_letter.json").write_text(package.cover_letter.model_dump_json(indent=2), encoding="utf-8")

        # 3. questions.json
        questions_payload = {
            "questions": [q.model_dump() for q in package.questions],
            "answers": [a.model_dump() for a in package.answers],
            "user_inputs_required": [u.model_dump() for u in package.user_inputs_required],
        }
        (job_dir / "questions.json").write_text(json.dumps(questions_payload, indent=2), encoding="utf-8")

        # 4. validation.json
        validation_payload = {
            "is_valid": len(package.validation_errors) == 0,
            "status": package.status.value,
            "errors": package.validation_errors,
            "cover_letter_validation": package.cover_letter.validation.model_dump(),
        }
        (job_dir / "validation.json").write_text(json.dumps(validation_payload, indent=2), encoding="utf-8")

        # 5. Phase 10A Object Storage Integration
        if self.artifact_service:
            try:
                from job_copilot.domain.artifact_enums import ArtifactType
                # Store package.json
                self.artifact_service.store_artifact(
                    data=package.model_dump_json(indent=2).encode("utf-8"),
                    artifact_type=ArtifactType.APPLICATION_PACKAGE,
                    job_id=package.job_id,
                    original_filename="package.json",
                    content_type="application/json",
                )
                # Store cover_letter.md
                self.artifact_service.store_artifact(
                    data=package.cover_letter.letter_text.encode("utf-8"),
                    artifact_type=ArtifactType.COVER_LETTER,
                    job_id=package.job_id,
                    original_filename="cover_letter.md",
                    content_type="text/markdown",
                )
                # Store validation.json
                self.artifact_service.store_artifact(
                    data=json.dumps(validation_payload, indent=2).encode("utf-8"),
                    artifact_type=ArtifactType.VALIDATION_REPORT,
                    job_id=package.job_id,
                    original_filename="validation.json",
                    content_type="application/json",
                )
            except Exception as ae:
                logger.debug(f"ArtifactService storage notice: {ae}")

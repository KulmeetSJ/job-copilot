"""Application Package Validator for truth safety and preparation completeness."""

from pathlib import Path
from typing import List, Tuple
from job_copilot.application.models import (
    ApplicationPackage,
    ApplicationPackageStatus,
    QuestionClassification,
)
from job_copilot.matching.models import JobRecommendation
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ApplicationPackageValidator:
    """
    Validates that an application preparation package satisfies all truth invariants,
    contains required artifacts, and accurately reflects unresolved questions.
    """

    def validate(self, package: ApplicationPackage) -> Tuple[bool, List[str], ApplicationPackageStatus]:
        """
        Validate package completeness and truth-safety.
        Returns (is_valid, error_list, suggested_status).
        """
        errors: List[str] = []

        # 1. Verify Job Assessment & Recommendation
        if package.assessment.recommendation == JobRecommendation.SKIP:
            errors.append("Job is classified as SKIP by Phase 4 Job Intelligence (unrelated role or citizenship block).")

        # 2. Verify Resume Artifacts
        pdf_path = Path(package.resume_pdf_path)
        if not pdf_path.exists():
            errors.append(f"Tailored resume PDF not found at {package.resume_pdf_path}.")

        # 3. Verify Cover Letter
        if not package.cover_letter.validation.is_valid:
            errors.extend([f"Cover letter error: {e}" for e in package.cover_letter.validation.errors])

        # 4. Check for unresolved questions vs UserInputRequests
        unresolved_count = sum(
            1 for a in package.answers
            if a.classification == QuestionClassification.ANSWER_REQUIRES_USER_INPUT
        )

        if len(package.user_inputs_required) != unresolved_count:
            errors.append("Mismatch between user-input answers and extracted UserInputRequest models.")

        # 5. Determine package status
        if errors and package.assessment.recommendation == JobRecommendation.SKIP:
            status = ApplicationPackageStatus.BLOCKED
        elif package.user_inputs_required:
            status = ApplicationPackageStatus.USER_INPUT_REQUIRED
        elif errors:
            status = ApplicationPackageStatus.PREPARING
        else:
            status = ApplicationPackageStatus.READY_FOR_REVIEW

        is_valid = len(errors) == 0
        return is_valid, errors, status

"""Resume Validation Service with Strict Truth Safety Invariants."""

from pathlib import Path
from typing import Dict, List, Optional
from job_copilot.resume.models import (
    JobAnalysis,
    ResumeValidationResult,
    TailoredResume,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# List of technologies explicitly flagged as unconfirmed / NEEDS_REVIEW in candidate profile
UNCONFIRMED_TECHNOLOGIES = {"aws", "apache kafka", "kafka"}


class ResumeValidator:
    """
    Validates generated resumes for structural integrity, truth safety, and JD coverage.
    """

    def validate(
        self,
        resume: TailoredResume,
        profile: CandidateProfile,
        pdf_path: Optional[Path] = None,
        latex_error: Optional[str] = None,
        page_count: Optional[int] = None,
        analysis: Optional[JobAnalysis] = None,
    ) -> ResumeValidationResult:
        """Execute full validation suite on the tailored resume."""
        content_errors: List[str] = []
        truth_violations: List[str] = []
        warnings: List[str] = []
        latex_errors: List[str] = [latex_error] if latex_error else []

        # 1. Structural Checks
        if not resume.personal_info or not resume.personal_info.full_name:
            content_errors.append("Missing personal information or candidate name.")

        if not resume.experience:
            content_errors.append("Resume experience section is empty.")

        if not resume.skill_groups:
            content_errors.append("Resume skill groups section is empty.")

        if not resume.education:
            content_errors.append("Resume education section is empty.")

        if page_count and page_count > 2:
            warnings.append(f"Resume page count ({page_count}) exceeds recommended 1-2 pages.")

        # 2. Content & Truth Safety Invariants

        # 2a. Canonical Employment Title & Company
        for exp in resume.experience:
            matching_emp = next((e for e in profile.employment if e.company.lower() == exp.company.lower()), None)
            if matching_emp:
                expected_canonical_role = matching_emp.canonical_role or matching_emp.role
                if exp.canonical_role != expected_canonical_role:
                    truth_violations.append(
                        f"Invalid canonical role '{exp.canonical_role}'. Must be strictly '{expected_canonical_role}'."
                    )
                if matching_emp.start_date and exp.start_date != matching_emp.start_date:
                    truth_violations.append(
                        f"Employment start date '{exp.start_date}' contradicts canonical profile '{matching_emp.start_date}'."
                    )
            elif profile.employment:
                allowed_companies = ", ".join(f"'{e.company}'" for e in profile.employment)
                truth_violations.append(
                    f"Invalid company '{exp.company}'. Must match canonical profile (allowed: {allowed_companies})."
                )

        # 2b. Check that all experience bullets have evidence IDs
        for exp in resume.experience:
            for b in exp.bullets:
                if not b.evidence_ids:
                    truth_violations.append(
                        f"Experience bullet lacks provenance evidence IDs: '{b.text[:50]}...'"
                    )
                if b.claim_type != "PROFESSIONAL":
                    truth_violations.append(
                        f"Experience bullet has non-professional claim type '{b.claim_type}'"
                    )

        # 2c. Check projects
        for prj in resume.projects:
            if prj.deployment_status not in ("PORTFOLIO_DEMO", "BENCHMARK"):
                truth_violations.append(
                    f"Project '{prj.name}' has invalid deployment status '{prj.deployment_status}'."
                )
            for b in prj.bullets:
                if not b.evidence_ids:
                    truth_violations.append(
                        f"Project '{prj.name}' bullet lacks provenance evidence IDs: '{b.text[:50]}...'"
                    )
                # Ensure 100K+ RPS rate limiter is marked as benchmark, not production
                if "100k+" in b.text.lower() and "benchmark" not in b.text.lower() and b.metric_type != "BENCHMARK":
                    truth_violations.append(
                        f"Project '{prj.name}' claims benchmark metric (100K+ RPS) without benchmark qualification."
                    )

        # 2d. Check skills - ensure no unconfirmed technology is presented as confirmed
        for grp in resume.skill_groups:
            for skill_name in grp.skills:
                if skill_name.lower() in UNCONFIRMED_TECHNOLOGIES:
                    truth_violations.append(
                        f"Unconfirmed technology '{skill_name}' (NEEDS_REVIEW) presented in skills section."
                    )

        # 2e. Check Education
        if resume.education and profile.education:
            canonical_edu = profile.education[0]
            edu = resume.education[0]
            if edu.institution != canonical_edu.institution:
                truth_violations.append(
                    f"Education institution '{edu.institution}' contradicts canonical profile '{canonical_edu.institution}'."
                )

        # 3. JD Matching Coverage
        matched_skills: List[str] = []
        unmatched_skills: List[str] = []
        coverage_pct = 100.0

        if analysis:
            all_resume_skills = set()
            for grp in resume.skill_groups:
                for s in grp.skills:
                    all_resume_skills.add(s.lower())
            for exp in resume.experience:
                for t in exp.technologies:
                    all_resume_skills.add(t.lower())
            for prj in resume.projects:
                for t in prj.technologies:
                    all_resume_skills.add(t.lower())

            all_jd_reqs = analysis.required_skills + analysis.preferred_skills
            for req in all_jd_reqs:
                norm_req = req.normalized_name.lower()
                if norm_req in all_resume_skills or any(norm_req in rs for rs in all_resume_skills):
                    matched_skills.append(req.normalized_name)
                else:
                    unmatched_skills.append(req.normalized_name)

            total_reqs = len(all_jd_reqs)
            if total_reqs > 0:
                coverage_pct = round((len(matched_skills) / total_reqs) * 100.0, 1)

        is_valid = (
            len(truth_violations) == 0
            and len(content_errors) == 0
            and len(latex_errors) == 0
            and (pdf_path is not None and pdf_path.exists())
        )

        return ResumeValidationResult(
            is_valid=is_valid,
            pdf_generated=pdf_path.exists() if pdf_path else False,
            page_count=page_count,
            latex_errors=latex_errors,
            content_errors=content_errors,
            truth_violations=truth_violations,
            matched_skills=matched_skills,
            unmatched_skills=unmatched_skills,
            keyword_coverage_pct=coverage_pct,
            warnings=warnings,
        )

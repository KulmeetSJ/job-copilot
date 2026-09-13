"""LLM Resume Writer Orchestrator with Deterministic Validation and Fallback."""

from typing import List, Optional

from job_copilot.resume.llm.models import LLMResumeDraft
from job_copilot.resume.llm.prompts import RESUME_SYSTEM_PROMPT, build_grounded_resume_prompt
from job_copilot.resume.llm.provider import LLMResumeProvider, get_resume_llm_provider
from job_copilot.resume.llm.validator import GroundingValidator
from job_copilot.resume.models import (
    JobAnalysis,
    JobMatchResult,
    ResumeBullet,
    ResumeExperience,
    ResumeProject,
    ResumeSkillGroup,
    TailoredResume,
)
from job_copilot.resume.strategy import ResumeStrategyConfig
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class LLMResumeWriter:
    """
    Orchestrates prompt building, LLM generation, strict truth validation,
    single retry with error feedback, and deterministic conversion to TailoredResume.
    """

    def __init__(
        self,
        provider: Optional[LLMResumeProvider] = None,
        validator: Optional[GroundingValidator] = None,
    ):
        self.provider = provider or get_resume_llm_provider()
        self.validator = validator or GroundingValidator()

    def is_available(self) -> bool:
        """Check if the underlying LLM provider is available."""
        return self.provider is not None and self.provider.is_available()

    def generate_tailored_resume(
        self,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis] = None,
        match_result: Optional[JobMatchResult] = None,
    ) -> Optional[TailoredResume]:
        """
        Generate a fully tailored resume draft using the LLM.
        Validates the output against candidate truth.
        Returns TailoredResume on success, or None to signal fallback to deterministic selector.
        """
        if not self.is_available():
            logger.debug("LLMResumeWriter: Provider is unavailable. Deferring to deterministic generator.")
            return None

        # 1. Build Grounded Prompt
        user_prompt = build_grounded_resume_prompt(
            profile=profile,
            analysis=analysis,
            strategy_name=strategy.name,
        )

        # 2. Initial Generation
        draft: Optional[LLMResumeDraft] = self.provider.generate_resume_draft(
            system_prompt=RESUME_SYSTEM_PROMPT,
            user_prompt=user_prompt,
        )

        if not draft:
            logger.warning("LLMResumeWriter: Initial generation failed. Returning None for fallback.")
            return None

        # 3. Grounding Validation
        is_valid, errors = self.validator.validate(draft, profile)

        # 4. Retry Step if Validation Failed
        if not is_valid:
            logger.info(f"LLMResumeWriter: Initial draft failed validation with {len(errors)} errors. Attempting retry.")
            retry_error_msg = "\n".join(f"- {e}" for e in errors)

            draft = self.provider.generate_resume_draft(
                system_prompt=RESUME_SYSTEM_PROMPT,
                user_prompt=user_prompt,
                retry_error=retry_error_msg,
            )

            if not draft:
                logger.warning("LLMResumeWriter: Retry generation returned empty. Falling back to deterministic.")
                return None

            is_valid, errors = self.validator.validate(draft, profile)
            if not is_valid:
                logger.warning(f"LLMResumeWriter: Draft failed validation after retry ({len(errors)} errors): {errors}. Falling back to deterministic generator.")
                return None

        # 5. Convert Valid Draft to TailoredResume
        try:
            return self._build_tailored_resume(draft, profile, strategy, analysis, match_result)
        except Exception as conv_err:
            logger.error(f"LLMResumeWriter: Error converting draft to TailoredResume: {conv_err}")
            return None

    def _build_tailored_resume(
        self,
        draft: LLMResumeDraft,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis],
        match_result: Optional[JobMatchResult],
    ) -> TailoredResume:
        """Construct the canonical TailoredResume model from the validated LLM draft."""

        # 1. Convert Experience Bullets
        exp_bullets: List[ResumeBullet] = []
        for b in draft.experience_bullets:
            exp_bullets.append(
                ResumeBullet(
                    text=b.text.strip(),
                    evidence_ids=b.evidence_ids,
                    claim_type="PROFESSIONAL",
                    metric_type="PRODUCTION",
                    relevance_score=1.0,
                )
            )

        canonical_emp = profile.employment[0] if profile.employment else None
        experience = [
            ResumeExperience(
                company=canonical_emp.company if canonical_emp else "HSBC",
                role=canonical_emp.role if canonical_emp else "Software Engineer",
                canonical_role=canonical_emp.canonical_role or "Software Engineer",
                team=canonical_emp.team if canonical_emp else "Payments Data Platform",
                location=canonical_emp.location if canonical_emp else "Pune, India",
                start_date=canonical_emp.start_date if canonical_emp else "2024-07",
                end_date=canonical_emp.end_date if canonical_emp else "Present",
                current=canonical_emp.current if canonical_emp else True,
                bullets=exp_bullets,
                technologies=canonical_emp.technologies if canonical_emp else [],
                evidence_ids=canonical_emp.evidence_ids if canonical_emp else ["EXP-HSBC-001"],
            )
        ]

        # 2. Convert Projects
        projects: List[ResumeProject] = []
        canonical_projects_by_name = {p.name.lower(): p for p in profile.projects}

        for prj_item in draft.projects:
            canon_p = canonical_projects_by_name.get(prj_item.name.lower())
            
            p_bullets: List[ResumeBullet] = []
            for pb in prj_item.bullets:
                p_bullets.append(
                    ResumeBullet(
                        text=pb.text.strip(),
                        evidence_ids=pb.evidence_ids or prj_item.evidence_ids,
                        claim_type="BENCHMARK" if ("rate limiter" in prj_item.name.lower()) else "PERSONAL_PROJECT",
                        metric_type="BENCHMARK" if ("rate limiter" in prj_item.name.lower()) else "PROJECT",
                        relevance_score=1.0,
                    )
                )

            # Fallback bullet if LLM omitted bullets for a project
            if not p_bullets and canon_p:
                desc = canon_p.description
                p_bullets.append(
                    ResumeBullet(
                        text=desc,
                        evidence_ids=canon_p.evidence_ids,
                        claim_type=canon_p.claim_type,
                        metric_type="BENCHMARK" if ("rate limiter" in prj_item.name.lower()) else "PROJECT",
                    )
                )

            projects.append(
                ResumeProject(
                    name=canon_p.name if canon_p else prj_item.name,
                    description=canon_p.description if canon_p else "",
                    architecture=canon_p.architecture if canon_p else None,
                    deployment_status=canon_p.deployment_status if canon_p else "PORTFOLIO_DEMO",
                    bullets=p_bullets,
                    technologies=prj_item.technologies or (canon_p.technologies if canon_p else []),
                    links=canon_p.links if canon_p else [],
                    evidence_ids=prj_item.evidence_ids or (canon_p.evidence_ids if canon_p else []),
                )
            )

        # 3. Convert Skill Groups
        skill_groups: List[ResumeSkillGroup] = []
        for grp in draft.skill_groups:
            if grp.skills:
                skill_groups.append(
                    ResumeSkillGroup(
                        category=grp.category,
                        skills=grp.skills,
                        evidence_ids=[],
                    )
                )

        return TailoredResume(
            strategy_name=strategy.name,
            display_title=strategy.display_title,
            personal_info=profile.personal_info,
            summary=draft.summary.strip(),
            skill_groups=skill_groups,
            experience=experience,
            projects=projects,
            education=profile.education,
            certifications=profile.certifications,
            awards=profile.awards,
            section_order=strategy.section_order,
            target_job_title=analysis.job_title if analysis else None,
            target_company=analysis.company if analysis else None,
            metadata={
                "llm_tailored": True,
                "strategy": strategy.name,
                "tailoring_rationale": draft.tailoring_rationale,
                "overall_score": match_result.overall_score if match_result else None,
            },
        )

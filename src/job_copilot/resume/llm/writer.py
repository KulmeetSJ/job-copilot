"""LLM Resume Writer Orchestrator with Deterministic Validation and Fallback."""


from datetime import datetime, timezone
from job_copilot.resume.llm.models import LLMResumeDraft
from job_copilot.resume.llm.prompts import (
    build_grounded_resume_prompt,
    build_resume_system_prompt,
)
from job_copilot.resume.llm.provider import LLMResumeProvider, get_resume_llm_provider
from job_copilot.resume.llm.validator import (
    GroundingValidator,
    resolve_canonical_project,
)
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


def categorize_validation_error(err: str) -> str:
    """Classify a validation error into a structured diagnostic failure category."""
    err_l = err.lower()
    if any(k in err_l for k in ["metric", "%", "$", "unverified metric", "exceeds verified"]):
        return "METRIC_GROUNDING_VIOLATION"
    if any(k in err_l for k in ["unconfirmed technology", "unsupported technology"]):
        return "UNCONFIRMED_TECHNOLOGY"
    if any(k in err_l for k in ["project evidence id", "not an authorized employment", "lacks evidence id", "fake evidence"]):
        return "EVIDENCE_PROVENANCE_VIOLATION"
    if any(k in err_l for k in ["benchmark", "production employment", "rate limiter"]):
        return "BENCHMARK_PRODUCTION_BOUNDARY"
    if any(k in err_l for k in ["summary", "bullets", "projects", "skill groups", "too many", "insufficient", "missing a name"]):
        return "STRUCTURAL_FORMAT_VIOLATION"
    if any(k in err_l for k in ["architected", "leadership", "management", "ownership"]):
        return "UNSUPPORTED_ROLE_OR_LEADERSHIP_CLAIM"
    if any(k in err_l for k in ["certification", "unconfirmed certification"]):
        return "UNCONFIRMED_CERTIFICATION"
    return "SEMANTIC_GROUNDING_VIOLATION"


def log_validation_diagnostic(
    stage: str,
    errors: list[str],
    job_id: str | None = None,
    provider: LLMResumeProvider | None = None,
) -> None:
    """
    Emit privacy-safe, structured diagnostic telemetry for LLM draft validation failures.
    Strictly omits candidate PII, raw resumes, secrets, tokens, or profile dumps.
    """
    categories = sorted(list(set(categorize_validation_error(e) for e in errors))) if errors else ["UNKNOWN"]
    provider_name = provider.__class__.__name__ if provider else "UnknownProvider"
    model_name = getattr(provider, "model", None) or "unknown_model"
    now_ts = datetime.now(timezone.utc).isoformat()
    job_identifier = job_id or "unspecified_job"

    logger.warning(
        f"[RESUME_VALIDATION_DIAGNOSTIC] stage={stage} job_id={job_identifier} "
        f"provider={provider_name} model={model_name} "
        f"categories={','.join(categories)} error_count={len(errors)} timestamp={now_ts}"
    )


class LLMResumeWriter:
    """
    Orchestrates prompt building, LLM generation, strict truth validation,
    single retry with error feedback, and deterministic conversion to TailoredResume.
    """

    def __init__(
        self,
        provider: LLMResumeProvider | None = None,
        validator: GroundingValidator | None = None,
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
        analysis: JobAnalysis | None = None,
        match_result: JobMatchResult | None = None,
        job_id: str | None = None,
    ) -> TailoredResume | None:
        """
        Generate a fully tailored resume draft using the LLM.
        Validates the output against candidate truth.
        Returns TailoredResume on success, or None to signal fallback to deterministic selector.
        """
        effective_job_id = job_id or (analysis.job_title if analysis else None) or "unspecified_job"

        if not self.is_available():
            logger.debug("LLMResumeWriter: Provider is unavailable. Deferring to deterministic generator.")
            return None

        # 1. Build Grounded Prompts
        system_prompt = build_resume_system_prompt(
            profile=profile,
            evidence_facts=self.validator._evidence_facts if self.validator else None,
        )

        user_prompt = build_grounded_resume_prompt(
            profile=profile,
            analysis=analysis,
            strategy_name=strategy.name,
        )

        # 2. Initial Generation
        draft: LLMResumeDraft | None = self.provider.generate_resume_draft(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
        )

        if not draft:
            logger.warning(f"LLMResumeWriter: Initial generation failed for {effective_job_id}. Returning None for fallback.")
            log_validation_diagnostic("fallback", ["Initial generation returned empty response"], job_id=effective_job_id, provider=self.provider)
            return None

        # 3. Grounding Validation
        is_valid, errors = self.validator.validate(draft, profile)

        # 4. Retry Step if Validation Failed
        if not is_valid:
            log_validation_diagnostic("retry", errors, job_id=effective_job_id, provider=self.provider)
            logger.info(f"LLMResumeWriter: Initial draft failed validation with {len(errors)} errors. Attempting retry.")
            retry_error_msg = "\n".join(f"- {e}" for e in errors)

            draft = self.provider.generate_resume_draft(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                retry_error=retry_error_msg,
            )

            if not draft:
                logger.warning(f"LLMResumeWriter: Retry generation returned empty for {effective_job_id}. Falling back to deterministic.")
                log_validation_diagnostic("fallback", ["Retry generation returned empty response"], job_id=effective_job_id, provider=self.provider)
                return None

            is_valid, errors = self.validator.validate(draft, profile)
            if not is_valid:
                log_validation_diagnostic("fallback", errors, job_id=effective_job_id, provider=self.provider)
                logger.warning(f"LLMResumeWriter: Draft failed validation after retry ({len(errors)} errors): {errors}. Falling back to deterministic generator.")
                return None

        # 5. Convert Valid Draft to TailoredResume
        try:
            return self._build_tailored_resume(draft, profile, strategy, analysis, match_result)
        except (ValueError, TypeError, KeyError, AttributeError) as conv_err:
            logger.error(f"LLMResumeWriter: Error converting draft to TailoredResume: {conv_err}")
            return None

    def _build_tailored_resume(
        self,
        draft: LLMResumeDraft,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: JobAnalysis | None = None,
        match_result: JobMatchResult | None = None,
    ) -> TailoredResume:
        """Construct the canonical TailoredResume model from the validated LLM draft."""

        # 1. Convert Experience Bullets
        exp_bullets: list[ResumeBullet] = []
        for b in draft.experience_bullets:
            b_claim_type = "PROFESSIONAL"
            b_metric_type = "PRODUCTION"

            # Derive claim_type dynamically from canonical employment achievements
            for emp in profile.employment:
                for ach in emp.achievements:
                    if any(eid in ach.evidence_ids for eid in b.evidence_ids):
                        if ach.claim_type:
                            b_claim_type = ach.claim_type
                        break

            # Cross-reference evidence facts if available
            if self.validator and self.validator._evidence_facts:
                for eid in b.evidence_ids:
                    if eid in self.validator._evidence_facts:
                        fact = self.validator._evidence_facts[eid]
                        if fact.get("claim_type"):
                            b_claim_type = fact.get("claim_type")
                        break

            # Distinguish production vs benchmark / project / estimate / academic / positioning
            if b_claim_type == "BENCHMARK":
                b_metric_type = "BENCHMARK"
            elif b_claim_type == "PERSONAL_PROJECT":
                b_metric_type = "PROJECT"
            elif b_claim_type == "PROFESSIONAL":
                b_metric_type = "PRODUCTION"
            elif b_claim_type == "ESTIMATE":
                b_metric_type = "ESTIMATE"
            elif b_claim_type == "ACADEMIC":
                b_metric_type = "ACADEMIC"
            elif b_claim_type == "POSITIONING":
                b_metric_type = "POSITIONING"

            exp_bullets.append(
                ResumeBullet(
                    text=b.text.strip(),
                    evidence_ids=b.evidence_ids,
                    claim_type=b_claim_type,
                    metric_type=b_metric_type,
                    relevance_score=1.0,
                )
            )

        experience: list[ResumeExperience] = []
        if not profile.employment:
            pass
        elif len(profile.employment) == 1:
            canonical_emp = profile.employment[0]
            experience.append(
                ResumeExperience(
                    company=canonical_emp.company,
                    role=canonical_emp.role or canonical_emp.canonical_role or "Software Engineer",
                    canonical_role=canonical_emp.canonical_role or canonical_emp.role or "Software Engineer",
                    team=canonical_emp.team,
                    location=canonical_emp.location,
                    start_date=canonical_emp.start_date,
                    end_date=canonical_emp.end_date,
                    current=canonical_emp.current,
                    bullets=exp_bullets,
                    technologies=canonical_emp.technologies,
                    evidence_ids=canonical_emp.evidence_ids,
                )
            )
        else:
            # Candidate profile has multiple employment records:
            # Map each tailored bullet to its specific employer via evidence IDs
            for emp in profile.employment:
                emp_ev_ids = set(emp.evidence_ids)
                for ach in emp.achievements:
                    emp_ev_ids.update(ach.evidence_ids)

                matching_bullets = [
                    b for b in exp_bullets
                    if any(eid in emp_ev_ids for eid in b.evidence_ids)
                ]
                if matching_bullets:
                    experience.append(
                        ResumeExperience(
                            company=emp.company,
                            role=emp.role or emp.canonical_role or "Software Engineer",
                            canonical_role=emp.canonical_role or emp.role or "Software Engineer",
                            team=emp.team,
                            location=emp.location,
                            start_date=emp.start_date,
                            end_date=emp.end_date,
                            current=emp.current,
                            bullets=matching_bullets,
                            technologies=emp.technologies,
                            evidence_ids=emp.evidence_ids,
                        )
                    )
            # Fallback if bullets could not be cleanly partitioned by evidence ID
            if not experience and profile.employment:
                emp = next((e for e in profile.employment if e.current), profile.employment[0])
                experience.append(
                    ResumeExperience(
                        company=emp.company,
                        role=emp.role or emp.canonical_role or "Software Engineer",
                        canonical_role=emp.canonical_role or emp.role or "Software Engineer",
                        team=emp.team,
                        location=emp.location,
                        start_date=emp.start_date,
                        end_date=emp.end_date,
                        current=emp.current,
                        bullets=exp_bullets,
                        technologies=emp.technologies,
                        evidence_ids=emp.evidence_ids,
                    )
                )

        # 2. Convert Projects
        projects: list[ResumeProject] = []

        for prj_item in draft.projects:
            canon_p = resolve_canonical_project(prj_item.name, profile)
            p_claim_type = canon_p.claim_type if canon_p else "PERSONAL_PROJECT"
            p_deployment_status = canon_p.deployment_status if canon_p else "PORTFOLIO_DEMO"
            if p_claim_type == "BENCHMARK":
                p_metric_type = "BENCHMARK"
            elif p_claim_type == "PROFESSIONAL" and p_deployment_status == "PRODUCTION":
                p_metric_type = "PRODUCTION"
            elif p_claim_type == "ESTIMATE":
                p_metric_type = "ESTIMATE"
            elif p_claim_type == "ACADEMIC":
                p_metric_type = "ACADEMIC"
            elif p_claim_type == "POSITIONING":
                p_metric_type = "POSITIONING"
            else:
                p_metric_type = "PROJECT"

            p_bullets: list[ResumeBullet] = []
            for pb in prj_item.bullets:
                bullet_claim_type = p_claim_type
                bullet_metric_type = p_metric_type
                if canon_p and pb.evidence_ids:
                    for ach in canon_p.achievements:
                        if any(eid in ach.evidence_ids for eid in pb.evidence_ids):
                            if ach.claim_type:
                                bullet_claim_type = ach.claim_type
                                if bullet_claim_type == "BENCHMARK":
                                    bullet_metric_type = "BENCHMARK"
                                elif bullet_claim_type == "PROFESSIONAL" and p_deployment_status == "PRODUCTION":
                                    bullet_metric_type = "PRODUCTION"
                                elif bullet_claim_type == "ESTIMATE":
                                    bullet_metric_type = "ESTIMATE"
                                elif bullet_claim_type == "ACADEMIC":
                                    bullet_metric_type = "ACADEMIC"
                                elif bullet_claim_type == "POSITIONING":
                                    bullet_metric_type = "POSITIONING"
                                else:
                                    bullet_metric_type = "PROJECT"
                            break

                p_bullets.append(
                    ResumeBullet(
                        text=pb.text.strip(),
                        evidence_ids=pb.evidence_ids or (canon_p.evidence_ids if canon_p else prj_item.evidence_ids),
                        claim_type=bullet_claim_type,
                        metric_type=bullet_metric_type,
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
                        claim_type=p_claim_type,
                        metric_type=p_metric_type,
                    )
                )

            projects.append(
                ResumeProject(
                    name=canon_p.name if canon_p else prj_item.name,
                    description=canon_p.description if canon_p else "",
                    architecture=canon_p.architecture if canon_p else None,
                    deployment_status=p_deployment_status,
                    bullets=p_bullets,
                    technologies=prj_item.technologies or (canon_p.technologies if canon_p else []),
                    links=canon_p.links if canon_p else [],
                    evidence_ids=prj_item.evidence_ids or (canon_p.evidence_ids if canon_p else []),
                )
            )

        # 3. Convert Skill Groups
        skill_groups: list[ResumeSkillGroup] = []
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
                "dominant_themes": getattr(draft, "dominant_themes", []) or (analysis.dominant_themes if analysis else []),
                "tailoring_rationale": draft.tailoring_rationale,
                "overall_score": match_result.overall_score if match_result else None,
            },
        )

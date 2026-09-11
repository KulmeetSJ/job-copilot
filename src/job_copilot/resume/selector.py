"""Deterministic Resume Content Selector."""

import re
from typing import Dict, List, Optional, Set, Tuple
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
from job_copilot.resume.summary import SummaryGenerator
from job_copilot.schemas.candidate import (
    Achievement,
    CandidateProfile,
    Project,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ResumeContentSelector:
    """
    Selects, filters, and ranks candidate profile facts deterministically into a TailoredResume.
    
    Safety Invariants:
    1. Only CONFIRMED facts from the canonical profile are selected.
    2. Employment title and company remain strictly canonical ('Software Engineer', 'HSBC').
    3. Benchmark metrics remain explicitly benchmarks.
    4. Personal/portfolio projects remain explicitly projects.
    5. Every bullet point retains full provenance evidence IDs.
    """

    def __init__(self, summary_generator: Optional[SummaryGenerator] = None):
        self.summary_generator = summary_generator or SummaryGenerator()

    def select_content(
        self,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis] = None,
        match_result: Optional[JobMatchResult] = None,
    ) -> TailoredResume:
        """Construct a TailoredResume intermediate representation."""
        
        # 1. Generate Summary
        summary = self.summary_generator.generate(strategy, profile, analysis)

        # 2. Select and Categorize Technical Skills
        skill_groups = self._select_skills(profile, strategy, analysis)

        # 3. Select Experience Bullets
        experience = self._select_experience(profile, strategy, analysis)

        # 4. Select Projects
        projects = self._select_projects(profile, strategy, analysis)

        # 5. Education, Certifications, Awards
        education = profile.education
        certifications = profile.certifications
        awards = profile.awards

        return TailoredResume(
            strategy_name=strategy.name,
            display_title=strategy.display_title,
            personal_info=profile.personal_info,
            summary=summary,
            skill_groups=skill_groups,
            experience=experience,
            projects=projects,
            education=education,
            certifications=certifications,
            awards=awards,
            section_order=strategy.section_order,
            target_job_title=analysis.job_title if analysis else None,
            target_company=analysis.company if analysis else None,
            metadata={
                "overall_score": match_result.overall_score if match_result else None,
                "strategy": strategy.name,
            },
        )

    def _select_skills(
        self,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis] = None,
    ) -> List[ResumeSkillGroup]:
        """Group and prioritize CONFIRMED skills based on strategy and JD requirements."""
        groups: List[ResumeSkillGroup] = []
        prioritized_set = {s.lower(): s for s in strategy.prioritized_skills}
        deprioritized_set = {s.lower() for s in strategy.deprioritized_skills}

        jd_skills_lower = set()
        if analysis:
            jd_skills_lower = {s.normalized_name.lower() for s in analysis.required_skills + analysis.preferred_skills}

        for cat in profile.skills:
            confirmed_skills = []
            ev_ids = []

            for s in cat.skills:
                # Truth Safety: Only select CONFIRMED skills
                if s.status != "CONFIRMED":
                    continue
                if s.name.lower() in deprioritized_set:
                    continue

                confirmed_skills.append(s.name)
                if s.evidence:
                    for ev in s.evidence:
                        if ev.evidence_id:
                            ev_ids.append(ev.evidence_id)

            if not confirmed_skills:
                continue

            # Sort skills: JD matches first, then strategy prioritized, then alphabetical
            def skill_rank(skill_name: str) -> Tuple[int, int, str]:
                name_l = skill_name.lower()
                is_jd = 0 if name_l in jd_skills_lower else 1
                is_strat = 0 if name_l in prioritized_set else 1
                return (is_jd, is_strat, skill_name)

            sorted_skills = sorted(confirmed_skills, key=skill_rank)

            groups.append(
                ResumeSkillGroup(
                    category=cat.category,
                    skills=sorted_skills,
                    evidence_ids=sorted(list(set(ev_ids))),
                )
            )

        return groups

    def _select_experience(
        self,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis] = None,
    ) -> List[ResumeExperience]:
        """Rank and format HSBC employment bullets."""
        exp_list: List[ResumeExperience] = []

        keywords = [k.lower() for k in strategy.preferred_experience_keywords]
        if analysis:
            keywords.extend([kw.lower() for kw in analysis.ats_keywords])

        for emp in profile.employment:
            candidate_bullets: List[ResumeBullet] = []

            for ach in emp.achievements:
                # Score bullet relevance
                desc_lower = ach.description.lower()
                score = sum(2.0 for kw in keywords if kw in desc_lower)
                # Boost if it contains verified metrics
                if ach.metrics:
                    score += 3.0

                bullet = ResumeBullet(
                    text=ach.description,
                    evidence_ids=ach.evidence_ids,
                    claim_type=ach.claim_type,
                    metric_type="PRODUCTION",
                    relevance_score=score,
                )
                candidate_bullets.append(bullet)

            # Sort by relevance score descending
            candidate_bullets.sort(key=lambda b: b.relevance_score, reverse=True)

            # Cap at max_bullets_per_experience
            selected_bullets = candidate_bullets[: strategy.max_bullets_per_experience]

            # Format experience record
            exp_list.append(
                ResumeExperience(
                    company=emp.company,
                    role=emp.role,  # Canonical 'Software Engineer'
                    canonical_role=emp.canonical_role or emp.role or "Software Engineer",
                    team=emp.team,
                    location=emp.location,
                    start_date=emp.start_date,
                    end_date=emp.end_date,
                    current=emp.current,
                    bullets=selected_bullets,
                    technologies=emp.technologies,
                    evidence_ids=emp.evidence_ids,
                )
            )

        return exp_list

    def _select_projects(
        self,
        profile: CandidateProfile,
        strategy: ResumeStrategyConfig,
        analysis: Optional[JobAnalysis] = None,
    ) -> List[ResumeProject]:
        """Select and rank preferred projects up to max_projects."""
        selected_projects: List[ResumeProject] = []

        pref_map = {p.lower(): idx for idx, p in enumerate(strategy.preferred_projects)}
        depref_set = {p.lower() for p in strategy.deprioritized_projects}

        jd_skills_lower = set()
        if analysis:
            jd_skills_lower = {s.normalized_name.lower() for s in analysis.required_skills + analysis.preferred_skills}

        ranked_projects: List[Tuple[float, Project]] = []

        for prj in profile.projects:
            name_l = prj.name.lower()
            if name_l in depref_set:
                continue

            # Calculate project relevance score
            score = 0.0
            if name_l in pref_map:
                # Strategy preference rank boost
                score += 50.0 - (pref_map[name_l] * 5.0)

            # Technology match boost
            for tech in prj.technologies:
                if tech.lower() in jd_skills_lower:
                    score += 10.0

            ranked_projects.append((score, prj))

        # Sort projects by score descending
        ranked_projects.sort(key=lambda x: x[0], reverse=True)

        for score, prj in ranked_projects[: strategy.max_projects]:
            # Select project bullets
            prj_bullets: List[ResumeBullet] = []
            for ach in prj.achievements:
                prj_bullets.append(
                    ResumeBullet(
                        text=ach.description,
                        evidence_ids=ach.evidence_ids,
                        claim_type=ach.claim_type,
                        metric_type="PROJECT" if ach.claim_type == "PERSONAL_PROJECT" else "BENCHMARK",
                        relevance_score=score,
                    )
                )

            # If no achievement bullet was found, use main description
            if not prj_bullets:
                prj_bullets.append(
                    ResumeBullet(
                        text=prj.description,
                        evidence_ids=prj.evidence_ids,
                        claim_type=prj.claim_type,
                        metric_type="PROJECT",
                        relevance_score=score,
                    )
                )

            selected_projects.append(
                ResumeProject(
                    name=prj.name,
                    description=prj.description,
                    architecture=prj.architecture,
                    deployment_status=prj.deployment_status,
                    bullets=prj_bullets[: strategy.max_bullets_per_project],
                    technologies=prj.technologies,
                    links=prj.links,
                    start_date=prj.start_date,
                    end_date=prj.end_date,
                    evidence_ids=prj.evidence_ids,
                    relevance_score=score,
                )
            )

        return selected_projects

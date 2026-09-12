"""Candidate to Job Description Matching Engine."""

from typing import Dict, List, Optional, Set, Tuple
from job_copilot.resume.models import (
    JobAnalysis,
    JobMatchResult,
    JobRequirement,
    MatchStatus,
    RequirementMatch,
)
from job_copilot.schemas.candidate import CandidateProfile, SkillCategory
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CandidateJobMatcher:
    """
    Compares structured JobAnalysis against the canonical CandidateProfile.
    Classifies candidate evidence relationship for every requirement:
    - MATCH_CONFIRMED: Confirmed professional evidence in master profile
    - MATCH_PARTIAL: Confirmed skill but years of experience is below JD requirement
    - MATCH_PROJECT_ONLY: Confirmed evidence exists in personal / demo projects
    - MATCH_POSITIONING_ONLY: Skill exists only in unverified positioning (NEEDS_REVIEW)
    - NO_EVIDENCE: No factual candidate evidence for this skill
    """

    def match(
        self,
        analysis: JobAnalysis,
        profile: CandidateProfile,
    ) -> JobMatchResult:
        """Perform deterministic matching between job requirements and candidate profile."""
        skill_index = self._index_candidate_skills(profile)
        candidate_years = profile.verified_experience_years
        
        matches: List[RequirementMatch] = []
        matched_req = 0
        total_req = len(analysis.required_skills)
        matched_pref = 0
        total_pref = len(analysis.preferred_skills)

        # Match Required Skills
        for req in analysis.required_skills:
            match = self._evaluate_requirement(req, skill_index, candidate_years=candidate_years)
            matches.append(match)
            if match.match_status in (MatchStatus.MATCH_CONFIRMED, MatchStatus.MATCH_PARTIAL, MatchStatus.MATCH_PROJECT_ONLY):
                matched_req += 1

        # Match Preferred Skills
        for req in analysis.preferred_skills:
            match = self._evaluate_requirement(req, skill_index, candidate_years=candidate_years)
            matches.append(match)
            if match.match_status in (MatchStatus.MATCH_CONFIRMED, MatchStatus.MATCH_PARTIAL, MatchStatus.MATCH_PROJECT_ONLY):
                matched_pref += 1

        # Calculate keyword coverage
        total_ats = len(analysis.ats_keywords)
        matched_ats = sum(1 for kw in analysis.ats_keywords if self._skill_in_index(kw, skill_index))
        coverage_pct = round((matched_ats / total_ats * 100.0) if total_ats > 0 else 100.0, 1)

        # Calculate overall score
        req_rate = (matched_req / total_req) if total_req > 0 else 1.0
        pref_rate = (matched_pref / total_pref) if total_pref > 0 else 1.0
        ats_rate = (matched_ats / total_ats) if total_ats > 0 else 1.0
        
        # Weighted overall score (60% required, 25% preferred, 15% ATS keywords)
        overall_score = round((req_rate * 60.0 + pref_rate * 25.0 + ats_rate * 15.0), 1)

        # Suggest strategy
        recommended_strategy = self._recommend_strategy(analysis, profile)

        summary = (
            f"Matched {matched_req}/{total_req} required skills and "
            f"{matched_pref}/{total_pref} preferred skills. "
            f"Keyword coverage: {coverage_pct}%. Recommended strategy: {recommended_strategy}."
        )

        return JobMatchResult(
            overall_score=overall_score,
            matches=matches,
            matched_required_count=matched_req,
            total_required_count=total_req,
            matched_preferred_count=matched_pref,
            total_preferred_count=total_pref,
            keyword_coverage_pct=coverage_pct,
            recommended_strategy=recommended_strategy,
            summary=summary,
        )

    def _index_candidate_skills(self, profile: CandidateProfile) -> Dict[str, Dict]:
        """Build normalized skill lookup index mapping lowercase names to skill record & context."""
        index: Dict[str, Dict] = {}

        # 1. Index skills from categories
        for cat in profile.skills:
            for skill in cat.skills:
                norm = skill.name.lower()
                evidence_types = [e.type.lower() for e in skill.evidence] if skill.evidence else []
                evidence_ids = [e.evidence_id for e in skill.evidence if e.evidence_id] if skill.evidence else []
                
                index[norm] = {
                    "canonical_name": skill.name,
                    "status": skill.status,
                    "evidence_types": evidence_types,
                    "evidence_ids": evidence_ids,
                    "contexts": [e.context for e in skill.evidence] if skill.evidence else [],
                }
                # Also add aliases / fragments (e.g. "gcp" for "google cloud platform (gcp)")
                if "(" in norm and ")" in norm:
                    inside = norm[norm.find("(") + 1 : norm.find(")")].strip()
                    outside = norm[: norm.find("(")].strip()
                    if inside not in index:
                        index[inside] = index[norm]
                    if outside not in index:
                        index[outside] = index[norm]

        # 2. Index technologies from employment (HSBC)
        for emp in profile.employment:
            for tech in emp.technologies:
                norm = tech.lower()
                if norm not in index:
                    index[norm] = {
                        "canonical_name": tech,
                        "status": "CONFIRMED",
                        "evidence_types": ["professional"],
                        "evidence_ids": emp.evidence_ids,
                        "contexts": [f"HSBC Work Experience: {tech}"],
                    }

        # 3. Index technologies from projects
        for prj in profile.projects:
            for tech in prj.technologies:
                norm = tech.lower()
                if norm not in index:
                    index[norm] = {
                        "canonical_name": tech,
                        "status": "CONFIRMED",
                        "evidence_types": ["project"],
                        "evidence_ids": prj.evidence_ids,
                        "contexts": [f"Project ({prj.name}): {tech}"],
                    }

        return index

    def _skill_in_index(self, skill_name: str, index: Dict[str, Dict]) -> bool:
        """Check if skill is present and confirmed in index."""
        norm = skill_name.lower()
        if norm in index and index[norm]["status"] == "CONFIRMED":
            return True
        for key in index:
            if norm == key or norm in key or key in norm:
                if index[key]["status"] == "CONFIRMED":
                    return True
        return False

    def _evaluate_requirement(
        self,
        req: JobRequirement,
        skill_index: Dict[str, Dict],
        candidate_years: Optional[float] = None,
    ) -> RequirementMatch:
        """Evaluate a single requirement against the indexed profile."""
        norm_name = req.normalized_name.lower()
        entry = None

        if norm_name in skill_index:
            entry = skill_index[norm_name]
        else:
            for key, val in skill_index.items():
                if norm_name == key or norm_name in key or key in norm_name:
                    entry = val
                    break

        if not entry:
            return RequirementMatch(
                requirement=req,
                match_status=MatchStatus.NO_EVIDENCE,
                candidate_evidence_ids=[],
                candidate_evidence_text=None,
                candidate_years=None,
                notes=f"No factual candidate evidence found for '{req.normalized_name}'.",
            )

        status = entry["status"]
        evidence_ids = entry["evidence_ids"]
        evidence_types = entry["evidence_types"]
        context_str = "; ".join(entry["contexts"][:2]) if entry["contexts"] else None

        # Check if needs review / positioning
        if status == "NEEDS_REVIEW" or "positioning" in evidence_types:
            return RequirementMatch(
                requirement=req,
                match_status=MatchStatus.MATCH_POSITIONING_ONLY,
                candidate_evidence_ids=evidence_ids,
                candidate_evidence_text=context_str,
                candidate_years=None,
                notes=f"Skill '{req.normalized_name}' is unverified / NEEDS_REVIEW.",
            )

        # Check if project-only evidence
        is_professional = "professional" in evidence_types
        if not is_professional:
            return RequirementMatch(
                requirement=req,
                match_status=MatchStatus.MATCH_PROJECT_ONLY,
                candidate_evidence_ids=evidence_ids,
                candidate_evidence_text=context_str,
                candidate_years=None,
                notes=f"Skill '{req.normalized_name}' supported via personal/portfolio projects.",
            )

        # Confirmed professional skill - check years of experience
        if req.years_required:
            if candidate_years is not None and req.years_required > candidate_years:
                return RequirementMatch(
                    requirement=req,
                    match_status=MatchStatus.MATCH_PARTIAL,
                    candidate_evidence_ids=evidence_ids,
                    candidate_evidence_text=context_str,
                    candidate_years=candidate_years,
                    notes=(
                        f"Candidate has {candidate_years} yrs confirmed professional experience; "
                        f"JD requires {req.years_required} yrs."
                    ),
                )
            elif candidate_years is None:
                return RequirementMatch(
                    requirement=req,
                    match_status=MatchStatus.MATCH_PARTIAL,
                    candidate_evidence_ids=evidence_ids,
                    candidate_evidence_text=context_str,
                    candidate_years=None,
                    notes=(
                        f"Candidate has confirmed professional experience for '{req.normalized_name}'; "
                        f"total experience duration cannot be confirmed from available evidence (JD requires {req.years_required} yrs)."
                    ),
                )

        return RequirementMatch(
            requirement=req,
            match_status=MatchStatus.MATCH_CONFIRMED,
            candidate_evidence_ids=evidence_ids,
            candidate_evidence_text=context_str,
            candidate_years=candidate_years,
            notes=f"Confirmed professional experience for '{req.normalized_name}'.",
        )

    def _recommend_strategy(self, analysis: JobAnalysis, profile: CandidateProfile) -> str:
        """Heuristically determine the best resume strategy based on JD keywords."""
        text = f"{analysis.job_title or ''} {' '.join(analysis.ats_keywords)}".lower()

        scores = {
            "backend_java": 0,
            "cloud_devops": 0,
            "sre_devops": 0,
            "data_engineering": 0,
            "full_stack": 0,
        }

        # Java Backend
        if "backend" in text: scores["backend_java"] += 3
        if "java" in text: scores["backend_java"] += 4
        if "spring" in text or "spring boot" in text: scores["backend_java"] += 4
        if "microservices" in text or "distributed" in text: scores["backend_java"] += 2
        if "rate limit" in text or "redis" in text: scores["backend_java"] += 2

        # Cloud / DevOps
        if "cloud" in text: scores["cloud_devops"] += 2
        if "devops" in text: scores["cloud_devops"] += 4
        if "terraform" in text: scores["cloud_devops"] += 4
        if "infrastructure" in text or "iac" in text: scores["cloud_devops"] += 3
        if "jenkins" in text or "ci/cd" in text: scores["cloud_devops"] += 3

        # SRE / DevOps
        if "sre" in text or "reliability" in text: scores["sre_devops"] += 5
        if "monitoring" in text or "observability" in text: scores["sre_devops"] += 4
        if "incident" in text or "mttr" in text or "sli" in text or "slo" in text: scores["sre_devops"] += 4
        if "uptime" in text or "alerts" in text: scores["sre_devops"] += 3

        # Data Engineering
        if "data" in text or "dataflow" in text or "beam" in text: scores["data_engineering"] += 4
        if "bigquery" in text or "etl" in text or "pipeline" in text: scores["data_engineering"] += 4
        if "parquet" in text or "airflow" in text: scores["data_engineering"] += 3

        # Full Stack
        if "full stack" in text or "fullstack" in text: scores["full_stack"] += 5
        if "react" in text or "next.js" in text: scores["full_stack"] += 4
        if "frontend" in text or "typescript" in text: scores["full_stack"] += 3
        if "ui" in text or "tailwind" in text: scores["full_stack"] += 2

        sorted_strategies = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_strategies[0][0]

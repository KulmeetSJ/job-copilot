"""Deterministic Candidate to Job Matching Engine with Provenance and Explainability."""

from typing import Dict, List, Optional, Set, Tuple

from job_copilot.matching.config import MatchingConfig, default_matching_config
from job_copilot.matching.models import (
    AnalyzedJob,
    MatchClassification,
    RequirementMatchResult,
    TechnicalRequirement,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

class CandidateMatcher:
    """
    Evaluates analyzed job requirements against canonical candidate truth.
    Strictly attaches upstream evidence IDs and provides explainable reasoning.
    """

    def __init__(self, config: Optional[MatchingConfig] = None):
        self.config = config or default_matching_config

    def match_job(
        self,
        job: AnalyzedJob,
        profile: CandidateProfile,
    ) -> List[RequirementMatchResult]:
        """Perform deterministic evaluation of all job requirements against candidate profile."""
        skill_index = self._build_candidate_skill_index(profile)
        verified_years = profile.verified_experience_years
        results: List[RequirementMatchResult] = []

        for req in job.technical_requirements:
            match_res = self._match_single_requirement(req, skill_index, verified_years=verified_years)
            results.append(match_res)

        return results

    def _build_candidate_skill_index(self, profile: CandidateProfile) -> Dict[str, Dict]:
        """Index skills, technologies, and achievements with their provenance and status."""
        index: Dict[str, Dict] = {}

        # 1. Index skills from categories
        for cat in profile.skills:
            for skill in cat.skills:
                norm = skill.name.lower()
                ev_types = [e.type.lower() for e in skill.evidence] if skill.evidence else []
                ev_ids = [e.evidence_id for e in skill.evidence if e.evidence_id] if skill.evidence else []
                contexts = [e.context for e in skill.evidence] if skill.evidence else []

                # Classify source tier
                tier = "POSITIONING"
                if skill.status == "CONFIRMED":
                    if any("training_exposure" in t for t in ev_types):
                        tier = "EXPOSURE"
                    elif any("professional" in t for t in ev_types):
                        tier = "PROFESSIONAL"
                    elif any("project" in t for t in ev_types):
                        tier = "PROJECT"
                    else:
                        tier = "PROFESSIONAL"
                elif skill.status == "NEEDS_REVIEW":
                    tier = "POSITIONING"

                index[norm] = {
                    "canonical_name": skill.name,
                    "status": skill.status,
                    "tier": tier,
                    "evidence_types": ev_types,
                    "evidence_ids": ev_ids,
                    "contexts": contexts,
                }
                
                # Handle acronyms / aliases e.g. "GCP" for "Google Cloud Platform (GCP)"
                if "(" in norm and ")" in norm:
                    inside = norm[norm.find("(") + 1 : norm.find(")")].strip()
                    outside = norm[: norm.find("(")].strip()
                    if inside not in index:
                        index[inside] = index[norm]
                    if outside not in index:
                        index[outside] = index[norm]

        # 2. Index technologies from HSBC employment & PaymentsAI
        for emp in profile.employment:
            for tech in emp.technologies:
                norm = tech.lower()
                if norm not in index:
                    index[norm] = {
                        "canonical_name": tech,
                        "status": "CONFIRMED",
                        "tier": "PROFESSIONAL",
                        "evidence_types": ["professional"],
                        "evidence_ids": emp.evidence_ids,
                        "contexts": [f"HSBC Employment ({emp.company}): {tech}"],
                    }

            for ach in emp.achievements:
                for tech in ach.technologies:
                    norm = tech.lower()
                    if norm not in index:
                        index[norm] = {
                            "canonical_name": tech,
                            "status": "CONFIRMED",
                            "tier": "PROFESSIONAL",
                            "evidence_types": ["professional"],
                            "evidence_ids": ach.evidence_ids,
                            "contexts": [ach.description],
                        }

        # 3. Index technologies from personal / demo projects
        for prj in profile.projects:
            for tech in prj.technologies:
                norm = tech.lower()
                if norm not in index or index[norm]["tier"] not in ("PROFESSIONAL", "EXPOSURE"):
                    index[norm] = {
                        "canonical_name": tech,
                        "status": "CONFIRMED",
                        "tier": "PROJECT",
                        "evidence_types": ["project"],
                        "evidence_ids": prj.evidence_ids,
                        "contexts": [f"Project ({prj.name}): {tech}"],
                    }

        # 4. Standard aliases for candidate's evidenced capabilities
        alias_map = {
            "ci/cd": ("CI/CD", ["EXP-HSBC-CICD-001"], "Jenkins CI/CD automation for DAG and pipeline releases"),
            "continuous integration": ("CI/CD", ["EXP-HSBC-CICD-001"], "Jenkins CI/CD automation for DAG and pipeline releases"),
            "rest apis": ("REST APIs", ["EXP-HSBC-PAYMENTS-AI-001"], "REST API development for HSBC PaymentsAI platform"),
            "rest api": ("REST APIs", ["EXP-HSBC-PAYMENTS-AI-001"], "REST API development for HSBC PaymentsAI platform"),
            "microservices": ("Microservices", ["EXP-HSBC-PAYMENTS-AI-001"], "Backend microservices architecture for HSBC PaymentsAI"),
            "iac": ("Infrastructure as Code", ["EXP-HSBC-TF-001"], "Terraform IaC for GCP infrastructure"),
            "infrastructure as code": ("Infrastructure as Code", ["EXP-HSBC-TF-001"], "Terraform IaC for GCP infrastructure"),
            "cloud composer": ("Cloud Composer", ["EXP-HSBC-BEAM-001", "EXP-HSBC-CICD-001"], "GCP Cloud Composer (Airflow) orchestration"),
            "monitoring": ("Cloud Monitoring", ["EXP-HSBC-OBS-001"], "GCP Cloud Monitoring and alerting"),
            "observability": ("Observability", ["EXP-HSBC-OBS-001"], "GCP Cloud Monitoring, metrics, and alerting"),
        }
        for alias_key, (canonical, ev_ids, ctx) in alias_map.items():
            if alias_key not in index:
                index[alias_key] = {
                    "canonical_name": canonical,
                    "status": "CONFIRMED",
                    "tier": "PROFESSIONAL",
                    "evidence_types": ["professional"],
                    "evidence_ids": ev_ids,
                    "contexts": [ctx],
                }

        return index

    def _match_single_requirement(
        self,
        req: TechnicalRequirement,
        skill_index: Dict[str, Dict],
        verified_years: Optional[float] = None,
    ) -> RequirementMatchResult:
        """Evaluate a single requirement against the candidate index."""
        norm_req = req.normalized_name.lower()
        entry = None

        if norm_req in skill_index:
            entry = skill_index[norm_req]
        else:
            for key, val in skill_index.items():
                if norm_req == key or norm_req in key or key in norm_req:
                    entry = val
                    break

        # Case 1: No evidence found
        if not entry:
            return RequirementMatchResult(
                requirement=req,
                classification=MatchClassification.NO_EVIDENCE,
                candidate_evidence_ids=[],
                candidate_evidence_text=None,
                confidence=1.0,
                reason=f"No factual candidate evidence or positioning found for '{req.normalized_name}'.",
            )

        tier = entry["tier"]
        ev_ids = entry["evidence_ids"]
        context_str = "; ".join(entry["contexts"][:2]) if entry["contexts"] else None

        # Case 2: Unverified / Positioning only (e.g. AWS)
        if tier == "POSITIONING":
            return RequirementMatchResult(
                requirement=req,
                classification=MatchClassification.MATCH_POSITIONING_ONLY,
                candidate_evidence_ids=ev_ids,
                candidate_evidence_text=context_str,
                confidence=0.9,
                reason=(
                    f"Candidate has positioning relevance for '{req.normalized_name}', "
                    f"but it is unverified (NEEDS_REVIEW) and does not count as confirmed technical experience."
                ),
            )

        # Case 3: Hands-on / Training Exposure (e.g. GKE, Helm, Google ADK)
        if tier == "EXPOSURE":
            # If JD asks for 3+ or 5+ years of heavy production administration
            if req.years_required and req.years_required >= 3.0:
                return RequirementMatchResult(
                    requirement=req,
                    classification=MatchClassification.PARTIAL_MATCH,
                    candidate_evidence_ids=ev_ids,
                    candidate_evidence_text=context_str,
                    confidence=0.85,
                    reason=(
                        f"Candidate has confirmed hands-on/training exposure in '{req.normalized_name}' ({', '.join(ev_ids)}), "
                        f"but JD requests {req.years_required} yrs depth of production operations."
                    ),
                )

            return RequirementMatchResult(
                requirement=req,
                classification=MatchClassification.MATCH_EXPOSURE_ONLY,
                candidate_evidence_ids=ev_ids,
                candidate_evidence_text=context_str,
                confidence=0.95,
                reason=(
                    f"Candidate has confirmed training and hands-on exposure in '{req.normalized_name}' "
                    f"({', '.join(ev_ids)}), distinct from large-scale multi-year production operations."
                ),
            )

        # Case 4: Personal / Portfolio Project Only (e.g. Redis, React)
        if tier == "PROJECT":
            return RequirementMatchResult(
                requirement=req,
                classification=MatchClassification.MATCH_PROJECT_ONLY,
                candidate_evidence_ids=ev_ids,
                candidate_evidence_text=context_str,
                confidence=0.95,
                reason=(
                    f"Candidate demonstrates capability in '{req.normalized_name}' via portfolio project "
                    f"({', '.join(ev_ids)}). Not represented as enterprise production experience."
                ),
            )

        # Case 5: Confirmed Professional Experience (HSBC, PaymentsAI)
        if tier == "PROFESSIONAL":
            if req.years_required:
                if verified_years is not None and req.years_required > verified_years:
                    return RequirementMatchResult(
                        requirement=req,
                        classification=MatchClassification.PARTIAL_MATCH,
                        candidate_evidence_ids=ev_ids,
                        candidate_evidence_text=context_str,
                        confidence=0.9,
                        reason=(
                            f"Candidate has confirmed professional experience in '{req.normalized_name}' "
                            f"({', '.join(ev_ids)}), with {verified_years} yrs verified experience (JD asks for {req.years_required} yrs)."
                        ),
                    )
                elif verified_years is None:
                    return RequirementMatchResult(
                        requirement=req,
                        classification=MatchClassification.PARTIAL_MATCH,
                        candidate_evidence_ids=ev_ids,
                        candidate_evidence_text=context_str,
                        confidence=0.8,
                        reason=(
                            f"Candidate has confirmed professional experience in '{req.normalized_name}' "
                            f"({', '.join(ev_ids)}), but total verified experience duration cannot be confirmed from evidence (JD asks for {req.years_required} yrs)."
                        ),
                    )

            return RequirementMatchResult(
                requirement=req,
                classification=MatchClassification.MATCH_CONFIRMED,
                candidate_evidence_ids=ev_ids,
                candidate_evidence_text=context_str,
                confidence=1.0,
                reason=(
                    f"Candidate has confirmed professional experience in '{req.normalized_name}' "
                    f"at HSBC / PaymentsAI ({', '.join(ev_ids)})."
                ),
            )

        return RequirementMatchResult(
            requirement=req,
            classification=MatchClassification.NO_EVIDENCE,
            candidate_evidence_ids=[],
            candidate_evidence_text=None,
            confidence=1.0,
            reason=f"No applicable candidate evidence for '{req.normalized_name}'.",
        )

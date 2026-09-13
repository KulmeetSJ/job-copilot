"""Deterministic Grounding Validator for LLM Resume Drafts."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Set, Tuple
import yaml

from job_copilot.resume.llm.models import LLMBulletItem, LLMResumeDraft
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Strictly unconfirmed technologies that must never appear in candidate materials
UNCONFIRMED_TECHNOLOGIES = {"aws", "amazon web services", "kafka", "apache kafka"}

# Known confirmed metric signatures across candidate evidence
VERIFIED_METRIC_WHITELIST = {
    "2,000+", "2000+", "2,000", "2000", "60%", "10m+", "10m", "10 million", "99.9%", "100+",
    "45%", "30%", "$150k+", "$150k", "150k+", "150k", "$150,000", "150,000", "40%", "12+",
    "1 tb+", "1tb+", "1 tb", "1tb", "100k+", "100k", "100,000+", "8.81", "10.0"
}


class GroundingValidator:
    """
    Validates that an LLM-generated resume draft strictly adheres to verified candidate facts,
    contains zero hallucinated metrics or technologies, preserves production/benchmark boundaries,
    and maps every claim to allowed candidate evidence IDs.
    """

    def __init__(self, evidence_path: Optional[Path] = None):
        self.evidence_path = evidence_path or Path("data/candidate/evidence.yaml")
        self._evidence_facts: Dict[str, Dict[str, Any]] = {}
        self._load_evidence_facts()

    def _load_evidence_facts(self) -> None:
        """Load atomic evidence facts from evidence.yaml if accessible."""
        if not self.evidence_path.exists():
            return
        try:
            with open(self.evidence_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)
            if data and "facts" in data:
                for fact in data["facts"]:
                    fid = fact.get("id")
                    if fid:
                        self._evidence_facts[fid] = fact
        except Exception as e:
            logger.debug(f"Notice loading evidence facts for validator: {e}")

    def validate(
        self,
        draft: LLMResumeDraft,
        profile: CandidateProfile,
    ) -> Tuple[bool, List[str]]:
        """
        Validate LLM resume draft against candidate truth and evidence constraints.
        Returns (is_valid, list_of_errors).
        """
        errors: List[str] = []

        # 1. Structural Checks
        if not draft.summary or len(draft.summary.strip()) < 30:
            errors.append("Resume summary is missing or too short.")
        elif len(draft.summary.strip()) > 900:
            errors.append(f"Resume summary is excessively long ({len(draft.summary.strip())} chars; max 900 chars).")

        if not draft.experience_bullets or len(draft.experience_bullets) < 3:
            errors.append(f"Insufficient experience bullets ({len(draft.experience_bullets)} provided; minimum 3 required).")
        elif len(draft.experience_bullets) > 5:
            errors.append(f"Too many experience bullets ({len(draft.experience_bullets)} provided; maximum 5 to ensure 1-page fit).")

        if not draft.projects or len(draft.projects) < 1:
            errors.append("At least 1 project must be selected.")
        elif len(draft.projects) > 3:
            errors.append(f"Too many projects ({len(draft.projects)} provided; maximum 3 for 1-page fit).")

        if not draft.skill_groups or len(draft.skill_groups) < 2:
            errors.append("At least 2 categorized skill groups must be provided.")

        # 2. Build Allowed Sets
        allowed_exp_evidence: Set[str] = set()
        allowed_proj_evidence: Set[str] = set()
        allowed_proj_names: Set[str] = {p.name.lower() for p in profile.projects}
        
        # Add project name aliases
        allowed_proj_names.update({
            "distributed rate limiter",
            "distributed rate limiter service",
            "smart data storage pipeline",
            "mcp diagnostic tools",
            "mcp diagnostic tools for data pipelines",
            "ai-powered rfp management system",
            "rfp management system",
            "gurugranthi services marketplace",
            "gurugranthi",
            "terraform log summarizer",
            "terraform log summarizer and compliance checker",
        })

        confirmed_skills: Set[str] = set()
        for cat in profile.skills:
            for s in cat.skills:
                if s.status == "CONFIRMED":
                    confirmed_skills.add(s.name.lower())
                    if s.evidence:
                        for ev in s.evidence:
                            if ev.evidence_id:
                                allowed_exp_evidence.add(ev.evidence_id)

        for emp in profile.employment:
            allowed_exp_evidence.update(emp.evidence_ids)
            for ach in emp.achievements:
                allowed_exp_evidence.update(ach.evidence_ids)

        for prj in profile.projects:
            allowed_proj_evidence.update(prj.evidence_ids)
            for ach in prj.achievements:
                allowed_proj_evidence.update(ach.evidence_ids)

        # Allow fallback general IDs
        allowed_exp_evidence.update({
            "EXP-HSBC-001", "EXP-HSBC-TF-001", "EXP-HSBC-BEAM-001", "EXP-HSBC-CICD-001",
            "EXP-HSBC-COST-001", "EXP-HSBC-OBS-001", "EXP-HSBC-SEC-001", "EXP-HSBC-PAYMENTS-AI-001"
        })
        allowed_proj_evidence.update({
            "PRJ-MCP-001", "PRJ-TF-001", "PRJ-STORAGE-001", "PRJ-RFP-001", "PRJ-GG-001", "PRJ-RL-001"
        })

        # 3. Validate Experience Bullets
        for idx, bullet in enumerate(draft.experience_bullets, start=1):
            if not bullet.text or not bullet.text.strip():
                errors.append(f"Experience bullet #{idx} text is empty.")
                continue

            # 3a. Evidence IDs presence and validity
            if not bullet.evidence_ids:
                errors.append(f"Experience bullet #{idx} ('{bullet.text[:35]}...') lacks evidence IDs.")
            else:
                for eid in bullet.evidence_ids:
                    if eid not in allowed_exp_evidence and eid not in self._evidence_facts:
                        errors.append(f"Experience bullet #{idx} cites unknown or unauthorized evidence ID '{eid}'.")

            # 3b. Production vs Benchmark Invariant: Rate Limiter is a project, not HSBC work
            b_lower = bullet.text.lower()
            if "100k+" in b_lower and "rate limiter" in b_lower:
                errors.append(
                    f"Experience bullet #{idx} erroneously attributes project benchmark ('100K+ RPS Rate Limiter') "
                    f"to HSBC production employment."
                )

            # 3c. Check for unconfirmed technologies
            for unconf in UNCONFIRMED_TECHNOLOGIES:
                if re.search(rf"\b{re.escape(unconf)}\b", b_lower):
                    errors.append(
                        f"Experience bullet #{idx} claims unconfirmed technology '{unconf}'."
                    )

            # 3d. Check for hallucinated / unsupported metrics
            self._validate_metrics_in_text(bullet.text, bullet.evidence_ids, f"Experience bullet #{idx}", errors)

        # 4. Validate Projects
        for p_idx, prj in enumerate(draft.projects, start=1):
            if not prj.name or not prj.name.strip():
                errors.append(f"Project #{p_idx} is missing a name.")
                continue

            if prj.name.lower() not in allowed_proj_names:
                errors.append(f"Project #{p_idx} '{prj.name}' is not in candidate's verified projects.")

            if not prj.evidence_ids:
                errors.append(f"Project #{p_idx} '{prj.name}' is missing evidence IDs.")

            for b_idx, p_bullet in enumerate(prj.bullets, start=1):
                pb_lower = p_bullet.text.lower()
                
                # Benchmark distinction for Rate Limiter
                if "100k+" in pb_lower and "production" in pb_lower:
                    errors.append(
                        f"Project '{prj.name}' bullet #{b_idx} claims simulated benchmark ('100K+ RPS') as 'production'."
                    )

                for unconf in UNCONFIRMED_TECHNOLOGIES:
                    if re.search(rf"\b{re.escape(unconf)}\b", pb_lower):
                        errors.append(
                            f"Project '{prj.name}' bullet #{b_idx} claims unconfirmed technology '{unconf}'."
                        )

                self._validate_metrics_in_text(
                    p_bullet.text,
                    p_bullet.evidence_ids or prj.evidence_ids,
                    f"Project '{prj.name}' bullet #{b_idx}",
                    errors
                )

        # 5. Validate Skills Groups
        all_draft_skills: List[str] = []
        for s_grp in draft.skill_groups:
            for s in s_grp.skills:
                all_draft_skills.append(s)
                s_lower = s.lower().strip()
                
                if s_lower in UNCONFIRMED_TECHNOLOGIES:
                    errors.append(f"Skill group '{s_grp.category}' contains unconfirmed technology '{s}'.")

        # 6. Validate Summary Invariants
        sum_lower = draft.summary.lower()
        if "google" in sum_lower and "employed" in sum_lower:
            errors.append("Summary falsely claims candidate was employed at Google.")
        for unconf in UNCONFIRMED_TECHNOLOGIES:
            if re.search(rf"\b{re.escape(unconf)}\b", sum_lower):
                errors.append(f"Summary contains unconfirmed technology '{unconf}'.")

        is_valid = len(errors) == 0
        return is_valid, errors

    def _validate_metrics_in_text(
        self,
        text: str,
        evidence_ids: List[str],
        location_label: str,
        errors: List[str],
    ) -> None:
        """Scan text for metric numbers and ensure they are substantiated by candidate evidence."""
        metric_pattern = re.compile(
            r"[$]?\d[\d,]*(?:\.\d+)?(?:%|[MKk]\+?|\+)?"
        )
        raw_matches = metric_pattern.findall(text)
        found_metrics = [m.strip() for m in raw_matches if any(c.isdigit() for c in m)]

        # Gather context text from cited evidence IDs
        combined_evidence_text = ""
        for eid in evidence_ids:
            if eid in self._evidence_facts:
                fact = self._evidence_facts[eid]
                combined_evidence_text += " " + fact.get("claim", "") + " " + fact.get("context", "")

        combined_evidence_lower = combined_evidence_text.lower()

        for m in found_metrics:
            m_clean = m.lower().strip()
            # Ignore standard experience years, counts or dates (e.g. '1', '2', '3', '4', '5', '6', '10', '2024')
            if m_clean in {"1", "2", "3", "4", "5", "6", "10", "2024", "2023", "2026"}:
                continue

            # If it's in global verified whitelist, allow
            if (
                m_clean in VERIFIED_METRIC_WHITELIST
                or m_clean.rstrip("+") in VERIFIED_METRIC_WHITELIST
                or m_clean.lstrip("$") in VERIFIED_METRIC_WHITELIST
                or m_clean.lstrip("$").rstrip("+") in VERIFIED_METRIC_WHITELIST
            ):
                continue

            # Check if it literally appears in the cited evidence
            if m_clean in combined_evidence_lower or m_clean.rstrip("+") in combined_evidence_lower:
                continue

            errors.append(
                f"{location_label} contains unverified metric '{m}'. Not present in candidate verified evidence."
            )

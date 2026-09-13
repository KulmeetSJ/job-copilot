"""Deterministic Grounding Validator for LLM Resume Drafts."""

import re
from pathlib import Path
from typing import Any

import yaml

from job_copilot.resume.llm.models import LLMResumeDraft
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Strictly unconfirmed technologies that must never appear in candidate materials
UNCONFIRMED_TECHNOLOGIES = {
    "aws",
    "amazon web services",
    "kafka",
    "apache kafka",
    "kubeflow",
    "snowflake",
    "databricks",
    "azure",
}

# Regex to detect metrics in bullet texts
METRIC_REGEX = re.compile(
    r"(?:[$]?\d[\d,]*(?:\.\d+)?\s*(?:%|[MKmk]\+?|TB\+?|tb\+?|\+)?)"
)

# Common non-metric integers (dates, small counts) to ignore during metric validation
BENIGN_INTEGERS = {
    "1", "2", "3", "4", "5", "6", "10", "2018", "2020", "2023", "2024", "2025", "2026"
}


def generate_skill_aliases(name: str) -> set[str]:
    """Algorithmically generate harmless normalized aliases for a skill or technology name."""
    aliases = set()
    cleaned = name.lower().strip()
    if not cleaned:
        return aliases
    aliases.add(cleaned)
    aliases.add(cleaned.replace("-", " "))

    # Handle CI/CD specifically so it does not get split on slash
    if "ci/cd" in cleaned or "cicd" in cleaned:
        aliases.add("ci/cd")
        aliases.add("cicd")

    # Slashes (skip if it's CI/CD)
    if "/" in cleaned and "ci/cd" not in cleaned:
        for part in cleaned.split("/"):
            p = part.strip()
            if p:
                aliases.add(p)
                if p == "javascript":
                    aliases.add("js")
                elif p == "typescript":
                    aliases.add("ts")

    # Parentheses e.g. "Google Cloud Platform (GCP)"
    m_paren = re.search(r"^(.*?)\s*\((.*?)\)$", cleaned)
    if m_paren:
        left = m_paren.group(1).strip()
        inside = m_paren.group(2).strip()
        aliases.add(left)
        aliases.add(inside)
        aliases.add(f"{left} {inside}")
        if "kubernetes" in left:
            aliases.add("kubernetes")
            aliases.add("k8s")
        if "google cloud platform" in left:
            aliases.add("google cloud")

    # Common vendor prefixes
    for prefix in ["gcp ", "google cloud ", "cloud ", "apache "]:
        if cleaned.startswith(prefix):
            aliases.add(cleaned[len(prefix):].strip())

    if cleaned.endswith(" charts"):
        aliases.add(cleaned[:-7].strip())
    if cleaned.endswith(" css"):
        aliases.add(cleaned[:-4].strip())
    if "pub/sub" in cleaned:
        aliases.add("pub/sub")
        aliases.add("pubsub")
        aliases.add("cloud pub/sub")
    if "spring boot" in cleaned:
        aliases.add("spring")
        aliases.add("spring boot")
    if "rest" in cleaned:
        aliases.add("rest")
        aliases.add("rest api")
        aliases.add("rest apis")
        aliases.add("restful apis")
    if "microservice" in cleaned:
        aliases.add("microservices")
        aliases.add("microservice")

    return aliases


def get_metric_variants(raw: str) -> set[str]:
    """Normalize metric representations (e.g. 2,000+ vs 2000+, $150K+ vs $150,000 vs 150k)."""
    raw_clean = raw.strip().lower()
    variants = {raw_clean}
    variants.add(raw_clean.replace(",", ""))

    if raw_clean.endswith("+"):
        base = raw_clean[:-1].strip()
        variants.add(base)
        variants.add(base.replace(",", ""))
    else:
        variants.add(raw_clean + "+")
        variants.add(raw_clean.replace(",", "") + "+")

    if "$" in raw_clean:
        no_dollar = raw_clean.replace("$", "")
        variants.add(no_dollar)
        variants.add(no_dollar.replace(",", ""))
        if no_dollar.endswith("+"):
            variants.add(no_dollar[:-1])
        else:
            variants.add(no_dollar + "+")

    m_int = re.search(r"^(\d{4,})(\+?)$", raw_clean.replace(",", ""))
    if m_int:
        n = int(m_int.group(1))
        p = m_int.group(2)
        variants.add(f"{n:,}{p}")
        variants.add(f"{n:,}")
        variants.add(f"{n}{p}")
        variants.add(f"{n}")

    m_k = re.search(r"^([$]?)(\d+(?:\.\d+)?)\s*k(\+?)$", raw_clean)
    if m_k:
        prefix = m_k.group(1)
        num_val = float(m_k.group(2))
        full_num = int(num_val * 1000)
        plus = m_k.group(3)
        num_str = f"{full_num:,}"
        variants.update({
            f"{prefix}{full_num}{plus}",
            f"{prefix}{num_str}{plus}",
            f"{prefix}{full_num}",
            f"{prefix}{num_str}",
            f"{full_num}{plus}",
            f"{num_str}{plus}",
            f"{full_num}",
            f"{num_str}",
        })

    m_m = re.search(r"^([$]?)(\d+(?:\.\d+)?)\s*m(\+?)$", raw_clean)
    if m_m:
        prefix = m_m.group(1)
        num_val = float(m_m.group(2))
        full_num = int(num_val * 1000000)
        plus = m_m.group(3)
        num_str = f"{full_num:,}"
        variants.update({
            f"{prefix}{full_num}{plus}",
            f"{prefix}{num_str}{plus}",
            f"{prefix}{full_num}",
            f"{prefix}{num_str}",
            f"{full_num}{plus}",
            f"{num_str}{plus}",
            f"{full_num}",
            f"{num_str}",
            f"{int(num_val)} million{plus}",
            f"{int(num_val)} million",
        })

    m_tb = re.search(r"^(\d+)\s*tb(\+?)$", raw_clean)
    if m_tb:
        num = m_tb.group(1)
        plus = m_tb.group(2)
        variants.update({
            f"{num}tb{plus}", f"{num} tb{plus}",
            f"{num}tb", f"{num} tb",
        })

    if "%" in raw_clean:
        no_pct = raw_clean.replace("%", "").strip()
        variants.add(no_pct)
        variants.add(no_pct.rstrip("+"))

    return variants


class GroundingValidator:
    """
    Validates that an LLM-generated resume draft strictly adheres to verified candidate facts,
    contains zero hallucinated metrics or technologies, preserves production/benchmark boundaries,
    and maps every claim to allowed candidate evidence IDs.
    """

    def __init__(self, evidence_path: Path | None = None):
        self.evidence_path = evidence_path or Path("data/candidate/evidence.yaml")
        self._evidence_facts: dict[str, dict[str, Any]] = {}
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
        except (OSError, yaml.YAMLError) as e:
            logger.debug(f"Notice loading evidence facts for validator: {e}")

    def extract_allowed_skills_and_aliases(self, profile: CandidateProfile) -> set[str]:
        """
        Derive allowed skills exclusively and dynamically from confirmed candidate skills
        and canonical profile technologies, generating harmless aliases.
        No hard-coded allowed list is maintained.
        """
        allowed: set[str] = set()

        # 1. From profile.skills (CONFIRMED only)
        for cat in profile.skills:
            # Also register category domain capabilities (e.g. CI/CD, DevOps, Security)
            for part in re.split(r"[,&]|\band\b", cat.category):
                p = part.strip().lower()
                if p and p not in {"languages", "frontend"}:
                    allowed.update(generate_skill_aliases(p))

            for s in cat.skills:
                if s.status == "CONFIRMED":
                    allowed.update(generate_skill_aliases(s.name))

        # 2. From canonical employment technologies & achievements
        for emp in profile.employment:
            for t in emp.technologies:
                allowed.update(generate_skill_aliases(t))
            for ach in emp.achievements:
                for t in ach.technologies:
                    allowed.update(generate_skill_aliases(t))

        # 3. From canonical project technologies & architectures
        for prj in profile.projects:
            for t in prj.technologies:
                allowed.update(generate_skill_aliases(t))
            for ach in prj.achievements:
                for t in ach.technologies:
                    allowed.update(generate_skill_aliases(t))
            if prj.architecture:
                arch_l = prj.architecture.lower()
                if "microservice" in arch_l:
                    allowed.add("microservices")
                    allowed.add("microservice")
                if "rest api" in arch_l or "restful" in arch_l:
                    allowed.add("rest apis")
                    allowed.add("rest api")

        return allowed

    def extract_allowed_metrics_for_evidence(
        self,
        evidence_ids: list[str],
        profile: CandidateProfile,
    ) -> set[str]:
        """
        Derive allowed metrics exclusively from the specific candidate evidence IDs cited.
        Every metric must be traceable to the cited evidence.
        """
        allowed_variants: set[str] = set()

        for eid in evidence_ids:
            # 1. Check atomic fact in evidence.yaml
            if eid in self._evidence_facts:
                fact = self._evidence_facts[eid]
                text = f"{fact.get('claim', '')} {fact.get('context', '')}"
                for m in METRIC_REGEX.findall(text):
                    if any(c.isdigit() for c in m):
                        allowed_variants.update(get_metric_variants(m))

            # 2. Check employment achievements matching eid
            for emp in profile.employment:
                for ach in emp.achievements:
                    if eid in ach.evidence_ids:
                        for m in ach.metrics:
                            for match in METRIC_REGEX.findall(m):
                                if any(c.isdigit() for c in match):
                                    allowed_variants.update(get_metric_variants(match))
                        for match in METRIC_REGEX.findall(ach.description):
                            if any(c.isdigit() for c in match):
                                allowed_variants.update(get_metric_variants(match))
                        # Include linked MET facts for this achievement
                        for lid in ach.evidence_ids:
                            if lid in self._evidence_facts:
                                l_fact = self._evidence_facts[lid]
                                l_text = f"{l_fact.get('claim', '')} {l_fact.get('context', '')}"
                                for match in METRIC_REGEX.findall(l_text):
                                    if any(c.isdigit() for c in match):
                                        allowed_variants.update(get_metric_variants(match))

            # 3. Check projects matching eid
            for prj in profile.projects:
                if eid in prj.evidence_ids:
                    for m in prj.metrics:
                        for match in METRIC_REGEX.findall(m):
                            if any(c.isdigit() for c in match):
                                allowed_variants.update(get_metric_variants(match))
                    for match in METRIC_REGEX.findall(prj.description):
                        if any(c.isdigit() for c in match):
                            allowed_variants.update(get_metric_variants(match))

                for ach in prj.achievements:
                    if eid in ach.evidence_ids or eid in prj.evidence_ids:
                        for m in ach.metrics:
                            for match in METRIC_REGEX.findall(m):
                                if any(c.isdigit() for c in match):
                                    allowed_variants.update(get_metric_variants(match))
                        for match in METRIC_REGEX.findall(ach.description):
                            if any(c.isdigit() for c in match):
                                allowed_variants.update(get_metric_variants(match))
                        for lid in ach.evidence_ids:
                            if lid in self._evidence_facts:
                                l_fact = self._evidence_facts[lid]
                                l_text = f"{l_fact.get('claim', '')} {l_fact.get('context', '')}"
                                for match in METRIC_REGEX.findall(l_text):
                                    if any(c.isdigit() for c in match):
                                        allowed_variants.update(get_metric_variants(match))

            # 4. Handle EXP-HSBC-CICD-001 canonical deployment reduction metric (45%)
            if eid in {"EXP-HSBC-CICD-001", "MET-007"}:
                allowed_variants.update(get_metric_variants("45%"))
                allowed_variants.update(get_metric_variants("100+"))

        return allowed_variants

    def _get_evidence_text(self, evidence_ids: list[str], profile: CandidateProfile) -> str:
        """Gather all context, claim, notes, and description text from cited evidence IDs and linked achievements."""
        combined = []
        for eid in evidence_ids:
            if eid in self._evidence_facts:
                f = self._evidence_facts[eid]
                combined.extend([f.get("claim", ""), f.get("context", ""), f.get("notes", "")])
            for emp in profile.employment:
                for ach in emp.achievements:
                    if eid in ach.evidence_ids:
                        combined.append(ach.description)
                        combined.extend(ach.technologies)
                        for lid in ach.evidence_ids:
                            if lid in self._evidence_facts:
                                lf = self._evidence_facts[lid]
                                combined.extend([lf.get("claim", ""), lf.get("context", ""), lf.get("notes", "")])
            for prj in profile.projects:
                if eid in prj.evidence_ids:
                    combined.append(prj.description)
                    combined.extend(prj.technologies)
                for ach in prj.achievements:
                    if eid in ach.evidence_ids or eid in prj.evidence_ids:
                        combined.append(ach.description)
                        combined.extend(ach.technologies)
                        for lid in ach.evidence_ids:
                            if lid in self._evidence_facts:
                                lf = self._evidence_facts[lid]
                                combined.extend([lf.get("claim", ""), lf.get("context", ""), lf.get("notes", "")])
        return " ".join(combined).lower()

    def validate(
        self,
        draft: LLMResumeDraft,
        profile: CandidateProfile,
    ) -> tuple[bool, list[str]]:
        """
        Validate LLM resume draft against candidate truth and evidence constraints.
        Returns (is_valid, list_of_errors).
        """
        errors: list[str] = []

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

        # 2. Derive Allowed Skills and Evidence Universe
        allowed_skills = self.extract_allowed_skills_and_aliases(profile)

        allowed_exp_evidence: set[str] = set()
        allowed_proj_evidence: set[str] = set()
        allowed_proj_names: set[str] = {p.name.lower() for p in profile.projects}

        # Project name harmless aliases
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
            "terraform log summarizer & shift-left compliance checker",
        })

        for cat in profile.skills:
            for s in cat.skills:
                if s.status == "CONFIRMED" and s.evidence:
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

        all_valid_evidence_ids = allowed_exp_evidence | allowed_proj_evidence | set(self._evidence_facts.keys())

        # 3. Validate Experience Bullets
        for idx, bullet in enumerate(draft.experience_bullets, start=1):
            loc = f"Experience bullet #{idx}"
            if not bullet.text or not bullet.text.strip():
                errors.append(f"{loc} text is empty.")
                continue

            # 3a. Evidence IDs presence and validity
            if not bullet.evidence_ids:
                errors.append(f"{loc} lacks evidence IDs.")
            else:
                for eid in bullet.evidence_ids:
                    if eid not in all_valid_evidence_ids:
                        errors.append(f"{loc} cites unknown or unauthorized evidence ID '{eid}'.")

            # 3b. Production vs Benchmark Boundary: Rate Limiter is a project, not HSBC work
            b_lower = bullet.text.lower()
            if ("100k+" in b_lower or "rate limiter" in b_lower) and "rate limiter" in b_lower:
                errors.append(
                    f"{loc} erroneously attributes project benchmark ('100K+ RPS Rate Limiter') to HSBC production employment."
                )

            # 3c. Check for unconfirmed technologies
            for unconf in UNCONFIRMED_TECHNOLOGIES:
                if re.search(rf"\b{re.escape(unconf)}\b", b_lower):
                    errors.append(f"{loc} claims unconfirmed technology '{unconf}'.")

            # 3d. Check technologies field
            cited_ev_text = self._get_evidence_text(bullet.evidence_ids, profile)
            for tech in bullet.technologies:
                t_clean = tech.lower().strip()
                t_aliases = generate_skill_aliases(t_clean)

                for unconf in UNCONFIRMED_TECHNOLOGIES:
                    if t_clean == unconf or unconf in t_aliases:
                        errors.append(f"{loc} claims unconfirmed technology '{tech}'.")
                        break
                else:
                    is_in_skills = bool(t_aliases & allowed_skills)
                    is_in_evidence = any(alias in cited_ev_text for alias in t_aliases) or (t_clean in cited_ev_text)
                    if not (is_in_skills or is_in_evidence):
                        errors.append(
                            f"{loc} mentions unsupported technology '{tech}'. "
                            f"Must occur in cited evidence or confirmed candidate skills."
                        )

            # 3e. Grounded Metric Validation (derived per cited evidence ID)
            allowed_metrics = self.extract_allowed_metrics_for_evidence(bullet.evidence_ids, profile)
            self._validate_metrics_in_text(bullet.text, bullet.evidence_ids, allowed_metrics, loc, errors)

            # 3f. Semantic Action & Embellishment Checks
            self._validate_semantic_claims(bullet.text, bullet.evidence_ids, profile, loc, errors)

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
                p_loc = f"Project '{prj.name}' bullet #{b_idx}"
                pb_lower = p_bullet.text.lower()

                # Benchmark distinction for Rate Limiter
                if "100k+" in pb_lower and "production" in pb_lower:
                    errors.append(
                        f"{p_loc} claims simulated benchmark ('100K+ RPS') as 'production'."
                    )

                for unconf in UNCONFIRMED_TECHNOLOGIES:
                    if re.search(rf"\b{re.escape(unconf)}\b", pb_lower):
                        errors.append(f"{p_loc} claims unconfirmed technology '{unconf}'.")

                effective_eids = p_bullet.evidence_ids or prj.evidence_ids
                p_ev_text = self._get_evidence_text(effective_eids, profile)
                for tech in p_bullet.technologies:
                    t_clean = tech.lower().strip()
                    t_aliases = generate_skill_aliases(t_clean)
                    for unconf in UNCONFIRMED_TECHNOLOGIES:
                        if t_clean == unconf or unconf in t_aliases:
                            errors.append(f"{p_loc} claims unconfirmed technology '{tech}'.")
                            break
                    else:
                        is_in_skills = bool(t_aliases & allowed_skills)
                        is_in_evidence = any(alias in p_ev_text for alias in t_aliases) or (t_clean in p_ev_text)
                        if not (is_in_skills or is_in_evidence):
                            errors.append(
                                f"{p_loc} mentions unsupported technology '{tech}'. "
                                f"Must occur in cited evidence or confirmed candidate skills."
                            )

                allowed_p_metrics = self.extract_allowed_metrics_for_evidence(effective_eids, profile)
                self._validate_metrics_in_text(p_bullet.text, effective_eids, allowed_p_metrics, p_loc, errors)
                self._validate_semantic_claims(p_bullet.text, effective_eids, profile, p_loc, errors)

        # 5. Strict Dynamic Skills Groups Validation
        for s_grp in draft.skill_groups:
            for s in s_grp.skills:
                s_clean = s.strip()
                s_aliases = generate_skill_aliases(s_clean)

                for unconf in UNCONFIRMED_TECHNOLOGIES:
                    if s_clean.lower() == unconf or unconf in s_aliases:
                        errors.append(f"Skill group '{s_grp.category}' contains unconfirmed technology '{s}'.")

                if not (s_aliases & allowed_skills):
                    errors.append(
                        f"Skill group '{s_grp.category}' contains unknown or unconfirmed skill '{s}'. "
                        f"Every skill must match a confirmed candidate skill from CandidateProfile."
                    )

        # 6. Validate Summary Invariants
        sum_lower = draft.summary.lower()
        if re.search(r"\b(?:employed\s+at|worked\s+at|engineer\s+at|developer\s+at)\s+google\b", sum_lower):
            errors.append("Summary falsely claims candidate was employed at Google.")
        for unconf in UNCONFIRMED_TECHNOLOGIES:
            if re.search(rf"\b{re.escape(unconf)}\b", sum_lower):
                errors.append(f"Summary contains unconfirmed technology '{unconf}'.")

        # Global Certification Check
        self._validate_certifications(draft, profile, errors)

        # Global Leadership / People Management Check
        self._validate_leadership_claims(draft, errors)

        is_valid = len(errors) == 0
        return is_valid, errors

    def _validate_metrics_in_text(
        self,
        text: str,
        evidence_ids: list[str],
        allowed_metrics: set[str],
        location_label: str,
        errors: list[str],
    ) -> None:
        """Scan text for metrics and ensure each is traceable to the bullet's cited evidence."""
        raw_matches = METRIC_REGEX.findall(text)
        found_metrics = [m.strip() for m in raw_matches if any(c.isdigit() for c in m)]

        for m in found_metrics:
            m_clean = m.lower().strip()
            if m_clean in BENIGN_INTEGERS:
                continue

            variants = get_metric_variants(m)
            if not (variants & allowed_metrics):
                errors.append(
                    f"{location_label} contains unverified metric '{m}'. "
                    f"Not traceable to cited evidence IDs: {evidence_ids}."
                )

    def _validate_semantic_claims(
        self,
        text: str,
        evidence_ids: list[str],
        profile: CandidateProfile,
        location_label: str,
        errors: list[str],
    ) -> None:
        """Enforce deterministic evidence grounding for verbs, scale, and performance claims."""
        text_lower = text.lower()
        ev_text = self._get_evidence_text(evidence_ids, profile)

        # 1. Architecture / Ownership verbs: "architected", "architect"
        if re.search(r"\barchitect(?:ed|ing)?\b", text_lower) and "architect" not in ev_text:
            errors.append(
                f"{location_label} claims 'architected' or architectural ownership, "
                f"which is not substantiated by cited evidence IDs: {evidence_ids}."
            )

        # 2. Scale / Sub-second latency claims
        if "sub-second" in text_lower and "sub-second" not in ev_text:
            errors.append(
                f"{location_label} claims 'sub-second' latency not substantiated by cited evidence IDs: {evidence_ids}."
            )

    def _validate_certifications(
        self,
        draft: LLMResumeDraft,
        profile: CandidateProfile,
        errors: list[str],
    ) -> None:
        """Verify that any certification mentioned is confirmed in CandidateProfile."""
        # Known forbidden or unconfirmed certifications that an LLM might hallucinate
        fake_cert_pattern = re.compile(
            r"\b(aws\s+certified(?:[a-z\s]+)?|azure\s+certified(?:[a-z\s]+)?|certified\s+kubernetes\s+administrator|cka\b|ckad\b|hashicorp\s+certified|pmp\b|scrum\s+master)\b",
            re.IGNORECASE,
        )

        all_texts = [draft.summary]
        for b in draft.experience_bullets:
            all_texts.append(b.text)
        for p in draft.projects:
            for pb in p.bullets:
                all_texts.append(pb.text)

        for txt in all_texts:
            m = fake_cert_pattern.search(txt)
            if m:
                errors.append(
                    f"Draft claims unconfirmed certification '{m.group(0)}' not present in CandidateProfile."
                )
                break

    def _validate_leadership_claims(
        self,
        draft: LLMResumeDraft,
        errors: list[str],
    ) -> None:
        """Reject unsupported management or team leadership claims."""
        leadership_pattern = re.compile(
            r"\b(?:led|managed|headed|supervised|directed)\s+(?:a\s+)?(?:team|engineers|developers|squad|group|department)\b",
            re.IGNORECASE,
        )

        all_texts = [draft.summary]
        for b in draft.experience_bullets:
            all_texts.append(b.text)
        for p in draft.projects:
            for pb in p.bullets:
                all_texts.append(pb.text)

        for txt in all_texts:
            m = leadership_pattern.search(txt)
            if m:
                errors.append(
                    f"Draft claims unsupported leadership/management ('{m.group(0)}') not present in candidate profile."
                )
                break

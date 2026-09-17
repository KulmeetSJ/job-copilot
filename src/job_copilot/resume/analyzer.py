"""Deterministic Job Description Analyzer."""

import re
from typing import Dict, List, Optional, Set, Tuple

from job_copilot.resume.models import (
    JobAnalysis,
    JobRequirement,
    JobRequirementType,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Canonical technology dictionary and synonym aliases
TECH_DICTIONARY: Dict[str, Tuple[str, JobRequirementType]] = {
    # Languages
    "java": ("Java", JobRequirementType.LANGUAGE),
    "python": ("Python", JobRequirementType.LANGUAGE),
    "sql": ("SQL", JobRequirementType.LANGUAGE),
    "javascript": ("JavaScript", JobRequirementType.LANGUAGE),
    "typescript": ("TypeScript", JobRequirementType.LANGUAGE),
    "groovy": ("Groovy", JobRequirementType.LANGUAGE),
    "go": ("Go", JobRequirementType.LANGUAGE),
    "golang": ("Go", JobRequirementType.LANGUAGE),
    "c++": ("C++", JobRequirementType.LANGUAGE),
    "rust": ("Rust", JobRequirementType.LANGUAGE),
    
    # Frameworks & Libraries
    "spring": ("Spring Boot", JobRequirementType.FRAMEWORK),
    "spring boot": ("Spring Boot", JobRequirementType.FRAMEWORK),
    "springboot": ("Spring Boot", JobRequirementType.FRAMEWORK),
    "fastapi": ("FastAPI", JobRequirementType.FRAMEWORK),
    "react": ("React", JobRequirementType.FRAMEWORK),
    "reactjs": ("React", JobRequirementType.FRAMEWORK),
    "react.js": ("React", JobRequirementType.FRAMEWORK),
    "next.js": ("Next.js", JobRequirementType.FRAMEWORK),
    "nextjs": ("Next.js", JobRequirementType.FRAMEWORK),
    "node.js": ("Node.js", JobRequirementType.FRAMEWORK),
    "nodejs": ("Node.js", JobRequirementType.FRAMEWORK),
    "express": ("Express", JobRequirementType.FRAMEWORK),
    "tailwind": ("Tailwind CSS", JobRequirementType.FRAMEWORK),
    "tailwind css": ("Tailwind CSS", JobRequirementType.FRAMEWORK),
    "shadcn": ("shadcn/ui", JobRequirementType.FRAMEWORK),
    "junit": ("JUnit", JobRequirementType.FRAMEWORK),
    "mockito": ("Mockito", JobRequirementType.FRAMEWORK),

    # Cloud & Infrastructure
    "gcp": ("GCP", JobRequirementType.CLOUD),
    "google cloud": ("GCP", JobRequirementType.CLOUD),
    "google cloud platform": ("GCP", JobRequirementType.CLOUD),
    "aws": ("AWS", JobRequirementType.CLOUD),
    "amazon web services": ("AWS", JobRequirementType.CLOUD),
    "azure": ("Azure", JobRequirementType.CLOUD),
    "terraform": ("Terraform", JobRequirementType.TOOL),
    "docker": ("Docker", JobRequirementType.TOOL),
    "kubernetes": ("Kubernetes", JobRequirementType.TOOL),
    "k8s": ("Kubernetes", JobRequirementType.TOOL),
    "gke": ("Kubernetes (GKE)", JobRequirementType.TOOL),
    "helm": ("Helm", JobRequirementType.TOOL),
    "argocd": ("ArgoCD", JobRequirementType.TOOL),
    "ansible": ("Ansible", JobRequirementType.TOOL),
    
    # Data & Messaging
    "apache beam": ("Apache Beam", JobRequirementType.FRAMEWORK),
    "beam": ("Apache Beam", JobRequirementType.FRAMEWORK),
    "dataflow": ("GCP Dataflow", JobRequirementType.CLOUD),
    "google cloud dataflow": ("GCP Dataflow", JobRequirementType.CLOUD),
    "bigquery": ("GCP BigQuery", JobRequirementType.DATABASE),
    "google bigquery": ("GCP BigQuery", JobRequirementType.DATABASE),
    "airflow": ("Apache Airflow", JobRequirementType.TOOL),
    "apache airflow": ("Apache Airflow", JobRequirementType.TOOL),
    "cloud composer": ("Cloud Composer", JobRequirementType.CLOUD),
    "pubsub": ("Google Cloud Pub/Sub", JobRequirementType.CLOUD),
    "pub/sub": ("Google Cloud Pub/Sub", JobRequirementType.CLOUD),
    "google cloud pub/sub": ("Google Cloud Pub/Sub", JobRequirementType.CLOUD),
    "kafka": ("Apache Kafka", JobRequirementType.TOOL),
    "apache kafka": ("Apache Kafka", JobRequirementType.TOOL),
    "parquet": ("Parquet", JobRequirementType.TOOL),

    # Databases & Storage
    "postgresql": ("PostgreSQL", JobRequirementType.DATABASE),
    "postgres": ("PostgreSQL", JobRequirementType.DATABASE),
    "redis": ("Redis", JobRequirementType.DATABASE),
    "supabase": ("Supabase", JobRequirementType.DATABASE),
    "mongodb": ("MongoDB", JobRequirementType.DATABASE),
    "gcs": ("Google Cloud Storage", JobRequirementType.CLOUD),
    "google cloud storage": ("Google Cloud Storage", JobRequirementType.CLOUD),
    "s3": ("AWS S3", JobRequirementType.CLOUD),

    # CI/CD & Security & Observability
    "jenkins": ("Jenkins", JobRequirementType.TOOL),
    "sonarqube": ("SonarQube", JobRequirementType.TOOL),
    "checkmarx": ("Checkmarx", JobRequirementType.TOOL),
    "nexus": ("Nexus", JobRequirementType.TOOL),
    "devsecops": ("DevSecOps", JobRequirementType.CONCEPT),
    "ci/cd": ("CI/CD", JobRequirementType.CONCEPT),
    "iac": ("Infrastructure as Code", JobRequirementType.CONCEPT),
    "prometheus": ("Prometheus", JobRequirementType.TOOL),
    "grafana": ("Grafana", JobRequirementType.TOOL),
    "cloud monitoring": ("GCP Cloud Monitoring", JobRequirementType.CLOUD),
    
    # AI & Architecture
    "mcp": ("Model Context Protocol (MCP)", JobRequirementType.TOOL),
    "model context protocol": ("Model Context Protocol (MCP)", JobRequirementType.TOOL),
    "claude api": ("Claude API", JobRequirementType.TOOL),
    "llm": ("LLMs", JobRequirementType.CONCEPT),
    "microservices": ("Microservices", JobRequirementType.CONCEPT),
    "distributed systems": ("Distributed Systems", JobRequirementType.CONCEPT),
    "rest api": ("REST APIs", JobRequirementType.CONCEPT),
    "rest apis": ("REST APIs", JobRequirementType.CONCEPT),
    "restful": ("REST APIs", JobRequirementType.CONCEPT),
    "etl": ("ETL Pipelines", JobRequirementType.CONCEPT),
}

THEME_DEFINITIONS: Dict[str, Set[str]] = {
    "Java/Spring backend development": {
        "java", "spring", "spring boot", "springboot", "backend", "jvm", "hibernate", "maven", "gradle",
    },
    "GCP/data platform engineering": {
        "gcp", "google cloud", "bigquery", "dataflow", "cloud composer", "pub/sub", "pubsub",
        "data platform", "beam", "apache beam", "dataproc", "gcs", "google cloud storage",
    },
    "distributed systems/payment processing": {
        "distributed systems", "payment", "payments", "fintech", "transaction", "transactions",
        "concurrency", "high-throughput", "low-latency", "messaging", "event-driven",
    },
    "infrastructure/DevOps": {
        "terraform", "kubernetes", "k8s", "docker", "helm", "ci/cd", "jenkins",
        "devops", "iac", "infrastructure as code", "ansible", "argocd",
    },
    "reliability/observability": {
        "observability", "monitoring", "cloud monitoring", "prometheus", "grafana",
        "logging", "alerting", "sre", "reliability", "mttr",
    },
    "data streaming/ETL pipelines": {
        "streaming", "stream processing", "etl", "data pipeline", "airflow", "apache airflow",
        "kafka", "apache kafka", "parquet", "batch processing",
    },
    "microservices/API engineering": {
        "microservices", "rest api", "rest apis", "restful", "grpc", "api design", "fastapi",
    },
    "cloud architecture/security": {
        "cloud architecture", "devsecops", "sonarqube", "checkmarx", "nexus", "iam", "cloud security",
    },
    "full-stack/web development": {
        "react", "next.js", "typescript", "javascript", "tailwind", "frontend", "full stack", "ui",
    },
}


def derive_dominant_themes(analysis: JobAnalysis) -> List[str]:
    """
    Deterministically derive the top 2-3 dominant technical themes from structured JobAnalysis.
    Weights job title, required skills, preferred skills, technology categories, domain keywords,
    and responsibilities to score canonical technical themes.

    If no meaningful matching theme is found, returns an empty list rather than assigning an
    unrelated technical theme.
    """
    title_lower = (analysis.job_title or "").lower()
    scores: Dict[str, float] = {theme: 0.0 for theme in THEME_DEFINITIONS}

    # Collect combined JD evidence text to verify genuine text support
    all_techs = (
        analysis.programming_languages
        + analysis.frameworks
        + analysis.cloud_technologies
        + analysis.databases
        + analysis.infrastructure_technologies
    )
    jd_evidence_text = " ".join(
        [analysis.job_title or ""]
        + [req.name + " " + req.normalized_name for req in analysis.required_skills + analysis.preferred_skills]
        + all_techs
        + analysis.domain_keywords
        + analysis.responsibilities
        + analysis.ats_keywords
    ).lower()

    for theme, keywords in THEME_DEFINITIONS.items():
        # "Java/Spring backend development" requires genuine Java/Spring presence
        if theme == "Java/Spring backend development":
            java_spring_signals = {"java", "spring", "spring boot", "springboot", "jvm", "hibernate", "maven", "gradle"}
            if not any(sig in jd_evidence_text for sig in java_spring_signals):
                continue

        # 1. Job Title signal (primary indicator)
        for kw in keywords:
            if kw in title_lower:
                scores[theme] += 6.0

        # 2. Required skills (mandatory technical stack)
        for req in analysis.required_skills:
            req_name = req.normalized_name.lower()
            for kw in keywords:
                if kw == req_name or kw in req_name:
                    scores[theme] += 3.5
                    if req.years_required:
                        scores[theme] += 1.0

        # 3. Preferred skills
        for pref in analysis.preferred_skills:
            pref_name = pref.normalized_name.lower()
            for kw in keywords:
                if kw == pref_name or kw in pref_name:
                    scores[theme] += 1.5

        # 4. Categorized technologies
        for tech in all_techs:
            tech_lower = tech.lower()
            for kw in keywords:
                if kw == tech_lower or kw in tech_lower:
                    scores[theme] += 1.0

        # 5. Domain keywords
        for dom in analysis.domain_keywords:
            dom_lower = dom.lower()
            for kw in keywords:
                if kw in dom_lower:
                    scores[theme] += 1.5

        # 6. Key responsibilities
        for resp in analysis.responsibilities:
            resp_lower = resp.lower()
            for kw in keywords:
                if kw in resp_lower:
                    scores[theme] += 0.5

    # Filter meaningful positive scores (score >= 2.5 ensures at least one required skill,
    # title keyword, or multiple confirmed technical signals)
    meaningful_themes = [
        (theme, score) for theme, score in scores.items() if score >= 2.5
    ]
    meaningful_themes.sort(key=lambda item: (-item[1], item[0]))

    if meaningful_themes:
        # Return top 2 or 3 themes
        selected = [t for t, _ in meaningful_themes[:3]]
        return selected

    # Useful title heuristics ONLY if genuinely supported by the JD text
    if any(k in title_lower for k in ["data", "etl", "analytics", "beam"]):
        if any(k in jd_evidence_text for k in ["data platform", "gcp", "bigquery", "dataflow", "beam", "streaming", "etl", "pipeline", "warehouse", "airflow", "pub/sub", "spark"]):
            return ["GCP/data platform engineering", "data streaming/ETL pipelines"]
    if any(k in title_lower for k in ["devops", "cloud", "infra", "sre", "platform"]):
        if any(k in jd_evidence_text for k in ["terraform", "kubernetes", "k8s", "docker", "ci/cd", "jenkins", "ansible", "cloud", "aws", "gcp", "sre", "observability", "infrastructure"]):
            return ["infrastructure/DevOps", "reliability/observability"]

    # When no meaningful matching theme is found, return empty list rather than assigning an unrelated theme
    return []


class JobDescriptionAnalyzer:
    """Extracts structured requirements, technology keywords, and seniority metadata from JDs."""

    def analyze(
        self,
        text: str,
        title_override: Optional[str] = None,
        company_override: Optional[str] = None,
    ) -> JobAnalysis:
        """Parse raw job description text into structured JobAnalysis model."""
        clean_text = text.strip()
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

        # 1. Infer Job Title & Company
        job_title = title_override or self._extract_title(lines, clean_text)
        company = self._clean_company_name(company_override) or self._extract_company(lines, clean_text)
        location = self._extract_location(lines, clean_text)
        seniority = self._extract_seniority(job_title, clean_text)
        years_req = self._extract_years_experience(clean_text)

        # 2. Partition into Required vs Preferred sections
        required_text, preferred_text = self._partition_sections(clean_text)

        # 3. Extract Technologies & Map to Canonical Normalized Names
        required_skills = self._extract_skills(required_text, is_required=True)
        preferred_skills = self._extract_skills(preferred_text, is_required=False)

        # Ensure no duplicates between required and preferred
        req_norm_names = {s.normalized_name for s in required_skills}
        preferred_skills = [s for s in preferred_skills if s.normalized_name not in req_norm_names]

        # 4. Categorize skills
        all_skills = required_skills + preferred_skills
        languages = [s.normalized_name for s in all_skills if s.type == JobRequirementType.LANGUAGE]
        frameworks = [s.normalized_name for s in all_skills if s.type == JobRequirementType.FRAMEWORK]
        clouds = [s.normalized_name for s in all_skills if s.type == JobRequirementType.CLOUD]
        databases = [s.normalized_name for s in all_skills if s.type == JobRequirementType.DATABASE]
        infra = [s.normalized_name for s in all_skills if s.type == JobRequirementType.TOOL]
        ats = sorted(list({s.normalized_name for s in all_skills}))

        analysis = JobAnalysis(
            job_title=job_title,
            company=company,
            location=location,
            seniority_level=seniority,
            years_experience_requirement=years_req,
            required_skills=required_skills,
            preferred_skills=preferred_skills,
            programming_languages=sorted(list(set(languages))),
            frameworks=sorted(list(set(frameworks))),
            cloud_technologies=sorted(list(set(clouds))),
            databases=sorted(list(set(databases))),
            infrastructure_technologies=sorted(list(set(infra))),
            domain_keywords=self._extract_domains(clean_text),
            responsibilities=self._extract_bullet_points(clean_text),
            education_requirements=self._extract_education(clean_text),
            certification_requirements=[],
            ats_keywords=ats,
        )
        analysis.dominant_themes = derive_dominant_themes(analysis)
        return analysis

    def _extract_title(self, lines: List[str], text: str) -> str:
        """Heuristic title extraction."""
        # Look for first line or "Job Title: ..."
        for line in lines[:5]:
            if line.lower().startswith("job title:") or line.lower().startswith("role:"):
                return line.split(":", 1)[1].strip()

        # Look for common software engineering titles
        title_patterns = [
            r"\b(Senior\s+Backend\s+Engineer)\b",
            r"\b(Backend\s+Software\s+Engineer)\b",
            r"\b(Cloud\s+&\s+DevOps\s+Engineer)\b",
            r"\b(Site\s+Reliability\s+Engineer)\b",
            r"\b(Data\s+Engineer)\b",
            r"\b(Full\s+Stack\s+Engineer)\b",
            r"\b(Software\s+Engineer)\b",
            r"\b(DevOps\s+Engineer)\b",
        ]
        for pat in title_patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1)

        return lines[0] if lines else "Role unavailable"

    @staticmethod
    def _clean_company_name(name: Optional[str]) -> Optional[str]:
        """Sanitize and normalize company name, stripping newlines, pronouns, and extraneous punctuation."""
        if not name:
            return None
        lines = [line.strip() for line in name.split("\n") if line.strip()]
        if not lines:
            return None
        first_line = lines[0]
        first_line = re.sub(r"[\.,;:!\?].*$", "", first_line)
        first_line = re.sub(r"\s+\b(We|You|Our|The|In|On|At|For|To|Is|Are|And)\b.*$", "", first_line, flags=re.IGNORECASE)
        first_line = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", first_line)
        cleaned = re.sub(r"\s+", " ", first_line).strip()
        return cleaned or None

    def _extract_company(self, lines: List[str], text: str) -> Optional[str]:
        """Heuristic company extraction."""
        for line in lines[:8]:
            if line.lower().startswith("company:"):
                extracted = self._clean_company_name(line.split(":", 1)[1])
                if extracted:
                    return extracted

        for line in lines[:5]:
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                for part in parts:
                    if part and not any(loc in part.lower() for loc in ["remote", "hybrid", "onsite", "full-time", "contract", "engineer", "developer"]):
                        if len(part.split()) <= 4 and re.match(r"^[A-Z][A-Za-z0-9 &.,'-]+$", part):
                            extracted = self._clean_company_name(part)
                            if extracted:
                                return extracted

        for line in lines[:15]:
            m = re.search(r"\b(?:at|with)\s+([A-Z][A-Za-z0-9 &.,'-]{1,40})\b", line)
            if m:
                extracted = self._clean_company_name(m.group(1))
                if extracted:
                    return extracted

        return None

    def _extract_location(self, lines: List[str], text: str) -> Optional[str]:
        """Heuristic location extraction."""
        for line in lines[:8]:
            if line.lower().startswith("location:"):
                return line.split(":", 1)[1].strip()
        if re.search(r"\bremote\b", text, re.IGNORECASE):
            return "Remote"
        if re.search(r"\bhybrid\b", text, re.IGNORECASE):
            return "Hybrid"
        return None

    def _extract_seniority(self, title: str, text: str) -> str:
        """Extract seniority level."""
        combined = f"{title} {text[:500]}".lower()
        if "lead" in combined or "staff" in combined or "principal" in combined:
            return "Lead/Staff"
        if "senior" in combined or "sr." in combined or "sr " in combined:
            return "Senior"
        if "junior" in combined or "jr." in combined or "associate" in combined:
            return "Junior"
        return "Mid-Level"

    def _extract_years_experience(self, text: str) -> Optional[float]:
        """Extract required years of experience."""
        # e.g. "3+ years", "5-7 years", "at least 4 years"
        m = re.search(r"(\d+)(?:\+|\s*-\s*\d+)?\s*(?:years|yrs)\s+(?:of\s+)?(?:[^.\n]{0,60}?)?(?:experience|exp)", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None

    def _partition_sections(self, text: str) -> Tuple[str, str]:
        """Split JD into required vs preferred text sections."""
        preferred_markers = [
            "nice to have", "preferred qualifications", "bonus points",
            "plus if you have", "good to have", "desired skills"
        ]
        text_lower = text.lower()
        pref_start_idx = -1
        for marker in preferred_markers:
            idx = text_lower.find(marker)
            if idx != -1 and (pref_start_idx == -1 or idx < pref_start_idx):
                pref_start_idx = idx

        if pref_start_idx != -1:
            return text[:pref_start_idx], text[pref_start_idx:]
        return text, ""

    def _extract_skills(self, section_text: str, is_required: bool) -> List[JobRequirement]:
        """Scan text against tech dictionary and return extracted JobRequirements."""
        found_skills: Dict[str, JobRequirement] = {}
        section_lower = section_text.lower()

        for term, (canon_name, req_type) in TECH_DICTIONARY.items():
            # Match on word boundary
            escaped_term = re.escape(term)
            pattern = rf"(?<!\w){escaped_term}(?!\w)"
            match = re.search(pattern, section_lower)
            if match:
                if canon_name not in found_skills:
                    found_skills[canon_name] = JobRequirement(
                        name=term,
                        type=req_type,
                        normalized_name=canon_name,
                        raw_text=section_text[max(0, match.start() - 20):min(len(section_text), match.end() + 20)],
                        is_required=is_required,
                    )

        return list(found_skills.values())

    def _extract_domains(self, text: str) -> List[str]:
        """Extract domain keywords."""
        domains = []
        domain_map = {
            "fintech": "Fintech",
            "payment": "Payments",
            "banking": "Banking",
            "e-commerce": "E-Commerce",
            "procurement": "Procurement",
            "healthcare": "Healthcare",
        }
        for kw, domain_name in domain_map.items():
            if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
                domains.append(domain_name)
        return list(set(domains))

    def _extract_bullet_points(self, text: str) -> List[str]:
        """Extract raw responsibility bullet points."""
        bullets = []
        for line in text.split("\n"):
            line_s = line.strip()
            if line_s.startswith("•") or line_s.startswith("-") or line_s.startswith("*"):
                cleaned = line_s.lstrip("•-* ").strip()
                if len(cleaned) > 20:
                    bullets.append(cleaned)
        return bullets[:10]

    def _extract_education(self, text: str) -> List[str]:
        """Extract degree mentions."""
        edu = []
        if re.search(r"\b(?:bachelor|b\.s\.|b\.tech|bs|computer science degree)\b", text, re.IGNORECASE):
            edu.append("Bachelor's Degree in Computer Science or related field")
        return edu

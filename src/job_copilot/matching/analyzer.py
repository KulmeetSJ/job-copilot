"""Comprehensive Job Description Analyzer and Ingestion Engine."""

import hashlib
import re
from typing import Dict, List, Optional, Set, Tuple

from job_copilot.domain.enums import EmploymentType, RemoteStatus
from job_copilot.matching.models import (
    AnalyzedJob,
    JobSeniority,
    RequirementImportance,
    TechnicalRequirement,
    WorkAuthorizationRequirement,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Canonical technology dictionary: alias -> (Canonical Name, Category)
CANONICAL_TECH_MAP: Dict[str, Tuple[str, str]] = {
    # Languages
    "java": ("Java", "Language"),
    "python": ("Python", "Language"),
    "sql": ("SQL", "Language"),
    "javascript": ("JavaScript", "Language"),
    "typescript": ("TypeScript", "Language"),
    "groovy": ("Groovy", "Language"),
    "go": ("Go", "Language"),
    "golang": ("Go", "Language"),
    "c++": ("C++", "Language"),
    "rust": ("Rust", "Language"),
    "scala": ("Scala", "Language"),
    "kotlin": ("Kotlin", "Language"),
    
    # Frameworks & Backend
    "spring": ("Spring Boot", "Framework"),
    "spring boot": ("Spring Boot", "Framework"),
    "springboot": ("Spring Boot", "Framework"),
    "fastapi": ("FastAPI", "Framework"),
    "react": ("React", "Framework"),
    "reactjs": ("React", "Framework"),
    "react.js": ("React", "Framework"),
    "next.js": ("Next.js", "Framework"),
    "nextjs": ("Next.js", "Framework"),
    "node.js": ("Node.js", "Framework"),
    "nodejs": ("Node.js", "Framework"),
    "express": ("Express", "Framework"),
    "tailwind": ("Tailwind CSS", "Framework"),
    "tailwind css": ("Tailwind CSS", "Framework"),
    "shadcn": ("shadcn/ui", "Framework"),
    "junit": ("JUnit", "Framework"),
    "mockito": ("Mockito", "Framework"),
    "grpc": ("gRPC", "Framework"),
    "rest": ("REST APIs", "Concept"),
    "rest api": ("REST APIs", "Concept"),
    "rest apis": ("REST APIs", "Concept"),
    "microservices": ("Microservices", "Concept"),
    "distributed systems": ("Distributed Systems", "Concept"),

    # Cloud Platforms & Infrastructure
    "gcp": ("GCP", "Cloud"),
    "google cloud": ("GCP", "Cloud"),
    "google cloud platform": ("GCP", "Cloud"),
    "aws": ("AWS", "Cloud"),
    "amazon web services": ("AWS", "Cloud"),
    "azure": ("Azure", "Cloud"),
    "terraform": ("Terraform", "Tool"),
    "docker": ("Docker", "Tool"),
    "kubernetes": ("Kubernetes", "Tool"),
    "k8s": ("Kubernetes", "Tool"),
    "gke": ("Google Kubernetes Engine (GKE)", "Cloud"),
    "google kubernetes engine": ("Google Kubernetes Engine (GKE)", "Cloud"),
    "helm": ("Helm Charts", "Tool"),
    "helm charts": ("Helm Charts", "Tool"),
    "argocd": ("ArgoCD", "Tool"),
    "ansible": ("Ansible", "Tool"),
    "ci/cd": ("CI/CD", "Concept"),
    "jenkins": ("Jenkins", "Tool"),
    "github actions": ("GitHub Actions", "Tool"),
    "gitlab ci": ("GitLab CI", "Tool"),

    # Data Engineering & Messaging
    "apache beam": ("Apache Beam", "Framework"),
    "beam": ("Apache Beam", "Framework"),
    "dataflow": ("GCP Dataflow", "Cloud"),
    "gcp dataflow": ("GCP Dataflow", "Cloud"),
    "bigquery": ("GCP BigQuery", "Database"),
    "gcp bigquery": ("GCP BigQuery", "Database"),
    "airflow": ("Apache Airflow", "Tool"),
    "apache airflow": ("Apache Airflow", "Tool"),
    "cloud composer": ("Cloud Composer", "Cloud"),
    "pubsub": ("Google Cloud Pub/Sub", "Cloud"),
    "pub/sub": ("Google Cloud Pub/Sub", "Cloud"),
    "google cloud pub/sub": ("Google Cloud Pub/Sub", "Cloud"),
    "kafka": ("Apache Kafka", "Tool"),
    "apache kafka": ("Apache Kafka", "Tool"),
    "parquet": ("Parquet", "Tool"),
    "spark": ("Apache Spark", "Framework"),
    "apache spark": ("Apache Spark", "Framework"),
    "etl": ("ETL Pipelines", "Concept"),
    "etl pipelines": ("ETL Pipelines", "Concept"),

    # Databases & Caching
    "postgresql": ("PostgreSQL", "Database"),
    "postgres": ("PostgreSQL", "Database"),
    "redis": ("Redis", "Database"),
    "supabase": ("Supabase", "Database"),
    "mongodb": ("MongoDB", "Database"),
    "gcs": ("Google Cloud Storage", "Cloud"),
    "google cloud storage": ("Google Cloud Storage", "Cloud"),

    # Security & Observability
    "sonarqube": ("SonarQube", "Tool"),
    "checkmarx": ("Checkmarx", "Tool"),
    "nexus": ("Nexus", "Tool"),
    "devsecops": ("DevSecOps", "Concept"),
    "prometheus": ("Prometheus", "Tool"),
    "grafana": ("Grafana", "Tool"),
    "cloud monitoring": ("GCP Cloud Monitoring", "Cloud"),
    "gcp cloud monitoring": ("GCP Cloud Monitoring", "Cloud"),

    # AI & Agentic Tooling
    "mcp": ("Model Context Protocol (MCP)", "Tool"),
    "model context protocol": ("Model Context Protocol (MCP)", "Tool"),
    "claude api": ("Claude API", "Tool"),
    "google adk": ("Google ADK", "Tool"),
    "adk": ("Google ADK", "Tool"),
    "llm": ("LLMs", "Concept"),
    "paymentsai": ("PaymentsAI", "Project"),
    "orchestration": ("Orchestration Service", "Concept"),
    "orchestration service": ("Orchestration Service", "Concept"),
}


class JobAnalyzer:
    """Deterministic analyzer extracting structured metadata, requirements, and domain signals from JDs."""

    def analyze(
        self,
        raw_text: str,
        source: str = "text_input",
        source_url: Optional[str] = None,
        company_override: Optional[str] = None,
        title_override: Optional[str] = None,
    ) -> AnalyzedJob:
        """Parse raw job description into strongly typed AnalyzedJob model."""
        clean_text = raw_text.strip()
        lines = [line.strip() for line in clean_text.split("\n") if line.strip()]

        from job_copilot.ingestion.metadata_extractor import JobMetadataExtractor

        company = JobMetadataExtractor.clean_company_name(company_override) or self._extract_company(lines, clean_text) or "Company unavailable"
        title = title_override or self._extract_title(lines, clean_text) or "Role unavailable"
        location = self._extract_location(lines, clean_text)
        remote_policy = self._extract_remote_policy(clean_text)
        seniority = self._extract_seniority(title, clean_text)
        years_exp = self._extract_years_experience(clean_text)
        work_auth = self._extract_work_authorization(clean_text)

        # Partition text into must-have vs preferred
        must_have_text, preferred_text = self._partition_sections(clean_text)

        # Extract technical requirements
        tech_reqs = self._extract_technical_requirements(must_have_text, preferred_text)

        # Extract responsibilities & domain
        responsibilities = self._extract_responsibilities(clean_text)
        domains = self._extract_domains(clean_text)
        education = self._extract_education(clean_text)

        # ATS Keywords
        ats_keywords = sorted(list({r.normalized_name for r in tech_reqs}))

        # Generate stable deterministic job_id
        job_id = self._generate_job_id(company, title, clean_text)

        return AnalyzedJob(
            job_id=job_id,
            source=source,
            source_url=source_url,
            company=company,
            title=title,
            location=location,
            remote_policy=remote_policy,
            employment_type=EmploymentType.FULL_TIME,
            seniority=seniority,
            years_experience_required=years_exp,
            description=clean_text,
            technical_requirements=tech_reqs,
            responsibilities=responsibilities,
            domain_requirements=domains,
            certifications=[],
            education_requirements=education,
            work_authorization=work_auth,
            ats_keywords=ats_keywords,
        )

    def _generate_job_id(self, company: str, title: str, text: str) -> str:
        """Create clean deterministic identifier e.g. stripe-senior-backend-java-a1b2c3."""
        c_slug = re.sub(r'[^a-zA-Z0-9]+', '-', company.lower()).strip('-') or "company-unavailable"
        t_slug = re.sub(r'[^a-zA-Z0-9]+', '-', title.lower()).strip('-') or "role-unavailable"
        text_hash = hashlib.sha256(text.encode('utf-8')).hexdigest()[:6]
        return f"{c_slug}-{t_slug}-{text_hash}"

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

    def _extract_title(self, lines: List[str], text: str) -> Optional[str]:
        for line in lines[:6]:
            if line.lower().startswith("job title:") or line.lower().startswith("role:") or line.lower().startswith("title:"):
                return line.split(":", 1)[1].strip()
        patterns = [
            r"\b(Senior\s+Backend\s+Engineer(?:\s+-\s+Java)?)\b",
            r"\b(Senior\s+Backend\s+Java\s+Engineer)\b",
            r"\b(Backend\s+Software\s+Engineer)\b",
            r"\b(Cloud\s+(?:&|and)\s+DevOps\s+Engineer)\b",
            r"\b(Principal\s+Cloud\s+DevOps\s+Engineer)\b",
            r"\b(Senior\s+Kubernetes\s+Platform\s+Engineer)\b",
            r"\b(Lead\s+Data\s+Engineer)\b",
            r"\b(Data\s+Engineer)\b",
            r"\b(Full\s+Stack\s+Engineer)\b",
            r"\b(Software\s+Engineer)\b",
            r"\b(DevOps\s+Engineer)\b",
            r"\b(Site\s+Reliability\s+Engineer)\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return lines[0] if lines else "Role unavailable"

    def _extract_location(self, lines: List[str], text: str) -> Optional[str]:
        for line in lines[:8]:
            if line.lower().startswith("location:"):
                return line.split(":", 1)[1].strip()
        if re.search(r"\bremote\b", text, re.IGNORECASE):
            return "Remote"
        if re.search(r"\bhybrid\b", text, re.IGNORECASE):
            return "Hybrid"
        return None

    def _extract_remote_policy(self, text: str) -> RemoteStatus:
        if re.search(r"\bremote\b", text, re.IGNORECASE):
            return RemoteStatus.REMOTE
        if re.search(r"\bhybrid\b", text, re.IGNORECASE):
            return RemoteStatus.HYBRID
        if re.search(r"\bon-?site\b|\bin-office\b", text, re.IGNORECASE):
            return RemoteStatus.ONSITE
        return RemoteStatus.UNKNOWN

    def _extract_seniority(self, title: str, text: str) -> JobSeniority:
        comb = f"{title} {text[:400]}".lower()
        if "intern" in comb or "internship" in comb:
            return JobSeniority.INTERN
        if "principal" in comb:
            return JobSeniority.PRINCIPAL
        if "staff" in comb:
            return JobSeniority.STAFF
        if "lead" in comb:
            return JobSeniority.LEAD
        if "senior" in comb or "sr." in comb or "sr " in comb:
            return JobSeniority.SENIOR
        if "junior" in comb or "jr." in comb or "entry" in comb or "associate" in comb:
            return JobSeniority.JUNIOR
        return JobSeniority.MID_LEVEL

    def _extract_years_experience(self, text: str) -> Optional[float]:
        m = re.search(r"(\d+)(?:\+|\s*-\s*\d+)?\s*(?:years|yrs)\s+(?:of\s+)?(?:[^.\n]{0,60}?)?(?:experience|exp)", text, re.IGNORECASE)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass
        return None

    def _extract_work_authorization(self, text: str) -> WorkAuthorizationRequirement:
        text_l = text.lower()
        if "no sponsorship" in text_l or "sponsorship not available" in text_l or "must be authorized to work without sponsorship" in text_l:
            return WorkAuthorizationRequirement.REQUIRED
        if "sponsorship available" in text_l or "visa sponsorship provided" in text_l or "will sponsor" in text_l:
            return WorkAuthorizationRequirement.SPONSORSHIP_AVAILABLE
        if "us citizen only" in text_l or "security clearance" in text_l:
            return WorkAuthorizationRequirement.CITIZEN_ONLY
        return WorkAuthorizationRequirement.SPONSORSHIP_UNKNOWN

    def _partition_sections(self, text: str) -> Tuple[str, str]:
        preferred_markers = [
            "nice to have", "preferred qualifications", "bonus points",
            "plus if you have", "good to have", "desired skills", "preferred requirements"
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

    def _extract_technical_requirements(self, must_have_text: str, pref_text: str) -> List[TechnicalRequirement]:
        reqs: Dict[str, TechnicalRequirement] = {}

        # 1. Process Must-have Section
        must_lower = must_have_text.lower()
        for alias, (canonical_name, category) in CANONICAL_TECH_MAP.items():
            pat = rf"(?<!\w){re.escape(alias)}(?!\w)"
            m = re.search(pat, must_lower)
            if m:
                # Look for associated years
                snippet = must_have_text[max(0, m.start() - 30):min(len(must_have_text), m.end() + 30)]
                years = None
                ym = re.search(r"(\d+)(?:\+|\s*-\s*\d+)?\s*(?:years|yrs)", snippet, re.IGNORECASE)
                if ym:
                    try:
                        years = float(ym.group(1))
                    except ValueError:
                        pass

                importance = RequirementImportance.CRITICAL if ("must" in snippet.lower() or "required" in snippet.lower()) else RequirementImportance.HIGH
                
                reqs[canonical_name] = TechnicalRequirement(
                    name=alias,
                    normalized_name=canonical_name,
                    category=category,
                    importance=importance,
                    is_must_have=True,
                    years_required=years,
                    raw_snippet=snippet.strip(),
                )

        # 2. Process Preferred Section
        pref_lower = pref_text.lower()
        for alias, (canonical_name, category) in CANONICAL_TECH_MAP.items():
            if canonical_name in reqs:
                continue
            pat = rf"(?<!\w){re.escape(alias)}(?!\w)"
            m = re.search(pat, pref_lower)
            if m:
                snippet = pref_text[max(0, m.start() - 30):min(len(pref_text), m.end() + 30)]
                reqs[canonical_name] = TechnicalRequirement(
                    name=alias,
                    normalized_name=canonical_name,
                    category=category,
                    importance=RequirementImportance.LOW,
                    is_must_have=False,
                    years_required=None,
                    raw_snippet=snippet.strip(),
                )

        return list(reqs.values())

    def _extract_responsibilities(self, text: str) -> List[str]:
        responsibilities = []
        resp_keywords = [
            "backend development", "api development", "distributed systems",
            "streaming data pipelines", "cloud infrastructure", "ci/cd automation",
            "observability and monitoring", "orchestration services", "platform setup",
            "frontend development", "ai and agentic tooling"
        ]
        text_l = text.lower()
        for kw in resp_keywords:
            if kw in text_l:
                responsibilities.append(kw.title())
        return responsibilities

    def _extract_domains(self, text: str) -> List[str]:
        domains = []
        domain_map = {
            "fintech": "Fintech",
            "payment": "Payments",
            "banking": "Banking",
            "healthcare": "Healthcare",
            "e-commerce": "E-Commerce",
            "saas": "SaaS",
        }
        for kw, domain in domain_map.items():
            if re.search(rf"\b{re.escape(kw)}\b", text, re.IGNORECASE):
                domains.append(domain)
        return sorted(list(set(domains)))

    def _extract_education(self, text: str) -> List[str]:
        edu = []
        if re.search(r"\b(?:bachelor|b\.s\.|b\.tech|bs|computer science degree)\b", text, re.IGNORECASE):
            edu.append("Bachelor's Degree in Computer Science or related field")
        return edu

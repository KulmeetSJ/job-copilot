"""Cover Letter Generator and Deterministic Truth Validator."""

from datetime import datetime
import re
from typing import List, Tuple
from job_copilot.application.models import (
    ClaimProvenance,
    CoverLetter,
    CoverLetterValidation,
)
from job_copilot.matching.models import JobAssessment
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class CoverLetterEngine:
    """
    Generates targeted, factual cover letters aligned with the candidate's canonical background
    and validates them against strict truth invariants.
    """

    def generate_cover_letter(
        self,
        assessment: JobAssessment,
        profile: CandidateProfile,
    ) -> CoverLetter:
        """Compose a tailored cover letter and validate its factual claims."""
        job = assessment.job
        company = job.company
        title = job.title
        strategy = assessment.recommended_strategy

        text, provenance = self._compose_letter(company, title, strategy, assessment)
        word_count = len(re.findall(r"\b\w+\b", text))

        # Perform truth-safety validation
        validation = self.validate_cover_letter(text, provenance, company, title)

        return CoverLetter(
            job_id=job.job_id,
            company=company,
            title=title,
            letter_text=text,
            word_count=word_count,
            provenance=provenance,
            validation=validation,
            created_at=datetime.utcnow(),
        )

    def validate_cover_letter(
        self,
        letter_text: str,
        provenance: List[ClaimProvenance],
        company: str,
        title: str,
    ) -> CoverLetterValidation:
        """Deterministically validate cover letter against truth safety invariants."""
        errors: List[str] = []
        warnings: List[str] = []
        text_lower = letter_text.lower()

        # Rule 1: No unsupported cloud/infra claims
        if "aws" in text_lower and not any("aws" in p.claim_text.lower() for p in provenance):
            errors.append("Cover letter contains unverified claim regarding AWS experience.")

        if "5+ years" in text_lower or "10+ years" in text_lower:
            errors.append("Cover letter claims excessive years of experience not supported by ~2 yrs career history.")

        # Rule 2: Exposure must not become production administration
        if "production kubernetes cluster administration" in text_lower:
            errors.append("GKE/Helm hands-on exposure promoted to enterprise production Kubernetes administration.")

        # Rule 3: Benchmark isolation
        if "100k+ rps production" in text_lower or "100,000 rps production" in text_lower:
            errors.append("100K+ RPS benchmark incorrectly asserted as HSBC production traffic.")

        # Rule 4: Word count check
        words = len(re.findall(r"\b\w+\b", letter_text))
        if words < 180:
            warnings.append(f"Cover letter is relatively short ({words} words).")
        elif words > 450:
            warnings.append(f"Cover letter exceeds recommended brevity ({words} words).")

        # Rule 5: Context check
        if company.lower() not in text_lower and "your team" not in text_lower:
            warnings.append(f"Company name '{company}' not explicitly referenced in cover letter.")

        is_valid = len(errors) == 0

        return CoverLetterValidation(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            claims_checked=len(provenance),
            provenance=provenance,
        )

    def _compose_letter(
        self,
        company: str,
        title: str,
        strategy: str,
        assessment: JobAssessment,
    ) -> Tuple[str, List[ClaimProvenance]]:
        """Synthesize tailored 4-paragraph cover letter based on strategy focus."""
        provenance: List[ClaimProvenance] = []

        # Opening
        opening = (
            f"Dear Hiring Team at {company},\n\n"
            f"I am writing to express my strong interest in the {title} role at {company}. "
            f"With over two years of professional software engineering experience at HSBC building cloud-native "
            f"backend services, streaming data pipelines, and distributed APIs on Google Cloud Platform, I am eager "
            f"to contribute to {company}'s ongoing engineering initiatives."
        )
        provenance.append(
            ClaimProvenance(
                claim_text="Over two years professional software engineering experience at HSBC on GCP",
                source_type="PROFESSIONAL",
                source_ref="EXP-HSBC-BEAM-001",
                context="HSBC employment baseline",
                metric_type="PRODUCTION",
            )
        )

        # Body Paragraph 1: Professional Experience
        if strategy == "data_engineering":
            body1 = (
                "At HSBC, I specialized in data platform engineering, developing scalable batch and real-time streaming "
                "data pipelines using Apache Beam and GCP Dataflow. I designed high-capacity analytical schemas in BigQuery, "
                "processed multi-terabyte transactional feeds in Parquet format, and automated complex workflow orchestration "
                "with Cloud Composer (Airflow) DAGs."
            )
            provenance.append(
                ClaimProvenance(
                    claim_text="Developed streaming pipelines with Apache Beam, Dataflow, and BigQuery at HSBC",
                    source_type="PROFESSIONAL",
                    source_ref="EXP-HSBC-BEAM-001",
                    context="HSBC Streaming Data Platform",
                    metric_type="PRODUCTION",
                )
            )
        elif strategy in ("cloud_devops", "sre_devops"):
            body1 = (
                "In my current role at HSBC, I design and maintain reproducible cloud infrastructure utilizing Terraform (IaC) "
                "and manage automated CI/CD release pipelines with Jenkins. I established observability dashboards and alerting "
                "with GCP Cloud Monitoring and integrated automated code quality and security scanning with SonarQube and Checkmarx."
            )
            provenance.append(
                ClaimProvenance(
                    claim_text="Terraform IaC, Jenkins CI/CD, and GCP Cloud Monitoring at HSBC",
                    source_type="PROFESSIONAL",
                    source_ref="EXP-HSBC-TF-001",
                    context="HSBC Cloud Infrastructure & CI/CD",
                    metric_type="PRODUCTION",
                )
            )
        elif strategy == "full_stack":
            body1 = (
                "At HSBC, I contributed to the PaymentsAI platform, developing responsive web interfaces and resilient backend "
                "microservices in Java and Python. In addition, I have engineered full-stack applications with React, Next.js, "
                "TypeScript, and Supabase, ensuring seamless user experiences and robust database architectures."
            )
            provenance.append(
                ClaimProvenance(
                    claim_text="PaymentsAI platform development and full-stack web applications",
                    source_type="PROFESSIONAL",
                    source_ref="EXP-HSBC-PAYMENTS-AI-001",
                    context="HSBC PaymentsAI and web projects",
                    metric_type="PRODUCTION",
                )
            )
        else:  # backend_java default
            body1 = (
                "At HSBC, I engineered high-throughput backend services and RESTful microservices in Java and Spring Boot. "
                "I designed distributed transactional components on Google Cloud Platform, implemented event-driven messaging "
                "via Google Cloud Pub/Sub, and optimized database interactions with PostgreSQL."
            )
            provenance.append(
                ClaimProvenance(
                    claim_text="Java/Spring Boot backend microservices and event-driven architecture at HSBC",
                    source_type="PROFESSIONAL",
                    source_ref="EXP-HSBC-BEAM-001",
                    context="HSBC Java & Cloud microservices",
                    metric_type="PRODUCTION",
                )
            )

        # Body Paragraph 2: Engineering Impact & Projects
        body2 = (
            "Beyond day-to-day feature development, I maintain a strong commitment to system reliability, clean code, and "
            "automated testing. I hold the Google Cloud Certified Professional Cloud Architect credential and have developed "
            "a high-performance distributed Rate Limiter in Go and Redis with benchmark throughput exceeding 100K+ RPS under test. "
            "I also have confirmed hands-on training exposure to Google Kubernetes Engine (GKE) and Helm Charts."
        )
        provenance.append(
            ClaimProvenance(
                claim_text="Google Cloud Certified Professional Cloud Architect credential",
                source_type="ACADEMIC",
                source_ref="EDU-GCP-PCA-001",
                context="Google Cloud certification",
                metric_type="UNMETRIC",
            )
        )
        provenance.append(
            ClaimProvenance(
                claim_text="Distributed Rate Limiter personal project in Go and Redis with 100K+ RPS benchmark",
                source_type="PERSONAL_PROJECT",
                source_ref="PRJ-RL-001",
                context="Rate Limiter project benchmark measurement",
                metric_type="BENCHMARK",
            )
        )

        # Closing
        closing = (
            f"I am eager to bring my technical foundation, cloud-native experience, and problem-solving focus to the "
            f"{title} position at {company}. Thank you for your time and consideration, and I welcome the opportunity "
            f"to discuss how my background aligns with your team's goals.\n\n"
            f"Sincerely,\n"
            f"Kulmeet Singh Jaggi"
        )

        full_text = f"{opening}\n\n{body1}\n\n{body2}\n\n{closing}"
        return full_text, provenance

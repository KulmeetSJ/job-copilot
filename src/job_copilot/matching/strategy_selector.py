"""Resume Strategy Selector for matching and tailoring workflows."""

from typing import Dict, List, Tuple
from job_copilot.matching.models import (
    AnalyzedJob,
    MatchClassification,
    RequirementMatchResult,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class StrategySelector:
    """
    Deterministically recommends the optimal Phase 3 resume strategy based on job requirements,
    candidate confirmed evidence, and role positioning.
    """

    def select_strategy(
        self,
        job: AnalyzedJob,
        matches: List[RequirementMatchResult],
    ) -> Tuple[str, List[str], str]:
        """
        Returns (recommended_strategy, alternative_strategies, reasoning_string).
        """
        scores: Dict[str, float] = {
            "backend_java": 0.0,
            "cloud_devops": 0.0,
            "data_engineering": 0.0,
            "full_stack": 0.0,
            "sre_devops": 0.0,
        }

        # 1. Evaluate Title and Seniority Keywords
        title_l = job.title.lower()
        if "backend" in title_l or "java" in title_l:
            scores["backend_java"] += 40.0
        if "cloud" in title_l or "infrastructure" in title_l:
            scores["cloud_devops"] += 35.0
        if "sre" in title_l or "reliability" in title_l:
            scores["sre_devops"] += 45.0
        if "data" in title_l or "etl" in title_l or "pipeline" in title_l:
            scores["data_engineering"] += 40.0
        if "full stack" in title_l or "fullstack" in title_l or "frontend" in title_l:
            scores["full_stack"] += 45.0
        if "devops" in title_l:
            scores["cloud_devops"] += 25.0
            scores["sre_devops"] += 25.0

        # 2. Evaluate Matched Technical Requirements
        for m in matches:
            norm = m.requirement.normalized_name.lower()
            weight = 10.0 if m.classification == MatchClassification.MATCH_CONFIRMED else 5.0

            # Backend Java keywords
            if norm in ("java", "spring boot", "postgresql", "redis", "rest apis", "microservices", "distributed systems"):
                scores["backend_java"] += weight

            # Cloud & DevOps keywords
            if norm in ("gcp", "terraform", "jenkins", "docker", "ci/cd", "google kubernetes engine (gke)", "helm charts"):
                scores["cloud_devops"] += weight

            # SRE keywords
            if norm in ("gcp cloud monitoring", "prometheus", "grafana", "sonarqube", "checkmarx", "devsecops", "ci/cd"):
                scores["sre_devops"] += weight

            # Data Engineering keywords
            if norm in ("apache beam", "gcp dataflow", "gcp bigquery", "apache airflow", "cloud composer", "google cloud pub/sub", "parquet", "sql", "etl pipelines"):
                scores["data_engineering"] += weight

            # Full Stack keywords
            if norm in ("react", "next.js", "typescript", "javascript", "tailwind css", "supabase", "shadcn/ui"):
                scores["full_stack"] += weight

        # Sort strategies by score descending
        sorted_strats = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        recommended = sorted_strats[0][0]
        alternatives = [s[0] for s in sorted_strats[1:3] if s[1] > 0]

        # Generate clear explainable reasoning
        reasoning_map = {
            "backend_java": "JD emphasizes backend microservices, Java/Spring Boot development, APIs, and high-throughput data processing where candidate possesses strong professional HSBC experience.",
            "cloud_devops": "JD emphasizes cloud infrastructure, Terraform IaC, GCP resource management, and CI/CD automation where candidate has verified enterprise experience.",
            "data_engineering": "JD emphasizes streaming/batch data pipelines, Apache Beam, GCP Dataflow, BigQuery warehousing, and Cloud Composer orchestration.",
            "full_stack": "JD emphasizes end-to-end full stack web applications, React/Next.js/TypeScript frontend interfaces, combined with backend services and database design.",
            "sre_devops": "JD emphasizes system reliability, observability dashboards, CI/CD pipeline automation, DevSecOps security scanning, and operational alerting.",
        }

        reason = reasoning_map.get(recommended, f"Selected based on technical requirement alignment and role positioning for {recommended}.")

        return recommended, alternatives, reason

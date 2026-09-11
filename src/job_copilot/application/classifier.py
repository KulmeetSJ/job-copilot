"""Deterministic Application Question Classifier."""

import re
from typing import Optional, Set
from job_copilot.application.models import (
    ApplicationQuestion,
    QuestionClassification,
    QuestionType,
)
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Topics supported by candidate canonical evidence
EVIDENCED_TOPICS: Set[str] = {
    "java", "spring", "spring boot", "gcp", "google cloud", "bigquery",
    "apache beam", "beam", "dataflow", "cloud composer", "airflow",
    "python", "sql", "rest", "rest api", "rest apis", "microservices",
    "payment", "payments", "transaction", "transactions", "paymentsai", "fintech", "banking", "terraform", "iac",
    "ci/cd", "jenkins", "docker", "redis", "react", "next.js", "typescript",
    "javascript", "supabase", "distributed systems", "observability",
    "cloud monitoring", "gke", "google kubernetes engine", "helm",
    "google adk", "adk", "mcp", "model context protocol", "rate limiter",
    "why are you interested", "why do you want to work", "project you are proud of",
    "tell us about yourself", "describe your background", "overview of your experience"
}

# Sensitive / Legal / Financial keywords requiring explicit human input
USER_INPUT_PATTERNS = [
    r"\bsalary\b", r"\bcompensation\b", r"\bnotice\s*period\b",
    r"\bstart\s*date\b", r"\bavailability\b", r"\bavailable\s*to\s*start\b",
    r"\bvisa\b", r"\bsponsorship\b", r"\bwork\s*authorization\b",
    r"\bauthorized\s*to\s*work\b", r"\bcitizen\b", r"\bcitizenship\b",
    r"\bsecurity\s*clearance\b", r"\brelocation\b", r"\brelocate\b",
    r"\bonsite\b", r"\btravel\b", r"\bcriminal\b", r"\bbackground\s*check\b",
    r"\bdrug\s*test\b", r"\bgpa\b", r"\btranscripts?\b",
    r"\bhow\s+many\s+years.*(?:kubernetes|k8s|aws|azure|c\+\+|embedded)\b",
]

# Patterns asking to confirm unsupported production experience
UNSUPPORTED_PATTERNS = [
    r"\b(?:5|6|7|8|10)\+?\s*years.*(?:aws|azure|kubernetes|k8s)\b",
    r"\bdo\s+you\s+have.*(?:5|6|7|8|10)\+?\s*years\b",
    r"\bexperience\s+with\s+(?:c\+\+|embedded\s+firmware|rtos|arm\s+microcontrollers|assembly)\b",
]


class QuestionClassifier:
    """
    Deterministically categorizes application questions before answer generation.
    Enforces that legal/salary/sponsorship/unverified questions are never automatically answered.
    """

    def classify(self, question: ApplicationQuestion) -> QuestionClassification:
        """Evaluate question text, field name, and question type to return classification."""
        text_lower = question.question_text.lower()
        field_lower = (question.field_name or "").lower()
        combined = f"{text_lower} {field_lower}".strip()

        # 1. Type-based overrides
        if question.question_type in (
            QuestionType.SALARY,
            QuestionType.WORK_AUTHORIZATION,
            QuestionType.SPONSORSHIP,
            QuestionType.DATE,
        ):
            return QuestionClassification.ANSWER_REQUIRES_USER_INPUT

        # 2. Check for unsupported experience traps (e.g. 5+ years AWS)
        for pat in UNSUPPORTED_PATTERNS:
            if re.search(pat, combined):
                return QuestionClassification.DO_NOT_ANSWER

        # 3. Check for Sensitive / Legal / Personal Input patterns
        for pat in USER_INPUT_PATTERNS:
            if re.search(pat, combined):
                return QuestionClassification.ANSWER_REQUIRES_USER_INPUT

        # 4. Check for Yes/No Production Depth traps (e.g. "Do you have production Kubernetes experience?")
        if re.search(r"\bdo\s+you\s+have\b.*\bproduction\s+(?:kubernetes|k8s|aws)\b", combined):
            return QuestionClassification.ANSWER_REQUIRES_USER_INPUT

        # 5. Check if question directly relates to evidenced candidate background
        for topic in EVIDENCED_TOPICS:
            if topic in combined:
                return QuestionClassification.ANSWERABLE_FROM_EVIDENCE

        # 6. Default: If question asks for unspecified external facts, require user input
        if question.question_type in (QuestionType.YES_NO, QuestionType.NUMERIC, QuestionType.SINGLE_SELECT):
            return QuestionClassification.ANSWER_REQUIRES_USER_INPUT

        # If general motivation / software engineering question
        if any(w in combined for w in ["experience", "background", "project", "approach", "technologies", "interested", "role", "strength"]):
            return QuestionClassification.ANSWERABLE_FROM_EVIDENCE

        return QuestionClassification.ANSWER_REQUIRES_USER_INPUT

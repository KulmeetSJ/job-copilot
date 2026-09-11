"""Deterministic Browser Form Field Classifier."""

import re
from typing import Tuple
from job_copilot.browser.models import BrowserElementType, BrowserField, FieldClassification


class FieldClassifier:
    """
    Classifies detected HTML fields into candidate fields, file uploads,
    sensitive user inputs, application questions, or prohibited fields.
    """

    # Prohibited/Sensitive security fields
    PROHIBITED_PATTERNS = [
        r"\bpassword\b",
        r"\bssn\b",
        r"\bsocial\s+security\b",
        r"\bcredit\s*card\b",
        r"\bbank\s*account\b",
        r"\bsecurity\s*code\b",
        r"\bpin\b",
    ]

    # Sensitive user input patterns requiring explicit user input
    SENSITIVE_USER_INPUT_PATTERNS = [
        r"\bsalary\b",
        r"\bcompensation\b",
        r"\bexpected\s*(?:pay|salary|rate)\b",
        r"\bcurrent\s*salary\b",
        r"\bnotice\s*period\b",
        r"\bstart\s*date\b",
        r"\bearliest\s*start\b",
        r"\bavailable\s*to\s*start\b",
        r"\bvisa\b",
        r"\bsponsorship\b",
        r"\bwork\s*authorization\b",
        r"\blegally\s*authorized\b",
        r"\brelocation\b",
        r"\bwilling\s*to\s*relocate\b",
        r"\bonsite\b",
        r"\bremote\s*preference\b",
        r"\bsecurity\s*clearance\b",
        r"\bcriminal\b",
        r"\bbackground\s*check\b",
        r"\bcitizenship\b",
        r"\byears\s*of\s*(?:experience|production)\b",
        r"\bhow\s*many\s*years\b",
    ]

    # Candidate contact fields
    CANDIDATE_PATTERNS = {
        "first_name": [r"\bfirst\s*name\b", r"\bgiven\s*name\b", r"\bforename\b", r"\bfirst_name\b"],
        "last_name": [r"\blast\s*name\b", r"\bsurname\b", r"\bfamily\s*name\b", r"\blast_name\b"],
        "full_name": [r"\bfull\s*name\b", r"^name$", r"\bcandidate\s*name\b"],
        "email": [r"\bemail\b", r"\be-mail\b"],
        "phone": [r"\bphone\b", r"\bmobile\b", r"\btelephone\b", r"\bcell\b", r"\bcontact\s*number\b"],
        "location": [r"\blocation\b", r"\bcity\b", r"\baddress\b", r"\bcurrent\s*city\b", r"\bcountry\b", r"\bstate\b", r"\bpostal\s*code\b", r"\bzip\b"],
        "linkedin": [r"\blinkedin\b", r"\blinkedin\s*(?:url|profile)?\b"],
        "github": [r"\bgithub\b", r"\bgithub\s*(?:url|profile)?\b"],
        "portfolio": [r"\bportfolio\b", r"\bwebsite\b", r"\bpersonal\s*site\b", r"\bblog\b"],
    }

    # File uploads
    FILE_PATTERNS = {
        "resume": [r"\bresume\b", r"\bcv\b", r"\bcurriculum\s*vitae\b"],
        "cover_letter": [r"\bcover\s*letter\b"],
    }

    @classmethod
    def classify_field(cls, field: BrowserField) -> Tuple[FieldClassification, str]:
        """
        Classify a browser field and return (FieldClassification, target_name_or_key).
        """
        raw_text = " ".join(
            filter(
                None,
                [
                    field.label,
                    field.name,
                    field.id_attr,
                    field.placeholder,
                    field.aria_label,
                    field.autocomplete,
                ],
            )
        )
        # Normalize separators so phone_number and cv_upload match word patterns
        text_corpus = re.sub(r"[_\-]", " ", raw_text).lower()

        # 1. Prohibited / Security fields
        for pat in cls.PROHIBITED_PATTERNS:
            if re.search(pat, text_corpus):
                return FieldClassification.DO_NOT_TOUCH, "prohibited_security_field"

        # 2. File Uploads
        if field.element_type == BrowserElementType.INPUT_FILE:
            for key, patterns in cls.FILE_PATTERNS.items():
                for pat in patterns:
                    if re.search(pat, text_corpus):
                        return FieldClassification.FILE_UPLOAD, key
            return FieldClassification.FILE_UPLOAD, "generic_file"

        # 3. Explicit Sensitive User Input Questions
        for pat in cls.SENSITIVE_USER_INPUT_PATTERNS:
            if re.search(pat, text_corpus):
                return FieldClassification.USER_INPUT_REQUIRED, "sensitive_user_input"

        # 4. Known Candidate Fields
        if field.element_type in [BrowserElementType.INPUT_TEL]:
            return FieldClassification.KNOWN_CANDIDATE_FIELD, "phone"
        if field.element_type in [BrowserElementType.INPUT_EMAIL]:
            return FieldClassification.KNOWN_CANDIDATE_FIELD, "email"

        for target, patterns in cls.CANDIDATE_PATTERNS.items():
            # Check autocomplete attribute exact match
            if field.autocomplete:
                ac = field.autocomplete.lower()
                if target in ac or (target == "first_name" and "given-name" in ac) or (target == "last_name" and "family-name" in ac):
                    return FieldClassification.KNOWN_CANDIDATE_FIELD, target

            # Check text corpus
            for pat in patterns:
                if re.search(pat, text_corpus):
                    return FieldClassification.KNOWN_CANDIDATE_FIELD, target

        # 5. Buttons
        if field.element_type == BrowserElementType.BUTTON:
            return FieldClassification.JOB_METADATA, "button"

        # 6. Check if Textarea or long question input
        if field.element_type in [BrowserElementType.TEXTAREA, BrowserElementType.INPUT_TEXT, BrowserElementType.SELECT, BrowserElementType.INPUT_RADIO]:
            # If label looks like a question
            if field.label and (len(field.label) > 15 or "?" in field.label or "describe" in field.label.lower() or "tell" in field.label.lower() or "why" in field.label.lower()):
                return FieldClassification.APPLICATION_QUESTION, "application_question"

        return FieldClassification.UNKNOWN, "unknown"

"""Deterministic Browser Field Mapper."""

import re
from typing import List, Optional
from job_copilot.application.models import (
    ApplicationAnswer,
    ApplicationPackage,
    QuestionClassification,
)
from job_copilot.browser.classifier import FieldClassifier
from job_copilot.browser.models import (
    BrowserField,
    FieldClassification,
    FieldMapping,
    MappingConfidence,
)
from job_copilot.schemas.candidate import CandidateProfile
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class FieldMapper:
    """
    Maps detected BrowserFields to CandidateProfile data and Phase 6 ApplicationPackage answers.
    """

    @classmethod
    def map_fields(
        cls,
        fields: List[BrowserField],
        profile: CandidateProfile,
        package: Optional[ApplicationPackage] = None,
    ) -> List[FieldMapping]:
        """Map a list of detected browser fields."""
        mappings: List[FieldMapping] = []
        for field in fields:
            mapping = cls.map_single_field(field, profile, package)
            mappings.append(mapping)
        return mappings

    @classmethod
    def map_single_field(
        cls,
        field: BrowserField,
        profile: CandidateProfile,
        package: Optional[ApplicationPackage] = None,
    ) -> FieldMapping:
        """Map a single field with safety classification and confidence score."""
        classification, target_key = FieldClassifier.classify_field(field)

        # 1. Prohibited / Do Not Touch
        if classification == FieldClassification.DO_NOT_TOUCH:
            return FieldMapping(
                field_id=field.field_id,
                target_field="prohibited",
                classification=FieldClassification.DO_NOT_TOUCH,
                confidence=MappingConfidence.HIGH,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=False,
                rationale="Field is sensitive/prohibited (e.g., password, SSN, bank info). Automation strictly prohibited.",
            )

        # 2. Known Candidate Fields
        if classification == FieldClassification.KNOWN_CANDIDATE_FIELD:
            return cls._map_candidate_field(field, target_key, profile)

        # 3. File Uploads
        if classification == FieldClassification.FILE_UPLOAD:
            return cls._map_file_upload(field, target_key, package)

        # 4. Sensitive User Input Required
        if classification == FieldClassification.USER_INPUT_REQUIRED:
            return FieldMapping(
                field_id=field.field_id,
                target_field=target_key,
                classification=FieldClassification.USER_INPUT_REQUIRED,
                confidence=MappingConfidence.HIGH,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=True,
                rationale=f"Sensitive field '{field.label or field.name}' requires explicit human input.",
            )

        # 5. Application Questions
        if classification == FieldClassification.APPLICATION_QUESTION:
            return cls._map_application_question(field, package)

        # 6. Button / Job Metadata
        if classification == FieldClassification.JOB_METADATA:
            return FieldMapping(
                field_id=field.field_id,
                target_field=target_key,
                classification=FieldClassification.JOB_METADATA,
                confidence=MappingConfidence.HIGH,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=False,
                rationale="Job metadata or interactive button.",
            )

        # 7. Unknown Field
        return FieldMapping(
            field_id=field.field_id,
            target_field="unknown",
            classification=FieldClassification.UNKNOWN,
            confidence=MappingConfidence.UNKNOWN,
            proposed_value=None,
            is_safe_to_autofill=False,
            requires_user_input=False,
            rationale="Unrecognized field. Manual human inspection recommended.",
        )

    @classmethod
    def _map_candidate_field(
        cls, field: BrowserField, target_key: str, profile: CandidateProfile
    ) -> FieldMapping:
        """Extract candidate value from Canonical Profile."""
        info = profile.personal_info
        val = None
        evidence_refs: List[str] = info.evidence_ids.copy() if info.evidence_ids else []

        # Split full name into first and last
        name_parts = info.full_name.split()
        first_name = name_parts[0] if name_parts else ""
        last_name = " ".join(name_parts[1:]) if len(name_parts) > 1 else ""

        if target_key == "first_name":
            val = first_name
        elif target_key == "last_name":
            val = last_name
        elif target_key == "full_name":
            val = info.full_name
        elif target_key == "email":
            val = info.email
        elif target_key == "phone":
            val = info.phone
        elif target_key == "location":
            val = info.location
        elif target_key in ["linkedin", "github", "portfolio"]:
            for link in info.links:
                if link.label.lower() == target_key or (target_key == "portfolio" and link.label.lower() in ["website", "portfolio", "blog"]):
                    val = link.url
                    if link.evidence_ids:
                        evidence_refs.extend(link.evidence_ids)
                    break

        if val:
            return FieldMapping(
                field_id=field.field_id,
                target_field=target_key,
                classification=FieldClassification.KNOWN_CANDIDATE_FIELD,
                confidence=MappingConfidence.HIGH,
                proposed_value=val,
                is_safe_to_autofill=True,
                requires_user_input=False,
                rationale=f"Mapped to verified canonical candidate profile: {target_key}",
                evidence_refs=evidence_refs,
            )
        else:
            return FieldMapping(
                field_id=field.field_id,
                target_field=target_key,
                classification=FieldClassification.KNOWN_CANDIDATE_FIELD,
                confidence=MappingConfidence.MEDIUM,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=True,
                rationale=f"Candidate field '{target_key}' has no canonical value populated.",
            )

    @classmethod
    def _map_file_upload(
        cls, field: BrowserField, target_key: str, package: Optional[ApplicationPackage]
    ) -> FieldMapping:
        """Map resume PDF or cover letter artifact."""
        if not package:
            return FieldMapping(
                field_id=field.field_id,
                target_field=target_key,
                classification=FieldClassification.FILE_UPLOAD,
                confidence=MappingConfidence.LOW,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=True,
                rationale="No application package available for file upload.",
            )

        if target_key == "resume" or "resume" in (field.label or "").lower() or "cv" in (field.label or "").lower():
            if package.resume_pdf_path:
                return FieldMapping(
                    field_id=field.field_id,
                    target_field="resume_pdf",
                    classification=FieldClassification.FILE_UPLOAD,
                    confidence=MappingConfidence.HIGH,
                    proposed_value=package.resume_pdf_path,
                    is_safe_to_autofill=True,
                    requires_user_input=False,
                    rationale=f"Mapped to Phase 3 tailored resume artifact: {package.selected_resume_strategy}",
                    evidence_refs=[f"RESUME-{package.selected_resume_strategy}"],
                )
        elif target_key == "cover_letter" or "cover" in (field.label or "").lower():
            if package.cover_letter and package.cover_letter.letter_text:
                return FieldMapping(
                    field_id=field.field_id,
                    target_field="cover_letter",
                    classification=FieldClassification.FILE_UPLOAD,
                    confidence=MappingConfidence.HIGH,
                    proposed_value=package.cover_letter.letter_text,
                    is_safe_to_autofill=True,
                    requires_user_input=False,
                    rationale="Mapped to Phase 6 tailored cover letter text.",
                    evidence_refs=package.cover_letter.evidence_refs,
                )

        return FieldMapping(
            field_id=field.field_id,
            target_field=target_key,
            classification=FieldClassification.FILE_UPLOAD,
            confidence=MappingConfidence.MEDIUM,
            proposed_value=None,
            is_safe_to_autofill=False,
            requires_user_input=True,
            rationale="File upload target could not be verified automatically.",
        )

    @classmethod
    def _map_application_question(
        cls, field: BrowserField, package: Optional[ApplicationPackage]
    ) -> FieldMapping:
        """Match browser question against Phase 6 answers."""
        if not package or not package.answers:
            return FieldMapping(
                field_id=field.field_id,
                target_field="application_question",
                classification=FieldClassification.APPLICATION_QUESTION,
                confidence=MappingConfidence.LOW,
                proposed_value=None,
                is_safe_to_autofill=False,
                requires_user_input=True,
                rationale="No prepared Phase 6 application answers available.",
            )

        field_text = (field.label or field.placeholder or field.name or "").lower()

        # Find best matching answer from package
        best_match: Optional[ApplicationAnswer] = None
        best_score = 0

        for ans in package.answers:
            # Find the corresponding question
            q = next((q for q in package.questions if q.id == ans.question_id), None)
            q_text = q.question_text.lower() if q else ""

            # Check exact or keyword overlap
            q_words = set(re.findall(r"\w+", q_text))
            f_words = set(re.findall(r"\w+", field_text))
            overlap = len(q_words.intersection(f_words))

            if overlap > best_score:
                best_score = overlap
                best_match = ans

        if best_match and best_score >= 2:
            if best_match.classification == QuestionClassification.ANSWERABLE_FROM_EVIDENCE:
                evidence_refs = [p.source_ref for p in best_match.provenance] if best_match.provenance else []
                return FieldMapping(
                    field_id=field.field_id,
                    target_field=best_match.question_id,
                    classification=FieldClassification.APPLICATION_QUESTION,
                    confidence=MappingConfidence.HIGH if best_score >= 3 else MappingConfidence.MEDIUM,
                    proposed_value=best_match.answer,
                    is_safe_to_autofill=True,
                    requires_user_input=False,
                    rationale=f"Matched to Phase 6 evidence-backed answer ({best_match.question_id}).",
                    evidence_refs=evidence_refs,
                )
            elif best_match.classification == QuestionClassification.DO_NOT_ANSWER:
                return FieldMapping(
                    field_id=field.field_id,
                    target_field=best_match.question_id,
                    classification=FieldClassification.DO_NOT_TOUCH,
                    confidence=MappingConfidence.HIGH,
                    proposed_value=None,
                    is_safe_to_autofill=False,
                    requires_user_input=False,
                    rationale="Question classified as DO_NOT_ANSWER due to missing evidence or truth-safety constraint.",
                )
            else:
                return FieldMapping(
                    field_id=field.field_id,
                    target_field=best_match.question_id,
                    classification=FieldClassification.USER_INPUT_REQUIRED,
                    confidence=MappingConfidence.HIGH,
                    proposed_value=None,
                    is_safe_to_autofill=False,
                    requires_user_input=True,
                    rationale="Phase 6 classified this question as requiring explicit human input.",
                )

        return FieldMapping(
            field_id=field.field_id,
            target_field="unmatched_question",
            classification=FieldClassification.APPLICATION_QUESTION,
            confidence=MappingConfidence.LOW,
            proposed_value=None,
            is_safe_to_autofill=False,
            requires_user_input=True,
            rationale="Unmatched application question. User input required.",
        )

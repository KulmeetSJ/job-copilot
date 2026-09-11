"""Unit tests for Phase 7 browser field classifier."""

from job_copilot.browser.classifier import FieldClassifier
from job_copilot.browser.models import BrowserElementType, BrowserField, FieldClassification


def test_classify_candidate_fields():
    f1 = BrowserField(field_id="f1", label="First Name", element_type=BrowserElementType.INPUT_TEXT)
    cls1, target1 = FieldClassifier.classify_field(f1)
    assert cls1 == FieldClassification.KNOWN_CANDIDATE_FIELD
    assert target1 == "first_name"

    f2 = BrowserField(field_id="f2", label="Email Address", element_type=BrowserElementType.INPUT_EMAIL)
    cls2, target2 = FieldClassifier.classify_field(f2)
    assert cls2 == FieldClassification.KNOWN_CANDIDATE_FIELD
    assert target2 == "email"

    f3 = BrowserField(field_id="f3", name="phone_number", element_type=BrowserElementType.INPUT_TEL)
    cls3, target3 = FieldClassifier.classify_field(f3)
    assert cls3 == FieldClassification.KNOWN_CANDIDATE_FIELD
    assert target3 == "phone"

    f4 = BrowserField(field_id="f4", label="LinkedIn Profile URL", element_type=BrowserElementType.INPUT_TEXT)
    cls4, target4 = FieldClassifier.classify_field(f4)
    assert cls4 == FieldClassification.KNOWN_CANDIDATE_FIELD
    assert target4 == "linkedin"


def test_classify_file_uploads():
    f_res = BrowserField(field_id="f_res", label="Attach Resume (PDF)", element_type=BrowserElementType.INPUT_FILE)
    cls_res, target_res = FieldClassifier.classify_field(f_res)
    assert cls_res == FieldClassification.FILE_UPLOAD
    assert target_res == "resume"

    f_cv = BrowserField(field_id="f_cv", name="cv_upload", element_type=BrowserElementType.INPUT_FILE)
    cls_cv, target_cv = FieldClassifier.classify_field(f_cv)
    assert cls_cv == FieldClassification.FILE_UPLOAD
    assert target_cv == "resume"


def test_classify_sensitive_user_inputs():
    f_sal = BrowserField(field_id="f_sal", label="What are your salary expectations?", element_type=BrowserElementType.INPUT_TEXT)
    cls_sal, _ = FieldClassifier.classify_field(f_sal)
    assert cls_sal == FieldClassification.USER_INPUT_REQUIRED

    f_spons = BrowserField(field_id="f_spons", label="Will you require visa sponsorship?", element_type=BrowserElementType.SELECT)
    cls_spons, _ = FieldClassifier.classify_field(f_spons)
    assert cls_spons == FieldClassification.USER_INPUT_REQUIRED

    f_k8s = BrowserField(field_id="f_k8s", label="How many years of production Kubernetes experience do you have?", element_type=BrowserElementType.INPUT_NUMBER)
    cls_k8s, _ = FieldClassifier.classify_field(f_k8s)
    assert cls_k8s == FieldClassification.USER_INPUT_REQUIRED


def test_classify_prohibited_security_fields():
    f_pwd = BrowserField(field_id="f_pwd", label="Account Password", name="password", element_type=BrowserElementType.INPUT_TEXT)
    cls_pwd, _ = FieldClassifier.classify_field(f_pwd)
    assert cls_pwd == FieldClassification.DO_NOT_TOUCH

    f_ssn = BrowserField(field_id="f_ssn", label="Social Security Number (SSN)", name="ssn", element_type=BrowserElementType.INPUT_TEXT)
    cls_ssn, _ = FieldClassifier.classify_field(f_ssn)
    assert cls_ssn == FieldClassification.DO_NOT_TOUCH

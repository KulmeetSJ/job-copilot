"""AUTO_APPLY Policy Engine and Centralized Safety Evaluator.

Enforces strict gating invariants for automated application submission.
Never executes Playwright submission directly; only authorizes the canonical
BrowserTaskExecutor when all 14 safety conditions (A-N) are verified.
"""

from datetime import datetime, timezone
import re
import secrets
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid
from pydantic import BaseModel, Field
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from job_copilot.browser_worker.exceptions import DomainSecurityError, SubmissionSafetyError
from job_copilot.browser_worker.safety import (
    is_prohibited_field,
    is_sensitive_field,
    validate_target_domain,
)
from job_copilot.browser_worker.session_manager import AuthenticatedSessionManager
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus, BrowserTaskStatus, FieldAction
from job_copilot.domain.enums import ApplicationMode, ApplicationStatus
from job_copilot.models.browser_task import BrowserTaskModel
from job_copilot.repositories.application_repository import ApplicationRepository
from job_copilot.repositories.browser_task_repository import BrowserTaskRepository
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class AutoApplyEligibilityResult(BaseModel):
    """Deterministic outcome of AUTO_APPLY safety evaluation."""

    eligible: bool = Field(description="Whether the task is safe and eligible for AUTO_APPLY")
    reason: str = Field(description="Deterministic human-readable explanation")
    reason_code: Optional[str] = Field(default=None, description="Machine-readable error/status code")
    blocking_conditions: List[str] = Field(default_factory=list, description="List of failed safety condition codes")
    checked_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


DEFAULT_DAILY_AUTO_APPLY_LIMIT: int = 10


def get_configured_daily_limit() -> int:
    """Retrieve the configured daily auto-apply submission limit from settings or config."""
    try:
        from job_copilot.config import settings
        if hasattr(settings, "auto_apply_daily_limit") and settings.auto_apply_daily_limit is not None:
            return int(settings.auto_apply_daily_limit)
        if hasattr(settings, "max_daily_auto_apply_submissions") and settings.max_daily_auto_apply_submissions is not None:
            return int(settings.max_daily_auto_apply_submissions)
    except Exception:
        pass
    try:
        from job_copilot.copilot.config import load_copilot_config
        cfg = load_copilot_config()
        if hasattr(cfg.queue, "max_daily_auto_apply") and cfg.queue.max_daily_auto_apply is not None:
            return int(cfg.queue.max_daily_auto_apply)
    except Exception:
        pass
    return DEFAULT_DAILY_AUTO_APPLY_LIMIT


def count_daily_auto_apply_submissions(
    db: Session,
    since_time: Optional[datetime] = None,
    exclude_application_id: Optional[str] = None,
) -> int:
    """
    Deterministically count unique applications submitted or authorized for AUTO_APPLY in the daily window.

    Inspects:
    1. ApplicationEventModel: events with source='AUTO_APPLY_POLICY' and event_type in ('SUBMISSION_AUTHORIZED', 'SUBMITTED').
    2. BrowserTaskModel: tasks with application_mode='AUTO_APPLY' (or auto_apply audit event) and status in (SUBMISSION_AUTHORIZED, SUBMISSION_RUNNING, COMPLETED).
    3. Application: applications with mode=AUTO_APPLY and status=APPLIED / submitted_at is not None.
    """
    if since_time is None:
        now = datetime.now(timezone.utc)
        since_time = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif since_time.tzinfo is None:
        since_time = since_time.replace(tzinfo=timezone.utc)

    submitted_app_ids = set()

    # 1. Check ApplicationEventModel
    try:
        from job_copilot.models.application import ApplicationEventModel
        stmt = select(ApplicationEventModel.application_id, ApplicationEventModel.timestamp).where(
            ApplicationEventModel.source == "AUTO_APPLY_POLICY",
            ApplicationEventModel.event_type.in_(["SUBMISSION_AUTHORIZED", "SUBMITTED"]),
        )
        for row in db.execute(stmt).all():
            app_id = row[0]
            ts = row[1]
            if not ts:
                continue
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            if ts >= since_time and app_id:
                submitted_app_ids.add(str(app_id))
    except Exception as e:
        logger.debug(f"Notice querying ApplicationEventModel for daily cap: {e}")

    # 2. Check BrowserTaskModel
    try:
        task_stmt = select(BrowserTaskModel).where(
            or_(
                BrowserTaskModel.application_mode == "AUTO_APPLY",
                BrowserTaskModel.status.in_([
                    BrowserTaskStatus.SUBMISSION_AUTHORIZED,
                    BrowserTaskStatus.SUBMISSION_RUNNING,
                    BrowserTaskStatus.COMPLETED,
                ]),
            )
        )
        for task in db.scalars(task_stmt).all():
            is_auto = (getattr(task, "application_mode", None) == "AUTO_APPLY")
            audit_events = getattr(task, "audit_events", None) or []
            has_auto_audit = any(
                e.get("authorization_source") == "AUTO_APPLY_POLICY"
                or e.get("event") == "auto_apply_submission_authorized"
                for e in audit_events
            )
            if not (is_auto or has_auto_audit):
                continue

            task_status = task.status.value if hasattr(task.status, "value") else str(task.status)
            if task_status not in ("SUBMISSION_AUTHORIZED", "SUBMISSION_RUNNING", "COMPLETED"):
                continue

            task_ts = None
            for e in audit_events:
                if e.get("authorization_source") == "AUTO_APPLY_POLICY" or e.get("event") == "auto_apply_submission_authorized":
                    ts_str = e.get("timestamp")
                    if ts_str:
                        try:
                            task_ts = datetime.fromisoformat(ts_str)
                        except Exception:
                            pass
                    break
            if not task_ts:
                task_ts = task.completed_at or task.updated_at or task.created_at

            if task_ts:
                if task_ts.tzinfo is None:
                    task_ts = task_ts.replace(tzinfo=timezone.utc)
                if task_ts >= since_time and task.application_id:
                    submitted_app_ids.add(str(task.application_id))
    except Exception as e:
        logger.debug(f"Notice querying BrowserTaskModel for daily cap: {e}")

    # 3. Check Application table
    try:
        from job_copilot.models.application import Application
        app_stmt = select(Application).where(
            Application.mode == ApplicationMode.AUTO_APPLY,
            or_(
                Application.status == ApplicationStatus.APPLIED,
                Application.submitted_at.isnot(None),
            ),
        )
        for app in db.scalars(app_stmt).all():
            app_ts = app.submitted_at or app.current_status_at or app.updated_at
            if app_ts:
                if app_ts.tzinfo is None:
                    app_ts = app_ts.replace(tzinfo=timezone.utc)
                if app_ts >= since_time and app.application_id:
                    submitted_app_ids.add(str(app.application_id))
    except Exception as e:
        logger.debug(f"Notice querying Application for daily cap: {e}")

    if exclude_application_id:
        submitted_app_ids.discard(str(exclude_application_id))

    return len(submitted_app_ids)


def _normalize_name(name: Optional[str]) -> str:
    """Normalize employer/company name for robust equality comparisons."""
    if not name:
        return ""
    s = re.sub(r"[^a-zA-Z0-9]+", " ", str(name).lower()).strip()
    s = re.sub(r"\b(inc|llc|corp|corporation|ltd|limited|co|company|we)\b", "", s).strip()
    return re.sub(r"\s+", " ", s).strip()


def _is_valid_canonical_url(url: Optional[str], allow_test_fixture: bool = False) -> Tuple[bool, str]:
    """Validate canonical application URL structure and safety against SSRF/untrusted hosts."""
    if not url or not isinstance(url, str) or not url.strip():
        return False, "Canonical application URL is missing or empty."
    url_str = url.strip()
    try:
        parsed = urlparse(url_str)
        if parsed.scheme.lower() not in ("http", "https"):
            return False, f"Disallowed URL scheme '{parsed.scheme}'. Only HTTP and HTTPS are permitted."
        if not parsed.hostname:
            return False, "URL has no valid hostname."
        validate_target_domain(url_str, allow_test_fixture=allow_test_fixture)
        return True, "OK"
    except DomainSecurityError as dse:
        return False, str(dse)
    except Exception as e:
        return False, f"Invalid canonical URL: {e}"


def evaluate_auto_apply_eligibility(
    application: Any,
    browser_task: Any,
    session: Optional[Any] = None,
    db: Optional[Session] = None,
    allow_test_fixture: bool = False,
    max_daily_submissions: Optional[int] = None,
) -> AutoApplyEligibilityResult:
    """
    Centralized policy engine evaluating strict eligibility for AUTO_APPLY submission.

    AUTO_APPLY is eligible ONLY when ALL 14 required safety conditions pass:
    A. Application/job identity is resolved and canonical.
    B. A valid canonical application URL exists.
    C. Authenticated browser session is ACTIVE, unexpired, matches employer & domain, isolates cross-employer state.
    D. Browser task is genuinely in READY_FOR_REVIEW state.
    E. Required application fields have been resolved.
    F. NO unresolved user inputs exist.
    G. NO sensitive fields requiring user input exist.
    H. NO CAPTCHA blocker exists.
    I. NO MFA/OTP blocker exists.
    J. NO LOGIN_REQUIRED blocker exists.
    K. NO HUMAN_ACTION_REQUIRED blocker exists.
    L. NO duplicate/previous submission exists.
    M. Existing safety/domain/authorization checks pass (mode == AUTO_APPLY, domains align).
    N. NO existing policy/risk blocker prevents automated submission.
    """
    # --------------------------------------------------------------------------
    # Condition A: Application / Job Identity is resolved and canonical
    # --------------------------------------------------------------------------
    app_id = getattr(application, "application_id", None) or getattr(application, "id", None)
    if not app_id:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="Application canonical identity is missing or unresolved.",
            reason_code="CANONICAL_IDENTITY_UNRESOLVED",
            blocking_conditions=["A_APPLICATION_IDENTITY"],
        )

    if browser_task is None:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="Browser task does not exist for application.",
            reason_code="TASK_MISSING",
            blocking_conditions=["A_APPLICATION_IDENTITY"],
        )

    clean_app_id = str(app_id).strip()
    task_app_id = getattr(browser_task, "application_id", None)
    if task_app_id and str(task_app_id).strip() != clean_app_id:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Task application ID '{task_app_id}' does not match application ID '{clean_app_id}'.",
            reason_code="IDENTITY_MISMATCH",
            blocking_conditions=["A_APPLICATION_IDENTITY"],
        )

    expected_job_id = (
        getattr(application, "job_id_str", None)
        or getattr(getattr(application, "job", None), "job_id", None)
        or getattr(application, "job_id", None)
    )
    task_job_id = getattr(browser_task, "job_id", None)
    if expected_job_id and task_job_id and str(task_job_id).strip() != str(expected_job_id).strip():
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Task job ID '{task_job_id}' does not match application job ID '{expected_job_id}'.",
            reason_code="IDENTITY_MISMATCH",
            blocking_conditions=["A_APPLICATION_IDENTITY"],
        )

    # --------------------------------------------------------------------------
    # Condition B: A valid canonical application URL exists
    # --------------------------------------------------------------------------
    canonical_url = getattr(application, "canonical_job_url", None) or getattr(browser_task, "target_url", None)
    is_fixture = (
        allow_test_fixture
        or ("test.local" in (canonical_url or ""))
        or ("localhost" in (canonical_url or ""))
        or ("127.0.0.1" in (canonical_url or ""))
    )
    valid_url, url_err = _is_valid_canonical_url(canonical_url, allow_test_fixture=is_fixture)
    if not valid_url:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Invalid or missing canonical application URL: {url_err}",
            reason_code="INVALID_CANONICAL_URL",
            blocking_conditions=["B_CANONICAL_URL"],
        )

    # --------------------------------------------------------------------------
    # Condition C: Authenticated browser session
    # --------------------------------------------------------------------------
    resolved_session = session
    if resolved_session is None and db is not None:
        mgr = AuthenticatedSessionManager(db)
        resolved_session = mgr.get_active_session_for_application(
            source=getattr(application, "source", None) or getattr(browser_task, "source", None),
            company=getattr(application, "company", None),
            canonical_job_url=canonical_url,
        )

    if resolved_session is None:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="No active authenticated browser session found for employer or target domain.",
            reason_code="NO_AUTHENTICATED_SESSION",
            blocking_conditions=["C_AUTHENTICATED_SESSION"],
        )

    sess_status = getattr(resolved_session, "status", None)
    if hasattr(sess_status, "value"):
        sess_status = sess_status.value
    if not sess_status or str(sess_status).upper() != "ACTIVE":
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Authenticated session is in '{sess_status}' state, expected ACTIVE.",
            reason_code="SESSION_NOT_ACTIVE",
            blocking_conditions=["C_AUTHENTICATED_SESSION"],
        )

    now = datetime.now(timezone.utc)
    exp = getattr(resolved_session, "expires_at", None)
    if exp is not None:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp <= now:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Authenticated browser session expired at {exp.isoformat()}.",
                reason_code="SESSION_EXPIRED",
                blocking_conditions=["C_AUTHENTICATED_SESSION"],
            )

    company = getattr(application, "company", None)
    norm_target_company = _normalize_name(company)
    meta = getattr(resolved_session, "metadata_json", None) or {}

    session_emp = None
    for k in (
        "company",
        "employer",
        "company_name",
        "employer_name",
        "target_company",
        "target_employer",
        "organization",
        "org",
        "account_employer",
    ):
        if k in meta and meta[k]:
            session_emp = str(meta[k]).strip()
            break

    if session_emp:
        if norm_target_company and _normalize_name(session_emp) != norm_target_company:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Session employer '{session_emp}' does not match application employer '{company}'. Cross-employer isolation violation.",
                reason_code="WRONG_EMPLOYER_SESSION",
                blocking_conditions=["C_AUTHENTICATED_SESSION"],
            )
        if not norm_target_company:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason="Cannot verify session employer match because application company is not specified.",
                reason_code="WRONG_EMPLOYER_SESSION",
                blocking_conditions=["C_AUTHENTICATED_SESSION"],
            )

    sess_source = (getattr(resolved_session, "source", "") or "").lower().strip()
    known_platforms = {
        "linkedin", "naukri", "instahyre", "generic",
        "greenhouse", "lever", "workday", "ashby", "smartrecruiters", "workable", "breezy", "rippling",
    }
    if sess_source and sess_source not in known_platforms:
        if norm_target_company and _normalize_name(sess_source) != norm_target_company:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Session source employer '{sess_source}' does not match application company '{company}'.",
                reason_code="WRONG_EMPLOYER_SESSION",
                blocking_conditions=["C_AUTHENTICATED_SESSION"],
            )

    # Domain restriction alignment
    target_domains = []
    if meta.get("target_domain"):
        target_domains.append(str(meta["target_domain"]).strip().lower())
    if meta.get("domain"):
        target_domains.append(str(meta["domain"]).strip().lower())
    if isinstance(meta.get("allowed_domains"), list):
        for d in meta["allowed_domains"]:
            target_domains.append(str(d).strip().lower())

    if target_domains and canonical_url:
        app_host = (urlparse(canonical_url).hostname or "").lower()
        url_lower = canonical_url.lower()
        domain_matched = False
        for td in target_domains:
            if "://" in td:
                td_host = (urlparse(td).hostname or "").lower()
            else:
                td_host = td.split("/")[0].strip()
            if app_host and (app_host == td_host or app_host.endswith("." + td_host) or td_host.endswith("." + app_host)):
                domain_matched = True
                break
            elif td in url_lower:
                domain_matched = True
                break
        if not domain_matched:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Session domain restrictions {target_domains} do not match application domain '{app_host}'.",
                reason_code="SESSION_DOMAIN_MISMATCH",
                blocking_conditions=["C_AUTHENTICATED_SESSION"],
            )

    audit_events = getattr(browser_task, "audit_events", None) or []
    pause_reason = getattr(browser_task, "pause_reason", None) or ""
    task_status = getattr(browser_task, "status", None)
    if hasattr(task_status, "value"):
        task_status = task_status.value

    # --------------------------------------------------------------------------
    # Condition L: NO duplicate/previous submission exists
    # --------------------------------------------------------------------------
    app_status = getattr(application, "status", None)
    if hasattr(app_status, "value"):
        app_status = app_status.value
    if app_status in ("APPLIED", "OFFER", "REJECTED", "WITHDRAWN"):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Application is already in terminal state '{app_status}'. Duplicate submission prevented.",
            reason_code="DUPLICATE_SUBMISSION",
            blocking_conditions=["L_DUPLICATE_SUBMISSION"],
        )

    if task_status in ("COMPLETED", "SUBMISSION_AUTHORIZED", "SUBMISSION_RUNNING"):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task is already '{task_status}'. Duplicate submission prevented.",
            reason_code="DUPLICATE_SUBMISSION",
            blocking_conditions=["L_DUPLICATE_SUBMISSION"],
        )

    if any(e.get("event") == "submission_verified" for e in audit_events):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="Browser task already has a verified submission record. Duplicate submission prevented.",
            reason_code="DUPLICATE_SUBMISSION",
            blocking_conditions=["L_DUPLICATE_SUBMISSION"],
        )

    # --------------------------------------------------------------------------
    # Condition H: NO CAPTCHA blocker
    # --------------------------------------------------------------------------
    if (
        task_status == "CAPTCHA_REQUIRED"
        or any(e.get("blocker_type") == "CAPTCHA" or e.get("event") == "captcha_detected" for e in audit_events)
        or "CAPTCHA" in pause_reason.upper()
    ):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="CAPTCHA challenge blocker detected.",
            reason_code="CAPTCHA_REQUIRED",
            blocking_conditions=["H_CAPTCHA_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Condition I: NO MFA/OTP blocker
    # --------------------------------------------------------------------------
    if (
        task_status == "MFA_REQUIRED"
        or any(e.get("blocker_type") == "MFA" for e in audit_events)
        or any(w in pause_reason.upper() for w in ("MFA", "OTP", "VERIFICATION CODE"))
    ):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="MFA / OTP verification code blocker detected.",
            reason_code="MFA_REQUIRED",
            blocking_conditions=["I_MFA_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Condition J: NO LOGIN_REQUIRED blocker
    # --------------------------------------------------------------------------
    if (
        task_status == "LOGIN_REQUIRED"
        or any(e.get("blocker_type") == "LOGIN" for e in audit_events)
        or "LOGIN" in pause_reason.upper()
    ):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="Authentication login wall detected.",
            reason_code="LOGIN_REQUIRED",
            blocking_conditions=["J_LOGIN_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Condition K: NO HUMAN_ACTION_REQUIRED blocker
    # --------------------------------------------------------------------------
    if (
        task_status == "HUMAN_ACTION_REQUIRED"
        or any(e.get("event") == "human_action_required" and not e.get("resolved") for e in audit_events)
        or "HUMAN ACTION" in pause_reason.upper()
    ):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason="Human action required blocker detected.",
            reason_code="HUMAN_ACTION_REQUIRED",
            blocking_conditions=["K_HUMAN_ACTION_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Condition N: NO existing policy/risk blocker prevents automated submission
    # --------------------------------------------------------------------------
    if task_status in ("BLOCKED", "FAILED"):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task is in '{task_status}' state: {getattr(browser_task, 'failure_reason', None) or pause_reason or 'Blocked by policy'}.",
            reason_code="TASK_BLOCKED_OR_FAILED",
            blocking_conditions=["N_POLICY_RISK_BLOCKER"],
        )

    if getattr(browser_task, "failure_reason", None):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task recorded failure reason: {browser_task.failure_reason}",
            reason_code="POLICY_RISK_BLOCKER",
            blocking_conditions=["N_POLICY_RISK_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Condition D: Browser task is genuinely READY_FOR_REVIEW
    # --------------------------------------------------------------------------
    if task_status != "READY_FOR_REVIEW":
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task is in '{task_status}' status, expected READY_FOR_REVIEW.",
            reason_code="TASK_NOT_READY_FOR_REVIEW",
            blocking_conditions=["D_TASK_STATE"],
        )

    # --------------------------------------------------------------------------
    # Condition E: Required application fields have been resolved
    # --------------------------------------------------------------------------
    review_pkg = getattr(browser_task, "review_package_json", None) or {}
    fields_req = review_pkg.get("fields_requiring_user_input", 0)
    if fields_req > 0:
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Application has {fields_req} required form field(s) awaiting user input.",
            reason_code="UNRESOLVED_REQUIRED_FIELDS",
            blocking_conditions=["E_REQUIRED_FIELDS"],
        )

    fields_summary = review_pkg.get("fields_summary", [])
    for f in fields_summary:
        act = f.get("action")
        if hasattr(act, "value"):
            act = act.value
        if act == "REQUIRES_USER_INPUT":
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Field '{f.get('label') or f.get('name') or f.get('field_id')}' requires user input.",
                reason_code="UNRESOLVED_REQUIRED_FIELDS",
                blocking_conditions=["E_REQUIRED_FIELDS"],
            )
        if f.get("required") and (act in ("DO_NOT_FILL", "UNKNOWN") or not f.get("filled_value_masked")):
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Required field '{f.get('label') or f.get('name') or f.get('field_id')}' has not been resolved.",
                reason_code="UNRESOLVED_REQUIRED_FIELDS",
                blocking_conditions=["E_REQUIRED_FIELDS"],
            )

    # --------------------------------------------------------------------------
    # Condition F: NO unresolved user inputs
    # --------------------------------------------------------------------------
    app_inputs = getattr(application, "user_inputs_required", None) or []
    for inp in app_inputs:
        answered = getattr(inp, "answered", False) if not isinstance(inp, dict) else inp.get("answered", False)
        val = getattr(inp, "value", None) if not isinstance(inp, dict) else inp.get("value")
        if not answered and not val:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason="Application has pending user inputs awaiting candidate answers.",
                reason_code="UNRESOLVED_USER_INPUT",
                blocking_conditions=["F_UNRESOLVED_USER_INPUT"],
            )

    # --------------------------------------------------------------------------
    # Condition G: NO sensitive fields requiring user input
    # --------------------------------------------------------------------------
    for f in fields_summary:
        lbl = f.get("label") or f.get("name") or ""
        if is_prohibited_field(lbl):
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Prohibited field detected on application: '{lbl}'.",
                reason_code="PROHIBITED_FIELD_DETECTED",
                blocking_conditions=["G_SENSITIVE_FIELDS"],
            )
        if is_sensitive_field(lbl):
            act = f.get("action")
            if hasattr(act, "value"):
                act = act.value
            if act != "AUTO_FILL" or not f.get("filled_value_masked"):
                return AutoApplyEligibilityResult(
                    eligible=False,
                    reason=f"Sensitive field '{lbl}' requires explicit user input.",
                    reason_code="SENSITIVE_USER_INPUT_PENDING",
                    blocking_conditions=["G_SENSITIVE_FIELDS"],
                )


    # --------------------------------------------------------------------------
    # Condition M: Existing safety/domain/authorization checks pass
    # --------------------------------------------------------------------------
    app_mode = getattr(application, "mode", None)
    if hasattr(app_mode, "value"):
        app_mode = app_mode.value
    if app_mode and str(app_mode).upper() != "AUTO_APPLY":
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Application mode is '{app_mode}', expected AUTO_APPLY.",
            reason_code="MODE_NOT_AUTO_APPLY",
            blocking_conditions=["M_SAFETY_AND_DOMAIN"],
        )

    app_url = getattr(application, "canonical_job_url", None)
    task_url = getattr(browser_task, "target_url", None)
    if app_url and task_url:
        app_host = (urlparse(app_url).hostname or "").lower()
        task_host = (urlparse(task_url).hostname or "").lower()
        if app_host and task_host and app_host != task_host:
            if not (app_host.endswith("." + task_host) or task_host.endswith("." + app_host)):
                return AutoApplyEligibilityResult(
                    eligible=False,
                    reason=f"Browser task target domain '{task_host}' does not match application domain '{app_host}'.",
                    reason_code="DOMAIN_MISMATCH",
                    blocking_conditions=["M_SAFETY_AND_DOMAIN"],
                )

    # Condition M (Rate Limiting): Daily AUTO_APPLY submission cap
    if db is not None:
        effective_cap = max_daily_submissions if max_daily_submissions is not None else get_configured_daily_limit()
        if effective_cap is not None and effective_cap >= 0:
            current_app_id = getattr(application, "application_id", None) or getattr(application, "id", None)
            current_count = count_daily_auto_apply_submissions(
                db=db,
                exclude_application_id=str(current_app_id) if current_app_id else None,
            )
            if current_count >= effective_cap:
                return AutoApplyEligibilityResult(
                    eligible=False,
                    reason=f"Daily AUTO_APPLY submission limit reached ({current_count}/{effective_cap} submissions today).",
                    reason_code="RATE_LIMIT_EXCEEDED",
                    blocking_conditions=["M_SAFETY_AND_DOMAIN"],
                )

    # --------------------------------------------------------------------------
    # Condition N: NO existing policy/risk blocker prevents automated submission
    # --------------------------------------------------------------------------
    if task_status in ("BLOCKED", "FAILED"):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task is in '{task_status}' state: {getattr(browser_task, 'failure_reason', None) or pause_reason or 'Blocked by policy'}.",
            reason_code="TASK_BLOCKED_OR_FAILED",
            blocking_conditions=["N_POLICY_RISK_BLOCKER"],
        )

    if getattr(browser_task, "failure_reason", None):
        return AutoApplyEligibilityResult(
            eligible=False,
            reason=f"Browser task recorded failure reason: {browser_task.failure_reason}",
            reason_code="POLICY_RISK_BLOCKER",
            blocking_conditions=["N_POLICY_RISK_BLOCKER"],
        )

    # --------------------------------------------------------------------------
    # Clean Pass: ALL 14 safety conditions satisfied
    # --------------------------------------------------------------------------
    return AutoApplyEligibilityResult(
        eligible=True,
        reason="All AUTO_APPLY safety and eligibility conditions satisfied.",
        reason_code="ELIGIBLE",
        blocking_conditions=[],
    )


class AutoApplyPolicyService:
    """
    Service coordinating AUTO_APPLY eligibility evaluation and safe authorization.

    AUTHORIZATION CONTRACT:
    - Sets BrowserTaskModel.status = SUBMISSION_AUTHORIZED.
    - Appends audit event with authorization_source = 'AUTO_APPLY_POLICY'.
    - Does NOT call Playwright directly.
    - Does NOT mark the Application as APPLIED/SUBMITTED.
    - Actual submission strictly delegates to BrowserTaskExecutor.execute_submission_task().
    """

    DEFAULT_DAILY_SUBMISSION_CAP: int = 10

    def __init__(self, db: Session, max_daily_submissions: Optional[int] = None):
        self.db = db
        self.task_repo = BrowserTaskRepository(db)
        self.app_repo = ApplicationRepository(db)
        self.session_manager = AuthenticatedSessionManager(db)
        if max_daily_submissions is not None:
            self.max_daily_submissions = max_daily_submissions
        else:
            self.max_daily_submissions = get_configured_daily_limit()

    def count_daily_submissions(
        self,
        since_time: Optional[datetime] = None,
        exclude_application_id: Optional[str] = None,
    ) -> int:
        """Count distinct AUTO_APPLY submissions for the current daily window."""
        return count_daily_auto_apply_submissions(
            db=self.db,
            since_time=since_time,
            exclude_application_id=exclude_application_id,
        )

    def evaluate(
        self,
        application_id: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        allow_test_fixture: bool = False,
        max_daily_submissions: Optional[int] = None,
    ) -> AutoApplyEligibilityResult:
        """Evaluate AUTO_APPLY eligibility without modifying any task state."""
        app = self.app_repo.get_by_application_id(application_id) or self.app_repo.get_by_job_id_str(application_id)
        if not app:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"Application '{application_id}' not found.",
                reason_code="APPLICATION_NOT_FOUND",
                blocking_conditions=["A_APPLICATION_IDENTITY"],
            )

        task = None
        if task_id:
            task = self.task_repo.get_by_task_id(task_id)
        else:
            task = self.task_repo.get_by_application_id(app.application_id) or self.task_repo.get_by_application_or_job_id(
                application_id=app.application_id, job_id=app.job_id_str
            )
        if not task:
            return AutoApplyEligibilityResult(
                eligible=False,
                reason=f"No active browser task found for application '{application_id}'.",
                reason_code="TASK_MISSING",
                blocking_conditions=["A_APPLICATION_IDENTITY"],
            )

        session = None
        if session_id:
            session = self.session_manager.get_session(session_id)
        else:
            session = self.session_manager.get_active_session_for_application(
                source=app.source or task.source,
                company=app.company,
                canonical_job_url=app.canonical_job_url or task.target_url,
            )

        effective_cap = max_daily_submissions if max_daily_submissions is not None else self.max_daily_submissions
        return evaluate_auto_apply_eligibility(
            application=app,
            browser_task=task,
            session=session,
            db=self.db,
            allow_test_fixture=allow_test_fixture,
            max_daily_submissions=effective_cap,
        )

    def authorize(
        self,
        application_id: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        allow_test_fixture: bool = False,
        max_daily_submissions: Optional[int] = None,
    ) -> Tuple[BrowserTaskModel, AutoApplyEligibilityResult]:
        """
        Safely authorize an AUTO_APPLY application for downstream execution.

        Raises SubmissionSafetyError if any safety condition fails.
        Transitions task to SUBMISSION_AUTHORIZED and records audit event with
        authorization_source = 'AUTO_APPLY_POLICY'.
        """
        app = self.app_repo.get_by_application_id(application_id) or self.app_repo.get_by_job_id_str(application_id)
        if not app:
            raise SubmissionSafetyError(f"Application '{application_id}' not found.")

        task = None
        if task_id:
            task = self.task_repo.get_by_task_id(task_id)
        else:
            task = self.task_repo.get_by_application_id(app.application_id) or self.task_repo.get_by_application_or_job_id(
                application_id=app.application_id, job_id=app.job_id_str
            )
        if not task:
            raise SubmissionSafetyError(f"No active browser task found for application '{application_id}'.")


        session = None
        if session_id:
            session = self.session_manager.get_session(session_id)
        else:
            session = self.session_manager.get_active_session_for_application(
                source=app.source or task.source,
                company=app.company,
                canonical_job_url=app.canonical_job_url or task.target_url,
            )

        effective_cap = max_daily_submissions if max_daily_submissions is not None else self.max_daily_submissions
        eligibility = evaluate_auto_apply_eligibility(
            application=app,
            browser_task=task,
            session=session,
            db=self.db,
            allow_test_fixture=allow_test_fixture,
            max_daily_submissions=effective_cap,
        )

        if not eligibility.eligible:
            logger.warning(
                f"AUTO_APPLY authorization blocked for '{application_id}': {eligibility.reason} ({eligibility.reason_code})"
            )
            raise SubmissionSafetyError(f"AUTO_APPLY not eligible: {eligibility.reason}")

        now = datetime.now(timezone.utc)
        ref_id = f"AUTO-{secrets.token_hex(4).upper()}"

        # 1. Update status to SUBMISSION_AUTHORIZED
        self.task_repo.update_status(task.task_id, BrowserTaskStatus.SUBMISSION_AUTHORIZED)

        # 2. Append audit event with exact authorization_source = 'AUTO_APPLY_POLICY'
        self.task_repo.append_audit_event(
            task.task_id,
            {
                "event": "auto_apply_submission_authorized",
                "authorization_source": "AUTO_APPLY_POLICY",
                "reference": ref_id,
                "reason": eligibility.reason,
                "reason_code": eligibility.reason_code,
                "application_id": app.application_id,
                "task_id": task.task_id,
                "timestamp": now.isoformat(),
            },
        )

        # 3. Append tracking event in application lifecycle
        try:
            self.app_repo.append_event(
                application_id=app.application_id,
                job_id=task.job_id or app.job_id_str or app.application_id,
                event_type="SUBMISSION_AUTHORIZED",
                event_id=f"evt-{uuid.uuid4().hex[:8]}",
                source="AUTO_APPLY_POLICY",
                notes=f"Submission authorized by AUTO_APPLY_POLICY (ref: {ref_id}, reason: {eligibility.reason})",
            )
            self.db.commit()
        except Exception as e:
            logger.warning(f"Notice appending application lifecycle event: {e}")

        logger.info(
            f"AUTO_APPLY policy authorized submission for task '{task.task_id}' (ref: {ref_id})"
        )
        updated_task = self.task_repo.get_by_task_id(task.task_id)
        return updated_task, eligibility

"""Manager for Authenticated Browser Sessions lifecycle and validation."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse
import uuid
from sqlalchemy.orm import Session

from job_copilot.browser_worker.session_store import BrowserSessionStore
from job_copilot.domain.browser_worker_enums import AuthenticatedSessionStatus
from job_copilot.models.browser_session import BrowserSessionModel
from job_copilot.repositories.browser_session_repository import BrowserSessionRepository
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class AuthenticatedSessionManager:
    """
    Coordinates authenticated session metadata in PostgreSQL with secure
    isolated browser storage state files.
    """

    def __init__(self, db: Session, session_store: Optional[BrowserSessionStore] = None):
        self.db = db
        self.repo = BrowserSessionRepository(db)
        self.session_store = session_store or BrowserSessionStore()

    def create_session(
        self,
        source: str,
        session_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> BrowserSessionModel:
        """Register a new authenticated session tracking record."""
        sid = session_id or f"sess-{source.lower()}-{uuid.uuid4().hex[:8]}"
        model = BrowserSessionModel(
            session_id=sid,
            source=source.lower(),
            status=AuthenticatedSessionStatus.NOT_CONFIGURED,
            metadata_json=metadata_json,
        )
        return self.repo.create(model)

    def get_session(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Fetch session metadata by session ID."""
        return self.repo.get_by_session_id(session_id)

    def get_active_session_for_source(self, source: str) -> Optional[BrowserSessionModel]:
        """Fetch the active session record for a given job portal source."""
        session_model = self.repo.get_by_source(source.lower())
        if session_model and session_model.status == AuthenticatedSessionStatus.ACTIVE:
            return session_model
        return None

    def get_active_session_for_application(
        self,
        source: Optional[str] = None,
        company: Optional[str] = None,
        canonical_job_url: Optional[str] = None,
    ) -> Optional[BrowserSessionModel]:
        """
        Safely resolve an active authenticated browser session for an application.

        SECURITY & ISOLATION INVARIANTS:
        1. ACTIVE Status: Session must have AuthenticatedSessionStatus.ACTIVE and not be expired.
        2. Employer Isolation: A session registered for Employer A must NEVER be reused for Employer B.
        3. Domain Alignment: Application domain must match session's source or target domain.
        4. Safe Fallback: If session cannot be verified safely, returns None (causing LOGIN_REQUIRED).
        """
        def _norm_name(n: Optional[str]) -> str:
            if not n:
                return ""
            s = re.sub(r"[^a-zA-Z0-9]+", " ", str(n).lower()).strip()
            s = re.sub(r"\b(inc|llc|corp|corporation|ltd|limited|co|company|we)\b", "", s).strip()
            return re.sub(r"\s+", " ", s).strip()

        KNOWN_MULTI_TENANT = {"linkedin", "naukri", "instahyre", "generic"}
        KNOWN_ATS = {
            "greenhouse": ["greenhouse.io", "boards.greenhouse.io", "job-boards.greenhouse.io", "boards.eu.greenhouse.io"],
            "lever": ["lever.co", "jobs.lever.co"],
            "workday": ["workday.com", "myworkdayjobs.com"],
            "ashby": ["ashbyhq.com", "jobs.ashbyhq.com"],
            "smartrecruiters": ["smartrecruiters.com", "jobs.smartrecruiters.com"],
            "workable": ["workable.com", "apply.workable.com"],
            "breezy": ["breezy.hr"],
            "rippling": ["rippling-ats.com"],
        }

        app_host = ""
        url_lower = ""
        if canonical_job_url:
            url_lower = canonical_job_url.lower()
            parsed = urlparse(canonical_job_url)
            app_host = (parsed.hostname or "").lower()

        norm_target_company = _norm_name(company)
        app_source_lower = (source or "").lower().strip()

        now = datetime.now(timezone.utc)
        active_sessions = self.repo.list_active() if hasattr(self.repo, "list_active") else [
            s for s in self.repo.list_all(limit=100) if s.status == AuthenticatedSessionStatus.ACTIVE
        ]

        candidate_sessions: List[Tuple[int, BrowserSessionModel]] = []

        for sess in active_sessions:
            if sess.status != AuthenticatedSessionStatus.ACTIVE:
                continue

            # 1. Check expiration
            if sess.expires_at is not None:
                exp = sess.expires_at
                if exp.tzinfo is None:
                    exp = exp.replace(tzinfo=timezone.utc)
                if exp <= now:
                    continue

            meta = sess.metadata_json or {}
            sess_source = sess.source.lower().strip()

            # 2. Employer Ownership Isolation
            session_emp = None
            for k in ("company", "employer", "company_name", "employer_name", "target_company", "target_employer", "organization", "org", "account_employer"):
                if k in meta and meta[k]:
                    session_emp = str(meta[k]).strip()
                    break

            # If metadata specifies an employer, it MUST match the application's company
            if session_emp:
                norm_sess_emp = _norm_name(session_emp)
                if norm_target_company and norm_sess_emp != norm_target_company:
                    # Session belongs to another employer -> DO NOT REUSE
                    continue
                if not norm_target_company:
                    # Cannot safely determine company match -> DO NOT REUSE
                    continue

            # Check if session.source itself designates an employer
            is_known_platform = sess_source in KNOWN_MULTI_TENANT or sess_source in KNOWN_ATS
            if not is_known_platform:
                norm_src_emp = _norm_name(sess_source)
                if norm_target_company and norm_src_emp != norm_target_company:
                    continue
                if not norm_target_company and norm_src_emp != _norm_name(app_source_lower):
                    continue

            # 3. Domain & Target Restrictions Verification
            target_domains = []
            if meta.get("target_domain"):
                target_domains.append(str(meta["target_domain"]).strip().lower())
            if meta.get("domain"):
                target_domains.append(str(meta["domain"]).strip().lower())
            if isinstance(meta.get("allowed_domains"), list):
                for d in meta["allowed_domains"]:
                    target_domains.append(str(d).strip().lower())

            if target_domains:
                domain_matched = False
                for td in target_domains:
                    if "://" in td:
                        td_host = (urlparse(td).hostname or "").lower()
                    else:
                        td_host = td.split("/")[0].strip()

                    if app_host and (app_host == td_host or app_host.endswith("." + td_host) or td_host.endswith("." + app_host)):
                        if "/" in td and not td.startswith("http"):
                            prefix = td.split("/", 1)[1]
                            if prefix in url_lower:
                                domain_matched = True
                                break
                        else:
                            domain_matched = True
                            break
                    elif td in url_lower:
                        domain_matched = True
                        break

                if not domain_matched:
                    # Domain restriction mismatch -> DO NOT REUSE
                    continue

            # 4. Source Platform Alignment
            if sess_source in KNOWN_ATS:
                ats_domains = KNOWN_ATS[sess_source]
                if app_host and not any(app_host == d or app_host.endswith("." + d) for d in ats_domains):
                    continue

            if sess_source == "linkedin" and app_host and not ("linkedin.com" in app_host):
                continue
            if sess_source == "naukri" and app_host and not ("naukri.com" in app_host):
                continue
            if sess_source == "instahyre" and app_host and not ("instahyre.com" in app_host):
                continue

            # Source name match
            source_matched = False
            if app_source_lower and sess_source == app_source_lower:
                source_matched = True
            elif sess_source in KNOWN_ATS and app_host and any(app_host == d or app_host.endswith("." + d) for d in KNOWN_ATS[sess_source]):
                source_matched = True
            elif sess_source in KNOWN_MULTI_TENANT and app_host and (sess_source in app_host):
                source_matched = True
            elif norm_target_company and (_norm_name(sess_source) == norm_target_company):
                source_matched = True
            elif not is_known_platform and norm_target_company and (_norm_name(sess_source) == norm_target_company):
                source_matched = True

            if not source_matched and app_source_lower:
                continue

            # Priority score:
            # 2 = Explicit company match in metadata or employer source
            # 1 = Generic / unrestricted session matching source and domain
            score = 1
            if session_emp and _norm_name(session_emp) == norm_target_company:
                score = 2
            elif not is_known_platform and _norm_name(sess_source) == norm_target_company:
                score = 2

            candidate_sessions.append((score, sess))

        if not candidate_sessions:
            return None

        candidate_sessions.sort(key=lambda x: (x[0], getattr(x[1], "id", 0)), reverse=True)
        return candidate_sessions[0][1]

    def list_sessions(self, limit: int = 50) -> List[BrowserSessionModel]:
        """List session metadata records."""
        return self.repo.list_all(limit=limit)

    async def save_authenticated_state(
        self,
        session_id: str,
        state_dict: Dict[str, Any],
        expires_in_days: int = 14,
    ) -> Optional[BrowserSessionModel]:
        """
        Store authenticated Playwright state to isolated storage and activate session.
        """
        session_obj = self.get_session(session_id)
        if not session_obj:
            logger.warning(f"Attempted to save state for non-existent session '{session_id}'")
            return None

        # 1. Save state in secure store
        await self.session_store.save_session_state(session_id, state_dict)

        # 2. Update DB metadata
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(days=expires_in_days)
        updated = self.repo.update_status(
            session_id,
            status=AuthenticatedSessionStatus.ACTIVE,
            last_verified_at=now,
            expires_at=expires_at,
        )
        logger.info(f"Activated browser session '{session_id}' for source '{session_obj.source}'")
        return updated

    def mark_login_required(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Mark session as requiring human login."""
        return self.repo.update_status(session_id, status=AuthenticatedSessionStatus.LOGIN_REQUIRED)

    def mark_expired(self, session_id: str) -> Optional[BrowserSessionModel]:
        """Mark session as expired."""
        return self.repo.update_status(session_id, status=AuthenticatedSessionStatus.EXPIRED)

    async def revoke_session(self, session_id: str) -> bool:
        """Revoke session and securely delete its stored state."""
        await self.session_store.delete_session_state(session_id)
        updated = self.repo.update_status(session_id, status=AuthenticatedSessionStatus.REVOKED)
        return updated is not None

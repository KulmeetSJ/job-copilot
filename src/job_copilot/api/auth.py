"""Authentication and Access Control dependencies for Job Copilot API and Dashboard."""

import hmac
from typing import Optional
from fastapi import Header, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from job_copilot.config import settings
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

security_bearer = HTTPBearer(auto_error=False)


def require_dashboard_auth(
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
) -> bool:
    """
    Validate access to dashboard endpoints and sensitive application operations.
    
    Security rules:
    - Production (APP_ENV=production): DASHBOARD_API_KEY MUST be configured.
      If missing, requests fail safely with 500 error rather than allowing open access.
    - Development: If DASHBOARD_API_KEY is configured, it is enforced.
      If unset, pass-through is permitted for local developer convenience.
    - Uses constant-time hmac.compare_digest to prevent timing attacks.
    - Never logs provided or configured secrets.
    """
    configured_key = settings.dashboard_api_key

    # Production safety guard: missing key must fail safely
    if settings.is_production:
        if not configured_key or not configured_key.strip():
            logger.critical("Production configuration error: DASHBOARD_API_KEY is required in production.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Server misconfigured: DASHBOARD_API_KEY is required in production.",
            )

    # In development mode without a configured key, pass-through is permitted
    if not configured_key:
        return True

    provided_key: Optional[str] = None
    if x_api_key:
        provided_key = x_api_key.strip()
    elif auth_credentials and auth_credentials.credentials:
        provided_key = auth_credentials.credentials.strip()

    if not provided_key or not hmac.compare_digest(provided_key, configured_key.strip()):
        logger.warning("Unauthorized access attempt to Job Copilot API.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing dashboard authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True

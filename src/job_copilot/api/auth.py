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
    If DASHBOARD_API_KEY is configured in settings:
      - Requires valid X-API-Key header OR Bearer token.
    If DASHBOARD_API_KEY is not configured:
      - Allows local/internal access in development mode.
    """
    configured_key = settings.dashboard_api_key
    if not configured_key:
        # In development without an explicit DASHBOARD_API_KEY, pass-through is permitted
        return True

    provided_key: Optional[str] = None
    if x_api_key:
        provided_key = x_api_key.strip()
    elif auth_credentials and auth_credentials.credentials:
        provided_key = auth_credentials.credentials.strip()

    if not provided_key or not hmac.compare_digest(provided_key, configured_key):
        logger.warning("Unauthorized access attempt to Job Copilot Dashboard API.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing dashboard authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return True

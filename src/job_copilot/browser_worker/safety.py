"""Domain security, sensitive field detection, SSRF protection, and submission safeguards."""

import ipaddress
import re
from typing import List, Optional
from urllib.parse import urlparse

from job_copilot.browser_worker.exceptions import DomainSecurityError, SubmissionSafetyError
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Default trusted job application portal domains (production public ATS platforms)
DEFAULT_ALLOWED_DOMAINS = [
    "example.com",
    "greenhouse.io",
    "boards.greenhouse.io",
    "lever.co",
    "jobs.lever.co",
    "workday.com",
    "myworkdayjobs.com",
    "ashbyhq.com",
    "jobs.ashbyhq.com",
    "smartrecruiters.com",
    "jobs.smartrecruiters.com",
    "applytojob.com",
    "rippling-ats.com",
    "bamboohr.com",
    "workable.com",
    "linkedin.com",
    "naukri.com",
    "instahyre.com",
    "wellfound.com",
    "angel.co",
]

# Sensitive input patterns requiring explicit user input
SENSITIVE_FIELD_PATTERNS = [
    r"\bsalary\b",
    r"\bcompensation\b",
    r"\bexpected\s*(?:pay|salary|rate|ctc)\b",
    r"\bcurrent\s*(?:salary|ctc)\b",
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
    r"\bgovernment\s*clearance\b",
    r"\bdisability\b",
    r"\bveteran\b",
    r"\bgender\b",
    r"\brace\b",
    r"\bethnicity\b",
    r"\byears\s*of\s*(?:experience|production)\b",
    r"\bhow\s*many\s*years\b",
]

# Strictly prohibited fields (credentials, financial details)
PROHIBITED_FIELD_PATTERNS = [
    r"\bpassword\b",
    r"\bpassphrase\b",
    r"\bssn\b",
    r"\bsocial\s*security\b",
    r"\bcredit\s*card\b",
    r"\bbank\s*account\b",
    r"\bsecurity\s*code\b",
    r"\bcvv\b",
    r"\bpin\b",
]

FORBIDDEN_HOSTNAMES = {
    "metadata.google.internal",
    "instance-data",
    "169.254.169.254",
    "metadata.azure.com",
    "100.100.100.200",
}


def is_forbidden_private_or_loopback_host(hostname: str, allow_test_fixture: bool = False) -> bool:
    """
    Check if a hostname or IP represents loopback, private RFC1918, link-local, or cloud metadata.
    """
    clean_host = hostname.strip().lower()
    
    # Check explicitly forbidden hostnames & local domain suffixes
    if clean_host in FORBIDDEN_HOSTNAMES:
        return True
    if clean_host.endswith(".internal") or clean_host.endswith(".local"):
        return not (allow_test_fixture and clean_host == "test.local")

    # Localhost / 127.0.0.1 / ::1 handling
    if clean_host in ("localhost", "127.0.0.1", "::1", "0.0.0.0"):
        return not allow_test_fixture
    if clean_host.endswith(".localhost"):
        return True

    # Try resolving/parsing as IP address
    try:
        ip = ipaddress.ip_address(clean_host)
        if ip.is_loopback:
            return not allow_test_fixture
        if ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
            return not allow_test_fixture
    except ValueError:
        pass

    return False


def validate_target_domain(
    url: str,
    allowed_domains: Optional[List[str]] = None,
    allow_test_fixture: bool = False,
) -> str:
    """
    Validate that target URL has a safe HTTP/HTTPS scheme and belongs to an allowed domain.
    Raises DomainSecurityError on forbidden schemes, private/loopback hosts, or unknown domains.
    """
    if not url or not isinstance(url, str):
        raise DomainSecurityError("Target URL must be a non-empty string.")

    url_str = url.strip()
    parsed = urlparse(url_str)
    scheme = parsed.scheme.lower()

    # Reject dangerous schemes
    if scheme not in ("http", "https"):
        raise DomainSecurityError(
            f"Disallowed URL scheme '{scheme}'. Only HTTP and HTTPS are permitted."
        )

    hostname = (parsed.hostname or "").lower()
    if not hostname:
        raise DomainSecurityError(f"Target URL '{url}' has no valid hostname.")

    # Defense-in-depth: Reject private, loopback, and cloud metadata targets
    if is_forbidden_private_or_loopback_host(hostname, allow_test_fixture=allow_test_fixture):
        raise DomainSecurityError(
            f"Security Violation: Target host '{hostname}' represents a private, loopback, or cloud metadata address."
        )

    allowed = allowed_domains or DEFAULT_ALLOWED_DOMAINS
    if allow_test_fixture:
        allowed = list(allowed) + ["localhost", "127.0.0.1", "test.local", "example.com"]

    is_allowed = any(
        hostname == domain.lower() or hostname.endswith("." + domain.lower())
        for domain in allowed
    )

    if not is_allowed:
        raise DomainSecurityError(
            f"Target domain '{hostname}' is not in the allowed job portal domain list."
        )

    return url_str


def validate_local_agent_target_url(
    url: str,
    allowed_domains: Optional[List[str]] = None,
    allow_test_fixture: bool = False,
) -> str:
    """
    Strict defense-in-depth validation executed directly on the local agent's machine
    before launching or navigating a visible browser.
    """
    return validate_target_domain(
        url=url,
        allowed_domains=allowed_domains,
        allow_test_fixture=allow_test_fixture,
    )


def is_sensitive_field(field_text: str) -> bool:
    """Check if field label or name requires human confirmation / user input."""
    if not field_text:
        return False
    text = field_text.lower()
    return any(re.search(pat, text, re.IGNORECASE) for pat in SENSITIVE_FIELD_PATTERNS)


def is_prohibited_field(field_text: str) -> bool:
    """Check if field asks for passwords, payment, or financial credentials."""
    if not field_text:
        return False
    text = field_text.lower()
    return any(re.search(pat, text, re.IGNORECASE) for pat in PROHIBITED_FIELD_PATTERNS)


def mask_sensitive_value(value: Optional[str]) -> str:
    """Mask text for inclusion in review packages without exposing sensitive data."""
    if not value:
        return ""
    if len(value) <= 4:
        return "***"
    return value[:2] + "***" + value[-2:]

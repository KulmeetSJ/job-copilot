"""Normalization engine for job descriptions, URLs, metadata, and identifiers."""

import hashlib
import html
import re
from typing import Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

from job_copilot.domain.enums import EmploymentType, RemoteStatus
from job_copilot.ingestion.models import CanonicalJob, RawJob
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "utm_id", "ref", "source", "fbclid", "gclid", "msclkid", "trk",
    "trackingid", "tracking_id", "ref_id", "refId", "li_fat_id",
    "gh_src", "src", "job_board", "jobBoard"
}


class JobNormalizer:
    """
    Normalizes raw job descriptions, cleans HTML/Unicode, strips tracking params from URLs,
    and produces deterministic CanonicalJob representations.
    """

    def normalize(self, raw_job: RawJob) -> CanonicalJob:
        """Transform raw job into normalized CanonicalJob."""
        # 1. Clean description text
        clean_desc = self.clean_text(raw_job.raw_description)

        # 2. Extract or use provided metadata
        lines = [line.strip() for line in clean_desc.split("\n") if line.strip()]
        
        company = self._clean_company_name(raw_job.company) or self._extract_company(lines, clean_desc) or "Target Company"
        title = raw_job.title or self._extract_title(lines, clean_desc) or "Software Engineer"
        location = raw_job.location or self._extract_location(lines, clean_desc)
        remote_policy = self._extract_remote_policy(clean_desc, location)
        
        # 3. Canonicalize URL
        canonical_url = self.canonicalize_url(raw_job.source_url) if raw_job.source_url else None
        
        # 4. Content Hash
        content_hash = self.compute_content_hash(clean_desc)
        
        # 5. Deterministic Job ID
        job_id = self.generate_job_id(
            source=raw_job.source,
            source_job_id=raw_job.source_job_id,
            company=company,
            title=title,
            clean_text=clean_desc,
        )

        return CanonicalJob(
            job_id=job_id,
            source=raw_job.source,
            source_job_id=raw_job.source_job_id,
            source_url=raw_job.source_url,
            canonical_url=canonical_url,
            company=company.strip(),
            title=title.strip(),
            location=location.strip() if location else None,
            remote_policy=remote_policy,
            employment_type=EmploymentType.FULL_TIME,
            clean_description=clean_desc,
            content_hash=content_hash,
            discovered_at=raw_job.discovered_at,
            retrieved_at=raw_job.retrieved_at,
            source_metadata=raw_job.source_metadata,
        )

    def clean_text(self, text: str) -> str:
        """Strip HTML, unescape unicode/html entities, and normalize whitespace."""
        if not text:
            return ""

        # Remove script and style tags completely
        cleaned = re.sub(r"<(script|style)[^>]*>[\s\S]*?</\1>", "", text, flags=re.IGNORECASE)

        # Convert breaks and list items to newlines
        cleaned = re.sub(r"<(br|p|div|li)[^>]*>", "\n", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"</(p|div|li|ul|ol|h[1-6])>", "\n", cleaned, flags=re.IGNORECASE)

        # Remove remaining HTML tags
        cleaned = re.sub(r"<[^>]+>", " ", cleaned)

        # Unescape HTML entities (e.g. &amp; -> &, &nbsp; -> ' ')
        cleaned = html.unescape(cleaned)

        # Normalize unicode whitespace (e.g. \u00a0, \u200b)
        cleaned = cleaned.replace("\u00a0", " ").replace("\u200b", "").replace("\ufeff", "")

        # Standardize bullet symbols
        cleaned = re.sub(r"^[ \t]*[•\*\-\–\—\+]\s*", "- ", cleaned, flags=re.MULTILINE)

        # Collapse excessive whitespace
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in cleaned.split("\n")]
        # Remove consecutive blank lines
        result_lines = []
        last_empty = False
        for line in lines:
            if line:
                result_lines.append(line)
                last_empty = False
            elif not last_empty:
                result_lines.append("")
                last_empty = True

        return "\n".join(result_lines).strip()

    def canonicalize_url(self, url: Optional[str]) -> Optional[str]:
        """Strip tracking query parameters and trailing slashes from URL."""
        if not url:
            return None
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return url

        parsed = urlparse(url)
        # Filter query params
        query_pairs = parse_qsl(parsed.query, keep_blank_values=False)
        clean_pairs = [(k, v) for k, v in query_pairs if k.lower() not in TRACKING_QUERY_PARAMS]
        clean_query = urlencode(clean_pairs)

        # Clean path (strip trailing slash if not root)
        path = parsed.path
        if len(path) > 1 and path.endswith("/"):
            path = path[:-1]

        clean_url = urlunparse((
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            path,
            parsed.params,
            clean_query,
            "",  # Strip fragment
        ))
        return clean_url

    def compute_content_hash(self, text: str) -> str:
        """Compute stable SHA-256 hash of normalized text."""
        # Use first 3000 chars of normalized text to create robust fingerprint
        normalized_sample = re.sub(r"\s+", " ", text.lower().strip())[:3000]
        return hashlib.sha256(normalized_sample.encode("utf-8")).hexdigest()

    def generate_job_id(
        self,
        source: str,
        source_job_id: Optional[str],
        company: str,
        title: str,
        clean_text: str,
    ) -> str:
        """
        Generate stable deterministic job ID with path safety.
        Format:
        If source_job_id: {source_slug}-{source_job_id_slug}
        Else: {company_slug}-{title_slug}-{content_hash[:6]}
        """
        if source_job_id and source_job_id.strip():
            s_slug = self._sanitize_slug(source)
            sjid_slug = self._sanitize_slug(source_job_id.strip())
            return f"{s_slug}-{sjid_slug}"

        c_slug = self._sanitize_slug(company) or "target-company"
        t_slug = self._sanitize_slug(title) or "software-engineer"
        text_hash = hashlib.sha256(clean_text.encode("utf-8")).hexdigest()[:6]
        return f"{c_slug}-{t_slug}-{text_hash}"

    def _sanitize_slug(self, text: str) -> str:
        """Sanitize string into a path-safe lowercase slug."""
        text = text.lower().strip()
        # Remove path traversal characters and non-alphanumeric
        cleaned = re.sub(r"[^a-z0-9]+", "-", text)
        return cleaned.strip("-")[:60]

    @staticmethod
    def _clean_company_name(name: Optional[str]) -> Optional[str]:
        """Sanitize and normalize company name, stripping newlines, pronouns, and extraneous punctuation."""
        if not name:
            return None
        # First non-empty line
        lines = [line.strip() for line in name.split("\n") if line.strip()]
        if not lines:
            return None
        first_line = lines[0]
        # Remove trailing sentence connectors or stop-words
        first_line = re.sub(r"[\.,;:!\?].*$", "", first_line)
        first_line = re.sub(r"\s+\b(We|You|Our|The|In|On|At|For|To|Is|Are|And)\b.*$", "", first_line, flags=re.IGNORECASE)
        # Strip extraneous punctuation
        first_line = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", first_line)
        cleaned = re.sub(r"\s+", " ", first_line).strip()
        return cleaned or None

    def _extract_company(self, lines: list[str], text: str) -> Optional[str]:
        # 1. Explicit company line
        for line in lines[:8]:
            if line.lower().startswith("company:"):
                extracted = self._clean_company_name(line.split(":", 1)[1])
                if extracted:
                    return extracted

        # 2. Header line with pipe separator (e.g. "Mastercard | Pune, India")
        for line in lines[:5]:
            if "|" in line:
                parts = [p.strip() for p in line.split("|")]
                for part in parts:
                    if part and not any(loc in part.lower() for loc in ["remote", "hybrid", "onsite", "full-time", "contract", "engineer", "developer"]):
                        if len(part.split()) <= 4 and re.match(r"^[A-Z][A-Za-z0-9 &.,'-]+$", part):
                            extracted = self._clean_company_name(part)
                            if extracted:
                                return extracted

        # 3. "at <Company>" or "with <Company>" pattern on single lines
        for line in lines[:15]:
            m = re.search(r"\b(?:at|with)\s+([A-Z][A-Za-z0-9 &.,'-]{1,40})\b", line)
            if m:
                extracted = self._clean_company_name(m.group(1))
                if extracted:
                    return extracted

        return None

    def _extract_title(self, lines: list[str], text: str) -> Optional[str]:
        for line in lines[:6]:
            if line.lower().startswith("job title:") or line.lower().startswith("role:") or line.lower().startswith("title:"):
                return line.split(":", 1)[1].strip()
        patterns = [
            r"\b(Senior\s+Backend\s+Engineer(?:\s+-\s+Java)?)\b",
            r"\b(Senior\s+Backend\s+Java\s+Engineer)\b",
            r"\b(Backend\s+Software\s+Engineer)\b",
            r"\b(Cloud\s+(?:&|and)\s+DevOps\s+Engineer)\b",
            r"\b(Principal\s+Cloud\s+DevOps\s+Engineer)\b",
            r"\b(Senior\s+Kubernetes\s+Platform\s+Engineer)\b",
            r"\b(Lead\s+Data\s+Engineer)\b",
            r"\b(Data\s+Engineer)\b",
            r"\b(Full\s+Stack\s+Engineer)\b",
            r"\b(Software\s+Engineer)\b",
            r"\b(DevOps\s+Engineer)\b",
            r"\b(Site\s+Reliability\s+Engineer)\b",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE)
            if m:
                return m.group(1).strip()
        return lines[0] if lines else "Software Engineer"

    def _extract_location(self, lines: list[str], text: str) -> Optional[str]:
        for line in lines[:8]:
            if line.lower().startswith("location:"):
                return line.split(":", 1)[1].strip()
        if re.search(r"\bremote\b", text, re.IGNORECASE):
            return "Remote"
        if re.search(r"\bhybrid\b", text, re.IGNORECASE):
            return "Hybrid"
        return None

    def _extract_remote_policy(self, text: str, location: Optional[str] = None) -> RemoteStatus:
        comb = f"{location or ''} {text}".lower()
        if re.search(r"\bremote\b", comb):
            return RemoteStatus.REMOTE
        if re.search(r"\bhybrid\b", comb):
            return RemoteStatus.HYBRID
        if re.search(r"\bon-?site\b|\bin-office\b", comb):
            return RemoteStatus.ONSITE
        return RemoteStatus.UNKNOWN

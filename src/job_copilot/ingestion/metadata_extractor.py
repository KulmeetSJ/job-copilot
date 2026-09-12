"""Comprehensive structured metadata extraction from HTML, ATS URLs, JSON-LD, OpenGraph, and raw text."""

import html
import json
import re
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlparse
from pydantic import BaseModel, Field

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ExtractedMetadata(BaseModel):
    """Structured metadata extracted from job web page or text."""
    company: Optional[str] = None
    title: Optional[str] = None
    location: Optional[str] = None
    clean_description: Optional[str] = None
    ats_name: Optional[str] = None
    source_type: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class JobMetadataExtractor:
    """
    Extracts structured job metadata preferring:
    1. Explicit ATS URL & Domain structure
    2. JSON-LD Schema.org JobPosting metadata
    3. OpenGraph / HTML Meta tags
    4. HTML <title> tag patterns
    5. Carefully bounded raw text heuristics
    """

    @classmethod
    def extract_from_html(cls, raw_html: str, url: Optional[str] = None) -> ExtractedMetadata:
        """Extract structured metadata from HTML content and source URL."""
        meta = ExtractedMetadata()

        # 1. JSON-LD Schema.org JobPosting (highest fidelity)
        cls._extract_from_json_ld(raw_html, meta)

        # 2. OpenGraph & Meta Tags
        cls._extract_from_meta_tags(raw_html, meta)

        # 3. HTML <title> Tag
        cls._extract_from_html_title(raw_html, meta)

        # 4. ATS Domain & URL Structure (fallback if missing)
        if url:
            cls._extract_from_url(url, meta)

        # 5. Clean and validate extracted values
        if meta.company:
            meta.company = cls.clean_company_name(meta.company)
        if meta.title:
            meta.title = cls.clean_title(meta.title)
        if meta.location:
            meta.location = cls.clean_location(meta.location)

        return meta

    @classmethod
    def clean_company_name(cls, name: Optional[str]) -> Optional[str]:
        """
        Sanitize and normalize company name, stripping newlines, pronouns, and extraneous prose.
        Handles cases like 'Mastercard\\nWe are...' -> 'Mastercard' without hardcoding.
        """
        if not name:
            return None

        # Take first non-empty line
        lines = [line.strip() for line in str(name).split("\n") if line.strip()]
        if not lines:
            return None
        first_line = lines[0]

        # Strip HTML tags if any leaked in
        first_line = re.sub(r"<[^>]+>", " ", first_line)
        first_line = html.unescape(first_line).strip()

        # Strip sentence endings with continuation prose (e.g. 'Mastercard. We are looking...')
        first_line = re.sub(r"(?:[\.!\?]\s+|[:;]\s*).*$", "", first_line)
        first_line = re.sub(
            r"\s+\b(We|You|Our|The|In|On|At|For|To|Is|Are|And|With|About|Careers|Jobs|Hiring)\b.*$",
            "",
            first_line,
            flags=re.IGNORECASE,
        )

        # Strip leading/trailing non-alphanumeric punctuation
        first_line = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9\.]+$", "", first_line)
        cleaned = re.sub(r"\s+", " ", first_line).strip()

        # Reject generic fallback words or sentences
        if not cleaned or len(cleaned) < 2 or len(cleaned) > 80:
            return None
        if cleaned.lower() in {"unknown", "n/a", "null", "none", "company unavailable"}:
            return None

        return cleaned

    @classmethod
    def clean_title(cls, title: Optional[str]) -> Optional[str]:
        """Sanitize job title, stripping requisition IDs, department prefixes, and HTML."""
        if not title:
            return None

        t = html.unescape(str(title)).strip()
        # Take first line
        lines = [l.strip() for l in t.split("\n") if l.strip()]
        if not lines:
            return None
        t = lines[0]

        # Strip requisition numbers like (R-12345) or [REQ-999] or - R-12345
        t = re.sub(r"[\(\[\-]\s*(?:R|REQ|Req|req|Job\s*ID|Req\s*ID)[\s\-_#:]*[0-9A-Za-z\-]+[\)\]]?", "", t)
        t = re.sub(r"\b(?:R|REQ|Req)[\-_][0-9A-Za-z]+\b", "", t)
        # Strip trailing location or pipe separators
        t = re.sub(r"\s*[-|–—]\s*(?:Remote|Hybrid|Onsite|Full[\s-]Time|Pune|Bangalore|London|New York|San Francisco|US|USA|India).*$", "", t, flags=re.IGNORECASE)
        t = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", t)
        cleaned = re.sub(r"\s+", " ", t).strip()

        if not cleaned or len(cleaned) < 2 or len(cleaned) > 120:
            return None
        if cleaned.lower() in {"software engineer", "role", "unknown", "job title"}:
            # Accept Software Engineer if extracted, but reject generic words
            return cleaned

        return cleaned

    @classmethod
    def clean_location(cls, loc: Optional[str]) -> Optional[str]:
        """Sanitize location string."""
        if not loc:
            return None
        loc_str = html.unescape(str(loc)).strip()
        lines = [l.strip() for l in loc_str.split("\n") if l.strip()]
        if not lines:
            return None
        cleaned = re.sub(r"\s+", " ", lines[0]).strip()
        cleaned = re.sub(r"^[^A-Za-z0-9]+|[^A-Za-z0-9]+$", "", cleaned)
        return cleaned or None

    @classmethod
    def _extract_from_url(cls, url: str, meta: ExtractedMetadata) -> None:
        """Parse structured company and title hints from ATS URL domains and paths."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            path = unquote(parsed.path)

            # 1. Workday: https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers/job/...
            # or https://myworkdayjobs.com/en-US/company/...
            wd_match = re.search(r"^(?:www\.)?([a-z0-9\-]+)\.(?:wd\d+|myworkdayjobs)\.myworkdayjobs\.com", domain)
            if wd_match:
                company_slug = wd_match.group(1)
                meta.ats_name = "Workday"
                meta.source_type = "workday"
                if not meta.company and company_slug:
                    meta.company = cls._slug_to_display_name(company_slug)

                # Workday path title hint: /job/.../Software-Engineer-II_R-12345
                job_match = re.search(r"/job/(?:[^/]+/)?([^/?#]+)", path)
                if job_match:
                    raw_title_slug = job_match.group(1)
                    # Strip requisition id: Software-Engineer-II_R-12345
                    title_clean = re.sub(r"_[Rr][\-_]?[0-9A-Za-z]+$", "", raw_title_slug)
                    meta.title = meta.title or cls._slug_to_display_name(title_clean)
                return

            # 2. Greenhouse: https://boards.greenhouse.io/companyname/jobs/12345
            gh_match = re.search(r"^boards\.greenhouse\.io", domain)
            if gh_match:
                meta.ats_name = "Greenhouse"
                meta.source_type = "greenhouse"
                parts = [p for p in path.split("/") if p]
                if parts and not meta.company:
                    meta.company = cls._slug_to_display_name(parts[0])
                return

            # 3. Lever: https://jobs.lever.co/companyname/uuid
            lever_match = re.search(r"^jobs\.lever\.co", domain)
            if lever_match:
                meta.ats_name = "Lever"
                meta.source_type = "lever"
                parts = [p for p in path.split("/") if p]
                if parts and not meta.company:
                    meta.company = cls._slug_to_display_name(parts[0])
                return

            # 4. Ashby: https://jobs.ashbyhq.com/companyname/uuid
            ashby_match = re.search(r"^jobs\.ashbyhq\.com", domain)
            if ashby_match:
                meta.ats_name = "Ashby"
                meta.source_type = "ashby"
                parts = [p for p in path.split("/") if p]
                if parts and not meta.company:
                    meta.company = cls._slug_to_display_name(parts[0])
                return

            # 5. SmartRecruiters: https://jobs.smartrecruiters.com/companyname/uuid
            sr_match = re.search(r"^jobs\.smartrecruiters\.com", domain)
            if sr_match:
                meta.ats_name = "SmartRecruiters"
                meta.source_type = "smartrecruiters"
                parts = [p for p in path.split("/") if p]
                if parts and not meta.company:
                    meta.company = cls._slug_to_display_name(parts[0])
                return

            # 6. Workable: https://apply.workable.com/companyname/j/id
            workable_match = re.search(r"^apply\.workable\.com", domain)
            if workable_match:
                meta.ats_name = "Workable"
                meta.source_type = "workable"
                parts = [p for p in path.split("/") if p]
                if parts and not meta.company:
                    meta.company = cls._slug_to_display_name(parts[0])
                return

            # 7. Generic careers domain: careers.company.com or company.com/careers
            if domain.startswith("careers."):
                sub = domain.replace("careers.", "").split(".")[0]
                if not meta.company and sub:
                    meta.company = cls._slug_to_display_name(sub)
        except Exception as e:
            logger.debug(f"URL parsing notice for '{url}': {e}")

    @classmethod
    def _extract_from_json_ld(cls, raw_html: str, meta: ExtractedMetadata) -> None:
        """Parse schema.org JobPosting JSON-LD script tags."""
        if not raw_html or "<script" not in raw_html:
            return

        json_ld_matches = re.findall(
            r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>([\s\S]*?)</script>',
            raw_html,
            flags=re.IGNORECASE,
        )

        for raw_json in json_ld_matches:
            try:
                data = json.loads(raw_json.strip())
                postings = []
                if isinstance(data, dict):
                    if data.get("@type") in ["JobPosting", "jobposting", "Job"]:
                        postings.append(data)
                    elif "@graph" in data and isinstance(data["@graph"], list):
                        for item in data["@graph"]:
                            if isinstance(item, dict) and item.get("@type") in ["JobPosting", "jobposting", "Job"]:
                                postings.append(item)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict) and item.get("@type") in ["JobPosting", "jobposting", "Job"]:
                            postings.append(item)

                for p in postings:
                    # Title
                    if not meta.title and p.get("title"):
                        meta.title = str(p.get("title"))

                    # Company / Organization
                    org = p.get("hiringOrganization")
                    if org:
                        if isinstance(org, dict) and org.get("name"):
                            meta.company = str(org.get("name"))
                        elif isinstance(org, str):
                            meta.company = org

                    # Location
                    job_loc = p.get("jobLocation")
                    if job_loc:
                        if isinstance(job_loc, dict):
                            addr = job_loc.get("address")
                            if isinstance(addr, dict):
                                parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                                meta.location = ", ".join([str(x) for x in parts if x])
                            elif isinstance(addr, str):
                                meta.location = addr
                            elif job_loc.get("name"):
                                meta.location = str(job_loc.get("name"))
                        elif isinstance(job_loc, list) and job_loc:
                            first_loc = job_loc[0]
                            if isinstance(first_loc, dict) and first_loc.get("name"):
                                meta.location = str(first_loc.get("name"))

                    # Description
                    if p.get("description"):
                        meta.clean_description = str(p.get("description"))

                    meta.metadata["json_ld"] = p
                    return
            except Exception:
                continue

    @classmethod
    def _extract_from_meta_tags(cls, raw_html: str, meta: ExtractedMetadata) -> None:
        """Extract OpenGraph and standard HTML meta tags."""
        if not raw_html:
            return

        meta_tags = re.findall(
            r'<meta[^>]+(?:name|property)=["\']([^"\']+)["\'][^>]+content=["\']([^"\']*)["\']',
            raw_html,
            flags=re.IGNORECASE,
        )
        # Also handle content before name/property
        meta_tags += re.findall(
            r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+(?:name|property)=["\']([^"\']+)["\']',
            raw_html,
            flags=re.IGNORECASE,
        )

        for tag, val in meta_tags:
            t = tag.lower().strip()
            v = val.strip()
            if not v:
                continue

            if t in ["og:site_name", "author", "company", "twitter:creator"] and not meta.company:
                meta.company = v
            elif t in ["og:title", "twitter:title"] and not meta.title:
                meta.title = v
            elif t in ["og:description", "description"] and not meta.clean_description:
                meta.clean_description = v

    @classmethod
    def _extract_from_html_title(cls, raw_html: str, meta: ExtractedMetadata) -> None:
        """Parse page <title> tag for role and company combinations."""
        if not raw_html or "<title" not in raw_html.lower():
            return

        title_match = re.search(r"<title[^>]*>([\s\S]*?)</title>", raw_html, flags=re.IGNORECASE)
        if not title_match:
            return

        page_title = html.unescape(title_match.group(1)).strip()
        if not page_title:
            return

        # Common Title Formats:
        # 1. "Software Engineer II at Mastercard"
        m1 = re.match(r"^(.+?)\s+at\s+([A-Za-z0-9 &.,'-]+?)(?:\s*[-|–—].*)?$", page_title, flags=re.IGNORECASE)
        if m1:
            meta.title = meta.title or m1.group(1).strip()
            meta.company = meta.company or m1.group(2).strip()
            return

        # 2. "Software Engineer II - Mastercard Careers - Workday" or "Software Engineer - Mastercard"
        m2 = re.match(r"^(.+?)\s*[-|–—]\s*([A-Za-z0-9 &.,'-]+?)(?:\s+Careers|\s+Jobs|\s+Workday|\s+Greenhouse|\s+Lever)?$", page_title, flags=re.IGNORECASE)
        if m2:
            cand_title = m2.group(1).strip()
            cand_comp = m2.group(2).strip()
            if cls._looks_like_role(cand_title):
                meta.title = meta.title or cand_title
                meta.company = meta.company or cand_comp
                return

        # 3. "Mastercard Careers - Software Engineer II"
        m3 = re.match(r"^([A-Za-z0-9 &.,'-]+?)\s+(?:Careers|Jobs)\s*[-|–—]\s*(.+)$", page_title, flags=re.IGNORECASE)
        if m3:
            meta.company = meta.company or m3.group(1).strip()
            meta.title = meta.title or m3.group(2).strip()
            return

        # 4. "Mastercard - Software Engineer II"
        m4 = re.match(r"^([A-Za-z0-9 &.,'-]+?)\s*[-|–—]\s*(.+)$", page_title)
        if m4:
            cand_first = m4.group(1).strip()
            cand_second = m4.group(2).strip()
            if cls._looks_like_role(cand_second):
                meta.company = meta.company or cand_first
                meta.title = meta.title or cand_second
            elif cls._looks_like_role(cand_first):
                meta.title = meta.title or cand_first
                meta.company = meta.company or cand_second

    @staticmethod
    def _looks_like_role(text: str) -> bool:
        """Check if text contains common engineering role keywords."""
        keywords = [
            "engineer", "developer", "architect", "lead", "manager", "director",
            "specialist", "scientist", "consultant", "analyst", "intern", "sre",
            "devops", "qa", "tester", "programmer", "administrator"
        ]
        t = text.lower()
        return any(k in t for k in keywords)

    @staticmethod
    def _slug_to_display_name(slug: str) -> str:
        """Convert slug like 'mastercard' or 'software-engineer-ii' to display name."""
        words = re.split(r"[-_]+", slug.strip())
        capitalized = []
        for w in words:
            if not w:
                continue
            if w.lower() in {"ii", "iii", "iv", "vi", "vii", "viii", "ix", "x"}:
                capitalized.append(w.upper())
            elif w.lower() in {"sre", "qa", "swe", "devops", "ai", "ml", "api", "ui", "ux", "hr"}:
                capitalized.append(w.upper())
            else:
                capitalized.append(w.capitalize())
        return " ".join(capitalized)

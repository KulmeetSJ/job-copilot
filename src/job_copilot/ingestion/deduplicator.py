"""Deduplication Engine with multi-signal identity, URL canonicalization, and safe heuristics."""

import re
from typing import List, Optional, Set, Tuple
from job_copilot.ingestion.models import CanonicalJob
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobDeduplicator:
    """
    Evaluates new CanonicalJob candidates against existing store jobs to identify duplicates.
    Prioritizes deterministic identifiers first, then canonical URLs, then content hashes,
    and finally safe domain-aware similarity signals.
    """

    def check_duplicate(
        self,
        candidate: CanonicalJob,
        existing_jobs: List[CanonicalJob],
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Check if candidate job is a duplicate of any existing job.
        Returns:
            (is_duplicate: bool, canonical_job_id: Optional[str], reason: Optional[str])
        """
        cand_source_id = f"{candidate.source}:{candidate.source_job_id}" if candidate.source_job_id else None
        cand_url = candidate.canonical_url.lower() if candidate.canonical_url else None
        cand_hash = candidate.content_hash
        cand_comp = self._norm_str(candidate.company)
        cand_title = self._norm_str(candidate.title)
        cand_loc = self._norm_str(candidate.location or "")

        for existing in existing_jobs:
            if existing.job_id == candidate.job_id:
                return True, existing.job_id, "Exact job_id match"

            # 1. Exact Source & Source Job ID Match
            if candidate.source_job_id and existing.source_job_id:
                if candidate.source == existing.source and candidate.source_job_id == existing.source_job_id:
                    return True, existing.job_id, f"Identical source and source_job_id ({candidate.source}:{candidate.source_job_id})"

            # 2. Canonical URL Match (after stripping UTM/tracking noise)
            if cand_url and existing.canonical_url:
                if cand_url == existing.canonical_url.lower():
                    return True, existing.job_id, f"Identical canonical URL ({candidate.canonical_url})"

            # 3. Exact Content Hash Match
            if cand_hash == existing.content_hash:
                return True, existing.job_id, "Identical normalized job description content hash"

            # 4. Safe Heuristic Similarity Check
            ex_comp = self._norm_str(existing.company)
            ex_title = self._norm_str(existing.title)
            ex_loc = self._norm_str(existing.location or "")

            # If company and title are identical, inspect location and description
            if cand_comp and ex_comp and cand_comp == ex_comp:
                if cand_title and ex_title and cand_title == ex_title:
                    # Location Guard: Do NOT merge if locations are clearly different cities
                    if self._is_location_conflict(cand_loc, ex_loc):
                        continue

                    # Calculate token Jaccard similarity of descriptions
                    sim = self._text_similarity(candidate.clean_description, existing.clean_description)
                    if sim >= 0.85:
                        return (
                            True,
                            existing.job_id,
                            f"Heuristic match: same company ('{candidate.company}'), title ('{candidate.title}'), and {round(sim * 100, 1)}% description similarity",
                        )

        return False, None, None

    def _norm_str(self, text: str) -> str:
        """Normalize string for fuzzy comparison."""
        cleaned = re.sub(r"[^a-zA-Z0-9]+", " ", text.lower()).strip()
        return cleaned

    def _is_location_conflict(self, loc1: str, loc2: str) -> bool:
        """
        Check if two location strings conflict (e.g. Pune vs Bangalore).
        Returns True if locations are distinct non-remote locations.
        """
        if not loc1 or not loc2:
            return False
        if "remote" in loc1 or "remote" in loc2:
            return False
        
        # Check known distinct tech hubs
        hubs = ["pune", "bangalore", "bengaluru", "hyderabad", "mumbai", "delhi", "gurgaon", "noida", "chennai", "san francisco", "new york", "london", "singapore"]
        hubs1 = {h for h in hubs if h in loc1}
        hubs2 = {h for h in hubs if h in loc2}
        
        if hubs1 and hubs2 and hubs1 != hubs2:
            return True
            
        return False

    def _text_similarity(self, text1: str, text2: str) -> float:
        """Calculate word-level Jaccard similarity between two texts."""
        tokens1 = set(re.findall(r"\b\w{3,}\b", text1.lower()))
        tokens2 = set(re.findall(r"\b\w{3,}\b", text2.lower()))
        if not tokens1 or not tokens2:
            return 0.0
        intersection = len(tokens1.intersection(tokens2))
        union = len(tokens1.union(tokens2))
        return intersection / union if union > 0 else 0.0

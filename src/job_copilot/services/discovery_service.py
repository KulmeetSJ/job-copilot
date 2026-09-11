"""Job Discovery & Ingestion Orchestration Service."""

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml

from job_copilot.ingestion.deduplicator import JobDeduplicator
from job_copilot.ingestion.models import (
    CanonicalJob,
    DiscoveryQuery,
    DiscoveryResult,
    JobIndexEntry,
    JobLifecycleStatus,
    RawJob,
)
from job_copilot.ingestion.normalizer import JobNormalizer
from job_copilot.ingestion.sources.base import JobSource
from job_copilot.ingestion.sources.feed import FeedJobSource
from job_copilot.ingestion.sources.manual import ManualJobSource
from job_copilot.ingestion.sources.url import UrlJobSource
from job_copilot.ingestion.store import JobStore
from job_copilot.matching.models import JobAssessment
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class DiscoveryService:
    """
    High-level orchestration service for Phase 5 Job Discovery & Ingestion.
    Coordinates:
      - Multi-source adapters (Manual, URL, Feed)
      - Deterministic normalization & cleaning
      - Deduplication across sources & URLs
      - Job store persistence & index management
      - Phase 4 Job Intelligence integration & ranking
    """

    def __init__(
        self,
        jobs_data_dir: Optional[Path] = None,
        preferences_path: Optional[Path] = None,
        job_intelligence_service: Optional[JobIntelligenceService] = None,
    ):
        self.jobs_data_dir = jobs_data_dir or Path("data/jobs")
        self.preferences_path = preferences_path or Path("data/candidate/preferences.yaml")
        
        self.store = JobStore(base_dir=self.jobs_data_dir)
        self.normalizer = JobNormalizer()
        self.deduplicator = JobDeduplicator()
        self.intelligence_service = job_intelligence_service or JobIntelligenceService(jobs_data_dir=self.jobs_data_dir)

        # Registered sources
        self.manual_source = ManualJobSource()
        self.url_source = UrlJobSource()
        self.sources: Dict[str, JobSource] = {
            "manual": self.manual_source,
            "url": self.url_source,
        }

    def register_source(self, source: JobSource) -> None:
        """Register a custom job source adapter."""
        self.sources[source.name] = source

    def load_default_query_from_preferences(self) -> DiscoveryQuery:
        """Derive search query defaults from candidate preferences.yaml."""
        if not self.preferences_path.exists():
            return DiscoveryQuery(
                keywords=["Software Engineer", "Backend Engineer"],
                locations=["Pune", "Bangalore", "Remote"],
            )

        try:
            with open(self.preferences_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            pref = data.get("preferences", {})
            pos = data.get("resume_positioning", {})

            keywords = pref.get("target_roles", ["Software Engineer"])
            locations = [loc.split(",")[0].strip() for loc in pref.get("preferred_locations", ["Remote"])]
            strategies = list(pos.keys())
            remote_pref = pref.get("remote_preference", "HYBRID") != "ONSITE"

            return DiscoveryQuery(
                keywords=keywords,
                locations=locations,
                strategies=strategies,
                domains=["Fintech", "Payments", "Banking"],
                remote_preferred=remote_pref,
            )
        except Exception as e:
            logger.warning(f"Error loading preferences: {e}. Using standard defaults.")
            return DiscoveryQuery(
                keywords=["Software Engineer", "Backend Engineer"],
                locations=["Pune", "Bangalore", "Remote"],
            )

    def ingest_raw_job(self, raw_job: RawJob) -> CanonicalJob:
        """
        Normalize, deduplicate, and persist a single raw job.
        """
        # 1. Normalize
        canonical = self.normalizer.normalize(raw_job)

        # 2. Check for duplicate against existing jobs
        existing_jobs = self.store.list_canonical_jobs(include_duplicates=True)
        is_dup, canonical_id, reason = self.deduplicator.check_duplicate(canonical, existing_jobs)

        if is_dup:
            canonical.lifecycle_status = JobLifecycleStatus.DUPLICATE
            canonical.duplicate_of = canonical_id
            canonical.duplicate_reason = reason
            logger.info(f"Job {canonical.job_id} identified as DUPLICATE of {canonical_id} ({reason})")

        # 3. Persist Raw and Canonical Job
        self.store.save_raw_job(canonical.job_id, raw_job)
        self.store.save_canonical_job(canonical)

        return canonical

    def ingest_file(
        self,
        file_path: str,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
    ) -> Optional[CanonicalJob]:
        """Ingest job description from local file."""
        raw_job = self.manual_source.fetch(file_path)
        if not raw_job:
            return None
        if company:
            raw_job.company = company
        if title:
            raw_job.title = title
        if location:
            raw_job.location = location

        return self.ingest_raw_job(raw_job)

    def ingest_text(
        self,
        text: str,
        company: Optional[str] = None,
        title: Optional[str] = None,
        location: Optional[str] = None,
        source_url: Optional[str] = None,
        source_job_id: Optional[str] = None,
    ) -> CanonicalJob:
        """Ingest job description from text string."""
        raw_job = self.manual_source.ingest_text(
            text=text,
            company=company,
            title=title,
            location=location,
            source_url=source_url,
            source_job_id=source_job_id,
        )
        return self.ingest_raw_job(raw_job)

    def ingest_url(self, url: str) -> Optional[CanonicalJob]:
        """Fetch and ingest job description from public URL."""
        raw_job = self.url_source.fetch(url)
        if not raw_job:
            return None
        return self.ingest_raw_job(raw_job)

    def discover_jobs(self, query: Optional[DiscoveryQuery] = None) -> DiscoveryResult:
        """
        Execute discovery query across all registered discoverable sources.
        """
        active_query = query or self.load_default_query_from_preferences()
        result = DiscoveryResult(query=active_query)

        all_raw_jobs: List[RawJob] = []

        for name, source in self.sources.items():
            if source.source_type in ("manual", "url"):
                continue  # Skip point-to-point ingestion sources during broadcast discovery
            try:
                found = source.discover(active_query)
                all_raw_jobs.extend(found)
                result.jobs_discovered += len(found)
            except Exception as e:
                logger.error(f"Discovery error in source '{name}': {e}")
                result.failed_sources[name] = str(e)

        # Process and store discovered jobs
        for raw in all_raw_jobs:
            canonical = self.ingest_raw_job(raw)
            result.jobs.append(canonical)
            if canonical.lifecycle_status == JobLifecycleStatus.DUPLICATE:
                result.duplicates_found += 1
            else:
                result.jobs_new += 1

        return result

    def process_job(self, job_id: str) -> Optional[JobAssessment]:
        """
        Bridge to Phase 4: Run stored job through the Phase 4 Job Intelligence Engine.
        """
        canonical = self.store.get_canonical_job(job_id)
        if not canonical:
            logger.warning(f"Job ID '{job_id}' not found in job store.")
            return None

        # Execute Phase 4 evaluation
        assessment = self.intelligence_service.evaluate_job(
            raw_text=canonical.clean_description,
            source=canonical.source,
            source_url=canonical.source_url,
            company_override=canonical.company,
            title_override=canonical.title,
            save_artifacts=True,
        )

        # Update Phase 5 store index with assessment results
        self.store.update_phase_4_status(
            job_id=job_id,
            overall_score=assessment.score_breakdown.overall_score,
            recommendation=assessment.recommendation.value,
            recommended_strategy=assessment.recommended_strategy,
        )

        return assessment

    def list_jobs(
        self,
        status: Optional[str] = None,
        min_score: Optional[float] = None,
        recommendation: Optional[str] = None,
        strategy: Optional[str] = None,
        include_duplicates: bool = False,
    ) -> List[JobIndexEntry]:
        """List and filter jobs from index."""
        index = self.store.load_index()
        entries = list(index.values())

        filtered: List[JobIndexEntry] = []
        for entry in entries:
            if not include_duplicates and entry.lifecycle_status == JobLifecycleStatus.DUPLICATE.value:
                continue
            if status and entry.lifecycle_status.upper() != status.upper():
                continue
            if min_score is not None:
                if entry.overall_fit_score is None or entry.overall_fit_score < min_score:
                    continue
            if recommendation and entry.recommendation != recommendation.upper():
                continue
            if strategy and entry.recommended_strategy != strategy:
                continue

            filtered.append(entry)

        return filtered

    def rank_jobs(self, include_duplicates: bool = False) -> List[JobIndexEntry]:
        """
        Return jobs ranked primarily by Phase 4 overall_fit_score descending.
        Evaluated jobs (with scores) appear at top; un-evaluated jobs follow.
        """
        jobs = self.list_jobs(include_duplicates=include_duplicates)

        def sort_key(entry: JobIndexEntry) -> tuple:
            score = entry.overall_fit_score if entry.overall_fit_score is not None else -1.0
            # Recommendations weighting
            rec_weight = {
                "STRONG_APPLY": 5,
                "APPLY": 4,
                "REVIEW": 3,
                "LOW_PRIORITY": 2,
                "SKIP": 1,
            }.get(entry.recommendation or "", 0)
            return (rec_weight, score, entry.discovered_at)

        return sorted(jobs, key=sort_key, reverse=True)

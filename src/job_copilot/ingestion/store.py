"""Job Store and Index Persistence Layer for discovered and ingested jobs."""

import json
from pathlib import Path
import re
from typing import Dict, List, Optional
from job_copilot.ingestion.models import CanonicalJob, JobIndexEntry, JobLifecycleStatus, RawJob
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class JobStore:
    """
    Persistent storage and indexing manager for jobs across all lifecycle states.
    Manages structured folders on disk:
      - data/jobs/raw/
      - data/jobs/normalized/
      - data/jobs/analyzed/
      - data/jobs/matched/
      - data/jobs/recommendations/
      - data/jobs/index.json
    """

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path("data/jobs")
        self.raw_dir = self.base_dir / "raw"
        self.normalized_dir = self.base_dir / "normalized"
        self.analyzed_dir = self.base_dir / "analyzed"
        self.matched_dir = self.base_dir / "matched"
        self.rec_dir = self.base_dir / "recommendations"
        self.index_file = self.base_dir / "index.json"

        # Ensure directory structure exists
        for d in [self.raw_dir, self.normalized_dir, self.analyzed_dir, self.matched_dir, self.rec_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self._index_cache: Optional[Dict[str, JobIndexEntry]] = None

    def _sanitize_job_id(self, job_id: str) -> str:
        """Sanitize job_id to prevent path traversal attacks."""
        if ".." in job_id or "/" in job_id or "\\" in job_id:
            raise ValueError(f"Invalid or unsafe job ID: {job_id}")
        cleaned = re.sub(r"[^a-zA-Z0-9_\-\.]+", "-", job_id).strip("-")
        if not cleaned:
            raise ValueError(f"Invalid or unsafe job ID: {job_id}")
        return cleaned

    def load_index(self, reload: bool = False) -> Dict[str, JobIndexEntry]:
        """Load the searchable job index from disk."""
        if self._index_cache is not None and not reload:
            return self._index_cache

        if not self.index_file.exists():
            self._index_cache = {}
            return self._index_cache

        try:
            data = json.loads(self.index_file.read_text(encoding="utf-8"))
            self._index_cache = {
                k: JobIndexEntry.model_validate(v) for k, v in data.items()
            }
        except Exception as e:
            logger.error(f"Failed to read job index at {self.index_file}: {e}")
            self._index_cache = {}

        return self._index_cache

    def save_index(self) -> None:
        """Save in-memory index to disk atomically."""
        if self._index_cache is None:
            return
        data = {k: v.model_dump() for k, v in self._index_cache.items()}
        temp_file = self.index_file.with_suffix(".tmp")
        temp_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp_file.replace(self.index_file)

    def save_raw_job(self, job_id: str, raw_job: RawJob) -> Path:
        """Persist raw job description and metadata."""
        safe_id = self._sanitize_job_id(job_id)
        # 1. Save raw text
        txt_path = self.raw_dir / f"{safe_id}.txt"
        txt_path.write_text(raw_job.raw_description, encoding="utf-8")

        # 2. Save raw metadata JSON
        json_path = self.raw_dir / f"{safe_id}.json"
        json_path.write_text(raw_job.model_dump_json(indent=2), encoding="utf-8")
        return txt_path

    def save_canonical_job(self, job: CanonicalJob) -> Path:
        """Persist normalized CanonicalJob and update index."""
        safe_id = self._sanitize_job_id(job.job_id)
        path = self.normalized_dir / f"{safe_id}.json"
        path.write_text(job.model_dump_json(indent=2), encoding="utf-8")

        # Update index, preserving Phase 4 evaluation data if present
        index = self.load_index()
        existing = index.get(job.job_id)
        index[job.job_id] = JobIndexEntry(
            job_id=job.job_id,
            source=job.source,
            source_url=job.source_url,
            company=job.company,
            title=job.title,
            location=job.location,
            remote_policy=job.remote_policy.value,
            lifecycle_status=job.lifecycle_status.value,
            duplicate_of=job.duplicate_of,
            overall_fit_score=existing.overall_fit_score if existing else None,
            recommendation=existing.recommendation if existing else None,
            recommended_strategy=existing.recommended_strategy if existing else None,
            discovered_at=job.discovered_at.isoformat(),
            updated_at=job.updated_at.isoformat(),
        )
        self.save_index()
        return path

    def get_canonical_job(self, job_id: str) -> Optional[CanonicalJob]:
        """Load normalized job by ID from disk."""
        try:
            safe_id = self._sanitize_job_id(job_id)
        except ValueError:
            return None
        path = self.normalized_dir / f"{safe_id}.json"
        if not path.exists():
            return None
        try:
            return CanonicalJob.model_validate_json(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.error(f"Error loading canonical job {job_id}: {e}")
            return None

    def get_raw_job_text(self, job_id: str) -> Optional[str]:
        """Retrieve raw job text by ID."""
        try:
            safe_id = self._sanitize_job_id(job_id)
        except ValueError:
            return None
        txt_path = self.raw_dir / f"{safe_id}.txt"
        if txt_path.exists():
            return txt_path.read_text(encoding="utf-8")
        return None

    def list_canonical_jobs(self, include_duplicates: bool = True) -> List[CanonicalJob]:
        """Load all canonical jobs stored in normalized directory."""
        jobs: List[CanonicalJob] = []
        for file in sorted(self.normalized_dir.glob("*.json")):
            try:
                job = CanonicalJob.model_validate_json(file.read_text(encoding="utf-8"))
                if not include_duplicates and job.lifecycle_status == JobLifecycleStatus.DUPLICATE:
                    continue
                jobs.append(job)
            except Exception as e:
                logger.error(f"Failed reading {file}: {e}")
        return jobs

    def update_phase_4_status(
        self,
        job_id: str,
        overall_score: float,
        recommendation: str,
        recommended_strategy: str,
    ) -> None:
        """Update job index with Phase 4 evaluation results."""
        # Update canonical job JSON on disk if present
        job = self.get_canonical_job(job_id)
        if job:
            job.lifecycle_status = JobLifecycleStatus.RECOMMENDED
            safe_id = self._sanitize_job_id(job.job_id)
            path = self.normalized_dir / f"{safe_id}.json"
            path.write_text(job.model_dump_json(indent=2), encoding="utf-8")

        index = self.load_index()
        if job_id in index:
            entry = index[job_id]
            entry.overall_fit_score = overall_score
            entry.recommendation = recommendation
            entry.recommended_strategy = recommended_strategy
            entry.lifecycle_status = JobLifecycleStatus.RECOMMENDED.value
            self.save_index()

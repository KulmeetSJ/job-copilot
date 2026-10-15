"""Featured job definitions and fixtures.

DEPRECATION NOTICE:
Fabricated/demo-like curated jobs with hardcoded match scores, generic career URLs,
and synthetic tracking IDs have been removed. Live featured openings must be populated
exclusively from genuine, ingested job records.

CURATED_FEATURED_JOBS is maintained as an empty mapping for backwards-compatibility
to ensure no synthetic fixture records can ever be seeded into the database or dashboard.
"""

from typing import Any, Dict

CURATED_FEATURED_JOBS: Dict[str, Dict[str, Any]] = {}

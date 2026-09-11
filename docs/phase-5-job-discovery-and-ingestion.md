# Phase 5 — Job Discovery & Ingestion Engine

## 1. Overview & Architecture

Phase 5 introduces the **Job Discovery & Ingestion Engine** to Job Copilot. It automatically discovers, ingests, normalizes, deduplicates, and stores job postings from diverse external sources (local files, public URLs, career page feeds), and routes clean jobs into the Phase 4 Job Intelligence Engine for multi-dimensional evaluation and ranking.

```
                      JOB SOURCES
                           │
      ┌────────────────────┼────────────────────┐
      │                    │                    │
 Manual File / Text    Direct URL        Public Feed / API
 (ManualJobSource)   (UrlJobSource)       (FeedJobSource)
      │                    │                    │
      └────────────────────┼────────────────────┘
                           ▼
                  ┌─────────────────┐
                  │ Source Adapter  │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ RawJob (Source) │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ JobNormalizer   │
                  │ (CanonicalJob)  │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ JobDeduplicator │
                  │ (Identity/URL)  │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ JobStore        │
                  │ (Disk & Index)  │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Phase 4 Service │
                  │ (Evaluate &     │
                  │  Rank)          │
                  └────────┬────────┘
                           ▼
                  ┌─────────────────┐
                  │ Ranked Jobs     │
                  └─────────────────┘
```

---

## 2. Core Components

### A. Source Adapters (`src/job_copilot/ingestion/sources/`)
- `JobSource` (ABC): Defines the interface for all adapters (`discover(query)` and `fetch(id_or_url)`).
- `ManualJobSource`: Ingests from local text files or raw string input.
- `UrlJobSource`: Fetches permitted public job postings via standard HTTP GET with timeout, standard headers, and error handling.
- `FeedJobSource`: Queries structured JSON feeds, career feeds, or in-memory feeds for batch discovery.

### B. Normalization Engine (`src/job_copilot/ingestion/normalizer.py`)
- Strips HTML tags, unescapes HTML entities, normalizes unicode whitespace, and formats bullet points.
- Canonicalizes URLs by stripping tracking query parameters (`utm_*`, `ref`, `source`, `fbclid`, `trk`, `trackingId`, etc.).
- Computes stable `SHA-256` content hashes.
- Generates path-safe deterministic job IDs.

### C. Deduplication Engine (`src/job_copilot/ingestion/deduplicator.py`)
- Identifies duplicates using a tiered hierarchy of evidence:
  1. Exact source + source job ID match.
  2. Canonical URL match (normalized without tracking noise).
  3. Exact content hash match.
  4. Heuristic similarity match (same company + normalized title + Jaccard token description similarity $\ge 85\%$).
- **Safety**: Never merges roles in different non-remote cities (e.g., Pune vs Bangalore) or distinct domains.

### D. Persistent Job Store & Index (`src/job_copilot/ingestion/store.py`)
- Directory structure:
  - `data/jobs/raw/<job_id>.txt` & `<job_id>.json`
  - `data/jobs/normalized/<job_id>.json`
  - `data/jobs/analyzed/<job_id>.json` (Phase 4)
  - `data/jobs/matched/<job_id>.json` (Phase 4)
  - `data/jobs/recommendations/<job_id>.json` (Phase 4)
  - `data/jobs/index.json` (Searchable indexed registry)
- Prevents silent historical deletion.
- Path traversal sanitization on all job IDs.

### E. Phase 4 Intelligence Integration & Ranking (`src/job_copilot/services/discovery_service.py`)
- `process_job(job_id)`: Bridges directly to Phase 4 `JobIntelligenceService.evaluate_job` to generate 7-dimensional scores, requirement matches, and recommendations.
- `rank_jobs()`: Returns indexed jobs ordered by Phase 4 fit scores and recommendation tiers (`STRONG_APPLY` > `APPLY` > `REVIEW` > `LOW_PRIORITY` > `SKIP`).

---

## 3. CLI Commands

```bash
# 1. Ingest a raw job description file
python -m job_copilot ingest-job data/sample_jds/java_backend_jd.txt

# 2. Ingest from a public URL
python -m job_copilot ingest-url "https://jobs.example.com/posting/12345"

# 3. Discover jobs matching criteria or candidate preferences
python -m job_copilot discover-jobs --keyword "Backend Engineer" --location "Pune,Remote"

# 4. List and rank all stored jobs
python -m job_copilot list-jobs

# 5. Process a stored job with Phase 4 Intelligence
python -m job_copilot process-job manual-java-backend-jd
```

---

## 4. FastAPI Endpoints

- `POST /api/jobs/ingest`: Ingest raw job description text.
- `POST /api/jobs/ingest-url`: Ingest from a public URL.
- `POST /api/jobs/discover`: Run batch discovery query across configured sources.
- `GET /api/jobs`: List, filter, and rank stored jobs.
- `GET /api/jobs/{job_id}`: Retrieve canonical job record.
- `POST /api/jobs/{job_id}/process`: Process stored job with Phase 4 Intelligence and update score index.

---

## 5. Truth & Claim Safety Invariants

1. **Candidate Truth Immutability**: External JDs are treated as untrusted external data. No skill or requirement in an external JD is ever written to `master_profile.yaml` or candidate evidence.
2. **No Scraping Bypasses**: No anti-bot evasion, CAPTCHA hacking, or terms-of-service violations.
3. **No LLM Dependency**: Normalization, deduplication, indexing, and ranking operate 100% deterministically offline.

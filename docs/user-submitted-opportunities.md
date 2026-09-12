# User-Submitted Job Opportunities ("Found a job yourself?")

## Feature Overview
Job Copilot enables candidates to directly submit job postings discovered outside automated searches (e.g. from company careers pages, job boards, or direct referrals). When a candidate pastes a job URL into the dashboard, Job Copilot immediately ingests the opportunity, assesses fit against Candidate Truth, selects the optimal resume strategy, generates tailored resume artifacts, and stages the application for human review without requiring the candidate to wait for scheduled discovery runs.

---

## Candidate Experience Flow

```
+-------------------------------------------------------------+
| Found a job yourself?                                       |
| [ https://jobs.lever.co/stripe/staff-backend-engineer ]     |
|                                     [ Analyze Opportunity ] |
+-------------------------------------------------------------+
                              |
                              v
                  [ Reading job posting ]
                              |
                              v
              [ Understanding requirements ]
                              |
                              v
                [ Matching your profile ]
                              |
                              v
                  [ Tailoring resume ]
                              |
                              v
                [ Preparing application ]
                              |
                              v
               [ STAGED AT READY_FOR_REVIEW ]
                              |
        +---------------------+---------------------+
        |                     |                     |
        v                     v                     v
[ View Opportunity ]  [ Download Resume ]  [ Review Application ]
                                                    |
                                                    v
                                      [ Human Review & Edits ]
                                                    |
                                                    v
                                      [ Explicit "SUBMIT" Confirmation ]
```

---

## Core Capabilities

### 1. URL Security & SSRF Protection
- **Scheme Validation**: Strictly allows only `http://` and `https://` protocols. Rejects `file://`, `javascript:`, `data:`, `ftp://`, and arbitrary schemes.
- **SSRF Defenses**: Rejects loopback addresses (`localhost`, `127.0.0.1`, `::1`), private IPv4 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local metadata addresses (`169.254.169.254`), and internal `.local` / `.internal` hostnames.
- **Safe Error Reporting**: When an invalid or inaccessible domain is provided, returns user-friendly guidance:
  > *"This job site isn't currently supported for automated processing."* or *"Couldn't reliably read this job posting."*

### 2. Ingestion & Provenance
- Reuses the authoritative `UrlJobSource` abstraction.
- Provenance is recorded as `USER_SUBMITTED_URL` and displayed in the UI as **"Added by you"** (preserving clear separation from scheduled scrapers/feeds).
- Normalized content is stored in the canonical job store with unique SHA-256 content hashes.

### 3. Deduplication
- Runs through `JobDeduplicator` against all existing records.
- If a duplicate job is identified:
  - Preserves existing application and job history without creating duplicate records.
  - Returns a user notification: *"This opportunity is already in Job Copilot."* with a direct **[ View Existing Opportunity ]** action.

### 4. 7-Dimensional Fit Scoring & Truth Safety
- Evaluates the job description using `JobIntelligenceService` across 7 dimensions:
  1. Technical Stack Match
  2. Core Responsibilities Alignment
  3. Role & Seniority Fit
  4. Verified Professional Evidence
  5. Industry Domain Background
  6. Candidate Preferences
  7. Credentials & Education
- **Truth Invariant**: Candidate Truth profiles (`master_profile.yaml`, `evidence.yaml`, `preferences.yaml`) remain strictly read-only. Manual URL submission does not artificially boost match scores.

### 5. Resume Tailoring & Artifact Downloads
- Automatically selects the best-fitting Phase 3 resume strategy (e.g. `backend_java`, `cloud_infrastructure`, `data_engineering`, `engineering_leadership`).
- Generates tailored LaTeX source and compiled PDF resume.
- Persists files in Object Storage & PostgreSQL via `ArtifactService`.
- Provides an authorized one-click **[ Download Resume ]** link for the candidate.

### 6. Application Package Preparation & Sensitive Fields
- Reuses `ApplicationPrepService` to assemble evidence-backed answers and custom cover letters.
- **Sensitive Questions**: Fields requesting salary expectations, visa sponsorship, legal declarations, or background clearances are flagged with `requires_user_input: true` and left for human input.

### 7. Submission Safety Guarantee
- Ingestion and preparation operations stop strictly at `READY_FOR_REVIEW`.
- No automatic browser submissions, Enter-key triggers, or background submissions take place.
- All final submissions remain gated behind `HumanConfirmationService`, requiring the candidate to explicitly type the confirmation word `SUBMIT`.

---

## API Reference

### `POST /api/dashboard/opportunities/analyze`
Submits a public job posting URL for ingestion and automated preparation.

#### Request Body
```json
{
  "url": "https://jobs.lever.co/example-company/backend-lead"
}
```

#### Response (`200 OK`)
```json
{
  "job_id": "example-company-backend-lead-8f1a2b",
  "application_id": "app-usr-1a2b3c4d",
  "company": "Example Company",
  "title": "Backend Lead",
  "location": "Remote",
  "canonical_url": "https://jobs.lever.co/example-company/backend-lead",
  "source": "user_submitted_url",
  "match_score": 88.0,
  "recommendation": "APPLY",
  "priority_band": "HIGH",
  "priority_score": 78.5,
  "selected_strategy": "backend_java",
  "strengths": [
    "Strength: Java — confirmed professional experience",
    "Strength: Spring Boot — confirmed professional experience",
    "Strong domain alignment with candidate's fintech background"
  ],
  "gaps": [],
  "risks": [],
  "is_duplicate": false,
  "duplicate_of_id": null,
  "status": "READY_FOR_REVIEW",
  "resume_download_url": "/api/dashboard/applications/app-usr-1a2b3c4d/resume/pdf",
  "supports_browser_prep": true,
  "has_active_session": false,
  "needs_user_input_count": 2,
  "message": "Opportunity successfully analyzed and prepared for review."
}
```

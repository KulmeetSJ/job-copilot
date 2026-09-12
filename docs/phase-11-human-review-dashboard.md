# Phase 11 — Human Review Dashboard & Control Center

## 1. Executive Summary

Phase 11 implements the primary human interface and operational console for Job Copilot.

Job Copilot is strictly a human-assistive decision support and preparation engine—**not an autonomous application system**. The Human Review Dashboard & Control Center ensures that all sensitive personal disclosures, salary expectations, work authorization statements, custom answers, and final application submissions remain under absolute, non-delegable human control.

---

## 2. Architecture & Design Principles

The Phase 11 Dashboard architecture cleanly separates presentation from authoritative domain logic:

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     React 18 + TypeScript + Vite SPA                    │
│            (Built into static assets served at /dashboard)              │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ JSON API (Header: X-Dashboard-API-Key)
┌────────────────────────────────────▼────────────────────────────────────┐
│                    FastAPI Dashboard Router (/api/dashboard/*)          │
│                Protected by require_dashboard_auth dependency           │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │ In-memory & DB Orchestration
┌────────────────────────────────────▼────────────────────────────────────┐
│                             DashboardService                            │
│ ┌─────────────────────────────────────────────────────────────────────┐ │
│ │ Phase 4 Intelligence: Dimensional scoring, evidence classifications │ │
│ │ Phase 6 Application Preparation: Tailored resumes & cover letters   │ │
│ │ Phase 8 Tracking & Analytics: Append-only event store & metrics     │ │
│ │ Phase 10A Storage: Authorized artifact downloads & safe previews    │ │
│ │ Phase 10B/10C Browser & Sessions: Safe status & metadata retrieval  │ │
│ │ Authoritative HumanConfirmationService: Nonce & SUBMIT token gate   │ │
│ └─────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Safety Invariants Enforced
1. **Candidate Truth Immutability**: `data/candidate/master_profile.yaml`, `evidence.yaml`, and `preferences.yaml` are strictly read-only and never modified by dashboard actions.
2. **Phase 3 Strategy Definitions**: Unmodified and authoritative.
3. **Phase 4 Scoring Thresholds**: Authoritative 7-dimensional scoring weights remain unchanged.
4. **Phase 6 Application Prep**: Authoritative generator for answers and resume materials.
5. **No Autonomous Submissions**: `READY_FOR_REVIEW` is never treated as `SUBMITTED`.
6. **Explicit Confirmation Boundary**: Confirmation requires the exact keyword `SUBMIT` passed with a single-use nonce to `HumanConfirmationService`.
7. **Credential Protection**: Zero cookies, passwords, API tokens, or Playwright `storage_state` contents are exposed in API payloads or UI views.

---

## 3. Frontend Views & Capabilities

The Dashboard UI provides 7 dedicated operational views:

### 3.1 Overview & Control Center
- **Key Metrics**: Critical Queue, High Priority, Ready for Review, Needs Input, Awaiting Confirmation, Active Interviews, Offers, Recent Submissions.
- **Visual Application Pipeline**: Stage-by-stage funnel from Recommended to Offer.
- **Source Health Snapshot & Recent Activity Stream**.

### 3.2 Priority Queue & Job Detail
- **Structured Job Cards**: Displays match score, recommendation category (`STRONG_APPLY`, `APPLY`, `CONSIDER`, `SKIP`), priority tier, source, matched skills, gaps, and risk flags.
- **Match Explanation Modal**:
  - **7-Dimensional Breakdown**: Technical (30%), Responsibilities (20%), Role/Seniority (15%), Evidence (15%), Domain (10%), Preferences (5%), Credentials (5%).
  - **Evidence Provenance**: Itemized evidence classifications (`MATCH_CONFIRMED`, `MATCH_PROJECT_ONLY`, etc.).
  - **Epistemic Clarity**: Clear visual separation of **FACT**, **INFERENCE**, and **RECOMMENDATION**.

### 3.3 Application Review & Artifacts
- **Tailored Resume & Cover Letter**: LaTeX resume source preview, PDF compilation status, and cover letter reader.
- **Artifact Management**: Safe downloads via authorized `/api/dashboard/artifacts/{id}/download` route.
- **"Needs Your Input" Questionnaire**: Prominent card highlighting sensitive unanswered questions (e.g. salary, sponsorship) where user input is required.

### 3.4 Browser Review & Execution Status
- Displays live status: `NOT_STARTED`, `RUNNING`, `READY_FOR_REVIEW`, `BLOCKED`, `FAILED`, `COMPLETED`.
- **Prominent Safety Banner**: When in `READY_FOR_REVIEW`, visually alerts the operator:
  > *"READY FOR YOUR REVIEW — The application has NOT been sent. Review all fields before continuing."*

### 3.5 Submission Confirmation Boundary
- Dedicated confirmation modal requiring the operator to explicitly type **`SUBMIT`**.
- Displays application metadata, target company, role, resume version, and sensitive declarations.
- Calls authoritative backend `HumanConfirmationService` with the confirmation nonce.

### 3.6 Application Tracking & Timeline
- **16-Stage Kanban Board**: Visualizing applications across authoritative Phase 8 lifecycle states.
- **Append-Only Event Timeline**: Chronological, immutable record of all lifecycle events.

### 3.7 Analytics & Source Health
- **Outcome Analytics**: Conversion rates across stages, strategy performance, source performance, and role-family breakdowns.
- **Sample Guardrail**: Datasets with $N < 10$ are explicitly labeled *"Insufficient sample"*.
- **Source & Session Health**: Monitoring for all configured sources (LinkedIn, Lever, Greenhouse, etc.) showing health, mode, and session validity without exposing credentials.

---

## 4. API Endpoints

All dashboard routes are located under `/api/dashboard/*` and protected by `require_dashboard_auth`:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/dashboard/overview` | KPI summary, pipeline counts, source summary, recent activity |
| `GET` | `/api/dashboard/queue` | Paginated priority queue with 7D scores and evidence |
| `GET` | `/api/dashboard/jobs/{job_id}` | Detailed job info, evidence provenance, epistemic breakdown |
| `GET` | `/api/dashboard/applications` | List applications with status and job metadata |
| `GET` | `/api/dashboard/applications/{id}` | Comprehensive application review package and artifacts |
| `GET` | `/api/dashboard/applications/{id}/timeline` | Append-only event history |
| `GET` | `/api/dashboard/artifacts/{id}/download` | Stream authorized artifact binaries (PDF, TEX, JSON) |
| `GET` | `/api/dashboard/analytics` | Phase 8 conversion metrics and dimension aggregations |
| `GET` | `/api/dashboard/sources` | Configured job sources and session health metadata |
| `GET` | `/api/dashboard/activity` | Sanitized system activity log |
| `POST` | `/api/dashboard/applications/{id}/prepare` | Trigger application preparation workflow |
| `POST` | `/api/dashboard/applications/{id}/skip` | Mark job/application as skipped/archived |
| `POST` | `/api/dashboard/applications/{id}/input` | Store user-provided answers for sensitive questions |
| `POST` | `/api/dashboard/applications/{id}/confirm` | Authorize submission via `HumanConfirmationService` |

---

## 5. Security & Access Control

- **Authentication**: Dashboard endpoints require `X-Dashboard-API-Key` header matching `DASHBOARD_API_KEY` configuration.
- **IDOR Protection**: All artifact and application endpoints validate resource existence and authorization.
- **Zero Credential Leakage**: Browser session endpoints return only metadata (`is_authenticated`, `created_at`, `expires_at`); secrets and tokens are stripped before serialization.
- **Single Submission Path**: No UI shortcuts exist. Submissions can only occur via the validated confirmation nonce and explicit `confirm_text="SUBMIT"`.

---

## 6. Verification & Test Summary

- **Total Test Suite**: 234 / 234 passing (217 baseline + 17 Phase 11 unit/integration/safety tests).
- **Safety Boundary Tests**: Verified that review opening, preparation approval, and session authentication never trigger submission without explicit user confirmation.
- **Candidate Truth Verification**: Verified `data/candidate/master_profile.yaml`, `evidence.yaml`, and `preferences.yaml` remain byte-for-byte unmodified.

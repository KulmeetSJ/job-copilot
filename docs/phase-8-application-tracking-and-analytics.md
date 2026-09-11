# Phase 8 — Application Tracking & Outcome Analytics

## Overview
Phase 8 delivers an Application Tracking and Outcome Analytics Engine. It provides an append-only, immutable event ledger tracking the complete application lifecycle, captures frozen historical snapshots at submission time, enables manual outcome updates and notes, and computes funnel, conversion, response-time, strategy, recommendation, and discovery-source analytics with sample-size awareness.

```
Discovery (Phase 5)
       ↓
Job Intelligence (Phase 4)
       ↓
Application Preparation (Phase 6)
       ↓
Browser Form Submission (Phase 7)
       ↓
Tracking Service (Phase 8) ────────┐
  ├── Create ApplicationRecord     │
  ├── Freeze ApplicationSnapshot   │
  └── Append SUBMITTED Event       │
                                   ↓
                       Immutable Event Ledger
                  (data/tracking/events.json)
                                   │
                   ┌───────────────┴───────────────┐
                   ↓                               ↓
         Manual Status/Outcome Updates     Lifecycle Derivation
         (INTERVIEW, OFFER, REJECTED)   (Latest Valid Status)
                   │                               │
                   └───────────────┬───────────────┘
                                   ↓
                         Analytics Engine
    ┌──────────────────────────────┼──────────────────────────────┐
    ↓                              ↓                              ↓
Funnel & Conversion         Cohort Performance             Response Time
(Discovered → Offer)      (Strategy, Rec, Source)       (Submit → Interview)
```

---

## Key Design Principles & Guardrails

### 1. Immutable Historical Snapshots
When an application is submitted, an `ApplicationSnapshot` freezes:
- Exact fit score (e.g. 84.0) and multi-dimensional breakdown
- Exact resume strategy used (e.g. `backend_java`)
- Compiled 1-page LaTeX resume artifact path
- Tailored cover letter artifact path
- Discovery source and submission timestamp

Even if Phase 4 scoring algorithms or Phase 3 resume tailoring rules change months later, the historical snapshot is permanently preserved.

### 2. Append-Only Event Ledger
State transitions are recorded as immutable `ApplicationEvent` records with ISO timestamps and event sources (`SYSTEM`, `BROWSER`, `USER`, `MANUAL`). The current status is always deterministically derived from the latest valid event.

### 3. Sample-Size Awareness ($N \ge 10$)
Comparative metrics between strategies or sources enforce a minimum sample size threshold (default $N=10$). If $N < 10$, reports explicitly surface:
`"Insufficient sample size (N < 10) for reliable statistical comparison."`
This cleanly distinguishes observed facts from statistical inferences.

### 4. Zero Sensitive Data Persistence
No passwords, authentication secrets, SSNs, or sensitive email contents are stored in tracking records or event metadata.

---

## Lifecycle Stages & Model

### Active Stages (Pipeline Progress)
| Stage | Description |
| :--- | :--- |
| `DISCOVERED` | Job identified through discovery sources (Phase 5). |
| `RECOMMENDED` | Evaluated and scored by Job Intelligence (Phase 4). |
| `PREPARED` | Resume tailored and Q&A answered (Phase 6). |
| `READY_FOR_REVIEW` | Form filled and ready for candidate review (Phase 7). |
| `SUBMITTED` | Form submitted with explicit human confirmation (Phase 7). |
| `ACKNOWLEDGED` | Application receipt confirmed by employer/portal. |
| `RECRUITER_RESPONSE`| Recruiter outreach or initial screen invitation. |
| `ASSESSMENT` | Online technical assessment (OA) or take-home challenge. |
| `INTERVIEW` | Live technical, system design, or behavioral interview. |
| `FINAL_ROUND` | Executive or onsite/virtual final round. |

### Outcome States
| State | Description |
| :--- | :--- |
| `OFFER` | Formal employment offer extended. |
| `ACCEPTED` | Offer accepted by candidate. |
| `REJECTED` | Application declined at any stage. |
| `WITHDRAWN` | Candidate withdrew application. |
| `EXPIRED` | Posting closed or expired before action. |

### Archive State
| State | Description |
| :--- | :--- |
| `CLOSED` | Inactive archive state for concluded applications (from outcome states). |

---

## Analytics & Metric Definitions

### 1. Funnel Metrics
Counts distinct applications reaching each pipeline milestone:
$\text{Discovered} \rightarrow \text{Recommended} \rightarrow \text{Prepared} \rightarrow \text{Submitted} \rightarrow \text{Recruiter Response} \rightarrow \text{Assessment} \rightarrow \text{Interview} \rightarrow \text{Final Round} \rightarrow \text{Offer} \rightarrow \text{Accepted}$

### 2. Conversion Formulas
- **Application Rate**: $\frac{\text{Applications Submitted}}{\text{Jobs Discovered}} \times 100\%$
- **Response Rate**: $\frac{\text{Recruiter Responses}}{\text{Applications Submitted}} \times 100\%$
- **Interview Rate**: $\frac{\text{Interviews Reached}}{\text{Applications Submitted}} \times 100\%$
- **Offer Rate**: $\frac{\text{Offers Extended}}{\text{Applications Submitted}} \times 100\%$
- **Acceptance Rate**: $\frac{\text{Offers Accepted}}{\text{Offers Extended}} \times 100\%$

### 3. Response-Time Analytics
Calculates median, mean, min, and max elapsed days between:
- `submission` $\rightarrow$ `acknowledgement`
- `submission` $\rightarrow$ `recruiter_response`
- `submission` $\rightarrow$ `interview`
- `submission` $\rightarrow$ `rejection`
- `interview` $\rightarrow$ `offer`

---

## Storage Layout

```
data/
├── tracking/
│   ├── applications.json     # Central registry of all tracked applications
│   └── events.json           # Global immutable event ledger
└── applications/<job_id>/tracking/
    ├── application.json      # Job-specific application record
    ├── snapshot.json         # Frozen submission snapshot
    └── events.json           # Chronological event log
```

---

## CLI Reference

### Applications Management
```bash
# List tracked applications
python -m job_copilot applications [--status SUBMITTED] [--strategy backend_java]

# Get detailed status of an application
python -m job_copilot application-status <application_id>

# Update application lifecycle status
python -m job_copilot application-update <application_id> --status INTERVIEW --notes "Tech screen scheduled"

# Record a specific lifecycle event
python -m job_copilot application-event <application_id> --event RECRUITER_RESPONSE --notes "Recruiter reached out"

# Display chronological event timeline
python -m job_copilot application-timeline <application_id>
```

### Outcome Analytics
```bash
# Display pipeline funnel & conversion
python -m job_copilot analytics-funnel [--from-date 2026-09-01] [--to-date 2026-09-30]

# Display conversion rates
python -m job_copilot analytics-conversion

# Strategy performance breakdown
python -m job_copilot analytics-strategies

# Recommendation tier performance
python -m job_copilot analytics-recommendations

# Discovery source performance
python -m job_copilot analytics-sources

# Milestone response times
python -m job_copilot analytics-response-times
```

---

## REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/tracking/applications` | Register an application into tracking |
| `GET` | `/api/tracking/applications` | List tracked applications (with filters) |
| `GET` | `/api/tracking/applications/{id}` | Get application record & snapshot |
| `POST` | `/api/tracking/applications/{id}/events` | Record lifecycle event |
| `GET` | `/api/tracking/applications/{id}/timeline` | Get chronological event timeline |
| `POST` | `/api/tracking/applications/{id}/notes` | Add candidate note |
| `GET` | `/api/analytics/dashboard` | Aggregated analytics dashboard |
| `GET` | `/api/analytics/funnel` | Pipeline stage funnel counts |
| `GET` | `/api/analytics/conversion` | Conversion rates |
| `GET` | `/api/analytics/strategies` | Strategy performance breakdown |
| `GET` | `/api/analytics/recommendations` | Recommendation tier breakdown |
| `GET` | `/api/analytics/sources` | Discovery source breakdown |
| `GET` | `/api/analytics/response-times` | Milestone response time metrics |

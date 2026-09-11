# Phase 9 — Continuous Job Copilot

## Overview
Phase 9 delivers the Continuous Job Copilot — an intelligent orchestration, prioritization, and decision-support engine built on top of the completed and locked upstream architecture (Phases 1–8).

> **Architectural Guardrail Statement**:
> Phase 9 is an orchestration and decision-support layer. It does not override candidate truth, Phase 4 scoring, Phase 6 preparation, Phase 7 submission safeguards, or Phase 8 historical records.

```
                    ┌────────────────────────────────────────┐
                    │      PHASE 9 CONTINUOUS COPILOT        │
                    │                                        │
                    │  • Orchestration Service               │
                    │  • Transparent Prioritization Engine   │
                    │  • Evidence-Traceable Explanations     │
                    │  • Persistent Copilot Queue            │
                    │  • Sample-Safe Historical Learning     │
                    └───────────────────┬────────────────────┘
                                        │
        ┌───────────────────────────────┼───────────────────────────────┐
        ↓                               ↓                               ↓
 Phase 5 Discovery             Phase 4 Intelligence            Phase 8 Analytics
 (Ingest / Deduplicate)        (Analyze / Match / Rec)         (Ledger / Cohorts)
        │                               │                               │
        └───────────────────────────────┼───────────────────────────────┘
                                        ↓
                         Prioritized Copilot Queue
                                        ↓
                             Candidate Action Choice
                         (Review / Prepare / Skip / Wait)
                                        ↓
                       Phase 6 Application Preparation
                                        ↓
                    Phase 7 Browser Workflow + Review Artifact
                                        ↓
                       [EXPLICIT HUMAN CONFIRMATION]
                                        ↓
                             Phase 7 Submission
                                        ↓
                           Phase 8 Event Tracking
```

---

## Component Responsibilities

1. **`CopilotOrchestrator` (`src/job_copilot/copilot/orchestrator.py`)**:
   Coordinates end-to-end pipeline steps across Phases 4–8 without duplicating storage.
2. **`OpportunityPrioritizer` (`src/job_copilot/copilot/prioritizer.py`)**:
   Calculates deterministic priority scores and assigns explainable priority bands (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `IGNORE`).
3. **`ExplanationEngine` (`src/job_copilot/copilot/explanations.py`)**:
   Generates evidence-backed reasoning (`why_apply`, `why_not_apply`, `uncertainties`) with strict claim typing (`PROFESSIONAL_EXPERIENCE`, `PERSONAL_PROJECT`, `EXPOSURE`).
4. **`HistoricalLearningEngine` (`src/job_copilot/copilot/learning.py`)**:
   Surfaces sample-safe insights from Phase 8 outcomes, enforcing strict separation between `FACT`, `INFERENCE`, and `RECOMMENDATION`.
5. **`CopilotQueueStore` (`src/job_copilot/copilot/queue.py`)**:
   Maintains a persistent, thread-safe queue of opportunities under `data/copilot/queue.json`.

---

## Queue Lifecycle

```
NEW ──► REVIEW ──► APPROVED ──► PREPARING ──► READY_FOR_REVIEW ──► WAITING_FOR_USER ──► SUBMITTED ──► TRACKING
  │       │                                                                                             │
  ▼       ▼                                                                                             ▼
[SKIPPED] ────────────────────────────────────────────────────────────────────────────────────────► [ARCHIVED]
```

| Queue State | Meaning |
| :--- | :--- |
| `NEW` | Discovered and ingested by Phase 5. |
| `REVIEW` | Evaluated by Phase 4 and prioritized by Phase 9; awaiting candidate review. |
| `APPROVED` | Candidate approved opportunity for application package preparation. |
| `PREPARING` | Phase 6 resume tailoring and question answering in progress. |
| `READY_FOR_REVIEW` | Package prepared; ready for browser inspection or candidate review. |
| `WAITING_FOR_USER` | Browser form filled; awaiting mandatory candidate confirmation token. |
| `SUBMITTED` | Form submitted externally via Phase 7 with verified confirmation token. |
| `TRACKING` | Post-submission milestones monitored via Phase 8. |
| `SKIPPED` | Candidate or policy skipped the opportunity. |
| `ARCHIVED` | Concluded opportunity archived. |

---

## Scheduled & Periodic Execution Semantics

Phase 9 operates on a **Scheduled/Periodic Copilot Execution** model. Opportunities are ingested and processed via:
1. **Periodic Scheduled Invocations** (e.g. daily/hourly `cron` running `python -m job_copilot copilot-discover` and `copilot-process`).
2. **On-Demand CLI Commands** for candidate review, approval, preparation, and browser review.
3. **REST API Triggers** via `/api/copilot/discover` and `/api/copilot/process`.

Phase 9 does not run an unmanaged background daemon process; all state is persisted atomically in `data/copilot/queue.json` and Phase 8 tracking ledgers.

---

## Prioritization Model (Zero Double-Counting)

Priority score ($0.0 \dots 100.0$) is calculated as:
$$\text{Priority Score} = \text{clamp}\Big(\text{Fit Score} + \text{Tier Adjustment} + \text{Freshness Signal} + \text{Historical Signal} + \text{Risk Signal},\; 0.0,\; 100.0\Big)$$

Where:
- $\text{Fit Score}$: Continuous Phase 4 overall match score ($0.0 \dots 100.0$).
- $\text{Tier Adjustment}$: Explicit policy modifier for categorical decisions (`STRONG_APPLY`: $+5.0$, `APPLY`: $0.0$, `REVIEW`: $-5.0$, `LOW_PRIORITY`: $-15.0$, `SKIP`: $-40.0$, `HIGH_RISK`: $-50.0$).
- $\text{Freshness Signal}$: $+10.0$ points ($\le 3$ days), $+5.0$ points ($\le 7$ days), $0.0$ older.
- $\text{Historical Signal}$: $+10.0$ points (strategy bonus when sample threshold $N \ge 10$ is met).
- $\text{Risk Signal}$: $-50.0$ (hard conflict), $-20.0$ (missing critical skill), $-25.0$ (unsupported seniority), $-5.0$ (unknown sponsorship).

### Priority Bands:
- `CRITICAL`: $\ge 90.0$
- `HIGH`: $75.0 \dots 89.9$
- `MEDIUM`: $50.0 \dots 74.9$
- `LOW`: $30.0 \dots 49.9$
- `IGNORE`: $< 30.0$

---

## Historical Learning & Sample Thresholds

The Historical Learning Engine enforces three fundamental safety guarantees:

### 1. Minimum Sample Threshold ($N \ge 10$)
If a cohort has fewer than 10 submitted applications ($N < 10$), the engine flags:
`"Insufficient sample size (N < 10). Minimum sample threshold for surfacing historical signals not met."`
Strong statistical inferences are suppressed until $N \ge 10$.

### 2. Strict Separation of Truth
- **`FACT`**: Empirical counts and observed conversion rates.
- **`INFERENCE`**: Derived patterns and comparative signals.
- **`RECOMMENDATION`**: Advisory guidance for candidate decision-making.

### 3. Zero Automatic Configuration Mutation
Every insight carries the explicit guarantee:
`"No configuration change made (human decision required)"`.
The engine **never** silently modifies Phase 4 weights, thresholds, resume strategies, or candidate truth.

---

## Human Approval Boundaries

The following operations strictly require human candidate interaction:
1. **Sensitive application questions** (salary expectations, notice period, legal declarations).
2. **Sponsorship and work authorization** declarations.
3. **Unverified experience claims** not supported by verified evidence.
4. **Final application review** artifact confirmation.
5. **External portal submission** (requires explicit Phase 7 confirmation token).

---

## Failure Handling

- **Source Unavailable**: Logged gracefully, other sources continue uninterrupted.
- **Malformed Job Description**: Handled by normalizer without corrupting storage.
- **Duplicate Job**: Flagged via Phase 5 deduplicator and skipped.
- **CAPTCHA / Login Encountered**: Phase 7 pauses browser session in `WAITING_FOR_USER` state.
- **Missing Confirmation Token**: Submissions blocked (`SUBMISSION_BLOCKED`).

---

## CLI Reference

```bash
# Display prioritized daily dashboard
python -m job_copilot copilot

# Run continuous discovery & process new jobs into queue
python -m job_copilot copilot-discover

# Process unassessed stored jobs
python -m job_copilot copilot-process [--job-id <job_id>]

# View prioritized opportunity queue
python -m job_copilot copilot-queue [--priority HIGH] [--status REVIEW]

# One-click application preparation
python -m job_copilot copilot-prepare <job_id> [--strategy backend_java]

# Approve or skip opportunity
python -m job_copilot copilot-approve <job_id>
python -m job_copilot copilot-skip <job_id> [--reason "Relocation required"]

# Display historical outcome learning & insights
python -m job_copilot copilot-insights
```

---

## REST API Reference

- `GET  /api/copilot/dashboard`: Daily prioritized summary and recent outcomes.
- `GET  /api/copilot/queue`: Filtered list of queued opportunities.
- `GET  /api/copilot/recommendations`: Actionable recommendation objects.
- `GET  /api/copilot/insights`: Sample-safe historical outcome insights.
- `POST /api/copilot/discover`: Trigger continuous discovery.
- `POST /api/copilot/process`: Process pipeline jobs.
- `POST /api/copilot/{job_id}/prepare`: Prepare Phase 6 application package.
- `POST /api/copilot/{job_id}/approve`: Mark opportunity as approved.
- `POST /api/copilot/{job_id}/skip`: Skip opportunity.
- `POST /api/copilot/{job_id}/apply`: Browser handoff (requires confirmation token for submission).

---

## Configuration (`data/config/copilot.yaml`)

```yaml
priority:
  recommendation_tier_adjustments:
    STRONG_APPLY: 5.0
    APPLY: 0.0
    CONSIDER: -5.0
    REVIEW: -5.0
    LOW_PRIORITY: -15.0
    SKIP: -40.0
    HIGH_RISK: -50.0
  freshness_bonus:
    very_recent_days: 3
    very_recent_points: 10.0
    recent_days: 7
    recent_points: 5.0
    old_points: 0.0
  historical:
    enabled: true
    minimum_sample_size: 10
    high_performing_bonus: 10.0
    low_performing_penalty: -10.0
```

---

## Limitations & Future ML Possibilities

### Version 1 Design Decisions:
- Relies exclusively on deterministic rule-based prioritization and transparent calculations.
- Zero black-box machine learning models.

### Future ML Enhancements (Post-V1):
- Learned ranking models (e.g., LambdaMART) trained on candidate-confirmed positive/negative review feedback once $\ge 500$ verified outcomes are recorded.
- Automated JD parsing assistance with confidence thresholds.

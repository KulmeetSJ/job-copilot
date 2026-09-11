# Phase 7 — Browser-Assisted Application Workflow

## Overview
Phase 7 implements a human-in-the-loop, browser-assisted application workflow. It bridges the gap between prepared application packages (Phase 6) and real-world application forms without ever becoming an unmonitored or risky auto-apply bot.

```
Phase 6 Application Package (data/applications/<job_id>/)
                       ↓
         Browser Workflow Service (Phase 7)
                       ↓
              Browser Adapter (Playwright)
                       ↓
             Page Form Detection (DOM)
                       ↓
             Deterministic Field Classifier
                       ↓
               Deterministic Field Mapper
                       ↓
    ┌──────────────────┴──────────────────┐
    ↓                                     ↓
Safe Auto-Fill                      Sensitive Fields
(Contact, Resume PDF,             (Salary, Sponsorship,
Cover Letter, Evidence Answers)   Notice Period, Clearances)
    │                                     ↓
    │                              WAITING_FOR_USER
    │                             (User Input Request)
    │                                     │
    └──────────────────┬──────────────────┘
                       ↓
               Review Gate Artifact
          (data/applications/<job_id>/browser/review.json)
                       ↓
               READY_TO_SUBMIT
                       ↓
             Explicit Human Action ("SUBMIT")
                       ↓
             Submission Guard Check
                       ↓
            Browser Form Submission
                       ↓
           Submission Result & Audit Log
```

---

## Key Design Principles & Guardrails

### 1. Human-in-the-Loop Confirmation Gate
The system **never** silently submits an application.
- The workflow transitions to `READY_TO_SUBMIT` only after all required fields are resolved.
- Submitting requires an explicit user action (`confirmed=True` or `confirm_text="SUBMIT"` in CLI/API).
- No automatic timeouts, no implicit inferences.

### 2. Zero Anti-Bot Evasion / CAPTCHA Bypass
- If a login page (`is_login_page()`) or CAPTCHA challenge (`is_captcha_present()`) is detected, the browser pauses in `WAITING_FOR_USER` status.
- The human candidate completes the verification or authentication manually in the browser.

### 3. Strict Truth Safety & Provenance Retention
- Basic contact info (name, email, phone, location, links) is populated strictly from canonical `CandidateProfile`.
- File uploads attach the exact Phase 3 tailored resume PDF and Phase 6 cover letter.
- Free-text questions use verified Phase 6 `ApplicationAnswer` records with claim provenance.
- Unsupported technologies (e.g. AWS) or questions classified as `DO_NOT_ANSWER` block automated fill.
- Sensitive fields (salary, sponsorship, notice period, clearances) are flagged as `USER_INPUT_REQUIRED` and pause automation.

### 4. Double-Submission Protection
- Submission status and confirmation reference IDs are persisted under `data/applications/<job_id>/browser/`.
- Resubmitting an already submitted application is blocked unless explicitly reset.

---

## Component Architecture

### 1. `FormDetector` (`src/job_copilot/browser/detector.py`)
Inspects the DOM and extracts structured `BrowserField` items including tag types, labels, placeholders, ARIA attributes, autocomplete tags, and nearby text context.

### 2. `FieldClassifier` (`src/job_copilot/browser/classifier.py`)
Classifies detected fields deterministically into:
- `KNOWN_CANDIDATE_FIELD`
- `FILE_UPLOAD`
- `USER_INPUT_REQUIRED`
- `APPLICATION_QUESTION`
- `JOB_METADATA`
- `DO_NOT_TOUCH` (passwords, SSN, bank info)
- `UNKNOWN`

### 3. `FieldMapper` (`src/job_copilot/browser/mapper.py`)
Maps `BrowserField` elements to candidate profile facts and Phase 6 answers with explicit `MappingConfidence` (`HIGH`, `MEDIUM`, `LOW`, `UNKNOWN`).

### 4. `PlaywrightBrowserAdapter` (`src/job_copilot/browser/adapter.py`)
Encapsulates all Playwright browser interactions: page navigation, field filling, file uploads, screenshots, CAPTCHA/login detection, and bounded DOM stabilization.

### 5. `BrowserWorkflowService` (`src/job_copilot/services/browser_workflow_service.py`)
Central orchestrator managing session state, field auto-fill, human inputs, review generation, submission guard checks, audit trail logging, and artifact persistence.

---

## Artifact Storage Layout

Artifacts are persisted under `data/applications/<job_id>/browser/`:
```
data/applications/<job_id>/
├── package.json
├── cover_letter.md
├── questions.json
├── validation.json
└── browser/
    ├── session.json          # Active session status, URLs, step counters
    ├── fields.json           # All detected DOM form controls
    ├── mapping.json          # Semantic field mappings & confidence
    ├── audit.json            # Timestamped audit trail of all browser actions
    ├── review.json           # Pre-submission review summary artifact
    └── screenshots/          # Audit screenshots
        ├── before_fill.png
        ├── after_fill.png
        ├── review.png
        └── post_submit.png
```

---

## CLI Reference

### Start Browser Session
```bash
python -m job_copilot browser-start <job_id> --url "<url>" [--headed]
```

### Inspect Page Controls
```bash
python -m job_copilot browser-inspect <session_id>
```

### Auto-fill Safe Fields
```bash
python -m job_copilot browser-fill <session_id>
```

### Inspect Pending User Inputs
```bash
python -m job_copilot browser-inputs <session_id>
```

### Pre-Submission Review
```bash
python -m job_copilot browser-review <session_id>
```

### Submit Application
```bash
python -m job_copilot browser-submit <session_id> [--confirm SUBMIT]
```

### Cancel Session
```bash
python -m job_copilot browser-cancel <session_id>
```

---

## REST API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/api/browser/start` | Start interactive browser session |
| `GET` | `/api/browser/{session_id}` | Get session status & detected fields |
| `POST` | `/api/browser/{session_id}/inspect` | Re-inspect page DOM |
| `POST` | `/api/browser/{session_id}/fill` | Auto-fill safe fields & flag user inputs |
| `GET` | `/api/browser/{session_id}/inputs` | List unresolved sensitive fields |
| `POST` | `/api/browser/{session_id}/input` | Provide explicit value for a field |
| `POST` | `/api/browser/{session_id}/review` | Generate pre-submission review artifact |
| `POST` | `/api/browser/{session_id}/submit` | Submit application (requires `confirmed=True`) |
| `POST` | `/api/browser/{session_id}/cancel` | Cancel session & close browser |

---

## Verification & Testing
- Offline HTML fixtures in `tests/browser/fixtures/` (`basic_form.html`, `sensitive_questions.html`, `file_upload.html`, `captcha_page.html`, `login_page.html`, `representative_job_application.html`).
- 15 unit and integration tests verifying field detection, classification, mapping, auto-filling, pause gates, human confirmation, duplicate submission protection, and API endpoints.

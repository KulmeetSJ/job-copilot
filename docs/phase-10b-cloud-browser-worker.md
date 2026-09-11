# Phase 10B — Cloud Browser Worker

> [!WARNING]
> **PRIMARY SAFETY INVARIANT**:
> The browser worker is strictly preparation-oriented and human-gated. It fills and prepares job applications up to `READY_FOR_REVIEW`. It **never** autonomously submits an external job application. All submissions require explicit, cryptographically validated human confirmation.

---

## 1. Architecture Overview

Phase 10B extracts browser automation into an isolated worker subsystem that executes Playwright in headless container environments. It interacts with the FastAPI core and PostgreSQL database via asynchronous task models, and leverages Phase 10A `ArtifactService` for durable evidence persistence.

```
                      +------------------------------------+
                      |    FastAPI Core / REST Endpoint    |
                      +------------------------------------+
                                         |
                              Create Task / Query
                                         |
                                         v
                      +------------------------------------+
                      |   PostgreSQL: `browser_tasks`      |
                      |   (Durable State Machine Storage)  |
                      +------------------------------------+
                                         |
                              Claim Task / Execute
                                         |
                                         v
                      +------------------------------------+
                      |         BrowserWorker              |
                      |   - Playwright Manager             |
                      |   - Domain Security Guard          |
                      |   - Evidence Field Mapper          |
                      |   - Anti-Bot / CAPTCHA Guard       |
                      +------------------------------------+
                                    /         \
                      Evidence Artifacts       Terminal Prep State:
                            /                   READY_FOR_REVIEW
                           v                           |
                 +-------------------+                 | (Stops Here)
                 |  ArtifactService  |                 v
                 |  - Screenshots    |     +-------------------------+
                 |  - Resumes (PDF)  |     | Explicit Confirmation   |
                 |  - Traces         |     | (HumanConfirmationSvc)  |
                 +-------------------+     +-------------------------+
                                                       |
                                                 Token Verified
                                                       |
                                                       v
                                           +-------------------------+
                                           |     Authorized Submit   |
                                           +-------------------------+
```

---

## 2. Worker Lifecycle & State Machine

Every browser execution task follows a strict deterministic state machine:

| State | Classification | Description |
| :--- | :--- | :--- |
| `QUEUED` | Initial | Task created and waiting for an available worker process. |
| `RUNNING` | Active | Worker has claimed the task, launched Playwright, and is inspecting/filling the form. |
| `LOGIN_REQUIRED` | Paused | Form is behind an authentication wall; automation halts safely. |
| `CAPTCHA_REQUIRED` | Paused | Anti-bot challenge or CAPTCHA detected; automation halts safely without bypass. |
| `USER_INPUT_REQUIRED` | Paused | Form contains sensitive fields (salary, sponsorship, clearance) or unknown questions. |
| `BLOCKED` | Terminated | Target URL violated domain allowlist or attempted disallowed scheme. |
| `READY_FOR_REVIEW` | Terminal Preparation | Form successfully autofilled; screenshots and review package generated; **STOPS HERE**. |
| `FAILED` | Terminated | Execution failed due to network error, timeout, or exceeded max retry attempts. |
| `COMPLETED` | Authorized Final | Submission confirmed explicitly by human operator with valid token. |
| `EXPIRED` | Terminated | Confirmation token timed out (1 hour expiry). |

---

## 3. Playwright Isolation & Browser Management

The `BrowserManager` and `BrowserSessionAdapter` completely isolate Playwright execution:
- Runs in non-root user mode (`appuser`).
- Automatically handles browser context startup and teardown in `finally` blocks.
- Manages DOM idle synchronization, screenshot capturing, and file uploads.
- Never exposes raw Playwright page or browser objects to upper application layers.

---

## 4. Field Classification & Sensitive Field Protection

Form fields are classified using deterministic regex rules:
- **`AUTO_FILL`**: Candidate contact details (`full_name`, `email`, `phone`, `location`, `linkedin`, `github`) backed by the authoritative candidate profile.
- **`REQUIRES_USER_INPUT`**: Questions asking for salary, visa sponsorship, work authorization, notice period, start date, relocation, criminal history, or security clearance. Automation pauses in `USER_INPUT_REQUIRED`.
- **`DO_NOT_FILL`**: Prohibited fields (passwords, SSNs, credit cards, bank credentials).
- **`UNKNOWN`**: Fields with no candidate match. Pauses automation if required.

Candidate truth (`data/candidate/master_profile.yaml`) remains strictly immutable and read-only.

---

## 5. Domain Safety & URL Validation

Before any browser navigation occurs:
1. Validates that the URL scheme is strictly `http` or `https` (rejects `javascript:`, `file:`, `data:`).
2. Verifies the target hostname against an allowed domain whitelist (e.g., `greenhouse.io`, `lever.co`, `workday.com`, `ashbyhq.com`, `smartrecruiters.com`, `linkedin.com`, `naukri.com`, `instahyre.com`, `localhost`).
3. Disallowed domains transition the task immediately to `BLOCKED`.

---

## 6. CAPTCHA & Anti-Bot Protection

- When CAPTCHA or anti-bot challenge is detected, the task transitions to `CAPTCHA_REQUIRED` and pauses.
- **Zero Bypass Policy**: No automated CAPTCHA solving, fingerprint spoofing, or stealth evasion is implemented.

---

## 7. Artifact Integration (Phase 10A)

- **Resume Upload**: Retrieves tailored resume PDFs from Phase 10A `ArtifactService` and uploads them to file input fields.
- **Evidence Screenshots**: Captures initial page and post-fill form screenshots, storing them in object storage via `ArtifactService` with SHA-256 checksums.

---

## 8. Human-Confirmation Boundary & Submission Gate

The `HumanConfirmationService` enforces the primary safety invariant:
1. Reaching `READY_FOR_REVIEW` issues a cryptographically random, time-limited `confirmation_token` (1 hour lifespan).
2. Submission is **only** permitted via explicit POST to `/api/browser/tasks/{task_id}/confirm` with:
   - `confirmation_token`: matching the issued token.
   - `confirm_text`: strictly equal to `"SUBMIT"`.
3. Stale tokens, mismatched application IDs, and invalid tokens are rejected with HTTP 403 Forbidden.
4. Duplicate confirmation requests on already completed tasks return the existing submission reference without triggering duplicate actions.

---

## 9. What is Implemented vs. What is Cloud-Live

| Feature / Capability | Status | Description |
| :--- | :--- | :--- |
| **Worker Subsystem & State Machine** | **IMPLEMENTED & VERIFIED** | `BrowserWorker`, `BrowserTaskExecutor`, explicit state transitions. |
| **Playwright Isolation** | **IMPLEMENTED & VERIFIED** | `BrowserManager`, `BrowserSessionAdapter`, clean cleanup. |
| **Sensitive Field & Domain Safety** | **IMPLEMENTED & VERIFIED** | Pauses on sensitive questions, blocks untrusted domains. |
| **Phase 10A Artifact Integration** | **IMPLEMENTED & VERIFIED** | Uploads resumes, stores screenshots via `ArtifactService`. |
| **Human Confirmation Submission Gate** | **IMPLEMENTED & VERIFIED** | Cryptographic token verification; zero autonomous submission. |
| **Local Headless Execution & Tests** | **IMPLEMENTED & VERIFIED** | 198/198 tests passing in virtual environment. |
| **Cloud-Authenticated Sessions (Phase 10C)**| **PENDING FUTURE PHASE** | Real LinkedIn/Naukri/Instahyre authenticated sessions belong to Phase 10C. |
| **Render Background Worker Container** | **PREPARED** | Dockerfile and CLI entrypoint (`python -m job_copilot.browser_worker`) ready for worker service. |

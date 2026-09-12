# Phase 10C — Authenticated Source Sessions & Source Adapters

> [!WARNING]
> **PRIMARY SAFETY INVARIANT**: The Browser Worker and all source adapters are preparation-oriented and strictly human-gated. Authenticated access does **NOT** imply submission authorization. The browser worker and all source adapters halt strictly at `READY_FOR_REVIEW`. External job applications are **never** autonomously submitted.

---

## 1. Session Architecture

Phase 10C introduces an isolated, authenticated session management subsystem:

```
┌─────────────────────────────────────────────────────────────┐
│                      FastAPI API / CLI                      │
│        POST /api/browser/sessions/{session_id}/save-state   │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│               AuthenticatedSessionManager                   │
│   Coordinates lifecycle, expiration, verification timestamps│
└──────────────┬───────────────────────────────┬──────────────┘
               │ (Metadata only)               │ (Storage State)
               ▼                               ▼
┌──────────────────────────────┐ ┌────────────────────────────┐
│      PostgreSQL Database     │ │     BrowserSessionStore    │
│       `browser_sessions`     │ │ `data/browser_sessions/`   │
│   (NO cookies/passwords)     │ │ POSIX 0o700 dir, 0o600 file│
└──────────────────────────────┘ └────────────────────────────┘
```

---

## 2. Authentication Lifecycle

1. **Session Registration (`NOT_CONFIGURED`)**: A session record is created for a target source (`linkedin`, `naukri`, `instahyre`).
2. **Human Login Bootstrap**: The human operator performs authentication in an interactive browser window. The system detects login completion, extracts the Playwright `storage_state`, and saves it via `BrowserSessionStore`.
3. **Activation (`ACTIVE`)**: The session transitions to `ACTIVE` with a verified expiration timestamp.
4. **Session Verification**: Before running a task, the adapter verifies authentication validity against source endpoints.
5. **Expiration / Login Required (`LOGIN_REQUIRED` / `EXPIRED`)**: If cookies expire or an authwall redirect occurs, the task safely pauses in `LOGIN_REQUIRED`.
6. **Revocation (`REVOKED`)**: Revoking a session purges the physical storage state file and marks the database record `REVOKED`.

---

## 3. Session Security Model

* **PostgreSQL Isolation**: Strictly **no** cookies, passwords, authentication tokens, or storage states are stored in PostgreSQL database columns.
* **REST API Isolation**: API responses never return cookies or raw storage states.
* **Filesystem Protection**: Local storage files are restricted with POSIX `0o600` (read/write only by the process owner) in a `0o700` directory.
* **Logging Sanitization**: Browser state payloads and credentials are never emitted in structured or application logs.

---

## 4. Source Adapter Registry

The `SourceAdapterRegistry` manages validated source adapters and enforces strict domain matching:
* `linkedin` / `*.linkedin.com` ➔ `LinkedInAdapter`
* `naukri` / `*.naukri.com` ➔ `NaukriAdapter`
* `instahyre` / `*.instahyre.com` ➔ `InstahyreAdapter`
* `generic` / ATS domains (Greenhouse, Lever, etc.) ➔ `GenericPortalAdapter`
* **Unsupported domains**: Immediately rejected with `DomainSecurityError` and task status `BLOCKED`.

---

## 5. Source Adapters

### A. LinkedIn Adapter (`LinkedInAdapter`)
* **Supported Domains**: `linkedin.com`, `www.linkedin.com`
* **Login Detection**: Checks for `/login`, `/authwall`, `checkpoint/lg`.
* **CAPTCHA Detection**: Checks for `checkpoint/challenge`, security verification frames.
* **Field Mapping**: Maps Easy Apply modal inputs to candidate contact fields.
* **Submission Boundary**: Halts strictly at `READY_FOR_REVIEW`.

### B. Naukri Adapter (`NaukriAdapter`)
* **Supported Domains**: `naukri.com`, `www.naukri.com`
* **Login Detection**: Checks for `/nlogin`, `login.naukri.com`.
* **CAPTCHA Detection**: Detects bot challenge checkpoints.
* **Field Mapping**: Maps multi-step form fields.
* **Submission Boundary**: Halts strictly at `READY_FOR_REVIEW`.

### C. Instahyre Adapter (`InstahyreAdapter`)
* **Supported Domains**: `instahyre.com`, `www.instahyre.com`
* **Login Detection**: Checks for `/login`, `/candidate/login`.
* **CAPTCHA Detection**: Detects challenge checkpoints.
* **Field Mapping**: Maps candidate profile fields and resume upload.
* **Submission Boundary**: Halts strictly at `READY_FOR_REVIEW`.

---

## 6. Safety Safeguards & Protections

1. **Job Identity Verification (Wrong-Job Protection)**:
   * The adapter verifies that the target page matches the expected company and job title before interacting.
   * Mismatches immediately pause the task in `BLOCKED` with reason `JOB_IDENTITY_MISMATCH`.
2. **Duplicate Application Guard**:
   * Inspects Phase 8 tracked applications (`ApplicationRepository`).
   * If the application is already `SUBMITTED`, `ACCEPTED`, or `CLOSED`, task execution is immediately halted in `BLOCKED` (`DUPLICATE_APPLICATION`).
3. **Sensitive Field Rules**:
   * Salary expectations, visa sponsorship, work authorization, notice period, and legal declarations are never automatically filled.
   * Triggers safe pause in `USER_INPUT_REQUIRED`.
4. **Artifact Integration (Phase 10A)**:
   * Tailored resumes are retrieved through `ArtifactService`.
   * Initial and post-fill screenshots are persisted to `ArtifactService`.

---

## 7. Explicit Human Confirmation Gate

```
BrowserTaskExecutor (Any Adapter)
        ↓
Inspecting & Autofilling Safe Fields
        ↓
READY_FOR_REVIEW (Browser Process Closed)
        ↓
Human Operator Reviews Review Package
        ↓
Explicit Confirmation (POST /confirm with confirm_text="SUBMIT")
        ↓
Authorized Transition -> COMPLETED / Phase 8 SUBMITTED
```

---

## 8. Implementation & Deployment Status Matrix

| Component / Feature | Implemented | Fixture-Tested | Live-Source Tested | Cloud-Deployed | Status |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Generic Session Infrastructure** | ✅ | ✅ | ⏳ | ⏳ | Complete (Local Verified) |
| **Secure Session Store (`0o600`)** | ✅ | ✅ | ⏳ | ⏳ | Complete (Local Verified) |
| **Source Adapter Registry** | ✅ | ✅ | ⏳ | ⏳ | Complete |
| **LinkedIn Adapter** | ✅ | ✅ | ⏳ | ⏳ | Complete (Fixture Verified) |
| **Naukri Adapter** | ✅ | ✅ | ⏳ | ⏳ | Complete (Fixture Verified) |
| **Instahyre Adapter** | ✅ | ✅ | ⏳ | ⏳ | Complete (Fixture Verified) |
| **Wrong-Job Identity Guard** | ✅ | ✅ | ⏳ | ⏳ | Complete |
| **Duplicate Application Guard** | ✅ | ✅ | ⏳ | ⏳ | Complete |
| **Human Confirmation Boundary** | ✅ | ✅ | ⏳ | ⏳ | Complete & Verified |
| **Cloud KMS Session Encryption** | ⏳ | ⏳ | ⏳ | ⏳ | Reserved for Phase 10D |
| **Live Portal Submissions** | ⏳ | ⏳ | ⏳ | ⏳ | Manual / User-Driven |

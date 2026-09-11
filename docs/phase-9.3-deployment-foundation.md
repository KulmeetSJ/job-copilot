# Phase 9.3 — Deployment Foundation & Security Hardening

Phase 9.3 establishes a reproducible, containerized, CI-tested, security-hardened, and deployment-ready foundation for Job Copilot without modifying locked business logic, candidate truth, or human-in-the-loop safety boundaries.

> [!IMPORTANT]
> **Deployment Readiness Notice:**
> Phase 9.3 delivers a **deployment foundation**. It does not mean the system is already deployed to live cloud infrastructure. Live deployment requires user-configured cloud infrastructure, environment credentials, and persistent data volumes.

---

## 1. Objective

Transform the verified Phase 1–9.2 Job Copilot codebase into a clean, reproducible, and containerized package ready for Git version control and cloud deployment, while strictly isolating private candidate data and credentials.

---

## 2. Repository Structure & Artifact Layout

```text
/
├── .github/
│   └── workflows/
│       └── ci.yml                 # GitHub Actions CI Workflow
├── data/
│   ├── config/                    # [SAFE_TO_COMMIT] Target, source, and copilot configs
│   │   ├── copilot.yaml
│   │   ├── job_sources.yaml
│   │   └── job_targets.yaml
│   ├── resume_strategies/         # [SAFE_TO_COMMIT] Strategy tailoring configs
│   ├── sample_jds/                # [SAFE_TO_COMMIT] Generic test JDs
│   ├── candidate/                 # [SENSITIVE_DO_NOT_COMMIT] Master profile & evidence
│   ├── jobs/                      # [SENSITIVE_DO_NOT_COMMIT] Raw and normalized job store
│   ├── applications/              # [SENSITIVE_DO_NOT_COMMIT] Prepared packages and mappings
│   ├── tracking/                  # [SENSITIVE_DO_NOT_COMMIT] Historical lifecycle logs
│   └── copilot/                   # [SENSITIVE_DO_NOT_COMMIT] Prioritized queue state
├── docs/                          # [SAFE_TO_COMMIT] Architectural documentation
├── src/
│   └── job_copilot/               # [SAFE_TO_COMMIT] Application source code
├── tests/                         # [SAFE_TO_COMMIT] Full regression test suite
├── .dockerignore                  # Docker build exclusions
├── .env.example                   # Environment variable template (no secrets)
├── .gitignore                     # Repository exclusion rules
├── docker-compose.yml             # Local multi-service orchestration
├── Dockerfile                     # Production container definition
├── Makefile                       # Development & execution commands
├── pyproject.toml                 # Package definition & dependencies
└── render.yaml                    # Render Cloud Blueprint specification
```

---

## 3. Security & Data Classification

| Classification | Category | Examples / Paths | Git / Docker Handling |
| :--- | :--- | :--- | :--- |
| **SAFE_TO_COMMIT** | Source Code & Tests | `src/`, `tests/`, `pyproject.toml` | Tracked in Git, included in Docker |
| **SAFE_TO_COMMIT** | Generic Configs | `data/config/*.yaml`, `data/resume_strategies/*.yaml` | Tracked in Git, included in Docker |
| **SAFE_TO_COMMIT** | Deployment Files | `Dockerfile`, `docker-compose.yml`, `render.yaml`, `ci.yml`, `.env.example` | Tracked in Git |
| **SENSITIVE_DO_NOT_COMMIT** | Environment & Secrets | `.env`, `.env.*`, `*.pem`, `*.key` | Ignored by `.gitignore` & `.dockerignore` |
| **SENSITIVE_DO_NOT_COMMIT** | Candidate Personal Data | `data/candidate/master_profile.yaml`, `evidence.yaml` | Ignored; mounted or injected at runtime |
| **SENSITIVE_DO_NOT_COMMIT** | Dynamic Application Data | `data/applications/`, `data/jobs/`, `data/tracking/`, `data/copilot/` | Ignored; stored in external persistent volume |
| **SENSITIVE_DO_NOT_COMMIT** | Databases & Logs | `*.sqlite`, `*.db`, `data/job_copilot.db`, `logs/` | Ignored by `.gitignore` |
| **SENSITIVE_DO_NOT_COMMIT** | Browser Session State | `.playwright/`, `playwright-report/`, `data/downloads/` | Ignored by `.gitignore` |

---

## 4. Environment Variables (`.env.example`)

The application consumes configuration from environment variables (or `.env` in local development):

- **Application:** `APP_ENV` (`development`, `production`), `DEBUG` (`true`/`false`), `LOG_LEVEL` (`INFO`, `DEBUG`, `ERROR`), `LOG_FORMAT` (`text`, `json`), `SECRET_KEY`.
- **API Server:** `API_HOST` (`0.0.0.0`), `API_PORT` (`8000`).
- **Database:** `DATABASE_URL` (`sqlite:///./data/job_copilot.db` or PostgreSQL connection string).
- **Candidate Data:** `CANDIDATE_PROFILE_PATH`, `CANDIDATE_EVIDENCE_PATH`, `CANDIDATE_PREFERENCES_PATH`.
- **Browser Automation:** `PLAYWRIGHT_HEADLESS` (`true`), `BROWSER_TIMEOUT_MS` (`30000`).
- **Safety Boundaries:** `HUMAN_CONFIRMATION_REQUIRED` (`true`).

---

## 5. Local Development Workflow

Run commands via the [`Makefile`](file:///Users/Hp/Apply-Agent/Makefile):

```bash
# 1. Install dependencies & Playwright Chromium
make install

# 2. Run full test suite (165 tests)
make test

# 3. Run secret scanner check
make test-security

# 4. Start local API server (http://localhost:8000)
make run-api

# 5. Run Copilot CLI dashboard
make run-copilot

# 6. Build and run Docker container
make docker-build
make docker-run
```

---

## 6. Dockerization & Container Architecture

The [`Dockerfile`](file:///Users/Hp/Apply-Agent/Dockerfile) is built on `python:3.13-slim-bookworm` with the following properties:
- **Security:** Runs as unprivileged non-root user `appuser` (UID 1000).
- **Dependencies:** Includes Playwright Chromium system dependencies (`libnss3`, `libatk`, `libgbm1`, etc.).
- **Healthcheck:** Configured against `GET /health` with 30s interval.
- **Port:** Exposes `8000`.

To run with Docker Compose:
```bash
docker compose up api              # Start API Web Service
docker compose --profile cron run copilot-cron  # Run periodic discovery
```

---

## 7. GitHub Actions CI Workflow

The workflow at [`.github/workflows/ci.yml`](file:///Users/Hp/Apply-Agent/.github/workflows/ci.yml) executes on every push/PR to `main`:
1. Checks out repository.
2. Sets up Python 3.13 with pip caching.
3. Installs package dependencies & Playwright Chromium.
4. Executes repository secret scanning (`job_copilot.utils.security`).
5. Executes full pytest regression suite (165+ tests).

---

## 8. Health & Status Endpoints

- **`GET /health`**: Returns minimal, non-sensitive health status:
  ```json
  {
    "status": "ok"
  }
  ```
- **`GET /`**: Returns basic service metadata:
  ```json
  {
    "service": "Job Copilot API",
    "version": "0.1.0",
    "status": "online"
  }
  ```

---

## 9. Cloud-Safe & Structured Logging

Enhanced in [`src/job_copilot/utils/logging.py`](file:///Users/Hp/Apply-Agent/src/job_copilot/utils/logging.py):
- Supports standard text output for local development and structured JSON output for cloud log aggregators via `LOG_FORMAT=json`.
- Automatically redacts passwords, bearer tokens, API keys, and session credentials using regex sanitization.

---

## 10. Deployment Architecture (Render Blueprint)

Configured in [`render.yaml`](file:///Users/Hp/Apply-Agent/render.yaml):
- **Web Service (`job-copilot-api`):** Runs FastAPI on port 8000 with healthcheck on `/health`.
- **Periodic Cron Job (`job-copilot-periodic-discovery`):** Executes `python -m job_copilot copilot-discover && python -m job_copilot copilot-process` every 3 hours (`0 */3 * * *`).
- **No Unmanaged Daemons:** Preserves Phase 9's scheduled/periodic execution model.

---

## 11. Playwright & Authentication Safety Boundaries

- **No Credential Bypasses:** Authenticated portals (LinkedIn, Naukri, Instahyre) require manual or browser-session login.
- **State Handling:** If session is unauthenticated, source state is set to `LOGIN_REQUIRED`.
- **Bot Challenge Handling:** CAPTCHA challenges transition sources to `PAUSED` / `BLOCKED`.
- **Submission Barrier:** External portal submission strictly requires human confirmation token.

---

## 12. Candidate Data Separation & Storage Strategy

- **Repository Separation:** Candidate truth (`master_profile.yaml`, `evidence.yaml`) is excluded from source control.
- **Production Injection:** In cloud deployment, candidate profiles are injected via secure environment variables or mounted private volumes.
- **Single Source of Truth:** Canonical truth schema remains authoritatively intact.

---

## 13. What is Intentionally NOT Automated

1. **Credential Harvesting:** The system does not attempt to steal or automatically bypass login credentials.
2. **CAPTCHA Evasion:** The system does not use IP rotation or anti-bot circumvention hacks.
3. **Blind Submissions:** The system never submits applications without human review and confirmation.
4. **Auto Git Pushes:** The system never executes autonomous Git commits or pushes.

---

## 14. Verification Summary

- **Total Test Suite:** 165 / 165 passing (100%).
- **Phase 1–9.2 Integrity:** 100% preserved.
- **Secret Scan:** 0 secrets found.

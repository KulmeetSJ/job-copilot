# Phase 9.4 — Cloud API Deployment

Phase 9.4 deploys the verified Job Copilot FastAPI web service to a cloud environment using the repository's containerized Docker and Render blueprint configuration, transitioning the system from `local + GitHub` to `local + GitHub + live cloud API` without changing any locked business logic or candidate data safety boundaries.

> [!IMPORTANT]
> **Deployment Status Distinction:**
> - **API Service Status:** `DEPLOYED` (Live containerized REST API with `/health` and read-only endpoints).
> - **Full Copilot System:** `NOT FULLY PRODUCTION-READY` (Live authenticated browser automation and persistent stateful workers require subsequent infrastructure phases).

---

## 1. Objective

Provide verifiable cloud deployment for the Job Copilot API service on Render while preserving:
- Strict isolation of candidate personal truth and browser session data.
- Read-only availability of job targets, discovery sources, and operational health.
- Dynamic port and environment-variable runtime binding.
- Immutability of Phases 1–9.3 business rules, scoring, and safety boundaries.

---

## 2. Deployment Architecture

```text
Developer / Pair-Programmer
          │
          ▼
   GitHub Repository (https://github.com/KulmeetSJ/job-copilot.git)
          │
          ├──▶ GitHub Actions CI (Secrets Scan + 168 Pytest Suite)
          │             │
          │          (PASS)
          ▼             ▼
   Render Cloud Platform (render.yaml Blueprint)
          │
          ▼
   Docker Runtime Container (Dockerfile)
   ├── Non-root execution: appuser (UID 1000)
   ├── Dynamic Port Binding: $PORT (default: 8000)
   ├── Non-sensitive Config: data/config/*, data/resume_strategies/*
   │
   └── FastAPI Web Server (uvicorn job_copilot.api.app:app)
          ├── GET /health                      (Container healthcheck & monitoring)
          ├── GET /                            (Service identity & status)
          ├── GET /api/copilot/targets         (Target companies & criteria)
          ├── GET /api/copilot/sources         (Configured discovery sources)
          └── GET /api/copilot/sources/health  (Operational source health)
```

---

## 3. Render Blueprint Configuration (`render.yaml`)

The deployment is managed declaratively via [render.yaml](file:///Users/Hp/Apply-Agent/render.yaml):

```yaml
services:
  # ----------------------------------------------------------------------------
  # 1. API Web Service (Phase 9.4 Cloud Deployment)
  # ----------------------------------------------------------------------------
  - type: web
    name: job-copilot-api
    runtime: docker
    dockerfilePath: Dockerfile
    plan: starter
    region: oregon
    healthCheckPath: /health
    autoDeploy: true
    envVars:
      - key: APP_ENV
        value: production
      - key: LOG_LEVEL
        value: INFO
      - key: LOG_FORMAT
        value: json
      - key: HUMAN_CONFIRMATION_REQUIRED
        value: "true"
      - key: PORT
        value: "8000"

  # ----------------------------------------------------------------------------
  # 2. Scheduled Periodic Copilot Execution (Cron Job - Reserved for Future Phase)
  # NOTE: In Phase 9.4, only the Web API service is active.
  # ----------------------------------------------------------------------------
```

---

## 4. Environment Variables Classification

| Variable | Category | Purpose | Default / Example |
| :--- | :--- | :--- | :--- |
| `PORT` | **Required** | Dynamic port provided by Render for HTTP routing | `8000` |
| `APP_ENV` | **Required** | Application runtime environment | `production` |
| `LOG_LEVEL` | **Required** | Logging threshold | `INFO` |
| `LOG_FORMAT` | **Required** | Structured log format (`json` for cloud log aggregators) | `json` |
| `HUMAN_CONFIRMATION_REQUIRED` | **Required** | Safety invariant ensuring no autonomous submissions | `true` |
| `API_HOST` | **Optional** | Host binding address | `0.0.0.0` |
| `DATABASE_URL` | **Optional** | Database connection string | `sqlite:///./data/job_copilot.db` |
| `SECRET_KEY` | **Optional** | Session signing key (configured in Render Dashboard) | Injected via Render Secrets |
| `CANDIDATE_PROFILE_PATH` | **Optional** | Path to mounted candidate truth file | `./data/candidate/master_profile.yaml` |
| `POSTGRES_URL` | **Future** | Managed relational DB for persistent cloud data | Reserved for Phase 10 |
| `S3_BUCKET_NAME` | **Future** | Object storage for generated PDF packages | Reserved for Phase 10 |
| `OPENAI_API_KEY` | **Future** | Advisory LLM integration | Optional / Future |

---

## 5. Local Docker & Container Verification

The production [`Dockerfile`](file:///Users/Hp/Apply-Agent/Dockerfile) includes:
1. **Base Layer:** `python:3.13-slim-bookworm` with Chromium system libraries.
2. **Security:** Runs as unprivileged non-root user `appuser` (UID 1000).
3. **Isolation:** Excludes `.env`, candidate profiles, and browser sessions via `.dockerignore`.
4. **Dynamic Port Handling:** Entrypoint command dynamically consumes `${PORT:-8000}`.
5. **Healthcheck:** Validates `http://localhost:${PORT:-8000}/health`.

To build and run locally:
```bash
# Build Docker image
make docker-build

# Run container locally on port 8000
make docker-run
```

---

## 6. CI/CD Workflow

The GitHub Actions CI pipeline ([`.github/workflows/ci.yml`](file:///Users/Hp/Apply-Agent/.github/workflows/ci.yml)) runs on every push to `main`:
1. Checks out repository.
2. Sets up Python 3.13 and installs dependencies.
3. Installs Playwright Chromium.
4. Executes secret scanner (`job_copilot.utils.security.scan_repository_for_secrets`).
5. Executes full 168-test regression suite.
6. Render webhooks / GitHub integration triggers automatic redeploy on green commits.

---

## 7. Health Endpoint Specification

- **Endpoint:** `GET /health`
- **Response:**
  ```json
  {
    "status": "ok"
  }
  ```
- **Guarantees:**
  - Fast, deterministic HTTP 200 response.
  - Zero leakage of file paths, environment secrets, or candidate data.
  - Used by Render container orchestrator for zero-downtime rolling deploys.

---

## 8. API Smoke Test Results

All smoke test endpoints were verified:

| Endpoint | Method | Status | Verification Summary |
| :--- | :--- | :--- | :--- |
| `/health` | GET | `200 OK` | Confirms web service is online and healthy |
| `/` | GET | `200 OK` | Returns `{"service": "Job Copilot API", "version": "0.1.0", "status": "online"}` |
| `/api/copilot/targets` | GET | `200 OK` | Returns target company tiers, job families, skills, and locations |
| `/api/copilot/sources` | GET | `200 OK` | Returns 7 configured job discovery sources |
| `/api/copilot/sources/health` | GET | `200 OK` | Returns health reports; authenticated sources report `LOGIN_REQUIRED` |

---

## 9. Security & Candidate Data Separation

- **No Secrets in Repo:** Verified by automated AST/regex secret scanner (`0` findings).
- **Candidate Data Isolation:** `data/candidate/`, `data/applications/`, and `data/tracking/` excluded by `.gitignore` and `.dockerignore`.
- **Log Sanitization:** Sensitive authorization tokens, passwords, and candidate PII are automatically redacted (`[REDACTED]`) by logging handlers.
- **Human Confirmation Invariant:** `HUMAN_CONFIRMATION_REQUIRED=true` enforced across all application mutation endpoints.

---

## 10. Authentication Safety Boundaries (Phase 9.2 Invariant)

- Authenticated portals (LinkedIn, Naukri, Instahyre) report state `LOGIN_REQUIRED`.
- No session cookies, tokens, or credential harvesting scripts are packaged in the Docker container.
- Authenticated sources are never scraped as public job boards.

---

## 11. Render Deployment Details

- **Platform:** Render (Cloud Application Platform)
- **Service Name:** `job-copilot-api`
- **Service Type:** Web Service (Docker Runtime)
- **Region:** Oregon (US-West) / Standard Render Default
- **Live Health URL:** `https://<render-service-subdomain>.onrender.com/health`
- **Live API Root URL:** `https://<render-service-subdomain>.onrender.com/`

---

## 12. Rollback and Redeployment Procedure

1. **Rollback:** In the Render Dashboard (`job-copilot-api` > `Deploys`), select any previous successful build commit and click **Rollback to this deploy**.
2. **Manual Redeploy:** Trigger via `Manual Deploy` > `Deploy latest commit` or push a fix to `main` branch on GitHub.
3. **Local Fallback:** Execute `make run-api` or `make docker-run` locally for isolated debugging.

---

## 13. Known Limitations

1. **Ephemeral Local Storage:** SQLite database inside container is ephemeral between container restarts until a managed PostgreSQL database is attached.
2. **Scheduler Inactive:** The scheduled periodic cron job is deliberately inactive in Phase 9.4 to allow isolated validation of the web API service.
3. **Authenticated Job Sources:** LinkedIn, Naukri, and Instahyre require local or dedicated authenticated browser worker sessions (planned for future phases).

---

## 14. Production-Readiness Status

| Component | Status | Description |
| :--- | :--- | :--- |
| **Local Application** | `READY` | 168/168 tests pass, CLI and MCP functional |
| **Docker Container** | `READY` | Non-root `appuser`, dynamic port binding, healthchecked |
| **CI Pipeline** | `READY` | Automated secret scan and pytest on push/PR |
| **Cloud Web API** | `DEPLOYED` | Cloud service deployed and smoke-tested |
| **Full Job Copilot System** | `PHASED DEPLOYMENT` | Core API live; background workers and persistent storage in future phases |

# Phase 9.6 — Production Persistence Verification

## 1. Objective

Verify that the durable PostgreSQL persistence foundation established in Phase 9.5 is fully operational, resilient, and verifiable in the containerized and Render cloud deployment environment.

This phase is a controlled operationalization and verification milestone. Its goal is to establish that:
- The Job Copilot API service connects to its PostgreSQL database.
- Database connection strings provided by cloud providers (such as Render's `postgres://` or `postgresql://` URIs) are safely normalized to `postgresql+psycopg://` for SQLAlchemy 2.0 / `psycopg3` compatibility.
- Alembic database migrations reach `head` cleanly without destructive downgrade operations.
- The 8 core relational tables, indexes, constraints, and relationships exist and function as designed.
- Controlled synthetic records (`__PHASE_9_6_PERSISTENCE_TEST__`) can be safely written, read, persisted across service/container restarts, and cleanly deleted without polluting production state.
- The `/ready` probe safely verifies database connectivity without leaking credentials, while `/health` remains a lightweight liveness check.
- Candidate truth (`data/candidate/`), local browser session storage, and private resumes remain strictly isolated from cloud databases.

---

## 2. Status Categorization Matrix

| Component / Layer | Status | Description |
| :--- | :--- | :--- |
| **Render Blueprint Configuration** | **CONFIGURED** | `render.yaml` specifies Web Service `job-copilot-api` and managed DB `job-copilot-postgres` with automatic environment binding. |
| **Driver & Dialect Normalization** | **VERIFIED** | `normalize_database_url()` automatically maps `postgres://` and `postgresql://` to `postgresql+psycopg://`. |
| **Local / Container Persistence** | **VERIFIED** | Full CRUD, multi-source provenance, append-only event ledger, and queue persistence verified. |
| **Alembic Schema & Migrations** | **VERIFIED** | Migration `001_initial_schema` reaches `head` cleanly and creates all 8 core tables with foreign keys and cascade rules. |
| **Readiness & Liveness Probes** | **VERIFIED** | `/health` returns 200 OK; `/ready` verifies database connectivity and returns 503 on connection failure with masked logs. |
| **Synthetic Persistence Round-Trip** | **VERIFIED** | Synthetic non-personal test record created, read, verified across engine restart, and deleted. |
| **Restart-Survival Mechanism** | **VERIFIED** | Database persistence verified across process/connection pool teardown and re-instantiation. |
| **Candidate Data Isolation** | **VERIFIED** | `.dockerignore` and `.gitignore` prevent local candidate truth or application artifacts from uploading to cloud. |
| **Cloud Managed DB (Live Render)** | **CONFIGURED / PENDING PROVISIONING** | Ready for automated provisioning on Render deployment via `render.yaml`. |

---

## 3. Render Infrastructure Architecture

The Job Copilot cloud deployment architecture comprises two coordinated managed components defined in [render.yaml](file:///Users/Hp/Apply-Agent/render.yaml):

```
+-------------------------------------------------------------------------+
|                               Render Cloud                              |
|                                                                         |
|   +-----------------------------------------------------------------+   |
|   |                       Web Service: job-copilot-api             |   |
|   |  - Docker Runtime (python:3.13-slim, non-root appuser)          |   |
|   |  - Dynamic PORT / API_PORT binding                             |   |
|   |  - Alembic Auto-migration on Lifespan Startup                  |   |
|   |  - Probes: /health (Liveness), /ready (Database Readiness)     |   |
|   +-----------------------------------------------------------------+   |
|                                    |                                    |
|             DATABASE_URL (Managed Secret from envVarGroups)             |
|                                    v                                    |
|   +-----------------------------------------------------------------+   |
|   |               PostgreSQL Service: job-copilot-postgres          |   |
|   |  - Managed PostgreSQL 16+                                       |   |
|   |  - Internal VPC networking (not unnecessarily public)           |   |
|   |  - 8 Relational Tables + Alembic Version Tracking               |   |
|   +-----------------------------------------------------------------+   |
+-------------------------------------------------------------------------+
```

### Managed Environment Variable Binding
Render's infrastructure dynamically injects `DATABASE_URL` into the `job-copilot-api` service via:
```yaml
envVars:
  - key: DATABASE_URL
    fromDatabase:
      name: job-copilot-postgres
      property: connectionString
```

---

## 4. Database Connection String Normalization

### Driver Compatibility: SQLAlchemy 2.0 & psycopg3
Render provides connection strings starting with `postgres://` or `postgresql://`. In SQLAlchemy 2.0, the `postgres://` dialect identifier has been deprecated and removed in favor of explicit driver names.

Job Copilot implements automated URL normalization in [src/job_copilot/db/database.py](file:///Users/Hp/Apply-Agent/src/job_copilot/db/database.py), [src/job_copilot/db/migrations_runner.py](file:///Users/Hp/Apply-Agent/src/job_copilot/db/migrations_runner.py), and [src/job_copilot/db/migrations/env.py](file:///Users/Hp/Apply-Agent/src/job_copilot/db/migrations/env.py):

```python
def normalize_database_url(url: str) -> str:
    if not url:
        return url
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    if url.startswith("postgresql://") and not url.startswith("postgresql+"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url
```

---

## 5. Alembic Migrations & Schema Verification

### Migration Status: UPGRADE ONLY
Against cloud/production databases, migrations must strictly be forward-only (`alembic upgrade head`). Downgrade operations are verified in isolated local environments and test suites.

### Core Tables & Relationships
1. **`jobs`**: Canonical job postings with unique `job_id`, normalized content hashes, JSON structures for requirements and qualifications.
2. **`job_provenance`**: Multi-source discovery provenance with `uq_job_source_provenance` unique constraint and `ON DELETE CASCADE`.
3. **`recommendations`**: Phase 4 match scores, priority scores, priority bands, category scores, and explanations.
4. **`applications`**: Application tracking records with strategy used and lifecycle status.
5. **`application_events`**: Append-only event ledger tracking all transitions (`DISCOVERED`, `PREPARED`, `SUBMITTED`, etc.) with unique `event_id`.
6. **`application_snapshots`**: Frozen submission records capturing exact match scores and criteria at submission time.
7. **`copilot_queue`**: Prioritized job review queue for human-in-the-loop oversight.
8. **`source_health`**: Real-time status and login requirements across job discovery channels.

---

## 6. Probes & Health Checks

### Liveness Probe: `GET /health`
- **Purpose**: Lightweight process liveness check for container orchestrators.
- **Dependency**: Zero external dependencies (does not require DB connection).
- **Response**: `HTTP 200 OK {"status": "ok"}`

### Readiness Probe: `GET /ready`
- **Purpose**: Verifies that the API service can successfully execute SQL queries against the persistence layer (`SELECT 1`).
- **Response when DB connected**: `HTTP 200 OK {"status": "ready", "database": "connected"}`
- **Response when DB unreachable**: `HTTP 503 SERVICE UNAVAILABLE {"detail": "Database connectivity unavailable"}`
- **Security Invariant**: Never leaks raw database URLs, credentials, hostnames, or SQL error traces.

---

## 7. Controlled Persistence & Restart Survival Test

The persistence lifecycle was verified using a synthetic, non-personal record:

1. **Synthetic Record Creation**:
   - Company: `__PHASE_9_6_PERSISTENCE_TEST__`
   - Job ID: `job-phase-9-6-persistence-synthetic-test`
   - Data Classification: 100% synthetic, no candidate or application data.
2. **Persistence Write & Read**:
   - Record committed to the database store and verified via primary key lookup.
3. **Container / Engine Restart Simulation**:
   - Database session was closed and the engine was fully disposed (`engine.dispose()`).
   - A completely fresh engine and session pool were established against the same storage.
4. **Persistence Verification Post-Restart**:
   - Record re-queried and confirmed identical.
5. **Clean Deletion**:
   - Synthetic test record was permanently deleted and verified absent.

---

## 8. Security & Candidate Data Isolation

- **Zero Candidate Data in Cloud DB**: Candidate profile information (`data/candidate/`), private resumes, and browser storage states are excluded via `.dockerignore` and `.gitignore`.
- **Credential Protection**: `DATABASE_URL` is passed via Render environment variables and never committed to source control or logged in plain text (`sanitize_database_url` masks passwords).
- **Safe Logging**: `sanitize_message` redacts secrets and sensitive tokens from standard output and error streams.

---

## 9. Backup & Disaster Recovery Architecture

| Dimension | Render PostgreSQL Free Tier | Render PostgreSQL Starter / Standard |
| :--- | :--- | :--- |
| **Automated Daily Backups** | Not included (7-day database lifespan) | Included (7 to 30 days retention) |
| **Point-in-Time Recovery (PITR)** | Not included | Included on Pro+ tiers |
| **Restore Procedure** | Manual dump/restore via `pg_dump` / `psql` | One-click restore via Render Dashboard |
| **Production Recommendation** | Suitable for development and verification | Required for production deployment |

---

## 10. Smoke Test Verification Suite

Against the API endpoints, all smoke tests pass deterministically:

| Endpoint | Method | Expected Status | Result |
| :--- | :--- | :--- | :--- |
| `/health` | GET | 200 OK | **PASS** |
| `/` | GET | 200 OK | **PASS** |
| `/ready` | GET | 200 OK | **PASS** |
| `/api/copilot/targets` | GET | 200 OK | **PASS** |
| `/api/copilot/sources` | GET | 200 OK | **PASS** |
| `/api/copilot/sources/health` | GET | 200 OK | **PASS** |

---

## 11. Locked-Phase Integrity Status

- **Phase 1 (Foundation)**: PASS — Core domain entities and configuration integrity preserved.
- **Phase 2 (Candidate Truth)**: PASS — Zero candidate truth data committed or exposed.
- **Phase 3 (Resume Strategies)**: PASS — Strategy generation logic unchanged.
- **Phase 4 (Job Intelligence & Scoring)**: PASS — Scoring weights, thresholds, and risk rules untouched.
- **Phase 5 (Discovery & Deduplication)**: PASS — Deduplication and multi-source provenance intact.
- **Phase 6 (Application Prep)**: PASS — Application package generation and validation unchanged.
- **Phase 7 (Browser Workflow & Safety)**: PASS — Human confirmation invariants and CAPTCHA pause behaviors preserved.
- **Phase 8 (Tracking & Outcome Analytics)**: PASS — Append-only event ledger semantics fully preserved in relational schema.
- **Phase 9 (Job Copilot Orchestration)**: PASS — Priority calculation, targeting, and queue management operational.
- **Phase 9.2 (Targeting & Sources)**: PASS — Target companies, source health, and login states intact.
- **Phase 9.3 (Deployment Foundation)**: PASS — Docker, security hardening, and secret scanning verified.
- **Phase 9.4 (Cloud API Deployment)**: PASS — API deployment blueprint and dynamic port binding verified.
- **Phase 9.5 (Persistent Storage & Database Foundation)**: PASS — 8 core tables and Alembic migrations fully verified.

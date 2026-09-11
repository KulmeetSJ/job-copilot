# Job Copilot 🚀

A personal Job Application Automation and Copilot system for finding, evaluating, tailoring, applying to, and tracking software engineering jobs.

---

## Features (Milestone 1 - Foundation)

- **Canonical Master Candidate Profile**: Structured YAML-based source of truth (`data/candidate/master_profile.yaml`) storing validated work history, achievements with metrics, categorized skills, education, and career preferences.
- **Model Context Protocol (MCP) Server**: Built with the official Python MCP SDK, allowing AI assistants (Claude Desktop, Cursor, Gemini) to query candidate profile data, analyze job postings, and track applications.
- **Service & Repository Layer**: Clean architectural separation ensuring business logic is independent of UI, MCP, and database layers.
- **Database Persistence**: SQLAlchemy 2.0 ORM with SQLite (Postgres-ready) for job posting management and application lifecycle tracking.
- **FastAPI Core**: Lightweight REST API with health endpoints.
- **Strict Factual Accuracy Policy**: Built-in design invariants preventing AI-driven fabrication of skills, metrics, or experiences.

---

## Quickstart

### 1. Prerequisites
- Python 3.12+

### 2. Installation

Create a virtual environment and install the package with development dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Or using the Makefile:
```bash
make install
```

### 3. Initialize & Verify System

Run the system status check to verify the database and master profile:

```bash
python -m job_copilot
```

Or initialize database explicitly:
```bash
python -m job_copilot --init-db
```

---

## Running the Services

### Running the FastAPI Web Server
```bash
# Via console script
job-copilot-api

# Or via uvicorn
uvicorn job_copilot.api.app:app --host 0.0.0.0 --port 8000 --reload
```
Health Check:
```bash
curl http://localhost:8000/health
# Response: {"status": "ok"}
```

### Running the MCP Server
```bash
# Via console script
job-copilot-mcp

# Or via module
python -m job_copilot.mcp.server
```

#### Configuring MCP in Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "job-copilot": {
      "command": "/path/to/Apply-Agent/.venv/bin/python",
      "args": ["-m", "job_copilot.mcp.server"],
      "cwd": "/path/to/Apply-Agent"
    }
  }
}
```

---

## Running Tests

Execute the automated test suite with pytest:

```bash
pytest -v
```
Or:
```bash
make test
```

---

## Project Structure

```
job-copilot/
├── src/
│   └── job_copilot/
│       ├── __main__.py               # CLI entrypoint & diagnostic check
│       ├── config.py                 # Pydantic Settings
│       ├── api/
│       │   └── app.py                # FastAPI web service
│       ├── mcp/
│       │   └── server.py             # FastMCP tools
│       ├── domain/
│       │   └── enums.py              # ApplicationStatus, RemoteStatus, Strategy
│       ├── models/
│       │   ├── base.py               # SQLAlchemy Declarative Base
│       │   ├── job.py                # Job ORM model
│       │   └── application.py        # Application ORM model
│       ├── schemas/
│       │   ├── candidate.py          # Master Profile Pydantic schemas
│       │   ├── job.py                # Job & JobAnalysis schemas
│       │   └── application.py        # Application schemas
│       ├── repositories/
│       │   ├── candidate_repository.py # YAML-based profile persistence
│       │   ├── job_repository.py     # SQLAlchemy Job repository
│       │   └── application_repository.py # SQLAlchemy Application repository
│       ├── services/
│       │   ├── candidate_service.py  # Profile retrieval service
│       │   ├── job_service.py        # Job creation & keyword match scoring
│       │   ├── application_service.py# Application tracking & status transitions
│       │   └── resume_service.py     # Resume generation interfaces
│       ├── resume/
│       │   ├── profile.py            # Tailored resume schemas
│       │   ├── renderer.py           # LaTeX renderer interface/stubs
│       │   └── templates/            # LaTeX templates directory
│       └── db/
│           ├── database.py           # Engine & SessionLocal
│           └── base.py               # Model registry
├── tests/
│   ├── conftest.py
│   ├── unit/
│   │   ├── test_candidate_profile.py
│   │   ├── test_database.py
│   │   ├── test_repositories.py
│   │   └── test_services.py
│   └── integration/
│       ├── test_api.py
│       └── test_mcp.py
├── data/
│   ├── candidate/
│   │   └── master_profile.yaml       # Canonical Master Profile
│   ├── resumes/                      # Input candidate resumes
│   ├── generated/                    # Output tailored resumes / cover letters
│   └── jobs/                         # Saved job postings
├── docs/
│   └── architecture.md               # Detailed architecture & Mermaid diagram
├── .env.example
├── .gitignore
├── pyproject.toml
└── Makefile
```

---

## Roadmap

- [x] **Milestone 1**: Foundational Architecture, Master Profile Schema, Database, MCP Tools, FastAPI, Test Suite.
- [x] **Milestone 2**: Ingest candidate resumes, reconcile contradictions, and finalize Master Candidate Profile (Phase 2).
- [x] **Milestone 3**: Deterministic Resume Tailoring Engine with 5 verified strategies and 1-page LaTeX rendering (Phase 3 & 3.5).
- [x] **Milestone 4**: Deterministic Job Intelligence, Multi-Dimensional Fit Scoring, Strategy Selector & Explainable Reports (Phase 4).
- [x] **Milestone 5**: Job Discovery & Ingestion Engine with Source Adapters, Normalization, Deduplication, and Store Indexing (Phase 5).
- [x] **Milestone 6**: Application Preparation Engine (Evidence-backed Cover Letters, Q&A Classification, User Input Requests) (Phase 6).
- [x] **Milestone 7**: Browser-Assisted Application Workflow with Playwright automation, safe auto-fill, human confirmation gate (Phase 7).
- [x] **Milestone 8**: Application Tracking, Immutable Lifecycle Ledger & Outcome Analytics (Phase 8).

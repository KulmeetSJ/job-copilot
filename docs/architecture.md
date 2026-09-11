# Job Copilot — System Architecture

## 1. Overview & Philosophy

**Job Copilot** is a personal engineering system designed to automate, tailor, evaluate, and track software engineering job applications.

### Core Architectural Principles
* **Layered Clean Architecture**: Strict separation of concerns (Schemas/Domain → Repositories → Services → Interfaces [API & MCP]).
* **Single Source of Truth**: The **Canonical Master Candidate Profile** (`data/candidate/master_profile.yaml`) is the sole factual authority for candidate background, experience, metrics, and skills.
* **Zero AI Hallucination Invariant**: Tailored resumes and application answers are strictly derived projections and faithful rephrasings of the Master Profile. The AI is structurally forbidden from fabricating metrics, roles, dates, or skills.
* **Extensible Persistence**: SQLite by default via SQLAlchemy 2.0 ORM; designed for zero-refactor migration to PostgreSQL.
* **Agent-First Control**: Comprehensive Model Context Protocol (MCP) server enables AI agents (like Claude Desktop or Gemini) to operate the application lifecycle conversationally.

---

## 2. Architecture Diagram

```mermaid
flowchart TD
    subgraph UI_Agents ["Interfaces & Interaction"]
        Agent["AI Assistant / MCP Client (Claude / Gemini)"]
        FastAPI_App["FastAPI REST API (Dashboard Backend)"]
        CLI["CLI Tool (python -m job_copilot)"]
    end

    subgraph Interface_Layer ["Interface Adapters"]
        MCP_Server["FastMCP Server (job_copilot.mcp)"]
        API_Routes["API Endpoints (job_copilot.api)"]
    end

    subgraph Service_Layer ["Application Services"]
        CandidateService["CandidateService"]
        JobService["JobService"]
        ApplicationService["ApplicationService"]
        ResumeService["ResumeService (Tailoring & LaTeX)"]
    end

    subgraph Data_Layer ["Data Access & Storage"]
        CandidateRepo["CandidateRepository (YAML Source of Truth)"]
        JobRepo["JobRepository (SQLAlchemy)"]
        AppRepo["ApplicationRepository (SQLAlchemy)"]
        
        MasterYAML[("data/candidate/master_profile.yaml")]
        SQLiteDB[("SQLite Database (job_copilot.db)")]
    end

    Agent <-->|MCP Protocol (stdio)| MCP_Server
    FastAPI_App <--> API_Routes
    CLI <--> Service_Layer

    MCP_Server --> CandidateService
    MCP_Server --> JobService
    MCP_Server --> ApplicationService

    API_Routes --> JobService
    API_Routes --> ApplicationService

    CandidateService --> CandidateRepo
    ResumeService --> CandidateRepo
    JobService --> JobRepo
    ApplicationService --> AppRepo

    CandidateRepo <--> MasterYAML
    JobRepo <--> SQLiteDB
    AppRepo <--> SQLiteDB
```

---

## 3. Component Breakdown

### 3.1 Domain & Schemas (`job_copilot.schemas`, `job_copilot.domain`)
- **`CandidateProfile`**: Comprehensive schema representing personal info, work authorization, education, categorized skills, structured experiences, achievements with metrics, projects, and career preferences.
- **`JobBase / JobRead / JobCreate`**: Structured representation of ingested job descriptions, requirements, compensation, and qualifications.
- **`ApplicationBase / ApplicationRead`**: Application lifecycle tracking model.
- **`ApplicationStatus`**: Enum tracking states: `DISCOVERED` → `SHORTLISTED` → `PREPARING` → `READY_TO_APPLY` → `APPLIED` → `OA` → `INTERVIEW` → `OFFER` / `REJECTED` / `WITHDRAWN`.

### 3.2 Repositories (`job_copilot.repositories`)
- **`CandidateRepository`**: Handles disk I/O, validation, and serialization for `master_profile.yaml`.
- **`JobRepository`**: SQLAlchemy repository managing job persistence and queries.
- **`ApplicationRepository`**: SQLAlchemy repository managing application lifecycle records and joins with jobs.

### 3.3 Services (`job_copilot.services`)
- **`CandidateService`**: Exposes validated profile entities, skill matrices, and work histories.
- **`JobService`**: Coordinates job creation, listing, and deterministic keyword/profile match scoring.
- **`ApplicationService`**: Coordinates application creation, status transitions, and timeline logging.
- **`ResumeService`**: Coordinates master profile verification and future LaTeX resume rendering pipelines.

### 3.4 MCP Server (`job_copilot.mcp.server`)
Uses the official Python MCP SDK (`FastMCP`) to expose tools:
- `get_candidate_profile`: Returns complete canonical profile.
- `get_candidate_skills`: Returns categorized technical skills.
- `get_experience`: Returns verified work history.
- `get_projects`: Returns portfolio projects.
- `analyze_job`: Evaluates job description against candidate skills and suggests resume strategy.
- `list_applications`: Returns tracked applications and their statuses.

---

## 4. Safety & Factual Integrity Rules

1. **No Hallucinated Work History**: Tailoring only selects, orders, highlights, or tightens existing factual bullets.
2. **No Hallucinated Skills**: Skills extracted in resumes must exist in the candidate's canonical skill matrix.
3. **No Fabricated Metrics**: If an achievement does not have a metric recorded in the Master Profile, the system will not invent one.
4. **Audit Trail**: Every status change and tailoring strategy is logged in the application tracking database.

---

## 5. Incremental Project Roadmap

1. **Milestone 1 (Current)**: Foundational architecture, domain models, YAML master profile, SQLite database, service layer, FastMCP tools, FastAPI health endpoint, test suite.
2. **Milestone 2**: Ingest candidate resumes, reconcile contradictions, build the finalized Master Profile.
3. **Milestone 3**: Resume Tailoring Engine & LaTeX PDF rendering with multiple target strategies (Backend Java, Cloud/Data, DevOps/Platform, AI/Backend).
4. **Milestone 4**: Job Ingestion & LLM Semantic Job Scorer.
5. **Milestone 5**: Application Preparation (Cover Letters, Tailored QA Generation).
6. **Milestone 6**: Playwright-assisted Browser Automation for form filling and submission verification.
7. **Milestone 7**: Next.js Dashboard & Outcome Analytics.

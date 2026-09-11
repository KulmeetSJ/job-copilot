# Phase 6 — Application Preparation Engine

## 1. Overview & Architecture

Phase 6 introduces the **Application Preparation Engine** to Job Copilot. Given a selected, analyzed, and matched job, this engine generates a complete, validated application package:
1. Reuses the Phase 4 Job Assessment & Strategy Selector.
2. Compiles or retrieves the Phase 3 tailored 1-page LaTeX PDF resume.
3. Generates a tailored Cover Letter with deterministic truth-safety validation.
4. Ingests and classifies application questions (`ANSWERABLE_FROM_EVIDENCE`, `ANSWER_REQUIRES_USER_INPUT`, `DO_NOT_ANSWER`).
5. Synthesizes factual answers directly from candidate truth with attached provenance.
6. Surfaces sensitive personal/legal/salary/visa questions as structured `UserInputRequest` items for human decision.
7. Bundles the complete package under `data/applications/<job_id>/`.

```
                      Selected / Discovered Job
                                 │
                                 ▼
                    Phase 4 Job Assessment
                    (Score, Recommendation,
                     Strategy Selection)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
      Phase 3 Resume Service           Cover Letter Engine
      (Retrieve/Generate 1-page PDF)   (Draft + Truth Validation)
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                     Application Questions
                                 │
                                 ▼
                    Question Classification Engine
        (ANSWERABLE_FROM_EVIDENCE | ANSWER_REQUIRES_USER_INPUT | DO_NOT_ANSWER)
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
      Evidence Retrieval &             User Input Extractor
      Answer Synthesis Engine          (Structured User Requests)
                 │                               │
                 └───────────────┬───────────────┘
                                 ▼
                   Application Package Validator
                                 │
                                 ▼
                    Unified Application Package
                    (data/applications/<job_id>/)
```

---

## 2. Core Components

### A. Question Classification (`src/job_copilot/application/classifier.py`)
- **`ANSWERABLE_FROM_EVIDENCE`**: Questions addressing evidenced technologies (Java, Spring Boot, GCP, BigQuery, Beam, Airflow, Payments, Terraform, Redis, Docker, Microservices, CI/CD, Observability) or role motivation.
- **`ANSWER_REQUIRES_USER_INPUT`**: Questions touching sensitive personal, financial, or legal parameters:
  - Salary expectations & current compensation.
  - Visa sponsorship & legal work authorization.
  - Notice period, start dates, and availability.
  - Relocation, travel, and onsite preferences.
  - High-seniority depth questions (e.g. "Do you have production Kubernetes experience?").
- **`DO_NOT_ANSWER`**: Questions requiring unevidenced or fabricated capabilities (e.g. "Do you have 5+ years of AWS production experience?" or embedded hardware protocols).

### B. Evidence Retrieval & Answer Synthesis (`src/job_copilot/application/qa_engine.py`)
- Retrieves facts from canonical `master_profile.yaml`.
- Enforces strict truth-safety rules:
  - Professional experience cited with `EXP-HSBC-*` and enterprise context.
  - Project experience (Rate Limiter / Redis) explicitly labeled as personal/portfolio projects (`PRJ-RL-001`), never promoted to enterprise production.
  - GKE and Helm cited strictly as hands-on / training exposure (`SKL-GKE-001`, `SKL-HELM-001`).
  - Benchmarks (100K+ RPS) strictly cited as project load test measurements.
  - Missing evidence = `DO_NOT_ANSWER` or `USER_INPUT`. Never fabricated.
- Every answer attaches `List[ClaimProvenance]`.

### C. Cover Letter Generator & Validator (`src/job_copilot/application/cover_letter.py`)
- Composes 200–350 word professional cover letters tailored to the target role and company.
- Deterministic validator verifies:
  - No unsupported cloud technologies (e.g. AWS).
  - No unsupported years of experience (> 2 years).
  - No benchmark promotion to production.
  - Correct company and role references.

### D. Application Package Persistence (`src/job_copilot/services/application_prep_service.py`)
- Persists structured artifacts in `data/applications/<job_id>/`:
  - `package.json` — Complete serialized package.
  - `cover_letter.md` & `cover_letter.json` — Cover letter and provenance.
  - `questions.json` — Full question list, answers, and `user_inputs_required`.
  - `validation.json` — Truth safety status and checks.

---

## 3. CLI Commands

```bash
# 1. Prepare complete application package
python -m job_copilot prepare-job manual-java-backend-jd

# 2. Answer a single question with evidence
python -m job_copilot answer-question manual-java-backend-jd --question "Describe your Java experience."

# 3. View validated cover letter
python -m job_copilot generate-cover-letter manual-java-backend-jd

# 4. View application package summary
python -m job_copilot application-package manual-java-backend-jd

# 5. Inspect unresolved user inputs required
python -m job_copilot application-inputs manual-java-backend-jd
```

---

## 4. FastAPI Endpoints

- `POST /api/applications/prepare`: Prepare complete application package for a job.
- `GET /api/applications/{job_id}`: Retrieve saved application package.
- `POST /api/applications/{job_id}/questions`: Ingest and answer a batch of application questions.
- `POST /api/applications/{job_id}/cover-letter`: Generate or retrieve validated cover letter.
- `GET /api/applications/{job_id}/inputs`: Retrieve unresolved `UserInputRequest` models.
- `POST /api/applications/{job_id}/validate`: Run truth-safety validation checks on the package.

---

## 5. Phase 7 Integration Points

Phase 6 produces clean structured JSON artifacts (`package.json`, `questions.json`, `UserInputRequest` list).
In Phase 7 (Browser Interaction & Form Filling):
- The browser automation subagent extracts form fields and sends them to `POST /api/applications/{job_id}/questions`.
- Answerable questions receive pre-filled, evidence-backed text.
- Sensitive or user-input required fields prompt the candidate for confirmation before form submission.

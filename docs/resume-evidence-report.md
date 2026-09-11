# Resume Evidence & Provenance Report

## 1. Architectural Philosophy: The Three Layers

In Phase 2, we enforce a strict architectural boundary across three distinct concepts:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. FACT (data/candidate/master_profile.yaml)                │
│    Factual, verified candidate background without           │
│    subjective adjectives or inferred proficiencies.         │
└──────────────────────────────┬──────────────────────────────┘
                               │ references evidence_ids
┌──────────────────────────────▼──────────────────────────────┐
│ 2. EVIDENCE (data/candidate/evidence.yaml)                  │
│    Atomic claims with exact source file, section, context,   │
│    claim_type, metric_type, and status (CONFIRMED/REVIEW).   │
└─────────────────────────────────────────────────────────────┘
                               │ guides targeting
┌──────────────────────────────▼──────────────────────────────┐
│ 3. POSITIONING & PREFERENCES (data/candidate/preferences.yaml)│
│    Target roles, resume tracks (Cloud/DevOps, Java Backend, │
│    SRE, Data), taglines, location/salary preferences.        │
└─────────────────────────────────────────────────────────────┘
```

> **Core Invariant**:
> **FACTS NEVER CHANGE BASED ON THE JOB.**
> **POSITIONING CHANGES BASED ON THE JOB.**

---

## 2. Ingestion Corpus (18 Files Processed)

All extractions are derived exclusively from files physically present in `data/resumes/`:

| # | Filename | Format | Strategy / Primary Focus |
|---|---|---|---|
| 1 | `Kulmeet_Singh_Resume.pdf` | PDF | Cloud & DevOps / GCP Data Platform |
| 2 | `Kulmeet_Singh_Resume_MS.pdf` | PDF | Cloud & DevOps (Microsoft / Stakeholder focus) |
| 3 | `Kulmeet_Resume_JPMorgan_DevOps.pdf` | PDF | Site Reliability Engineering (SRE) & DevSecOps |
| 4 | `Kulmeet_Resume_JPMorgan_DevOps.tex` | LaTeX | Source LaTeX document for JPMorgan SRE resume |
| 5 | `Kulmeet_Resume_Java_React_FullStack.pdf` | PDF | Full Stack Engineer (Java Spring Boot + React/Next.js) |
| 6 | `KulmeetSingh_Java.pdf` | PDF | Java Backend & Full Stack Engineer |
| 7 | `Kulmeet_Resume_Mastercard_Backend_Engineer.pdf` | PDF | Backend Engineer (High-throughput APIs & Redis) |
| 8 | `Kulmeet_Resume_Mastercard_Implementation_Specialist.pdf` | PDF | Processing Implementation Specialist (Payment schemes) |
| 9 | `Kulmeet_Resume_Cloud_Engineer_v2.pdf` | PDF | Cloud Infrastructure Engineer (GCP, Terraform, Cost optimization) |
| 10 | `Kulmeet_Resume_Data_Engineer_v2.pdf` | PDF | Data Engineer (Apache Beam, BigQuery, Airflow, Parquet) |
| 11 | `Kulmeet_Resume_DevOps_v2.pdf` | PDF | DevOps Engineer (Jenkins CI/CD, SonarQube, Checkmarx) |
| 12 | `Kulmeet_Resume_Frontend_v2.pdf` | PDF | Frontend / Full Stack (React, Next.js, Supabase) |
| 13 | `Kulmeet_Resume_Generic_Neutral.pdf` | PDF | General Software Engineer |
| 14 | `Kulmeet_Singh_Resume_Final.pdf` | PDF | Cloud & DevOps (GCP IaC & Dataflow Automation) |
| 15 | `Kulmeet_Singh_Resume_2.pdf` | PDF | Cloud & DevOps (with RFP Management System) |
| 16 | `KulmeetSingh_Resume.pdf` | PDF | Software Engineer (with High School details) |
| 17 | `Kulmeet Singh Jaggi_Pat on the Back.pdf` | PDF | Official HSBC Leadership Award Certificate (Q1 2026) |

---

## 3. Candidate-Confirmed Decisions & Resolutions

### 3.1 Employment Title (Resolved: DEC-TITLE-001)
- **Official Corporate/HR Title**: `Software Engineer`
- **Canonical Role**: Locked as `Software Engineer` in `master_profile.yaml`.
- **Positioning Variants**: Preserved under `historical_titles` and in `preferences.yaml` as role-targeting presets (`Cloud & DevOps`, `Backend & Distributed Systems`, `Data Platform`, `SRE`, `Full Stack`). They will never overwrite the official employment record.

### 3.2 Metrics & Context Restrictions (Resolved: DEC-MET-001 & DEC-MET-002)

| Metric ID | Exact Value | Claim Type | Metric Type | Context & Usage Restriction |
|---|---|---|---|---|
| `MET-001` | **2,000+** | PROFESSIONAL | PRODUCTION | GCP resources provisioned using Terraform. |
| `MET-002` | **60%** | PROFESSIONAL | PRODUCTION | Infrastructure provisioning time acceleration. |
| `MET-003` | **10M+** | PROFESSIONAL | PRODUCTION | Daily payment transactions ingested via Apache Beam. |
| `MET-004` | **99.9%** | PROFESSIONAL | PRODUCTION | Uptime for the Beam payment streaming pipeline *(not generalized company-wide)*. |
| `MET-005` | **30%** | PROFESSIONAL | PRODUCTION | Compute cost reduction through Dataflow weekend shutdown/restart automation. |
| `MET-006` | **$150K+** | PROFESSIONAL | ESTIMATE | Annualized compute savings associated with the 30% cost reduction. |
| `MET-007` | **100+** | PROFESSIONAL | PRODUCTION | Cloud Composer DAG deployments automated via Jenkins. |
| `MET-008` | **40%** | PROFESSIONAL | PRODUCTION | MTTR / incident detection speedup for relevant monitoring workflows. |
| `MET-009` | **12+** | PROFESSIONAL | PRODUCTION | Critical misconfigurations caught by shift-left security tool. |
| `MET-010` | **35%** | PROFESSIONAL | PRODUCTION | Code review time reduction via Terraform plan summarizer. |
| `MET-011` | **70%** | PERSONAL_PROJECT | PROJECT | Troubleshooting time reduction for MCP Diagnostic Tools. |
| `MET-012` | **95%+** | PERSONAL_PROJECT | PROJECT | Claimed diagnostic accuracy for MCP Diagnostic Tools *(not organization-wide production accuracy)*. |
| `MET-013` | **1TB+** | PERSONAL_PROJECT | PROJECT | BigQuery data converted to Parquet in Smart Data Storage project. |
| `MET-014` | **55%** | PERSONAL_PROJECT | PROJECT | Query performance improvement in Smart Data Storage project. |
| `MET-015` | **50K+** | PERSONAL_PROJECT | PROJECT | Files tiered to Coldline in Smart Data Storage project. |
| `MET-016` | **80%** | PERSONAL_PROJECT | PROJECT | RFP drafting time reduction in AI RFP Management project. |
| `MET-017` | **100K+** | BENCHMARK | BENCHMARK | Rate limiter benchmark only. **Never characterize as HSBC / production traffic.** |

### 3.3 Technologies & Skills Classification (Resolved: DEC-TECH-001)
- **Confirmed Professional / Project Skills**:
  - `GCP (Pub/Sub, BigQuery, Dataflow, Cloud Composer, GCS, IAM, Cloud Monitoring)`
  - `Terraform`, `Java (Spring Boot)`, `Python`, `SQL`, `Groovy`
  - `Apache Beam`, `Apache Airflow`, `Jenkins`, `Docker`
  - `PostgreSQL`, `Redis`, `FastAPI`, `React`, `Next.js`, `Tailwind CSS`
  - `Model Context Protocol (MCP)`, `Claude API`
  - `SonarQube`, `Checkmarx`, `Nexus`
- **Retained as NEEDS_REVIEW (Not Confirmed Professional Experience)**:
  - `AWS (EC2, S3, IAM)`: Kept as `NEEDS_REVIEW` / `POSITIONING_ONLY`.
  - `Kubernetes (GKE)`: Kept as `NEEDS_REVIEW`.
  - `Apache Kafka`: Kept as `NEEDS_REVIEW`.

### 3.4 Project Contexts (Resolved: DEC-PRJ-001)
All projects (`MCP Diagnostic Tools`, `Terraform Compliance Checker`, `Smart Data Storage Pipeline`, `GuruGranthi Services Marketplace`, `AI-Powered RFP Management System`, `Distributed Rate Limiter Service`) are marked `deployment_status: "PORTFOLIO_DEMO"`.

### 3.5 Certifications & Awards (Resolved: DEC-CERT-001)
- **Google Cloud Professional Cloud Architect**: Confirmed. Credential IDs and dates remain null until supplied.
- **Pat on the Back Award (Q1 2026)**: Confirmed with certificate from Vikram Kulkarni.
- **Flipkart Grid 5.0 Semi-Finalist**: Confirmed.

### 3.6 Work Authorization & Preferences (Resolved: DEC-PREF-001)
- **Primary Location**: `Pune, India`
- **Work Authorization**: `current_country: "India"`, `current_work_authorization: null` (unverified until explicitly confirmed).
- **International Sponsorship**: `international_sponsorship_required: true` for international destinations.
- **Salary**: `target_salary_min: null`, `currency: "INR"`.
- **LeetCode**: Handle/URL remains `null` / unconfirmed.

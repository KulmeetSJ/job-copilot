# Phase 9.2 — Job Targeting & Source Configuration

Phase 9.2 introduces structured, candidate-controlled targeting and discovery source configuration for the Continuous Job Copilot without modifying locked Phase 1–9 core matching algorithms or candidate truth.

---

## 1. Core Architecture & Separation of Concerns

Phase 9.2 strictly decouples three operational concepts:

```
WHERE to search        WHO / WHAT to prioritize       HOW to make decisions
      ↓                           ↓                              ↓
job_sources.yaml          job_targets.yaml                 copilot.yaml
```

> [!IMPORTANT]
> **Candidate Truth & Immutability Guarantee:**
> - Candidate truth remains exclusively authoritative in `data/candidate/master_profile.yaml` and `data/candidate/evidence.yaml`.
> - Targeting preferences are discovery and prioritization signals, NOT candidate qualification evidence.
> - The absence of a company from the target list does NOT prevent discovery, scoring, or recommendation.

---

## 2. Target Companies & Preference Tiers

Target employers are defined in [`data/config/job_targets.yaml`](file:///Users/Hp/Apply-Agent/data/config/job_targets.yaml) and categorized into domain tiers:

### Tier 1 — Financial Services / Payments / Banking
Companies with high domain adjacency to the candidate's verified HSBC Payments and Data Platform experience:
- **Companies:** Mastercard, Deutsche Bank, Morgan Stanley, JPMorgan Chase, Goldman Sachs, Citi, UBS, Barclays, Bajaj Finance, Stripe, Finastra, American Express
- **Priority Tier:** `1`
- **Domain Group:** `financial_services`
- **Preference Bonus:** `+5.0` points
- **Rationale:** High domain alignment with real-time transactional systems and payment platforms.

### Tier 2 — Technology / Product
High-scale engineering environments and consumer/enterprise technology leaders:
- **Companies:** Zomato, Blinkit, Myntra, Microsoft, Google, Uber, Ola, Siemens, Meta, Optum
- **Priority Tier:** `2`
- **Domain Group:** `technology_product`
- **Preference Bonus:** `+2.0` points
- **Rationale:** High-scale distributed systems and cloud data infrastructure engineering.

### Non-Target Companies (Discoverability Guarantee)
- Non-target employers receive `0.0` preference bonus and are **NEVER ignored or filtered out**.
- A high-fit non-target job (e.g., Fit Score = 94.0) achieves `CRITICAL` / `HIGH` priority.
- A low-fit Tier 1 job (e.g., Fit Score = 45.0) remains `MEDIUM` / `LOW` priority and is never automatically recommended.

---

## 3. Job Families, Skills & Locations

### Job Families
Broad role families (not exact-title restrictions):
- **Primary:** Backend Software Engineer, Software Engineer - Java, Java Backend Engineer, Backend Engineer, Software Engineer - Distributed Systems, Platform Engineer, Data Platform Engineer, Data Engineer, Cloud Engineer, Cloud Platform Engineer, DevOps Engineer, Site Reliability Engineer, SRE.
- **Secondary:** Full Stack Engineer, Software Engineer - GCP, Software Engineer - Data, Infrastructure Engineer, Production Engineer, Payments Engineer, Payment Systems Engineer.

### Skills & Search Signals
- **High Priority:** Java, Spring Boot, GCP, BigQuery, Pub/Sub, Dataflow, Apache Beam, Terraform, Jenkins, Python, SQL, Distributed Systems, Data Platform, Payments.
- **Secondary:** Docker, Kubernetes, GKE, Helm, Kafka, Airflow, Cloud Composer, React, TypeScript, Next.js.

### Locations & Remote Policies
- **Primary:** Pune, Bangalore / Bengaluru, Hyderabad, Delhi NCR, Gurgaon / Gurugram, Mumbai.
- **Secondary:** Chennai, Noida, Remote - India.
- **International:** Enabled (Singapore, Tokyo).
- **Supported Remote Modes:** `REMOTE_WORLDWIDE`, `REMOTE_INDIA`, `REMOTE_REGION_RESTRICTED`, `HYBRID`, `ONSITE`, `UNKNOWN`.

---

## 4. Job Sources Registry & Capability Model

Defined in [`data/config/job_sources.yaml`](file:///Users/Hp/Apply-Agent/data/config/job_sources.yaml):

| Source ID | Source Name | Discovery Mode | Requires Login | Check Interval | Priority |
| :--- | :--- | :--- | :---: | :---: | :--- |
| `linkedin_pune` | LinkedIn Jobs - Pune | `AUTHENTICATED_BROWSER` | Yes | 60m | CRITICAL |
| `naukri` | Naukri | `AUTHENTICATED_BROWSER` | Yes | 180m | HIGH |
| `instahyre` | Instahyre | `AUTHENTICATED_BROWSER` | Yes | 180m | HIGH |
| `wellfound` | Wellfound | `PUBLIC` | No | 180m | HIGH |
| `welcome_to_the_jungle` | Welcome to the Jungle | `PUBLIC` | No | 180m | HIGH |
| `we_work_remotely` | We Work Remotely | `PUBLIC` | No | 360m | HIGH |
| `example_source` | Example Source Template | `PUBLIC` | No | 360m | MEDIUM (Disabled) |

### Discovery Modes & States
- **Discovery Modes:** `PUBLIC`, `AUTHENTICATED_BROWSER`, `USER_PROVIDED_SEARCH_URL`, `FEED`, `MANUAL`, `UNSUPPORTED`.
- **Source States:** `ACTIVE`, `PAUSED`, `LOGIN_REQUIRED`, `BLOCKED`, `ERROR`, `UNSUPPORTED`, `DISABLED`.

---

## 5. Safety, Authentication & CAPTCHA Boundaries

The Job Copilot strictly enforces ethical automation standards:
- **No Login Bypass:** Authenticated portals (LinkedIn, Naukri, Instahyre) require user-initiated browser sessions. If unauthenticated, the source state is set to `LOGIN_REQUIRED`.
- **No CAPTCHA / Anti-Bot Bypass:** If bot challenges are encountered, the source transitions to `BLOCKED` or `PAUSED` without crashing the copilot or halting discovery across other sources.
- **No Unmanaged Daemons:** Execution remains scheduled / periodic via cron, CLI, or API.

---

## 6. Multi-Source Deduplication & Provenance

When the same opportunity is discovered across multiple platforms (e.g., LinkedIn + Wellfound + Careers Portal):
1. Phase 5's `JobDeduplicator` matches identical canonical URL, normalized text hash, or employer+title heuristic.
2. The job resolves to a single canonical ID while preserving source provenance and source URLs.

---

## 7. CLI & API Reference

### CLI Commands
```bash
# Display target companies, tiers, job families, and locations
python -m job_copilot targets

# List all configured job sources
python -m job_copilot sources

# List only enabled sources
python -m job_copilot sources --enabled

# Display operational health and accessibility status of sources
python -m job_copilot sources --health
```

### API Endpoints
- `GET /api/copilot/targets` — Returns target companies, tiers, job families, skills, and locations.
- `GET /api/copilot/sources` — Returns list of configured sources (supports `?enabled_only=true`).
- `GET /api/copilot/sources/health` — Returns source health reports and operational availability.

---

## 8. Adding New Sources Without Code Changes

Add new entries to [`data/config/job_sources.yaml`](file:///Users/Hp/Apply-Agent/data/config/job_sources.yaml):
```yaml
  - id: "custom_board"
    name: "Custom Tech Jobs"
    type: "job_board"
    enabled: true
    priority: "medium"
    discovery_mode: "public"
    requires_login: false
    supports_public_discovery: true
    check_interval_minutes: 360
    urls:
      - "https://customtechjobs.example.com"
    notes: "Custom tech board added by user configuration."
```

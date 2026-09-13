"""Curated featured high-match job definitions for immediate demonstration and tailoring."""

from typing import Any, Dict
from job_copilot.domain.enums import RemoteStatus

CURATED_FEATURED_JOBS: Dict[str, Dict[str, Any]] = {
    "barclays-software-engineer-infrastructure-ce0266": {
        "company": "Barclays",
        "title": "Software Engineer – Infrastructure & Cloud",
        "location": "Pune, India (Hybrid)",
        "remote_status": RemoteStatus.HYBRID,
        "source": "Barclays Careers",
        "canonical_url": "https://search.jobs.barclays/job/-/-/13015/9",
        "description": """Barclays is seeking a Software Engineer – Infrastructure & Cloud to join our global engineering team in Pune. You will be responsible for automating and scaling cloud infrastructure, designing resilient CI/CD pipelines, and ensuring high-availability operations across enterprise banking services.

Key Responsibilities:
- Design, provision, and maintain secure multi-region cloud infrastructure on Google Cloud Platform (GCP) and AWS using Terraform and infrastructure-as-code principles.
- Develop and optimize automated CI/CD deployment pipelines using Jenkins, GitLab CI, and Docker.
- Implement proactive monitoring, telemetry dashboards, and alerting systems using Prometheus, Grafana, and ELK Stack.
- Collaborate with distributed application engineering teams to accelerate deployment frequency and reduce MTTR.
- Enforce strict security, compliance, and governance benchmarks across containerized Kubernetes clusters.

Required Qualifications & Skills:
- 3+ years of software engineering or DevOps experience managing cloud infrastructure.
- Hands-on proficiency with Google Cloud Platform (GCP), Terraform, and Docker containers.
- Strong scripting and programming skills in Python, Bash, or Go.
- Practical experience with CI/CD automation, GitOps, and Linux systems engineering.
- Solid understanding of networking, microservices architecture, and cloud security best practices.""",
        "requirements": ["Google Cloud Platform (GCP)", "Terraform", "CI/CD", "Docker", "Python", "Linux"],
        "preferred_qualifications": ["Kubernetes", "Banking/FinTech infrastructure experience", "Prometheus & Grafana"],
        "technologies": ["Google Cloud Platform (GCP)", "Terraform", "CI/CD", "Docker", "Python", "Kubernetes", "Linux"],
        "years_experience": 3.0,
        "match_score": 94.0,
        "strategy": "cloud_devops",
        "tracking_app_id": "app-barclays-ce0266",
    },
    "hsbc-fintech-senior-software-engineer-backend-0da84f": {
        "company": "HSBC FinTech",
        "title": "Senior Software Engineer — Payments Data Platform",
        "location": "Pune, India (Hybrid)",
        "remote_status": RemoteStatus.HYBRID,
        "source": "HSBC Careers",
        "canonical_url": "https://mycareer.hsbc.com",
        "description": """HSBC FinTech is looking for a Senior Software Engineer to build and scale mission-critical transaction ingestion and real-time streaming pipelines for our global Payments Data Platform.

Key Responsibilities:
- Architect, build, and optimize scalable real-time stream and batch data pipelines using Apache Beam, Google Cloud Dataflow, and BigQuery.
- Design resilient backend microservices in Java and Spring Boot processing millions of daily financial transactions.
- Partner with infrastructure and SRE teams to deploy and operate containerized services with 99.99% availability.
- Implement data governance, automated validation checks, and low-latency API layers for downstream payment analytics.

Required Qualifications & Skills:
- 4+ years of professional backend software development experience in Java or Python.
- Proven experience with distributed data processing systems (Apache Beam, GCP Dataflow, Spark, or Kafka).
- Strong knowledge of relational and NoSQL databases, SQL optimization, and Google Cloud BigQuery.
- Solid understanding of microservices, Spring Boot, REST APIs, and event-driven architecture.""",
        "requirements": ["Java", "Spring Boot", "Apache Beam", "GCP Dataflow", "BigQuery", "Distributed Systems"],
        "preferred_qualifications": ["Payments data domain experience", "Docker & Kubernetes", "Cloud pub/sub"],
        "technologies": ["Java", "Spring Boot", "Apache Beam", "GCP Dataflow", "BigQuery", "GCP", "SQL"],
        "years_experience": 4.0,
        "match_score": 96.0,
        "strategy": "cloud_devops",
        "tracking_app_id": "app-hsbc-fintech-0da84f",
    },
    "mastercard-software-engineer-backend-java-b5bb2c": {
        "company": "Mastercard",
        "title": "Software Engineer II — Backend & Payment Systems",
        "location": "Pune, India / Remote Friendly",
        "remote_status": RemoteStatus.HYBRID,
        "source": "Mastercard Careers",
        "canonical_url": "https://mastercard.wd1.myworkdayjobs.com",
        "description": """Mastercard is looking for a Software Engineer II to join our Payments Processing engineering team. In this role, you will build and evolve high-throughput transaction processing microservices that power secure electronic payments globally.

Key Responsibilities:
- Build, test, and deploy resilient, high-volume RESTful microservices using Java, Spring Boot, and PostgreSQL.
- Implement transactional integrity, fault-tolerant messaging patterns, and high-concurrency event processing.
- Maintain comprehensive unit, integration, and automated regression test coverage.
- Collaborate on API contracts, OpenAPI specifications, and microservices decoupling.

Required Qualifications & Skills:
- 3+ years of experience in backend development with Java and Spring Boot.
- Deep expertise in relational databases (PostgreSQL, Oracle), transaction management, and indexing.
- Experience with microservices architecture, REST APIs, and asynchronous messaging (Kafka or RabbitMQ).
- Strong problem-solving skills, data structures, and computer science fundamentals.""",
        "requirements": ["Java", "Spring Boot", "Microservices", "REST APIs", "PostgreSQL"],
        "preferred_qualifications": ["Kafka", "Payment gateways & ISO 8583 standards", "Docker"],
        "technologies": ["Java", "Spring Boot", "Microservices", "REST APIs", "PostgreSQL", "Kafka"],
        "years_experience": 3.0,
        "match_score": 91.0,
        "strategy": "backend_java",
        "tracking_app_id": "app-mastercard-b5bb2c",
    },
    "stripe-staff-backend-engineer-payments-platform-8eadc9": {
        "company": "Stripe",
        "title": "Backend Software Engineer — Payments Infrastructure",
        "location": "Remote (Global)",
        "remote_status": RemoteStatus.REMOTE,
        "source": "Stripe Careers",
        "canonical_url": "https://stripe.com/jobs",
        "description": """Stripe is building economic infrastructure for the internet. We are looking for a Backend Software Engineer to join our Payments Infrastructure team to scale the global core payment engine.

Key Responsibilities:
- Design, build, and maintain low-latency, fault-tolerant distributed systems powering billions of dollars in daily transactions.
- Develop robust data processing pipelines and backend APIs in Python and Java with strict SLA commitments.
- Enhance observability, automated failover, and zero-downtime deployment strategies across multi-region cloud infrastructure.
- Optimize database queries, caching strategies, and system throughput.

Required Qualifications & Skills:
- 3+ years of software engineering experience in backend systems or distributed infrastructure.
- Strong coding skills in Python, Java, Go, or Ruby.
- Experience with distributed systems, concurrency, and cloud architectures (GCP, AWS).
- Proven ability to write clean, maintainable, and thoroughly tested production code.""",
        "requirements": ["Distributed Systems", "GCP or AWS", "High Throughput", "Reliability", "Python or Java"],
        "preferred_qualifications": ["Fintech experience", "Terraform", "Container orchestration"],
        "technologies": ["Distributed Systems", "GCP", "High Throughput", "Reliability", "Python", "Java", "PostgreSQL"],
        "years_experience": 3.0,
        "match_score": 89.0,
        "strategy": "cloud_devops",
        "tracking_app_id": "app-stripe-8eadc9",
    },
}

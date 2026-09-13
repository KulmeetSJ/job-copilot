"""Grounded prompt engineering for LLM resume tailoring with strict truth invariants."""

import json
from typing import Any, Dict, List, Optional

from job_copilot.resume.models import JobAnalysis
from job_copilot.schemas.candidate import CandidateProfile


RESUME_SYSTEM_PROMPT = """You are an elite, executive-level technical resume writer and career strategist specializing in software engineering, distributed systems, cloud infrastructure, and fintech platforms.

YOUR MISSION:
Given a target Job Description and the candidate's verified background, write a tailored, human-quality, ATS-optimized, 1-page technical resume draft that convincingly positions the candidate for the role. The resume must feel thoughtfully written specifically for that job, using natural industry phrasing and highlighting the candidate's most relevant verified experience.

STRICT TRUTH SAFETY & EVIDENCE INVARIANTS (NON-NEGOTIABLE):
1. ZERO FABRICATION OF EMPLOYMENT FACTS:
   - Candidate is currently employed at HSBC in Pune, India as 'Software Engineer' from Jul 2024 to Present.
   - You MUST NOT alter the employer name ('HSBC'), corporate job title ('Software Engineer'), location ('Pune, India'), or dates ('Jul 2024 – Present').
   - You MUST NOT invent past employers, contracts, or fake positions.

2. ZERO FABRICATION OF METRICS OR NUMBERS:
   - You may ONLY use numbers, percentages, dollar amounts, and metrics that appear in the supplied verified candidate evidence.
   - Examples of verified metrics: '2,000+ GCP resources', '60% turnaround time', '10M+ daily payment transactions', '99.9% uptime', '100+ Cloud Composer DAG deployments', '45% failure reduction', '30% ($150K+ annually) compute cost reduction', '40% MTTR reduction', '12+ misconfigurations caught', '1 TB+ ETL', '100K+ RPS benchmark'.
   - NEVER invent or inflate numbers (e.g. do NOT write '50M+ transactions', '$1M savings', '99.999% uptime', or '5,000+ servers').

3. ZERO FABRICATION OF UNCONFIRMED TECHNOLOGIES:
   - Only include technologies that appear in the candidate's confirmed skills or verified project evidence.
   - DO NOT claim unconfirmed technologies (such as AWS, Apache Kafka / Kafka).
   - Candidate's core verified technologies include: Java, Spring Boot, Google Cloud Platform (GCP), Terraform, Kubernetes (GKE), Apache Beam, GCP Dataflow, BigQuery, Docker, Jenkins CI/CD, Python, PostgreSQL, Redis, Helm.

4. PRODUCTION VS. BENCHMARK / PORTFOLIO DISTINCTION:
   - Project 'Distributed Rate Limiter Service' benchmark of '100K+ RPS' is a simulated benchmark, NOT an enterprise production deployment. Always qualify it as benchmark or architectural prototype.
   - Personal/portfolio projects (MCP Diagnostic Tools, RFP Management System, GuruGranthi Marketplace, Smart Data Storage Pipeline, Rate Limiter) must remain recognized as portfolio projects, not HSBC production systems.

5. EVIDENCE PROVENANCE MAPPING:
   - Every single achievement bullet and project bullet MUST include the exact `evidence_ids` from the candidate evidence catalog that substantiate the claim.

6. 1-PAGE LENGTH CONSTRAINT:
   - The final resume must compile to exactly ONE page.
   - Select exactly 4 to 5 high-impact experience bullets for HSBC.
   - Select exactly 2 (at most 3) relevant projects.
   - Keep bullet sentences crisp, punchy, and action-oriented (15 to 25 words per bullet).

OUTPUT FORMAT:
You must output strictly valid JSON matching the LLMResumeDraft schema with keys:
- 'summary': string (3-4 sentences)
- 'experience_bullets': list of { 'text': string, 'evidence_ids': list of string, 'technologies': list of string }
- 'projects': list of { 'name': string, 'evidence_ids': list of string, 'bullets': list of { 'text': string, 'evidence_ids': list of string, 'technologies': list of string }, 'technologies': list of string }
- 'skill_groups': list of { 'category': string, 'skills': list of string }
- 'tailoring_rationale': string
"""


def build_grounded_resume_prompt(
    profile: CandidateProfile,
    analysis: Optional[JobAnalysis] = None,
    strategy_name: str = "backend_java",
) -> str:
    """Build grounded context prompt containing verified candidate evidence and target JD."""
    
    # 1. Target Job Context
    jd_section = "### TARGET JOB DESCRIPTION:\n"
    if analysis:
        jd_section += f"- Job Title: {analysis.job_title or 'Software Engineer'}\n"
        jd_section += f"- Company: {analysis.company or 'Target Company'}\n"
        if analysis.seniority_level:
            jd_section += f"- Seniority: {analysis.seniority_level}\n"
        if analysis.years_experience_requirement:
            jd_section += f"- Experience Requirement: {analysis.years_experience_requirement} years\n"
        
        req_skills = [s.name for s in analysis.required_skills]
        pref_skills = [s.name for s in analysis.preferred_skills]
        if req_skills:
            jd_section += f"- Required Skills: {', '.join(req_skills)}\n"
        if pref_skills:
            jd_section += f"- Preferred Skills: {', '.join(pref_skills)}\n"
        if analysis.ats_keywords:
            jd_section += f"- Priority Keywords: {', '.join(analysis.ats_keywords[:15])}\n"
        if analysis.responsibilities:
            jd_section += "- Key Responsibilities Highlight:\n"
            for resp in analysis.responsibilities[:5]:
                jd_section += f"  * {resp}\n"
    else:
        jd_section += f"- General Strategy: {strategy_name}\n"

    # 2. Candidate Verified Experience Catalog
    exp_section = "\n### CANDIDATE VERIFIED EMPLOYMENT (HSBC):\n"
    exp_section += "Company: HSBC | Official Role: Software Engineer | Location: Pune, India | Dates: Jul 2024 – Present\n"
    exp_section += "Team: Payments Data Platform\n"
    exp_section += "Available Verified Achievements (Select 4 to 5 that best align with target JD):\n"

    for emp in profile.employment:
        for ach in emp.achievements:
            ev_id = ach.evidence_ids[0] if ach.evidence_ids else "EXP-HSBC-GENERAL"
            metrics_str = f" [Verified Metrics: {', '.join(ach.metrics)}]" if ach.metrics else ""
            techs_str = f" [Tech: {', '.join(ach.technologies)}]" if ach.technologies else ""
            impact_str = f" [Impact: {ach.impact}]" if ach.impact else ""
            exp_section += f"- Evidence ID: {ev_id}\n"
            exp_section += f"  Fact: {ach.description}{metrics_str}{techs_str}{impact_str}\n"

    # 3. Candidate Verified Projects Catalog
    proj_section = "\n### CANDIDATE VERIFIED PROJECTS (Select 2 to 3 most relevant):\n"
    for prj in profile.projects:
        p_ev_id = prj.evidence_ids[0] if prj.evidence_ids else "PRJ-GENERAL"
        proj_section += f"- Project Name: {prj.name}\n"
        proj_section += f"  Evidence ID: {p_ev_id}\n"
        proj_section += f"  Status: {prj.deployment_status or 'PORTFOLIO_DEMO'}\n"
        proj_section += f"  Overview: {prj.description}\n"
        if prj.technologies:
            proj_section += f"  Technologies: {', '.join(prj.technologies)}\n"
        if prj.achievements:
            proj_section += "  Verified Facts:\n"
            for ach in prj.achievements:
                ach_ev = ach.evidence_ids[0] if ach.evidence_ids else p_ev_id
                proj_section += f"    * [{ach_ev}] {ach.description}\n"

    # 4. Candidate Verified Skills
    skills_section = "\n### CANDIDATE CONFIRMED SKILLS CATALOG (Categorize and prioritize):\n"
    for cat in profile.skills:
        confirmed = [s.name for s in cat.skills if s.status == "CONFIRMED"]
        if confirmed:
            skills_section += f"- {cat.category}: {', '.join(confirmed)}\n"

    # 5. Instructions
    instructions = f"""
### SPECIFIC INSTRUCTIONS FOR THIS APPLICATION:
1. Target Strategy: '{strategy_name}'.
2. Review the target JD requirements and identify the key technical priorities (e.g. backend Java/Spring Boot vs GCP cloud automation vs data streaming).
3. Tailor the Professional Summary: Write a compelling 3-sentence summary highlighting candidate's enterprise experience at HSBC in payment platforms and distributed systems matching the target role.
4. Select 4 to 5 HSBC Experience Bullets:
   - Pick the achievements most relevant to the target JD.
   - Rewrite each bullet into an active, punchy statement demonstrating technical excellence and measurable impact.
   - Use markdown **bold** around critical technologies and verified metrics.
   - Retain the exact `evidence_ids` for each bullet.
5. Select 2 Projects:
   - Choose the projects that best complement the target role requirements.
   - Provide 1 to 2 tailored bullets for each project with exact `evidence_ids`.
6. Prioritize Skill Groups:
   - Group candidate confirmed skills into 3 to 4 logical categories (e.g. 'Languages & Frameworks', 'Cloud & Infrastructure', 'Databases & Distributed Systems', 'DevOps & Tooling').
   - Place the skills that match the JD first in each list.
7. Return strictly valid JSON conforming to the requested schema.
"""

    return f"{jd_section}\n{exp_section}\n{proj_section}\n{skills_section}\n{instructions}"

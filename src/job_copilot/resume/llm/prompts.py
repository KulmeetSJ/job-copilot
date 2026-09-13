from pathlib import Path
from typing import Any

import yaml

from job_copilot.resume.models import JobAnalysis
from job_copilot.schemas.candidate import CandidateProfile


def build_resume_system_prompt(
    profile: CandidateProfile | None = None,
    evidence_facts: dict[str, Any] | None = None,
) -> str:
    """Dynamically generate system prompt containing verified candidate invariants, metrics, technologies, and projects."""
    if profile is None:
        try:
            prof_path = Path("data/candidate/master_profile.yaml")
            if prof_path.exists():
                with open(prof_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                if data:
                    profile = CandidateProfile.model_validate(data)
        except (OSError, yaml.YAMLError, ValueError):
            profile = None

    if evidence_facts is None:
        try:
            ev_path = Path("data/candidate/evidence.yaml")
            if ev_path.exists():
                with open(ev_path, "r", encoding="utf-8") as f:
                    ev_data = yaml.safe_load(f)
                if ev_data and "facts" in ev_data:
                    evidence_facts = {fact["id"]: fact for fact in ev_data["facts"] if "id" in fact}
        except (OSError, yaml.YAMLError, ValueError):
            evidence_facts = {}

    company = "Candidate Employer"
    role = "Software Engineer"
    location = ""
    dates = "Present"
    confirmed_techs_str = "candidate confirmed technologies"
    verified_metrics_str = "supplied verified metrics"
    benchmarks_str = "simulated benchmark projects"
    portfolios_str = "portfolio/demo projects"

    if profile:
        if profile.employment:
            emp = profile.employment[0]
            company = emp.company or "Candidate Employer"
            role = emp.role or emp.canonical_role or "Software Engineer"
            location = emp.location or ""
            dates = f"{emp.start_date or ''} – {emp.end_date or 'Present'}"

        techs = []
        for cat in profile.skills:
            techs.extend([s.name for s in cat.skills if s.status == "CONFIRMED"])
        if techs:
            confirmed_techs_str = ", ".join(techs)

        metrics = set()
        for emp in profile.employment:
            for ach in emp.achievements:
                metrics.update(ach.metrics)
        for prj in profile.projects:
            metrics.update(prj.metrics)
            for ach in prj.achievements:
                metrics.update(ach.metrics)
        if evidence_facts:
            for fid, f in evidence_facts.items():
                if fid.startswith("MET-") and f.get("claim"):
                    metrics.add(f.get("claim"))
        if metrics:
            verified_metrics_str = ", ".join(f"'{m}'" for m in sorted(metrics))

        bench_list = [f"'{p.name}'" for p in profile.projects if p.claim_type == "BENCHMARK"]
        if bench_list:
            benchmarks_str = ", ".join(bench_list)
        port_list = [f"'{p.name}'" for p in profile.projects]
        if port_list:
            portfolios_str = ", ".join(port_list)

    loc_clause = f" in {location}" if location else ""

    return f"""You are an elite, executive-level technical resume writer and career strategist specializing in software engineering, distributed systems, cloud infrastructure, and fintech platforms.

YOUR MISSION:
Given a target Job Description and the candidate's verified background, write a tailored, human-quality, ATS-optimized, 1-page technical resume draft that convincingly positions the candidate for the role. The resume must feel thoughtfully written specifically for that job, using natural industry phrasing and highlighting the candidate's most relevant verified experience.

STRICT TRUTH SAFETY & EVIDENCE INVARIANTS (NON-NEGOTIABLE):
1. ZERO FABRICATION OF EMPLOYMENT FACTS:
   - Candidate is currently employed at {company}{loc_clause} as '{role}' from {dates}.
   - You MUST NOT alter the employer name ('{company}'), corporate job title ('{role}'), or dates ('{dates}').
   - You MUST NOT invent past employers, contracts, or fake positions.
   - Experience bullets must cite ONLY employment evidence IDs from {company}.

2. ZERO FABRICATION OF METRICS OR NUMBERS:
   - You may ONLY use numbers, percentages, dollar amounts, and metrics that appear in the supplied verified candidate evidence.
   - Allowed verified metrics include: {verified_metrics_str}.
   - NEVER invent or inflate numbers (e.g. do NOT write '50M+ transactions', '$1M savings', '99.999% uptime', or '5,000+ servers').
   - Every metric in generated text must be traceable to the cited evidence IDs.

3. ZERO FABRICATION OF UNCONFIRMED TECHNOLOGIES:
   - Only include technologies that appear in the candidate's confirmed skills or verified project evidence.
   - DO NOT claim unconfirmed technologies (such as AWS, Apache Kafka / Kafka).
   - Candidate's confirmed technologies include: {confirmed_techs_str}.

4. PRODUCTION VS. BENCHMARK / PORTFOLIO DISTINCTION:
   - Benchmark projects ({benchmarks_str}) are simulated benchmarks, NOT enterprise production deployments. Always qualify them as benchmarks or architectural prototypes.
   - Personal/portfolio projects ({portfolios_str}) must remain recognized as portfolio/demo projects, not {company} production systems.
   - Project bullets must cite ONLY evidence belonging to that specific canonical project.

5. EVIDENCE PROVENANCE MAPPING:
   - Every single achievement bullet and project bullet MUST include the exact `evidence_ids` from the candidate evidence catalog that substantiate the claim.

6. 1-PAGE LENGTH CONSTRAINT:
   - The final resume must compile to exactly ONE page.
   - Select exactly 4 to 5 high-impact experience bullets for {company}.
   - Select exactly 2 (at most 3) relevant projects.
   - Keep bullet sentences crisp, punchy, and action-oriented (15 to 25 words per bullet).

OUTPUT FORMAT:
You must output strictly valid JSON matching the LLMResumeDraft schema with keys:
- 'summary': string (3-4 sentences)
- 'experience_bullets': list of {{ 'text': string, 'evidence_ids': list of string, 'technologies': list of string }}
- 'projects': list of {{ 'name': string, 'evidence_ids': list of string, 'bullets': list of {{ 'text': string, 'evidence_ids': list of string, 'technologies': list of string }}, 'technologies': list of string }}
- 'skill_groups': list of {{ 'category': string, 'skills': list of string }}
- 'tailoring_rationale': string
"""


RESUME_SYSTEM_PROMPT = build_resume_system_prompt()


def build_grounded_resume_prompt(
    profile: CandidateProfile,
    analysis: JobAnalysis | None = None,
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
    canonical_emp = profile.employment[0] if profile.employment else None
    emp_company = canonical_emp.company if canonical_emp else "Candidate Employer"
    emp_role = (canonical_emp.role or canonical_emp.canonical_role) if canonical_emp else "Software Engineer"
    emp_loc = canonical_emp.location if canonical_emp else ""
    emp_dates = f"{canonical_emp.start_date or ''} – {canonical_emp.end_date or 'Present'}" if canonical_emp else ""
    emp_team = canonical_emp.team or ""

    exp_section = f"\n### CANDIDATE VERIFIED EMPLOYMENT ({emp_company}):\n"
    exp_section += f"Company: {emp_company} | Official Role: {emp_role} | Location: {emp_loc} | Dates: {emp_dates}\n"
    if emp_team:
        exp_section += f"Team: {emp_team}\n"
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

from pathlib import Path
from typing import Any, List

import yaml

from job_copilot.resume.analyzer import derive_dominant_themes
from job_copilot.resume.models import JobAnalysis
from job_copilot.schemas.candidate import CandidateProfile


def rank_ats_keywords(analysis: JobAnalysis, limit: int = 15) -> list[str]:
    """
    Deterministically rank ATS keywords based on requirement criticality,
    job title relevance, and technology categories rather than naive position/alphabetical slicing.
    """
    if not analysis.ats_keywords:
        return []

    title_lower = (analysis.job_title or "").lower()
    req_names = {s.normalized_name.lower() for s in analysis.required_skills}
    pref_names = {s.normalized_name.lower() for s in analysis.preferred_skills}
    core_techs = {
        t.lower()
        for t in (
            analysis.programming_languages
            + analysis.frameworks
            + analysis.cloud_technologies
            + analysis.databases
            + analysis.infrastructure_technologies
        )
    }

    resp_text = " ".join(analysis.responsibilities).lower()

    def keyword_score(kw: str) -> tuple[float, str]:
        kw_lower = kw.lower()
        score = 0.0

        # Title match is highest priority
        if kw_lower in title_lower:
            score += 10.0

        # Required skill
        if kw_lower in req_names:
            score += 6.0

        # Preferred skill
        elif kw_lower in pref_names:
            score += 3.0

        # Core technology category
        if kw_lower in core_techs:
            score += 2.0

        # Mentions in responsibilities
        if kw_lower in resp_text:
            score += 1.5

        # Lexicographical tie-breaker for strict determinism
        return (-score, kw_lower)

    ranked = sorted(set(analysis.ats_keywords), key=keyword_score)
    return ranked[:limit]


def rank_responsibilities(analysis: JobAnalysis, limit: int = 5) -> list[str]:
    """
    Deterministically rank JD responsibilities prioritizing technical depth,
    alignment with required skills, action impact, and scale signals.
    Prevents critical technical requirements from being dropped merely because they appear late.
    """
    if not analysis.responsibilities:
        return []

    required_lower = [s.normalized_name.lower() for s in analysis.required_skills]
    core_tech_lower = [
        t.lower()
        for t in (
            analysis.programming_languages
            + analysis.frameworks
            + analysis.cloud_technologies
            + analysis.databases
            + analysis.infrastructure_technologies
        )
    ]
    technical_action_verbs = {
        "architect", "design", "build", "develop", "implement", "engineer",
        "scale", "optimize", "automate", "deploy", "pipeline", "infrastructure",
        "provision", "maintain", "manage", "lead", "spearhead",
    }
    scale_signals = {"%", "throughput", "latency", "scale", "uptime", "sla", "real-time", "distributed", "high-throughput"}

    def resp_score(indexed_resp: tuple[int, str]) -> tuple[float, int]:
        idx, text = indexed_resp
        text_lower = text.lower()
        score = 0.0

        # 1. Matches required skills
        for req in required_lower:
            if req in text_lower:
                score += 3.0

        # 2. Matches core tech
        for tech in core_tech_lower:
            if tech in text_lower:
                score += 1.5

        # 3. Technical action verbs
        for verb in technical_action_verbs:
            if verb in text_lower:
                score += 1.0

        # 4. Scale / performance / SLA signals
        for sig in scale_signals:
            if sig in text_lower:
                score += 1.5

        # Stable tie-breaker: original list position
        return (-score, idx)

    indexed = list(enumerate(analysis.responsibilities))
    ranked_indexed = sorted(indexed, key=resp_score)
    return [text for _, text in ranked_indexed[:limit]]


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
            current_emp = next((e for e in profile.employment if e.current), profile.employment[0])
            company = current_emp.company or "Candidate Employer"
            role = current_emp.role or current_emp.canonical_role or "Software Engineer"
            location = current_emp.location or ""
            dates = f"{current_emp.start_date or ''} – {current_emp.end_date or 'Present'}"

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
- 'dominant_themes': list of string (top 2-3 dominant JD themes identified in prompt, or empty list [] if none identified; do NOT invent ungrounded themes)
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
    """Build grounded context prompt containing verified candidate evidence, target JD dominant themes, and ranked requirements."""
    
    # 1. Target Job Context & Dominant Themes
    jd_section = "### TARGET JOB DESCRIPTION:\n"
    dominant_themes: list[str] = []
    if analysis:
        dominant_themes = (
            analysis.dominant_themes
            if getattr(analysis, "dominant_themes", None)
            else derive_dominant_themes(analysis)
        )
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

        # Importance-ranked keywords and responsibilities
        ranked_keywords = rank_ats_keywords(analysis, limit=15)
        if ranked_keywords:
            jd_section += f"- Priority Keywords (Importance Ranked): {', '.join(ranked_keywords)}\n"

        ranked_resps = rank_responsibilities(analysis, limit=5)
        if ranked_resps:
            jd_section += "- Key Responsibilities Highlight (Importance Ranked):\n"
            for resp in ranked_resps:
                jd_section += f"  * {resp}\n"
    else:
        jd_section += f"- General Strategy: {strategy_name}\n"

    # Dominant themes section
    if dominant_themes:
        themes_list_str = "\n".join(f"{i+1}. {t}" for i, t in enumerate(dominant_themes))
        themes_section = f"""
### TARGET JOB DOMINANT THEMES:
The target role centers around the following dominant technical themes (derived directly from the Job Description):
{themes_list_str}

DOMINANT THEME TAILORING MANDATE:
You must explicitly use these dominant themes to steer:
1. Experience bullet selection & ordering: Choose achievements that directly substantiate these top themes and order them with the primary theme first.
2. Skills emphasis: Feature technologies relevant to these dominant themes prominently in the top skill groups.
3. Summary positioning: Anchor candidate summary around these core technical themes without adding unconfirmed candidate claims.
"""
    else:
        themes_section = """
### TARGET JOB REQUIREMENTS FOCUS:
No single dominant theme from the theme catalog was identified for this role.
You must tailor the resume strictly using the ranked requirements, priority keywords, and key responsibilities provided in the Target Job Description above.
Do NOT invent, fabricate, or assume an ungrounded dominant technical theme.
Tailor the experience bullet selection, skills emphasis, and summary strictly based on the candidate's verified evidence matching the ranked requirements above.
"""

    # 2. Candidate Verified Experience Catalog (Multi-employment safe)
    exp_section = "\n### CANDIDATE VERIFIED EMPLOYMENT:\n"
    if profile and profile.employment:
        for emp_idx, emp in enumerate(profile.employment, start=1):
            emp_comp = emp.company or "Candidate Employer"
            emp_role = emp.role or emp.canonical_role or "Software Engineer"
            emp_loc = emp.location or ""
            emp_dates = f"{emp.start_date or ''} – {emp.end_date or 'Present'}"
            emp_team = emp.team or ""
            exp_section += f"\nEmployer #{emp_idx}: {emp_comp} | Official Role: {emp_role} | Location: {emp_loc} | Dates: {emp_dates}\n"
            if emp_team:
                exp_section += f"Team: {emp_team}\n"
            exp_section += f"Available Verified Achievements for {emp_comp} (Select 4 to 5 that best align with JD requirements):\n"
            for ach in emp.achievements:
                ev_id = ach.evidence_ids[0] if ach.evidence_ids else "EXP-GENERAL"
                metrics_str = f" [Verified Metrics: {', '.join(ach.metrics)}]" if ach.metrics else ""
                techs_str = f" [Tech: {', '.join(ach.technologies)}]" if ach.technologies else ""
                impact_str = f" [Impact: {ach.impact}]" if ach.impact else ""
                exp_section += f"- Evidence ID: {ev_id}\n"
                exp_section += f"  Fact: {ach.description}{metrics_str}{techs_str}{impact_str}\n"
    else:
        exp_section += "No verified employment records found.\n"

    # 3. Candidate Verified Projects Catalog
    proj_section = "\n### CANDIDATE VERIFIED PROJECTS (Select 2 to 3 most relevant to JD requirements):\n"
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
    if dominant_themes:
        theme_directive = f": {', '.join(dominant_themes)}"
        themes_instruction = f"2. Dominant JD Themes: Tailor the resume to prominently address the identified dominant themes{theme_directive}."
        summary_instruction = "3. Tailor the Professional Summary: Write a compelling 3-sentence summary positioning the candidate around the dominant themes and verified enterprise experience."
        bullets_instruction = """4. Select 4 to 5 Experience Bullets:
   - Prioritize achievements matching the primary dominant JD themes.
   - Order the most theme-relevant achievements first.
   - Rewrite each bullet into an active, punchy statement demonstrating technical excellence and measurable impact.
   - Use markdown **bold** around critical technologies and verified metrics.
   - Retain the exact `evidence_ids` for each bullet."""
        proj_instruction = """5. Select 2 Projects:
   - Choose the projects that best complement the target role's dominant themes.
   - Provide 1 to 2 tailored bullets for each project with exact `evidence_ids`."""
        skills_instruction = """6. Prioritize Skill Groups:
   - Group candidate confirmed skills into 3 to 4 logical categories (e.g. 'Languages & Frameworks', 'Cloud & Infrastructure', 'Databases & Distributed Systems', 'DevOps & Tooling').
   - Place the skills that match the target JD themes first in each list."""
    else:
        themes_instruction = "2. Focus on Ranked JD Requirements: No dominant theme was identified. Tailor the resume strictly using the ranked requirements, priority keywords, and key responsibilities provided above. Do NOT invent a dominant theme."
        summary_instruction = "3. Tailor the Professional Summary: Write a compelling 3-sentence summary positioning the candidate's verified enterprise experience against the target role's ranked requirements and responsibilities. Do NOT invent an ungrounded dominant theme."
        bullets_instruction = """4. Select 4 to 5 Experience Bullets:
   - Prioritize achievements directly matching the target role's required skills and key responsibilities.
   - Order the most requirement-relevant achievements first.
   - Rewrite each bullet into an active, punchy statement demonstrating technical excellence and measurable impact.
   - Use markdown **bold** around critical technologies and verified metrics.
   - Retain the exact `evidence_ids` for each bullet."""
        proj_instruction = """5. Select 2 Projects:
   - Choose the projects that best demonstrate competencies relevant to the target role's ranked requirements.
   - Provide 1 to 2 tailored bullets for each project with exact `evidence_ids`."""
        skills_instruction = """6. Prioritize Skill Groups:
   - Group candidate confirmed skills into 3 to 4 logical categories (e.g. 'Languages & Frameworks', 'Cloud & Infrastructure', 'Databases & Distributed Systems', 'DevOps & Tooling').
   - Place the skills that match the target role's required skills and priority keywords first in each list."""

    instructions = f"""
### SPECIFIC INSTRUCTIONS FOR THIS APPLICATION:
1. Target Strategy: '{strategy_name}'.
{themes_instruction}
{summary_instruction}
{bullets_instruction}
{proj_instruction}
{skills_instruction}
7. Return strictly valid JSON conforming to the requested schema.
"""

    return f"{jd_section}{themes_section}{exp_section}\n{proj_section}\n{skills_section}\n{instructions}"

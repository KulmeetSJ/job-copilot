"""Command-line interface and system diagnostic entrypoint for Job Copilot."""

import argparse
from pathlib import Path
import sys
from job_copilot import __version__
from job_copilot.config import settings
from job_copilot.db.database import init_db
from job_copilot.repositories.candidate_repository import CandidateRepository
from job_copilot.services.job_intelligence_service import JobIntelligenceService
from job_copilot.services.resume_service import ResumeService
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def check_system_status() -> bool:
    """Check and display the initialization status of Job Copilot."""
    print("=" * 60)
    print(f"  Job Copilot - System Status (v{__version__})")
    print("=" * 60)
    print(f"Environment       : {settings.app_env}")
    print(f"Debug Mode        : {settings.debug}")
    print(f"Database URL      : {settings.database_url}")
    print(f"Master Profile    : {settings.candidate_profile_path}")
    print("-" * 60)

    # 1. Check & Init DB
    try:
        init_db()
        print("[✓] Database        : Initialized & schema ready")
    except Exception as e:
        print(f"[✗] Database        : Initialization error ({e})")
        return False

    # 2. Check Master Candidate Profile
    repo = CandidateRepository()
    if repo.exists():
        try:
            profile = repo.load()
            print(f"[✓] Candidate Profile: Found & Validated ({profile.personal_info.full_name})")
            print(f"    - Education records   : {len(profile.education)}")
            print(f"    - Experience records  : {len(profile.experience)}")
            print(f"    - Projects            : {len(profile.projects)}")
            print(f"    - Skill categories    : {len(profile.skills)}")
        except Exception as e:
            print(f"[!] Candidate Profile: File exists but validation failed: {e}")
    else:
        print(f"[!] Candidate Profile: Missing at {settings.candidate_profile_path}")

    # 3. Check Resume Strategies
    resume_service = ResumeService()
    strategies = resume_service.list_strategies()
    print(f"[✓] Resume Strategies : {len(strategies)} loaded ({', '.join(strategies)})")

    print("=" * 60)
    print("Available Launch Modes:")
    print("  Job Intelligence CLI: python -m job_copilot analyze-job <file>")
    print("                        python -m job_copilot match-job <file>")
    print("                        python -m job_copilot recommend-job <file>")
    print("                        python -m job_copilot tailor-job <file>")
    print("  Resume Engine CLI   : python -m job_copilot resume --help")
    print("  FastAPI Server      : python -m job_copilot --start-api")
    print("  MCP Server          : python -m job_copilot --start-mcp")
    print("=" * 60)
    return True


def handle_resume_cli(args: argparse.Namespace):
    """Handle CLI resume commands (Phase 3)."""
    service = ResumeService()

    if args.resume_command == "strategies":
        strategies = service.list_strategies()
        print("\nAvailable Resume Strategies:")
        print("-" * 40)
        for s in strategies:
            strat_config = service.get_strategy(s)
            print(f"• {s:20} -> {strat_config.display_title}")
        print()

    elif args.resume_command == "generate":
        strategy_name = args.strategy
        print(f"\n[+] Generating resume for strategy '{strategy_name}'...")
        try:
            res = service.generate_tailored_resume(strategy_name)
            print(f"[✓] Resume generated successfully!")
            print(f"    - LaTeX source : {res.tex_path}")
            print(f"    - PDF document : {res.pdf_path}")
            print(f"    - Page count   : {res.validation.page_count}")
            print(f"    - Valid        : {res.validation.is_valid}")
            if res.validation.truth_violations:
                print(f"    - Truth violations : {res.validation.truth_violations}")
        except Exception as e:
            print(f"[✗] Failed to generate resume: {e}")
            sys.exit(1)

    elif args.resume_command == "analyze":
        jd_file = Path(args.job_description)
        if not jd_file.exists():
            print(f"[✗] File not found: {jd_file}")
            sys.exit(1)
        text = jd_file.read_text(encoding="utf-8")
        analysis = service.analyze_job(text)
        print("\n" + "=" * 50)
        print("  Job Description Analysis")
        print("=" * 50)
        print(f"Title            : {analysis.job_title}")
        print(f"Company          : {analysis.company}")
        print(f"Location         : {analysis.location}")
        print(f"Seniority        : {analysis.seniority_level}")
        print(f"Experience (Yrs) : {analysis.years_experience_requirement}")
        print(f"Required Skills  : {', '.join([s.normalized_name for s in analysis.required_skills])}")
        print(f"Preferred Skills : {', '.join([s.normalized_name for s in analysis.preferred_skills])}")
        print(f"ATS Keywords     : {', '.join(analysis.ats_keywords)}")
        print("=" * 50 + "\n")

    elif args.resume_command == "tailor":
        jd_file = Path(args.job)
        if not jd_file.exists():
            print(f"[✗] File not found: {jd_file}")
            sys.exit(1)
        text = jd_file.read_text(encoding="utf-8")
        analysis = service.analyze_job(text)
        match_res = service.match_job(analysis)
        strategy = args.strategy or match_res.recommended_strategy

        print(f"\n[+] Job Title: {analysis.job_title} at {analysis.company or 'Unknown'}")
        print(f"[+] Match fit score: {match_res.overall_score}%")
        print(f"[+] Tailoring resume using strategy: '{strategy}'...")

        res = service.generate_tailored_resume(strategy, job_description_text=text)
        print(f"[✓] Tailored resume produced:")
        print(f"    - LaTeX source : {res.tex_path}")
        print(f"    - PDF document : {res.pdf_path}")
        print(f"    - Matched reqs : {match_res.matched_required_count}/{match_res.total_required_count}")
        print(f"    - Keyword cov  : {match_res.keyword_coverage_pct}%")
        print()


def handle_job_intelligence_cli(subcommand: str, args: argparse.Namespace):
    """Handle Job Intelligence & Matching CLI commands (Phase 4)."""
    intel_service = JobIntelligenceService()
    
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"[✗] File not found: {file_path}")
        sys.exit(1)
        
    raw_text = file_path.read_text(encoding="utf-8")

    if subcommand == "analyze-job":
        analyzed = intel_service.analyze_job(raw_text)
        print("\n" + "=" * 60)
        print("  ANALYZED JOB SPECIFICATION")
        print("=" * 60)
        print(f"Job ID           : {analyzed.job_id}")
        print(f"Title            : {analyzed.title}")
        print(f"Company          : {analyzed.company}")
        print(f"Location         : {analyzed.location or 'Unspecified'} ({analyzed.remote_policy.value})")
        print(f"Seniority        : {analyzed.seniority.value}")
        print(f"Experience Req   : {analyzed.years_experience_required or 'Unspecified'} yrs")
        print(f"Work Auth Signal : {analyzed.work_authorization.value}")
        print("-" * 60)
        print(f"Technical Requirements ({len(analyzed.technical_requirements)}):")
        for r in analyzed.technical_requirements:
            prefix = "[Must-Have]" if r.is_must_have else "[Preferred]"
            print(f"  • {prefix:12} {r.normalized_name:25} ({r.category}) - Importance: {r.importance.value}")
        if analyzed.responsibilities:
            print(f"\nResponsibilities:")
            for resp in analyzed.responsibilities:
                print(f"  • {resp}")
        print(f"\nSaved artifacts under: data/jobs/analyzed/{analyzed.job_id}.json\n")

    elif subcommand == "match-job":
        assessment = intel_service.evaluate_job(raw_text)
        print(assessment.human_report)

    elif subcommand == "recommend-job":
        assessment = intel_service.evaluate_job(raw_text)
        print("\n" + "=" * 60)
        print(f"  JOB RECOMMENDATION SUMMARY")
        print("=" * 60)
        print(f"Role & Company      : {assessment.job.title} at {assessment.job.company}")
        print(f"Overall Fit Score   : {assessment.score_breakdown.overall_score} / 100.0")
        print(f"Recommendation Tier : {assessment.recommendation.value}")
        print(f"Recommended Strategy: {assessment.recommended_strategy}")
        print(f"Reasoning           : {assessment.strategy_reasoning}")
        print("-" * 60)
        print(f"Key Strengths       : {len(assessment.strengths)}")
        for s in assessment.strengths[:3]:
            print(f"  ✓ {s}")
        print(f"Key Gaps / Risks    : {len(assessment.gaps) + len(assessment.risks)}")
        for g in assessment.gaps[:2] + assessment.risks[:2]:
            print(f"  ! {g}")
        print("=" * 60 + "\n")

    elif subcommand == "tailor-job":
        assessment = intel_service.evaluate_job(raw_text)
        strategy = args.strategy or assessment.recommended_strategy
        print(f"\n[+] Job Title: {assessment.job.title} at {assessment.job.company}")
        print(f"[+] Overall Fit: {assessment.score_breakdown.overall_score}% -> Recommendation: {assessment.recommendation.value}")
        print(f"[+] Tailoring resume using strategy: '{strategy}'...")
        
        gen_res = intel_service.resume_service.generate_tailored_resume(strategy, job_description_text=raw_text)
        print(f"[✓] Tailored resume produced:")
        print(f"    - LaTeX source : {gen_res.tex_path}")
        print(f"    - PDF document : {gen_res.pdf_path}")
        print(f"    - Valid        : {gen_res.validation.is_valid}")
        print()


def handle_discovery_cli(subcommand: str, args: argparse.Namespace):
    """Handle Job Discovery & Ingestion CLI commands (Phase 5)."""
    from job_copilot.ingestion.models import DiscoveryQuery
    from job_copilot.services.discovery_service import DiscoveryService

    discovery_service = DiscoveryService()

    if subcommand == "ingest-job":
        file_path = args.file
        print(f"[+] Ingesting job from file: {file_path}")
        job = discovery_service.ingest_file(
            file_path=file_path,
            company=args.company,
            title=args.title,
            location=args.location,
        )
        if not job:
            print(f"[✗] Failed to ingest job from: {file_path}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("  JOB INGESTION SUCCESSFUL")
        print("=" * 60)
        print(f"Job ID           : {job.job_id}")
        print(f"Title            : {job.title}")
        print(f"Company          : {job.company}")
        print(f"Location         : {job.location or 'Unspecified'} ({job.remote_policy.value})")
        print(f"Lifecycle Status : {job.lifecycle_status.value}")
        if job.duplicate_of:
            print(f"Duplicate of     : {job.duplicate_of} (Reason: {job.duplicate_reason})")
        print(f"Content Hash     : {job.content_hash[:12]}...")
        print("-" * 60)
        print(f"Normalized stored: data/jobs/normalized/{job.job_id}.json\n")

    elif subcommand == "ingest-url":
        url = args.url
        print(f"[+] Fetching and ingesting job from URL: {url}")
        job = discovery_service.ingest_url(url)
        if not job:
            print(f"[✗] Failed to fetch or ingest job from: {url}")
            sys.exit(1)

        print("\n" + "=" * 60)
        print("  URL INGESTION SUCCESSFUL")
        print("=" * 60)
        print(f"Job ID           : {job.job_id}")
        print(f"Title            : {job.title}")
        print(f"Company          : {job.company}")
        print(f"Canonical URL    : {job.canonical_url}")
        print(f"Lifecycle Status : {job.lifecycle_status.value}")
        print("-" * 60)
        print(f"Normalized stored: data/jobs/normalized/{job.job_id}.json\n")

    elif subcommand == "discover-jobs":
        query = discovery_service.load_default_query_from_preferences()
        if args.keyword:
            query.keywords = [k.strip() for k in args.keyword.split(",")]
        if args.location:
            query.locations = [l.strip() for l in args.location.split(",")]

        print(f"[+] Discovering jobs with keywords: {query.keywords}, locations: {query.locations}...")
        result = discovery_service.discover_jobs(query)
        print("\n" + "=" * 60)
        print("  DISCOVERY SUMMARY")
        print("=" * 60)
        print(f"Jobs Discovered  : {result.jobs_discovered}")
        print(f"New Jobs Ingested: {result.jobs_new}")
        print(f"Duplicates Found : {result.duplicates_found}")
        if result.failed_sources:
            print(f"Failed Sources   : {result.failed_sources}")
        print("-" * 60)
        for job in result.jobs:
            status_tag = f"[{job.lifecycle_status.value}]"
            print(f"  • {status_tag:14} {job.title:28} at {job.company:18} ({job.job_id})")
        print("=" * 60 + "\n")

    elif subcommand == "list-jobs":
        ranked = not args.unranked
        jobs = discovery_service.rank_jobs(include_duplicates=args.include_duplicates) if ranked else discovery_service.list_jobs(
            status=args.status,
            min_score=args.min_score,
            recommendation=args.recommendation,
            strategy=args.strategy,
            include_duplicates=args.include_duplicates,
        )

        print("\n" + "=" * 75)
        print(f"  STORED JOBS REGISTRY ({len(jobs)} total)")
        print("=" * 75)
        print(f"{'#':<3} {'Score':<7} {'Rec Tier':<14} {'Job ID':<36} {'Company & Title'}")
        print("-" * 75)
        for i, j in enumerate(jobs, 1):
            score_str = f"{j.overall_fit_score:.1f}" if j.overall_fit_score is not None else "N/A"
            rec_str = j.recommendation or j.lifecycle_status
            print(f"{i:<3} {score_str:<7} {rec_str:<14} {j.job_id:<36} {j.company} - {j.title}")
        print("=" * 75 + "\n")

    elif subcommand == "process-job":
        job_id = args.job_id
        print(f"[+] Processing stored job '{job_id}' with Phase 4 Intelligence Engine...")
        assessment = discovery_service.process_job(job_id)
        if not assessment:
            print(f"[✗] Failed to process job '{job_id}'. Check if job ID exists in data/jobs/normalized/.")
            sys.exit(1)

        print(assessment.human_report)


def handle_application_prep_cli(subcommand: str, args: argparse.Namespace):
    """Handle Application Preparation CLI commands (Phase 6)."""
    from job_copilot.services.application_prep_service import ApplicationPrepService

    prep_service = ApplicationPrepService()
    job_id = args.job_id

    if subcommand == "prepare-job":
        print(f"\n[+] Preparing complete application package for job: {job_id}...")
        try:
            pkg = prep_service.prepare_application(
                job_id_or_text=job_id,
                strategy_override=getattr(args, "strategy", None),
            )
            print("\n" + "=" * 70)
            print("  APPLICATION PACKAGE PREPARATION COMPLETE")
            print("=" * 70)
            print(f"Job ID           : {pkg.job_id}")
            print(f"Target Role      : {pkg.job_title} at {pkg.company}")
            print(f"Resume Strategy  : {pkg.selected_resume_strategy}")
            print(f"Resume PDF       : {pkg.resume_pdf_path}")
            print(f"Cover Letter     : {pkg.cover_letter.word_count} words (Valid: {pkg.cover_letter.validation.is_valid})")
            print(f"Questions Handled: {len(pkg.questions)} ({len(pkg.answers)} answers)")
            print(f"User Inputs Req  : {len(pkg.user_inputs_required)}")
            print(f"Package Status   : {pkg.status.value}")
            print("-" * 70)
            print(f"Saved artifacts under: data/applications/{pkg.job_id}/\n")
        except Exception as e:
            print(f"[✗] Failed to prepare application package: {e}")
            sys.exit(1)

    elif subcommand == "answer-question":
        question_text = args.question
        print(f"[+] Answering question for job '{job_id}':\n    \"{question_text}\"\n")
        ans = prep_service.answer_single_question(job_id, question_text)
        print("=" * 60)
        print(f"Classification : {ans.classification.value}")
        print(f"Requires Input : {ans.requires_user_input}")
        print(f"Rationale      : {ans.rationale}")
        print("-" * 60)
        if ans.answer:
            print(f"Generated Answer:\n{ans.answer}\n")
            if ans.provenance:
                print("Evidence Provenance:")
                for p in ans.provenance:
                    print(f"  • [{p.source_type}] {p.source_ref}: {p.claim_text}")
        else:
            print("[!] No automated answer generated (Human decision required).")
        print("=" * 60 + "\n")

    elif subcommand == "generate-cover-letter":
        pkg = prep_service.get_application_package(job_id)
        if not pkg:
            print(f"[+] Application package not found on disk. Preparing now...")
            pkg = prep_service.prepare_application(job_id_or_text=job_id)

        print("\n" + "=" * 70)
        print(f"  COVER LETTER — {pkg.company.upper()} ({pkg.job_title})")
        print("=" * 70)
        print(pkg.cover_letter.letter_text)
        print("-" * 70)
        print(f"Word Count : {pkg.cover_letter.word_count}")
        print(f"Valid      : {pkg.cover_letter.validation.is_valid}")
        if pkg.cover_letter.validation.warnings:
            print(f"Warnings   : {', '.join(pkg.cover_letter.validation.warnings)}")
        print("=" * 70 + "\n")

    elif subcommand == "application-package":
        pkg = prep_service.get_application_package(job_id)
        if not pkg:
            print(f"[✗] No application package found for '{job_id}'. Run 'prepare-job {job_id}' first.")
            sys.exit(1)

        print("\n" + "=" * 70)
        print(f"  APPLICATION PACKAGE SUMMARY: {pkg.company} - {pkg.job_title}")
        print("=" * 70)
        print(f"Job ID           : {pkg.job_id}")
        print(f"Fit Score        : {pkg.assessment.score_breakdown.overall_score} ({pkg.assessment.recommendation.value})")
        print(f"Resume Strategy  : {pkg.selected_resume_strategy}")
        print(f"Resume PDF       : {pkg.resume_pdf_path}")
        print(f"Cover Letter     : {pkg.cover_letter.word_count} words (Valid: {pkg.cover_letter.validation.is_valid})")
        print(f"Total Questions  : {len(pkg.questions)}")
        print(f"Pending Inputs   : {len(pkg.user_inputs_required)}")
        print(f"Package Status   : {pkg.status.value}")
        print("=" * 70 + "\n")

    elif subcommand == "application-inputs":
        pkg = prep_service.get_application_package(job_id)
        if not pkg:
            print(f"[✗] No application package found for '{job_id}'. Run 'prepare-job {job_id}' first.")
            sys.exit(1)

        print("\n" + "=" * 70)
        print(f"  UNRESOLVED USER INPUTS REQUIRED ({len(pkg.user_inputs_required)})")
        print("=" * 70)
        if not pkg.user_inputs_required:
            print("  [✓] All questions answered from verified evidence! Zero pending inputs.")
        for req in pkg.user_inputs_required:
            print(f"• Question ID   : {req.question_id}")
            print(f"  Question Text : {req.question_text}")
            print(f"  Expected Type : {req.expected_type.value}")
            print(f"  Reason        : {req.reason}")
            print()
        print("=" * 70 + "\n")


def handle_browser_cli(subcommand: str, args: argparse.Namespace):
    """Handle CLI browser-assisted application workflow commands (Phase 7)."""
    import asyncio
    from job_copilot.services.browser_workflow_service import BrowserWorkflowService

    service = BrowserWorkflowService()

    async def _run():
        if subcommand == "browser-start":
            job_id = args.job_id
            url = args.url
            print(f"\n[+] Starting browser session for job '{job_id}' at:\n    {url}")
            try:
                sess = await service.start_session(job_id=job_id, application_url=url, headless=not args.headed)
                print(f"[✓] Browser session created: {sess.session_id}")
                print(f"    Status         : {sess.status.value}")
                print(f"    Detected fields: {len(sess.detected_fields)}")
                print(f"    Mappings       : {len(sess.mappings)}")
                if sess.pause_reason:
                    print(f"    [!] Note: {sess.pause_reason}")
                print(f"\nNext step: python -m job_copilot browser-fill {sess.session_id}\n")
            except Exception as e:
                print(f"[✗] Failed to start browser session: {e}")
                sys.exit(1)

        elif subcommand == "browser-inspect":
            session_id = args.session_id
            print(f"\n[+] Inspecting page for session '{session_id}'...")
            try:
                sess = await service.inspect_session(session_id)
                print(f"[✓] Inspection complete. {len(sess.detected_fields)} field(s) detected:")
                print("-" * 60)
                for f in sess.detected_fields:
                    req_mark = " (REQUIRED)" if f.required else ""
                    print(f"• [{f.element_type.value}] {f.field_id}: '{f.label or f.name or f.placeholder}'{req_mark}")
                print("=" * 60 + "\n")
            except Exception as e:
                print(f"[✗] Inspection failed: {e}")
                sys.exit(1)

        elif subcommand == "browser-fill":
            session_id = args.session_id
            print(f"\n[+] Auto-filling safe fields for session '{session_id}'...")
            try:
                sess = await service.fill_session(session_id)
                print(f"[✓] Auto-fill completed!")
                print(f"    Status       : {sess.status.value}")
                print(f"    Filled fields: {len(sess.filled_fields)}")
                print(f"    Pending input: {len(sess.unresolved_fields)}")
                print(f"    Blocked      : {len(sess.blocked_fields)}")
                if sess.unresolved_fields:
                    print(f"\n[!] Pending inputs: {', '.join(sess.unresolved_fields)}")
                    print(f"Run 'python -m job_copilot browser-inputs {sess.session_id}' to review.")
                elif sess.status.value == "READY_TO_SUBMIT":
                    print(f"\n[✓] All required fields satisfied! Ready for final review.")
                    print(f"Run 'python -m job_copilot browser-review {sess.session_id}' before submission.")
                print()
            except Exception as e:
                print(f"[✗] Auto-fill failed: {e}")
                sys.exit(1)

        elif subcommand == "browser-inputs":
            session_id = args.session_id
            sess = service.get_session(session_id)
            if not sess:
                print(f"[✗] Session '{session_id}' not found.")
                sys.exit(1)

            print("\n" + "=" * 70)
            print(f"  BROWSER PENDING USER INPUTS ({len(sess.unresolved_fields)})")
            print("=" * 70)
            if not sess.unresolved_fields:
                print("  [✓] Zero pending inputs. All required fields filled!")
            for fid in sess.unresolved_fields:
                f = next((f for f in sess.detected_fields if f.field_id == fid), None)
                m = next((m for m in sess.mappings if m.field_id == fid), None)
                print(f"• Field ID  : {fid}")
                print(f"  Label     : {f.label if f else fid}")
                print(f"  Type      : {f.element_type.value if f else 'UNKNOWN'}")
                print(f"  Rationale : {m.rationale if m else 'User input required'}")
                print()
            print("=" * 70 + "\n")

        elif subcommand == "browser-review":
            session_id = args.session_id
            try:
                review = await service.review_session(session_id)
                print("\n" + "=" * 70)
                print(f"  APPLICATION PRE-SUBMISSION REVIEW: {review.company} - {review.role}")
                print("=" * 70)
                print(f"Resume Strategy : {review.resume_strategy}")
                print(f"Resume Artifact : {review.resume_path}")
                print(f"Fields Total    : {review.fields_total}")
                print(f"Fields Filled   : {review.fields_filled}")
                print(f"User Inputs     : {review.user_confirmed}")
                print(f"Unresolved      : {review.unresolved}")
                print(f"Blocked         : {review.blocked}")
                print(f"Validation      : {review.validation}")
                print(f"Ready to Submit : {review.ready_to_submit}")
                print("-" * 70)
                print("Field Breakdown:")
                for d in review.details:
                    print(f"  • {d['field_id']:20} -> [{d['status']}] {d['value'] or '(empty)'}")
                print("=" * 70 + "\n")
            except Exception as e:
                print(f"[✗] Review failed: {e}")
                sys.exit(1)

        elif subcommand == "browser-submit":
            session_id = args.session_id
            sess = service.get_session(session_id)
            if not sess:
                print(f"[✗] Session '{session_id}' not found.")
                sys.exit(1)

            confirm_arg = getattr(args, "confirm", None)
            confirmed = False

            if confirm_arg and confirm_arg.strip().upper() == "SUBMIT":
                confirmed = True
            else:
                # Interactive prompt
                print("\n" + "!" * 70)
                print("  HUMAN CONFIRMATION REQUIRED BEFORE APPLICATION SUBMISSION")
                print("!" * 70)
                print(f"Job ID          : {sess.job_id}")
                print(f"Session ID      : {sess.session_id}")
                print(f"Current URL     : {sess.current_url}")
                print("This action will submit the application form in the browser.")
                user_choice = input("Type 'SUBMIT' to confirm submission: ")
                if user_choice.strip() == "SUBMIT":
                    confirmed = True

            if not confirmed:
                print("[!] Submission cancelled. Explicit human confirmation was not provided.")
                sys.exit(1)

            print("\n[+] Submitting application...")
            try:
                res = await service.submit_session(session_id, confirmed=True, confirm_text="SUBMIT")
                print(f"[✓] Application successfully submitted!")
                print(f"    Reference ID : {res.confirmation_reference}")
                print(f"    Submitted At : {res.submitted_at}")
                print(f"    Evidence     : {res.evidence}\n")
            except Exception as e:
                print(f"[✗] Submission failed or blocked: {e}")
                sys.exit(1)

        elif subcommand == "browser-cancel":
            session_id = args.session_id
            print(f"\n[+] Cancelling browser session '{session_id}'...")
            try:
                await service.cancel_session(session_id)
                print(f"[✓] Session '{session_id}' cancelled and browser closed.\n")
            except Exception as e:
                print(f"[✗] Cancel failed: {e}")
                sys.exit(1)

    asyncio.run(_run())


def handle_tracking_cli(subcommand: str, args: argparse.Namespace):
    """Handle CLI application tracking and outcome analytics commands (Phase 8)."""
    from datetime import datetime
    from job_copilot.services.tracking_service import TrackingService
    from job_copilot.tracking.models import ApplicationLifecycleStatus

    service = TrackingService()

    if subcommand == "applications":
        apps = service.list_applications(
            status=ApplicationLifecycleStatus(args.status) if getattr(args, "status", None) else None,
            strategy=getattr(args, "strategy", None),
            recommendation=getattr(args, "recommendation", None),
        )
        print("\n" + "=" * 80)
        print(f"  TRACKED JOB APPLICATIONS ({len(apps)})")
        print("=" * 80)
        if not apps:
            print("  No applications currently tracked.")
        else:
            print(f"{'App ID':15} | {'Company':15} | {'Role':22} | {'Strategy':14} | {'Status':14}")
            print("-" * 85)
            for a in apps:
                strat = a.resume_strategy or "N/A"
                print(f"{a.application_id:15} | {a.company[:15]:15} | {a.role[:22]:22} | {strat[:14]:14} | {a.current_status.value:14}")
        print("=" * 80 + "\n")

    elif subcommand == "application-status":
        app_id = args.application_id
        app = service.get_application(app_id)
        if not app:
            print(f"[✗] Application '{app_id}' not found.")
            sys.exit(1)

        print("\n" + "=" * 70)
        print(f"  APPLICATION STATUS: {app.company} — {app.role}")
        print("=" * 70)
        print(f"Application ID  : {app.application_id}")
        print(f"Job ID          : {app.job_id}")
        print(f"Current Status  : {app.current_status.value} (since {app.current_status_at})")
        print(f"Resume Strategy : {app.resume_strategy}")
        print(f"Match Score     : {app.match_score} ({app.recommendation})")
        print(f"Submitted At    : {app.submitted_at or 'Not submitted'}")
        print(f"Source          : {app.source}")
        print(f"Events Count    : {len(app.events)}")
        if app.user_notes:
            print("\nUser Notes:")
            for n in app.user_notes:
                print(f"  • {n}")
        print("=" * 70 + "\n")

    elif subcommand == "application-update":
        app_id = args.application_id
        status_val = ApplicationLifecycleStatus(args.status)
        notes = getattr(args, "notes", None)
        try:
            ev = service.record_event(app_id, status_val, notes=notes)
            print(f"\n[✓] Updated application '{app_id}' status to: {status_val.value}")
            if notes:
                print(f"    Notes: {notes}\n")
        except Exception as e:
            print(f"[✗] Failed to update status: {e}")
            sys.exit(1)

    elif subcommand == "application-event":
        app_id = args.application_id
        event_val = ApplicationLifecycleStatus(args.event)
        notes = getattr(args, "notes", None)
        try:
            ev = service.record_event(app_id, event_val, notes=notes)
            print(f"\n[✓] Recorded event '{event_val.value}' for application '{app_id}' ({ev.event_id})\n")
        except Exception as e:
            print(f"[✗] Failed to record event: {e}")
            sys.exit(1)

    elif subcommand == "application-timeline":
        app_id = args.application_id
        try:
            timeline = service.get_timeline(app_id)
            print("\n" + "=" * 70)
            print(f"  APPLICATION TIMELINE: {app_id}")
            print("=" * 70)
            for ev in timeline:
                note_str = f" - {ev.notes}" if ev.notes else ""
                print(f"• [{ev.timestamp.strftime('%Y-%m-%d %H:%M:%S')}] {ev.event_type.value} ({ev.source.value}){note_str}")
            print("=" * 70 + "\n")
        except Exception as e:
            print(f"[✗] Failed to fetch timeline: {e}")
            sys.exit(1)

    elif subcommand == "analytics-funnel":
        from_d = datetime.fromisoformat(args.from_date) if getattr(args, "from_date", None) else None
        to_d = datetime.fromisoformat(args.to_date) if getattr(args, "to_date", None) else None
        funnel = service.get_funnel(from_d, to_d)
        conv = service.get_conversion(from_d, to_d)

        print("\n" + "=" * 60)
        print("  APPLICATION PIPELINE FUNNEL")
        print("=" * 60)
        print(f"Discovered              : {funnel.discovered}")
        print(f"Recommended             : {funnel.recommended}")
        print(f"Prepared                : {funnel.prepared}")
        print(f"Submitted               : {funnel.submitted}")
        print(f"Acknowledged            : {funnel.acknowledged}")
        print(f"Recruiter Responses     : {funnel.recruiter_responses}")
        print(f"Assessments             : {funnel.assessments}")
        print(f"Interviews              : {funnel.interviews}")
        print(f"Final Rounds            : {funnel.final_rounds}")
        print(f"Offers                  : {funnel.offers}")
        print(f"Accepted                : {funnel.accepted}")
        print(f"Rejected                : {funnel.rejected}")
        print(f"Withdrawn               : {funnel.withdrawn}")
        print("-" * 60)
        print("CONVERSION METRICS:")
        print(f"Application Rate        : {conv.application_rate}%")
        print(f"Response Rate           : {conv.response_rate}%")
        print(f"Interview Rate          : {conv.interview_rate}%")
        print(f"Offer Rate              : {conv.offer_rate}%")
        print(f"Acceptance Rate         : {conv.acceptance_rate}%")
        if conv.sample_size_warning:
            print(f"[!] Note: {conv.sample_size_warning}")
        print("=" * 60 + "\n")

    elif subcommand == "analytics-conversion":
        conv = service.get_conversion()
        print("\n" + "=" * 60)
        print("  CONVERSION RATES SUMMARY")
        print("=" * 60)
        print(f"Application Rate (Submitted / Discovered) : {conv.application_rate}%")
        print(f"Response Rate (Responses / Submitted)     : {conv.response_rate}%")
        print(f"Interview Rate (Interviews / Submitted)   : {conv.interview_rate}%")
        print(f"Offer Rate (Offers / Submitted)           : {conv.offer_rate}%")
        print(f"Acceptance Rate (Accepted / Offers)       : {conv.acceptance_rate}%")
        if conv.sample_size_warning:
            print(f"\n[!] Note: {conv.sample_size_warning}")
        print("=" * 60 + "\n")

    elif subcommand == "analytics-strategies":
        metrics = service.get_strategy_metrics()
        print("\n" + "=" * 80)
        print("  STRATEGY PERFORMANCE COMPARISON")
        print("=" * 80)
        if not metrics:
            print("  No application data recorded.")
        else:
            print(f"{'Strategy':20} | {'Apps':5} | {'Resp':5} | {'Intv':5} | {'Offer':5} | {'Intv %':7} | {'Reliability':12}")
            print("-" * 80)
            for m in metrics:
                rel = "RELIABLE" if m.is_statistically_reliable else "SAMPLE < 10"
                print(f"{m.cohort_name:20} | {m.total_applications:5} | {m.recruiter_responses:5} | {m.interviews:5} | {m.offers:5} | {m.interview_rate:6.1f}% | {rel:12}")
        print("=" * 80 + "\n")

    elif subcommand == "analytics-recommendations":
        metrics = service.get_recommendation_metrics()
        print("\n" + "=" * 80)
        print("  RECOMMENDATION TIER OUTCOME ANALYSIS")
        print("=" * 80)
        if not metrics:
            print("  No application data recorded.")
        else:
            print(f"{'Recommendation':18} | {'Apps':5} | {'Resp':5} | {'Intv':5} | {'Offer':5} | {'Intv %':7} | {'Reliability':12}")
            print("-" * 80)
            for m in metrics:
                rel = "RELIABLE" if m.is_statistically_reliable else "SAMPLE < 10"
                print(f"{m.cohort_name:18} | {m.total_applications:5} | {m.recruiter_responses:5} | {m.interviews:5} | {m.offers:5} | {m.interview_rate:6.1f}% | {rel:12}")
        print("=" * 80 + "\n")

    elif subcommand == "analytics-sources":
        metrics = service.get_source_metrics()
        print("\n" + "=" * 80)
        print("  DISCOVERY SOURCE PERFORMANCE ANALYSIS")
        print("=" * 80)
        if not metrics:
            print("  No application data recorded.")
        else:
            print(f"{'Source':20} | {'Apps':5} | {'Resp':5} | {'Intv':5} | {'Offer':5} | {'Intv %':7} | {'Reliability':12}")
            print("-" * 80)
            for m in metrics:
                rel = "RELIABLE" if m.is_statistically_reliable else "SAMPLE < 10"
                print(f"{m.cohort_name:20} | {m.total_applications:5} | {m.recruiter_responses:5} | {m.interviews:5} | {m.offers:5} | {m.interview_rate:6.1f}% | {rel:12}")
        print("=" * 80 + "\n")

    elif subcommand == "analytics-response-times":
        metrics = service.get_response_time_metrics()
        print("\n" + "=" * 75)
        print("  MILESTONE RESPONSE TIME METRICS (DAYS)")
        print("=" * 75)
        print(f"{'Milestone Transition':32} | {'Count':6} | {'Median':7} | {'Mean':7} | {'Min-Max':10}")
        print("-" * 75)
        for m in metrics:
            range_str = f"{m.min_days:.1f}-{m.max_days:.1f}"
            print(f"{m.metric_name:32} | {m.sample_count:6} | {m.median_days:6.1f}d | {m.mean_days:6.1f}d | {range_str:10}")
        print("=" * 75 + "\n")


def handle_copilot_cli(subcommand: str, args: argparse.Namespace):
    """Handle Phase 9 Continuous Copilot CLI actions."""
    from job_copilot.copilot.models import PriorityBand, QueueStatus
    from job_copilot.services.copilot_service import CopilotService

    service = CopilotService()

    if subcommand == "copilot":
        dash = service.get_dashboard()
        print("\n" + "=" * 80)
        print("  JOB COPILOT — TODAY'S PRIORITIZED OPPORTUNITIES")
        print("=" * 80)

        all_active = dash.critical_priority_jobs + dash.high_priority_jobs + dash.medium_priority_jobs
        if not all_active:
            print("  No opportunities currently pending review in queue.")
            print("  Run 'python -m job_copilot copilot-discover' to discover new roles.")
        else:
            if dash.critical_priority_jobs:
                print("\n[CRITICAL PRIORITY]")
                print("─" * 80)
                for j in dash.critical_priority_jobs[:5]:
                    print(f"• {j.company} — {j.title}")
                    print(f"  Score: {j.match_score:.1f} | Rec: {j.recommendation_tier} | Strategy: {j.selected_strategy} | Action: {j.recommendation.action.value if j.recommendation else 'REVIEW'}")
                    if j.explanation and j.explanation.why_apply:
                        print(f"  Why: {j.explanation.why_apply[0]}")
                    print(f"  ID: {j.job_id}")

            if dash.high_priority_jobs:
                print("\n[HIGH PRIORITY]")
                print("─" * 80)
                for j in dash.high_priority_jobs[:5]:
                    print(f"• {j.company} — {j.title}")
                    print(f"  Score: {j.match_score:.1f} | Rec: {j.recommendation_tier} | Strategy: {j.selected_strategy} | Action: {j.recommendation.action.value if j.recommendation else 'REVIEW'}")
                    if j.explanation and j.explanation.why_apply:
                        print(f"  Why: {j.explanation.why_apply[0]}")
                    print(f"  ID: {j.job_id}")

            if dash.medium_priority_jobs:
                print("\n[MEDIUM PRIORITY]")
                print("─" * 80)
                for j in dash.medium_priority_jobs[:5]:
                    print(f"• {j.company} — {j.title} (Score: {j.match_score:.1f}, Strategy: {j.selected_strategy}) [ID: {j.job_id}]")

        if dash.waiting_for_user_jobs:
            print("\n[WAITING FOR USER / READY FOR REVIEW]")
            print("─" * 80)
            for j in dash.waiting_for_user_jobs[:5]:
                print(f"• {j.company} — {j.title} (Status: {j.queue_status.value}) [ID: {j.job_id}]")

        print("\n[RECENT APPLICATION OUTCOMES]")
        print("─" * 80)
        o = dash.recent_outcomes
        print(f"  Discovered: {o.get('discovered', 0)} | Recommended: {o.get('recommended', 0)} | Prepared: {o.get('prepared', 0)} | Submitted: {o.get('submitted', 0)}")
        print(f"  Responses: {o.get('recruiter_responses', 0)} | Interviews: {o.get('interviews', 0)} | Offers: {o.get('offers', 0)} | Accepted: {o.get('accepted', 0)}")

        if dash.top_historical_insights:
            print("\n[TOP HISTORICAL INSIGHTS]")
            print("─" * 80)
            for ins in dash.top_historical_insights[:2]:
                print(f"• {ins.topic}:")
                if ins.inference_statements:
                    print(f"  {ins.inference_statements[0]}")
                if ins.recommendation_statements:
                    print(f"  {ins.recommendation_statements[0]}")

        print("=" * 80 + "\n")

    elif subcommand == "copilot-discover":
        print("\n" + "=" * 80)
        print("  EXECUTING CONTINUOUS JOB DISCOVERY")
        print("=" * 80)
        jobs = service.discover()
        print(f"  Discovered & Processed {len(jobs)} opportunity(ies) into the queue.")
        for j in jobs[:8]:
            print(f"• [{j.priority_band.value}] {j.company} — {j.title} (Score: {j.match_score:.1f})")
        print("=" * 80 + "\n")

    elif subcommand == "copilot-process":
        print("\n" + "=" * 80)
        print("  PROCESSING UNASSESSED OPPORTUNITIES")
        print("=" * 80)
        if getattr(args, "job_id", None):
            job = service.process_job(args.job_id)
            if job:
                print(f"  Processed {job.job_id}: {job.company} — {job.title} (Score: {job.match_score:.1f}, Priority: {job.priority_band.value})")
            else:
                print(f"  Job '{args.job_id}' not found.")
        else:
            jobs = service.process_all_stored()
            print(f"  Processed {len(jobs)} stored jobs into the Copilot queue.")
        print("=" * 80 + "\n")

    elif subcommand == "copilot-queue":
        band = PriorityBand(args.priority) if getattr(args, "priority", None) else None
        st = QueueStatus(args.status) if getattr(args, "status", None) else None
        jobs = service.get_queue(status=st, priority_band=band)
        print("\n" + "=" * 90)
        print(f"  COPILOT OPPORTUNITY QUEUE ({len(jobs)} items)")
        print("=" * 90)
        print(f"{'Priority':9} | {'Score':5} | {'Status':16} | {'Company':20} | {'Role':22} | {'Job ID'}")
        print("-" * 90)
        for j in jobs:
            print(f"{j.priority_band.value:9} | {j.priority_score:5.1f} | {j.queue_status.value:16} | {j.company[:20]:20} | {j.title[:22]:22} | {j.job_id}")
        print("=" * 90 + "\n")

    elif subcommand == "copilot-prepare":
        pkg = service.prepare(job_id=args.job_id, strategy_override=getattr(args, "strategy", None))
        print(f"\n[OK] Application prepared for {pkg.company} ({pkg.job_title})")
        print(f"     Strategy: {pkg.selected_resume_strategy}")
        print(f"     PDF: {pkg.resume_pdf_path}\n")

    elif subcommand == "copilot-approve":
        j = service.approve(job_id=args.job_id)
        if j:
            print(f"\n[OK] Job '{j.job_id}' marked as APPROVED for preparation.\n")
        else:
            print(f"\n[ERROR] Job '{j.job_id}' not found in queue.\n")

    elif subcommand == "copilot-skip":
        j = service.skip(job_id=args.job_id, reason=getattr(args, "reason", None))
        if j:
            print(f"\n[OK] Job '{j.job_id}' SKIPPED.\n")
        else:
            print(f"\n[ERROR] Job '{j.job_id}' not found in queue.\n")

    elif subcommand == "copilot-insights":
        insights = service.get_insights()
        print("\n" + "=" * 80)
        print("  JOB SEARCH HISTORICAL INSIGHTS & LEARNING")
        print("=" * 80)
        if not insights:
            print("  No historical insights generated yet. Accumulate application outcomes through Phase 8.")
        else:
            for ins in insights:
                rel_str = f"SIGNAL SURFACED (N={ins.sample_size} >= 10)" if ins.sample_threshold_met else f"INSUFFICIENT SAMPLE (N={ins.sample_size} < 10)"
                print(f"\n• {ins.topic} [{rel_str}]")
                print("  " + "\n  ".join(ins.fact_statements))
                if ins.inference_statements:
                    print("  " + "\n  ".join(ins.inference_statements))
                if ins.recommendation_statements:
                    print("  " + "\n  ".join(ins.recommendation_statements))
                print(f"  GUARANTEE: {ins.action_required}")
        print("\n" + "=" * 80 + "\n")

    elif subcommand == "targets":
        targets = service.get_targets()
        print("\n" + "=" * 80)
        print("  CANDIDATE TARGETING PREFERENCES (PHASE 9.2)")
        print("=" * 80)
        print("\nTIER 1 — FINANCIAL SERVICES")
        for comp in targets.tier_1.companies:
            print(f"  {comp.name}")
        print("\nTIER 2 — TECHNOLOGY / PRODUCT")
        for comp in targets.tier_2.companies:
            print(f"  {comp.name}")
        print("\nOTHER COMPANIES")
        print("  Allowed: YES")
        print("\nJOB FAMILIES (PRIMARY)")
        for fam in targets.job_families.primary:
            print(f"  • {fam}")
        print("\nLOCATIONS")
        print(f"  Primary: {', '.join(targets.locations.primary)}")
        print(f"  Secondary: {', '.join(targets.locations.secondary)}")
        if targets.locations.international.enabled:
            print(f"  International: {', '.join(targets.locations.international.locations)}")
        print("=" * 80 + "\n")

    elif subcommand == "sources":
        if getattr(args, "health", False):
            reports = service.get_sources_health()
            print("\n" + "=" * 80)
            print("  JOB SOURCES HEALTH & ACCESSIBILITY")
            print("=" * 80)
            for r in reports:
                icon = "✓" if r.state.value == "ACTIVE" else "⚠" if r.state.value in ["LOGIN_REQUIRED", "PAUSED"] else "✗" if r.state.value == "BLOCKED" else "○"
                print(f"{icon} {r.name:28} [{r.state.value:14}] Mode: {r.discovery_mode.value:21} (Every {r.check_interval_minutes}m)")
                if r.message:
                    print(f"    Note: {r.message}")
            print("=" * 80 + "\n")
        else:
            enabled_only = getattr(args, "enabled", False)
            sources = service.get_sources(enabled_only=enabled_only)
            print("\n" + "=" * 80)
            print(f"  JOB SOURCES REGISTRY ({'ENABLED ONLY' if enabled_only else 'ALL CONFIGURED'})")
            print("=" * 80)
            for s in sources:
                icon = "✓" if s.enabled else "○"
                auth_str = "AUTHENTICATED" if s.requires_login else "PUBLIC"
                print(f"{icon} {s.name:28} {auth_str:14} {s.priority.upper():9} (Every {s.check_interval_minutes}m)")
            print("=" * 80 + "\n")


def main():
    """Main CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Job Copilot - Personal Job Application Automation & Copilot"
    )
    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # Phase 9 Continuous Copilot Commands
    subparsers.add_parser("copilot", help="Show daily prioritized Copilot dashboard")
    subparsers.add_parser("copilot-discover", help="Run continuous discovery & process new jobs into queue")
    
    cp_proc = subparsers.add_parser("copilot-process", help="Process stored jobs through Copilot pipeline")
    cp_proc.add_argument("--job-id", help="Optional specific Job ID to process")

    cp_q = subparsers.add_parser("copilot-queue", help="Display prioritized Copilot opportunity queue")
    cp_q.add_argument("--status", help="Filter by queue status (e.g. REVIEW, APPROVED, WAITING_FOR_USER)")
    cp_q.add_argument("--priority", help="Filter by priority band (e.g. CRITICAL, HIGH, MEDIUM)")

    cp_prep = subparsers.add_parser("copilot-prepare", help="Prepare application package for a job")
    cp_prep.add_argument("job_id", help="Target Job ID")
    cp_prep.add_argument("--strategy", help="Optional strategy override")

    cp_appr = subparsers.add_parser("copilot-approve", help="Approve a job for preparation")
    cp_appr.add_argument("job_id", help="Target Job ID")

    cp_sk = subparsers.add_parser("copilot-skip", help="Skip a job opportunity")
    cp_sk.add_argument("job_id", help="Target Job ID")
    cp_sk.add_argument("--reason", help="Optional skip rationale")

    subparsers.add_parser("copilot-insights", help="Display historical outcome learning & insights")

    # Phase 9.2 Targeting & Sources Commands
    subparsers.add_parser("targets", help="Display candidate target companies, job families, and locations")
    src_parser = subparsers.add_parser("sources", help="Display configured job sources and discovery schedules")
    src_parser.add_argument("--enabled", action="store_true", help="List only enabled job sources")
    src_parser.add_argument("--health", action="store_true", help="Display operational health and accessibility status")

    # Phase 8 Tracking & Analytics Commands
    subparsers.add_parser("applications", help="List all tracked job applications")
    
    app_st_parser = subparsers.add_parser("application-status", help="Get status and details of a tracked application")
    app_st_parser.add_argument("application_id", help="Application ID (e.g. app-9d4f10a)")

    app_up_parser = subparsers.add_parser("application-update", help="Update application lifecycle status")
    app_up_parser.add_argument("application_id", help="Application ID")
    app_up_parser.add_argument("--status", required=True, help="New status (e.g. INTERVIEW, REJECTED, OFFER)")
    app_up_parser.add_argument("--notes", help="Optional outcome notes")

    app_ev_parser = subparsers.add_parser("application-event", help="Record a specific lifecycle event")
    app_ev_parser.add_argument("application_id", help="Application ID")
    app_ev_parser.add_argument("--event", required=True, help="Event type (e.g. RECRUITER_RESPONSE, ASSESSMENT)")
    app_ev_parser.add_argument("--notes", help="Optional notes")

    app_tl_parser = subparsers.add_parser("application-timeline", help="Display chronological event timeline")
    app_tl_parser.add_argument("application_id", help="Application ID")

    an_fn_parser = subparsers.add_parser("analytics-funnel", help="Display application pipeline funnel & conversion")
    an_fn_parser.add_argument("--from-date", help="Start date filter (YYYY-MM-DD)")
    an_fn_parser.add_argument("--to-date", help="End date filter (YYYY-MM-DD)")

    subparsers.add_parser("analytics-conversion", help="Display application conversion rates")
    subparsers.add_parser("analytics-strategies", help="Display outcome breakdown by resume strategy")
    subparsers.add_parser("analytics-recommendations", help="Display outcome breakdown by recommendation tier")
    subparsers.add_parser("analytics-sources", help="Display outcome breakdown by job discovery source")
    subparsers.add_parser("analytics-response-times", help="Display milestone response times in days")

    # Phase 7 Browser Commands
    b_start_parser = subparsers.add_parser("browser-start", help="Start browser session for a prepared job")
    b_start_parser.add_argument("job_id", help="Job ID from stored index or application package")
    b_start_parser.add_argument("--url", required=True, help="Job application URL")
    b_start_parser.add_argument("--headed", action="store_true", help="Launch in visible/headed browser mode")

    b_insp_parser = subparsers.add_parser("browser-inspect", help="Re-inspect DOM form fields for a session")
    b_insp_parser.add_argument("session_id", help="Active browser session ID")

    b_fill_parser = subparsers.add_parser("browser-fill", help="Auto-fill safe fields with candidate & Phase 6 data")
    b_fill_parser.add_argument("session_id", help="Active browser session ID")

    b_inp_parser = subparsers.add_parser("browser-inputs", help="List unresolved user input fields for a session")
    b_inp_parser.add_argument("session_id", help="Active browser session ID")

    b_rev_parser = subparsers.add_parser("browser-review", help="Display pre-submission review artifact")
    b_rev_parser.add_argument("session_id", help="Active browser session ID")

    b_sub_parser = subparsers.add_parser("browser-submit", help="Submit application (requires explicit confirmation)")
    b_sub_parser.add_argument("session_id", help="Active browser session ID")
    b_sub_parser.add_argument("--confirm", help="Confirmation text (must be 'SUBMIT')")

    b_canc_parser = subparsers.add_parser("browser-cancel", help="Cancel browser session and close browser")
    b_canc_parser.add_argument("session_id", help="Active browser session ID")

    # Phase 6 Commands
    # prepare-job <job_id> [--strategy <name>]
    prep_parser = subparsers.add_parser("prepare-job", help="Prepare complete application package (resume, cover letter, Q&A)")
    prep_parser.add_argument("job_id", help="Job ID from stored index or text file")
    prep_parser.add_argument("--strategy", help="Optional strategy override")

    # answer-question <job_id> --question "<text>"
    ans_parser = subparsers.add_parser("answer-question", help="Answer a single application question with evidence")
    ans_parser.add_argument("job_id", help="Job ID from stored index")
    ans_parser.add_argument("--question", required=True, help="Question text")

    # generate-cover-letter <job_id>
    cl_parser = subparsers.add_parser("generate-cover-letter", help="Generate and print validated cover letter")
    cl_parser.add_argument("job_id", help="Job ID from stored index")

    # application-package <job_id>
    pkg_parser = subparsers.add_parser("application-package", help="Display summary of prepared application package")
    pkg_parser.add_argument("job_id", help="Job ID from stored index")

    # application-inputs <job_id>
    inp_parser = subparsers.add_parser("application-inputs", help="List unresolved user-input required questions")
    inp_parser.add_argument("job_id", help="Job ID from stored index")

    # Phase 5 Commands
    ingest_parser = subparsers.add_parser("ingest-job", help="Ingest a raw job description file")
    ingest_parser.add_argument("file", help="Path to text file containing job description")
    ingest_parser.add_argument("--company", help="Optional company name override")
    ingest_parser.add_argument("--title", help="Optional job title override")
    ingest_parser.add_argument("--location", help="Optional location override")

    url_parser = subparsers.add_parser("ingest-url", help="Fetch and ingest a job posting from public URL")
    url_parser.add_argument("url", help="Public URL of the job posting")

    disc_parser = subparsers.add_parser("discover-jobs", help="Discover jobs matching criteria across configured sources")
    disc_parser.add_argument("--keyword", help="Comma-separated keywords/titles")
    disc_parser.add_argument("--location", help="Comma-separated locations")

    list_parser = subparsers.add_parser("list-jobs", help="List and rank stored jobs from index")
    list_parser.add_argument("--status", help="Filter by lifecycle status")
    list_parser.add_argument("--min-score", type=float, help="Filter by minimum fit score")
    list_parser.add_argument("--recommendation", help="Filter by recommendation tier")
    list_parser.add_argument("--strategy", help="Filter by resume strategy")
    list_parser.add_argument("--unranked", action="store_true", help="Display without fit score ranking")
    list_parser.add_argument("--include-duplicates", action="store_true", help="Include duplicate jobs")

    proc_parser = subparsers.add_parser("process-job", help="Evaluate a stored job through Phase 4 Intelligence Engine")
    proc_parser.add_argument("job_id", help="Job ID from stored index")

    # Phase 4 Top-level commands
    an_parser = subparsers.add_parser("analyze-job", help="Analyze a job description file into structured JSON")
    an_parser.add_argument("file", help="Path to text file containing job description")

    match_parser = subparsers.add_parser("match-job", help="Match candidate profile against a job description with multi-dimensional score")
    match_parser.add_argument("file", help="Path to text file containing job description")

    rec_parser = subparsers.add_parser("recommend-job", help="Get application recommendation (STRONG_APPLY, APPLY, REVIEW, SKIP)")
    rec_parser.add_argument("file", help="Path to text file containing job description")

    tailor_job_parser = subparsers.add_parser("tailor-job", help="Evaluate job and compile tailored 1-page resume PDF")
    tailor_job_parser.add_argument("file", help="Path to text file containing job description")
    tailor_job_parser.add_argument("--strategy", help="Optional strategy override (auto-selected if omitted)")

    # Resume Subcommands (Phase 3)
    resume_parser = subparsers.add_parser("resume", help="Resume tailoring, generation, and analysis")
    resume_subparsers = resume_parser.add_subparsers(dest="resume_command", help="Resume actions")
    resume_subparsers.add_parser("strategies", help="List all configured resume strategies")
    
    gen_parser = resume_subparsers.add_parser("generate", help="Generate resume for a strategy")
    gen_parser.add_argument("--strategy", required=True, help="Strategy name (e.g. backend_java, cloud_devops)")
    
    an_jd_parser = resume_subparsers.add_parser("analyze", help="Analyze a job description file")
    an_jd_parser.add_argument("--job-description", required=True, help="Path to text file with job description")
    
    t_parser = resume_subparsers.add_parser("tailor", help="Tailor and generate resume for a job description")
    t_parser.add_argument("--job", required=True, help="Path to job description file")
    t_parser.add_argument("--strategy", help="Optional strategy name (auto-recommended if omitted)")

    # Top-level standalone flags
    parser.add_argument("--init-db", action="store_true", help="Initialize database tables")
    parser.add_argument("--start-api", action="store_true", help="Start the FastAPI web server")
    parser.add_argument("--start-mcp", action="store_true", help="Start the FastMCP server via stdio")

    args = parser.parse_args()

    if args.subcommand in (
        "copilot",
        "copilot-discover",
        "copilot-process",
        "copilot-queue",
        "copilot-prepare",
        "copilot-approve",
        "copilot-skip",
        "copilot-insights",
        "targets",
        "sources",
    ):
        handle_copilot_cli(args.subcommand, args)
        return

    if args.subcommand in (
        "applications",
        "application-status",
        "application-update",
        "application-event",
        "application-timeline",
        "analytics-funnel",
        "analytics-conversion",
        "analytics-strategies",
        "analytics-recommendations",
        "analytics-sources",
        "analytics-response-times",
    ):
        handle_tracking_cli(args.subcommand, args)
        return

    if args.subcommand in ("browser-start", "browser-inspect", "browser-fill", "browser-inputs", "browser-review", "browser-submit", "browser-cancel"):
        handle_browser_cli(args.subcommand, args)
        return

    if args.subcommand in ("prepare-job", "answer-question", "generate-cover-letter", "application-package", "application-inputs"):
        handle_application_prep_cli(args.subcommand, args)
        return

    if args.subcommand in ("ingest-job", "ingest-url", "discover-jobs", "list-jobs", "process-job"):
        handle_discovery_cli(args.subcommand, args)
        return

    if args.subcommand in ("analyze-job", "match-job", "recommend-job", "tailor-job"):
        handle_job_intelligence_cli(args.subcommand, args)
        return

    if args.subcommand == "resume":
        handle_resume_cli(args)
        return

    if args.start_api:
        from job_copilot.api.app import start_api
        start_api()
        return

    if args.start_mcp:
        from job_copilot.mcp.server import main as start_mcp
        start_mcp()
        return

    # Default: Run system status check
    success = check_system_status()
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

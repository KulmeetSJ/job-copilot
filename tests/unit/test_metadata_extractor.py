"""Unit tests for JobMetadataExtractor."""

import pytest
from job_copilot.ingestion.metadata_extractor import JobMetadataExtractor, ExtractedMetadata


def test_clean_company_name_pronouns_and_newlines():
    """Verify company cleaner strips trailing sentences, pronouns, and punctuation without hardcoding."""
    assert JobMetadataExtractor.clean_company_name("Mastercard\nWe are a leading payments tech company") == "Mastercard"
    assert JobMetadataExtractor.clean_company_name("Mastercard We are looking for engineers") == "Mastercard"
    assert JobMetadataExtractor.clean_company_name("Google You will build distributed systems") == "Google"
    assert JobMetadataExtractor.clean_company_name("Stripe, Inc.") == "Stripe, Inc."
    assert JobMetadataExtractor.clean_company_name("   Amazon AWS   ") == "Amazon AWS"
    # Reject explicit unknown markers
    assert JobMetadataExtractor.clean_company_name("Company unavailable") is None
    assert JobMetadataExtractor.clean_company_name("unknown") is None
    assert JobMetadataExtractor.clean_company_name("") is None


def test_clean_title_requisition_and_tags():
    """Verify title cleaner strips requisition IDs and location tags."""
    assert JobMetadataExtractor.clean_title("Software Engineer II (R-12345)") == "Software Engineer II"
    assert JobMetadataExtractor.clean_title("Senior Backend Engineer - Req-9999") == "Senior Backend Engineer"
    assert JobMetadataExtractor.clean_title("Principal Cloud Architect - Pune, India") == "Principal Cloud Architect"
    assert JobMetadataExtractor.clean_title("DevOps Engineer | Remote") == "DevOps Engineer"


def test_extract_from_workday_url_and_html():
    """Test extracting Workday job posting with JSON-LD, title, and domain slug."""
    url = "https://mastercard.wd1.myworkdayjobs.com/en-US/CorporateCareers/job/O-Fallon-Missouri/Software-Engineer-II_R-198273"
    html_doc = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Software Engineer II - Mastercard Careers - Workday</title>
        <meta property="og:site_name" content="Mastercard" />
        <meta property="og:title" content="Software Engineer II" />
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "JobPosting",
            "title": "Software Engineer II",
            "hiringOrganization": {
                "@type": "Organization",
                "name": "Mastercard"
            },
            "jobLocation": {
                "@type": "Place",
                "address": {
                    "addressLocality": "O'Fallon",
                    "addressRegion": "MO",
                    "addressCountry": "USA"
                }
            },
            "description": "<p>We are seeking a Software Engineer II to join Mastercard Payments team.</p>"
        }
        </script>
    </head>
    <body>
        <div id="root">Loading Workday...</div>
    </body>
    </html>
    """
    meta = JobMetadataExtractor.extract_from_html(html_doc, url=url)
    assert meta.company == "Mastercard"
    assert meta.title == "Software Engineer II"
    assert "O'Fallon" in (meta.location or "")
    assert meta.ats_name == "Workday"
    assert meta.source_type == "workday"


def test_extract_from_greenhouse_url_and_meta():
    """Test extracting Greenhouse posting."""
    url = "https://boards.greenhouse.io/stripe/jobs/4567890"
    html_doc = """
    <html>
    <head>
        <title>Backend Engineer at Stripe</title>
        <meta property="og:site_name" content="Stripe" />
    </head>
    <body>
        <h1>Backend Engineer</h1>
    </body>
    </html>
    """
    meta = JobMetadataExtractor.extract_from_html(html_doc, url=url)
    assert meta.company == "Stripe"
    assert meta.title == "Backend Engineer"
    assert meta.ats_name == "Greenhouse"


def test_extract_from_lever_url():
    """Test extracting Lever posting."""
    url = "https://jobs.lever.co/netflix/a1b2c3d4-e5f6-7890"
    html_doc = """
    <html>
    <head>
        <title>Netflix Careers - Senior Distributed Systems Engineer</title>
    </head>
    <body></body>
    </html>
    """
    meta = JobMetadataExtractor.extract_from_html(html_doc, url=url)
    assert meta.company == "Netflix"
    assert meta.title == "Senior Distributed Systems Engineer"
    assert meta.ats_name == "Lever"


def test_extract_from_ashby_url():
    """Test extracting Ashby posting."""
    url = "https://jobs.ashbyhq.com/openai/98765432-1234"
    html_doc = """
    <html>
    <head>
        <title>Research Engineer | OpenAI</title>
    </head>
    <body></body>
    </html>
    """
    meta = JobMetadataExtractor.extract_from_html(html_doc, url=url)
    assert meta.company == "OpenAI"
    assert meta.title == "Research Engineer"
    assert meta.ats_name == "Ashby"

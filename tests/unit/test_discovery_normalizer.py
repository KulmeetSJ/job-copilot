"""Unit tests for Phase 5 JobNormalizer."""

import pytest
from job_copilot.domain.enums import RemoteStatus
from job_copilot.ingestion.models import RawJob
from job_copilot.ingestion.normalizer import JobNormalizer


@pytest.fixture
def normalizer():
    return JobNormalizer()


def test_html_and_unicode_cleaning(normalizer):
    raw_html = """
    <div>
        <h1>Senior Software Engineer</h1>
        <p>We are hiring at <b>Stripe</b> for remote work.</p>
        <ul>
            <li>Java &amp; Spring Boot</li>
            <li>PostgreSQL &nbsp; database</li>
        </ul>
        <script>alert('malicious')</script>
    </div>
    """
    clean = normalizer.clean_text(raw_html)
    assert "<script>" not in clean
    assert "alert(" not in clean
    assert "<b>" not in clean
    assert "Stripe" in clean
    assert "Java & Spring Boot" in clean
    assert "PostgreSQL   database" in clean or "PostgreSQL database" in clean


def test_url_canonicalization(normalizer):
    url_with_tracking = "https://jobs.stripe.com/positions/12345/?utm_source=linkedin&utm_medium=feed&ref=job_board"
    canonical = normalizer.canonicalize_url(url_with_tracking)
    assert canonical == "https://jobs.stripe.com/positions/12345"

    clean_url = "https://company.com/careers/swe/"
    assert normalizer.canonicalize_url(clean_url) == "https://company.com/careers/swe"


def test_content_hash_stability(normalizer):
    text1 = "Seeking a Java Engineer with 2+ years experience in Pune."
    text2 = "  Seeking a Java Engineer with 2+ years experience in Pune.  \n"
    hash1 = normalizer.compute_content_hash(text1)
    hash2 = normalizer.compute_content_hash(text2)
    assert hash1 == hash2


def test_normalize_raw_job(normalizer):
    raw = RawJob(
        source="manual",
        source_job_id="stripe-101",
        source_url="https://stripe.com/jobs/101?utm_campaign=spring",
        company="Stripe",
        title="Software Engineer - Backend",
        location="Remote",
        raw_description="<p>Stripe is hiring a Software Engineer for Remote work with Java and GCP.</p>",
    )
    canonical = normalizer.normalize(raw)
    assert canonical.job_id == "manual-stripe-101"
    assert canonical.company == "Stripe"
    assert canonical.title == "Software Engineer - Backend"
    assert canonical.remote_policy == RemoteStatus.REMOTE
    assert canonical.canonical_url == "https://stripe.com/jobs/101"
    assert "<p>" not in canonical.clean_description

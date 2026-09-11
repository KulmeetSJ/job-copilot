"""Repository security and secret scanning utilities."""

from pathlib import Path
import re
from typing import Dict, List, Optional, Tuple

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)

# Common secret detection regex patterns
SECRET_PATTERNS = [
    ("AWS Access Key", re.compile(r"(?i)\b(AKIA[0-9A-Z]{16})\b")),
    ("Private Key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----")),
    ("GitHub Personal Access Token", re.compile(r"\b(ghp_[a-zA-Z0-9]{36}|github_pat_[a-zA-Z0-9_]{82})\b")),
    ("Generic High-Entropy API Key", re.compile(r"(?i)(?:api_key|apikey|secret_key|app_secret)\s*[:=]\s*['\"][a-zA-Z0-9_\-]{20,}['\"]")),
    ("Bearer Token Literal", re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{30,}")),
    ("Slack Token", re.compile(r"xox[baprs]-[0-9a-zA-Z]{10,48}")),
]

# Paths allowed to contain test fixtures, compiled caches, or documentation examples
EXCLUDED_PATTERNS = [
    ".git/",
    ".venv/",
    "venv/",
    "__pycache__/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    "tests/",
    ".env.example",
    "docs/",
]


def scan_file_for_secrets(file_path: Path) -> List[Tuple[str, int, str]]:
    """
    Scan a single file for suspicious secret patterns.
    Returns list of (pattern_name, line_number, sanitized_snippet).
    """
    path_str = str(file_path).replace("\\", "/")
    if any(ex in path_str for ex in EXCLUDED_PATTERNS):
        return []

    if not file_path.exists() or not file_path.is_file():
        return []

    # Ignore binary files or files > 5MB
    if file_path.stat().st_size > 5 * 1024 * 1024:
        return []

    findings: List[Tuple[str, int, str]] = []
    try:
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        lines = content.splitlines()
        for idx, line in enumerate(lines, 1):
            # Skip comments or obvious example placeholders
            if "example" in line.lower() or "placeholder" in line.lower() or "mock" in line.lower():
                continue

            for pattern_name, pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    # Sanitize snippet: mask middle characters
                    masked_snippet = line.strip()[:60]
                    findings.append((pattern_name, idx, masked_snippet))
    except Exception as e:
        logger.warning(f"Failed to scan file {file_path}: {e}")

    return findings


def scan_repository_for_secrets(base_dir: Optional[Path] = None) -> Dict[str, List[Tuple[str, int, str]]]:
    """
    Recursively scan repository for suspicious secrets.
    Returns dictionary mapping relative file paths to findings.
    """
    root = base_dir or Path.cwd()
    all_findings: Dict[str, List[Tuple[str, int, str]]] = {}

    for file_path in root.rglob("*"):
        if file_path.is_file():
            rel_path = file_path.relative_to(root).as_posix()
            findings = scan_file_for_secrets(file_path)
            if findings:
                all_findings[rel_path] = findings

    return all_findings

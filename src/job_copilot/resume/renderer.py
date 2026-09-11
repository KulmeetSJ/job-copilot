"""LaTeX Resume Renderer and PDF Compiler."""

import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Optional, Tuple
import jinja2
from pypdf import PdfReader

from job_copilot.resume.models import TailoredResume
from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


def escape_latex(s: str) -> str:
    r"""
    Escape LaTeX special characters safely.
    Characters: \, %, &, _, {, }, $, ^, ~, #
    """
    if s is None:
        return ""
    text = str(s)
    
    # Backslash first to prevent escaping subsequent escape backslashes
    text = text.replace("\\", r"\textbackslash{}")
    
    replacements = {
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    
    for char, escaped in replacements.items():
        text = text.replace(char, escaped)
        
    return text


def format_date(date_str: Optional[str]) -> str:
    """Convert ISO or Year-Month date strings (e.g. '2024-07') to 'Jul 2024'."""
    if not date_str:
        return ""
    
    s = str(date_str).strip()
    if s.lower() == "present":
        return "Present"
        
    months = {
        "01": "Jan", "02": "Feb", "03": "Mar", "04": "Apr",
        "05": "May", "06": "Jun", "07": "Jul", "08": "Aug",
        "09": "Sep", "10": "Oct", "11": "Nov", "12": "Dec",
        "1": "Jan", "2": "Feb", "3": "Mar", "4": "Apr",
        "5": "May", "6": "Jun", "7": "Jul", "8": "Aug",
        "9": "Sep",
    }
    
    parts = s.split("-")
    if len(parts) >= 2 and parts[1] in months:
        return f"{months[parts[1]]} {parts[0]}"
    return s


class LaTeXResumeRenderer:
    """
    Renders strongly typed TailoredResume into LaTeX source code and compiles to PDF via Tectonic.
    """

    def __init__(self, templates_dir: Optional[Path] = None):
        self.templates_dir = templates_dir or Path(__file__).parent / "templates"
        
        # Configure Jinja2 environment with LaTeX-compatible custom delimiters
        self.jinja_env = jinja2.Environment(
            loader=jinja2.FileSystemLoader(str(self.templates_dir)),
            block_start_string=r"\BLOCK{",
            block_end_string=r"}",
            variable_start_string=r"\VAR{",
            variable_end_string=r"}",
            comment_start_string=r"\#{",
            comment_end_string=r"}",
            trim_blocks=True,
            lstrip_blocks=True,
            autoescape=False,
        )
        
        # Register custom filters
        self.jinja_env.filters["latex_escape"] = escape_latex
        self.jinja_env.filters["format_date"] = format_date

    def render_tex(self, resume: TailoredResume, template_name: str = "resume.tex.j2") -> str:
        """Render the structured resume model into a LaTeX string."""
        template = self.jinja_env.get_template(template_name)
        return template.render(
            personal_info=resume.personal_info,
            display_title=resume.display_title,
            summary=resume.summary,
            skill_groups=resume.skill_groups,
            experience=resume.experience,
            projects=resume.projects,
            education=resume.education,
            certifications=resume.certifications,
            awards=resume.awards,
            section_order=resume.section_order,
        )

    def write_tex(self, tex_content: str, output_tex_path: Path) -> Path:
        """Write rendered LaTeX string to file."""
        output_tex_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_tex_path, "w", encoding="utf-8") as f:
            f.write(tex_content)
        return output_tex_path

    def compile_pdf(self, tex_path: Path, output_pdf_dir: Optional[Path] = None) -> Tuple[Optional[Path], Optional[str], Optional[int]]:
        """
        Compile a .tex file to .pdf using Tectonic (or pdflatex).
        Returns (pdf_path, error_message, page_count).
        """
        output_dir = output_pdf_dir or tex_path.parent
        output_dir.mkdir(parents=True, exist_ok=True)
        pdf_path = output_dir / f"{tex_path.stem}.pdf"

        # Find Tectonic binary
        tectonic_bin = shutil.which("tectonic") or "/opt/homebrew/bin/tectonic"
        if not os.path.exists(tectonic_bin):
            pdflatex_bin = shutil.which("pdflatex")
            if not pdflatex_bin:
                return None, "Neither 'tectonic' nor 'pdflatex' compiler found.", None
            
            # Use pdflatex fallback
            try:
                cmd = [pdflatex_bin, "-interaction=nonstopmode", f"-output-directory={output_dir}", str(tex_path)]
                res = subprocess.run(cmd, capture_output=True, text=True, check=True)
                page_count = self._get_page_count(pdf_path)
                return pdf_path, None, page_count
            except subprocess.CalledProcessError as e:
                return None, f"pdflatex compilation error:\n{e.stderr or e.stdout}", None

        # Compile with Tectonic
        try:
            cmd = [tectonic_bin, "-o", str(output_dir), str(tex_path)]
            res = subprocess.run(cmd, capture_output=True, text=True, check=True)
            page_count = self._get_page_count(pdf_path)
            return pdf_path, None, page_count
        except subprocess.CalledProcessError as e:
            return None, f"Tectonic compilation error:\n{e.stderr or e.stdout}", None

    def _get_page_count(self, pdf_path: Path) -> Optional[int]:
        """Extract total page count from generated PDF."""
        if not pdf_path.exists():
            return None
        try:
            reader = PdfReader(str(pdf_path))
            return len(reader.pages)
        except Exception as e:
            logger.warning(f"Could not read page count from {pdf_path}: {e}")
            return None

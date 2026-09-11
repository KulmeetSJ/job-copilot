"""Resume Strategy Configuration models and loader."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class ResumeStrategyConfig(BaseModel):
    """Configuration defining positioning emphasis, skill priorities, and section ordering for a resume strategy."""
    name: str = Field(description="Internal strategy identifier (e.g. backend_java, cloud_devops)")
    display_title: str = Field(description="Header title (e.g. Software Engineer | Backend & Distributed Systems)")
    summary_template: str = Field(description="Base professional summary template with dynamic slots")
    prioritized_skills: List[str] = Field(default_factory=list, description="Skills to emphasize at top of skills section")
    deprioritized_skills: List[str] = Field(default_factory=list, description="Skills to omit or place lower")
    preferred_projects: List[str] = Field(default_factory=list, description="Project names to prioritize")
    deprioritized_projects: List[str] = Field(default_factory=list, description="Projects to exclude if space is constrained")
    preferred_experience_keywords: List[str] = Field(default_factory=list, description="Keywords for ranking experience bullets")
    section_order: List[str] = Field(
        default_factory=lambda: [
            "summary",
            "skills",
            "experience",
            "projects",
            "certifications",
            "awards",
            "education",
        ]
    )
    max_bullets_per_experience: int = Field(default=5)
    max_projects: int = Field(default=3)
    max_bullets_per_project: int = Field(default=2)


class StrategyRegistry:
    """Registry that discovers and loads YAML strategy configuration files."""

    def __init__(self, strategies_dir: Optional[Path] = None):
        self.strategies_dir = strategies_dir or Path("data/resume_strategies")

    def list_strategies(self) -> List[str]:
        """Return all available strategy identifiers."""
        if not self.strategies_dir.exists():
            return []
        return [f.stem for f in sorted(self.strategies_dir.glob("*.yaml"))]

    def get_strategy(self, name: str) -> ResumeStrategyConfig:
        """Load and parse a specific strategy YAML file."""
        file_path = self.strategies_dir / f"{name}.yaml"
        if not file_path.exists():
            raise FileNotFoundError(
                f"Resume strategy '{name}' not found at {file_path.resolve()}. "
                f"Available strategies: {self.list_strategies()}"
            )

        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        if not data:
            raise ValueError(f"Strategy file {file_path} is empty")

        return ResumeStrategyConfig.model_validate(data)

    def load_all(self) -> Dict[str, ResumeStrategyConfig]:
        """Load all registered strategies into a dictionary."""
        return {name: self.get_strategy(name) for name in self.list_strategies()}

"""Unit tests for Resume Strategy loader and registry."""

from pathlib import Path
import pytest
from job_copilot.resume.strategy import ResumeStrategyConfig, StrategyRegistry


@pytest.fixture
def registry():
    return StrategyRegistry(Path("data/resume_strategies"))


def test_list_strategies(registry):
    strategies = registry.list_strategies()
    expected = {"backend_java", "cloud_devops", "data_engineering", "full_stack", "sre_devops"}
    assert set(strategies) == expected


@pytest.mark.parametrize("strat_name", [
    "backend_java",
    "cloud_devops",
    "data_engineering",
    "full_stack",
    "sre_devops",
])
def test_load_each_strategy(registry, strat_name):
    strat = registry.get_strategy(strat_name)
    assert isinstance(strat, ResumeStrategyConfig)
    assert strat.name == strat_name
    assert len(strat.display_title) > 0
    assert len(strat.summary_template) > 0
    assert len(strat.prioritized_skills) > 0
    assert len(strat.preferred_projects) > 0
    assert strat.max_bullets_per_experience > 0
    assert strat.max_projects > 0


def test_missing_strategy_raises(registry):
    with pytest.raises(FileNotFoundError):
        registry.get_strategy("non_existent_strategy")

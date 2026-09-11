"""Configurable scoring weights, evidence multipliers, and recommendation thresholds."""

from typing import Dict
from pydantic import BaseModel, Field

from job_copilot.matching.models import MatchClassification, RequirementImportance


class ScoringDimensionWeights(BaseModel):
    """Weight distribution across the 7 fit evaluation dimensions (sums to 1.0)."""
    technical: float = Field(default=0.30, description="30% Technical skills match")
    responsibilities: float = Field(default=0.25, description="25% Responsibility overlap")
    role_seniority: float = Field(default=0.15, description="15% Role title & seniority alignment")
    professional_evidence: float = Field(default=0.15, description="15% Confirmed professional evidence depth")
    domain: float = Field(default=0.05, description="5% Domain overlap (Fintech/Payments)")
    preferences: float = Field(default=0.05, description="5% Work mode & location preference alignment")
    credentials: float = Field(default=0.05, description="5% Education & Certifications")


class EvidenceQualityWeights(BaseModel):
    """Quality multipliers for match classifications (0.0 to 1.0)."""
    confirmed: float = Field(default=1.00, description="Confirmed professional experience")
    project_only: float = Field(default=0.65, description="Personal/portfolio project experience")
    exposure_only: float = Field(default=0.50, description="Hands-on / training exposure (GKE, Helm, ADK)")
    partial: float = Field(default=0.40, description="Partial experience or compound requirement")
    positioning_only: float = Field(default=0.20, description="Positioning / unverified context (AWS)")
    no_evidence: float = Field(default=0.00, description="No evidence")
    conflict: float = Field(default=-0.50, description="Contradiction penalty")


class RequirementImportanceWeights(BaseModel):
    """Multiplier based on requirement criticality."""
    critical: float = Field(default=1.5, description="Must-have critical skill")
    high: float = Field(default=1.0, description="High importance requirement")
    medium: float = Field(default=0.7, description="Medium importance requirement")
    low: float = Field(default=0.4, description="Low importance / nice-to-have")


class RecommendationThresholds(BaseModel):
    """Score boundaries for application recommendation tiers."""
    strong_apply: float = Field(default=88.0, description="Minimum score for STRONG_APPLY")
    apply: float = Field(default=75.0, description="Minimum score for APPLY")
    review: float = Field(default=60.0, description="Minimum score for REVIEW")
    low_priority: float = Field(default=45.0, description="Minimum score for LOW_PRIORITY")
    # Below low_priority is SKIP


class MatchingConfig(BaseModel):
    """Unified matching and scoring configuration."""
    dimension_weights: ScoringDimensionWeights = Field(default_factory=ScoringDimensionWeights)
    evidence_weights: EvidenceQualityWeights = Field(default_factory=EvidenceQualityWeights)
    importance_weights: RequirementImportanceWeights = Field(default_factory=RequirementImportanceWeights)
    thresholds: RecommendationThresholds = Field(default_factory=RecommendationThresholds)

    def get_evidence_weight(self, classification: MatchClassification) -> float:
        """Lookup multiplier for a given match classification."""
        mapping = {
            MatchClassification.MATCH_CONFIRMED: self.evidence_weights.confirmed,
            MatchClassification.MATCH_PROJECT_ONLY: self.evidence_weights.project_only,
            MatchClassification.MATCH_EXPOSURE_ONLY: self.evidence_weights.exposure_only,
            MatchClassification.PARTIAL_MATCH: self.evidence_weights.partial,
            MatchClassification.MATCH_POSITIONING_ONLY: self.evidence_weights.positioning_only,
            MatchClassification.NO_EVIDENCE: self.evidence_weights.no_evidence,
            MatchClassification.CONFLICT: self.evidence_weights.conflict,
        }
        return mapping.get(classification, 0.0)

    def get_importance_multiplier(self, importance: RequirementImportance) -> float:
        """Lookup multiplier for requirement importance level."""
        mapping = {
            RequirementImportance.CRITICAL: self.importance_weights.critical,
            RequirementImportance.HIGH: self.importance_weights.high,
            RequirementImportance.MEDIUM: self.importance_weights.medium,
            RequirementImportance.LOW: self.importance_weights.low,
        }
        return mapping.get(importance, 1.0)


# Default global instance
default_matching_config = MatchingConfig()

"""Targeting and preference configuration loader for Phase 9.2."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import yaml

from job_copilot.utils.logging import get_logger

logger = get_logger(__name__)


class TargetCompany(BaseModel):
    """Specific targeted employer definition."""
    name: str
    domain: Optional[str] = None


class TargetCompanyTier(BaseModel):
    """Prioritized group of target companies with common domain characteristics."""
    priority_tier: int
    domain_group: str
    reason: str
    bonus_points: float = 0.0
    companies: List[TargetCompany] = Field(default_factory=list)


class NonTargetPolicy(BaseModel):
    """Policy regarding non-target company opportunities."""
    allow_non_target_companies: bool = True
    default_bonus_points: float = 0.0
    notes: Optional[str] = None


class JobFamilyConfig(BaseModel):
    """Broad role families for discovery (not restrictive exact-title filters)."""
    primary: List[str] = Field(default_factory=list)
    secondary: List[str] = Field(default_factory=list)


class SkillsConfig(BaseModel):
    """Search and matching signals (does not create unverified candidate claims)."""
    high_priority: List[str] = Field(default_factory=list)
    secondary: List[str] = Field(default_factory=list)


class InternationalLocationConfig(BaseModel):
    """International location targeting preferences."""
    enabled: bool = True
    locations: List[str] = Field(default_factory=list)


class LocationConfig(BaseModel):
    """Location preferences influencing discovery and prioritization."""
    primary: List[str] = Field(default_factory=list)
    secondary: List[str] = Field(default_factory=list)
    international: InternationalLocationConfig = Field(default_factory=InternationalLocationConfig)


class RemotePoliciesConfig(BaseModel):
    """Recognized remote work policies."""
    supported_modes: List[str] = Field(
        default_factory=lambda: [
            "REMOTE_WORLDWIDE",
            "REMOTE_INDIA",
            "REMOTE_REGION_RESTRICTED",
            "HYBRID",
            "ONSITE",
            "UNKNOWN",
        ]
    )
    notes: Optional[str] = None


class SearchProfile(BaseModel):
    """Focused query profile for search-based discovery."""
    name: str
    keywords: List[str] = Field(default_factory=list)
    locations: List[str] = Field(default_factory=list)


class JobTargetsConfig(BaseModel):
    """Consolidated targeting and preference configuration."""
    tier_1: TargetCompanyTier = Field(
        default_factory=lambda: TargetCompanyTier(
            priority_tier=1,
            domain_group="financial_services",
            reason="Strong domain adjacency to candidate's HSBC Payments/Data Platform experience",
            bonus_points=5.0,
            companies=[],
        )
    )
    tier_2: TargetCompanyTier = Field(
        default_factory=lambda: TargetCompanyTier(
            priority_tier=2,
            domain_group="technology_product",
            reason="High-scale product and technology engineering domain",
            bonus_points=2.0,
            companies=[],
        )
    )
    other_companies: NonTargetPolicy = Field(default_factory=NonTargetPolicy)
    job_families: JobFamilyConfig = Field(default_factory=JobFamilyConfig)
    skills: SkillsConfig = Field(default_factory=SkillsConfig)
    locations: LocationConfig = Field(default_factory=LocationConfig)
    remote_policies: RemotePoliciesConfig = Field(default_factory=RemotePoliciesConfig)
    search_profiles: Dict[str, SearchProfile] = Field(default_factory=dict)

    def get_company_targeting_info(self, company_name: str) -> Optional[Dict[str, Any]]:
        """
        Check if a company is in Tier 1 or Tier 2 targets and return metadata.
        Returns None if company is not explicitly targeted (non-target company).
        """
        if not company_name:
            return None

        comp_norm = company_name.strip().lower()

        # Check Tier 1
        for comp in self.tier_1.companies:
            if comp.name.lower() in comp_norm or comp_norm in comp.name.lower():
                return {
                    "tier": 1,
                    "tier_name": "Tier 1 — Financial Services",
                    "domain_group": self.tier_1.domain_group,
                    "reason": self.tier_1.reason,
                    "bonus_points": self.tier_1.bonus_points,
                    "matched_company": comp.name,
                }

        # Check Tier 2
        for comp in self.tier_2.companies:
            if comp.name.lower() in comp_norm or comp_norm in comp.name.lower():
                return {
                    "tier": 2,
                    "tier_name": "Tier 2 — Technology / Product",
                    "domain_group": self.tier_2.domain_group,
                    "reason": self.tier_2.reason,
                    "bonus_points": self.tier_2.bonus_points,
                    "matched_company": comp.name,
                }

        return None

    def matches_job_family(self, title: str) -> Dict[str, Any]:
        """Check if job title matches configured primary or secondary job families."""
        if not title:
            return {"matched": False, "category": None}

        t_lower = title.lower()

        for fam in self.job_families.primary:
            if fam.lower() in t_lower or any(word in t_lower for word in fam.lower().split() if len(word) > 3):
                return {"matched": True, "category": "primary", "family": fam}

        for fam in self.job_families.secondary:
            if fam.lower() in t_lower or any(word in t_lower for word in fam.lower().split() if len(word) > 3):
                return {"matched": True, "category": "secondary", "family": fam}

        return {"matched": False, "category": None}

    def matches_location(self, loc_str: str) -> Dict[str, Any]:
        """Check location against primary, secondary, international, and remote preferences."""
        if not loc_str:
            return {"matched": True, "category": "unknown"}

        l_lower = loc_str.lower()

        # Check Remote
        if "remote" in l_lower:
            return {"matched": True, "category": "remote", "location": loc_str}

        # Check Primary
        for loc in self.locations.primary:
            if loc.lower() in l_lower:
                return {"matched": True, "category": "primary", "location": loc}

        # Check Secondary
        for loc in self.locations.secondary:
            if loc.lower() in l_lower:
                return {"matched": True, "category": "secondary", "location": loc}

        # Check International
        if self.locations.international.enabled:
            for loc in self.locations.international.locations:
                if loc.lower() in l_lower:
                    return {"matched": True, "category": "international", "location": loc}

        return {"matched": False, "category": "other", "location": loc_str}


def load_job_targets_config(config_path: Optional[Path] = None) -> JobTargetsConfig:
    """Load job targets configuration from YAML file or return robust defaults."""
    target_path = config_path or Path("data/config/job_targets.yaml")
    if not target_path.exists():
        logger.info(f"Job targets config not found at {target_path}, using built-in defaults.")
        return JobTargetsConfig()

    try:
        raw_data = yaml.safe_load(target_path.read_text(encoding="utf-8")) or {}
        tc_data = raw_data.get("target_companies", {})

        t1_data = tc_data.get("tier_1", {})
        t1_comps = [TargetCompany(**c) if isinstance(c, dict) else TargetCompany(name=str(c)) for c in t1_data.get("companies", [])]
        tier_1 = TargetCompanyTier(
            priority_tier=t1_data.get("priority_tier", 1),
            domain_group=t1_data.get("domain_group", "financial_services"),
            reason=t1_data.get("reason", "Strong domain adjacency to candidate's HSBC Payments/Data Platform experience"),
            bonus_points=float(t1_data.get("bonus_points", 5.0)),
            companies=t1_comps,
        )

        t2_data = tc_data.get("tier_2", {})
        t2_comps = [TargetCompany(**c) if isinstance(c, dict) else TargetCompany(name=str(c)) for c in t2_data.get("companies", [])]
        tier_2 = TargetCompanyTier(
            priority_tier=t2_data.get("priority_tier", 2),
            domain_group=t2_data.get("domain_group", "technology_product"),
            reason=t2_data.get("reason", "High-scale product and technology engineering domain"),
            bonus_points=float(t2_data.get("bonus_points", 2.0)),
            companies=t2_comps,
        )

        other_data = tc_data.get("other_companies", {})
        other_policy = NonTargetPolicy(
            allow_non_target_companies=other_data.get("allow_non_target_companies", True),
            default_bonus_points=float(other_data.get("default_bonus_points", 0.0)),
            notes=other_data.get("notes"),
        )

        jf_data = raw_data.get("job_families", {})
        job_families = JobFamilyConfig(
            primary=jf_data.get("primary", []),
            secondary=jf_data.get("secondary", []),
        )

        sk_data = raw_data.get("skills", {})
        skills = SkillsConfig(
            high_priority=sk_data.get("high_priority", []),
            secondary=sk_data.get("secondary", []),
        )

        loc_data = raw_data.get("locations", {})
        intl_data = loc_data.get("international", {})
        intl_cfg = InternationalLocationConfig(
            enabled=intl_data.get("enabled", True),
            locations=intl_data.get("locations", ["Singapore", "Tokyo"]),
        )
        locations = LocationConfig(
            primary=loc_data.get("primary", []),
            secondary=loc_data.get("secondary", []),
            international=intl_cfg,
        )

        rem_data = raw_data.get("remote_policies", {})
        remote_policies = RemotePoliciesConfig(
            supported_modes=rem_data.get("supported_modes", []),
            notes=rem_data.get("notes"),
        )

        sp_data = raw_data.get("search_profiles", {})
        search_profiles = {}
        for sp_k, sp_v in sp_data.items():
            search_profiles[sp_k] = SearchProfile(
                name=sp_v.get("name", sp_k),
                keywords=sp_v.get("keywords", []),
                locations=sp_v.get("locations", []),
            )

        return JobTargetsConfig(
            tier_1=tier_1,
            tier_2=tier_2,
            other_companies=other_policy,
            job_families=job_families,
            skills=skills,
            locations=locations,
            remote_policies=remote_policies,
            search_profiles=search_profiles,
        )
    except Exception as e:
        logger.warning(f"Error reading job_targets config: {e}. Falling back to default configuration.")
        return JobTargetsConfig()

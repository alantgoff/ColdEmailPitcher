"""Module 3 — relevance scoring.

Hybrid: cheap recall filters narrow the universe, then a judge scores six dimensions with
a rationale and citations per dimension (R1.2). Direct portfolio conflicts are
hard-suppressed (R1.5) and the campaign list is capped (R1.1).
"""

from pitchline.targeting.conflicts import (
    ConflictOverrideError,
    apply_portfolio_conflict_suppression,
    override_conflict,
)
from pitchline.targeting.score import score_investor, ScoringSkipped
from pitchline.targeting.prospect import (
    ProspectReport,
    ranked_prospects,
    score_all_firms,
    score_firm,
)
from pitchline.targeting.campaign import (
    CampaignCapExceeded,
    CampaignReport,
    build_campaign,
    ranked_targets,
)

__all__ = [
    "ConflictOverrideError",
    "apply_portfolio_conflict_suppression",
    "override_conflict",
    "score_investor",
    "ScoringSkipped",
    "CampaignCapExceeded",
    "CampaignReport",
    "build_campaign",
    "ranked_targets",
    "ProspectReport",
    "ranked_prospects",
    "score_all_firms",
    "score_firm",
]

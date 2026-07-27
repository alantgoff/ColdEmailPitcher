"""Fit scoring (R1.2): six dimensions, 0-5 each, one-line rationale, cited evidence."""

from __future__ import annotations

from typing import Any

from sqlmodel import Session, select

from pitchline import events
from pitchline.llm import LLMClient, get_client, stamp
from pitchline.models import (
    Campaign,
    EventKind,
    Firm,
    Investor,
    StartupProfile,
    Target,
    TargetStatus,
)
from pitchline.research.store import evidence_payload, research_coverage
from pitchline.rules import MIN_COMPOSITE_FIT_SCORE, MIN_SECTOR_SCORE, MIN_STAGE_SCORE
from pitchline.schemas import FitScoreResult
from pitchline.targeting.conflicts import apply_portfolio_conflict_suppression


class ScoringSkipped(RuntimeError):
    """The investor cannot be scored yet — usually the R1.3 research floor."""


def investor_payload(session: Session, investor: Investor) -> dict[str, Any]:
    firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
    return {
        "full_name": investor.full_name,
        "role": investor.role.value,
        "firm": firm.name if firm else None,
        "stages": investor.stages or (firm.stages if firm else []),
        "sectors": investor.sectors or (firm.sectors if firm else []),
        "check_size_min_usd": investor.check_size_min_usd
        or (firm.check_size_min_usd if firm else None),
        "check_size_max_usd": investor.check_size_max_usd
        or (firm.check_size_max_usd if firm else None),
        "thesis_summary": investor.thesis_summary or (firm.thesis_summary if firm else None),
        "portfolio_companies": (firm.portfolio_companies if firm else []),
        "country": investor.country or (firm.hq_country if firm else None),
        "city": investor.city or (firm.hq_city if firm else None),
    }


def profile_payload(profile: StartupProfile) -> dict[str, Any]:
    return {
        "name": profile.name,
        "one_liner": profile.one_liner,
        "stage": profile.stage.value,
        "sectors": profile.sectors,
        "keywords": profile.keywords,
        "geography": profile.geography,
        "target_check_min_usd": profile.target_check_min_usd,
        "target_check_max_usd": profile.target_check_max_usd,
        "competitors": profile.competitors,
    }


def score_investor(
    session: Session,
    *,
    campaign: Campaign,
    investor: Investor,
    profile: StartupProfile,
    client: LLMClient | None = None,
    require_research_floor: bool = True,
) -> Target:
    """Score one investor and persist a ``Target``. Re-scoring updates in place."""
    client = client or get_client()

    if require_research_floor:
        coverage = research_coverage(session, investor.id)  # type: ignore[arg-type]
        if not coverage.meets_floor:
            raise ScoringSkipped(f"{investor.full_name}: {coverage.reason()} (R1.3)")

    evidence = evidence_payload(session, investor.id)  # type: ignore[arg-type]
    result: FitScoreResult = client.run(
        "fit_score_v1",
        FitScoreResult,
        {
            "profile": profile_payload(profile),
            "investor": investor_payload(session, investor),
            "evidence": evidence,
        },
    )

    valid_ids = {row["id"] for row in evidence}
    target = session.exec(
        select(Target).where(
            Target.campaign_id == campaign.id, Target.investor_id == investor.id
        )
    ).first() or Target(campaign_id=campaign.id, investor_id=investor.id)  # type: ignore[arg-type]

    dims = result.dimensions
    target.stage_score = dims["stage"].score
    target.sector_score = dims["sector"].score
    target.check_size_score = dims["check_size"].score
    target.geography_score = dims["geography"].score
    target.thesis_recency_score = dims["thesis_recency"].score
    target.portfolio_conflict_score = dims["portfolio_conflict"].score
    target.composite_score = result.composite
    target.rationales = {name: dim.rationale for name, dim in dims.items()}
    # Drop hallucinated citations rather than storing an id that resolves to nothing.
    target.dimension_evidence_ids = {
        name: [eid for eid in dim.evidence_ids if eid in valid_ids] for name, dim in dims.items()
    }
    target.evidence_ids = [eid for eid in result.evidence_ids if eid in valid_ids]
    target.has_portfolio_conflict = result.has_conflict
    target.conflict_companies = result.conflict_companies
    target.conflict_evidence_ids = [
        eid for eid in dims["portfolio_conflict"].evidence_ids if eid in valid_ids
    ]
    for key, value in stamp(client, "fit_score_v1").items():
        setattr(target, key, value)

    target.status = _status_for(target)
    session.add(target)
    session.flush()

    apply_portfolio_conflict_suppression(session, target)

    events.record(
        session,
        EventKind.SCORED,
        entity_type="target",
        entity_id=target.id,
        campaign_id=campaign.id,
        summary=f"{investor.full_name}: composite {target.composite_score} -> {target.status.value}",
        payload={"rationales": target.rationales},
        flush=False,
    )
    return target


def _status_for(target: Target) -> TargetStatus:
    """R1.2 — floors on the two dimensions the source names explicitly, plus composite."""
    if target.has_portfolio_conflict and not target.conflict_overridden:
        return TargetStatus.SUPPRESSED_CONFLICT
    if target.stage_score < MIN_STAGE_SCORE:
        return TargetStatus.DROPPED_LOW_FIT
    if target.sector_score < MIN_SECTOR_SCORE:
        return TargetStatus.DROPPED_LOW_FIT
    if target.composite_score < MIN_COMPOSITE_FIT_SCORE:
        return TargetStatus.DROPPED_LOW_FIT
    return TargetStatus.QUALIFIED

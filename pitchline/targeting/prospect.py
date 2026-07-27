"""Firm-level prospecting.

Targeting (``score.py``) answers "should I write to this person?". Prospecting answers a
question that comes *earlier*: "is this fund worth the thirty minutes it takes to find that
person and verify their address?" (R1.3).

The two are kept separate on purpose. A ranked list of firms is not a campaign list, and
collapsing them would let a fund with no resolved contact drift into a send queue — which
is precisely what R1.4 exists to prevent. Prospecting therefore writes ``FirmProspect``
rows, never ``Target`` rows, and nothing downstream of compose can read them.

The research floor is relaxed here, and only here: a prospect score decides where a human
spends thirty minutes, not whether an email goes out. A send still requires the full R1.3
coverage on the *person*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlmodel import Session, select

from pitchline import events
from pitchline.llm import LLMClient, get_client, stamp
from pitchline.models import (
    Campaign,
    Evidence,
    EventKind,
    Firm,
    FirmProspect,
    Investor,
    StartupProfile,
)
from pitchline.rules import MIN_COMPOSITE_FIT_SCORE
from pitchline.schemas import FitScoreResult
from pitchline.targeting.score import profile_payload
from pitchline.timeutil import ensure_utc


@dataclass
class ProspectReport:
    scored: int = 0
    strong: int = 0
    conflicts: int = 0
    contactable: int = 0
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.scored} firms scored -> {self.strong} above the fit floor, "
            f"{self.conflicts} holding a direct competitor, "
            f"{self.contactable} with a resolved contact"
        )


def firm_payload(session: Session, firm: Firm) -> dict[str, Any]:
    """Shape a firm like an investor so the same judge and prompt can score it."""
    return {
        "full_name": firm.name,
        "role": "firm",
        "firm": firm.name,
        "stages": firm.stages,
        "sectors": firm.sectors,
        "check_size_min_usd": firm.check_size_min_usd,
        "check_size_max_usd": firm.check_size_max_usd,
        "thesis_summary": firm.thesis_summary,
        "portfolio_companies": firm.portfolio_companies,
        "country": firm.hq_country,
        "city": firm.hq_city,
    }


def firm_evidence(session: Session, firm_id: int, *, limit: int = 12) -> list[dict[str, Any]]:
    rows = list(session.exec(select(Evidence).where(Evidence.firm_id == firm_id)))
    rows.sort(
        key=lambda r: ensure_utc(r.published_at or r.fetched_at) or ensure_utc(r.fetched_at),
        reverse=True,
    )
    return [
        {
            "id": r.id, "area": r.area.value, "kind": r.kind.value, "title": r.title,
            "url": r.url, "raw_text": r.raw_text[:1200], "entities": r.entities,
            "published_at": (ensure_utc(r.published_at).isoformat() if r.published_at else None),
            "fetched_at": (ensure_utc(r.fetched_at).isoformat() if r.fetched_at else None),
        }
        for r in rows[:limit]
    ]


def score_firm(
    session: Session,
    *,
    campaign: Campaign,
    firm: Firm,
    profile: StartupProfile,
    client: LLMClient | None = None,
) -> FirmProspect:
    client = client or get_client()
    evidence = firm_evidence(session, firm.id)  # type: ignore[arg-type]

    result: FitScoreResult = client.run(
        "fit_score_v1",
        FitScoreResult,
        {
            "profile": profile_payload(profile),
            "investor": firm_payload(session, firm),
            "evidence": evidence,
        },
    )

    prospect = session.exec(
        select(FirmProspect).where(
            FirmProspect.campaign_id == campaign.id, FirmProspect.firm_id == firm.id
        )
    ).first() or FirmProspect(campaign_id=campaign.id, firm_id=firm.id)  # type: ignore[arg-type]

    dims = result.dimensions
    prospect.stage_score = dims["stage"].score
    prospect.sector_score = dims["sector"].score
    prospect.check_size_score = dims["check_size"].score
    prospect.geography_score = dims["geography"].score
    prospect.thesis_recency_score = dims["thesis_recency"].score
    prospect.portfolio_conflict_score = dims["portfolio_conflict"].score
    prospect.composite_score = result.composite
    prospect.rationales = {name: dim.rationale for name, dim in dims.items()}
    prospect.has_portfolio_conflict = result.has_conflict
    prospect.conflict_companies = result.conflict_companies
    prospect.resolved_contacts = len(
        list(
            session.exec(
                select(Investor).where(
                    Investor.firm_id == firm.id,
                    Investor.quarantined == False,  # noqa: E712
                )
            )
        )
    )
    for key, value in stamp(client, "fit_score_v1").items():
        setattr(prospect, key, value)

    session.add(prospect)
    session.flush()
    return prospect


def score_all_firms(
    session: Session,
    *,
    campaign: Campaign,
    profile: StartupProfile,
    client: LLMClient | None = None,
    limit: int | None = None,
) -> ProspectReport:
    client = client or get_client()
    report = ProspectReport()
    firms = list(session.exec(select(Firm)))[: limit or None]

    for firm in firms:
        try:
            prospect = score_firm(
                session, campaign=campaign, firm=firm, profile=profile, client=client
            )
        except Exception as exc:
            report.errors.append(f"{firm.name}: {exc}")
            continue
        report.scored += 1
        if prospect.has_portfolio_conflict:
            report.conflicts += 1
        elif prospect.composite_score >= MIN_COMPOSITE_FIT_SCORE:
            report.strong += 1
        if prospect.resolved_contacts:
            report.contactable += 1

    session.flush()
    events.record(
        session,
        EventKind.SCORED,
        entity_type="campaign",
        entity_id=campaign.id,
        campaign_id=campaign.id,
        summary=report.summary(),
        payload={"errors": report.errors[:10]},
    )
    return report


def ranked_prospects(
    session: Session, campaign_id: int, *, limit: int | None = None, exclude_conflicts: bool = True
) -> list[tuple[FirmProspect, Firm]]:
    statement = select(FirmProspect).where(FirmProspect.campaign_id == campaign_id)
    rows = list(session.exec(statement))
    if exclude_conflicts:
        rows = [r for r in rows if not r.has_portfolio_conflict]
    rows.sort(key=lambda r: -r.composite_score)
    rows = rows[:limit] if limit else rows
    return [(r, session.get(Firm, r.firm_id)) for r in rows]  # type: ignore[misc]

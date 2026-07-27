"""Campaign assembly (R1.1): rank, cap at 400, warn above 250.

The cap is a ceiling, not a goal. ``build_campaign`` will happily return 60 targets and
say so; what it will not do is widen the net to fill the list. If the qualified list comes
in short the fix is the targeting or the pitch, not the volume.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from pitchline import events, suppression
from pitchline.llm import LLMClient, get_client
from pitchline.models import (
    Campaign,
    CampaignStatus,
    EventKind,
    Firm,
    Investor,
    StartupProfile,
    Target,
    TargetStatus,
)
from pitchline.research.store import research_coverage
from pitchline.rules import MAX_CAMPAIGN_TARGETS, MAX_TARGETS_PER_FIRM, WARN_CAMPAIGN_TARGETS
from pitchline.targeting.score import ScoringSkipped, score_investor


class CampaignCapExceeded(RuntimeError):
    """R1.1 — the cap cannot be raised. If the list is too small, fix the targeting."""


@dataclass
class CampaignReport:
    campaign_id: int | None = None
    considered: int = 0
    scored: int = 0
    qualified: int = 0
    dropped_low_fit: int = 0
    suppressed_conflict: int = 0
    suppressed_list: int = 0
    skipped_no_research: int = 0
    capped_out: int = 0
    held_firm_duplicates: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (
            f"{self.considered} considered -> {self.qualified} qualified "
            f"({self.dropped_low_fit} low fit, {self.suppressed_conflict} conflicts, "
            f"{self.suppressed_list} suppressed, {self.skipped_no_research} lacking research, "
            f"{self.held_firm_duplicates} held as firm duplicates, {self.capped_out} over cap)"
        )


def build_campaign(
    session: Session,
    *,
    campaign: Campaign,
    profile: StartupProfile,
    investor_ids: list[int] | None = None,
    client: LLMClient | None = None,
    max_targets: int | None = None,
    require_research_floor: bool = True,
) -> CampaignReport:
    """Score candidate investors into a capped, ranked campaign list."""
    client = client or get_client()
    cap = max_targets if max_targets is not None else campaign.max_targets
    if cap > MAX_CAMPAIGN_TARGETS:
        raise CampaignCapExceeded(
            f"R1.1 caps a campaign at {MAX_CAMPAIGN_TARGETS} targets; requested {cap}. "
            "If the list is too small, fix the targeting — do not widen the net."
        )

    statement = select(Investor).where(
        Investor.quarantined == False,  # noqa: E712 — SQL expression, not a Python bool
        Investor.active == True,  # noqa: E712
    )
    if investor_ids:
        statement = statement.where(Investor.id.in_(investor_ids))  # type: ignore[attr-defined]
    candidates = list(session.exec(statement))

    report = CampaignReport(campaign_id=campaign.id, considered=len(candidates))

    for investor in candidates:
        firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
        hit = suppression.check(session, investor=investor, firm=firm)
        if hit:
            report.suppressed_list += 1
            _mark_suppressed(session, campaign, investor, hit.describe())
            continue

        if require_research_floor:
            coverage = research_coverage(session, investor.id)  # type: ignore[arg-type]
            if not coverage.meets_floor:
                report.skipped_no_research += 1
                continue

        try:
            target = score_investor(
                session,
                campaign=campaign,
                investor=investor,
                profile=profile,
                client=client,
                require_research_floor=False,
            )
        except ScoringSkipped:
            report.skipped_no_research += 1
            continue
        except Exception as exc:
            report.errors.append(f"{investor.full_name}: {exc}")
            continue

        report.scored += 1
        if target.status is TargetStatus.QUALIFIED:
            report.qualified += 1
        elif target.status is TargetStatus.SUPPRESSED_CONFLICT:
            report.suppressed_conflict += 1
        elif target.status is TargetStatus.DROPPED_LOW_FIT:
            report.dropped_low_fit += 1

    report.held_firm_duplicates = _one_per_firm(session, campaign)
    report.qualified -= report.held_firm_duplicates
    report.capped_out = _apply_cap(session, campaign, cap)
    report.qualified -= report.capped_out

    if report.qualified > WARN_CAMPAIGN_TARGETS:
        report.warnings.append(
            f"R1.1: {report.qualified} targets is above the {WARN_CAMPAIGN_TARGETS} warning "
            f"threshold. Volume is not the objective — check that the tail is still relevant."
        )
    if report.qualified == 0:
        report.warnings.append(
            "No qualified targets. Fix the targeting or the evidence coverage; do not widen "
            "the net (R1.1)."
        )

    campaign.status = CampaignStatus.ACTIVE
    session.add(campaign)
    session.flush()
    events.record(
        session,
        EventKind.SCORED,
        entity_type="campaign",
        entity_id=campaign.id,
        campaign_id=campaign.id,
        summary=report.summary(),
        payload={"warnings": report.warnings, "errors": report.errors[:20]},
    )
    return report


def _mark_suppressed(
    session: Session, campaign: Campaign, investor: Investor, reason: str
) -> None:
    target = session.exec(
        select(Target).where(
            Target.campaign_id == campaign.id, Target.investor_id == investor.id
        )
    ).first()
    if target is None:
        target = Target(campaign_id=campaign.id, investor_id=investor.id)  # type: ignore[arg-type]
    target.status = TargetStatus.SUPPRESSED_LIST
    target.suppressed_reason = reason
    session.add(target)
    session.flush()


def _one_per_firm(session: Session, campaign: Campaign) -> int:
    """R1.6 — keep the strongest contact per firm, hold the rest.

    Three partners at one fund receiving three variants of the same email on the same
    morning disproves, to all three at once, the "I am writing to you specifically" claim
    that every one of those emails makes.
    """
    qualified = list(
        session.exec(
            select(Target).where(
                Target.campaign_id == campaign.id, Target.status == TargetStatus.QUALIFIED
            )
        )
    )
    by_firm: dict[int, list[Target]] = {}
    for target in qualified:
        investor = session.get(Investor, target.investor_id)
        if investor is None or investor.firm_id is None:
            continue  # an angel has no firm to collide with
        by_firm.setdefault(investor.firm_id, []).append(target)

    held = 0
    for firm_id, targets in by_firm.items():
        if len(targets) <= MAX_TARGETS_PER_FIRM:
            continue
        # Colleagues at one fund often score identically — the fit signal is the firm's.
        # Break the tie on target id so the same partner wins on every re-run rather than
        # rotating with row order, which would send the firm a second first-touch.
        targets.sort(key=lambda t: (-t.composite_score, t.id or 0))
        for target in targets[MAX_TARGETS_PER_FIRM:]:
            target.status = TargetStatus.HELD_FIRM_DUPLICATE
            target.suppressed_reason = (
                f"R1.6 — a higher-scoring colleague at firm {firm_id} is the active contact"
            )
            session.add(target)
            held += 1
    if held:
        session.flush()
    return held


def _apply_cap(session: Session, campaign: Campaign, cap: int) -> int:
    """Keep the top ``cap`` qualified targets by composite score; demote the rest."""
    qualified = list(
        session.exec(
            select(Target)
            .where(Target.campaign_id == campaign.id, Target.status == TargetStatus.QUALIFIED)
            .order_by(Target.composite_score.desc())  # type: ignore[attr-defined]
        )
    )
    overflow = qualified[cap:]
    for target in overflow:
        target.status = TargetStatus.DROPPED_LOW_FIT
        target.suppressed_reason = f"below the top {cap} by composite fit (R1.1 cap)"
        session.add(target)
    if overflow:
        session.flush()
    return len(overflow)


def ranked_targets(
    session: Session,
    campaign_id: int,
    *,
    statuses: tuple[TargetStatus, ...] = (TargetStatus.QUALIFIED, TargetStatus.IN_SEQUENCE),
    limit: int | None = None,
) -> list[Target]:
    statement = (
        select(Target)
        .where(Target.campaign_id == campaign_id, Target.status.in_(list(statuses)))  # type: ignore[attr-defined]
        .order_by(Target.composite_score.desc())  # type: ignore[attr-defined]
    )
    rows = list(session.exec(statement))
    return rows[:limit] if limit else rows

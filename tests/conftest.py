"""Shared fixtures.

Every test runs against an in-memory SQLite database and the offline heuristic LLM client,
so the suite is deterministic, free, and network-free.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from pitchline import demo, llm
from pitchline.models import (
    Campaign,
    Evidence,
    EvidenceArea,
    EvidenceKind,
    Firm,
    Investor,
    InvestorRole,
    Mailbox,
    SourceType,
    StartupProfile,
    Target,
)
from pitchline.textutil import content_hash, normalize_firm_name, normalize_person_name
from pitchline.timeutil import next_send_window, today_utc, utcnow


@pytest.fixture()
def engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    return engine


@pytest.fixture()
def session(engine) -> Session:
    with Session(engine) as session:
        yield session


@pytest.fixture()
def client():
    """The deterministic offline client, installed as the process default."""
    heuristic = llm.HeuristicClient()
    llm.set_client(heuristic)
    yield heuristic
    llm.set_client(None)


@pytest.fixture()
def profile(session) -> StartupProfile:
    return demo.seed_all(session)


@pytest.fixture()
def campaign(session, profile) -> Campaign:
    campaign = Campaign(name="test", startup_profile_id=profile.id, max_targets=400)
    session.add(campaign)
    session.flush()
    return campaign


@pytest.fixture()
def mailbox(session) -> Mailbox:
    """A fully warmed mailbox: age past the ramp, so the cap is the steady state."""
    from sqlmodel import select

    existing = session.exec(
        select(Mailbox).where(Mailbox.email == "dana@meridian-outreach.com")
    ).first()
    if existing is not None:
        existing.warmup_started_on = today_utc() - timedelta(days=120)
        session.add(existing)
        session.flush()
        return existing

    mailbox = Mailbox(
        email="dana@meridian-outreach.com",
        display_name="Dana Reyes",
        domain="meridian-outreach.com",
        warmup_started_on=today_utc() - timedelta(days=120),
        spf_verified=True,
        dkim_verified=True,
        dmarc_verified=True,
    )
    session.add(mailbox)
    session.flush()
    return mailbox


def make_investor(
    session: Session,
    *,
    name: str = "Ana Okafor",
    firm_name: str = "Northaven Capital",
    email: str | None = None,
    role: InvestorRole = InvestorRole.PARTNER,
    sectors: list[str] | None = None,
    stages: list[str] | None = None,
    timezone: str = "America/New_York",
    portfolio: list[str] | None = None,
) -> Investor:
    firm = Firm(
        name=firm_name,
        name_normalized=normalize_firm_name(firm_name),
        website="https://northaven.vc",
        hq_country="United States",
        hq_city="Boston",
        portfolio_companies=portfolio or ["Corvus Health", "SiteLedger"],
        source=SourceType.CSV_IMPORT,
    )
    session.add(firm)
    session.flush()

    investor = Investor(
        firm_id=firm.id,
        full_name=name,
        name_normalized=normalize_person_name(name),
        role=role,
        is_partner_level=True,
        email=email or f"{name.split()[0].lower()}@northaven.vc",
        email_domain="northaven.vc",
        timezone=timezone,
        country="United States",
        city="Boston",
        stages=stages or ["seed", "series_a"],
        sectors=sectors or ["healthtech", "clinical trials", "b2b saas", "payments"],
        check_size_min_usd=250_000,
        check_size_max_usd=2_000_000,
        thesis_summary=(
            "We back seed-stage healthtech founders rebuilding clinical trial payments and "
            "life sciences financial infrastructure."
        ),
        source=SourceType.CSV_IMPORT,
    )
    session.add(investor)
    session.flush()
    return investor


def add_evidence(
    session: Session,
    investor: Investor,
    *,
    area: EvidenceArea,
    kind: EvidenceKind,
    text: str,
    title: str = "",
    entities: list[str] | None = None,
    published_at: datetime | None = None,
) -> Evidence:
    evidence = Evidence(
        investor_id=investor.id,
        firm_id=investor.firm_id,
        area=area,
        kind=kind,
        title=title or f"{investor.full_name} {area.value}",
        url=f"https://northaven.vc/{area.value}",
        raw_text=text,
        excerpt=text[:400],
        content_hash=content_hash(text),
        entities=entities or [],
        published_at=published_at or (utcnow() - timedelta(days=20)),
        source=SourceType.FUND_SITE,
    )
    session.add(evidence)
    session.flush()
    return evidence


def give_full_research(session: Session, investor: Investor, *, competitor: str | None = None) -> None:
    """Meet the R1.3 floor: portfolio, thesis, and two pieces of recent activity."""
    portfolio = ["Corvus Health", "SiteLedger"] + ([competitor] if competitor else [])
    add_evidence(
        session,
        investor,
        area=EvidenceArea.PORTFOLIO,
        kind=EvidenceKind.PORTFOLIO_COMPANY,
        title="Northaven portfolio",
        text="Portfolio companies on record: " + ", ".join(portfolio) + ".",
        entities=portfolio,
    )
    add_evidence(
        session,
        investor,
        area=EvidenceArea.THESIS,
        kind=EvidenceKind.THESIS_STATEMENT,
        title="clinical trial payments thesis",
        text=(
            "We back seed-stage healthtech companies rebuilding clinical trial payments, site "
            "operations and life sciences financial infrastructure."
        ),
    )
    add_evidence(
        session,
        investor,
        area=EvidenceArea.RECENT_ACTIVITY,
        kind=EvidenceKind.INVESTMENT,
        title="recent investments",
        text="Recent investments on record: Corvus Health, SiteLedger.",
        entities=["Corvus Health", "SiteLedger"],
    )
    add_evidence(
        session,
        investor,
        area=EvidenceArea.RECENT_ACTIVITY,
        kind=EvidenceKind.BLOG_POST,
        title="why site payments break",
        text=(
            "Wrote about why site-level cost data never reaches the sponsor finance team in time, "
            "and what that does to trial timelines."
        ),
    )


def make_target(
    session: Session, campaign: Campaign, investor: Investor, *, qualified: bool = True
) -> Target:
    from pitchline.models import TargetStatus

    target = Target(
        campaign_id=campaign.id,
        investor_id=investor.id,
        stage_score=5,
        sector_score=5,
        check_size_score=5,
        geography_score=5,
        thesis_recency_score=5,
        portfolio_conflict_score=5,
        composite_score=5.0,
        rationales={"stage": "invests at seed"},
        status=TargetStatus.QUALIFIED if qualified else TargetStatus.SCORED,
        cohort="healthtech-seed",
    )
    session.add(target)
    session.flush()
    return target


def a_valid_send_time() -> datetime:
    """A UTC instant inside the R4.5 window for America/New_York."""
    moment = next_send_window(utcnow(), "America/New_York")
    assert moment is not None
    return moment

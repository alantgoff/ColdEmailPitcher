"""Demo seed data — a complete, runnable founder setup.

This is scaffolding for a first run, not a template to send. Everything here is meant to be
replaced by the founder's own copy: the credibility markers must be *their* credibility, the
problem and approach variants must be *their* words. What it demonstrates is the shape —
four slots, registered markers, dated updates, a warmed mailbox on a dedicated domain.
"""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from pitchline.models import (
    Mailbox,
    PitchVariant,
    SlotKind,
    Stage,
    StartupProfile,
    Update,
)
from pitchline.timeutil import today_utc, utcnow

DEMO_PROFILE_NAME = "Meridian"

CREDIBILITY_VARIANTS = [
    (
        "cred_prior_ops",
        "prior_company",
        "prior_company",
        "I spent six years running clinical operations at a CRO that paid 400 trial sites a month.",
    ),
    (
        "cred_traction",
        "traction_metric",
        "traction_metric",
        "We move $2.1M a month in clinical trial site payments across 34 sites.",
    ),
    (
        "cred_customers",
        "named_customer",
        "named_customer",
        "Two academic medical centres run their trial payments on us today.",
    ),
    (
        "cred_domain",
        "domain_expertise",
        "domain_expertise",
        "I have spent nine years inside clinical trial finance, most of it fixing site payments.",
    ),
]

PROBLEM_VARIANTS = [
    (
        "problem_payment_lag",
        "site payment lag",
        "Clinical trial sites wait an average of 87 days to be paid for visits they have already "
        "completed, and roughly 1 in 5 sites leaves a study citing cash flow.",
    ),
    (
        "problem_reconciliation",
        "manual reconciliation",
        "Trial budgets live in PDFs, so sponsors reconcile site invoices by hand and a mid-size "
        "study burns 30 finance hours a month before anyone is paid.",
    ),
    (
        "problem_site_dropout",
        "site dropout economics",
        "Replacing a trial site that quits costs a sponsor about $40,000 and six weeks, and payment "
        "delay is the reason sites give most often.",
    ),
]

APPROACH_VARIANTS = [
    (
        "approach_contract_parse",
        "contract to payment triggers",
        "We parse the executed site contract into machine-readable payment triggers, then release "
        "payment when the EDC records the visit.",
    ),
    (
        "approach_milestone_ledger",
        "visit-level ledger",
        "We keep a visit-level ledger per site, so a sponsor sees exactly what is owed the day a "
        "patient is seen rather than at quarter close.",
    ),
    (
        "approach_direct_rails",
        "direct payment rails",
        "We pay sites directly from an escrowed study account, which removes the sponsor finance "
        "queue from the critical path entirely.",
    ),
]

ASK_VARIANTS = [
    ("ask_share_more", "offer_to_share_more", "Worth me sending a short summary?"),
    ("ask_deck", "deck_offer", "Happy to send the deck if that is easier."),
    (
        "ask_quick_call",
        "quick_call_in_next_week_or_two",
        "Open to a quick call in the next week or two if this is relevant.",
    ),
]

UPDATES = [
    (
        "Second AMC live",
        "A second academic medical centre went live last week, taking us to 34 sites and $2.1M a "
        "month in payment volume.",
        "traction",
        7,
    ),
    (
        "Payment lag down to 9 days",
        "Median time from completed visit to site payment across our sites is now 9 days, against "
        "an industry average of 87.",
        "metric",
        21,
    ),
    (
        "Former Parexel finance lead joined",
        "Our new head of operations ran site payments for a top-five CRO for eleven years.",
        "team",
        35,
    ),
]


def seed_profile(session: Session) -> StartupProfile:
    existing = session.exec(
        select(StartupProfile).where(StartupProfile.name == DEMO_PROFILE_NAME)
    ).first()
    if existing:
        return existing

    profile = StartupProfile(
        name=DEMO_PROFILE_NAME,
        one_liner="Meridian pays clinical trial sites the week they see a patient, not the quarter after.",
        stage=Stage.SEED,
        sectors=["healthtech", "clinical trials", "fintech", "b2b saas", "payments"],
        keywords=[
            "clinical trials", "site payments", "healthcare", "life sciences", "digital health",
            "payments infrastructure", "vertical saas", "pharma", "CRO", "reconciliation",
        ],
        geography="united states",
        raising_usd=4_000_000,
        target_check_min_usd=250_000,
        target_check_max_usd=2_000_000,
        # R1.5 — matched against portfolio evidence to detect direct conflicts.
        competitors=["Greenphire", "Mural Health", "Paylode Health", "TrialPay Sciences"],
        credibility_markers=[
            {"type": kind, "label": label, "text": text}
            for _, label, kind, text in CREDIBILITY_VARIANTS
        ],
        founder_name="Dana Reyes",
        founder_email="dana@meridiantrials.com",
        reply_to_email="dana@meridiantrials.com",
        deck_url="https://meridiantrials.com/deck",
        calendar_url="https://cal.com/meridian/intro",
        postal_address="Meridian Health Systems Inc., 2 Canal Park, Cambridge MA 02141",
        optout_instruction="Reply 'unsubscribe' and I will not contact you again.",
    )
    session.add(profile)
    session.flush()
    return profile


def seed_library(session: Session, profile: StartupProfile) -> int:
    created = 0
    existing = {(v.slot, v.key) for v in session.exec(select(PitchVariant))}

    def add(slot: SlotKind, key: str, label: str, text: str, **kwargs) -> None:
        nonlocal created
        if (slot, key) in existing:
            return
        session.add(
            PitchVariant(
                startup_profile_id=profile.id,
                slot=slot,
                key=key,
                label=label,
                body_text=text,
                sectors=profile.sectors,
                stages=[profile.stage.value],
                **kwargs,
            )
        )
        created += 1

    for key, label, marker_type, text in CREDIBILITY_VARIANTS:
        add(SlotKind.CREDIBILITY, key, label, text, marker_type=marker_type)
    for key, label, text in PROBLEM_VARIANTS:
        add(SlotKind.PROBLEM, key, label, text)
    for key, label, text in APPROACH_VARIANTS:
        add(SlotKind.APPROACH, key, label, text)
    for key, ask_type, text in ASK_VARIANTS:
        add(SlotKind.ASK, key, ask_type.replace("_", " "), text, ask_type=ask_type)

    session.flush()
    return created


def seed_updates(session: Session, profile: StartupProfile) -> int:
    created = 0
    existing = {u.headline for u in session.exec(select(Update))}
    for headline, body, category, days_ago in UPDATES:
        if headline in existing:
            continue
        session.add(
            Update(
                startup_profile_id=profile.id,
                headline=headline,
                body_text=body,
                category=category,
                occurred_on=today_utc() - timedelta(days=days_ago),
            )
        )
        created += 1
    session.flush()
    return created


def seed_mailboxes(session: Session, *, count: int = 2, warmed_days: int = 45) -> int:
    """R3.2/R3.3 — dedicated secondary domain, already through the warmup ramp."""
    created = 0
    existing = {m.email for m in session.exec(select(Mailbox))}
    for index in range(1, count + 1):
        email = f"dana{'' if index == 1 else index}@meridian-outreach.com"
        if email in existing:
            continue
        session.add(
            Mailbox(
                email=email,
                display_name="Dana Reyes",
                domain="meridian-outreach.com",
                warmup_started_on=today_utc() - timedelta(days=warmed_days),
                spf_verified=True,
                dkim_verified=True,
                dmarc_verified=True,
            )
        )
        created += 1
    session.flush()
    return created


def seed_all(session: Session, *, mailboxes: int = 2) -> StartupProfile:
    profile = seed_profile(session)
    seed_library(session, profile)
    seed_updates(session, profile)
    seed_mailboxes(session, count=mailboxes)
    return profile

"""Prime After Dark — Miami premium late-night delivery, $2.5M seed round.

Every claim below comes from the founder's investor deck (Prime After Dark LLC, 2026).
Nothing here is invented by the engine: the credibility markers are the founder's
credibility, the problem and approach text is the founder's framing, and the figures are
the founder's figures.

Two things to fix before a live send:

1. ``UPDATES`` carry the deck's traction language, which is qualitative ("LOIs in
   progress", "rapidly growing waitlist"). R4.3 exists because a follow-up needs *new
   information*, and a follow-up that says "things are going well" is the bump this system
   refuses to send. Replace each with a dated, numeric version — a signed LOI with a named
   counterparty, a waitlist number, a soft-launch order count and repeat rate.
2. ``cred_soft_launch`` and ``cred_hotel_lois`` are the two markers a Miami investor will
   test first. They are the strongest markers here *if* they carry a number, and the
   weakest if they do not.
"""

from __future__ import annotations

from datetime import timedelta

from sqlmodel import Session, select

from pitchline.models import Mailbox, PitchVariant, SlotKind, Stage, StartupProfile, Update
from pitchline.timeutil import today_utc

COMPANY = "Prime After Dark"

#: R2.3 — the registered credibility marker set. One of these opens every email.
CREDIBILITY_VARIANTS = [
    (
        "cred_nyc_ops",
        "NYC restaurant operations",
        "prior_company",
        "I ran high-volume restaurant operations in New York before starting Prime After Dark.",
    ),
    (
        "cred_kitchen_team",
        "premium kitchen team",
        "domain_expertise",
        "Our operating team comes out of New York premium kitchens, not out of a delivery app.",
    ),
    (
        "cred_hotel_lois",
        "Brickell hotel and corporate LOIs",
        "named_customer",
        "We have letters of intent in progress with a major Brickell hotel and corporate partners.",
    ),
    (
        "cred_soft_launch",
        "soft launch validation",
        "traction_metric",
        "Our Brickell soft launch confirmed real demand for premium food after midnight.",
    ),
    (
        "cred_advisors",
        "Miami hospitality advisors",
        "notable_advisor",
        "Our advisors scale ghost kitchens and run hospitality logistics in Miami.",
    ),
]

#: R2.2 — the problem, always before the solution. Straight from the deck's problem slide.
PROBLEM_VARIANTS = [
    (
        "problem_dark_kitchens",
        "restaurants go dark at peak",
        "Every top Miami restaurant is dark before midnight, which is exactly when the city's "
        "nightlife peaks.",
    ),
    (
        "problem_quality_gap",
        "the 70,000-resident quality gap",
        "After midnight, 70,000+ high-income Brickell residents choose between fast food and "
        "inconsistent ghost kitchens.",
    ),
    (
        "problem_open_daypart",
        "fastest-growing daypart, unserved",
        "Late night is the fastest-growing daypart in food delivery, up 7.5% year over year, and "
        "no premium operator serves it.",
    ),
]

#: R2.4 — the novel approach. What makes this not the tenth ghost-kitchen pitch of the week.
APPROACH_VARIANTS = [
    (
        "approach_night_only",
        "12AM-4:30AM only",
        "We operate only from 12AM to 4:30AM, so we own the window when every premium competitor "
        "is closed.",
    ),
    (
        "approach_delivery_engineered",
        "engineered for the ride",
        "Recipes and packaging are engineered for delivery, so a steakhouse-quality protein still "
        "arrives intact at 2AM.",
    ),
    (
        "approach_zero_capex",
        "zero restaurant capex",
        "We run out of ghost kitchens with no restaurant capex, so each new corridor launches in "
        "weeks rather than quarters.",
    ),
]

#: R2.5 — low-commitment asks only. A deck request is the expected modal positive.
ASK_VARIANTS = [
    ("ask_share_more", "offer_to_share_more", "Worth me sending a one-page summary?"),
    ("ask_deck", "deck_offer", "Happy to send the deck if that is useful."),
    (
        "ask_quick_call",
        "quick_call_in_next_week_or_two",
        "Open to a short call in the next week or two if this is relevant.",
    ),
]

#: R4.3 — follow-up payloads. REPLACE THESE with dated, numeric versions before sending.
#: As written they carry the deck's qualitative traction language, which makes for a weak
#: follow-up even though it passes the gate.
UPDATES = [
    (
        "Brickell hotel LOI",
        "Our first Brickell hotel letter of intent is in progress, alongside two corporate "
        "partners, for in-room late-night delivery.",
        "partnership",
        5,
    ),
    (
        "Pre-launch waitlist",
        "The pre-launch waitlist is still growing without any paid acquisition behind it.",
        "traction",
        18,
    ),
    (
        "Soft launch results",
        "Soft launch data confirmed demand for premium delivery inside the 12AM to 4:30AM window.",
        "metric",
        32,
    ),
]

#: R1.5 — a fund holding one of these is suppressed unless a named human overrides.
#: DoorDash and Uber are deliberately absent: they are distribution partners in the deck's
#: own business model, not competitors, and suppressing their investors would cost the
#: campaign its most relevant audience.
COMPETITORS = [
    "CloudKitchens",
    "Cloud Kitchens",
    # Surfaced by the first prospecting run: a16z and Founders Fund ranked top on fit and
    # both hold ghost-kitchen operators. A conflict list is never finished — it grows every
    # time the ranking puts a fund at the top for the wrong reason.
    "Virtual Kitchen Co",
    "All Day Kitchens",
    "Foodology",
    "Ghost Kitchen Brands",
    "REEF Technology",
    "Reef Kitchens",
    "Kitchen United",
    "Nextbite",
    "Ordermark",
    "Local Kitchens",
    "Zuul Kitchens",
    "Virtual Dining Concepts",
    "Creating Culinary Communities",
    "Franklin Junction",
    "Butler Hospitality",
    "Wonder",
    "Salted",
    "Kitopi",
    "Karma Kitchen",
]

SECTORS = [
    "food delivery",
    "ghost kitchens",
    "virtual restaurants",
    "hospitality",
    "consumer",
    "food and beverage",
    "restaurant technology",
]

#: Sector language only. Place names deliberately excluded: geography is scored on its own
#: dimension (R1.2), and leaving "miami" in here double-counts it into the sector score —
#: which ranks a generalist Miami fund above a food specialist in New York.
KEYWORDS = [
    "late night", "delivery", "ghost kitchen", "cloud kitchen", "virtual brand", "restaurant",
    "restaurants", "hospitality", "nightlife", "food", "beverage", "foodservice",
    "consumer brand", "qsr", "fast casual", "multi unit", "franchise", "last mile",
    "dtc food", "cpg", "culinary", "kitchen", "dining", "menu", "premium",
]


def seed_profile(session: Session) -> StartupProfile:
    existing = session.exec(
        select(StartupProfile).where(StartupProfile.name == COMPANY)
    ).first()
    if existing:
        return existing

    profile = StartupProfile(
        name=COMPANY,
        one_liner=(
            "Prime After Dark is Miami's premium food delivery brand built exclusively for "
            "midnight to 4:30AM."
        ),
        # Institutional seed. The deck cover still reads "Friends & Family Round" — that
        # needs updating before it goes to a fund, because a VC reads the mismatch as
        # either a stale deck or a round that failed to fill.
        stage=Stage.SEED,
        sectors=SECTORS,
        keywords=KEYWORDS,
        geography="miami",
        raising_usd=2_500_000,
        # A $2.5M seed: a lead writes $1M-$1.5M, the rest fill $250k-$750k.
        target_check_min_usd=250_000,
        target_check_max_usd=2_000_000,
        competitors=COMPETITORS,
        credibility_markers=[
            {"type": marker_type, "label": label, "text": text}
            for _, label, marker_type, text in CREDIBILITY_VARIANTS
        ],
        founder_name="Josh",
        founder_email="josh@primeafterdark.com",
        reply_to_email="josh@primeafterdark.com",
        deck_url="https://primeafterdark.com/deck",
        calendar_url="https://cal.com/primeafterdark/intro",
        # R5.1 — CAN-SPAM requires a real, current postal address. Replace before sending.
        postal_address="Prime After Dark LLC, [street address], Miami, FL [ZIP]",
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
                stages=[profile.stage.value, "pre_seed", "series_a"],
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


def seed_mailboxes(session: Session, *, count: int = 2, warmed_days: int = 0) -> int:
    """R3.2/R3.3 — a dedicated secondary domain, not the company's primary.

    ``warmed_days`` defaults to 0: a new domain starts at the bottom of the warmup ramp
    (5 sends a day), and claiming otherwise would let the engine spend reputation the
    domain has not earned.
    """
    created = 0
    existing = {m.email for m in session.exec(select(Mailbox))}
    for index in range(1, count + 1):
        email = f"josh{'' if index == 1 else index}@primeafterdark-outreach.com"
        if email in existing:
            continue
        session.add(
            Mailbox(
                email=email,
                display_name="Josh — Prime After Dark",
                domain="primeafterdark-outreach.com",
                warmup_started_on=today_utc() - timedelta(days=warmed_days),
                notes="Set spf/dkim/dmarc verified once DNS is confirmed (R3.2).",
            )
        )
        created += 1
    session.flush()
    return created


def seed_all(session: Session, *, mailboxes: int = 2, warmed_days: int = 0) -> StartupProfile:
    profile = seed_profile(session)
    seed_library(session, profile)
    seed_updates(session, profile)
    seed_mailboxes(session, count=mailboxes, warmed_days=warmed_days)
    return profile

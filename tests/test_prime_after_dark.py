"""Prime After Dark: the profile pack, and the guardrail bugs its copy exposed.

A late-night delivery brand is a good adversarial test of this engine, because its pitch
is *about* times of day and its competitor list contains ordinary English words. Both of
those broke checks that looked fine against a B2B healthcare pack.
"""

from __future__ import annotations

import pytest
from sqlmodel import select

from pitchline import profiles
from pitchline.compose import compose_first_touch, generate_followup, plan_sequence
from pitchline.guardrails import lint_draft
from pitchline.llm import _detect_conflicts
from pitchline.models import (
    Campaign,
    EvidenceArea,
    EvidenceKind,
    GuardrailCode,
    InvestorRole,
    PitchVariant,
    SlotKind,
    Stage,
    Update,
)
from pitchline.profiles import prime_after_dark as pad
from pitchline.rules import ALLOWED_ASK_TYPES, CREDIBILITY_MARKER_TYPES, MAX_PITCH_WORDS
from pitchline.targeting import score_investor
from tests.conftest import add_evidence, make_investor, make_target

REAL_ADDRESS = "Prime After Dark LLC, 1 Example Way, Miami, FL 33131"


@pytest.fixture()
def pad_profile(session):
    profile = profiles.seed("prime-after-dark", session)
    # The shipped pack deliberately carries a placeholder; a live send needs a real one.
    profile.postal_address = REAL_ADDRESS
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture()
def food_investor(session):
    investor = make_investor(
        session,
        name="Sofia Chen",
        firm_name="Highgate Capital",
        sectors=["food and beverage", "restaurant tech", "consumer", "hospitality"],
        stages=["pre_seed", "seed"],
        portfolio=["Nocturne Hospitality", "Late Plate"],
    )
    investor.thesis_summary = (
        "We back consumer food and beverage brands at pre-seed and seed, with a strong "
        "preference for operators who have actually run kitchens."
    )
    investor.city = "Miami"
    investor.check_size_min_usd = 50_000
    investor.check_size_max_usd = 500_000
    session.add(investor)
    session.flush()

    add_evidence(
        session, investor, area=EvidenceArea.PORTFOLIO, kind=EvidenceKind.PORTFOLIO_COMPANY,
        title="Highgate portfolio",
        text="Portfolio companies on record: Nocturne Hospitality, Late Plate.",
        entities=["Nocturne Hospitality", "Late Plate"],
    )
    add_evidence(
        session, investor, area=EvidenceArea.THESIS, kind=EvidenceKind.THESIS_STATEMENT,
        title="consumer food thesis", text=investor.thesis_summary,
    )
    add_evidence(
        session, investor, area=EvidenceArea.RECENT_ACTIVITY, kind=EvidenceKind.INVESTMENT,
        title="recent investments", text="Recent investments on record: Late Plate.",
        entities=["Late Plate"],
    )
    add_evidence(
        session, investor, area=EvidenceArea.RECENT_ACTIVITY, kind=EvidenceKind.BLOG_POST,
        title="late night daypart",
        text="Wrote about why late night is the only daypart still growing for restaurants.",
    )
    return investor


# --------------------------------------------------------------------------------------
# The pack
# --------------------------------------------------------------------------------------


def test_the_pack_seeds_a_complete_founder_setup(session, pad_profile):
    assert pad_profile.stage is Stage.PRE_SEED, "a friends & family round is pre-seed"
    assert pad_profile.raising_usd == 2_500_000
    assert pad_profile.geography == "miami"

    variants = list(session.exec(select(PitchVariant)))
    by_slot = {slot: [v for v in variants if v.slot is slot] for slot in SlotKind}
    assert len(by_slot[SlotKind.CREDIBILITY]) >= 4
    assert len(by_slot[SlotKind.PROBLEM]) >= 3
    assert len(by_slot[SlotKind.APPROACH]) >= 3
    assert len(by_slot[SlotKind.ASK]) >= 3

    assert all(v.marker_type in CREDIBILITY_MARKER_TYPES for v in by_slot[SlotKind.CREDIBILITY])
    assert all(v.ask_type in ALLOWED_ASK_TYPES for v in by_slot[SlotKind.ASK])
    assert len(list(session.exec(select(Update)))) >= 3


def test_delivery_platforms_are_partners_not_competitors(pad_profile):
    """Suppressing DoorDash and Uber investors would remove the best-fit audience."""
    lowered = [c.lower() for c in pad_profile.competitors]
    assert "doordash" not in lowered and "uber" not in lowered and "ubereats" not in lowered
    assert "CloudKitchens" in pad_profile.competitors


def test_a_new_domain_starts_at_the_bottom_of_the_warmup_ramp(session, pad_profile):
    from pitchline.models import Mailbox
    from pitchline.rules import STEADY_STATE_DAILY_CAP, WARMUP_DAILY_CAPS
    from pitchline.send.budget import ReputationBudget

    mailbox = session.exec(select(Mailbox)).first()
    budget = ReputationBudget(session, mailbox)

    assert budget.cap == WARMUP_DAILY_CAPS[0]
    assert budget.cap < STEADY_STATE_DAILY_CAP


def test_the_pack_composes_a_draft_that_clears_every_gate(
    session, pad_profile, food_investor, client
):
    campaign = Campaign(name="pad-ff", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()

    target = score_investor(
        session, campaign=campaign, investor=food_investor, profile=pad_profile
    )
    assert target.status.value == "qualified"

    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)
    report = lint_draft(session, draft, profile=pad_profile)

    assert report.passed, report.describe()
    assert draft.word_count <= MAX_PITCH_WORDS
    assert draft.novelty_score >= 4.0
    assert "Prime After Dark" in draft.subject
    assert REAL_ADDRESS in draft.footer


def test_a_followup_carries_one_of_the_packs_updates(
    session, pad_profile, food_investor, client, mailbox
):
    from pitchline import approval
    from pitchline.send import Sender
    from pitchline.send.transport import DryRunTransport
    from tests.conftest import a_valid_send_time

    campaign = Campaign(name="pad-ff", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)

    first = compose_first_touch(session, target=target, profile=pad_profile)
    approval.approve(session, first, approved_by="Josh")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        first, mailbox=mailbox, now=a_valid_send_time()
    )

    followup = generate_followup(session, target=target, profile=pad_profile, touch_number=2)

    assert followup.update_id is not None
    update = session.get(Update, followup.update_id)
    assert update.headline in {h for h, _, _, _ in pad.UPDATES}
    assert lint_draft(session, followup, profile=pad_profile).passed


# --------------------------------------------------------------------------------------
# Bugs this pack exposed
# --------------------------------------------------------------------------------------


def test_a_time_of_day_product_claim_is_not_a_meeting_request(
    session, pad_profile, food_investor, client
):
    """R2.5 forbids asking for a slot, not mentioning a time.

    "arrives intact at 2AM" and "12AM to 4:30AM" are the product. Failing them would make
    the engine unusable for any company whose pitch involves a clock.
    """
    campaign = Campaign(name="pad-ff", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)

    draft.body = (
        "I ran high-volume restaurant operations in New York before starting Prime After Dark. "
        + (draft.personalization_hook or "")
        + "\n\nWe operate only from 12AM to 4:30AM, so we own the window when every premium "
        "competitor is closed.\n\nRecipes are engineered for delivery, so a steakhouse protein "
        "arrives intact at 2AM.\n\nHappy to send the deck if that is useful."
    )
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=pad_profile)

    assert not report.has(GuardrailCode.ASK_TYPE), report.describe()


def test_a_hard_scheduled_meeting_is_still_rejected(session, pad_profile, food_investor, client):
    campaign = Campaign(name="pad-ff", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)

    for ask in (
        "Can we meet at your office next Tuesday at 3 PM?",
        "I have booked Thursday at 9am for us.",
        "Are you free Wednesday at 4pm?",
    ):
        draft.body = f"{draft.body}\n\n{ask}"
        assert lint_draft(session, draft, profile=pad_profile).has(GuardrailCode.ASK_TYPE), ask
        draft.body = draft.body.rsplit("\n\n", 1)[0]


def test_a_placeholder_postal_address_is_rejected(session, pad_profile, food_investor, client):
    """CAN-SPAM needs a real address; "[street address]" satisfies a substring check only."""
    campaign = Campaign(name="pad-ff", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)
    assert lint_draft(session, draft, profile=pad_profile).passed

    pad_profile.postal_address = "Prime After Dark LLC, [street address], Miami, FL [ZIP]"
    session.add(pad_profile)
    session.flush()

    report = lint_draft(session, draft, profile=pad_profile)

    assert report.has(GuardrailCode.FOOTER)
    assert any("placeholder" in f.detail for f in report.failures)


def test_the_shipped_pack_refuses_to_send_until_the_address_is_filled(session, client):
    """The pack ships with a placeholder on purpose — that failure is the reminder."""
    profile = profiles.seed("prime-after-dark", session)
    assert "[" in profile.postal_address


def test_competitor_matching_does_not_fire_on_ordinary_words(pad_profile):
    """"Wonder" and "Salted" are real companies AND ordinary words.

    Case-insensitive matching would suppress a good investor because a blog post contained
    the word "wonder" — a silent false suppression nobody would ever notice.
    """
    profile_payload = {"competitors": pad_profile.competitors}
    evidence = [
        {
            "id": 1,
            "area": "portfolio",
            "kind": "portfolio_company",
            "title": "thoughts",
            "raw_text": "You have to wonder whether ghost kitchens ever had unit economics.",
            "entities": [],
        }
    ]

    found, _ = _detect_conflicts(profile_payload, {"portfolio_companies": []}, evidence)

    assert found == []


def test_a_real_competitor_holding_is_still_detected(pad_profile):
    profile_payload = {"competitors": pad_profile.competitors}
    evidence = [
        {
            "id": 2,
            "area": "portfolio",
            "kind": "portfolio_company",
            "title": "portfolio",
            "raw_text": "Portfolio companies on record: CloudKitchens, Late Plate.",
            "entities": ["CloudKitchens", "Late Plate"],
        }
    ]

    found, ids = _detect_conflicts(profile_payload, {"portfolio_companies": []}, evidence)

    assert "CloudKitchens" in found
    assert ids == [2]


def test_angels_are_inside_the_campaign_universe(session):
    """R1.4 — for a friends & family round the angel *is* the decision-maker."""
    from pitchline.ingest import parse_role
    from pitchline.rules import is_partner_level

    assert parse_role("Angel Investor") is InvestorRole.ANGEL
    assert is_partner_level("angel") is True
    assert is_partner_level("associate") is False

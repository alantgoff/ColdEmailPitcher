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
        stages=["seed", "series_a"],
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
    assert pad_profile.stage is Stage.SEED, "raising an institutional seed, not F&F"
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

    # The pack's shipped updates carry the deck's qualitative traction language and no
    # figures, so R2.4 refuses them. That is the software making the point the README
    # makes in prose: a follow-up that says "things are going well" is not new information.
    from pitchline.compose.pitch import HumanFixRequired

    with pytest.raises(HumanFixRequired):
        generate_followup(session, target=target, profile=pad_profile, touch_number=2)

    # Give the same update a real number and the same follow-up goes through.
    for update in session.exec(select(Update)):
        update.body_text = (
            "The Brickell hotel LOI is signed and two corporate partners are live, taking "
            "us to 34 delivery nights a month."
        )
        update.consumed_by_draft_id = None
        session.add(update)
    session.flush()

    followup = generate_followup(session, target=target, profile=pad_profile, touch_number=2)

    assert followup.update_id is not None
    assert session.get(Update, followup.update_id).consumed_by_draft_id == followup.id
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


def test_the_founder_of_a_fund_is_partner_level(session):
    """R1.4 — "Founder" at an investment firm is the most senior investing role there is.

    Treating it as unresolvable quarantined eight of the strongest contacts on the real
    list, including the founders of Cleveland Avenue, Forerunner and Boulder Food Group.
    """
    from pitchline.ingest import parse_role
    from pitchline.rules import is_partner_level

    for title in ("Founder", "Co-Founder", "CEO", "Chief Executive Officer", "Founding Partner"):
        role = parse_role(title)
        assert is_partner_level(role.value), f"{title!r} resolved to {role.value}"

    # Non-investing functions still stay out.
    for title in ("Head of Platform", "Chief of Staff", "Analyst", "Senior Associate"):
        assert not is_partner_level(parse_role(title).value), title


def test_angels_are_inside_the_campaign_universe(session):
    """R1.4 — angels co-invest in seed rounds and decide for themselves."""
    from pitchline.ingest import parse_role
    from pitchline.rules import is_partner_level

    assert parse_role("Angel Investor") is InvestorRole.ANGEL
    assert is_partner_level("angel") is True
    assert is_partner_level("associate") is False


# --------------------------------------------------------------------------------------
# R2.4 — the gate has to fire on the failure mode it was built for
# --------------------------------------------------------------------------------------


def test_the_novelty_gate_rejects_a_generic_pitch(client):
    """The missing test that let a broken gate ship.

    The first scorer only matched cliche phrases, so a pitch with no cliches and no
    content scored a perfect 5 — exactly the email the source says gets ignored. Every
    assertion here is about a draft that contains no cliche at all.
    """
    from pitchline.rules import MIN_NOVELTY_SCORE
    from pitchline.schemas import NoveltyVerdict

    def score(body: str) -> float:
        return client.run(
            "novelty_v1", NoveltyVerdict,
            {"subject": "Prime After Dark", "body": body,
             "has_personalization_hook": True, "has_specific_problem": True},
        ).score

    generic = (
        "We are building the future of food delivery. Our platform connects hungry "
        "customers with great restaurants. We have grown 40% month over month."
    )
    boilerplate = (
        "We are a technology company building innovative solutions for the modern "
        "consumer. Our team has 20 years of combined experience."
    )
    specific = (
        "Our operating team comes out of New York premium kitchens, not out of a delivery "
        "app. Late night is the fastest-growing daypart in food delivery, up 7.5% year "
        "over year. We operate only from 12AM to 4:30AM, so we own the window when every "
        "premium competitor is closed."
    )

    assert score(generic) < MIN_NOVELTY_SCORE, "a category pitch must not clear the gate"
    assert score(boilerplate) < MIN_NOVELTY_SCORE, "abstraction must not clear the gate"
    assert score(specific) >= MIN_NOVELTY_SCORE, "a specific, quantified pitch must clear it"
    assert score(specific) > score(generic) + 2, "the gate must separate them decisively"


def test_novelty_rewards_quantified_facts_not_bare_digits(client):
    """"raising 2M" is not specificity; "87 days" is."""
    from pitchline.schemas import NoveltyVerdict

    def score(body: str) -> float:
        return client.run("novelty_v1", NoveltyVerdict,
                          {"subject": "x", "body": body}).score

    bare = "We have 4 things and 12 other things and 7 more things in our platform."
    real = "Sites wait 87 days to be paid and 1 in 5 leave, costing sponsors $40,000 each."
    assert score(real) > score(bare)


# --------------------------------------------------------------------------------------
# Contact quality — the gate that protects the sending domain
# --------------------------------------------------------------------------------------


def test_an_unverified_address_is_refused_on_a_live_send(
    session, pad_profile, food_investor, client, mailbox
):
    """A guessed address bounces, and bounces cost every *other* recipient on the list."""
    from dataclasses import dataclass, field
    from email.message import EmailMessage

    from pitchline import approval
    from pitchline.models import EmailConfidence
    from pitchline.send import Sender, UnverifiedRecipientError
    from pitchline.send.transport import Delivery
    from tests.conftest import a_valid_send_time

    @dataclass
    class FakeLive:
        name: str = "fake_live"
        live: bool = True
        outbox: list = field(default_factory=list)

        def deliver(self, message: EmailMessage) -> Delivery:
            self.outbox.append(message)
            return Delivery(provider_message_id="x")

    campaign = Campaign(name="pad-seed", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)
    approval.approve(session, draft, approved_by="Josh")

    food_investor.email_confidence = EmailConfidence.UNKNOWN
    session.add(food_investor)
    session.flush()

    sender = Sender(session, transport=FakeLive(), dry_run=False)
    with pytest.raises(UnverifiedRecipientError):
        sender.send(draft, mailbox=mailbox, now=a_valid_send_time())
    assert sender.transport.outbox == []

    # Verified — the same draft goes out.
    food_investor.email_confidence = EmailConfidence.VERIFIED
    session.add(food_investor)
    session.flush()
    sender.send(draft, mailbox=mailbox, now=a_valid_send_time())
    assert len(sender.transport.outbox) == 1


def test_a_suppression_outranks_an_unverified_address(
    session, pad_profile, food_investor, client, mailbox
):
    """"Never contact this person" is a stronger fact than "we have not checked the address"."""
    from pitchline import approval, suppression
    from pitchline.models import EmailConfidence, SuppressionReason
    from pitchline.send import Sender, SuppressedRecipientError
    from pitchline.send.transport import DryRunTransport
    from tests.conftest import a_valid_send_time

    campaign = Campaign(name="pad-seed", startup_profile_id=pad_profile.id)
    session.add(campaign)
    session.flush()
    target = make_target(session, campaign, food_investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=pad_profile)
    approval.approve(session, draft, approved_by="Josh")

    food_investor.email_confidence = EmailConfidence.UNKNOWN
    session.add(food_investor)
    suppression.suppress_investor(session, food_investor, reason=SuppressionReason.PASS_REPLY)

    transport = DryRunTransport()
    transport.live = True  # a live-capable transport, so preflight runs the live path

    with pytest.raises(SuppressedRecipientError):
        Sender(session, transport=transport, dry_run=False).send(
            draft, mailbox=mailbox, now=a_valid_send_time()
        )


def test_firm_prospects_are_never_mistaken_for_targets(session, pad_profile, client):
    """A ranked list of funds is not a campaign list of people."""
    from pitchline.models import Firm, FirmProspect, Target
    from pitchline.targeting import ranked_prospects, score_all_firms
    from pitchline.textutil import normalize_firm_name

    campaign = Campaign(name="pad-seed", startup_profile_id=pad_profile.id)
    session.add(campaign)
    firm = Firm(
        name="Branded Hospitality Ventures",
        name_normalized=normalize_firm_name("Branded Hospitality Ventures"),
        sectors=["hospitality", "food and beverage", "restaurant tech"],
        stages=["seed", "series_a"],
        thesis_summary="Invests in hospitality and foodservice technology and food and beverage concepts.",
    )
    session.add(firm)
    session.flush()

    report = score_all_firms(session, campaign=campaign, profile=pad_profile)

    assert report.scored == 1
    assert session.exec(select(FirmProspect)).first() is not None
    # Crucially: no Target row was created, so nothing downstream can send to a firm.
    assert list(session.exec(select(Target))) == []
    prospects = ranked_prospects(session, campaign.id)
    assert prospects and prospects[0][1].name == "Branded Hospitality Ventures"


# --------------------------------------------------------------------------------------
# The audit itself has to stay true
# --------------------------------------------------------------------------------------


def test_audit_findings_are_actually_applied():
    """Findings recorded as data are worthless if the pipeline does not honour them."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from data.investor_audit_2026 import CORRECTIONS, REMOVE
    from scripts.audit_investors import apply_audit
    from data.investor_universe_2026 import ALL_RECORDS

    audited = apply_audit(ALL_RECORDS)
    firms = {r["firm"] for r in audited}

    for removed in REMOVE:
        assert removed not in firms, f"{removed} was disproved but is still in the universe"

    by_firm = {r["firm"]: r for r in audited}
    # F1/F2 disproved two specific people, not the firms themselves. A later research pass
    # supplying a current, sourced partner is the audit working as intended; what must never
    # come back is the stale name. Assert on the person, not on the firm being contactless.
    # Firm-scoped: both people are real and reachable at their *current* funds — Christopher
    # at Asto, Patricof at Primetime Partners — so the bad pairing is person-at-firm.
    pairs = {(r["firm"], r["partner_name"]) for r in audited}
    assert ("CAVU Consumer Partners", "Clayton Christopher") not in pairs, "F1 regressed"
    assert ("Greycroft", "Alan Patricof") not in pairs, "F2 regressed"
    # F5: corrected HQ.
    assert by_firm["Blumberg Capital"]["city"] == "San Francisco"
    # F8: the family office kept its growth mandate.
    assert by_firm["JAWS Estates Capital"]["stages"] == "Growth"
    # The audit's own addition survived.
    assert "Asto Consumer Partners" in firms

    for firm, correction in CORRECTIONS.items():
        assert firm in by_firm, f"correction targets {firm}, which is not in the universe"


def test_growth_funds_never_reach_tier_a():
    """A buyout fund is a real investor and a structurally impossible recipient."""
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from scripts.audit_investors import grade

    for firm in ("Roark Capital", "Blackstone", "KKR", "Thoma Bravo"):
        record = {"firm": firm, "stages": "Growth", "sectors": "Restaurants; Consumer",
                  "thesis": "Restaurant private equity."}
        tier, reasons = grade(record)
        assert tier == "C", f"{firm} graded {tier}"
        assert "seed" in reasons[0]

"""Per-module tests for the phases either side of the acceptance contract."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlmodel import select

from pitchline import approval, suppression, textutil as tu
from pitchline.analytics import campaign_analytics, funnel
from pitchline.compose import compose_first_touch, generate_followup, plan_sequence
from pitchline.guardrails import lint_draft
from pitchline.ingest import import_investors_csv, parse_role
from pitchline.inbox import classify_reply, record_reply
from pitchline.inbox.crm import handle_reply
from pitchline.inbox.poll import MaildirPoller, poll_and_process
from pitchline.models import (
    Draft,
    EvidenceArea,
    GuardrailCode,
    Investor,
    InvestorRole,
    ReplyClass,
    SuppressionReason,
    Target,
    TargetStatus,
    Update,
)
from pitchline.research.store import needs_refetch, research_coverage, store_evidence
from pitchline.rules import MAX_CAMPAIGN_TARGETS
from pitchline.send import Sender, check_deliverability
from pitchline.send.preflight import OutsideSendWindowError, UnknownTimezoneError
from pitchline.send.transport import DryRunTransport, TransportError, build_message
from pitchline.targeting import CampaignCapExceeded, build_campaign, score_investor
from pitchline.timeutil import next_send_window, utcnow
from tests.conftest import a_valid_send_time, give_full_research, make_investor, make_target

SAMPLE_CSV = Path(__file__).resolve().parent.parent / "data" / "sample_investors.csv"


# --------------------------------------------------------------------------------------
# Phase 1 — ingest
# --------------------------------------------------------------------------------------


def test_role_parsing_prefers_the_specific_title():
    assert parse_role("Venture Partner") is InvestorRole.VENTURE_PARTNER
    assert parse_role("Managing Partner") is InvestorRole.MANAGING_PARTNER
    assert parse_role("General Partner") is InvestorRole.GENERAL_PARTNER
    assert parse_role("Partner") is InvestorRole.PARTNER
    assert parse_role("Senior Associate") is InvestorRole.ASSOCIATE
    assert parse_role("Head of Platform") is InvestorRole.PLATFORM
    assert parse_role("") is InvestorRole.UNKNOWN


@pytest.mark.skipif(not SAMPLE_CSV.exists(), reason="sample export not generated")
def test_sample_import_yields_500_partner_records_with_provenance(session):
    report = import_investors_csv(session, SAMPLE_CSV)

    partners = list(
        session.exec(select(Investor).where(Investor.quarantined == False))  # noqa: E712
    )
    assert len(partners) >= 500, "Phase 1 gate: 500 partner records"
    assert all(p.source and p.ingested_at for p in partners), "R5.3 provenance on every row"
    assert all(p.is_partner_level for p in partners), "R1.4 partner-level only"
    assert report.quarantined > 0, "non-partner and shared-inbox rows must be quarantined"
    assert "generic_mailbox" in report.quarantine_reasons
    assert any(k.startswith("role_not_partner_level") for k in report.quarantine_reasons)


@pytest.mark.skipif(not SAMPLE_CSV.exists(), reason="sample export not generated")
def test_reimport_is_idempotent(session):
    first = import_investors_csv(session, SAMPLE_CSV)
    before = len(list(session.exec(select(Investor))))
    second = import_investors_csv(session, SAMPLE_CSV)
    after = len(list(session.exec(select(Investor))))

    assert after == before, "re-importing the same export must not duplicate people"
    assert second.duplicates > first.investors_created * 0.9


def test_dedupe_survives_messy_spellings_without_merging_distinct_funds():
    normalize = tu.normalize_firm_name
    assert normalize("Northaven Capital, LLC") == normalize("northaven capital")
    assert normalize("The Northaven Capital L.P.") == normalize("Northaven Capital")
    # Different funds under one family name must stay apart: merging them would pool their
    # portfolios and manufacture phantom R1.5 conflicts.
    assert normalize("Northaven Capital") != normalize("Northaven Ventures")
    assert tu.normalize_person_name("ANA O'BRIEN Jr.") == tu.normalize_person_name("Ana O'Brien")


# --------------------------------------------------------------------------------------
# Phase 1 — evidence store and R1.3
# --------------------------------------------------------------------------------------


def test_research_floor_requires_all_three_areas(session):
    investor = make_investor(session)
    assert research_coverage(session, investor.id).meets_floor is False

    give_full_research(session, investor)
    coverage = research_coverage(session, investor.id)

    assert coverage.meets_floor is True
    assert set(coverage.by_area) >= {"portfolio", "thesis", "recent_activity"}


def test_missing_area_is_named_in_the_reason(session):
    investor = make_investor(session)
    store_evidence(
        session, investor=investor, raw_text="A thesis statement.", area=EvidenceArea.THESIS
    )
    coverage = research_coverage(session, investor.id)
    assert "portfolio" in coverage.reason()


def test_identical_evidence_is_not_stored_twice(session):
    investor = make_investor(session)
    first = store_evidence(session, investor=investor, raw_text="same text", area=EvidenceArea.THESIS)
    second = store_evidence(session, investor=investor, raw_text="same text", area=EvidenceArea.THESIS)
    assert first is not None and second is None


def test_a_fresh_url_is_not_refetched(session):
    investor = make_investor(session)
    store_evidence(
        session, investor=investor, raw_text="cached", url="https://northaven.vc/thesis",
        area=EvidenceArea.THESIS,
    )
    assert needs_refetch(session, "https://northaven.vc/thesis") is False
    assert needs_refetch(session, "https://elsewhere.vc/thesis") is True


def test_stale_evidence_does_not_count_toward_the_floor(session):
    investor = make_investor(session)
    give_full_research(session, investor)
    from pitchline.models import Evidence

    for row in session.exec(select(Evidence).where(Evidence.investor_id == investor.id)):
        row.published_at = utcnow() - timedelta(days=900)
        row.fetched_at = utcnow() - timedelta(days=900)
        session.add(row)
    session.flush()

    assert research_coverage(session, investor.id).meets_floor is False


# --------------------------------------------------------------------------------------
# Phase 2 — targeting
# --------------------------------------------------------------------------------------


def test_fit_score_has_a_rationale_and_citations_per_dimension(session, campaign, profile, client):
    investor = make_investor(session)
    give_full_research(session, investor)

    target = score_investor(session, campaign=campaign, investor=investor, profile=profile)

    assert set(target.rationales) == {
        "stage", "sector", "check_size", "geography", "thesis_recency", "portfolio_conflict",
    }
    assert all(text for text in target.rationales.values())
    assert target.evidence_ids, "R1.2 requires cited evidence"
    assert target.status is TargetStatus.QUALIFIED


def test_an_off_thesis_investor_is_dropped(session, campaign, profile, client):
    investor = make_investor(
        session,
        name="Ivan Petrov",
        firm_name="Basalt Ventures",
        sectors=["consumer gaming", "social", "creator economy"],
        stages=["growth"],
    )
    investor.thesis_summary = "We back consumer social and gaming at growth stage."
    give_full_research(session, investor)

    target = score_investor(session, campaign=campaign, investor=investor, profile=profile)

    assert target.status is TargetStatus.DROPPED_LOW_FIT


def test_conflict_is_detected_from_portfolio_evidence(session, campaign, profile, client):
    investor = make_investor(session, portfolio=["Greenphire"])
    give_full_research(session, investor, competitor="Greenphire")

    target = score_investor(session, campaign=campaign, investor=investor, profile=profile)

    assert target.has_portfolio_conflict is True
    assert "Greenphire" in target.conflict_companies
    assert target.status is TargetStatus.SUPPRESSED_CONFLICT


def test_the_campaign_cap_cannot_be_raised(session, campaign, profile, client):
    with pytest.raises(CampaignCapExceeded):
        build_campaign(
            session, campaign=campaign, profile=profile, max_targets=MAX_CAMPAIGN_TARGETS + 1
        )


def test_only_one_partner_per_firm_stays_live(session, campaign, profile, client):
    """R1.6 — colleagues at one fund compare notes; only the strongest stays live."""
    senior = make_investor(session, name="Ana Okafor")
    give_full_research(session, senior)
    for name in ("Bo Lindqvist", "Cara Mensah"):
        # make_investor mints a firm per call; repoint each colleague at the shared one.
        colleague = make_investor(session, name=name, firm_name=f"Placeholder {name}")
        colleague.firm_id = senior.firm_id
        session.add(colleague)
        session.flush()
        give_full_research(session, colleague)

    report = build_campaign(session, campaign=campaign, profile=profile)

    assert report.qualified == 1
    assert report.held_firm_duplicates == 2

    live = session.exec(
        select(Target).where(
            Target.campaign_id == campaign.id, Target.status == TargetStatus.QUALIFIED
        )
    ).all()
    held = session.exec(
        select(Target).where(
            Target.campaign_id == campaign.id,
            Target.status == TargetStatus.HELD_FIRM_DUPLICATE,
        )
    ).all()
    assert len(live) == 1 and len(held) == 2
    # Held, not dropped: if the live contact bounces the firm is still reachable.
    assert all("R1.6" in (t.suppressed_reason or "") for t in held)
    assert min(t.composite_score for t in live) >= max(t.composite_score for t in held)


def test_an_angel_without_a_firm_is_never_held_as_a_duplicate(
    session, campaign, profile, client
):
    """R1.6 collides on firms; two unaffiliated angels are two separate relationships."""
    for name in ("Dev Raman", "Elin Sato"):
        angel = make_investor(session, name=name, firm_name=f"Placeholder {name}")
        angel.firm_id = None
        session.add(angel)
        session.flush()
        give_full_research(session, angel)

    report = build_campaign(session, campaign=campaign, profile=profile)

    assert report.held_firm_duplicates == 0
    assert report.qualified == 2


def test_suppressed_investors_never_enter_the_campaign(session, campaign, profile, client):
    investor = make_investor(session)
    give_full_research(session, investor)
    suppression.suppress_investor(session, investor, reason=SuppressionReason.DO_NOT_CONTACT)

    report = build_campaign(session, campaign=campaign, profile=profile)

    assert report.suppressed_list == 1
    assert report.qualified == 0


# --------------------------------------------------------------------------------------
# Phase 3 — compose and guardrails
# --------------------------------------------------------------------------------------


@pytest.fixture()
def composed(session, campaign, profile, client):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    return compose_first_touch(session, target=target, profile=profile), target, investor


def test_a_composed_draft_passes_every_gate(session, profile, composed):
    draft, _, _ = composed
    report = lint_draft(session, draft, profile=profile)

    assert report.passed, report.describe()
    assert draft.word_count <= 150
    assert draft.novelty_score >= 4.0
    assert draft.claim_map and any(c["investor_specific"] for c in draft.claim_map)


def test_the_first_sentence_carries_the_marker_and_the_problem_precedes_the_approach(
    session, profile, composed
):
    draft, _, _ = composed
    from pitchline.models import PitchVariant

    credibility = session.get(PitchVariant, draft.credibility_variant_id)
    problem = session.get(PitchVariant, draft.problem_variant_id)
    approach = session.get(PitchVariant, draft.approach_variant_id)

    assert tu.first_sentence(draft.body).startswith(credibility.body_text[:30])
    assert draft.body.index(problem.body_text) < draft.body.index(approach.body_text)


def test_links_and_images_are_rejected_on_the_first_touch(session, profile, composed):
    draft, _, _ = composed
    draft.body = f"{draft.body}\n\nDeck: https://meridiantrials.com/deck"
    report = lint_draft(session, draft, profile=profile)
    assert report.has(GuardrailCode.LINKS)

    draft.body = f"{draft.body}\n\n![logo](https://cdn.example/logo.png)"
    report = lint_draft(session, draft, profile=profile)
    assert report.has(GuardrailCode.IMAGES)


def test_an_email_address_in_the_body_is_not_counted_as_a_link(session, profile, composed):
    draft, _, _ = composed
    draft.body = f"{draft.body} Reach me at dana@meridiantrials.com."
    report = lint_draft(session, draft, profile=profile)
    assert not report.has(GuardrailCode.LINKS)


def test_spam_terms_and_shouting_are_rejected(session, profile, composed):
    draft, _, _ = composed
    original = draft.body

    draft.body = f"{original} This is a risk-free opportunity, act now."
    assert lint_draft(session, draft, profile=profile).has(GuardrailCode.SPAM_TERMS)

    draft.body = f"{original} URGENTLY IMPORTANT."
    assert lint_draft(session, draft, profile=profile).has(GuardrailCode.SHOUTING)


def test_a_hard_scheduled_meeting_ask_is_rejected(session, profile, composed):
    draft, _, _ = composed
    draft.body = f"{draft.body} Can we meet at your office next Tuesday at 3 PM?"
    report = lint_draft(session, draft, profile=profile)
    assert report.has(GuardrailCode.ASK_TYPE)


def test_a_missing_footer_is_rejected(session, profile, composed):
    draft, _, _ = composed
    draft.footer = ""
    report = lint_draft(session, draft, profile=profile)
    assert report.has(GuardrailCode.FOOTER)


def test_editing_a_draft_drops_its_approval(session, profile, composed):
    draft, _, _ = composed
    approval.approve(session, draft, approved_by="Dana Reyes")
    assert draft.is_approved

    draft, report = approval.edit(
        session, draft, edited_by="Dana Reyes", body=draft.body, profile=profile
    )

    assert draft.is_approved is False, "R6.1 — an edited draft is a different email"
    assert report.passed


def test_batch_approval_is_refused(session, profile, composed):
    draft, _, _ = composed
    with pytest.raises(approval.ApprovalError, match="batch"):
        approval.approve_many(session, [draft, draft], approved_by="Dana Reyes")


# --------------------------------------------------------------------------------------
# Phase 5 — sending
# --------------------------------------------------------------------------------------


def test_send_outside_the_window_is_refused(session, profile, composed, mailbox):
    draft, _, _ = composed
    approval.approve(session, draft, approved_by="Dana Reyes")
    saturday = datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc)  # a Saturday

    with pytest.raises(OutsideSendWindowError):
        Sender(session, transport=DryRunTransport(), dry_run=True).send(
            draft, mailbox=mailbox, now=saturday
        )


def test_unknown_recipient_timezone_defers_rather_than_guessing(
    session, campaign, profile, client, mailbox
):
    investor = make_investor(session, name="Mei Tanaka", timezone="")
    investor.timezone = None
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")

    with pytest.raises(UnknownTimezoneError):
        Sender(session, transport=DryRunTransport(), dry_run=True).send(
            draft, mailbox=mailbox, now=a_valid_send_time()
        )


def test_next_send_window_lands_on_tuesday_to_thursday_morning():
    from zoneinfo import ZoneInfo

    moment = next_send_window(datetime(2026, 8, 1, 12, 0, tzinfo=timezone.utc), "America/New_York")
    local = moment.astimezone(ZoneInfo("America/New_York"))
    assert local.isoweekday() in (2, 3, 4)
    assert 7 <= local.hour < 10


def test_mime_is_plain_text_only():
    message = build_message(
        from_email="dana@meridian-outreach.com", from_name="Dana", to_email="ana@northaven.vc",
        subject="Meridian", body="Plain text body.",
    )
    assert message.get_content_type() == "text/plain"
    assert not message.is_multipart()

    with pytest.raises(TransportError):
        build_message(
            from_email="dana@meridian-outreach.com", from_name="Dana",
            to_email="ana@northaven.vc", subject="s", body="![x](y.png)",
        )


def test_mailbox_rotation_prefers_headroom(session, profile, composed):
    from pitchline.models import Mailbox
    from pitchline.timeutil import today_utc

    for email in ("a@outreach.example", "b@outreach.example"):
        session.add(
            Mailbox(
                email=email, domain="outreach.example",
                warmup_started_on=today_utc() - timedelta(days=90),
            )
        )
    session.flush()

    sender = Sender(session, transport=DryRunTransport(), dry_run=True)
    first, budget = sender.pick_mailbox()
    budget.consume(5)
    second, _ = sender.pick_mailbox()

    assert second.email != first.email


def test_a_dry_run_send_still_debits_the_budget(session, profile, composed, mailbox):
    from pitchline.send.budget import ReputationBudget

    draft, _, _ = composed
    now = a_valid_send_time()
    before = ReputationBudget(session, mailbox, day=now.date()).remaining

    Sender(session, transport=DryRunTransport(), dry_run=True).send(draft, mailbox=mailbox, now=now)

    after = ReputationBudget(session, mailbox, day=now.date()).remaining
    assert after == before - 1


# --------------------------------------------------------------------------------------
# Phase 6 — inbox
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,expected",
    [
        ("Sure — can you send me the deck?", ReplyClass.DECK_REQUEST),
        ("Happy to chat, are you free Thursday?", ReplyClass.INTERESTED),
        ("Thanks but we'll pass — not a fit for our thesis.", ReplyClass.PASS),
        ("Too early for us right now, circle back after your A.", ReplyClass.NOT_NOW),
        ("I am out of office until 4 August with limited access to email.", ReplyClass.OOO),
        ("Please unsubscribe me from this list.", ReplyClass.UNSUBSCRIBE),
        ("Delivery Status Notification (Failure): address not found", ReplyClass.BOUNCE),
    ],
)
def test_reply_classification(body, expected, client):
    verdict = classify_reply(subject="Re: Meridian", body=body, client=client)
    assert verdict.label == expected.value


def test_quoted_original_text_does_not_confuse_the_classifier(client):
    body = "Send me the deck.\n\nOn Tue, Dana wrote:\n> we'll pass on that\n"
    assert classify_reply(subject="Re:", body=body, client=client).label == "deck_request"


def test_a_pass_reply_suppresses_permanently_and_ends_the_sequence(
    session, campaign, profile, client, mailbox
):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    sequence = plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        draft, mailbox=mailbox, now=a_valid_send_time()
    )

    reply = record_reply(
        session, from_email=investor.email, subject="Re: Meridian",
        body="Thanks, but we'll pass — not a fit.", client=client,
    )
    outcome = handle_reply(session, reply, profile=profile)

    assert reply.classification is ReplyClass.PASS
    assert outcome.suppressed is True
    assert suppression.check(session, investor=investor) is not None
    session.refresh(sequence)
    assert sequence.ended is True
    assert session.get(Target, target.id).status is TargetStatus.CLOSED


def test_a_deck_request_drafts_the_one_click_response(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        draft, mailbox=mailbox, now=a_valid_send_time()
    )

    reply = record_reply(
        session, from_email=investor.email, subject="Re: Meridian",
        body="Interesting — can you send the deck?", client=client,
    )
    outcome = handle_reply(session, reply, profile=profile)

    assert outcome.suggested_response is not None
    assert profile.deck_url in outcome.suggested_response
    assert profile.calendar_url in outcome.suggested_response


def test_the_maildir_poller_runs_the_whole_reply_loop(
    session, campaign, profile, client, mailbox, tmp_path
):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        draft, mailbox=mailbox, now=a_valid_send_time()
    )

    (tmp_path / "reply.eml").write_text(
        f"From: {investor.email}\nTo: {mailbox.email}\nSubject: Re: Meridian\n\n"
        "Please send the deck.\n"
    )

    outcomes = poll_and_process(session, MaildirPoller(directory=tmp_path), profile=profile)

    assert len(outcomes) == 1
    assert outcomes[0].classification is ReplyClass.DECK_REQUEST


def test_an_rfc2047_encoded_subject_is_decoded_to_text(session, campaign, profile, client, tmp_path):
    """A subject with an em-dash arrives base64-encoded; it must not reach the DB as a
    Header object, and it must still be classifiable."""
    from email.message import EmailMessage

    message = EmailMessage()
    message["From"] = "ana@northaven.vc"
    message["To"] = "dana@meridian-outreach.com"
    message["Subject"] = "Re: Meridian — site payment lag"
    message.set_content("Can you send the deck?")
    (tmp_path / "encoded.eml").write_bytes(bytes(message))

    outcomes = poll_and_process(session, MaildirPoller(directory=tmp_path), profile=profile)

    from pitchline.models import Reply

    reply = session.exec(select(Reply)).first()
    assert isinstance(reply.subject, str)
    assert "site payment lag" in reply.subject
    assert outcomes[0].classification is ReplyClass.DECK_REQUEST


# --------------------------------------------------------------------------------------
# Phase 7 — analytics and the deliverability monitor
# --------------------------------------------------------------------------------------


def test_analytics_reports_against_the_benchmarks(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        draft, mailbox=mailbox, now=a_valid_send_time()
    )
    reply = record_reply(
        session, from_email=investor.email, subject="Re:", body="Send the deck please.",
        client=client,
    )
    handle_reply(session, reply, profile=profile)

    result = campaign_analytics(session, campaign.id)

    assert result.overall.sends == 1
    assert result.overall.qualified == 1
    assert result.overall.deck_requests == 1
    assert "insufficient sample" in result.overall.verdict, "one send is not a 100% reply rate"
    assert draft.variant_key in result.by_variant
    assert "healthtech-seed" in result.by_cohort

    counts = funnel(session, campaign.id)
    assert counts["sends"] == 1 and counts["replies"] == 1


def test_the_deliverability_monitor_is_quiet_on_a_healthy_campaign(session, campaign):
    alarm = check_deliverability(session, campaign_id=campaign.id)
    assert alarm.triggered is False


def test_the_monitor_alarms_and_pauses_after_consecutive_bad_windows(session, campaign, profile):
    from pitchline.models import CampaignStatus, Send, SendStatus
    from pitchline.rules import CONSECUTIVE_BAD_WINDOWS_TO_ALARM, ROLLING_WINDOW_SENDS

    investor = make_investor(session)
    target = make_target(session, campaign, investor)
    base = utcnow() - timedelta(days=3)
    for index in range(ROLLING_WINDOW_SENDS * CONSECUTIVE_BAD_WINDOWS_TO_ALARM):
        session.add(
            Send(
                draft_id=1, target_id=target.id, to_email=investor.email,
                status=SendStatus.SENT, dry_run=False, sent_at=base + timedelta(minutes=index),
                bounced=index % 10 == 0,  # 10% bounce rate — well past the R3.6 ceiling
            )
        )
    session.flush()

    alarm = check_deliverability(session, campaign_id=campaign.id)

    assert alarm.triggered is True
    assert alarm.campaign_paused is True
    assert session.get(type(campaign), campaign.id).status is CampaignStatus.PAUSED

"""The eight acceptance tests from BUILD_PROMPT.md.

These are the contract. Each one asserts that a rule is enforced *in code* — not that a
prompt mentions it. They were written before the modules they exercise.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta
from email.message import EmailMessage

import pytest
from sqlmodel import select

from pitchline import approval, suppression
from pitchline.compose import compose_first_touch, generate_followup, plan_sequence
from pitchline.compose.sequence import NoUnusedUpdateError
from pitchline.guardrails import lint_draft
from pitchline.models import (
    GuardrailCode,
    SuppressionReason,
    TargetStatus,
    Update,
)
from pitchline.rules import MAX_PITCH_WORDS, STEADY_STATE_DAILY_CAP
from pitchline.send import (
    PortfolioConflictError,
    ReputationBudget,
    ReputationBudgetExceeded,
    Sender,
    SuppressedRecipientError,
    UnapprovedDraftError,
)
from pitchline.send.transport import Delivery, DryRunTransport
from pitchline.targeting import (
    apply_portfolio_conflict_suppression,
    override_conflict,
)
from tests.conftest import (
    a_valid_send_time,
    give_full_research,
    make_investor,
    make_target,
)


@dataclass
class FakeLiveTransport:
    """A transport that reports itself live, so non-dry-run paths are testable."""

    name: str = "fake_live"
    live: bool = True
    outbox: list[EmailMessage] = field(default_factory=list)

    def deliver(self, message: EmailMessage) -> Delivery:
        self.outbox.append(message)
        return Delivery(provider_message_id="fake-1")


@pytest.fixture()
def passing_draft(session, campaign, profile, client):
    """A composed first touch that clears every gate — the baseline for negative tests."""
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    assert lint_draft(session, draft, profile=profile).passed
    return draft


# --------------------------------------------------------------------------------------
# 1. A 151-word draft is rejected.
# --------------------------------------------------------------------------------------


def test_draft_over_the_word_limit_is_rejected(session, profile, passing_draft):
    draft = passing_draft
    filler = " ".join(["reconciliation"] * (MAX_PITCH_WORDS + 1))
    draft.body = f"{draft.body} {filler}"
    session.add(draft)
    session.flush()

    words = len(f"{draft.greeting} {draft.body}".split())
    assert words > MAX_PITCH_WORDS

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.LENGTH)
    failure = next(f for f in report.failures if f.code is GuardrailCode.LENGTH)
    assert failure.rule_id == "R2.1"
    assert failure.allowed == f"{MAX_PITCH_WORDS} words"


def test_a_draft_of_exactly_151_words_is_rejected(session, profile, passing_draft):
    """The boundary itself, stated exactly as the acceptance criterion does."""
    draft = passing_draft
    draft.greeting = ""
    draft.body = " ".join(["word"] * 151)
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.LENGTH)


# --------------------------------------------------------------------------------------
# 2. A draft with an unsourced investor-specific claim is rejected.
# --------------------------------------------------------------------------------------


def test_unsourced_investor_specific_claim_is_rejected(session, profile, passing_draft):
    draft = passing_draft
    draft.claim_map = [
        {**claim, "evidence_id": None} if claim.get("investor_specific") else claim
        for claim in draft.claim_map
    ]
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.PROVENANCE)
    assert any(f.rule_id == "R2.6" for f in report.failures)


def test_claim_citing_a_nonexistent_evidence_id_is_rejected(session, profile, passing_draft):
    draft = passing_draft
    draft.claim_map = [
        {**claim, "evidence_id": 9_999_999} if claim.get("investor_specific") else claim
        for claim in draft.claim_map
    ]
    draft.hook_evidence_id = 9_999_999
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.PROVENANCE)


# --------------------------------------------------------------------------------------
# 3. A draft whose first sentence lacks a credibility marker is rejected.
# --------------------------------------------------------------------------------------


def test_first_sentence_without_a_credibility_marker_is_rejected(session, profile, passing_draft):
    draft = passing_draft
    draft.body = f"I hope this finds you well. {draft.body}"
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.CREDIBILITY_MARKER)
    failure = next(f for f in report.failures if f.code is GuardrailCode.CREDIBILITY_MARKER)
    assert failure.rule_id == "R2.3"


def test_draft_with_no_registered_marker_at_all_is_rejected(session, profile, passing_draft):
    draft = passing_draft
    draft.credibility_variant_id = None
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile)

    assert not report.passed
    assert report.has(GuardrailCode.CREDIBILITY_MARKER)


# --------------------------------------------------------------------------------------
# 4. The 41st send from one mailbox in a day raises ReputationBudgetExceeded.
# --------------------------------------------------------------------------------------


def test_send_past_the_daily_cap_raises_reputation_budget_exceeded(session, mailbox):
    budget = ReputationBudget(session, mailbox)
    assert budget.cap == STEADY_STATE_DAILY_CAP == 40

    for _ in range(STEADY_STATE_DAILY_CAP):
        budget.consume(1)

    assert budget.used == 40
    assert budget.remaining == 0

    with pytest.raises(ReputationBudgetExceeded) as exc:
        budget.consume(1)  # the 41st

    assert "40" in str(exc.value)


def test_the_budget_survives_a_new_object_for_the_same_day(session, mailbox):
    """The ledger is a row, not process state — a restart cannot reset the count."""
    first = ReputationBudget(session, mailbox)
    for _ in range(STEADY_STATE_DAILY_CAP):
        first.consume(1)

    second = ReputationBudget(session, mailbox)

    assert second.remaining == 0
    with pytest.raises(ReputationBudgetExceeded):
        second.consume(1)


def test_a_cold_mailbox_gets_the_warmup_cap_not_the_steady_state(session, mailbox):
    from pitchline.timeutil import today_utc

    mailbox.warmup_started_on = today_utc()
    session.add(mailbox)
    session.flush()

    budget = ReputationBudget(session, mailbox)

    assert budget.cap < STEADY_STATE_DAILY_CAP


# --------------------------------------------------------------------------------------
# 5. An investor on the suppression list is never dispatched to, even if queued.
# --------------------------------------------------------------------------------------


def test_suppressed_investor_is_never_dispatched_to(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")

    # Queued and approved — and then they ask never to be contacted again.
    suppression.suppress_investor(session, investor, reason=SuppressionReason.PASS_REPLY)

    sender = Sender(session, transport=FakeLiveTransport(), dry_run=False)

    with pytest.raises(SuppressedRecipientError):
        sender.send(draft, mailbox=mailbox, now=a_valid_send_time())

    assert sender.transport.outbox == []


def test_suppression_by_domain_also_blocks_dispatch(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")

    from pitchline.models import SuppressionScope

    suppression.add(
        session,
        value="northaven.vc",
        scope=SuppressionScope.DOMAIN,
        reason=SuppressionReason.DO_NOT_CONTACT,
    )

    with pytest.raises(SuppressedRecipientError):
        Sender(session, transport=FakeLiveTransport(), dry_run=False).send(
            draft, mailbox=mailbox, now=a_valid_send_time()
        )


# --------------------------------------------------------------------------------------
# 6. A follow-up with no unused update is never generated.
# --------------------------------------------------------------------------------------


def test_followup_without_an_unused_update_is_never_generated(
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

    # Every update has already been used.
    for update in session.exec(select(Update)):
        update.consumed_by_draft_id = draft.id
        session.add(update)
    session.flush()

    with pytest.raises(NoUnusedUpdateError) as exc:
        generate_followup(session, target=target, profile=profile, touch_number=2)

    assert "R4.3" in str(exc.value)

    from pitchline.models import Draft

    followups = session.exec(
        select(Draft).where(Draft.target_id == target.id, Draft.touch_number == 2)
    ).all()
    assert list(followups) == [], "no follow-up row may exist when there is nothing new to say"

    session.refresh(sequence)
    assert sequence.ended is True


def test_an_update_is_consumed_once_and_only_once(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    first = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, first, approved_by="Dana Reyes")
    Sender(session, transport=DryRunTransport(), dry_run=True).send(
        first, mailbox=mailbox, now=a_valid_send_time()
    )

    followup = generate_followup(session, target=target, profile=profile, touch_number=2)
    used = session.get(Update, followup.update_id)

    assert used is not None
    assert used.consumed_by_draft_id == followup.id
    assert used.consumed_at is not None


# --------------------------------------------------------------------------------------
# 7. An investor with a direct competitor in portfolio is suppressed unless overridden.
# --------------------------------------------------------------------------------------


def test_portfolio_conflict_is_suppressed_and_not_dispatchable(
    session, campaign, profile, client, mailbox
):
    investor = make_investor(session, portfolio=["Corvus Health", "Greenphire"])
    give_full_research(session, investor, competitor="Greenphire")
    target = make_target(session, campaign, investor)
    target.has_portfolio_conflict = True
    target.conflict_companies = ["Greenphire"]
    session.add(target)
    session.flush()

    apply_portfolio_conflict_suppression(session, target)

    assert target.status is TargetStatus.SUPPRESSED_CONFLICT
    assert target.is_sendable is False

    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")

    with pytest.raises(PortfolioConflictError):
        Sender(session, transport=FakeLiveTransport(), dry_run=False).send(
            draft, mailbox=mailbox, now=a_valid_send_time()
        )


def test_a_named_human_can_override_a_portfolio_conflict(session, campaign, profile, client):
    investor = make_investor(session, portfolio=["Greenphire"])
    give_full_research(session, investor, competitor="Greenphire")
    target = make_target(session, campaign, investor)
    target.has_portfolio_conflict = True
    target.conflict_companies = ["Greenphire"]
    session.add(target)
    session.flush()
    apply_portfolio_conflict_suppression(session, target)

    override_conflict(
        session,
        target,
        approved_by="Dana Reyes",
        reason="Greenphire is adjacent, not competitive; confirmed with the partner directly.",
    )

    assert target.conflict_overridden is True
    assert target.status is TargetStatus.QUALIFIED
    assert target.is_sendable is True


def test_a_model_cannot_override_a_portfolio_conflict(session, campaign, profile, client):
    from pitchline.targeting import ConflictOverrideError

    investor = make_investor(session, portfolio=["Greenphire"])
    target = make_target(session, campaign, investor)
    target.has_portfolio_conflict = True
    target.conflict_companies = ["Greenphire"]
    session.add(target)
    session.flush()

    with pytest.raises(ConflictOverrideError):
        override_conflict(session, target, approved_by="system", reason="looks fine")

    with pytest.raises(ConflictOverrideError):
        override_conflict(session, target, approved_by="Dana Reyes", reason="")


# --------------------------------------------------------------------------------------
# 8. send() in non-dry-run mode raises unless the draft has approved_by and approved_at.
# --------------------------------------------------------------------------------------


def test_live_send_without_approval_raises(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)

    assert draft.approved_by is None and draft.approved_at is None

    sender = Sender(session, transport=FakeLiveTransport(), dry_run=False)

    with pytest.raises(UnapprovedDraftError):
        sender.send(draft, mailbox=mailbox, now=a_valid_send_time())

    assert sender.transport.outbox == []


def test_live_send_with_half_an_approval_still_raises(session, campaign, profile, client, mailbox):
    """approved_by without approved_at is not an approval (R6.1 requires both)."""
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    draft.approved_by = "Dana Reyes"
    draft.approved_at = None
    session.add(draft)
    session.flush()

    with pytest.raises(UnapprovedDraftError):
        Sender(session, transport=FakeLiveTransport(), dry_run=False).send(
            draft, mailbox=mailbox, now=a_valid_send_time()
        )


def test_live_send_with_a_full_approval_dispatches(session, campaign, profile, client, mailbox):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)
    approval.approve(session, draft, approved_by="Dana Reyes")

    sender = Sender(session, transport=FakeLiveTransport(), dry_run=False)
    send_row = sender.send(draft, mailbox=mailbox, now=a_valid_send_time())

    assert send_row.status.value == "sent"
    assert len(sender.transport.outbox) == 1
    assert sender.transport.outbox[0].get_content_type() == "text/plain"


def test_a_model_cannot_approve_a_draft(session, campaign, profile, client):
    investor = make_investor(session)
    give_full_research(session, investor)
    target = make_target(session, campaign, investor)
    plan_sequence(session, target)
    draft = compose_first_touch(session, target=target, profile=profile)

    with pytest.raises(approval.ApprovalError):
        approval.approve(session, draft, approved_by="claude")
    with pytest.raises(approval.ApprovalError):
        approval.approve(session, draft, approved_by="")

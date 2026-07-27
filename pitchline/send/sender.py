"""The sender.

``Sender.send`` is the only function that dispatches. It:

1. runs preflight (approval, suppression, conflict, sender identity, send window);
2. picks a mailbox with budget left and rotates between them;
3. debits the reputation budget *before* dispatch and refunds on transport failure;
4. re-checks the suppression list in the statement before ``transport.deliver``;
5. writes a ``Send`` row carrying the experiment dimensions (variant, cohort, timestamp).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sqlmodel import Session, select

from pitchline import events, suppression
from pitchline.models import (
    Campaign,
    Draft,
    DraftStatus,
    EventKind,
    Firm,
    Investor,
    Mailbox,
    Send,
    SendStatus,
    StartupProfile,
    Target,
    TargetStatus,
)
from pitchline.rules import MAX_CONSECUTIVE_SENDS_PER_MAILBOX, MIN_SECONDS_BETWEEN_SENDS
from pitchline.send.budget import ReputationBudget, ReputationBudgetExceeded, SendTooSoon
from pitchline.send.preflight import SendRefused, SuppressedRecipientError, preflight
from pitchline.send.transport import DryRunTransport, Transport, TransportError, build_message
from pitchline.timeutil import ensure_utc, utcnow


class NoMailboxAvailable(RuntimeError):
    """Every mailbox is out of budget for today (R3.3)."""


@dataclass
class SendReport:
    attempted: int = 0
    sent: int = 0
    refused: int = 0
    failed: int = 0
    budget_exhausted: int = 0
    paced_waits: int = 0
    refusals: dict[str, int] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)

    def note_refusal(self, exc: Exception) -> None:
        self.refused += 1
        key = type(exc).__name__
        self.refusals[key] = self.refusals.get(key, 0) + 1

    def summary(self) -> str:
        return (
            f"{self.attempted} attempted -> {self.sent} sent, {self.refused} refused, "
            f"{self.failed} failed, {self.budget_exhausted} out of budget"
        )


class Sender:
    """Dispatch with a reputation budget. Dry run by default, everywhere."""

    def __init__(
        self,
        session: Session,
        *,
        transport: Transport | None = None,
        dry_run: bool = True,
        actor: str = "system",
    ) -> None:
        self.session = session
        self.dry_run = dry_run
        self.transport = transport or DryRunTransport()
        self.actor = actor
        if not dry_run and not getattr(self.transport, "live", False):
            raise ValueError(
                f"transport {self.transport.name!r} cannot deliver live mail; "
                "pass dry_run=True or configure a live transport"
            )

    # -- mailbox selection --------------------------------------------------------------

    def available_mailboxes(
        self, *, day=None, now: datetime | None = None
    ) -> list[tuple[Mailbox, ReputationBudget]]:
        """Mailboxes with budget left that are not inside their R3.3 cooldown."""
        now = now or utcnow()
        rows = list(self.session.exec(select(Mailbox).where(Mailbox.active == True)))  # noqa: E712
        free: list[tuple[Mailbox, ReputationBudget]] = []
        for mailbox in rows:
            budget = ReputationBudget(self.session, mailbox, day=day or now.date())
            if budget.exhausted:
                continue
            try:
                budget.check_spacing(now=now)
            except SendTooSoon:
                continue
            free.append((mailbox, budget))
        # Rotation: most headroom first, then least recently used.
        return sorted(
            free,
            key=lambda pair: (
                -pair[1].remaining,
                ensure_utc(pair[0].last_send_at) or datetime.min.replace(tzinfo=timezone.utc),
                pair[0].id or 0,
            ),
        )

    def cooldown_seconds(self, *, now: datetime | None = None) -> float | None:
        """Seconds until some mailbox with budget left becomes sendable again."""
        now = now or utcnow()
        waits: list[float] = []
        for mailbox in self.session.exec(select(Mailbox).where(Mailbox.active == True)):  # noqa: E712
            budget = ReputationBudget(self.session, mailbox, day=now.date())
            if budget.exhausted or mailbox.consecutive_sends >= MAX_CONSECUTIVE_SENDS_PER_MAILBOX:
                continue
            last = ensure_utc(mailbox.last_send_at)
            waits.append(
                0.0 if last is None
                else max(0.0, MIN_SECONDS_BETWEEN_SENDS - (now - last).total_seconds())
            )
        return min(waits) if waits else None

    def pick_mailbox(
        self, *, day=None, now: datetime | None = None
    ) -> tuple[Mailbox, ReputationBudget]:
        options = self.available_mailboxes(day=day, now=now)
        if options:
            return options[0]
        wait = self.cooldown_seconds(now=now)
        if wait is not None:
            raise NoMailboxAvailable(
                f"every mailbox is inside its R3.3 cooldown; next one free in {wait:.0f}s. "
                "Pace the run (--pace) or let the scheduler drip it out."
            )
        raise NoMailboxAvailable(
            "every mailbox has spent its daily reputation budget (R3.3). "
            "Reputation is the constraint, not throughput — resume tomorrow."
        )

    # -- sending ------------------------------------------------------------------------

    def send(
        self,
        draft: Draft,
        *,
        mailbox: Mailbox | None = None,
        now: datetime | None = None,
        enforce_window: bool = True,
        profile: StartupProfile | None = None,
    ) -> Send:
        """Send one draft. Raises a :class:`SendRefused` subclass rather than skipping."""
        now = now or utcnow()
        target = self.session.get(Target, draft.target_id)
        if target is None:
            raise SendRefused(f"draft {draft.id} has no target")
        investor = self.session.get(Investor, target.investor_id)
        if investor is None:
            raise SendRefused(f"target {target.id} has no investor")

        budget: ReputationBudget | None = None
        if mailbox is None:
            mailbox, budget = self.pick_mailbox(now=now)
        else:
            budget = ReputationBudget(self.session, mailbox, day=now.date())

        preflight(
            self.session,
            draft=draft,
            target=target,
            investor=investor,
            mailbox=mailbox,
            dry_run=self.dry_run,
            now=now,
            enforce_window=enforce_window,
        )
        budget.check_spacing(now=now)

        profile = profile or self._profile_for(target)
        message = build_message(
            from_email=mailbox.email,
            from_name=mailbox.display_name or (profile.founder_name if profile else ""),
            to_email=investor.email,  # type: ignore[arg-type]
            subject=draft.subject,
            body=draft.rendered,
            reply_to=(profile.reply_to_email or profile.founder_email) if profile else None,
            in_reply_to=self._thread_parent(target, draft),
        )

        # R3.3 — debit before dispatch: an unrecorded send is worse than a refunded one.
        budget.consume(1, now=now)
        self._reset_other_streaks(mailbox)

        # R5.2 — the last check before the wire. A reply may have landed since preflight.
        firm = self.session.get(Firm, investor.firm_id) if investor.firm_id else None
        if hit := suppression.check(self.session, investor=investor, firm=firm):
            budget.refund(1)
            raise SuppressedRecipientError(
                f"{investor.email} was suppressed between preflight and dispatch ({hit.describe()})"
            )

        send_row = Send(
            draft_id=draft.id,  # type: ignore[arg-type]
            target_id=target.id,  # type: ignore[arg-type]
            mailbox_id=mailbox.id,
            to_email=investor.email,  # type: ignore[arg-type]
            subject=draft.subject,
            body_snapshot=draft.rendered,
            dry_run=self.dry_run,
            touch_number=draft.touch_number,
            scheduled_for=draft.scheduled_for,
            recipient_timezone=investor.timezone,
            experiment_id=draft.experiment_id,
            variant_key=draft.variant_key,
            cohort=target.cohort,
        )

        try:
            delivery = self.transport.deliver(message)
        except TransportError as exc:
            budget.refund(1)
            send_row.status = SendStatus.FAILED
            send_row.error = str(exc)
            self.session.add(send_row)
            self.session.flush()
            events.record(
                self.session,
                EventKind.SEND_REFUSED,
                entity_type="send",
                entity_id=send_row.id,
                campaign_id=target.campaign_id,
                summary=f"transport failure: {exc}",
                actor=self.actor,
                flush=False,
            )
            raise

        send_row.status = SendStatus.DRY_RUN if self.dry_run else SendStatus.SENT
        send_row.sent_at = now
        send_row.provider_message_id = delivery.provider_message_id
        send_row.thread_id = delivery.thread_id
        self.session.add(send_row)

        draft.status = DraftStatus.SENT
        target.status = TargetStatus.IN_SEQUENCE
        self.session.add_all([draft, target])
        self.session.flush()

        events.record(
            self.session,
            EventKind.SENT,
            entity_type="send",
            entity_id=send_row.id,
            campaign_id=target.campaign_id,
            summary=(
                f"touch {draft.touch_number} to {investor.email} via {mailbox.email} "
                f"({'dry run' if self.dry_run else 'live'}); {budget.remaining} left today"
            ),
            payload={
                "variant_key": draft.variant_key,
                "cohort": target.cohort,
                "budget_remaining": budget.remaining,
            },
            actor=self.actor,
            flush=False,
        )
        return send_row

    def send_batch(
        self,
        drafts: list[Draft],
        *,
        now: datetime | None = None,
        enforce_window: bool = True,
        stop_on_budget: bool = True,
        pace: bool = False,
        max_wait_seconds: float = 600.0,
    ) -> SendReport:
        """Send a queue, absorbing per-draft refusals so one bad row cannot stall a run.

        With ``pace=True`` the run waits out the R3.3 spacing instead of stopping. That is
        the honest way to drip a batch: the alternative is pretending the cooldown is a
        failure and skipping recipients who did nothing wrong.
        """
        report = SendReport()
        for draft in drafts:
            report.attempted += 1
            try:
                self.send(draft, now=now, enforce_window=enforce_window)
                report.sent += 1
            except ReputationBudgetExceeded as exc:
                report.budget_exhausted += 1
                report.errors.append(str(exc))
                if stop_on_budget:
                    break
            except NoMailboxAvailable as exc:
                wait = self.cooldown_seconds(now=now)
                if pace and wait is not None and wait <= max_wait_seconds and now is None:
                    time.sleep(wait + 0.5)
                    report.paced_waits += 1
                    report.attempted -= 1  # retried below, not a spent attempt
                    try:
                        self.send(draft, now=None, enforce_window=enforce_window)
                        report.attempted += 1
                        report.sent += 1
                        continue
                    except Exception as retry_exc:  # fall through to the normal accounting
                        report.attempted += 1
                        report.note_refusal(retry_exc)
                        report.errors.append(str(retry_exc))
                        continue
                report.budget_exhausted += 1
                report.errors.append(str(exc))
                if stop_on_budget:
                    break
            except SendTooSoon as exc:
                report.note_refusal(exc)
                report.errors.append(str(exc))
            except SendRefused as exc:
                report.note_refusal(exc)
                report.errors.append(f"draft {draft.id}: {exc}")
            except TransportError as exc:
                report.failed += 1
                report.errors.append(f"draft {draft.id}: {exc}")
        return report

    # -- helpers ------------------------------------------------------------------------

    def _reset_other_streaks(self, current: Mailbox) -> None:
        """R3.3 — 'consecutive' means consecutive. Using another mailbox breaks the streak."""
        others = [
            m
            for m in self.session.exec(select(Mailbox).where(Mailbox.active == True))  # noqa: E712
            if m.id != current.id and m.consecutive_sends
        ]
        for mailbox in others:
            mailbox.consecutive_sends = 0
            self.session.add(mailbox)
        if others:
            self.session.flush()

    def _profile_for(self, target: Target) -> StartupProfile | None:
        campaign = self.session.get(Campaign, target.campaign_id)
        return self.session.get(StartupProfile, campaign.startup_profile_id) if campaign else None

    def _thread_parent(self, target: Target, draft: Draft) -> str | None:
        """Thread a follow-up onto the original message rather than starting a new one."""
        if (draft.touch_number or 1) <= 1:
            return None
        previous = list(
            self.session.exec(
                select(Send)
                .where(Send.target_id == target.id)
                .order_by(Send.touch_number)  # type: ignore[arg-type]
            )
        )
        return previous[0].provider_message_id if previous else None


def approved_queue(session: Session, *, campaign_id: int | None = None) -> list[Draft]:
    """Approved drafts awaiting dispatch, oldest touch first."""
    drafts = list(session.exec(select(Draft).where(Draft.status == DraftStatus.APPROVED)))
    if campaign_id is not None:
        target_ids = {
            t.id for t in session.exec(select(Target).where(Target.campaign_id == campaign_id))
        }
        drafts = [d for d in drafts if d.target_id in target_ids]
    drafts.sort(key=lambda d: (d.touch_number, d.approved_at or utcnow()))
    return drafts

"""The reputation budget (R3.3).

Design principle 1 made concrete: reputation is depletable, so it is a ledger with a
balance, not a rate limiter that quietly defers. When the budget is exhausted the sender
raises ``ReputationBudgetExceeded`` — loudly, because "we ran out of reputation today" is
information the operator needs, and a silent deferral hides it.

The cap comes from the warmup ramp indexed by mailbox age, and the ledger is a database
row per mailbox per day, so a crash mid-campaign cannot reset the count.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlmodel import Session, select

from pitchline import events
from pitchline.models import EventKind, Mailbox, MailboxDailyQuota
from pitchline.rules import (
    DAILY_CAP_OVERRIDE_ALLOWED,
    MAX_CONSECUTIVE_SENDS_PER_MAILBOX,
    MIN_SECONDS_BETWEEN_SENDS,
    daily_cap_for_mailbox_age,
)
from pitchline.timeutil import ensure_utc, today_utc, utcnow


class ReputationBudgetExceeded(RuntimeError):
    """The mailbox has spent its daily reputation budget (R3.3)."""


class SendTooSoon(RuntimeError):
    """R3.3 — sends from one mailbox are spaced; this one is too close to the last."""


def quota_for(session: Session, mailbox: Mailbox, *, day: date | None = None) -> MailboxDailyQuota:
    """Get or create today's ledger row, with the cap the warmup ramp allows."""
    day = day or today_utc()
    row = session.exec(
        select(MailboxDailyQuota).where(
            MailboxDailyQuota.mailbox_id == mailbox.id, MailboxDailyQuota.day == day
        )
    ).first()
    cap = daily_cap_for_mailbox_age(mailbox.age_days(day))
    if row is None:
        row = MailboxDailyQuota(mailbox_id=mailbox.id, day=day, cap=cap, used=0)  # type: ignore[arg-type]
        session.add(row)
        session.flush()
    elif row.cap != cap and not DAILY_CAP_OVERRIDE_ALLOWED:
        # The ramp is authoritative: an operator cannot widen today's cap by editing a row.
        row.cap = cap
        session.add(row)
        session.flush()
    return row


class ReputationBudget:
    """A day's send allowance for one mailbox."""

    def __init__(self, session: Session, mailbox: Mailbox, *, day: date | None = None) -> None:
        self.session = session
        self.mailbox = mailbox
        self.day = day or today_utc()
        self.quota = quota_for(session, mailbox, day=self.day)

    @property
    def cap(self) -> int:
        return self.quota.cap

    @property
    def used(self) -> int:
        return self.quota.used

    @property
    def remaining(self) -> int:
        return self.quota.remaining

    @property
    def exhausted(self) -> bool:
        return self.remaining <= 0

    def can_send(self, cost: int = 1) -> bool:
        return self.remaining >= cost

    def check_spacing(self, *, now: datetime | None = None) -> None:
        """R3.3 — minimum gap between sends from the same mailbox."""
        now = now or utcnow()
        last = ensure_utc(self.mailbox.last_send_at)
        if last is None:
            return
        gap = (now - last).total_seconds()
        if gap < MIN_SECONDS_BETWEEN_SENDS:
            raise SendTooSoon(
                f"{self.mailbox.email}: {gap:.0f}s since last send, "
                f"minimum is {MIN_SECONDS_BETWEEN_SENDS}s (R3.3)"
            )
        if self.mailbox.consecutive_sends >= MAX_CONSECUTIVE_SENDS_PER_MAILBOX:
            raise SendTooSoon(
                f"{self.mailbox.email}: {self.mailbox.consecutive_sends} consecutive sends; "
                f"rotate mailboxes (R3.3 max {MAX_CONSECUTIVE_SENDS_PER_MAILBOX})"
            )

    def consume(self, cost: int = 1, *, now: datetime | None = None) -> int:
        """Debit the budget. Raises rather than deferring when exhausted."""
        if not self.can_send(cost):
            events.record(
                self.session,
                EventKind.BUDGET_EXHAUSTED,
                entity_type="mailbox",
                entity_id=self.mailbox.id,
                summary=f"{self.mailbox.email} exhausted its {self.cap}/day budget",
                payload={"day": str(self.day), "used": self.used, "cap": self.cap},
            )
            raise ReputationBudgetExceeded(
                f"{self.mailbox.email} has used {self.used}/{self.cap} sends for {self.day} "
                f"(R3.3, mailbox age {self.mailbox.age_days(self.day)}d). "
                "Reputation is the budget — rotate mailboxes or wait for tomorrow."
            )
        self.quota.used += cost
        self.mailbox.last_send_at = now or utcnow()
        self.mailbox.consecutive_sends += cost
        self.session.add_all([self.quota, self.mailbox])
        self.session.flush()
        return self.remaining

    def refund(self, cost: int = 1) -> None:
        """A transport failure did not consume reputation; give it back."""
        self.quota.used = max(0, self.quota.used - cost)
        self.mailbox.consecutive_sends = max(0, self.mailbox.consecutive_sends - cost)
        self.session.add_all([self.quota, self.mailbox])
        self.session.flush()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ReputationBudget {self.mailbox.email} {self.used}/{self.cap} on {self.day}>"

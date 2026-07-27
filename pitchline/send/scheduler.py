"""APScheduler wiring — the drip that makes the rules livable.

The rules make a burst impossible on purpose: 40 sends per mailbox per day (R3.3), 90
seconds between them, and a three-hour recipient-local window on three days a week (R4.5).
A campaign therefore has to be dripped, and this is the dripper. It only ever dispatches
drafts a human already approved.

APScheduler is an optional dependency: ``run_once`` is a plain function, so the whole
schedule can be driven from cron or a loop if you would rather not run a daemon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy.engine import Engine
from sqlmodel import Session, select

from pitchline import events
from pitchline.compose.sequence import (
    NoUnusedUpdateError,
    due_followups,
    generate_followup,
)
from pitchline.db import get_engine, session_scope
from pitchline.models import Campaign, CampaignStatus, EventKind, Investor, StartupProfile, Target
from pitchline.rules import MIN_SECONDS_BETWEEN_SENDS
from pitchline.send.monitor import check_deliverability
from pitchline.send.sender import SendReport, Sender, approved_queue
from pitchline.send.transport import DryRunTransport, Transport
from pitchline.timeutil import next_send_window, utcnow


@dataclass
class TickReport:
    at: datetime
    sent: int = 0
    followups_generated: int = 0
    sequences_ended: int = 0
    alarm: str = ""
    skipped_reason: str = ""
    errors: list[str] = field(default_factory=list)

    def describe(self) -> str:
        if self.skipped_reason:
            return f"{self.at:%Y-%m-%d %H:%M} skipped — {self.skipped_reason}"
        return (
            f"{self.at:%Y-%m-%d %H:%M} sent {self.sent}, "
            f"generated {self.followups_generated} follow-ups"
            + (f", ALARM: {self.alarm}" if self.alarm else "")
        )


def run_once(
    *,
    campaign_name: str,
    engine: Engine | None = None,
    transport: Transport | None = None,
    dry_run: bool = True,
    batch_size: int = 5,
    generate_followups: bool = True,
) -> TickReport:
    """One tick: check deliverability, top up follow-ups, dispatch a small batch."""
    report = TickReport(at=utcnow())
    engine = engine or get_engine()

    with session_scope(engine) as session:
        campaign = session.exec(select(Campaign).where(Campaign.name == campaign_name)).first()
        if campaign is None:
            report.skipped_reason = f"no campaign named {campaign_name!r}"
            return report

        # R3.6 — a paused campaign stays paused until a human resumes it.
        alarm = check_deliverability(session, campaign_id=campaign.id)
        if alarm.triggered:
            report.alarm = alarm.reason
        if campaign.status is CampaignStatus.PAUSED:
            report.skipped_reason = f"campaign paused: {campaign.paused_reason}"
            return report

        profile = session.get(StartupProfile, campaign.startup_profile_id)

        if generate_followups and profile is not None:
            for due in due_followups(session, campaign_id=campaign.id):  # type: ignore[arg-type]
                try:
                    generate_followup(
                        session, target=due.target, profile=profile, touch_number=due.touch_number
                    )
                    report.followups_generated += 1
                except NoUnusedUpdateError:
                    # R4.3 — nothing new to say, so the sequence ends. Not an error.
                    report.sequences_ended += 1
                except Exception as exc:
                    report.errors.append(f"target {due.target.id}: {exc}")

        drafts = approved_queue(session, campaign_id=campaign.id)[:batch_size]
        if not drafts:
            report.skipped_reason = "nothing approved to send"
            return report

        sender = Sender(session, transport=transport or DryRunTransport(), dry_run=dry_run)
        result: SendReport = sender.send_batch(drafts, stop_on_budget=True)
        report.sent = result.sent
        report.errors.extend(result.errors[:10])

        events.record(
            session,
            EventKind.SCHEDULED,
            entity_type="campaign",
            entity_id=campaign.id,
            campaign_id=campaign.id,
            summary=report.describe(),
        )
    return report


def next_window_for_campaign(session: Session, campaign_id: int) -> datetime | None:
    """The earliest R4.5 window across the campaign's remaining recipients."""
    moments: list[datetime] = []
    now = utcnow()
    for target in session.exec(select(Target).where(Target.campaign_id == campaign_id)):
        investor = session.get(Investor, target.investor_id)
        if investor is None or not investor.timezone:
            continue
        moment = next_send_window(now, investor.timezone)
        if moment is not None:
            moments.append(moment)
    return min(moments) if moments else None


def build_scheduler(
    *,
    campaign_name: str,
    dry_run: bool = True,
    transport: Transport | None = None,
    batch_size: int = 5,
    seconds: int | None = None,
):
    """A ``BackgroundScheduler`` ticking at the R3.3 minimum spacing.

    The interval is the send *spacing*, not the send rate: most ticks will find no mailbox
    free and do nothing, which is the intended shape of a reputation-limited campaign.
    """
    try:
        from apscheduler.schedulers.background import BackgroundScheduler  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError(
            "APScheduler is not installed; run `pip install apscheduler`, or drive "
            "pitchline.send.scheduler.run_once from cron"
        ) from exc

    scheduler = BackgroundScheduler(timezone="UTC")
    scheduler.add_job(
        run_once,
        "interval",
        seconds=seconds or MIN_SECONDS_BETWEEN_SENDS,
        kwargs={
            "campaign_name": campaign_name,
            "dry_run": dry_run,
            "transport": transport,
            "batch_size": batch_size,
        },
        id=f"pitchline-{campaign_name}",
        max_instances=1,
        coalesce=True,
    )
    return scheduler

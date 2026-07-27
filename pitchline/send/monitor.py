"""Deliverability monitor (R3.6).

The source's own failure mode: response rates fell as the campaign progressed because
filters caught an increasing share of the mail — roughly a quarter never arrived. The
monitor watches rolling windows of sends and pauses the campaign rather than continuing to
spend a domain's reputation into a spam folder.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from pitchline import events
from pitchline.models import Campaign, CampaignStatus, EventKind, Send, SendStatus, Target
from pitchline.rules import (
    BASELINE_REPLY_RATE,
    CONSECUTIVE_BAD_WINDOWS_TO_ALARM,
    DECLINE_RATIO_VS_BASELINE,
    MAX_WINDOW_BOUNCE_RATE,
    MIN_WINDOW_REPLY_RATE,
    PAUSE_CAMPAIGN_ON_ALARM,
    ROLLING_WINDOW_SENDS,
)
from pitchline.timeutil import ensure_utc, utcnow


@dataclass
class WindowStats:
    index: int
    sends: int
    replies: int
    bounces: int

    @property
    def reply_rate(self) -> float:
        return self.replies / self.sends if self.sends else 0.0

    @property
    def bounce_rate(self) -> float:
        return self.bounces / self.sends if self.sends else 0.0

    @property
    def is_bad(self) -> bool:
        """Bad = reply rate collapsed against the 4% baseline, or bounces spiked."""
        if self.sends < ROLLING_WINDOW_SENDS:
            return False  # a partial window is not evidence
        below_floor = self.reply_rate < MIN_WINDOW_REPLY_RATE
        declined = self.reply_rate < BASELINE_REPLY_RATE * DECLINE_RATIO_VS_BASELINE
        bouncing = self.bounce_rate > MAX_WINDOW_BOUNCE_RATE
        return below_floor or declined or bouncing

    def describe(self) -> str:
        return (
            f"window {self.index}: {self.sends} sends, reply {self.reply_rate:.1%}, "
            f"bounce {self.bounce_rate:.1%}"
        )


@dataclass
class DeliverabilityAlarm:
    triggered: bool = False
    reason: str = ""
    windows: list[WindowStats] = field(default_factory=list)
    campaign_paused: bool = False

    def describe(self) -> str:
        if not self.triggered:
            return "deliverability nominal: " + "; ".join(w.describe() for w in self.windows[-2:])
        return f"DELIVERABILITY ALARM — {self.reason}"


def rolling_windows(session: Session, *, campaign_id: int | None = None) -> list[WindowStats]:
    """Split the send history into fixed-size windows, oldest first."""
    statement = select(Send).where(
        Send.status.in_([SendStatus.SENT, SendStatus.DRY_RUN, SendStatus.REPLIED, SendStatus.BOUNCED])  # type: ignore[attr-defined]
    )
    sends = list(session.exec(statement))
    if campaign_id is not None:
        target_ids = {
            t.id for t in session.exec(select(Target).where(Target.campaign_id == campaign_id))
        }
        sends = [s for s in sends if s.target_id in target_ids]
    sends.sort(key=lambda s: (ensure_utc(s.sent_at) or utcnow(), s.id or 0))

    windows: list[WindowStats] = []
    for index, start in enumerate(range(0, len(sends), ROLLING_WINDOW_SENDS)):
        chunk = sends[start : start + ROLLING_WINDOW_SENDS]
        windows.append(
            WindowStats(
                index=index,
                sends=len(chunk),
                replies=sum(1 for s in chunk if s.replied),
                bounces=sum(1 for s in chunk if s.bounced),
            )
        )
    return windows


def check_deliverability(
    session: Session, *, campaign_id: int | None = None, pause: bool | None = None
) -> DeliverabilityAlarm:
    """Raise (record) an alarm after N consecutive bad windows, and pause the campaign."""
    windows = rolling_windows(session, campaign_id=campaign_id)
    alarm = DeliverabilityAlarm(windows=windows)

    trailing_bad = 0
    for window in reversed(windows):
        if window.is_bad:
            trailing_bad += 1
        else:
            break

    if trailing_bad >= CONSECUTIVE_BAD_WINDOWS_TO_ALARM:
        recent = windows[-1]
        alarm.triggered = True
        alarm.reason = (
            f"{trailing_bad} consecutive windows below threshold "
            f"(latest reply {recent.reply_rate:.1%} vs {BASELINE_REPLY_RATE:.0%} baseline, "
            f"bounce {recent.bounce_rate:.1%}). R3.6 — stop spending domain reputation."
        )
        events.record(
            session,
            EventKind.ALARM_RAISED,
            entity_type="campaign",
            entity_id=campaign_id,
            campaign_id=campaign_id,
            summary=alarm.reason,
            payload={"windows": [w.describe() for w in windows[-4:]]},
        )
        should_pause = PAUSE_CAMPAIGN_ON_ALARM if pause is None else pause
        if should_pause and campaign_id is not None:
            campaign = session.get(Campaign, campaign_id)
            if campaign and campaign.status is not CampaignStatus.PAUSED:
                campaign.status = CampaignStatus.PAUSED
                campaign.paused_reason = alarm.reason
                session.add(campaign)
                session.flush()
                alarm.campaign_paused = True
                events.record(
                    session,
                    EventKind.CAMPAIGN_PAUSED,
                    entity_type="campaign",
                    entity_id=campaign_id,
                    campaign_id=campaign_id,
                    summary="paused pending human review (R3.6 require_human_resume)",
                    flush=False,
                )
    return alarm

"""Phase 7 — experiment analytics.

The number that matters is not the reply rate; it is the *qualified* reply rate, and the
denominator is reputation spent, not emails sent. Every figure is reported against the
4% baseline and the 13-17% ceiling band from the source experiment, with an explicit
"not enough sends to say" when the sample is too small — a 1-of-3 run is not a 33% reply
rate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlmodel import Session, select

from pitchline.models import Draft, Reply, ReplyClass, Send, SendStatus, Target
from pitchline.rules import (
    BASELINE_REPLY_RATE,
    CEILING_REPLY_RATE_HIGH,
    CEILING_REPLY_RATE_LOW,
    MIN_SENDS_FOR_RATE_SIGNIFICANCE,
)

#: R2.5 — a deck request is the expected modal positive, so it counts as qualified.
QUALIFIED_CLASSES = {ReplyClass.INTERESTED, ReplyClass.DECK_REQUEST}
#: Automated noise never counts as a reply in any direction.
NON_REPLY_CLASSES = {ReplyClass.AUTO_REPLY, ReplyClass.OOO, ReplyClass.BOUNCE}


@dataclass
class RateBlock:
    label: str
    sends: int = 0
    replies: int = 0
    qualified: int = 0
    deck_requests: int = 0
    passes: int = 0
    bounces: int = 0

    @property
    def reply_rate(self) -> float:
        return self.replies / self.sends if self.sends else 0.0

    @property
    def qualified_rate(self) -> float:
        return self.qualified / self.sends if self.sends else 0.0

    @property
    def bounce_rate(self) -> float:
        return self.bounces / self.sends if self.sends else 0.0

    @property
    def significant(self) -> bool:
        return self.sends >= MIN_SENDS_FOR_RATE_SIGNIFICANCE

    @property
    def verdict(self) -> str:
        """Where this sits against the source's 4% baseline and 13-17% ceiling."""
        if not self.significant:
            return f"insufficient sample ({self.sends}/{MIN_SENDS_FOR_RATE_SIGNIFICANCE} sends)"
        rate = self.qualified_rate
        if rate >= CEILING_REPLY_RATE_HIGH:
            return f"above the {CEILING_REPLY_RATE_HIGH:.0%} ceiling — verify the classifier"
        if rate >= CEILING_REPLY_RATE_LOW:
            return f"in the {CEILING_REPLY_RATE_LOW:.0%}-{CEILING_REPLY_RATE_HIGH:.0%} top band"
        if rate >= BASELINE_REPLY_RATE:
            return f"above the {BASELINE_REPLY_RATE:.0%} baseline, below the top band"
        return f"below the {BASELINE_REPLY_RATE:.0%} baseline — fix targeting or the pitch"

    def row(self) -> dict[str, object]:
        return {
            "label": self.label,
            "sends": self.sends,
            "replies": self.replies,
            "reply_rate": round(self.reply_rate, 4),
            "qualified": self.qualified,
            "qualified_rate": round(self.qualified_rate, 4),
            "deck_requests": self.deck_requests,
            "passes": self.passes,
            "bounce_rate": round(self.bounce_rate, 4),
            "verdict": self.verdict,
        }


@dataclass
class CampaignAnalytics:
    campaign_id: int | None
    overall: RateBlock = field(default_factory=lambda: RateBlock("overall"))
    by_variant: dict[str, RateBlock] = field(default_factory=dict)
    by_cohort: dict[str, RateBlock] = field(default_factory=dict)
    by_touch: dict[int, RateBlock] = field(default_factory=dict)
    reputation_spent: int = 0

    @property
    def qualified_per_100_reputation(self) -> float:
        """The objective function (R0.1), in the units the founder actually feels."""
        if not self.reputation_spent:
            return 0.0
        return round(100 * self.overall.qualified / self.reputation_spent, 2)

    def describe(self) -> str:
        lines = [
            f"Sends: {self.overall.sends}  Replies: {self.overall.replies} "
            f"({self.overall.reply_rate:.1%})  Qualified: {self.overall.qualified} "
            f"({self.overall.qualified_rate:.1%})",
            f"Benchmark: {self.overall.verdict}",
            f"Objective: {self.qualified_per_100_reputation} qualified replies per 100 "
            f"units of reputation spent",
        ]
        if self.by_variant:
            lines.append("By variant:")
            for key, block in sorted(
                self.by_variant.items(), key=lambda kv: -kv[1].qualified_rate
            ):
                lines.append(
                    f"  {key}: {block.sends} sends, {block.qualified_rate:.1%} qualified "
                    f"({block.verdict})"
                )
        return "\n".join(lines)


def campaign_analytics(session: Session, campaign_id: int | None = None) -> CampaignAnalytics:
    """Aggregate the send/reply record into benchmark-relative rates."""
    analytics = CampaignAnalytics(campaign_id=campaign_id)

    sends = list(
        session.exec(
            select(Send).where(
                Send.status.in_(  # type: ignore[attr-defined]
                    [SendStatus.SENT, SendStatus.DRY_RUN, SendStatus.REPLIED, SendStatus.BOUNCED]
                )
            )
        )
    )
    if campaign_id is not None:
        target_ids = {
            t.id for t in session.exec(select(Target).where(Target.campaign_id == campaign_id))
        }
        sends = [s for s in sends if s.target_id in target_ids]

    replies_by_send: dict[int, list[Reply]] = {}
    for reply in session.exec(select(Reply)):
        if reply.send_id is not None:
            replies_by_send.setdefault(reply.send_id, []).append(reply)

    for send in sends:
        blocks = [
            analytics.overall,
            analytics.by_variant.setdefault(
                send.variant_key or "(none)", RateBlock(send.variant_key or "(none)")
            ),
            analytics.by_cohort.setdefault(
                send.cohort or "(none)", RateBlock(send.cohort or "(none)")
            ),
            analytics.by_touch.setdefault(
                send.touch_number, RateBlock(f"touch {send.touch_number}")
            ),
        ]
        analytics.reputation_spent += send.reputation_cost
        classes = {r.classification for r in replies_by_send.get(send.id or -1, [])}
        counted = classes - NON_REPLY_CLASSES

        for block in blocks:
            block.sends += 1
            if counted:
                block.replies += 1
            if classes & QUALIFIED_CLASSES:
                block.qualified += 1
            if ReplyClass.DECK_REQUEST in classes:
                block.deck_requests += 1
            if ReplyClass.PASS in classes:
                block.passes += 1
            if ReplyClass.BOUNCE in classes or send.bounced:
                block.bounces += 1

    return analytics


def funnel(session: Session, campaign_id: int) -> dict[str, int]:
    """Where the campaign loses people, in one dict."""
    targets = list(session.exec(select(Target).where(Target.campaign_id == campaign_id)))
    target_ids = {t.id for t in targets}
    drafts = [d for d in session.exec(select(Draft)) if d.target_id in target_ids]
    sends = [s for s in session.exec(select(Send)) if s.target_id in target_ids]
    replies = [r for r in session.exec(select(Reply)) if r.target_id in target_ids]

    counts: dict[str, int] = {"targets_scored": len(targets)}
    for status in {t.status for t in targets}:
        counts[f"targets_{status.value}"] = sum(1 for t in targets if t.status is status)
    for status in {d.status for d in drafts}:
        counts[f"drafts_{status.value}"] = sum(1 for d in drafts if d.status is status)
    counts["sends"] = len(sends)
    counts["replies"] = len(replies)
    for label in {r.classification for r in replies}:
        counts[f"replies_{label.value}"] = sum(1 for r in replies if r.classification is label)
    return counts

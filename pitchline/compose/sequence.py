"""Follow-up sequences (R4.1-R4.5).

The rule that shapes this module is R4.3: a follow-up must carry a distinct, previously
unused update. If there is nothing new to say, **no follow-up is generated** — the sequence
just ends. That is the whole point: "don't send one email and give up" is advice about
persistence across a well-targeted list, not about bumping one inbox three times.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlmodel import Session, select

from pitchline import events
from pitchline.compose import library
from pitchline.compose.pitch import (
    ComposeError,
    HumanFixRequired,
    _write_hook,
    render_footer,
    render_greeting,
)
from pitchline.guardrails import lint_draft
from pitchline.llm import LLMClient, get_client, stamp
from pitchline.models import (
    Draft,
    DraftStatus,
    EventKind,
    Investor,
    Send,
    SendStatus,
    Sequence,
    SlotKind,
    StartupProfile,
    Target,
    TargetStatus,
    Update,
)
from pitchline.research.store import evidence_payload
from pitchline.rules import (
    ALLOW_UPDATE_REUSE,
    FOLLOWUP_GAP_BUSINESS_DAYS,
    GENERATE_FOLLOWUP_WITHOUT_UPDATE,
    MAX_FOLLOWUPS_PER_TARGET,
    MAX_TOTAL_TOUCHES_PER_TARGET,
    MAX_UPDATE_AGE_DAYS,
    REQUIRE_NEW_INFORMATION,
    RULES_FINGERPRINT,
)
from pitchline.timeutil import add_business_days, age_days, ensure_utc, utcnow


class NoUnusedUpdateError(RuntimeError):
    """R4.3 — nothing new to say, so there is no follow-up to send."""


@dataclass
class DueFollowup:
    target: Target
    touch_number: int
    due_at: datetime


def plan_sequence(session: Session, target: Target) -> Sequence:
    """R4.1 — plan the whole cadence up front so it is visible before the first send."""
    sequence = session.exec(select(Sequence).where(Sequence.target_id == target.id)).first()
    if sequence is None:
        sequence = Sequence(
            target_id=target.id,  # type: ignore[arg-type]
            planned_touches=MAX_TOTAL_TOUCHES_PER_TARGET,
        )
        session.add(sequence)
        session.flush()
    return sequence


def end_sequence(session: Session, sequence: Sequence, reason: str) -> Sequence:
    if sequence.ended:
        return sequence
    sequence.ended = True
    sequence.ended_reason = reason
    sequence.ended_at = utcnow()
    session.add(sequence)
    session.flush()
    events.record(
        session,
        EventKind.SEQUENCE_ENDED,
        entity_type="sequence",
        entity_id=sequence.id,
        summary=reason,
        flush=False,
    )
    return sequence


def available_update(session: Session, profile: StartupProfile) -> Update | None:
    """The next unused, in-date update (R4.3)."""
    statement = select(Update).where(Update.startup_profile_id == profile.id)
    candidates = [
        row
        for row in session.exec(statement)
        if (ALLOW_UPDATE_REUSE or row.consumed_by_draft_id is None)
        and age_days(ensure_utc(datetime.combine(row.occurred_on, datetime.min.time())))
        <= MAX_UPDATE_AGE_DAYS
    ]
    candidates.sort(key=lambda row: row.occurred_on, reverse=True)
    return candidates[0] if candidates else None


def generate_followup(
    session: Session,
    *,
    target: Target,
    profile: StartupProfile,
    touch_number: int | None = None,
    client: LLMClient | None = None,
) -> Draft:
    """Generate the next touch. Raises :class:`NoUnusedUpdateError` if there is no news."""
    client = client or get_client()
    sequence = plan_sequence(session, target)

    sent_touches = _sent_touch_numbers(session, target)
    next_touch = touch_number or (max(sent_touches, default=0) + 1)

    if next_touch < 2:
        raise ComposeError("generate_followup is for touch 2 and later; use compose_first_touch")
    if next_touch > MAX_TOTAL_TOUCHES_PER_TARGET:
        end_sequence(session, sequence, f"reached the {MAX_FOLLOWUPS_PER_TARGET}-follow-up cap (R4.1)")
        raise NoUnusedUpdateError(
            f"R4.1 allows {MAX_FOLLOWUPS_PER_TARGET} follow-ups; touch {next_touch} would exceed it"
        )
    if sequence.ended:
        raise NoUnusedUpdateError(f"sequence already ended: {sequence.ended_reason}")
    if target.status in {TargetStatus.REPLIED, TargetStatus.CLOSED}:
        raise NoUnusedUpdateError("R4.4 — the target has replied; the cold sequence is over")

    update = available_update(session, profile)
    if update is None:
        # R4.3 — this is the point of the rule. No bump-only follow-ups exist in this system.
        if REQUIRE_NEW_INFORMATION and not GENERATE_FOLLOWUP_WITHOUT_UPDATE:
            end_sequence(session, sequence, "no unused update available (R4.3)")
            raise NoUnusedUpdateError(
                "R4.3 — a follow-up must carry a distinct, previously unused update. "
                "Add one to the updates table, or let the sequence end."
            )
        raise NoUnusedUpdateError("no update available")  # pragma: no cover

    investor = session.get(Investor, target.investor_id)
    if investor is None:
        raise ComposeError(f"target {target.id} has no investor")

    evidence = evidence_payload(session, investor.id)  # type: ignore[arg-type]
    if not evidence:
        raise ComposeError(f"{investor.full_name}: no evidence for a sourced follow-up hook (R2.6)")

    first = session.exec(
        select(Draft).where(Draft.target_id == target.id, Draft.touch_number == 1)
    ).first()

    # A different credibility marker on each touch: still R2.3-compliant, not a copy-paste.
    used_cred = {d.credibility_variant_id for d in _drafts_for(session, target)}
    credibility = _pick_credibility(session, used_cred)
    ask = library.shortest(session, SlotKind.ASK)
    hook = _write_hook(session, client, investor, profile, evidence)

    body = "\n\n".join(
        [
            f"{credibility.body_text.strip()} {hook.hook_text.strip()}",
            f"{update.headline.strip().rstrip('.')}: {update.body_text.strip()}",
            ask.body_text.strip(),
        ]
    )

    draft = session.exec(
        select(Draft).where(Draft.target_id == target.id, Draft.touch_number == next_touch)
    ).first() or Draft(target_id=target.id, touch_number=next_touch)  # type: ignore[arg-type]

    draft.sequence_id = sequence.id
    draft.greeting = render_greeting(investor)
    draft.body = body
    draft.footer = render_footer(profile)
    draft.subject = (f"Re: {first.subject}" if first and first.subject else f"{profile.name} — update")[:78]
    draft.word_count = len(f"{draft.greeting} {body}".split())
    draft.credibility_variant_id = credibility.id
    draft.credibility_marker_type = credibility.marker_type
    draft.ask_variant_id = ask.id
    draft.ask_type = ask.ask_type
    draft.problem_variant_id = None
    draft.approach_variant_id = None
    draft.personalization_hook = hook.hook_text
    draft.hook_evidence_id = hook.evidence_id
    draft.evidence_ids = [hook.evidence_id]
    draft.claim_map = [
        {"text": hook.hook_text, "evidence_id": hook.evidence_id, "investor_specific": True},
        {"text": update.body_text, "evidence_id": None, "investor_specific": False},
    ]
    draft.update_id = update.id
    draft.variant_key = f"followup|{update.category}|{ask.key}"
    draft.rules_fingerprint = RULES_FINGERPRINT
    draft.status = DraftStatus.COMPOSING
    draft.scheduled_for = _due_at(session, target, next_touch)
    for key, value in stamp(client, "hook_v1").items():
        setattr(draft, key, value)

    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile, client=client, persist=True)
    if not report.passed:
        draft.status = DraftStatus.NEEDS_HUMAN_FIX
        session.add(draft)
        session.flush()
        events.record(
            session,
            EventKind.ROUTED_TO_HUMAN,
            entity_type="draft",
            entity_id=draft.id,
            campaign_id=target.campaign_id,
            summary=f"follow-up {next_touch} failed the gate",
            payload={"failures": report.as_dicts()},
            flush=False,
        )
        raise HumanFixRequired(draft, report)

    # R4.3 — the update is consumed here, so no other follow-up can reuse it.
    update.consumed_by_draft_id = draft.id
    update.consumed_at = utcnow()
    draft.status = DraftStatus.PENDING_APPROVAL
    sequence.generated_touches = max(sequence.generated_touches, next_touch)
    session.add_all([update, draft, sequence])
    session.flush()

    events.record(
        session,
        EventKind.DRAFTED,
        entity_type="draft",
        entity_id=draft.id,
        campaign_id=target.campaign_id,
        summary=f"touch {next_touch} for {investor.full_name} carrying update {update.id}",
        payload={"update": update.headline, "scheduled_for": str(draft.scheduled_for)},
        flush=False,
    )
    return draft


def due_followups(
    session: Session, *, campaign_id: int, now: datetime | None = None
) -> list[DueFollowup]:
    """Targets whose next touch is due under R4.2 spacing and R4.4 stop conditions."""
    now = now or utcnow()
    due: list[DueFollowup] = []
    targets = list(
        session.exec(
            select(Target).where(
                Target.campaign_id == campaign_id,
                Target.status.in_([TargetStatus.IN_SEQUENCE, TargetStatus.QUALIFIED]),  # type: ignore[attr-defined]
            )
        )
    )
    for target in targets:
        sends = _sends_for(session, target)
        if not sends:
            continue
        if any(s.replied or s.bounced for s in sends):
            continue  # R4.4
        touches = max(s.touch_number for s in sends)
        if touches >= MAX_TOTAL_TOUCHES_PER_TARGET:
            continue
        last_sent = max(ensure_utc(s.sent_at) or ensure_utc(s.scheduled_for) or now for s in sends)
        gap_index = min(touches - 1, len(FOLLOWUP_GAP_BUSINESS_DAYS) - 1)
        due_at = add_business_days(last_sent, FOLLOWUP_GAP_BUSINESS_DAYS[gap_index])
        if due_at <= now:
            due.append(DueFollowup(target=target, touch_number=touches + 1, due_at=due_at))
    return due


# --------------------------------------------------------------------------------------
# Internals
# --------------------------------------------------------------------------------------


def _pick_credibility(session: Session, used_ids: set[int | None]):
    options = library.active_variants(session, SlotKind.CREDIBILITY)
    if not options:
        raise ComposeError("no credibility variants registered (R2.3)")
    fresh = [v for v in options if v.id not in used_ids]
    return min(fresh or options, key=lambda v: (len(v.body_text.split()), v.key))


def _drafts_for(session: Session, target: Target) -> list[Draft]:
    return list(session.exec(select(Draft).where(Draft.target_id == target.id)))


def _sends_for(session: Session, target: Target) -> list[Send]:
    return [
        s
        for s in session.exec(select(Send).where(Send.target_id == target.id))
        if s.status in {SendStatus.SENT, SendStatus.DRY_RUN, SendStatus.REPLIED, SendStatus.BOUNCED}
    ]


def _sent_touch_numbers(session: Session, target: Target) -> list[int]:
    return [s.touch_number for s in _sends_for(session, target)]


def _due_at(session: Session, target: Target, touch_number: int) -> datetime:
    sends = _sends_for(session, target)
    last = max(
        (ensure_utc(s.sent_at) or ensure_utc(s.scheduled_for) for s in sends if s.sent_at or s.scheduled_for),
        default=utcnow(),
    )
    gap_index = min(touch_number - 2, len(FOLLOWUP_GAP_BUSINESS_DAYS) - 1)
    return add_business_days(last, FOLLOWUP_GAP_BUSINESS_DAYS[gap_index])

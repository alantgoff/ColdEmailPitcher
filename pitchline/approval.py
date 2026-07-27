"""The approval queue (R6.1) — built before the sender, on purpose.

Human-in-the-loop is structural here, not a setting. ``approve`` is the only function in
the codebase that can set ``approved_by``/``approved_at``, it refuses non-human actors, and
it refuses a draft that has not cleared the guardrails. Editing a draft clears its approval
and re-runs the gate, because approval attaches to specific words, not to a row id.
"""

from __future__ import annotations

from sqlmodel import Session, select

from pitchline import events
from pitchline.guardrails import LintReport, lint_draft
from pitchline.llm import LLMClient
from pitchline.models import Draft, DraftStatus, EventKind, StartupProfile, Target
from pitchline.rules import (
    ALLOW_BATCH_APPROVAL,
    EDIT_INVALIDATES_APPROVAL,
    MODEL_MAY_APPROVE,
    REQUIRE_APPROVED_AT,
    REQUIRE_APPROVED_BY,
)
from pitchline.timeutil import utcnow

#: R6.1 — a model may not approve its own output.
_NON_HUMAN_ACTORS = {
    "system", "model", "llm", "anthropic", "claude", "offline", "auto", "pitchline", "bot",
}


class ApprovalError(RuntimeError):
    """The approval was refused. The message says why."""


def queue(
    session: Session,
    *,
    campaign_id: int | None = None,
    statuses: tuple[DraftStatus, ...] = (DraftStatus.PENDING_APPROVAL,),
    limit: int | None = None,
) -> list[Draft]:
    """Drafts waiting on a human, newest last so the founder works a stable order."""
    statement = select(Draft).where(Draft.status.in_(list(statuses)))  # type: ignore[attr-defined]
    drafts = list(session.exec(statement))
    if campaign_id is not None:
        target_ids = {
            t.id for t in session.exec(select(Target).where(Target.campaign_id == campaign_id))
        }
        drafts = [d for d in drafts if d.target_id in target_ids]
    drafts.sort(key=lambda d: (d.touch_number, d.id or 0))
    return drafts[:limit] if limit else drafts


def approve(session: Session, draft: Draft, *, approved_by: str) -> Draft:
    """Record explicit per-email approval. The only path to a sendable draft."""
    actor = (approved_by or "").strip()
    if REQUIRE_APPROVED_BY and not actor:
        raise ApprovalError("R6.1 requires a named approver")
    if not MODEL_MAY_APPROVE and actor.lower() in _NON_HUMAN_ACTORS:
        raise ApprovalError(
            f"R6.1 — {actor!r} is not a human approver; a model may not approve its own draft"
        )
    if draft.status not in {DraftStatus.PENDING_APPROVAL, DraftStatus.APPROVED}:
        raise ApprovalError(
            f"draft {draft.id} is {draft.status.value}; only a draft that has cleared the "
            "guardrails can be approved"
        )

    draft.approved_by = actor
    if REQUIRE_APPROVED_AT:
        draft.approved_at = utcnow()
    draft.status = DraftStatus.APPROVED
    draft.rejected_by = None
    draft.rejected_at = None
    draft.reject_reason = None
    session.add(draft)
    session.flush()
    events.record(
        session,
        EventKind.APPROVED,
        entity_type="draft",
        entity_id=draft.id,
        summary=f"approved by {actor}",
        actor=actor,
        flush=False,
    )
    return draft


def approve_many(session: Session, drafts: list[Draft], *, approved_by: str) -> list[Draft]:
    """Convenience for the UI. Still one explicit approval per email (R6.1)."""
    if not ALLOW_BATCH_APPROVAL and len(drafts) > 1:
        raise ApprovalError(
            "R6.1 forbids batch approval — each email is approved individually. "
            "Call approve() per draft from the review UI."
        )
    return [approve(session, draft, approved_by=approved_by) for draft in drafts]


def reject(session: Session, draft: Draft, *, rejected_by: str, reason: str) -> Draft:
    actor = (rejected_by or "").strip()
    if not actor:
        raise ApprovalError("a rejection needs a named rejecter")
    draft.status = DraftStatus.REJECTED
    draft.rejected_by = actor
    draft.rejected_at = utcnow()
    draft.reject_reason = reason
    draft.approved_by = None
    draft.approved_at = None
    session.add(draft)
    session.flush()
    events.record(
        session,
        EventKind.REJECTED,
        entity_type="draft",
        entity_id=draft.id,
        summary=f"rejected by {actor}: {reason[:160]}",
        actor=actor,
        flush=False,
    )
    return draft


def edit(
    session: Session,
    draft: Draft,
    *,
    edited_by: str,
    body: str | None = None,
    subject: str | None = None,
    profile: StartupProfile | None = None,
    client: LLMClient | None = None,
) -> tuple[Draft, LintReport]:
    """Apply a founder edit, drop any approval, and re-run the gate.

    An edited draft is a different email. R6.1 ``edit_invalidates_approval`` exists so a
    founder cannot approve a clean draft and then paste in a link.
    """
    actor = (edited_by or "").strip()
    if not actor:
        raise ApprovalError("an edit needs a named editor")
    if body is not None:
        draft.body = body
        draft.word_count = len(f"{draft.greeting} {body}".split())
    if subject is not None:
        draft.subject = subject
    draft.edited_by = actor
    draft.edited_at = utcnow()
    if EDIT_INVALIDATES_APPROVAL:
        draft.approved_by = None
        draft.approved_at = None
    session.add(draft)
    session.flush()

    report = lint_draft(session, draft, profile=profile, client=client, persist=True)
    draft.status = DraftStatus.PENDING_APPROVAL if report.passed else DraftStatus.NEEDS_HUMAN_FIX
    session.add(draft)
    session.flush()
    events.record(
        session,
        EventKind.EDITED,
        entity_type="draft",
        entity_id=draft.id,
        summary=f"edited by {actor}; re-lint {'passed' if report.passed else 'failed'}",
        payload={"failures": report.as_dicts()},
        actor=actor,
        flush=False,
    )
    return draft, report

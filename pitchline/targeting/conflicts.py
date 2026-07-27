"""R1.5 — direct portfolio conflicts are suppressed by default.

Two properties this module guarantees:

* Suppression is the *default*. A target with a detected conflict is not sendable unless
  an override exists, and the override must carry a named human, a written reason and a
  timestamp. A model can never produce one — ``override_conflict`` takes ``approved_by``
  as a required argument and refuses anything that looks automated.
* Enforcement happens twice: here at scoring time, and again at dispatch (R1.5
  ``enforce_at_dispatch``), so a target scored before a conflict was discovered still
  cannot be sent to.
"""

from __future__ import annotations

from sqlmodel import Session

from pitchline import events
from pitchline.models import EventKind, Target, TargetStatus
from pitchline.rules import (
    CONFLICT_OVERRIDE_ALLOWED,
    CONFLICT_OVERRIDE_REQUIRES_HUMAN,
    CONFLICT_OVERRIDE_REQUIRES_REASON,
    MODEL_MAY_OVERRIDE_CONFLICT,
    SUPPRESS_DIRECT_CONFLICT,
)
from pitchline.timeutil import utcnow

#: Actors that are not humans. R1.5 forbids a model-authored override.
_NON_HUMAN_ACTORS = {"system", "model", "llm", "anthropic", "offline", "auto", "pitchline"}


class ConflictOverrideError(RuntimeError):
    """An override was attempted without the human, reason or timestamp R1.5 requires."""


def apply_portfolio_conflict_suppression(session: Session, target: Target) -> Target:
    """Set the target's status from its conflict state. Idempotent."""
    if not SUPPRESS_DIRECT_CONFLICT:  # pragma: no cover - rules file would have to change
        return target

    if target.has_portfolio_conflict and not target.conflict_overridden:
        if target.status is not TargetStatus.SUPPRESSED_CONFLICT:
            target.status = TargetStatus.SUPPRESSED_CONFLICT
            target.suppressed_reason = (
                "direct portfolio conflict: " + ", ".join(target.conflict_companies)
            )
            session.add(target)
            session.flush()
            events.record(
                session,
                EventKind.SUPPRESSED,
                entity_type="target",
                entity_id=target.id,
                campaign_id=target.campaign_id,
                summary=target.suppressed_reason,
                payload={"companies": target.conflict_companies},
                flush=False,
            )
    return target


def override_conflict(
    session: Session,
    target: Target,
    *,
    approved_by: str,
    reason: str,
) -> Target:
    """Explicitly override a conflict suppression. Human-only, reason-required."""
    if not CONFLICT_OVERRIDE_ALLOWED:  # pragma: no cover - rules file would have to change
        raise ConflictOverrideError("R1.5 forbids overriding portfolio conflicts")
    actor = (approved_by or "").strip()
    if CONFLICT_OVERRIDE_REQUIRES_HUMAN and (
        not actor or (not MODEL_MAY_OVERRIDE_CONFLICT and actor.lower() in _NON_HUMAN_ACTORS)
    ):
        raise ConflictOverrideError(
            "R1.5 requires a named human to override a portfolio conflict; "
            f"got approved_by={approved_by!r}"
        )
    if CONFLICT_OVERRIDE_REQUIRES_REASON and not (reason or "").strip():
        raise ConflictOverrideError("R1.5 requires a written reason to override a conflict")

    target.conflict_override_by = actor
    target.conflict_override_reason = reason.strip()
    target.conflict_override_at = utcnow()
    target.status = TargetStatus.QUALIFIED
    target.suppressed_reason = None
    session.add(target)
    session.flush()
    events.record(
        session,
        EventKind.CONFLICT_OVERRIDDEN,
        entity_type="target",
        entity_id=target.id,
        campaign_id=target.campaign_id,
        summary=f"{actor} overrode conflict: {reason.strip()[:160]}",
        payload={"companies": target.conflict_companies},
        actor=actor,
        flush=False,
    )
    return target

"""Append-only audit trail.

Design principle 4 — every send is an experiment record — generalises: every decision the
engine makes is recorded, so a campaign can be reconstructed after the fact and a refusal
can always be explained.
"""

from __future__ import annotations

from typing import Any

from sqlmodel import Session

from pitchline.models import Event, EventKind


def record(
    session: Session,
    kind: EventKind,
    *,
    entity_type: str,
    entity_id: int | None = None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
    campaign_id: int | None = None,
    actor: str = "system",
    flush: bool = True,
) -> Event:
    event = Event(
        kind=kind,
        entity_type=entity_type,
        entity_id=entity_id,
        summary=summary,
        payload=payload or {},
        campaign_id=campaign_id,
        actor=actor,
    )
    session.add(event)
    if flush:
        session.flush()
    return event

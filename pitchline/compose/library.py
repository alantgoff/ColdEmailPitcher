"""The founder-authored variant library.

Every word that goes into a pitch — except the one personalization hook — comes from here.
The library is versioned and tagged, so "variant B outperformed variant A" is a statement
about copy the founder wrote, not about a sampling temperature.
"""

from __future__ import annotations

from typing import Any, Sequence

from sqlmodel import Session, select

from pitchline.models import PitchVariant, SlotKind, StartupProfile
from pitchline.rules import ALLOWED_ASK_TYPES, CREDIBILITY_MARKER_TYPES, PITCH_SLOTS


class VariantLibraryError(RuntimeError):
    """The library cannot satisfy a slot — composition cannot proceed."""


def active_variants(
    session: Session, slot: SlotKind, *, profile_id: int | None = None
) -> list[PitchVariant]:
    statement = select(PitchVariant).where(
        PitchVariant.slot == slot, PitchVariant.active == True  # noqa: E712
    )
    rows = list(session.exec(statement))
    if profile_id is not None:
        scoped = [r for r in rows if r.startup_profile_id in (None, profile_id)]
        rows = scoped or rows
    return sorted(rows, key=lambda r: r.key)


def variants_payload(session: Session, *, profile_id: int | None = None) -> dict[str, list[dict[str, Any]]]:
    """Serialise the library for the selection call. The model sees keys, never writes copy."""
    payload: dict[str, list[dict[str, Any]]] = {}
    for slot_name in PITCH_SLOTS:
        slot = SlotKind(slot_name)
        options = active_variants(session, slot, profile_id=profile_id)
        if not options:
            raise VariantLibraryError(
                f"no active pitch variants for slot {slot_name!r}; the founder writes the copy "
                "(R2.2) so composition cannot proceed"
            )
        payload[slot_name] = [
            {
                "key": v.key,
                "label": v.label,
                "text": v.body_text,
                "sectors": v.sectors,
                "stages": v.stages,
                "marker_type": v.marker_type,
                "ask_type": v.ask_type,
                "words": len(v.body_text.split()),
            }
            for v in options
        ]
    return payload


def by_key(session: Session, slot: SlotKind, key: str) -> PitchVariant:
    variant = session.exec(
        select(PitchVariant).where(PitchVariant.slot == slot, PitchVariant.key == key)
    ).first()
    if variant is None:
        raise VariantLibraryError(f"no {slot.value} variant with key {key!r}")
    return variant


def shortest(session: Session, slot: SlotKind, *, exclude: Sequence[str] = ()) -> PitchVariant:
    """Repair strategy for a length failure: the same slot, fewer words."""
    options = [v for v in active_variants(session, slot) if v.key not in exclude]
    if not options:
        raise VariantLibraryError(f"no remaining {slot.value} variants to fall back to")
    return min(options, key=lambda v: (len(v.body_text.split()), v.key))


def next_alternative(
    session: Session, slot: SlotKind, *, exclude: Sequence[str] = ()
) -> PitchVariant:
    """Repair strategy for a novelty failure: a different angle from the same slot."""
    options = [v for v in active_variants(session, slot) if v.key not in exclude]
    if not options:
        raise VariantLibraryError(
            f"no unused {slot.value} variants left; write another one rather than resending "
            "copy that already failed the novelty gate (R2.4)"
        )
    return options[0]


def seed_default_library(session: Session, profile: StartupProfile) -> int:
    """Seed a starter library derived from the founder's own profile.

    These are scaffolding, not ghost-written copy: the text is assembled from facts the
    founder already entered (credibility markers, one-liner, competitors). The founder is
    expected to rewrite them — but the pipeline must be runnable on day one.
    """
    created = 0
    existing = {(v.slot, v.key) for v in session.exec(select(PitchVariant))}

    def add(slot: SlotKind, key: str, label: str, text: str, **kwargs: Any) -> None:
        nonlocal created
        if (slot, key) in existing:
            return
        session.add(
            PitchVariant(
                startup_profile_id=profile.id,
                slot=slot,
                key=key,
                label=label,
                body_text=text.strip(),
                sectors=profile.sectors,
                stages=[profile.stage.value],
                **kwargs,
            )
        )
        created += 1

    for index, marker in enumerate(profile.credibility_markers or [], start=1):
        marker_type = str(marker.get("type", "domain_expertise"))
        if marker_type not in CREDIBILITY_MARKER_TYPES:
            marker_type = "domain_expertise"
        add(
            SlotKind.CREDIBILITY,
            f"cred_{index}",
            marker.get("label", f"credibility {index}"),
            str(marker.get("text", "")),
            marker_type=marker_type,
        )

    add(
        SlotKind.PROBLEM,
        "problem_default",
        "core problem",
        f"{profile.one_liner}",
    )
    add(
        SlotKind.APPROACH,
        "approach_default",
        "core approach",
        "Our approach is different because we start from the data nobody else has.",
    )
    for key, ask_type, text in (
        ("ask_share_more", "offer_to_share_more", "Worth me sending a short summary?"),
        ("ask_deck", "deck_offer", "Happy to send the deck if it is useful."),
        (
            "ask_quick_call",
            "quick_call_in_next_week_or_two",
            "Open to a quick call in the next week or two if this is relevant.",
        ),
    ):
        if ask_type in ALLOWED_ASK_TYPES:
            add(SlotKind.ASK, key, ask_type.replace("_", " "), text, ask_type=ask_type)

    if created:
        session.flush()
    return created

"""Founder profile packs.

A pack is one company's complete setup: the startup profile, the founder-authored variant
library, the dated updates that feed follow-ups, the competitor list that drives R1.5
conflict suppression, and the sending mailboxes.

Packs are the boundary between "the engine" and "your company". Everything a pack contains
is founder-authored copy and founder-asserted fact — the engine selects between variants
and cites evidence, it never writes the claims.
"""

from __future__ import annotations

from typing import Callable, Protocol

from sqlmodel import Session

from pitchline.models import StartupProfile


class ProfilePack(Protocol):
    key: str
    company: str

    def seed_all(self, session: Session, **kwargs) -> StartupProfile: ...


_PACKS: dict[str, Callable[..., StartupProfile]] = {}
_LABELS: dict[str, str] = {}


def register(key: str, label: str, seeder: Callable[..., StartupProfile]) -> None:
    _PACKS[key] = seeder
    _LABELS[key] = label


def available() -> dict[str, str]:
    return dict(_LABELS)


def seed(key: str, session: Session, **kwargs) -> StartupProfile:
    if key not in _PACKS:
        raise KeyError(f"unknown profile pack {key!r}; available: {sorted(_PACKS)}")
    return _PACKS[key](session, **kwargs)


# Registration happens on import so the CLI can list packs without importing each module.
from pitchline.profiles import prime_after_dark as _prime_after_dark  # noqa: E402
from pitchline import demo as _demo  # noqa: E402

register("prime-after-dark", "Prime After Dark — Miami late-night delivery", _prime_after_dark.seed_all)
register("meridian", "Meridian — demo/reference pack", _demo.seed_all)

__all__ = ["ProfilePack", "available", "register", "seed"]

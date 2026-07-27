"""The global suppression list (R5.2).

Checked at scoring time as a courtesy and immediately before every dispatch as a
requirement. Nothing bypasses it — not an approved draft, not a queued send, not an
operator in a hurry. ``pass`` replies land here permanently (R4.4).
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from pitchline import events, textutil as tu
from pitchline.models import (
    EventKind,
    Firm,
    Investor,
    Suppression,
    SuppressionReason,
    SuppressionScope,
)


@dataclass(frozen=True)
class SuppressionHit:
    scope: SuppressionScope
    value: str
    reason: SuppressionReason
    suppression_id: int | None = None

    def describe(self) -> str:
        return f"{self.scope.value}:{self.value} ({self.reason.value})"


def add(
    session: Session,
    *,
    value: str,
    scope: SuppressionScope = SuppressionScope.EMAIL,
    reason: SuppressionReason = SuppressionReason.MANUAL,
    permanent: bool = True,
    investor_id: int | None = None,
    firm_id: int | None = None,
    source: str = "system",
    notes: str | None = None,
) -> Suppression:
    """Idempotent: suppressing an already-suppressed value updates the reason, never
    creates a second row."""
    normalized = _normalize(value, scope)
    existing = session.exec(
        select(Suppression).where(Suppression.scope == scope, Suppression.value == normalized)
    ).first()
    if existing:
        if permanent and not existing.permanent:
            existing.permanent = True
        session.flush()
        return existing

    suppression = Suppression(
        scope=scope,
        value=normalized,
        reason=reason,
        permanent=permanent,
        investor_id=investor_id,
        firm_id=firm_id,
        source=source,
        notes=notes,
    )
    session.add(suppression)
    session.flush()
    events.record(
        session,
        EventKind.SUPPRESSED,
        entity_type="suppression",
        entity_id=suppression.id,
        summary=f"{scope.value}:{normalized} suppressed ({reason.value})",
        payload={"permanent": permanent, "source": source},
        flush=False,
    )
    return suppression


def suppress_investor(
    session: Session,
    investor: Investor,
    *,
    reason: SuppressionReason,
    permanent: bool = True,
    notes: str | None = None,
    source: str = "system",
) -> Suppression:
    """Suppress by email where known, and always by investor id so a later email change
    cannot resurrect the contact."""
    if investor.email:
        add(
            session,
            value=investor.email,
            scope=SuppressionScope.EMAIL,
            reason=reason,
            permanent=permanent,
            investor_id=investor.id,
            firm_id=investor.firm_id,
            notes=notes,
            source=source,
        )
    return add(
        session,
        value=str(investor.id),
        scope=SuppressionScope.INVESTOR,
        reason=reason,
        permanent=permanent,
        investor_id=investor.id,
        firm_id=investor.firm_id,
        notes=notes,
        source=source,
    )


def check(
    session: Session,
    *,
    email: str | None = None,
    investor: Investor | None = None,
    firm: Firm | None = None,
) -> SuppressionHit | None:
    """Return the first matching suppression, or ``None``.

    Checks every scope in R5.2: email, domain, investor, firm.
    """
    candidates: list[tuple[SuppressionScope, str]] = []
    address = tu.normalize_email(email or (investor.email if investor else None))
    if address:
        candidates.append((SuppressionScope.EMAIL, address))
        domain = tu.email_domain(address)
        if domain:
            candidates.append((SuppressionScope.DOMAIN, domain))
    if investor is not None and investor.id is not None:
        candidates.append((SuppressionScope.INVESTOR, str(investor.id)))
    firm_name = firm.name if firm else None
    if firm_name:
        candidates.append((SuppressionScope.FIRM, tu.normalize_firm_name(firm_name)))

    for scope, value in candidates:
        row = session.exec(
            select(Suppression).where(Suppression.scope == scope, Suppression.value == value)
        ).first()
        if row:
            return SuppressionHit(
                scope=row.scope, value=row.value, reason=row.reason, suppression_id=row.id
            )
    return None


def is_suppressed(session: Session, **kwargs) -> bool:
    return check(session, **kwargs) is not None


def _normalize(value: str, scope: SuppressionScope) -> str:
    if scope is SuppressionScope.EMAIL:
        return tu.normalize_email(value)
    if scope is SuppressionScope.DOMAIN:
        return value.strip().lower().lstrip("@")
    if scope is SuppressionScope.FIRM:
        return tu.normalize_firm_name(value)
    return str(value).strip()

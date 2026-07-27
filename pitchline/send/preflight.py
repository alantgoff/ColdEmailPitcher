"""Everything that must be true before a message can be dispatched.

Each refusal is its own exception type so a caller can tell "not approved yet" from "this
person asked never to be contacted again" — operationally very different problems.

Order is deliberate: cheap structural checks first, then the checks whose failure means
*never send this* (suppression, conflict), then timing. The suppression check runs again in
the sender immediately before dispatch (R5.2), because between preflight and dispatch a
reply could have arrived.
"""

from __future__ import annotations

from datetime import datetime

from sqlmodel import Session

from pitchline import suppression
from pitchline.models import Draft, DraftStatus, EmailConfidence, Firm, Investor, Mailbox, Target
from pitchline.rules import (
    APPROVAL_CANNOT_BYPASS_SUPPRESSION,
    DEFER_ON_UNKNOWN_TIMEZONE,
    DRY_RUN_EXEMPT_FROM_APPROVAL,
    ENFORCE_CONFLICT_AT_DISPATCH,
    FORBID_FREEMAIL_SENDERS,
    REQUIRE_PER_EMAIL_APPROVAL,
    is_freemail_sender,
    is_generic_mailbox,
    is_within_send_window,
)
from pitchline.timeutil import resolve_timezone, utcnow


class SendRefused(RuntimeError):
    """Base class for every dispatch refusal."""


class UnapprovedDraftError(SendRefused):
    """R6.1 — no ``approved_by``/``approved_at``, no send."""


class SuppressedRecipientError(SendRefused):
    """R5.2 — the recipient is on the global suppression list."""


class PortfolioConflictError(SendRefused):
    """R1.5 — the fund holds a direct competitor and no human overrode it."""


class OutsideSendWindowError(SendRefused):
    """R4.5 — outside Tue-Thu 07:00-10:00 recipient-local."""


class UnknownTimezoneError(SendRefused):
    """R4.5 — recipient timezone unknown, so the send is deferred rather than guessed."""


class GuardrailNotPassedError(SendRefused):
    """The draft never cleared the gate."""


class InvalidSenderError(SendRefused):
    """R3.2 — the sending identity is not on a dedicated professional domain."""


class MissingRecipientError(SendRefused):
    """No usable recipient address."""


class UnverifiedRecipientError(SendRefused):
    """The address has never been verified, so sending it risks a bounce.

    Bounces are not a per-message cost — they degrade the sending domain for every other
    recipient on the list. Guessing is therefore refused by default rather than attempted.
    """


def preflight(
    session: Session,
    *,
    draft: Draft,
    target: Target,
    investor: Investor,
    mailbox: Mailbox | None = None,
    dry_run: bool = True,
    now: datetime | None = None,
    enforce_window: bool = True,
) -> None:
    """Raise the first applicable :class:`SendRefused`. Returns ``None`` when clear."""
    now = now or utcnow()

    # 1. The draft must have cleared the guardrails.
    if draft.status in {DraftStatus.GUARDRAIL_FAILED, DraftStatus.NEEDS_HUMAN_FIX, DraftStatus.COMPOSING}:
        raise GuardrailNotPassedError(
            f"draft {draft.id} is {draft.status.value}; only a draft that passed every "
            "guardrail may be queued for sending"
        )
    if draft.status is DraftStatus.REJECTED:
        raise GuardrailNotPassedError(f"draft {draft.id} was rejected by {draft.rejected_by}")

    # 2. Human approval (R6.1). Dry runs are exempt so the pipeline is testable end to end.
    if REQUIRE_PER_EMAIL_APPROVAL and not (dry_run and DRY_RUN_EXEMPT_FROM_APPROVAL):
        if not draft.is_approved:
            raise UnapprovedDraftError(
                f"draft {draft.id} has approved_by={draft.approved_by!r} and "
                f"approved_at={draft.approved_at!r}. R6.1 requires explicit per-email human "
                "approval before a live send; nothing sends autonomously."
            )

    # 3. Recipient sanity.
    if not investor.email:
        raise MissingRecipientError(f"{investor.full_name} has no email address")
    if is_generic_mailbox(investor.email):
        raise MissingRecipientError(
            f"{investor.email} is a shared inbox; R1.4 targets named individuals"
        )

    # 4. Suppression (R5.2) — approval cannot bypass this.
    firm = session.get(Firm, investor.firm_id) if investor.firm_id else None
    hit = suppression.check(session, investor=investor, firm=firm)
    if hit and APPROVAL_CANNOT_BYPASS_SUPPRESSION:
        raise SuppressedRecipientError(
            f"{investor.email} is suppressed ({hit.describe()}). R5.2 — a queued, approved "
            "draft does not override the suppression list."
        )

    # 5. Portfolio conflict, re-checked at dispatch (R1.5).
    if ENFORCE_CONFLICT_AT_DISPATCH and target.has_portfolio_conflict and not target.conflict_overridden:
        raise PortfolioConflictError(
            f"{investor.full_name}'s fund holds "
            f"{', '.join(target.conflict_companies) or 'a direct competitor'}; R1.5 suppresses "
            "unless a named human overrides with a written reason."
        )

    # 6. Address verification. Deliberately AFTER suppression and conflict: "never contact
    #    this person" and "this fund holds a competitor" are permanent refusals, and they
    #    should be reported as such rather than masked by a fixable data-quality problem.
    if not dry_run and investor.email_confidence is not EmailConfidence.VERIFIED:
        raise UnverifiedRecipientError(
            f"{investor.email} is {investor.email_confidence.value}, not verified. A bounce "
            "degrades the sending domain for every other recipient on the list, so an "
            "unverified address is refused rather than guessed. Verify it, then set "
            "email_confidence=verified."
        )

    # 7. Sending identity (R3.2).
    if mailbox is not None:
        if not mailbox.active:
            raise InvalidSenderError(f"mailbox {mailbox.email} is inactive")
        if FORBID_FREEMAIL_SENDERS and is_freemail_sender(mailbox.email):
            raise InvalidSenderError(
                f"{mailbox.email} is a free-provider address; R3.2 requires a dedicated "
                "professional sending domain"
            )

    # 8. Send window (R4.5).
    if enforce_window:
        tz = resolve_timezone(investor.timezone)
        if tz is None:
            if DEFER_ON_UNKNOWN_TIMEZONE:
                raise UnknownTimezoneError(
                    f"{investor.full_name} has no known timezone; R4.5 defers rather than "
                    "guessing the recipient's morning."
                )
        elif not is_within_send_window(now.astimezone(tz)):
            local = now.astimezone(tz)
            raise OutsideSendWindowError(
                f"{local:%a %H:%M} in {investor.timezone} is outside the R4.5 window "
                "(Tue-Thu 07:00-10:00 recipient-local)"
            )

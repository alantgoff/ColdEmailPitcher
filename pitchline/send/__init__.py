"""Module 6 — the reputation-budgeted sender.

Reputation is a depletable budget and the sender refuses to overdraw it. Nothing here
sends autonomously: a draft without a human approval is refused in non-dry-run mode, and
the suppression list is re-checked in the last statement before dispatch.
"""

from pitchline.send.budget import ReputationBudget, ReputationBudgetExceeded, quota_for
from pitchline.send.preflight import (
    GuardrailNotPassedError,
    OutsideSendWindowError,
    PortfolioConflictError,
    SendRefused,
    SuppressedRecipientError,
    UnapprovedDraftError,
    UnknownTimezoneError,
    preflight,
)
from pitchline.send.transport import (
    DryRunTransport,
    FileTransport,
    GmailTransport,
    SMTPTransport,
    Transport,
    build_message,
)
from pitchline.send.sender import SendReport, Sender
from pitchline.send.monitor import DeliverabilityAlarm, WindowStats, check_deliverability

__all__ = [
    "ReputationBudget",
    "ReputationBudgetExceeded",
    "quota_for",
    "SendRefused",
    "UnapprovedDraftError",
    "SuppressedRecipientError",
    "PortfolioConflictError",
    "OutsideSendWindowError",
    "GuardrailNotPassedError",
    "UnknownTimezoneError",
    "preflight",
    "Transport",
    "DryRunTransport",
    "FileTransport",
    "SMTPTransport",
    "GmailTransport",
    "build_message",
    "Sender",
    "SendReport",
    "DeliverabilityAlarm",
    "WindowStats",
    "check_deliverability",
]

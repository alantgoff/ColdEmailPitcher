"""Transports and MIME construction.

R3.1 is enforced here structurally rather than by review: ``build_message`` produces a
single ``text/plain`` part. There is no code path that attaches a file, adds an HTML
alternative, or inserts a tracking pixel — not a flag that defaults to off, no path at all.

Four transports:

``DryRunTransport``  records and discards. The default.
``FileTransport``    writes ``.eml`` files — a real artefact to inspect before going live.
``SMTPTransport``    any SMTP relay, STARTTLS.
``GmailTransport``   Gmail API on the dedicated secondary domain (R3.2).
"""

from __future__ import annotations

import smtplib
import ssl
import uuid
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from pathlib import Path
from typing import Protocol

from pitchline.rules import ALLOW_HTML_PART, MAX_ATTACHMENTS, MIME_TYPE
from pitchline.textutil import find_images


class TransportError(RuntimeError):
    """Delivery failed. The reputation debit is refunded by the sender."""


def build_message(
    *,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    body: str,
    reply_to: str | None = None,
    in_reply_to: str | None = None,
    references: str | None = None,
) -> EmailMessage:
    """Build a plain-text message. R3.1: one part, no HTML, no attachments, no pixel."""
    if ALLOW_HTML_PART or MIME_TYPE != "text/plain":  # pragma: no cover - rules would change
        raise TransportError("R3.1 permits plain text only")
    if images := find_images(body):
        raise TransportError(f"R3.1 forbids embedded images; found {images[:2]}")

    message = EmailMessage()
    message["From"] = formataddr((from_name, from_email)) if from_name else from_email
    message["To"] = to_email
    message["Subject"] = subject
    message["Message-ID"] = make_msgid(domain=from_email.rsplit("@", 1)[-1])
    if reply_to:
        message["Reply-To"] = reply_to
    if in_reply_to:
        # Threading the follow-up onto the original keeps the conversation in one place.
        message["In-Reply-To"] = in_reply_to
        message["References"] = references or in_reply_to
    message.set_content(body, subtype="plain", charset="utf-8")

    if message.is_multipart():  # pragma: no cover - unreachable; kept as a structural assert
        raise TransportError(f"R3.1 allows {MAX_ATTACHMENTS} attachments and no alternative parts")
    return message


@dataclass
class Delivery:
    provider_message_id: str
    thread_id: str | None = None
    detail: str = ""


class Transport(Protocol):
    name: str
    live: bool

    def deliver(self, message: EmailMessage) -> Delivery: ...


@dataclass
class DryRunTransport:
    """Records what would have been sent. Nothing leaves the process."""

    name: str = "dry_run"
    live: bool = False
    outbox: list[EmailMessage] = field(default_factory=list)

    def deliver(self, message: EmailMessage) -> Delivery:
        self.outbox.append(message)
        return Delivery(
            provider_message_id=message["Message-ID"] or f"dryrun-{uuid.uuid4().hex[:12]}",
            detail="dry run — not dispatched",
        )

    def last_body(self) -> str:
        return self.outbox[-1].get_content() if self.outbox else ""


@dataclass
class FileTransport:
    """Writes each message to disk as ``.eml``. Useful for a final human read-through."""

    directory: Path = Path("outbox")
    name: str = "file"
    live: bool = False

    def deliver(self, message: EmailMessage) -> Delivery:
        self.directory.mkdir(parents=True, exist_ok=True)
        message_id = message["Message-ID"] or make_msgid()
        safe = message_id.strip("<>").replace("/", "_").replace("@", "_at_")
        path = self.directory / f"{safe}.eml"
        path.write_bytes(bytes(message))
        return Delivery(provider_message_id=message_id, detail=str(path))


@dataclass
class SMTPTransport:
    """Plain SMTP with STARTTLS."""

    host: str
    port: int = 587
    username: str | None = None
    password: str | None = None
    name: str = "smtp"
    live: bool = True

    def deliver(self, message: EmailMessage) -> Delivery:
        try:
            with smtplib.SMTP(self.host, self.port, timeout=30) as server:
                server.starttls(context=ssl.create_default_context())
                if self.username and self.password:
                    server.login(self.username, self.password)
                server.send_message(message)
        except Exception as exc:
            raise TransportError(f"SMTP delivery failed: {exc}") from exc
        return Delivery(provider_message_id=message["Message-ID"] or make_msgid())


@dataclass
class GmailTransport:
    """Gmail API on the dedicated secondary domain (R3.2).

    Credentials come from a service-account or OAuth token file the operator configures;
    nothing here prompts for or stores a password.
    """

    credentials_path: str | None = None
    token_path: str | None = None
    user_id: str = "me"
    name: str = "gmail"
    live: bool = True
    _service: object | None = None

    SCOPES = ("https://www.googleapis.com/auth/gmail.send",)

    def _build_service(self):
        if self._service is not None:
            return self._service
        try:
            from google.oauth2.credentials import Credentials  # noqa: PLC0415
            from googleapiclient.discovery import build  # noqa: PLC0415
        except ImportError as exc:
            raise TransportError(
                "Gmail transport needs google-api-python-client and google-auth; "
                "install them or use --transport dry_run"
            ) from exc
        if not self.token_path:
            raise TransportError("GmailTransport requires token_path (an authorised OAuth token)")
        credentials = Credentials.from_authorized_user_file(self.token_path, list(self.SCOPES))
        self._service = build("gmail", "v1", credentials=credentials, cache_discovery=False)
        return self._service

    def deliver(self, message: EmailMessage) -> Delivery:
        import base64  # noqa: PLC0415

        service = self._build_service()
        raw = base64.urlsafe_b64encode(bytes(message)).decode("ascii")
        try:
            sent = (
                service.users()  # type: ignore[attr-defined]
                .messages()
                .send(userId=self.user_id, body={"raw": raw})
                .execute()
            )
        except Exception as exc:
            raise TransportError(f"Gmail delivery failed: {exc}") from exc
        return Delivery(
            provider_message_id=sent.get("id", message["Message-ID"] or ""),
            thread_id=sent.get("threadId"),
        )


def transport_by_name(name: str, **kwargs) -> Transport:
    """CLI helper. ``dry_run`` is the default everywhere for a reason."""
    table = {
        "dry_run": DryRunTransport,
        "file": FileTransport,
        "smtp": SMTPTransport,
        "gmail": GmailTransport,
    }
    if name not in table:
        raise TransportError(f"unknown transport {name!r}; choose one of {sorted(table)}")
    return table[name](**kwargs)  # type: ignore[abstract]

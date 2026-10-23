"""Raw RFC 822 email → the inquiry inside it.

Two shapes arrive at the sales inbox:

- A coach writes directly: the sender is the coach.
- Someone at IGS forwards an inquiry (from their own mailbox, a contact form notification, a
  colleague): the coach is in the forwarded block ("---------- Forwarded message ---------" in
  Gmail, "Begin forwarded message:" in Apple Mail, "-----Original Message-----" in Outlook) or in
  an attached ``message/rfc822``. The forwarder's own note is kept apart from the coach's words.

Quoted history ("On Tue, … wrote:", "> " lines) and signatures are trimmed so extraction only
reads what the coach wrote this time.
"""

from __future__ import annotations

import hashlib
import html
import re
from dataclasses import dataclass
from datetime import datetime
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr, parsedate_to_datetime

_FORWARD_MARKERS = re.compile(
    r"^\s*(-{5,}\s*Forwarded message\s*-{5,}|Begin forwarded message:"
    r"|-{3,}\s*Original Message\s*-{3,})\s*$",
    re.IGNORECASE | re.MULTILINE,
)
_HEADER_LINE = re.compile(r"^\s*\*?(From|De|Date|Sent|Subject|Asunto|To|Para|Cc)\*?:\s*(.*)$", re.I)
_REPLY_MARKER = re.compile(
    r"^\s*(On .{4,200}wrote:|El .{4,200}escribi[óo]:|From: .+|_{5,})\s*$", re.MULTILINE
)
_SIGNATURE = re.compile(r"^\s*(--\s*|Sent from my \w+.*)$", re.MULTILINE)
_TAGS = re.compile(r"<[^>]+>")
_BLOCKS = re.compile(r"</?(p|div|br|tr|li|h\d)[^>]*>", re.IGNORECASE)
_BLANKS = re.compile(r"\n{3,}")
MAX_BODY_CHARS = 8000


@dataclass(frozen=True)
class InboundEmail:
    sender_name: str
    sender_email: str
    subject: str
    text: str
    message_id: str
    in_reply_to: str | None
    received_at: datetime | None
    forwarded: bool
    forwarded_by: str | None = None
    forwarder_note: str = ""
    is_reply: bool = False

    def dedupe_key(self) -> str:
        return "email:" + hashlib.sha256(self.message_id.encode()).hexdigest()[:32]

    def source_text(self) -> str:
        # A reply's subject is our own words ("Re: Your … tour"): only the coach's text counts.
        if self.is_reply:
            return self.text or "(empty)"
        return f"Subject: {self.subject or '—'}\n\n{self.text or '(empty)'}"


def parse_email(raw: bytes) -> InboundEmail:
    msg = message_from_bytes(raw, policy=policy.default)
    assert isinstance(msg, EmailMessage)
    from_name, from_email = parseaddr(str(msg.get("From", "")))
    subject = _clean_subject(str(msg.get("Subject", "")))
    message_id = str(msg.get("Message-ID", "")).strip() or _synthetic_id(raw)
    in_reply_to = str(msg.get("In-Reply-To", "")).strip() or None
    received_at = _date(str(msg.get("Date", "")))

    attached = _attached_message(msg)
    if attached is not None:  # forwarded "as attachment"
        inner = parse_email(attached.as_bytes())
        return InboundEmail(
            sender_name=inner.sender_name,
            sender_email=inner.sender_email,
            subject=inner.subject,
            text=inner.text,
            message_id=message_id,
            in_reply_to=in_reply_to,
            received_at=inner.received_at or received_at,
            forwarded=True,
            forwarded_by=from_email.lower() or None,
            forwarder_note=_trim(_body_text(msg)),
        )

    body = _body_text(msg)
    marker = _FORWARD_MARKERS.search(body)
    if marker is not None:  # forwarded inline
        note, block = body[: marker.start()], body[marker.end() :]
        headers, inner_text = _forwarded_headers(block)
        inner_name, inner_email = parseaddr(headers.get("from", ""))
        if inner_email:
            return InboundEmail(
                sender_name=inner_name or inner_email.split("@")[0],
                sender_email=inner_email.lower(),
                subject=_clean_subject(headers.get("subject", "")) or subject,
                text=_trim(inner_text),
                message_id=message_id,
                in_reply_to=in_reply_to,
                received_at=_date(headers.get("date", "")) or received_at,
                forwarded=True,
                forwarded_by=from_email.lower() or None,
                forwarder_note=_trim(note),
            )

    reply_to = getaddresses([str(msg.get("Reply-To", ""))])
    if reply_to and reply_to[0][1] and _is_notification(from_email):
        # Form notifications ("noreply@…") carry the coach in Reply-To.
        from_name, from_email = reply_to[0]
    raw_subject = str(msg.get("Subject", ""))
    return InboundEmail(
        sender_name=from_name or from_email.split("@")[0],
        sender_email=from_email.lower(),
        subject=subject,
        text=_trim(body),
        message_id=message_id,
        in_reply_to=in_reply_to,
        received_at=received_at,
        forwarded=False,
        is_reply=in_reply_to is not None or bool(re.match(r"\s*re\s*:", raw_subject, re.I)),
    )


def _attached_message(msg: EmailMessage) -> EmailMessage | None:
    for part in msg.walk():
        if part.get_content_type() == "message/rfc822":
            payload = part.get_payload()
            inner = payload[0] if isinstance(payload, list) and payload else payload
            if isinstance(inner, EmailMessage):
                return inner
    return None


def _body_text(msg: EmailMessage) -> str:
    part = msg.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    text = content if isinstance(content, str) else content.decode("utf-8", "replace")
    if part.get_content_type() == "text/html":
        text = html.unescape(_TAGS.sub("", _BLOCKS.sub("\n", text)))
    return text.replace("\r\n", "\n")


def _forwarded_headers(block: str) -> tuple[dict[str, str], str]:
    headers: dict[str, str] = {}
    lines = block.lstrip("\n").split("\n")
    i = 0
    while i < len(lines):
        match = _HEADER_LINE.match(lines[i])
        if match is None:
            if headers and not lines[i].strip():
                i += 1
                break
            if headers:
                break
            i += 1
            continue
        key = {"de": "from", "asunto": "subject", "para": "to", "sent": "date"}.get(
            match.group(1).lower(), match.group(1).lower()
        )
        headers.setdefault(key, match.group(2).strip())
        i += 1
    return headers, "\n".join(lines[i:])


def _trim(text: str) -> str:
    """Drop quoted history and signatures; keep only this message's words."""
    for pattern in (_REPLY_MARKER, _SIGNATURE):
        match = pattern.search(text)
        if match is not None and match.start() > 0:
            text = text[: match.start()]
    kept = [line for line in text.split("\n") if not line.lstrip().startswith(">")]
    return _BLANKS.sub("\n\n", "\n".join(kept)).strip()[:MAX_BODY_CHARS]


def _clean_subject(subject: str) -> str:
    return re.sub(r"^\s*((re|fwd?|rv|reenv)\s*:\s*)+", "", subject, flags=re.IGNORECASE).strip()


def _date(value: str) -> datetime | None:
    try:
        parsed = parsedate_to_datetime(value) if value else None
    except (TypeError, ValueError):
        return None
    return parsed if parsed is not None and parsed.tzinfo is not None else None


def _is_notification(address: str) -> bool:
    local = address.split("@")[0].lower()
    return local in {"noreply", "no-reply", "donotreply", "do-not-reply", "forms", "notifications"}


def _synthetic_id(raw: bytes) -> str:
    return "<sha256-" + hashlib.sha256(raw).hexdigest()[:32] + "@igs-os.local>"
